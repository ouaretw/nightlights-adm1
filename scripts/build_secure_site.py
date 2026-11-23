"""Assemble the password-protected site that is published to GitHub Pages.

Layout of the output (default build/pages/nightlights-adm1/, served at BASE):
  index.html, login.js, login.css, sw.js, auth.json   public sign-in shell (site_auth/)
  404.html, robots.txt, <old page>.html               public redirects to the sign-in page
  v3/**.enc     current site (build/site without data/)
  v2/**.enc     archived v2.0.0 site (archive/site_v2.0.0/)
  data/**.enc   data files shared by both versions (build/site/data/)

Every non-public file is encrypted with AES-256-GCM under one of two random content keys:
  key "2"  v2 pages, the data files v2.0.0 published (unchanged since; checked against
           archive/site_v2.0.0_data_files.txt) and v2's own copy of the v2.0.0 manifest
  key "3"  v3 pages and the data files that exist only in v3 (including the v3 manifest)
File format: b"NLE2" + key id (1 byte) + 12-byte nonce + ciphertext + 16-byte tag (the first
5 bytes are authenticated as associated data).

Passwords (each turned into a wrapping key with PBKDF2-HMAC-SHA-256, 600,000 iterations,
its own random salt; auth.json holds the content keys wrapped under each password):
  full access (v2 + v3): NLADM1_SITE_PASSWORD    or secrets/site_password.txt (required)
  v2 only:               NLADM1_SITE_PASSWORD_V2 or secrets/site_password_v2.txt (optional)
Usage:
    python scripts/build_secure_site.py [--out build/pages/nightlights-adm1] [--base /nightlights-adm1/]
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "build" / "site"
V2 = ROOT / "archive" / "site_v2.0.0"
AUTH = ROOT / "site_auth"
ITER = 600_000
CHECK_TEXT = "nightlights-adm1:signed-in"
OLD_PAGES = ["explore", "analysis", "about", "download", "methods", "integration", "docs"]


V2_DATA_LIST = ROOT / "archive" / "site_v2.0.0_data_files.txt"
V2_OWN = {"data/v2/manifest.json": V2 / "manifest_v2.0.0.json"}   # v2 files that differ in v3


def password(env: str, file: str, required: bool = True) -> str | None:
    pw = os.environ.get(env)
    if not pw:
        f = ROOT / "secrets" / file
        if not f.exists():
            if required:
                raise SystemExit(f"No password: set {env} or create secrets/{file}")
            return None
        pw = f.read_text(encoding="utf-8").strip()
    if len(pw) < 12:
        raise SystemExit(f"Password in {env} / secrets/{file} too short (minimum 12 characters)")
    return pw


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def v2_data() -> dict[str, str]:
    rows = [l.split(" ", 1) for l in V2_DATA_LIST.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    return {p: h for h, p in rows}


def bar(version: str, page: str) -> str:
    other, label = ("v2", "v2 (archived 2026-11-21)") if version == "v3" else ("v3", "v3 (current)")
    other_dir = V2 if other == "v2" else SITE
    target = page if (other_dir / page).exists() else "index.html"
    here = "v3 (current)" if version == "v3" else "v2 (archived 2026-11-21)"
    # on v2 pages the link to v3 stays hidden unless this browser holds the v3 key
    hide = ' hidden' if version == "v2" else ''
    reveal = ('<script>fetch("../__access.json").then(function(r){return r.json()}).then(function(a){'
              'if(a.v3)document.getElementById("nl-switch").hidden=false}).catch(function(){})</script>') if version == "v2" else ''
    return (f'<div style="background:#11263B;color:#DCE6ED;font:500 13px/1.4 \'IBM Plex Sans\',system-ui,sans-serif;'
            f'padding:6px 16px;display:flex;flex-wrap:wrap;gap:6px 16px;justify-content:center" role="note">'
            f'<span>Night Lights ADM1 · viewing <b style="color:#fff">{here}</b></span>'
            f'<a id="nl-switch" style="color:#E5AD4E" href="../{other}/{target}"{hide}>Switch to {label}</a>'
            f'<a style="color:#DCE6ED" href="../index.html?logout=1">Sign out</a></div>{reveal}')


def inject(html: str, version: str, page: str) -> str:
    html = html.replace("<head>", '<head>\n<meta name="robots" content="noindex, nofollow">', 1)
    return re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + bar(version, page), html, count=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "build" / "pages" / "nightlights-adm1"))
    ap.add_argument("--base", default="/nightlights-adm1/")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    if ROOT / "build" not in out.parents:
        raise SystemExit("--out must be inside build/")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    pw_full = password("NLADM1_SITE_PASSWORD", "site_password.txt")
    pw_v2 = password("NLADM1_SITE_PASSWORD_V2", "site_password_v2.txt", required=False)
    if pw_v2 == pw_full:
        raise SystemExit("The v2-only password must differ from the full-access password")
    keys = {"2": secrets.token_bytes(32), "3": secrets.token_bytes(32)}
    aes = {k: AESGCM(v) for k, v in keys.items()}

    def seal(data: bytes, kid: str) -> bytes:
        head, iv = b"NLE2" + kid.encode(), secrets.token_bytes(12)
        return head + iv + aes[kid].encrypt(iv, data, head)

    def login(pw: str, scopes: list[str]) -> dict:
        salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
        kek = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(pw.encode("utf-8"))
        body = json.dumps({"scopes": scopes, "keys": {v[1]: base64.b64encode(keys[v[1]]).decode() for v in scopes}}).encode()
        return {"salt": base64.b64encode(salt).decode(),
                "wrapped": base64.b64encode(iv + AESGCM(kek).encrypt(iv, body, b"nladm1-login")).decode()}

    v2d = v2_data()
    for rel, src in V2_OWN.items():
        if git_blob(src.read_bytes()) != v2d[rel]:
            raise SystemExit(f"{src} is not the published v2.0.0 {rel}")
    jobs = []   # (source, destination, transform, key id, expected v2.0.0 git blob)
    for p in SITE.rglob("*"):
        if p.is_file():
            rel = p.relative_to(SITE).as_posix()
            if rel.startswith("data/"):
                shared = rel in v2d and rel not in V2_OWN
                jobs.append((p, out / (rel + ".enc"), None, "2" if shared else "3", v2d[rel] if shared else None))
            elif rel != ".nojekyll":
                jobs.append((p, out / "v3" / (rel + ".enc"), ("v3", rel) if rel.endswith(".html") else None, "3", None))
    shared_rel = {j[0].relative_to(SITE).as_posix() for j in jobs if j[3] == "2"}
    missing = sorted(set(v2d) - set(V2_OWN) - shared_rel)
    if missing:
        raise SystemExit(f"{len(missing)} v2.0.0 data files are missing from build/site, e.g. {missing[:3]}")
    for rel, src in V2_OWN.items():
        jobs.append((src, out / "v2" / (rel + ".enc"), None, "2", None))
    for p in V2.rglob("*"):
        if p.is_file() and p.name != "manifest_v2.0.0.json":
            rel = p.relative_to(V2).as_posix()
            jobs.append((p, out / "v2" / (rel + ".enc"), ("v2", rel) if rel.endswith(".html") else None, "2", None))

    def run(job):
        src, dst, tr, kid, blob = job
        data = src.read_bytes()
        if blob and git_blob(data) != blob:
            raise SystemExit(f"{src} changed since v2.0.0; the v2-only password cannot be given the new version. "
                             "Add the v2.0.0 copy to V2_OWN (and to the V2_OWN list in sw.js).")
        if tr:
            data = inject(data.decode("utf-8"), *tr).encode("utf-8")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(seal(data, kid))
        return len(data)

    with ThreadPoolExecutor(max_workers=8) as ex:
        total = sum(ex.map(run, jobs))

    # public shell
    build = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for f in ("index.html", "login.js", "login.css"):
        shutil.copyfile(AUTH / f, out / f)
    sw = (AUTH / "sw.js").read_text(encoding="utf-8")
    assert '["__V2_OWN__"]' in sw
    (out / "sw.js").write_text(sw.replace("__BUILD__", build).replace('["__V2_OWN__"]', json.dumps(sorted(V2_OWN))),
                               encoding="utf-8")
    logins = [login(pw_full, ["v2", "v3"])] + ([login(pw_v2, ["v2"])] if pw_v2 else [])
    (out / "auth.json").write_text(json.dumps({
        "format": "NLE2", "kdf": "PBKDF2-HMAC-SHA-256", "iterations": ITER, "cipher": "AES-256-GCM",
        "logins": logins, "checks": {k: base64.b64encode(seal(CHECK_TEXT.encode(), k)).decode() for k in keys},
        "check_text": CHECK_TEXT, "build": build}, indent=1), encoding="utf-8")
    redirect = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="robots" content="noindex, nofollow">'
                '<title>Night Lights ADM1</title></head><body><script>{js}</script>'
                '<p style="font-family:sans-serif;padding:2em">Opening the <a href="{base}index.html">sign-in page</a>…</p></body></html>')
    for page in OLD_PAGES:          # old public addresses keep working (after sign-in), with their #hash
        (out / f"{page}.html").write_text(redirect.format(base=a.base, js=(
            f'location.replace("index.html?next=v3/{page}.html"+location.hash)')), encoding="utf-8")
    (out / "404.html").write_text(redirect.format(base=a.base, js=(
        f'var B={json.dumps(a.base)},p=location.pathname,r=p.indexOf(B)===0?p.slice(B.length):"";'
        'if(/^(v2|v3|data)\\//.test(r))location.replace(B+"index.html?next="+encodeURIComponent(r+location.search)+location.hash);'
        'else location.replace(B+"index.html");')), encoding="utf-8")
    (out / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    n_enc = sum(1 for _ in out.rglob("*.enc"))
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    by_key = {k: sum(1 for j in jobs if j[3] == k) for k in keys}
    print(f"encrypted {n_enc} files ({total / 1e6:,.0f} MB plaintext; key 2: {by_key['2']}, key 3: {by_key['3']}); "
          f"logins: full{' + v2-only' if pw_v2 else ' only (no v2-only password)'}; output {size / 1e6:,.0f} MB at {out}")


if __name__ == "__main__":
    main()
