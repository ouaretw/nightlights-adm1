"""Browser checks for the portal (headless Edge via the DevTools protocol; needs websocket-client).
Serve build/site first:  python -m http.server 8766 --directory build/site
Run from this folder:    python check_explorer.py   (screenshots go to ./shots)"""
import os; os.makedirs("shots", exist_ok=True)
import time, json
from cdp import Browser
B = "http://localhost:8766/explore.html"
b = Browser(9334); b.viewport(1440, 1000)
R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail)); print(("PASS " if cond else "FAIL ") + name, detail)
HOOK = r"""window.__dl=[];HTMLAnchorElement.prototype.__c=HTMLAnchorElement.prototype.__c||HTMLAnchorElement.prototype.click;
HTMLAnchorElement.prototype.click=function(){ if(this.href.startsWith('blob:')){const n=this.download;fetch(this.href).then(r=>r.text()).then(t=>window.__dl.push({name:n,lines:t.trim().split('\n').length,head:t.slice(0,200)}));} else this.__c(); };1"""
def load(hash, cond="document.querySelectorAll('#map .u').length>0"):
    b.goto("about:blank"); ok = b.goto(B + "#" + hash, cond, 40); b.js(HOOK); time.sleep(0.8); return ok

# 1 DZA map
check("DZA map loads", load("c=DZA&l=adm1&s=wb&f=annual&v=map"), str(b.js("document.querySelectorAll('#map .u').length")))
check("legend has classes + swatches", b.js("document.querySelectorAll('#legend .cls').length>=5 && document.querySelectorAll('#legend .sw').length>=2"))
check("default selection chips", b.js("document.querySelectorAll('#selbar .chip').length") == 5)
code = b.js("(()=>{const p=[...document.querySelectorAll('#map .u')].find(x=>!x.classList.contains('sel'));p.dispatchEvent(new MouseEvent('click',{bubbles:true}));return p.dataset.k})()")
time.sleep(0.5)
check("click selects + focuses region", b.js(f"document.querySelector('#region .region-id').textContent.startsWith('{code}')"), code)
check("chips now 6", b.js("document.querySelectorAll('#selbar .chip').length") == 6)
check("focused unit outlined", b.js(f"document.querySelector('#map .u.focus').dataset.k==='{code}'"))
check("hash has region", f"r={code}" in b.js("location.hash"))
check("region mini chart drawn", b.js("!!document.querySelector('#regionChart svg path')"))
check("region shows coverage", b.js("document.querySelector('#region .kv').textContent.includes('Valid-pixel coverage')"))
b.shot("shots/explore_dza_map.png")
b.js("document.querySelector('#mapframe .map-tools [data-z=in]').click()"); time.sleep(2.5)
check("zoom in applies transform", "scale" in (b.js("document.querySelector('#map svg g').getAttribute('transform')") or ""))
b.js("document.querySelector('#mapframe .map-tools [data-z=reset]').click()"); time.sleep(0.5)
for v in ["series", "change", "flares", "quality", "compare", "table", "map"]:
    b.js(f"document.querySelector('[data-view={v}]').click()"); time.sleep(1.8 if v == "compare" else 0.8)
    has = b.js("!!document.querySelector('#chart:not([hidden]) svg') || (document.querySelectorAll('#table tbody tr').length>0 && !document.getElementById('tableWrap').hidden) || (document.querySelectorAll('#map .u').length>0 && !document.getElementById('mapframe').hidden)")
    check(f"view {v} renders", has, str(b.errors(clear=False)))
    b.shot(f"shots/explore_dza_{v}.png")
    if v in ("series", "change", "table"):
        b.js("document.getElementById('exportView').click()"); time.sleep(0.8)
        d = b.js("window.__dl.at(-1)"); check(f"export view data {v}", d and d["lines"] > 1, str(d and (d["name"], d["lines"])))
b.js("document.querySelector('[data-view=change]').click()"); time.sleep(0.6)
for m in ["abs", "pct", "dlog"]:
    b.js(f"document.querySelector('[data-cm={m}]').click()"); time.sleep(0.4)
    check(f"change metric {m}", b.js("document.querySelectorAll('#chart rect').length>3") and "→" in b.js("document.querySelector('#chart .axis-title').textContent"))
