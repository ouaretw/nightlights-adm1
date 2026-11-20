"""Sanity-check gas-flaring variables in the ADM2 source."""
import numpy as np
import pandas as pd

pd.set_option("display.width", 220)
RAW = r"D:\nightlights_adm1\raw\ntl_adm2_monthly_all.parquet"
cols = ["ISO_A3", "NAM_1", "ADM2CD_c", "date", "n_gasflaring_locs", "ntl_sum",
        "ntl_gf_5km_sum", "ntl_nogf_5km_sum", "ntl_gf_10km_sum", "ntl_nogf_10km_sum"]
df = pd.read_parquet(RAW, columns=cols, filters=[("date", "==", pd.Timestamp("2024-06-01").date())])
for k in ("5km", "10km"):
    tot = df[f"ntl_gf_{k}_sum"].fillna(0) + df[f"ntl_nogf_{k}_sum"].fillna(0)
    rel = (tot - df.ntl_sum).abs() / df.ntl_sum.where(df.ntl_sum > 0)
    print(k, "gf+nogf vs total rel err quantiles:", rel.quantile([.5, .9, .99, 1]).round(6).to_dict())
    print(k, "share of ADM2 with gf_sum notna:", round(df[f"ntl_gf_{k}_sum"].notna().mean(), 3),
          " with gf_sum > 0:", round((df[f"ntl_gf_{k}_sum"] > 0).mean(), 3))
print(df[df.NAM_1.str.contains("Delhi", na=False)][cols[2:]].head(6).to_string())
# Is n_gasflaring_locs constant within country?
print("ISO with >1 distinct n_gasflaring_locs:", (df.groupby("ISO_A3").n_gasflaring_locs.nunique() > 1).sum(), "of", df.ISO_A3.nunique())
print(df[df.ISO_A3 == "DZA"].groupby("NAM_1").agg(n=("n_gasflaring_locs", "first"), gf=("ntl_gf_5km_sum", "sum"), tot=("ntl_sum", "sum")).sort_values("gf", ascending=False).head(8))
