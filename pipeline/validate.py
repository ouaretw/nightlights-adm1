"""Validation report for the v2 products -> build/site/data/v2/validation.json

Sections
  arithmetic     source reconciliation, mean-in-range, QA shares, NA handling
  weights        how much estimated pixel weights could move ADM1 means
  crosswalk      GADM assignment coverage, match grades, sensitivity
  benchmark      agreement with DIRECT raster->GADM 4.1 ADM1 extractions published
                 by the World Bank blackmarble-stata prototype (13 countries, 2021-2023)
  annual         official NASA annual composite vs annual values from monthly data
  dose           descriptive association with DOSE regional GDP (not causal)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "build" / "site" / "data" / "v2"
REL = ROOT / "build" / "release"
RAW = ROOT / "raw"


def load(sub, freq):
    p = DATA / sub / f"{sub}_{freq}_global.parquet"
    return pd.read_parquet(p if p.exists() else REL / p.name)


def q(s, qs=(0.5, 0.9, 0.99, 1.0), nd=4):
    s = pd.Series(s).dropna()
    return {str(k): round(float(v), nd) for k, v in s.quantile(list(qs)).items()} if len(s) else {}


def within_slope(df, y, x, unit, time):
    """Two-way fixed-effects slope (unit + time demeaning, balanced-ish panels)."""
    d = df[[y, x, unit, time]].dropna().copy()
    for c in (y, x):
        d[c] = d[c] - d.groupby(unit)[c].transform("mean") - d.groupby(time)[c].transform("mean") + d[c].mean()
    vx = (d[x] ** 2).sum()
    return float((d[x] * d[y]).sum() / vx) if vx > 0 else None, int(len(d))


def main():
    rep = {}
    meta = json.loads((DATA / "build_meta.json").read_text(encoding="utf-8"))
    wb_m, wb_a = load("adm1_wb", "monthly"), load("adm1_wb", "annual")
    g_m, g_a = load("adm1_gadm41", "monthly"), load("adm1_gadm41", "annual")
    a2_a = load("adm2", "annual")

    # ---------------- arithmetic
    qcols = [c for c in wb_m.columns if c.startswith("ntl_quality_prop_")]
    rep["arithmetic"] = {
        "country_total_max_rel_diff": meta["reconciliation"],
        "adm1_wb_monthly_rows": int(len(wb_m)),
        "adm1_months_no_valid_data_now_NA": int(wb_m.ntl_sum.isna().sum()),
        "note_v1": "v1.x reported these province-months as 0 because the source encodes 'no valid pixel' as sum = 0.",
        "quality_shares_sum_to_one_max_abs_dev": round(float((wb_m.loc[wb_m[qcols].notna().all(axis=1), qcols].sum(axis=1) - 1).abs().max()), 6),
        "adm1_months_quality_unreported": int(wb_m[qcols].isna().any(axis=1).sum()),
        "coverage_range": [round(float(wb_m.coverage.min()), 4), round(float(wb_m.coverage.max()), 4)],
    }

    # ---------------- weights
    s = wb_m.w_valid_estimated_share.fillna(0)
    lit = wb_m.ntl_sum > 0
    rep["weights"] = {
        "adm1_months_with_any_estimated_weight": int((s > 0).sum()),
        "share_of_lit_adm1_months_with_estimated_weight": round(float(((s > 0) & lit).sum() / lit.sum()), 4),
        "estimated_share_quantiles_where_positive_and_lit": q(s[(s > 0) & lit]),
        "assumed_error_of_estimated_weights": 0.05,
        "relative_change_of_mean_bound_quantiles": q(s[(s > 0) & lit] * 0.05),
        "note": ("Sums are unaffected. Only ntl_mean of provinces mixing completely dark and lit districts depends on estimated "
                 "weights. Estimated weights equal the district's recovered total weight x (1 - share missing); recovered total "
                 "weights vary month to month by at most ~5% (90th percentile; median 0.14%), so the provincial mean moves by at "
                 "most share x 5%."),
    }

    # ---------------- crosswalk
    xw = pd.read_csv(DATA / "crosswalks" / "crosswalk_adm2_to_gadm41.csv")
    mq = pd.read_csv(DATA / "crosswalks" / "gadm41_adm1_match_quality.csv")
    light = a2_a[a2_a.year == 2020].set_index("ADM2CD_c").ntl_sum
    xw["light2020"] = xw.ADM2CD_c.map(light).fillna(0)
    by_m = xw.groupby("method").light2020.sum() / xw.light2020.sum()
    g20 = g_a[g_a.year == 2020].merge(mq[["GID_1", "xw_match_quality"]], on="GID_1", how="left", suffixes=("", "_q"))
    grade_light = g20.groupby("xw_match_quality").ntl_sum.sum() / g20.ntl_sum.sum()
    coarse = xw.method.isin(["adm1_outline", "adm1_as_current_adm2", "sibling_vote", "adm1_name", "single_unit"]) | (xw.overlap_share < 0.9)
    unc = (xw.assign(c=coarse * xw.light2020).groupby("GID_1").agg(c=("c", "sum"), t=("light2020", "sum")))
    unc = (unc.c / unc.t.where(unc.t > 0)).dropna()
    rep["crosswalk"] = {
        "share_world_light_2020_by_method": {k: round(float(v), 4) for k, v in by_m.items()},
        "gadm_units_by_grade": mq.xw_match_quality.value_counts().to_dict(),
        "share_of_assigned_light_2020_by_grade": {k: round(float(v), 4) for k, v in grade_light.items()},
        "gadm_units_absorbing_others": int((mq.xw_absorbs_units.fillna("") != "").sum()),
        "per_unit_share_of_light_from_coarse_or_partial_placements_quantiles": q(unc, (0.5, 0.75, 0.9, 0.95, 0.99)),
        "units_with_more_than_10pct_light_from_coarse_or_partial_placements": int((unc > 0.1).sum()),
    }

    # ---------------- benchmark against direct extraction
    rows = []
    for f in sorted((RAW / "benchmark").glob("bm_stata_*.dta")):
        iso, year = f.stem.split("_")[2], int(f.stem.split("_")[3])
        b = pd.read_stata(f)[["GID_1", "ntl_sum", "prop_na"]].assign(ISO=iso, year=year)
        rows.append(b)
    if rows:
        bm = pd.concat(rows).rename(columns={"ntl_sum": "direct_sum", "prop_na": "direct_prop_na"})
        ours = g_a[["GID_1", "year", "ntl_sum", "ntl_quality_prop_na", "xw_match_quality"]]
        cmp_ = bm.merge(ours, on=["GID_1", "year"], how="left")
        both = cmp_.dropna(subset=["direct_sum", "ntl_sum"])
        both = both[(both.direct_sum > 0) & (both.ntl_sum > 0)]
        ratio = both.ntl_sum / both.direct_sum
        lr = np.log(both.ntl_sum), np.log(both.direct_sum)
        per_c = both.assign(r=ratio).groupby("ISO").r.median().round(4).to_dict()
        hi = both[both.xw_match_quality == "high"]
        rep["benchmark"] = {
            "reference": "World Bank blackmarble-stata prototype: NASA Black Marble annual (VNP46A4) extracted directly to GADM 4.1 ADM1 with exactextractr; public S3 files for 13 countries x 2021-2023",
            "gadm_units_compared": int(both.GID_1.nunique()), "unit_years": int(len(both)),
            "benchmark_units_missing_in_ours": int(cmp_.ntl_sum.isna().sum()),
            "ratio_ours_to_direct_quantiles": q(ratio, (0.05, 0.25, 0.5, 0.75, 0.95)),
            "ratio_ours_to_direct_quantiles_high_grade_only": q(hi.ntl_sum / hi.direct_sum, (0.05, 0.25, 0.5, 0.75, 0.95)),
            "share_within_5pct": round(float(((ratio - 1).abs() <= 0.05).mean()), 4),
            "share_within_10pct": round(float(((ratio - 1).abs() <= 0.10).mean()), 4),
            "corr_log_sums": round(float(np.corrcoef(lr[0], lr[1])[0, 1]), 5),
            "median_ratio_by_country": per_c,
            "caveat": "The two pipelines may use different Black Marble collections, land/water masks and zonal-coverage rules; differences therefore mix crosswalk error with processing differences. The prototype's ntl_mean is below its median in several files, so means are not compared.",
        }
        both.assign(ratio=ratio).to_csv(DATA / "validation_benchmark_units.csv", index=False)

    # ---------------- annual official vs from monthly
    afm = load("adm1_wb", "annual_from_monthly")
    j = wb_a[["ADM1CD_c", "year", "ntl_sum"]].merge(afm[["ADM1CD_c", "year", "ntl_sum_monthly_mean", "n_months_with_data"]], on=["ADM1CD_c", "year"])
    j = j[(j.ntl_sum > 0) & (j.ntl_sum_monthly_mean > 0) & (j.n_months_with_data == 12)]
    rep["annual"] = {
        "adm1_years_compared_12_months": int(len(j)),
        "ratio_official_to_monthly_mean_quantiles": q(j.ntl_sum / j.ntl_sum_monthly_mean, (0.05, 0.25, 0.5, 0.75, 0.95)),
        "corr_log": round(float(np.corrcoef(np.log(j.ntl_sum), np.log(j.ntl_sum_monthly_mean))[0, 1]), 5),
        "note": "The NASA annual composite is computed from daily observations over the year, not as a mean of monthly composites; the two are kept as separate products.",
    }

    # ---------------- DOSE association (descriptive)
    p = DATA / "econ" / "dose" / "panel_dose_v2_14_ntl.parquet"
    if p.exists():
        d = pd.read_parquet(p)
        d = d[(d.ntl_sum > 0) & (d.grp_pc_usd > 0) & (d["pop"] > 0)].copy()
        d["ln_grp"] = np.log(d.grp_pc_usd * d["pop"])
        d["ln_ntl"] = np.log(d.ntl_sum)
        cs = d[d.year == 2015]
        slope_fe, n_fe = within_slope(d, "ln_grp", "ln_ntl", "GID_1", "year")
        rep["dose"] = {
            "panel_rows_with_gdp_and_lights": int(len(d)), "regions": int(d.GID_1.nunique()),
            "countries": int(d.GID_0.nunique()), "years": [int(d.year.min()), int(d.year.max())],
            "cross_section_2015_corr_log_gdp_log_ntl": round(float(np.corrcoef(cs.ln_grp, cs.ln_ntl)[0, 1]), 4),
            "within_region_slope_log_gdp_on_log_ntl_twoway_fe": round(slope_fe, 4) if slope_fe is not None else None,
            "within_obs": n_fe,
            "note": "Descriptive association only, shown to document that the linkage behaves sensibly. Not a causal estimate.",
        }
    (DATA / "validation.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
