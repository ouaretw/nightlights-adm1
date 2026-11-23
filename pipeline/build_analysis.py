"""Economic-analysis layer: national (ADM0) lights joined to IMF and WDI, and the
exploratory models of the Economic Analysis page.

Run after build_v2.py, run_econ.py (DOSE), fetch_wdi.py and build_imf_groups.py.

Inputs (all already in the repository build or raw/):
  data/v2/adm1_wb/adm1_wb_annual_global.parquet   official annual composites, WB ADM1
  data/v2/econ/dose/panel_dose_v2_14_ntl.parquet   DOSE V2.14 regions + lights (exact rules)
  raw/econ/wdi/*.json                              World Bank WDI (population, GDP)
  raw/econ/imf/weo_2023apr_groups.csv              IMF WEO April 2023 classification
Outputs:
  data/v2/adm0/ntl_adm0_annual_econ.{csv,parquet}  national panel (download product)
  data/v2/analysis/*.json                          compact files read by analysis.html
  data/v2/analysis/models.json                     every estimate shown on the site

Rules
  * National lights are exact aggregates of the ADM1 rows: sum of sums, and mean =
    sum(ntl_sum) / sum(w_valid). If any ADM1 unit of a country lacks valid data in a
    year, the national value is NA (never a partial total). Units containing no pixel
    (w_total = 0) are counted in n_adm1_without_pixels and contribute nothing.
  * Economy definitions follow the IMF/WDI: the source's China ADM1 'Taiwan Sheng' is
    reported as TWN, not CHN. Other boundary conventions are listed in
    NATIONAL_NOTES and left unchanged.
  * Logs are taken only of positive values; non-positive or missing values are
    excluded and counted. No constant is added.
  * Medians cannot be aggregated from ADM2 summaries; no national/ADM1 median is
    produced.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "build" / "site" / "data" / "v2"
GEO = ROOT / "build" / "site" / "data" / "geo"
RAW = ROOT / "raw" / "econ"
OUT = DATA / "analysis"
ADM0 = DATA / "adm0"
SEED = 20261123
WDI = {"SP.POP.TOTL": "pop", "NY.GDP.PCAP.PP.KD": "gdp_pc_ppp", "NY.GDP.MKTP.PP.KD": "gdp_ppp",
       "NY.GDP.PCAP.KD": "gdp_pc_usd2015"}
NATIONAL_NOTES = {
    "CHN": "Source unit 'Taiwan Sheng' excluded and reported as TWN (IMF/WDI economy definition).",
    "TWN": "Built from the source's CHN unit 'Taiwan Sheng'. No WDI series (WDI does not report Taiwan).",
    "MAR": "Source ADM1 units include Laâyoune-Sakia al Hamra; WDI/IMF coverage of that territory is not stated. Left unchanged.",
    "UKR": "Source ADM1 units include Crimea. Left unchanged; WDI coverage of Crimea differs across years.",
    "GEO": "Source ADM1 units include Abkhazia; WDI excludes it. Left unchanged.",
    "CYP": "Source ADM1 units include the northern districts; WDI excludes them. Left unchanged.",
    "SRB": "Kosovo is a separate source code (XKX).",
}


# ---------------------------------------------------------------- data
def national_lights() -> pd.DataFrame:
    a = pd.read_parquet(DATA / "adm1_wb" / "adm1_wb_annual_global.parquet")
    a["iso3"] = np.where((a.ISO_A3 == "CHN") & (a.NAM_1 == "Taiwan Sheng"), "TWN", a.ISO_A3)
    a["country"] = np.where(a.iso3 == "TWN", "Taiwan", a.NAM_0)
    a["_est_w"] = a.w_valid_estimated_share.fillna(0) * a.w_valid
    # A unit with no pixel at all (w_total == 0, e.g. the source's sliver unit BRA014) cannot
    # contribute light; it is counted but does not make the national value missing.
    a["_nopix"] = a.ntl_sum.isna() & (a.w_total.fillna(0) == 0)
    a["_miss"] = a.ntl_sum.isna() & ~a._nopix
    g = a.groupby(["iso3", "year"])
    n = g.size().rename("n_adm1")
    miss = pd.concat([g._miss.sum().astype(int).rename("n_adm1_missing"),
                      g._nopix.sum().astype(int).rename("n_adm1_without_pixels")], axis=1)
    s = g[["ntl_sum", "ntl_nogf_5km_sum", "w_valid", "w_total", "_est_w"]].sum(min_count=1)
    # a code can carry several source country names (e.g. AUS includes 'Ashmore and Cartier Islands
    # (Aus.)'); the economy is named by its most frequent name, never by whichever row comes first
    name = a.groupby("iso3").country.agg(lambda x: x.value_counts().index[0]).rename("country")
    d = pd.concat([n, miss, s, g.n_gasflaring_locs_country.first()], axis=1).reset_index()
    d = d.merge(name, on="iso3", how="left")
    bad = d.n_adm1_missing > 0
    d.loc[bad, ["ntl_sum", "ntl_nogf_5km_sum"]] = np.nan
    d["ntl_mean"] = (d.ntl_sum / d.w_valid).where(d.w_valid > 0)
    d["coverage"] = d.w_valid / d.w_total
    d["w_valid_estimated_share"] = (d._est_w / d.w_valid).where(d.w_valid > 0)
    return d.drop(columns="_est_w")


def wdi() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for code, col in WDI.items():
        for r in json.loads((RAW / "wdi" / f"{code}.json").read_text(encoding="utf-8")):
            if r["countryiso3code"] and r["value"] is not None:
                rows.append((r["countryiso3code"], int(r["date"]), col, float(r["value"])))
    w = pd.DataFrame(rows, columns=["iso3", "year", "var", "value"]).pivot_table(
        index=["iso3", "year"], columns="var", values="value").reset_index()
    meta = pd.DataFrame([{"iso3": c["id"], "wb_name": c["name"], "wb_region": c["region"]["value"].strip(),
                          "wb_income": c["incomeLevel"]["value"].strip()}
                         for c in json.loads((RAW / "wdi" / "countries.json").read_text(encoding="utf-8"))
                         if c["region"]["value"] != "Aggregates"])
    return w, meta


def national_panel() -> pd.DataFrame:
    d = national_lights()
    w, meta = wdi()
    imf = pd.read_csv(RAW / "imf" / "weo_2023apr_groups.csv")
    d = d.merge(w, on=["iso3", "year"], how="left").merge(meta, on="iso3", how="left") \
         .merge(imf[["iso3", "imf_group", "imf_region"]], on="iso3", how="left")
    d["imf_group"] = d.imf_group.fillna("not_classified")
    d["ntl_sum_per_capita"] = (d.ntl_sum / d["pop"]).where(d["pop"] > 0)
    d["ntl_nogf_5km_sum_per_capita"] = (d.ntl_nogf_5km_sum / d["pop"]).where(d["pop"] > 0)
    d["national_definition_note"] = d.iso3.map(NATIONAL_NOTES).fillna("")
    cols = ["iso3", "country", "year", "imf_group", "imf_region", "wb_region", "wb_income", "n_adm1",
            "n_adm1_missing", "n_adm1_without_pixels", "ntl_sum", "ntl_nogf_5km_sum", "ntl_mean", "w_valid", "w_total", "coverage",
            "w_valid_estimated_share", "n_gasflaring_locs_country", "pop", "gdp_pc_ppp", "gdp_ppp",
            "gdp_pc_usd2015", "ntl_sum_per_capita", "ntl_nogf_5km_sum_per_capita", "national_definition_note"]
    return d[cols].sort_values(["iso3", "year"]).reset_index(drop=True)


# ---------------------------------------------------------------- statistics
def auc_ci(x_adv, x_emde, rng, B=2000):
    x_adv, x_emde = np.asarray(x_adv), np.asarray(x_emde)
    if len(x_adv) < 3 or len(x_emde) < 3:
        return None
    U = stats.mannwhitneyu(x_adv, x_emde, alternative="two-sided")
    auc = U.statistic / (len(x_adv) * len(x_emde))
    boots = []
    for _ in range(B):
        a = rng.choice(x_adv, len(x_adv)); e = rng.choice(x_emde, len(x_emde))
        boots.append(stats.mannwhitneyu(a, e).statistic / (len(a) * len(e)))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"auc": auc, "ci95": [lo, hi], "p_mannwhitney": U.pvalue}


def describe(x):
    x = np.asarray(x)
    q = np.percentile(x, [0, 25, 50, 75, 100])
    return {"n": int(len(x)), "min": q[0], "q25": q[1], "median": q[2], "q75": q[3], "max": q[4]}


def module_a(nat: pd.DataFrame) -> dict:
    rng = np.random.default_rng(SEED)
    metrics = {"ntl_mean": "Mean radiance (all valid pixels)", "ntl_sum": "Total radiance",
               "ntl_sum_per_capita": "Total radiance per person",
               "ntl_nogf_5km_sum_per_capita": "Total radiance per person, gas-flare areas excluded (5 km)"}
    out = {}
    for year, g in nat.groupby("year"):
        yr = {}
        for m in metrics:
            v = g[g[m] > 0]
            adv = v[v.imf_group == "advanced"][m]; em = v[v.imf_group == "emde"][m]
            if len(adv) < 3:
                continue
            ent = {"advanced": describe(adv), "emde": describe(em), "separation": auc_ci(adv, em, rng, 1000),
                   "n_nonpositive_or_missing": int(((g[m] <= 0) | g[m].isna()).sum()),
                   "share_emde_above_advanced_median": float((em > adv.median()).mean()),
                   "share_advanced_below_emde_median": float((adv < em.median()).mean())}
            gg = v.dropna(subset=["gdp_pc_ppp"])
            gg = gg[gg.gdp_pc_ppp > 0]
            if len(gg) > 10:
                ent["corr_with_ln_gdp_pc_ppp"] = {}
                for lab, sub in (("all", gg), ("advanced", gg[gg.imf_group == "advanced"]),
                                 ("emde", gg[gg.imf_group == "emde"])):
                    if len(sub) > 5:
                        r_s = stats.spearmanr(sub[m], sub.gdp_pc_ppp)
                        r_p = stats.pearsonr(np.log(sub[m]), np.log(sub.gdp_pc_ppp))
                        ent["corr_with_ln_gdp_pc_ppp"][lab] = {"n": int(len(sub)), "spearman": r_s.statistic,
                                                              "spearman_p": r_s.pvalue,
                                                              "pearson_logs": r_p.statistic, "pearson_p": r_p.pvalue}
            yr[m] = ent
        out[int(year)] = yr
    return {"metrics": metrics, "by_year": out}


def morans_i(lon, lat, resid, k=5, perms=999, seed=SEED):
    lon, lat, z = map(np.asarray, (lon, lat, resid))
    n = len(z)
    if n < k + 3:
        return None
    p1, p2 = np.radians(lat), np.radians(lon)
    dlat = p1[:, None] - p1[None, :]; dlon = p2[:, None] - p2[None, :]
    h = np.sin(dlat / 2) ** 2 + np.cos(p1[:, None]) * np.cos(p1[None, :]) * np.sin(dlon / 2) ** 2
    D = 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))
    np.fill_diagonal(D, np.inf)
    W = np.zeros((n, n))
    nn = np.argsort(D, axis=1)[:, :k]
    W[np.repeat(np.arange(n), k), nn.ravel()] = 1.0 / k
    z = z - z.mean()

    def I(v):
        return (n / W.sum()) * (v @ W @ v) / (v @ v)
    obs = I(z)
    rng = np.random.default_rng(seed)
    sims = np.array([I(rng.permutation(z)) for _ in range(perms)])
    p = (1 + np.sum(np.abs(sims - sims.mean()) >= abs(obs - sims.mean()))) / (perms + 1)
    return {"I": obs, "expected": -1 / (n - 1), "p_perm": p, "k_neighbours": k, "n": int(n), "permutations": perms}


def fit(df, formula, cluster=None, robust="HC3"):
    mod = smf.ols(formula, data=df)
    if cluster is not None:
        groups = pd.factorize(df[cluster])[0]
        res = mod.fit(cov_type="cluster", cov_kwds={"groups": groups})
        se_note = f"cluster-robust by {cluster} ({len(set(groups))} clusters)"
    else:
        res = mod.fit(cov_type=robust)
        se_note = robust
    keep = [t for t in res.params.index if not t.startswith(("C(", "Intercept"))]
    ci = res.conf_int()
    coefs = {t: {"b": res.params[t], "se": res.bse[t], "ci95": [ci.loc[t, 0], ci.loc[t, 1]], "p": res.pvalues[t]}
             for t in keep}
    out = {"formula": formula, "n": int(res.nobs), "r2": res.rsquared, "r2_adj": res.rsquared_adj,
           "se": se_note, "coef": coefs}
    if "ln_pop" in keep and "ln_gdppc" in keep:
        w = res.wald_test("ln_pop = ln_gdppc", scalar=True)
        out["test_equal_elasticities"] = {"F_or_chi2": float(w.statistic), "p": float(w.pvalue),
                                          "meaning": "H0: total radiance scales with GDP alone (equal elasticities on population and GDP per capita)"}
    return out, res


def logs(df, y, pop="pop", gdppc="gdp_pc_ppp"):
    d = df.copy()
    ok = (d[y] > 0) & (d[pop] > 0) & (d[gdppc] > 0)
    excluded = {"nonpositive_or_missing_radiance": int(((d[y] <= 0) | d[y].isna()).sum()),
                "missing_population": int(d[pop].isna().sum()), "missing_gdp_pc": int(d[gdppc].isna().sum())}
    d = d[ok].copy()
    d["ln_y"] = np.log(d[y]); d["ln_pop"] = np.log(d[pop]); d["ln_gdppc"] = np.log(d[gdppc])
    return d, excluded


def cv(df, formulas, split, label):
    """Out-of-sample RMSE (log points) for each formula over the given folds."""
    res = {}
    folds = list(split(df))
    for name, f in formulas.items():
        sse = sst0 = n = 0
        for tr, te in folds:
            # drop test rows whose categorical levels were not seen in training
            m = smf.ols(f, data=tr).fit()
            for c in ("year", "iso"):
                if f"C({c})" in f:
                    te = te[te[c].isin(set(tr[c]))]
            if not len(te):
                continue
            pred = m.predict(te)
            sse += float(((te.ln_y - pred) ** 2).sum())
            sst0 += float(((te.ln_y - tr.ln_y.mean()) ** 2).sum())
            n += len(te)
        res[name] = {"rmse": math.sqrt(sse / n), "rmse_null_training_mean": math.sqrt(sst0 / n),
                     "r2_oos_vs_training_mean": 1 - sse / sst0, "n_test": n, "folds": len(folds)}
    return {"design": label, "models": res}


def module_c(nat: pd.DataFrame, dose: pd.DataFrame, cent_nat: pd.DataFrame, cent_dose: pd.DataFrame) -> dict:
    out = {"national": {}, "subnational_dose": {}, "notes": []}
    F = {"pop_only": "ln_y ~ ln_pop", "gdppc_only": "ln_y ~ ln_gdppc", "both": "ln_y ~ ln_pop + ln_gdppc"}
    # ---- national cross-sections, one per year
    nat = nat[nat.iso3 != "TWN"]
    xs = {}
    for yv in ("ntl_sum", "ntl_nogf_5km_sum"):
        xs[yv] = {}
        for year, g in nat.groupby("year"):
            d, exc = logs(g, yv)
            if len(d) < 50:
                continue
            ent, res = fit(d, F["both"])
            ent["excluded"] = exc
            ent["year"] = int(year)
            c = d.merge(cent_nat, on="iso3", how="inner")
            if len(c) > 20:
                r = res.resid.loc[c.index] if False else (c.ln_y - res.predict(c))
                ent["morans_i_residuals"] = morans_i(c.lon, c.lat, r)
                ent["morans_i_residuals"]["n_without_centroid"] = int(len(d) - len(c))
            xs[yv][int(year)] = ent
    out["national"]["cross_sections"] = xs
    # ---- pooled national panel
    d, exc = logs(nat, "ntl_sum")
    d["iso"] = d.iso3
    years = sorted(d.year.unique())
    out["national"]["sample"] = {"years": [int(years[0]), int(years[-1])], "n_obs": int(len(d)),
                                 "n_countries": int(d.iso3.nunique()), "excluded": exc}
    pooled = {}
    for name, f in F.items():
        pooled[name], _ = fit(d, f + " + C(year)", cluster="iso")
    pooled["both_country_fe"], _ = fit(d, F["both"] + " + C(year) + C(iso)", cluster="iso")
    pooled["both_country_fe"]["note"] = ("Within-country (two-way fixed effects): identifies the association from "
                                         "changes over time inside each country, not from differences between countries.")
    out["national"]["pooled"] = pooled
    regions = sorted(d.wb_region.dropna().unique())
    out["national"]["cv_leave_one_region_out"] = cv(
        d.dropna(subset=["wb_region"]), {k: v + " + C(year)" for k, v in F.items()},
        lambda df: [(df[df.wb_region != r], df[df.wb_region == r]) for r in regions],
        f"Leave one World Bank region out ({len(regions)} folds); year effects")
    out["national"]["cv_temporal"] = cv(
        d, {**{k: v for k, v in F.items()}, "both_country_fe": F["both"] + " + C(iso)"},
        lambda df: [(df[df.year <= 2018], df[df.year >= 2019])],
        "Train 2012-2018, test 2019 onward (no year effects: test years unseen)")
    # ---- subnational, DOSE regions
    s = dose.rename(columns={"GID_0": "iso"})
    d, exc = logs(s, "ntl_sum", pop="pop", gdppc="grp_pc_usd_2015")
    out["subnational_dose"]["sample"] = {"years": [int(d.year.min()), int(d.year.max())], "n_obs": int(len(d)),
                                         "n_regions": int(d.GID_1.nunique()), "n_countries": int(d.iso.nunique()),
                                         "excluded": exc,
                                         "gdp_measure": "DOSE grp_pc_usd_2015 (gross regional product per capita, constant 2015 US$)"}
    sp = {}
    sp["both_pooled"], _ = fit(d, F["both"] + " + C(year)", cluster="iso")
    sp["both_country_fe"], _ = fit(d, F["both"] + " + C(year) + C(iso)", cluster="iso")
    sp["both_country_fe"]["note"] = "Compares regions within the same country and year."
    for name in ("pop_only", "gdppc_only"):
        sp[name + "_country_fe"], _ = fit(d, F[name] + " + C(year) + C(iso)", cluster="iso")
    out["subnational_dose"]["pooled"] = sp
    countries = {}
    for iso in ("CHN", "IND", "AUS", "USA", "BRA", "IDN"):
        c = d[d.iso == iso]
        if c.GID_1.nunique() < 5:
            continue
        ent, res = fit(c, F["both"] + " + C(year)", cluster="GID_1")
        ent["n_regions"] = int(c.GID_1.nunique())
        ent["years"] = [int(c.year.min()), int(c.year.max())]
        if ent["n_regions"] < 20:
            ent["warning"] = (f"Only {ent['n_regions']} regions: cluster-robust standard errors are unreliable "
                              "with this few clusters; treat as descriptive.")
        cc = c.merge(cent_dose, on="GID_1", how="inner")
        last = cc[cc.year == cc.year.max()]
        if len(last) > 8:
            ent["morans_i_residuals_last_year"] = morans_i(last.lon, last.lat, last.ln_y - res.predict(last), k=4)
        countries[iso] = ent
    out["subnational_dose"]["by_country"] = countries
    countries_list = sorted(d.iso.unique())
    out["subnational_dose"]["cv_leave_one_country_out"] = cv(
        d, {k: v + " + C(year)" for k, v in F.items()},
        lambda df: [(df[df.iso != c], df[df.iso == c]) for c in countries_list],
        f"Leave one country out ({len(countries_list)} folds); year effects")
    out["subnational_dose"]["cv_temporal"] = cv(
        d, {**F, "both_country_fe": F["both"] + " + C(iso)"},
        lambda df: [(df[df.year <= 2016], df[df.year >= 2017])],
        "Train 2012-2016, test 2017-2019")
    out["notes"] = [
        "Exploratory associations only; coefficients are not causal effects.",
        "Radiance is the official annual composite sum (ntl_sum); logs of positive values only, nothing added to zeros.",
        "National GDP per capita: WDI NY.GDP.PCAP.PP.KD (PPP, constant 2021 international $). Subnational: DOSE "
        "grp_pc_usd_2015. The two scales are never mixed in one model.",
        "Standard errors: HC3 for single cross-sections; cluster-robust by country for pooled panels "
        "(handles serial correlation within a country); by region within one country.",
        "Spatial dependence is checked with Moran's I of residuals (k nearest centroids); a significant I means "
        "the reported standard errors are likely too small.",
    ]
    return out


# ---------------------------------------------------------------- centroids
def centroids_national():
    import shapely.geometry as sg
    gj = json.loads((GEO / "world_adm1.geojson").read_text(encoding="utf-8"))
    vals = json.loads((GEO / "world_adm1_values.json").read_text(encoding="utf-8"))["units"]
    acc = {}
    for f in gj["features"]:
        code = f["properties"]["code"]
        iso = "TWN" if vals.get(code, {}).get("name") == "Taiwan Sheng" else f["properties"]["iso"]
        g = sg.shape(f["geometry"])
        a = g.area
        if a <= 0:
            continue
        c = g.centroid
        x = acc.setdefault(iso, [0.0, 0.0, 0.0])
        x[0] += c.x * a; x[1] += c.y * a; x[2] += a
    return pd.DataFrame([{"iso3": k, "lon": v[0] / v[2], "lat": v[1] / v[2]} for k, v in acc.items()])


def centroids_dose(dose):
    import geopandas as gpd
    g = gpd.read_parquet(ROOT / "raw" / "gadm" / "gadm41_adm1.parquet")[["GID_1", "geometry"]]
    pts = g.geometry.representative_point()
    m = pd.DataFrame({"gadm": g.GID_1, "lon": pts.x, "lat": pts.y}).drop_duplicates("gadm")
    custom = gpd.read_file(RAW / "dose" / "DOSE_additional_regions_V2_14.gpkg")
    cp = custom.to_crs(4326).geometry.representative_point()
    cm = pd.DataFrame({"GID_1": custom.GID_1, "lon": cp.x, "lat": cp.y})
    links = dose.drop_duplicates("GID_1")[["GID_1", "ntl_link_method", "ntl_link_detail"]]
    links["gadm"] = np.where(links.ntl_link_method.str.startswith("gadm"), links.ntl_link_detail, None)
    a = links.merge(m, on="gadm", how="inner")[["GID_1", "lon", "lat"]]
    return pd.concat([a, cm[~cm.GID_1.isin(a.GID_1)]], ignore_index=True)


# ---------------------------------------------------------------- site files
def r(v, n=5):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return float(f"{float(v):.{n}g}")
    return v


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, np.ndarray)):
        return [clean(v) for v in o]
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    return r(o)


def adm1_units():
    a = pd.read_parquet(DATA / "adm1_wb" / "adm1_wb_annual_global.parquet",
                        columns=["ISO_A3", "NAM_0", "ADM1CD_c", "NAM_1", "adm1_tier", "year", "ntl_sum", "ntl_mean",
                                 "coverage", "ntl_nogf_5km_sum"])
    years = sorted(int(y) for y in a.year.unique())
    units = {}
    for code, g in a.groupby("ADM1CD_c", sort=True):
        g = g.set_index("year").reindex(years)
        f = g.dropna(subset=["ISO_A3"]).iloc[0]
        units[code] = {"iso": f.ISO_A3, "name": f.NAM_1, "tier": f.adm1_tier,
                       "sum": [r(v) for v in g.ntl_sum], "mean": [r(v) for v in g.ntl_mean],
                       "nogf": [r(v) for v in g.ntl_nogf_5km_sum], "cov": [r(v, 3) for v in g.coverage]}
    return {"source": "adm1_wb_annual_global.parquet (official annual composites), World Bank ADM1 units",
            "years": years, "units": units}


ADM0_DICT = {
    "iso3": "ISO 3166 alpha-3 code of the economy (source ISO_A3; TWN split from the source's CHN unit 'Taiwan Sheng')",
    "country": "Name as in the source (World Bank boundaries); 'Taiwan' for TWN",
    "year": "Year of the official annual Black Marble composite",
    "imf_group": "IMF WEO April 2023 group: advanced | emde | not_classified (applied unchanged to all years)",
    "imf_region": "IMF WEO April 2023 regional group (EMDE regions; 'Advanced Economies' for advanced)",
    "wb_region": "World Bank region (WDI country metadata)",
    "wb_income": "World Bank income group (WDI country metadata, current classification)",
    "n_adm1": "Number of World Bank ADM1 units aggregated",
    "n_adm1_missing": "ADM1 units with pixels but no valid observation; if > 0 the national sums are NA",
    "n_adm1_without_pixels": "ADM1 units that contain no pixel (w_total = 0); contribute nothing",
    "ntl_sum": "Sum of radiance over valid pixels, nW·cm⁻²·sr⁻¹ × px (exact sum of ADM1 sums)",
    "ntl_nogf_5km_sum": "As ntl_sum, excluding 5 km buffers around gas-flaring sites",
    "ntl_mean": "Coverage-weighted mean radiance, nW·cm⁻²·sr⁻¹ = ntl_sum / w_valid (exact)",
    "w_valid": "Sum of valid-pixel coverage weights",
    "w_total": "Sum of all pixel coverage weights",
    "coverage": "w_valid / w_total",
    "w_valid_estimated_share": "Share of w_valid that was estimated (dark districts; see methods)",
    "n_gasflaring_locs_country": "Number of gas-flaring locations in the country (source, national count)",
    "pop": "Population, total (WDI SP.POP.TOTL); NA if not reported",
    "gdp_pc_ppp": "GDP per capita, PPP, constant 2021 international $ (WDI NY.GDP.PCAP.PP.KD); NA if not reported",
    "gdp_ppp": "GDP, PPP, constant 2021 international $ (WDI NY.GDP.MKTP.PP.KD)",
    "gdp_pc_usd2015": "GDP per capita, constant 2015 US$ (WDI NY.GDP.PCAP.KD)",
    "ntl_sum_per_capita": "ntl_sum / pop",
    "ntl_nogf_5km_sum_per_capita": "ntl_nogf_5km_sum / pop",
    "national_definition_note": "How the national unit relates to the IMF/WDI economy definition, where it matters",
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ADM0.mkdir(parents=True, exist_ok=True)
    nat = national_panel()
    assert list(nat.columns) == list(ADM0_DICT), "dictionary out of date"
    assert not nat.duplicated(["iso3", "year"]).any()
    nat.to_parquet(ADM0 / "ntl_adm0_annual_econ.parquet", index=False)
    nat.to_csv(ADM0 / "ntl_adm0_annual_econ.csv", index=False, float_format="%.10g")
    pd.DataFrame({"column": list(ADM0_DICT), "description": list(ADM0_DICT.values())}).to_csv(
        ADM0 / "ntl_adm0_annual_econ_dictionary.csv", index=False)
    import shutil
    shutil.copyfile(RAW / "imf" / "weo_2023apr_groups.csv", OUT / "imf_weo_2023apr_groups.csv")

    dose = pd.read_parquet(DATA / "econ" / "dose" / "panel_dose_v2_14_ntl.parquet")
    cn, cd = centroids_national(), centroids_dose(dose)
    models = module_c(nat, dose, cn, cd)
    a = module_a(nat)
    imf_meta = json.loads((RAW / "imf" / "weo_2023apr_groups_meta.json").read_text(encoding="utf-8"))
    wdi_log = json.loads((RAW / "wdi" / "fetch_log.json").read_text(encoding="utf-8"))

    sources = {
        "lights": "World Bank Space2Stats Black Marble (dataset 0066940), official annual composites, aggregated "
                  "exactly from ADM2 (this project, v2).",
        "imf": imf_meta,
        "wdi": {"indicators": WDI, "retrieved_utc": wdi_log["retrieved_utc"],
                "api": "https://api.worldbank.org/v2", "license": "CC BY 4.0"},
        "dose": "DOSE V2.14 (Wenz et al. 2023), CC BY 4.0, regions linked to source districts (see integration page).",
    }
    # national.json: one record per economy with year arrays
    years = sorted(int(y) for y in nat.year.unique())
    econ = {}
    for iso, g in nat.groupby("iso3"):
        g = g.set_index("year").reindex(years)
        f = g.dropna(subset=["country"]).iloc[0]
        econ[iso] = {"name": f.country, "imf": f.imf_group, "imf_region": f.imf_region if isinstance(f.imf_region, str) else None,
                     "wb_region": f.wb_region if isinstance(f.wb_region, str) else None,
                     "note": f.national_definition_note or None, "n_adm1": int(f.n_adm1),
                     **{k: [r(v) for v in g[c]] for k, c in
                        (("sum", "ntl_sum"), ("nogf", "ntl_nogf_5km_sum"), ("mean", "ntl_mean"), ("cov", "coverage"),
                         ("pop", "pop"), ("gdppc", "gdp_pc_ppp"), ("gdp", "gdp_ppp"))}}
    files = {
        "national.json": {"years": years, "sources": sources, "economies": econ},
        "module_a.json": a,
        "models.json": models,
        "adm1_annual.json": adm1_units(),
    }
    dk = dose[["GID_0", "GID_1", "country", "region", "year", "pop", "grp_pc_usd_2015", "ntl_sum", "ntl_mean",
               "coverage", "ntl_link_method"]]
    dyears = sorted(int(y) for y in dk.year.unique())
    reg = {}
    for gid, g in dk.groupby("GID_1"):
        g2 = g.set_index("year").reindex(dyears)
        f = g.iloc[0]
        reg[gid] = {"iso": f.GID_0, "country": f.country, "name": f.region, "link": f.ntl_link_method,
                    "pop": [r(v) for v in g2["pop"]], "grppc": [r(v) for v in g2.grp_pc_usd_2015],
                    "sum": [r(v) for v in g2.ntl_sum], "mean": [r(v) for v in g2.ntl_mean]}
    files["dose_regions.json"] = {"years": dyears, "source": sources["dose"],
                                  "gdp_measure": "grp_pc_usd_2015 (constant 2015 US$)", "regions": reg}
    for name, obj in files.items():
        (OUT / name).write_text(json.dumps(clean(obj), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(name, f"{(OUT / name).stat().st_size / 1e6:.2f} MB")
    summ = {"n_economies": int(nat.iso3.nunique()), "years": [years[0], years[-1]],
            "n_with_imf": int(nat[nat.imf_group != "not_classified"].iso3.nunique()),
            "n_with_wdi_gdp": int(nat.dropna(subset=["gdp_pc_ppp"]).iso3.nunique()),
            "imf_without_lights": sorted(set(pd.read_csv(RAW / "imf" / "weo_2023apr_groups.csv").iso3) - set(nat.iso3)),
            "national_missing_rows": int(nat.ntl_sum.isna().sum())}
    (OUT / "summary.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
