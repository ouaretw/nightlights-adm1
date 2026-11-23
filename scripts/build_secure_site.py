"""Assemble the password-protected site that is published to GitHub Pages.

Layout of the output (default build/pages/nightlights-adm1/, served at BASE):
  index.html, login.js, login.css, sw.js, auth.json   public sign-in shell (site_auth/)
  404.html, robots.txt, <old page>.html               public redirects to the sign-in page
  v3/**.enc     current site (build/site without data/)
  v2/**.enc     archived v2.0.0 site (archive/site_v2.0.0/)
  data/**.enc   data files shared by both versions (build/site/data/)

Every non-public file is encrypted with AES-256-GCM. The key is derived from the shared
password with PBKDF2-HMAC-SHA-256 (600,000 iterations, random salt) and never stored.
File format: b"NLE1" + 12-byte nonce + ciphertext + 16-byte tag.

The password is read from the environment variable NLADM1_SITE_PASSWORD or from
secrets/site_password.txt (git-ignored). Usage:
    python scripts/build_secure_site.py [--out build/pages/nightlights-adm1] [--base /nightlights-adm1/]
"""
from __future__ import annotations

import argparse
import base64
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


def password() -> str:
    pw = os.environ.get("NLADM1_SITE_PASSWORD")
    if not pw:
        f = ROOT / "secrets" / "site_password.txt"
        if not f.exists():
            raise SystemExit("No password: set NLADM1_SITE_PASSWORD or create secrets/site_password.txt")
        pw = f.read_text(encoding="utf-8").strip()
    if len(pw) < 12:
        raise SystemExit("Password too short (minimum 12 characters)")
    return pw


def bar(version: str, page: str) -> str:
    other, label = ("v2", "v2 (archived 2026-11-21)") if version == "v3" else ("v3", "v3 (current)")
    other_dir = V2 if other == "v2" else SITE
    target = page if (other_dir / page).exists() else "index.html"
    here = "v3 (current)" if version == "v3" else "v2 (archived 2026-11-21)"
    return (f'<div style="background:#11263B;color:#DCE6ED;font:500 13px/1.4 \'IBM Plex Sans\',system-ui,sans-serif;'
            f'padding:6px 16px;display:flex;flex-wrap:wrap;gap:6px 16px;justify-content:center" role="note">'
            f'<span>Night Lights ADM1 · viewing <b style="color:#fff">{here}</b></span>'
            f'<a style="color:#E5AD4E" href="../{other}/{target}">Switch to {label}</a>'
            f'<a style="color:#DCE6ED" href="../index.html?logout=1">Sign out</a></div>')


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

    salt = secrets.token_bytes(16)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(password().encode("utf-8"))
    aes = AESGCM(key)

    def seal(data: bytes) -> bytes:
        iv = secrets.token_bytes(12)
        return b"NLE1" + iv + aes.encrypt(iv, data, None)

    jobs = []   # (source, destination, transform)
    for p in SITE.rglob("*"):
        if p.is_file():
            rel = p.relative_to(SITE).as_posix()
            if rel.startswith("data/"):
                jobs.append((p, out / (rel + ".enc"), None))
            elif rel != ".nojekyll":
                jobs.append((p, out / "v3" / (rel + ".enc"), ("v3", rel) if rel.endswith(".html") else None))
    for p in V2.rglob("*"):
        if p.is_file() and p.name != "manifest_v2.0.0.json":
            rel = p.relative_to(V2).as_posix()
            jobs.append((p, out / "v2" / (rel + ".enc"), ("v2", rel) if rel.endswith(".html") else None))

    def run(job):
        src, dst, tr = job
        data = src.read_bytes()
        if tr:
            data = inject(data.decode("utf-8"), *tr).encode("utf-8")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(seal(data))
        return len(data)

    with ThreadPoolExecutor(max_workers=8) as ex:
        total = sum(ex.map(run, jobs))

    # public shell
    build = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for f in ("index.html", "login.js", "login.css"):
        shutil.copyfile(AUTH / f, out / f)
    (out / "sw.js").write_text((AUTH / "sw.js").read_text(encoding="utf-8").replace("__BUILD__", build), encoding="utf-8")
    (out / "auth.json").write_text(json.dumps({
        "format": "NLE1", "kdf": "PBKDF2-HMAC-SHA-256", "iterations": ITER, "cipher": "AES-256-GCM",
        "salt": base64.b64encode(salt).decode(), "check": base64.b64encode(seal(CHECK_TEXT.encode())).decode(),
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
    print(f"encrypted {n_enc} files ({total / 1e6:,.0f} MB plaintext); output {size / 1e6:,.0f} MB at {out}")


if __name__ == "__main__":
    main()
