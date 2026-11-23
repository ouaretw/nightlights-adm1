"""Browser checks for the Economic Analysis page and the explorer's region context
(headless Edge via CDP; serve build/site on :8766 first).
Run from this folder:    python check_analysis.py   (screenshots go to ./shots)"""
import csv, io, json, math, time
from pathlib import Path

import pandas as pd
from cdp import Browser

S = "http://localhost:8766/"
DATA = Path(__file__).resolve().parents[2] / "build" / "site" / "data" / "v2"
HOOK = r"""window.__dl=[];HTMLAnchorElement.prototype.__c=HTMLAnchorElement.prototype.__c||HTMLAnchorElement.prototype.click;
HTMLAnchorElement.prototype.click=function(){ if(this.href.startsWith('blob:')){const n=this.download;fetch(this.href).then(r=>r.text()).then(t=>window.__dl.push({name:n,text:t}));} else this.__c(); };1"""
R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond), detail)); print(("PASS " if cond else "FAIL ") + name, detail)
def n(sel): return b.js(f"document.querySelectorAll({json.dumps(sel)}).length")
def text(id_): return b.js(f"document.getElementById('{id_}').textContent")
def last_csv():
    time.sleep(0.6); d = b.js("window.__dl.at(-1)")
    return (d["name"], list(csv.DictReader(io.StringIO(d["text"].lstrip("﻿"))))) if d else (None, [])

nat = pd.read_parquet(DATA / "adm0" / "ntl_adm0_annual_econ.parquet")
adm1 = pd.read_parquet(DATA / "adm1_wb" / "adm1_wb_annual_global.parquet")
b = Browser(9341); b.viewport(1440, 1000)
b.goto(S + "analysis.html", "document.querySelectorAll('#a1 circle').length>100 && document.querySelectorAll('#c1 circle').length>100", 60)
time.sleep(1); b.js(HOOK)

# ---------------- module A
check("A1 scatter drawn (countries)", n("#a1 svg > g > circle") > 150, n("#a1 svg > g > circle"))
check("A1 caption reports n and sources", "n = " in text("a1Cap") and "WDI" in text("a1Cap"), text("a1Cap")[:90])
check("A2 group statistics with AUC", "AUC" in text("a2Stats") and "Mann" in text("a2Stats"))
check("A3 ranking table", n("#a3 tbody tr") > 150)
check("A4 correlation table", n("#a4 tbody tr") == 4)
b.js("document.querySelector('[data-export=a3]').click()"); name, rows = last_csv()
d = nat[nat.year == 2022].set_index("iso3")
bad = [r["iso3"] for r in rows if not math.isclose(float(r["ntl_mean"]), d.loc[r["iso3"], "ntl_mean"], rel_tol=1e-4)]
check("A3 export = national panel values (mean, 2022)", rows and not bad, f"{name} rows={len(rows)} bad={bad[:5]}")
order = [float(r["ntl_mean"]) for r in rows]
check("A3 ranking sorted descending", order == sorted(order, reverse=True))
b.js("document.querySelector('#a3 tbody tr[data-iso=AUS]').click()"); time.sleep(0.5)
check("clicking a ranked country highlights it", "Australia" in b.js("document.getElementById('aFind').value") and n("#a1 .pt-label") >= 1)
b.js("document.querySelector('[data-m=pc]').click()"); time.sleep(0.5)
check("per-person measure", "per person" in text("a1Title"))
b.js("document.querySelector('[data-export=a1]').click()"); name, rows = last_csv()
r_usa = next((r for r in rows if r["iso3"] == "USA"), None)
exp = d.loc["USA", "ntl_sum_per_capita"]
check("A1 export per person = panel", r_usa and math.isclose(float(r_usa["ntl_sum_per_capita"]), exp, rel_tol=1e-4), f"{r_usa and r_usa['ntl_sum_per_capita']} vs {exp}")
b.js("{const s=document.getElementById('aYear');s.value='2015';s.dispatchEvent(new Event('change'))}"); time.sleep(0.5)
check("year change updates module A", "2015" in text("a1Title"))
print("errors:", b.errors(clear=False))

