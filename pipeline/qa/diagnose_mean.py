"""Why do some weighted ADM1 means fall outside the ADM2 mean range?"""
import numpy as np
import pandas as pd

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
RAW = r"D:\nightlights_adm1\raw\ntl_adm2_monthly_all.parquet"
df = pd.read_parquet(RAW, columns=["ISO_A3", "ADM1CD_c", "ADM2CD_c", "date", "ntl_sum", "ntl_mean", "ntl_quality_prop_na"])
ok = (df.ntl_mean > 0) & (df.ntl_quality_prop_na < 0.99)
df["npx_valid"] = df.ntl_sum / df.ntl_mean
df["T_row"] = df.npx_valid / (1 - df.ntl_quality_prop_na)
T = df.loc[ok].groupby("ADM2CD_c").T_row.median()
df["T"] = df.ADM2CD_c.map(T)
df["valid_est"] = df["T"] * (1 - df.ntl_quality_prop_na)
df["ratio"] = df.npx_valid / df.valid_est
print("ratio npx_valid/valid_est quantiles (mean>0 rows):")
print(df.loc[df.ntl_mean > 0, "ratio"].quantile([0, .001, .01, .05, .25, .5, .75, .95, .99, .999, 1]).round(4))
# rows: mean NaN but sum >0 ? mean 0 but sum>0?
print("mean NaN & sum>0:", ((df.ntl_mean.isna()) & (df.ntl_sum > 0)).sum())
print("mean==0 & sum>0:", ((df.ntl_mean == 0) & (df.ntl_sum > 0)).sum())
print("mean NaN & prop_na<1:", ((df.ntl_mean.isna()) & (df.ntl_quality_prop_na < 0.999)).sum())
# per ADM1-month: mean computed with true npx_valid (where available) vs ADM2 range
g = df.groupby(["ADM1CD_c", "date"])
true_mean = g.ntl_sum.sum() / g.npx_valid.sum()
est_mean = g.ntl_sum.sum() / g.valid_est.sum()
lo, hi = g.ntl_mean.min(), g.ntl_mean.max()
out_true = ((true_mean < lo * (1 - 1e-6)) | (true_mean > hi * (1 + 1e-6))).sum()
out_est = ((est_mean < lo * (1 - 1e-6)) | (est_mean > hi * (1 + 1e-6))).sum()
print("outside range using row npx_valid:", out_true, " using T*(1-prop_na):", out_est)
rel = (est_mean / true_mean - 1).abs()
print("rel diff est vs true mean quantiles:", rel.quantile([.5, .9, .99, .999, 1]).round(5).to_dict())
# example bad case
bad = ((est_mean < lo * (1 - 1e-6)) | (est_mean > hi * (1 + 1e-6)))
k = bad[bad].index[0]
print(k, "est", est_mean[k], "true", true_mean[k], "lo", lo[k], "hi", hi[k])
print(df[(df.ADM1CD_c == k[0]) & (df.date == k[1])])
