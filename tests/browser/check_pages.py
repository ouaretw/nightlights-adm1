"""Browser checks for the portal (headless Edge via the DevTools protocol; needs websocket-client).
Serve build/site first:  python -m http.server 8766 --directory build/site
Run from this folder:    python check_pages.py   (screenshots go to ./shots)"""
import os; os.makedirs("shots", exist_ok=True)
import time, json, itertools
from cdp import Browser
S = "http://localhost:8766/"
b = Browser(9337); b.viewport(1440, 1000)
R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail)); print(("PASS " if cond else "FAIL ") + name, detail)

# ---------------- home map
b.goto(S + "index.html", "document.querySelectorAll('#worldmap .u').length>3000"); time.sleep(1)
check("home map units", b.js("document.querySelectorAll('#worldmap .u').length") > 3000)
b.js("(()=>{const p=document.querySelector('#worldmap .u');const r=p.getBoundingClientRect();p.dispatchEvent(new MouseEvent('mousemove',{bubbles:true,clientX:r.x+r.width/2,clientY:r.y+r.height/2}))})()")
time.sleep(0.3)
check("home tooltip shows value + coverage", b.js("!document.getElementById('wmTip').hidden && document.getElementById('wmTip').textContent.includes('coverage')"))
b.js("document.querySelector('[data-wm=sum]').click()"); time.sleep(0.4)
check("indicator toggle updates legend", "Sum of radiance" in b.js("document.getElementById('wmLegend').textContent"))
b.js("{const y=document.getElementById('wmYear');y.value=0;y.dispatchEvent(new Event('input'))}"); time.sleep(0.4)
check("year slider updates title", "2012" in b.js("document.getElementById('wmTitle').textContent"))
b.js("{const c=document.getElementById('wmCountry');c.value='Brazil (BRA)';c.dispatchEvent(new Event('change'))}"); time.sleep(2.5)
check("zoom to country", not b.js("document.getElementById('wmOpen').hidden") and "scale" in (b.js("document.querySelector('#worldmap svg > g').getAttribute('transform')") or ""))
b.js("document.querySelector('#worldmap .u').dispatchEvent(new MouseEvent('click',{bubbles:true}))"); time.sleep(2)
u = b.js("location.href")
check("click province -> explorer deep link", "explore.html#c=" in u and "&r=" in u and "&p=2012" in u, u)
b.wait("document.querySelector('#region .region-id')", 30)
check("deep link opens region details", b.js("!!document.querySelector('#region .region-id')"))
print("errors:", b.errors())

# ---------------- download picker
b.goto(S + "download.html", "document.querySelector('.filebox')"); time.sleep(0.6)
combos = {}
for L, F, Sc, K in itertools.product(["adm1_wb", "adm1_gadm41", "adm2"], ["annual", "monthly", "annual_from_monthly"], ["global", "country"], ["csv", "parquet", "stata"]):
    b.js(f"document.querySelector('[data-pl={L}]').click()"); b.js(f"document.querySelector('[data-pf={F}]').click()")
    b.js(f"document.querySelector('[data-ps={Sc}]').click()")
    if Sc == "country": b.js("{const s=document.getElementById('pCountry');s.value='DZA';s.dispatchEvent(new Event('change'))}")
    b.js(f"document.querySelector('[data-pk={K}]').click()")
    info = b.js("(()=>{const a=document.querySelector('.filebox a.btn');return {href:a?a.getAttribute('href'):null, title:document.querySelector('.result-head h2').textContent, fname:document.querySelector('.filebox .fname').textContent, alts:[...document.querySelectorAll('.filebox li a')].map(x=>x.getAttribute('href'))}})()")
    combos[(L, F, Sc, K)] = info
hrefs = set()
for k, v in combos.items():
    for h in ([v["href"]] if v["href"] else []) + v["alts"]:
        if h and not h.startswith("explore"): hrefs.add(h)
