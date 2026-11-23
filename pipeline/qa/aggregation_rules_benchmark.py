"""How much do simple ADM2 -> ADM1 collapses differ from the exact rules?

Compares, for official annual composites:
  exact      this project: mean = sum(ntl_sum) / sum(w_valid); no ADM1 median
  unweighted the collapse used by worldbank/space2stats-stata query_s2s.ado
             (collapse (sum) ntl_sum ... (mean) ntl_mean ntl_median ...): unweighted
             average of district means and of district medians
against DIRECT raster -> GADM 4.1 ADM1 extractions (World Bank blackmarble-stata
prototype files in raw/benchmark, 13 countries x 2021-2023), which carry a true
pixel median per ADM1.

Part 2 needs no benchmark: across all World Bank ADM1 units and years, how far is
the unweighted mean of district means from the exact coverage-weighted mean?

Writes build/site/data/v2/validation_aggregation_rules.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "build" / "site" / "data" / "v2"


def q(s, ps=(0.05, 0.25, 0.5, 0.75, 0.95)):
    s = pd.Series(s).dropna()
    return {f"p{int(p * 100):02d}": round(float(s.quantile(p)), 4) for p in ps} | {"n": int(len(s))}


def main():
    src = pd.read_csv(ROOT / "raw" / "ntl_adm2_annual.csv",
                      usecols=["ISO_A3", "ADM1CD_c", "ADM2CD_c", "year", "ntl_mean", "ntl_median", "ntl_sum",
                               "ntl_quality_prop_na"], dtype={"ADM1CD_c": str, "ADM2CD_c": str})
    valid = src[src.ntl_mean.notna() & (src.ntl_quality_prop_na < 0.999999)]
    rep = {"generated_by": "pipeline/qa/aggregation_rules_benchmark.py"}

    # ---- part 1: against direct extraction (GADM 4.1 ADM1)
    xw = pd.read_csv(ROOT / "build" / "crosswalks" / "crosswalk_adm2_to_gadm41.csv", dtype=str,
                     usecols=["ADM2CD_c", "GID_1"])
    bm = pd.concat([pd.read_stata(f)[["GID_1", "ntl_mean", "ntl_median", "ntl_sum"]].assign(year=int(f.stem.split("_")[3]))
                    for f in sorted((ROOT / "raw" / "benchmark").glob("bm_stata_*.dta"))])
    bm = bm.rename(columns={"ntl_mean": "direct_mean", "ntl_median": "direct_median", "ntl_sum": "direct_sum"})
    v = valid.merge(xw, on="ADM2CD_c", how="inner")
    v = v[v.year.isin(bm.year.unique()) & v.GID_1.isin(bm.GID_1)]
    unw = v.groupby(["GID_1", "year"]).agg(unweighted_mean=("ntl_mean", "mean"),
                                           mean_of_medians=("ntl_median", "mean"),
                                           n_adm2=("ADM2CD_c", "size")).reset_index()
    g = pd.read_parquet(DATA / "adm1_gadm41" / "adm1_gadm41_annual_global.parquet",
                        columns=["GID_1", "year", "ntl_mean", "xw_match_quality"])
    j = bm.merge(unw, on=["GID_1", "year"]).merge(g, on=["GID_1", "year"])
    j = j[(j.xw_match_quality == "high") & (j.n_adm2 >= 2)]        # boundary noise small; a real collapse
    pos = j[(j.direct_median > 0) & (j.mean_of_medians > 0)]
    rel = lambda a, b: (a - b) / b                                   # noqa: E731
    rep["vs_direct_extraction"] = {
        "reference": "World Bank blackmarble-stata prototype, direct VNP46A4 -> GADM 4.1 ADM1 (exactextractr), 2021-2023",
        "sample": "GADM 4.1 ADM1 units with crosswalk grade 'high' and >= 2 source districts",
        "unit_years": int(len(j)), "units": int(j.GID_1.nunique()), "countries": int(j.GID_1.str[:3].nunique()),
        "median_estimators": {
            "mean_of_district_medians_relative_error": q(rel(pos.mean_of_medians, pos.direct_median)),
            "exact_mean_relative_to_true_median": q(rel(pos.ntl_mean, pos.direct_median)),
            "share_within_10pct_mean_of_medians": round(float((rel(pos.mean_of_medians, pos.direct_median).abs() <= 0.10).mean()), 4),
            "share_true_median_zero": round(float((j.direct_median == 0).mean()), 4),
            "share_true_median_zero_but_mean_of_medians_positive":
                round(float(((j.direct_median == 0) & (j.mean_of_medians > 0)).mean()), 4),
            "spearman_mean_of_medians_vs_true_median": round(float(j[["mean_of_medians", "direct_median"]].corr("spearman").iloc[0, 1]), 4),
        },
        "mean_estimators_caveat": "The prototype's own ntl_mean is below its median in several files, so its mean "
                                  "is not used as truth; means are validated by the exact identity instead (tests).",
    }

    # ---- part 2: unweighted vs exact mean, every WB ADM1 unit-year
    w = pd.read_parquet(DATA / "adm1_wb" / "adm1_wb_annual_global.parquet", columns=["ADM1CD_c", "year", "ntl_mean", "n_adm2"])
    u = valid.groupby(["ADM1CD_c", "year"]).ntl_mean.mean().rename("unweighted_mean").reset_index()
    k = w.merge(u, on=["ADM1CD_c", "year"])
    k = k[(k.n_adm2 >= 2) & (k.ntl_mean > 0)]
    r = rel(k.unweighted_mean, k.ntl_mean)
    rep["unweighted_vs_exact_mean_wb_adm1"] = {
        "sample": "World Bank ADM1 unit-years with >= 2 districts and positive exact mean, official annual composites",
        "unit_years": int(len(k)), "relative_difference_quantiles": q(r),
        "share_abs_diff_over_10pct": round(float((r.abs() > 0.10).mean()), 4),
        "share_abs_diff_over_50pct": round(float((r.abs() > 0.50).mean()), 4),
        "share_unweighted_higher": round(float((r > 0).mean()), 4),
        "why": "Small, bright urban districts get the same weight as large dark rural districts.",
    }
    # ---- part 3: monthly no-data zeros (sums)
    m = pd.read_parquet(DATA / "adm1_wb" / "adm1_wb_monthly_global.parquet" if (DATA / "adm1_wb" / "adm1_wb_monthly_global.parquet").exists()
                        else ROOT / "build" / "release" / "adm1_wb_monthly_global.parquet",
                        columns=["ADM1CD_c", "n_adm2", "n_adm2_no_valid_data", "ntl_sum"])
    rep["monthly_no_data"] = {
        "adm1_months": int(len(m)),
        "all_districts_without_valid_data": int((m.n_adm2_no_valid_data == m.n_adm2).sum()),
        "some_districts_without_valid_data": int(((m.n_adm2_no_valid_data > 0) & (m.n_adm2_no_valid_data < m.n_adm2)).sum()),
        "meaning": "A plain sum of source ntl_sum reports 0 for the first group (here: NA) and silently "
                   "understates the second (here: flagged through n_adm2_no_valid_data).",
    }
    out = DATA / "validation_aggregation_rules.json"
    out.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