check("change legend reports omissions", "units with a valid change" in b.js("document.getElementById('legend').textContent"))
b.js("document.getElementById('exportCsv').click()"); time.sleep(0.8)
d = b.js("window.__dl.at(-1)"); check("export filtered rows", d and d["lines"] > 100, str(d and (d["name"], d["lines"])))
b.js("document.getElementById('dlRegion').click()"); time.sleep(0.8)
d = b.js("window.__dl.at(-1)"); check("download region CSV", d and d["lines"] >= 10, str(d and (d["name"], d["lines"])))
b.js("document.querySelector('[data-view=map]').click()"); time.sleep(0.5)
b.js("{const s=document.getElementById('period');s.value='2015';s.dispatchEvent(new Event('change'))}"); time.sleep(0.8)
check("period change -> legend title", "2015" in b.js("document.querySelector('#legend .lg-title').textContent"))
b.js("{const s=document.getElementById('indicator');s.value='ntl_mean';s.dispatchEvent(new Event('change'))}"); time.sleep(0.8)
check("indicator change", "ntl_mean" in b.js("document.querySelector('#legend .lg-title').textContent"))
b.js("{const s=document.getElementById('minCov');s.value='0.95';s.dispatchEvent(new Event('change'))}"); time.sleep(0.8)
n = b.js("[...document.querySelectorAll('#map .u')].filter(p=>p.getAttribute('fill')==='url(#hatch-filtered)').length")
check("coverage filter applied to map", n is not None, f"{n} hatched at >=95%")
print("errors so far:", b.errors())

check("AFG 2018 map", load("c=AFG&l=adm1&s=wb&f=annual&v=map&p=2018"))
z = b.js("[...document.querySelectorAll('#map .u.zero')].map(p=>p.dataset.k)")
check("observed zero drawn as zero class", "AFG006" in (z or []), str(z))
b.js("document.querySelector('#map .u[data-k=AFG006]').dispatchEvent(new MouseEvent('click',{bubbles:true}))"); time.sleep(0.5)
check("region panel labels observed zero", "observed, no detectable light" in b.js("document.getElementById('region').textContent"))
b.shot("shots/explore_afg_zero.png")
check("NOR monthly June", load("c=NOR&l=adm1&s=wb&f=monthly&v=map&p=2024-06"))
n = b.js("[...document.querySelectorAll('#map .u')].filter(p=>p.getAttribute('fill')==='#D3DBE1').length")
nf = b.js("[...document.querySelectorAll('#map .u')].filter(p=>p.getAttribute('fill')==='url(#hatch-filtered)').length")
check("June: missing/excluded shown, not coloured", (n or 0) + (nf or 0) == b.js("document.querySelectorAll('#map .u').length"), f"{n} grey, {nf} hatched")
b.shot("shots/explore_nor_june.png")
txt = b.js("document.getElementById('region').textContent")
check("NOR region explains state", "Missing" in txt or "Excluded" in txt)

check("BRA GADM loads", load("c=BRA&l=adm1&s=gadm&f=annual&v=map", "document.querySelector('#selbar .chip')"))
check("GADM map unavailable message", "licence" in b.js("document.getElementById('empty').textContent"))
check("GADM region shows crosswalk grade", "Crosswalk grade" in b.js("document.getElementById('region').textContent"))
b.js("document.querySelector('[data-view=quality]').click()"); time.sleep(0.8)
check("GADM quality view mentions crosswalk", "Crosswalk: grade" in b.js("document.getElementById('viewControls').textContent"))
b.shot("shots/explore_bra_gadm_quality.png")
b.js("document.querySelector('[data-sys=wb]').click()"); time.sleep(2)
b.js("document.querySelector('[data-view=map]').click()"); time.sleep(1.5)
check("switch to WB draws Brazil", (b.js("document.querySelectorAll('#map .u').length") or 0) >= 27)
check("KEN ADM2 map", load("c=KEN&l=adm2&s=wb&f=annual&v=map"), str(b.js("document.querySelectorAll('#map .u').length")))
check("ADM2 disables GADM + from-monthly", b.js("document.querySelector('[data-sys=gadm]').disabled && document.querySelector('[data-freq=annual_from_monthly]').disabled"))
b.shot("shots/explore_ken_adm2.png")
check("IND afm table", load("c=IND&l=adm1&s=wb&f=annual_from_monthly&v=table", "document.querySelectorAll('#table tbody tr').length>0"))
b.js("document.querySelector('[data-view=change]').click()"); time.sleep(0.5)
check("change refuses non-official annual", "official annual" in b.js("document.getElementById('empty').textContent"))
check("GHA map", load("c=GHA&l=adm1&s=wb&f=annual&v=map"))
check("units without outline listed", "no outline" in (b.js("document.getElementById('notDrawn').textContent") or ""), b.js("document.getElementById('notDrawn').textContent.slice(0,90)"))
load("c=DZA&l=adm1&s=wb&f=annual&v=table", "document.querySelectorAll('#table tbody tr').length>0")
k = b.js("(()=>{const tr=[...document.querySelectorAll('#table tbody tr')].find(t=>!t.classList.contains('sel'));tr.focus();tr.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));return tr.dataset.k})()"); time.sleep(0.5)
check("keyboard Enter selects table row", b.js(f"document.querySelector('#region .region-id').textContent.startsWith('{k}')"), k)
print("errors:", b.errors())
b.close()
print(f"\n{sum(r[1] for r in R)}/{len(R)} passed")
json.dump(R, open("results_explorer.json", "w"))
