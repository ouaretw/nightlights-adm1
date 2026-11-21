"""Audit of v1.1 assumptions against the source (findings feed docs/AUDIT.md)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw"
pd.set_option("display.width", 220)
out = {}

cols = ["ISO_A3", "ADM1CD_c", "ADM2CD_c", "date", "ntl_sum", "ntl_mean", "ntl_quality_prop_na",
        "ntl_quality_prop_0_good", "ntl_quality_prop_1_poor", "ntl_quality_prop_2_gapfilled",
        "ntl_nogf_5km_sum", "ntl_nogf_5km_mean"]
m = pd.read_parquet(RAW / "ntl_adm2_monthly_all.parquet", columns=cols)

# 1. completeness of the ADM2 x month grid
n2, nm = m.ADM2CD_c.nunique(), m.date.nunique()
out["monthly_rows"], out["monthly_expected"] = len(m), n2 * nm
full = pd.MultiIndex.from_product([m.ADM2CD_c.unique(), m.date.unique()])
have = pd.MultiIndex.from_frame(m[["ADM2CD_c", "date"]])
miss = full.difference(have)
out["monthly_missing_rows"] = [(a, str(d)) for a, d in miss[:20]]

# 2. pixel-count recovery: sum/mean should be an integer (pixel counts are integers)
pos = m[(m.ntl_mean > 0)]
k = pos.ntl_sum / pos.ntl_mean
frac = (k - k.round()).abs()
relerr = frac / k.clip(lower=1)
out["npx_valid_integer_check"] = {
    "rows_with_mean_gt0": int(len(pos)),
    "share_within_0.01_of_integer": round(float((frac < 0.01).mean()), 4),
    "share_within_0.5": round(float((frac < 0.5).mean()), 4),
    "relative_error_quantiles": relerr.quantile([0.5, 0.9, 0.99, 0.999]).round(8).to_dict(),
    "median_npx": float(k.median()),
}
# is the source float32? (float32 precision of sum/mean ~ 1e-7 relative)
out["dtype_note"] = "values stored as float64 but look float32-rounded" if (
    (pos.ntl_sum.head(1000).astype(np.float32).astype(np.float64) == pos.ntl_sum.head(1000)).mean() > 0.95) else "float64"

# 3. mean NaN rows: is sum 0 there? (no-data encoded as 0 sum)
nan_mean = m[m.ntl_mean.isna()]
out["mean_nan_rows"] = int(len(nan_mean))
out["mean_nan_rows_sum_eq_0"] = int((nan_mean.ntl_sum == 0).sum())
out["mean_nan_rows_prop_na_quantiles"] = nan_mean.ntl_quality_prop_na.quantile([0, .5, 1]).round(4).to_dict()
out["mean_nan_rows_prop_na_lt_1"] = int((nan_mean.ntl_quality_prop_na < 0.999).sum())

# 4. quality denominators: props over all pixels incl. NA?
qs = m[["ntl_quality_prop_na", "ntl_quality_prop_0_good", "ntl_quality_prop_1_poor", "ntl_quality_prop_2_gapfilled"]].sum(axis=1)
out["quality_props_sum_quantiles"] = qs.quantile([0, .001, .5, 1]).round(5).to_dict()
out["quality_all_nan_rows"] = int(m.ntl_quality_prop_na.isna().sum())

# 5. dark units: mean == 0 rows and how many ADM2 never have mean > 0
out["mean_eq_0_rows"] = int((m.ntl_mean == 0).sum())

# 6. ADM1 level: share of valid pixels that are estimated (fallback) in v1
T = (pos.ntl_sum / pos.ntl_mean / (1 - pos.ntl_quality_prop_na)).groupby(pos.ADM2CD_c).median()
mm = m.assign(T=m.ADM2CD_c.map(T).fillna(0))
mm["exact"] = mm.ntl_sum / mm.ntl_mean.where(mm.ntl_mean > 0)
mm["est"] = mm["T"] * (1 - mm.ntl_quality_prop_na.fillna(1))
mm["valid"] = mm.exact.fillna(mm.est)
mm["valid_est"] = np.where(mm.exact.isna(), mm.est, 0.0)
g = mm.groupby(["ADM1CD_c", "date"])
share_est = (g.valid_est.sum() / g.valid.sum().where(g.valid.sum() > 0))
out["adm1_share_valid_px_estimated_quantiles"] = share_est.quantile([.5, .9, .99, 1]).round(4).to_dict()
out["adm1_months_any_estimated"] = int((share_est > 0).sum())
# ADM1-months with zero valid pixels but reported sum 0 (should be NA)
vz = g.valid.sum() == 0
out["adm1_months_zero_valid"] = int(vz.sum())

# 7. annual file completeness
a = pd.read_csv(RAW / "ntl_adm2_annual.csv", usecols=["ADM2CD_c", "year", "ntl_sum", "ntl_mean"])
out["annual_rows"], out["annual_expected"] = len(a), a.ADM2CD_c.nunique() * a.year.nunique()
out["annual_years"] = sorted(a.year.unique().tolist())
out["annual_adm2"] = int(a.ADM2CD_c.nunique())
out["annual_mean_nan_rows"] = int(a.ntl_mean.isna().sum())

print(json.dumps(out, indent=2, default=str))
(ROOT / "raw" / "audit_v1.json").write_text(json.dumps(out, indent=2, default=str))