# ---------------- module B
chn = adm1[(adm1.ISO_A3 == "CHN") & (adm1.NAM_1 != "Taiwan Sheng") & (adm1.year == 2024) & adm1.ntl_mean.notna()]
check("B1 China ranking: 31 provinces (Taiwan reported separately)", n("#b1 svg > g:not(.axis) path") == len(chn) == 31, n("#b1 svg > g:not(.axis) path"))
check("B stats panel", "Brightest" in text("bStats") and "20%" in text("bStats"))
check("B2 lines drawn", n("#b2 path") >= 31)
check("B3 DOSE table for China", n("#b3t tbody tr") == 31, n("#b3t tbody tr"))
check("B3 caption names DOSE geography and year", "DOSE" in text("b3Cap") and "2019" in text("b3Cap"))
b.js("document.querySelector('#b1 rect').dispatchEvent(new MouseEvent('click',{bubbles:true}))"); time.sleep(0.5)
check("selecting a province highlights its line", "Selected unit" in b.js("document.querySelector('#b2 .an-legend').textContent"))
b.js("document.querySelector('[data-export=b1]').click()"); name, rows = last_csv()
top = chn.sort_values("ntl_mean", ascending=False).iloc[0]
check("B1 export = ADM1 values", rows and rows[0]["ADM1CD_c"] == top.ADM1CD_c and math.isclose(float(rows[0]["value"]), top.ntl_mean, rel_tol=1e-4), f"{rows[0] if rows else None}")
b.js("{const s=document.getElementById('bCountry');s.value='DZA';s.dispatchEvent(new Event('change'))}"); time.sleep(0.8)
check("country without DOSE: says so, no estimate", "No documented subnational GDP" in text("b3Body"))
check("Algeria ranking count", n("#b1 svg > g:not(.axis) path") == adm1[(adm1.ISO_A3 == "DZA") & (adm1.year == 2024) & adm1.ntl_mean.notna()].ADM1CD_c.nunique())
b.js("{const s=document.getElementById('bCountry');s.value='IND';s.dispatchEvent(new Event('change'))}"); time.sleep(0.8)
check("India: DOSE regions shown", n("#b3t tbody tr") > 25)

# ---------------- module C
for c in ("c1", "c2", "c3", "c4"):
    check(f"{c} scatter (countries)", n(f"#{c} svg > g > circle") > 150, n(f"#{c} svg > g > circle"))
check("model table: cross-section, pooled, within-country", all(s in text("cModels") for s in ("Countries, 2022", "Pooled", "Within-country")))
check("Moran's I reported", "Moran" in text("cModels"))
check("CV table", "Leave one World Bank region out" in text("cCv") and "RMSE" in text("cCv"))
check("C5 time series", n("#c5 path") >= 3)
b.js("document.querySelector('[data-l=dose]').click()"); time.sleep(1)
check("regions (DOSE): year range ends 2019", b.js("[...document.getElementById('cYear').options].map(o=>+o.value).at(-1)") == 2019)
dp = pd.read_parquet(DATA / "econ" / "dose" / "panel_dose_v2_14_ntl.parquet")
dp = dp[(dp.year == 2019) & (dp["pop"] > 0) & (dp.ntl_sum > 0)]
check("regions scatter = DOSE regions with positive pop and lights (2019)", n("#c1 svg > g > circle") == len(dp), f"{n('#c1 svg > g > circle')} vs {len(dp)}")
check("regions model table: per-country rows with few-cluster flag", "Australia" in text("cModels") and "few clusters" in text("cModels"))
b.js("{const s=document.getElementById('cCountry');s.value='AUS';s.dispatchEvent(new Event('change'))}"); time.sleep(0.6)
check("Australia: 8 regions", n("#c1 svg > g > circle") == 8, n("#c1 svg > g > circle"))
for k in ("a2", "b2", "b3", "c", "c5"):
    b.js(f"document.querySelector('[data-export={k}]').click()"); name, rows = last_csv()
    check(f"export {k}", len(rows) > 0, f"{name} {len(rows)}")
print("errors:", b.errors(clear=False))
b.shot("shots/analysis_1440.png")
b.viewport(390, 844, True); b.goto("about:blank"); b.goto(S + "analysis.html", "document.querySelectorAll('#a1 circle').length>100", 60); time.sleep(1.5)
check("no horizontal overflow analysis @390", b.js("document.documentElement.scrollWidth - window.innerWidth") <= 0)
b.shot("shots/analysis_390.png")
b.viewport(1440, 1000)

# ---------------- explorer region context
code = adm1[(adm1.ISO_A3 == "CHN") & (adm1.NAM_1 == "Beijing Shi")].ADM1CD_c.iloc[0]
b.goto("about:blank"); b.goto(S + f"explore.html#c=CHN&l=adm1&s=wb&f=annual&v=map&p=2019&r={code}", "document.querySelector('#regionCtx h4')", 60); time.sleep(1.5)
t = text("regionCtx")
check("explorer: national rank of a province", "National rank" in t and "of 32" in t, t[:120])
check("explorer: national WDI context and IMF group", "Country population (WDI, 2019)" in t and "Emerging" in t)
check("explorer: WB units point to GADM for DOSE", "switch to the GADM 4.1 version" in t)
b.goto("about:blank"); b.goto(S + "explore.html#c=CHN&l=adm1&s=gadm&f=annual&v=map&p=2019&r=CHN.2_1", "document.querySelector('#regionCtx h4')", 60); time.sleep(2)
t = text("regionCtx")
check("explorer (GADM): DOSE GRP and population for the same GID_1", "Region GRP pc (DOSE" in t and "Region population (DOSE, 2019)" in t, t[:160])
print("errors:", b.errors())
b.close()
print(f"\n{sum(r[1] for r in R)}/{len(R)} passed")
json.dump(R, open("results_analysis.json", "w"))
