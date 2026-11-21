"""Core, tested logic for aggregating the World Bank Space2Stats Black Marble
ADM2 tables (dataset 0066940) to coarser units.

Source facts this module relies on (verified by pipeline/qa/audit_v1.py and
tests/test_source_assumptions.py):

S1  Grid: one row per ADM2 x period. Monthly: 39,366 ADM2 x 168 months minus
    one missing row (SJM001001, 2022-07). Annual: complete, 2012-2024.
S2  ntl_mean is a weighted mean over *valid* pixels; ntl_sum the matching
    weighted sum. Weights are fractional (sum/mean is not an integer), i.e.
    pixel-coverage weights as produced by exact zonal extraction. Hence
        W_valid = ntl_sum / ntl_mean            (exact identity when mean > 0)
    and an aggregate mean  sum(S_i) / sum(W_i)  equals the coverage-weighted
    mean over all valid pixels of the union - exact, not an approximation.
S3  When an ADM2 has no valid pixel in a period, the source sets
    prop_na = 1, mean = NaN and **sum = 0**. That 0 is "no data", not "dark".
S4  When an ADM2 is valid but completely dark, mean = 0 and sum = 0, so
    W_valid cannot be recovered from that row. We then *estimate*
        W_valid = T * (1 - prop_na),  T = median_t[ sum/mean/(1-prop_na) ]
    and flag it. It only affects the denominator of an aggregate mean when
    dark and lit units are mixed.
S5  Quality shares (na, good, poor, gap-filled) sum to 1 over all pixels of
    the unit (same weights), so the total weight is W_valid / (1 - prop_na).
S6  n_gasflaring_locs is constant within each country (a national count).
S7  Medians and percentiles cannot be aggregated from unit summaries.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SUM_VARS = ["ntl_sum", "ntl_nogf_5km_sum", "ntl_nogf_10km_sum", "ntl_gf_5km_sum", "ntl_gf_10km_sum"]
Q_VARS = ["ntl_quality_prop_na", "ntl_quality_prop_0_good", "ntl_quality_prop_1_poor",
          "ntl_quality_prop_2_gapfilled"]
NATIVE_ONLY = ["ntl_median", "ntl_q05", "ntl_q95"]          # ADM2 only (S7)
ID_VARS = ["ISO_A3", "NAM_0", "ADM1CD_c", "NAM_1", "ADM2CD_c", "NAM_2"]
SOURCE_COLS = ID_VARS + ["n_gasflaring_locs", "ntl_mean", "ntl_max"] + NATIVE_ONLY + SUM_VARS + Q_VARS


def total_weights(df: pd.DataFrame) -> pd.Series:
    """Static total weight T per ADM2 (median over periods of sum/mean/(1-prop_na))."""
    ok = (df.ntl_mean > 0) & (df.ntl_quality_prop_na < 0.99)
    t = df.loc[ok, "ntl_sum"] / df.loc[ok, "ntl_mean"] / (1 - df.loc[ok, "ntl_quality_prop_na"])
    return t.groupby(df.loc[ok, "ADM2CD_c"]).median().rename("T")


def prepare_adm2(df: pd.DataFrame, T: pd.Series) -> pd.DataFrame:
    """Add weights, flags and NA-corrected sums to ADM2 rows (source values untouched
    except that 'no valid pixel' sums become NA, S3)."""
    d = df.copy()
    pna = d["ntl_quality_prop_na"]
    no_valid = (pna >= 0.999999) | d["ntl_mean"].isna()
    d["has_valid_data"] = ~no_valid
    exact = d["ntl_sum"] / d["ntl_mean"].where(d["ntl_mean"] > 0)
    t = d["ADM2CD_c"].map(T)
    est = t * (1 - pna.fillna(1.0))
    d["w_valid"] = np.where(no_valid, 0.0, exact.fillna(est))
    d["w_valid_estimated"] = (~no_valid) & exact.isna()
    # total weight: exact where recoverable (S5), else static T
    tot_exact = exact / (1 - pna).where(pna < 0.999999)
    d["w_total"] = tot_exact.fillna(t)
    d["w_total_estimated"] = tot_exact.isna()
    for c in SUM_VARS:
        d[c] = d[c].where(~no_valid)          # S3: 0 -> NA when nothing was observed
    # units with no recoverable weight at all (never lit): w unknown
    d["w_valid"] = d["w_valid"].fillna(0.0)
    d["w_total"] = d["w_total"].fillna(0.0)
    return d


def aggregate(d: pd.DataFrame, keys: list[str], time_col: str) -> pd.DataFrame:
    """Aggregate prepared ADM2 rows to `keys` + time. Exact for sums/max; mean is
    coverage-weighted (S2); quality shares weighted by total weight (S5)."""
    x = d.copy()
    x["_w_est_part"] = np.where(x["w_valid_estimated"], x["w_valid"], 0.0)
    x["_no_valid"] = (~x["has_valid_data"]).astype("int32")
    x["_any_valid"] = x["has_valid_data"].astype("int32")
    # quality shares: only districts that report them (the source has rare all-NaN rows)
    has_q = x[Q_VARS].notna().all(axis=1)
    x["_wt_q"] = np.where(has_q, x["w_total"], 0.0)
    for q in Q_VARS:
        x[q + "__w"] = np.where(has_q, x[q], 0.0) * x["w_total"]
    g = x.groupby(keys + [time_col], sort=True, dropna=False)
    out = g[SUM_VARS].sum(min_count=1)
    out["ntl_max"] = g["ntl_max"].max()
    wv, wt = g["w_valid"].sum(), g["w_total"].sum()
    out["w_valid"], out["w_total"] = wv, wt
    any_valid = g["_any_valid"].sum() > 0
    out["ntl_mean"] = out["ntl_sum"] / wv.where(wv > 0)
    # valid but completely dark with unrecoverable weight (e.g. always-dark islands): mean is 0
    out.loc[any_valid & (wv <= 0) & (out["ntl_sum"] == 0), "ntl_mean"] = 0.0
    out["coverage"] = (wv / wt.where(wt > 0)).clip(0, 1)
    out["w_valid_estimated_share"] = g["_w_est_part"].sum() / wv.where(wv > 0)
    wtq = g["_wt_q"].sum()
    for q in Q_VARS:
        out[q] = g[q + "__w"].sum() / wtq.where(wtq > 0)
    out["n_adm2"] = g["ADM2CD_c"].nunique()
    out["n_adm2_no_valid_data"] = g["_no_valid"].sum()
    out["n_gasflaring_locs_country"] = g["n_gasflaring_locs"].first()
    # no district with a valid observation -> every sum NA (not 0); dark-but-valid stays 0
    for c in SUM_VARS:
        out.loc[~any_valid, c] = np.nan
    return out.reset_index()


def add_transforms(df: pd.DataFrame, by: list[str], time_col: str, annual: bool) -> pd.DataFrame:
    """log / asinh transforms and (annual only) year-on-year changes."""
    d = df.sort_values(by + [time_col]).copy()
    for c in ["ntl_sum", "ntl_mean", "ntl_nogf_5km_sum"]:
        v = d[c]
        d[f"ln_{c}"] = np.log(v.where(v > 0))
        d[f"asinh_{c}"] = np.arcsinh(v)
    if annual:
        g = d.groupby(by, sort=False)
        for c in ["ntl_sum", "ntl_nogf_5km_sum"]:
            prev = g[c].shift(1)
            prev_year = g[time_col].shift(1)
            consecutive = (d[time_col] - prev_year) == 1
            d[f"dln_{c}"] = np.where(consecutive, np.log(d[c].where(d[c] > 0)) - np.log(prev.where(prev > 0)), np.nan)
            d[f"pct_change_{c}"] = np.where(consecutive & (prev > 0), d[c] / prev - 1, np.nan)
    return d


def annual_from_monthly(monthly: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Annual values derived from monthly observations (kept separate from the
    official NASA annual composite). Uses only months with valid data."""
    m = monthly.copy()
    m["year"] = pd.to_datetime(m["date"]).dt.year
    g = m.groupby(by + ["year"])
    out = pd.DataFrame({
        "n_months": g["date"].nunique(),
        "n_months_with_data": g["ntl_sum"].count(),
        "ntl_sum_monthly_mean": g["ntl_sum"].mean(),
        "ntl_nogf_5km_sum_monthly_mean": g["ntl_nogf_5km_sum"].mean(),
        "ntl_mean_from_monthly": g["ntl_sum"].sum(min_count=1) / g["w_valid"].sum().where(g["w_valid"].sum() > 0),
        "coverage_monthly_mean": g["coverage"].mean(),
    })
    return out.reset_index()


def round_output(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    for c in d.columns:
        if d[c].dtype.kind != "f":
            continue
        if c.startswith(("ntl_quality", "coverage", "w_valid_estimated_share")):
            d[c] = d[c].round(6)
        elif c in ("w_valid", "w_total"):
            d[c] = d[c].round(3)
        elif c.startswith(("ln_", "asinh_", "dln_", "pct_change")):
            d[c] = d[c].round(6)
        elif "mean" in c:
            d[c] = d[c].round(6)
        else:
            d[c] = d[c].round(4)
    return d
