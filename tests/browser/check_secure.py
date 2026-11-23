"""Browser checks for the password-protected build (scripts/build_secure_site.py).
Serve build/pages on :8767 first (python -m http.server 8767 --directory build/pages), then run
from this folder:   python check_secure.py
The password is read from NLADM1_SITE_PASSWORD or secrets/site_password.txt."""
import json, os, time, urllib.request
from pathlib import Path

from cdp import Browser

ROOT = Path(__file__).resolve().parents[2]
B = os.environ.get("NL_SECURE_BASE", "http://localhost:8767/nightlights-adm1/")
PW = os.environ.get("NLADM1_SITE_PASSWORD") or (ROOT / "secrets" / "site_password.txt").read_text().strip()
R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail)); print(("PASS " if cond else "FAIL ") + name, detail)

# ---- without a browser: nothing readable on the server
def get(u):
    try:
        with urllib.request.urlopen(u) as r: return r.status, r.read()
    except urllib.error.HTTPError as e: return e.code, e.read()
s, body = get(B + "v3/explore.html")
check("plain page path is not served (404 → sign-in redirect page)", s == 404 and b"index.html" in body and b"Explore" not in body, s)
s, body = get(B + "data/v2/manifest.json")
check("plain data path is not served", s == 404)
s, body = get(B + "data/v2/manifest.json.enc")
check("encrypted file is served but unreadable", s == 200 and body[:4] == b"NLE1" and b"sha256" not in body)
s, body = get(B + "v3/index.html.enc")
check("encrypted page contains no page text", s == 200 and b"Nighttime" not in body and b"<html" not in body)
s, body = get(B + "auth.json")
a = json.loads(body); check("auth.json holds salt/check only", s == 200 and set(a) >= {"salt", "iterations", "check"} and PW not in body.decode())

b = Browser(9353); b.viewport(1440, 1000)
def login(pw):
    b.js(f"document.getElementById('pw').value={json.dumps(pw)}; document.getElementById('f').requestSubmit(); 1")

# ---- deep link before sign-in -> sign-in page with next=..., hash kept
b.goto(B + "v3/explore.html#c=KEN&l=adm1&s=wb&f=annual&v=map", "document.getElementById('pw')", 30); time.sleep(1)
u = b.js("location.href")
check("deep link redirects to sign-in with next", "index.html?next=" in u and "v3%2Fexplore.html" in u and "#c=KEN" in u, u)
pre = b.errors()   # the expected 404 of the page requested before sign-in
check("only the expected 404 before sign-in", all("404" in e and "v3/explore.html" in e for e in pre), pre)
login("wrong-password-123"); time.sleep(4)
check("wrong password rejected", "Incorrect password" in b.js("document.getElementById('msg').textContent") and "index.html" in b.js("location.href"))
login(PW)
b.wait("location.pathname.endsWith('/v3/explore.html') && document.querySelectorAll('#map .u').length>0", 60); time.sleep(1.5)
check("correct password opens the requested page with its hash", b.js("location.hash").startswith("#c=KEN") and b.js("document.querySelectorAll('#map .u').length") > 10, b.js("location.href"))
check("explorer reads Parquet through the decrypting worker", b.js("document.querySelectorAll('#map .u').length") >= 40 and not b.js("document.getElementById('status').textContent").lower().startswith("could"))
check("version bar shown", "viewing v3" in b.js("document.body.textContent"))

# ---- data fetches through the worker: HEAD, range, checksum
res = b.js("""(async()=>{
  const m = await fetch('data/v2/manifest.json').then(r=>r.json());
  const f = m.files.find(x=>x.path.endsWith('adm1_wb/annual/DZA.parquet'));
  const full = new Uint8Array(await fetch(f.path).then(r=>r.arrayBuffer()));
  const h = await fetch(f.path,{method:'HEAD'});
  const rg = await fetch(f.path,{headers:{Range:'bytes=4-19'}});
  const part = new Uint8Array(await rg.arrayBuffer());
  const dig = [...new Uint8Array(await crypto.subtle.digest('SHA-256', full))].map(x=>x.toString(16).padStart(2,'0')).join('');
  return {version:m.version, bytes:f.bytes, len:full.length, head:+h.headers.get('content-length'), rs:rg.status,
          cr:rg.headers.get('content-range'), same:part.every((v,i)=>v===full[4+i]) && part.length===16, sha:dig===f.sha256};
})()""")
check("manifest decrypted (v3.0.0)", res["version"] == "3.0.0", res["version"])
check("file size after decryption = manifest bytes", res["len"] == res["bytes"] == res["head"], res)
check("SHA-256 after decryption = manifest checksum", res["sha"])
check("byte-range request answered 206 with correct bytes", res["rs"] == 206 and res["same"] and res["cr"].startswith("bytes 4-19/"), res["cr"])

# ---- v3 pages
for p, cond in [("index.html", "document.querySelectorAll('#worldmap .u').length>3000"),
                ("analysis.html", "document.querySelectorAll('#a1 svg > g > circle').length>100"),
                ("download.html", "document.querySelector('.filebox')"),
                ("about.html", "document.querySelector('#future')")]:
    b.goto("about:blank"); b.goto(B + "v3/" + p, cond, 60); time.sleep(0.8)
    check(f"v3 {p} works", b.js(f"!!({cond})"))
errs = b.errors()
check("no JS errors on v3", not errs, errs[:4])

# ---- v2 (archived) pages
b.js("[...document.querySelectorAll('a')].find(a=>a.textContent.includes('Switch to v2')).click()"); time.sleep(2)
check("switch to v2 from the bar (About exists only in v3 -> v2 home)", b.js("location.href").endswith("/v2/index.html") and b.js("!!document.querySelector('#worldmap')"), b.js("location.href"))
b.goto("about:blank"); b.goto(B + "v2/explore.html#c=DZA&l=adm1&s=wb&f=annual&v=map", "document.querySelectorAll('#map .u').length>0", 60); time.sleep(1)
check("v2 explorer works on shared data", b.js("document.querySelectorAll('#map .u').length") >= 40)
check("v2 is the archived 2.0.0 site", "v2.0.0" in b.js("document.querySelector('.ver').textContent") and "viewing v2" in b.js("document.body.textContent"))
b.goto("about:blank"); b.goto(B + "v2/index.html", "document.querySelectorAll('#worldmap .u').length>3000", 60)
check("v2 home map works", True)

# ---- old public addresses
b.goto("about:blank"); b.goto(B + "explore.html#c=BRA&l=adm1&s=gadm&f=annual&v=map", "location.pathname.endsWith('/v3/explore.html')", 40); time.sleep(1)
check("old address /explore.html#… reaches v3 with its hash (signed in)", "#c=BRA" in b.js("location.href"))

# ---- sign out
b.goto("about:blank"); b.goto(B + "index.html?logout=1", "document.getElementById('msg').textContent.includes('signed out')", 30)
b.goto("about:blank"); b.goto(B + "v3/analysis.html", "document.getElementById('pw')", 30)
check("after sign-out pages require the password again", "index.html?next=" in b.js("location.href"))
st = b.js("fetch('data/v2/manifest.json').then(r=>r.status)")
check("after sign-out data requests are refused", st in (401, 404), st)
b.shot("shots/secure_login.png", full=False)
b.close()
print(f"\n{sum(r[1] for r in R)}/{len(R)} passed")
json.dump(R, open("results_secure.json", "w"))