local = [h for h in hrefs if not h.startswith("http")]
status = b.js("Promise.all(" + json.dumps(local) + ".map(u=>fetch(u,{method:'HEAD'}).then(r=>[u,r.status])))")
bad = [s for s in status if s[1] != 200]
check("all local picker links resolve (HEAD 200)", not bad, f"{len(local)} links, bad={bad[:5]}")
rel = sorted(h for h in hrefs if h.startswith("http"))
json.dump(rel, open("release_links.json", "w"))
n_direct = sum(1 for v in combos.values() if v["href"])
print(f"picker: {n_direct}/{len(combos)} combinations resolve to a single file; others show real alternatives")
adm2afm = combos[("adm2", "annual_from_monthly", "global", "csv")]
check("ADM2 from-monthly button disabled (keeps previous frequency)", "from monthly" not in adm2afm["title"], adm2afm["title"])
print(json.dumps({"|".join(k): (v["href"] or "ALT:" + ",".join(v["alts"])) for k, v in list(combos.items())[:18]}, indent=0)[:2500])
print("errors:", b.errors())

# ---------------- links on every page
allbad = []
for p in ["index", "explore", "integration", "download", "methods", "docs"]:
    b.goto(S + p + ".html"); time.sleep(0.8)
    links = b.js("[...new Set([...document.querySelectorAll('a[href]')].map(a=>a.getAttribute('href')))]")
    loc = [l for l in links if not l.startswith(("http", "#", "mailto", "blob")) and "#" not in l.split("/")[-1][:1]]
    loc = sorted({l.split("#")[0] for l in loc if l.split("#")[0]})
    st = b.js("Promise.all(" + json.dumps(loc) + ".map(u=>fetch(u,{method:'HEAD'}).then(r=>[u,r.status]).catch(e=>[u,0])))")
    allbad += [(p, s) for s in st if s[1] != 200]
    ext = [l for l in links if l.startswith("http")]
    json.dump(sorted(set(ext)), open(f"ext_{p}.json", "w"))
check("all internal links on 6 pages resolve", not allbad, str(allbad[:8]))

# ---------------- responsive
for w, h, mob in [(1440, 900, False), (1024, 800, False), (768, 1000, True), (390, 844, True)]:
    b.viewport(w, h, mob)
    for p, extra in [("index", ""), ("explore", "#c=DZA&l=adm1&s=wb&f=annual&v=map"), ("integration", ""), ("download", ""), ("methods", ""), ("docs", "")]:
        b.goto("about:blank"); b.goto(S + p + ".html" + extra); time.sleep(2.2 if p in ("index", "explore") else 0.8)
        ov = b.js("document.documentElement.scrollWidth - window.innerWidth")
        check(f"no horizontal overflow {p} @{w}", ov <= 0, str(ov))
        if w in (390, 1024) and p in ("index", "explore", "download", "integration"): b.shot(f"shots/{p}_{w}.png")
    if w == 390:
        b.goto("about:blank"); b.goto(S + "explore.html#c=DZA&l=adm1&s=wb&f=annual&v=map", "document.querySelectorAll('#map .u').length>0"); time.sleep(1)
        check("mobile: filters collapsed by default", b.js("document.getElementById('controls').classList.contains('collapsed')"))
        b.js("document.getElementById('filtersToggle').click()"); time.sleep(0.3)
        check("mobile: filters toggle opens", not b.js("document.getElementById('controls').classList.contains('collapsed')") and b.js("document.getElementById('filtersToggle').getAttribute('aria-expanded')") == "true")
        b.js("document.querySelector('.navtoggle').click()"); time.sleep(0.2)
        check("mobile: nav menu opens", b.js("document.getElementById('nav').classList.contains('open')"))
print("errors:", b.errors())
b.close()
print(f"\n{sum(r[1] for r in R)}/{len(R)} passed")
json.dump(R, open("results_pages.json", "w"))
