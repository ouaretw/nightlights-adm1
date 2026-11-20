"""Profile the raw ADM2 parquet: coverage, keys, NaN patterns, and the
stability of the implied pixel count (sum / mean) used for weighting."""
import numpy as np
import pandas as pd

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)

RAW = r"D:\nightlights_adm1\raw\ntl_adm2_monthly_all.parquet"
cols = ["ISO_A3", "ADM1CD_c", "ADM2CD_c", "NAM_0", "NAM_1", "date",
        "ntl_sum", "ntl_mean", "ntl_max", "ntl_quality_prop_na",
        "ntl_quality_prop_0_good", "ntl_quality_prop_1_poor",
        "ntl_quality_prop_2_gapfilled", "ntl_gf_5km_sum", "ntl_gf_5km_mean",
        "ntl_nogf_5km_sum", "n_gasflaring_locs"]
df = pd.read_parquet(RAW, columns=cols)
print("rows", len(df))
print("countries", df.ISO_A3.nunique(), "adm1", df.ADM1CD_c.nunique(), "adm2", df.ADM2CD_c.nunique())
print("dates", df.date.min(), df.date.max(), df.date.nunique())
print("dup keys", df.duplicated(["ADM2CD_c", "date"]).sum())
print("ADM2 in >1 ADM1:", (df.groupby("ADM2CD_c").ADM1CD_c.nunique() > 1).sum())
print("null ADM1 codes", df.ADM1CD_c.isna().sum(), "null ISO", df.ISO_A3.isna().sum())
print("NaN share per col:\n", df.isna().mean().round(4))

# quality props: do they sum to 1?
q = df[["ntl_quality_prop_na", "ntl_quality_prop_0_good", "ntl_quality_prop_1_poor", "ntl_quality_prop_2_gapfilled"]].sum(axis=1)
print("quality prop row-sum quantiles", q.quantile([0, .01, .5, .99, 1]).round(4).to_dict())

# implied pixel count
pos = df[(df.ntl_mean > 0) & df.ntl_sum.notna()]
pos = pos.assign(npx=pos.ntl_sum / pos.ntl_mean)
g = pos.groupby("ADM2CD_c").npx
stab = (g.max() - g.min()) / g.median()
print("implied npx median-per-ADM2 quantiles", g.median().quantile([0, .1, .5, .9, 1]).round(1).to_dict())
print("relative range of npx across months, quantiles", stab.quantile([.5, .9, .99, 1]).round(4).to_dict())
# does npx vary with prop_na? (i.e. mean over non-NA pixels)
pos = pos.assign(npx_full=pos.npx / (1 - pos.ntl_quality_prop_na).clip(lower=1e-9))
g2 = pos[pos.ntl_quality_prop_na < 0.99].groupby("ADM2CD_c").npx_full
stab2 = (g2.max() - g2.min()) / g2.median()
print("relative range of npx/(1-prop_na), quantiles", stab2.quantile([.5, .9, .99, 1]).round(4).to_dict())
# ADM2s never positive
allzero = set(df.ADM2CD_c) - set(pos.ADM2CD_c)
print("ADM2 never with mean>0:", len(allzero))
print("ADM1 named 'not available':", df.loc[df.NAM_1.str.contains("not available", na=False), "ADM1CD_c"].nunique())
print(df.groupby("ISO_A3").ADM1CD_c.nunique().describe())
