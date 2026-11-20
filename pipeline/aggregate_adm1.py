"""Aggregate the World Bank / NASA Black Marble ADM2 nighttime-lights tables
(Space2Stats, dataset 0066940) to ADM1.

Inputs  (raw/, not committed):
    ntl_adm2_monthly_all.parquet   monthly, 2012-01 .. 2025-12
    ntl_adm2_annual.csv            annual composites

Outputs (docs/data/):
    adm1_monthly_all.parquet, adm1_monthly_all.csv.gz
    adm1_annual_all.parquet,  adm1_annual_all.csv.gz
    monthly/<ISO3>.csv, annual/<ISO3>.csv          per-country CSVs
    adm1_index.json                                 country -> ADM1 list for the site
    series/<ISO3>.json                              compact series for the site charts

Method (see METHODS.md for the full rationale):
  * ADM2 units nest exactly in ADM1 (same World Bank Official Boundaries
    vintage; every ADM2CD_c maps to one ADM1CD_c), so aggregation is a
    group-by on ADM1CD_c - no spatial overlay.
  * Sums (ntl_sum and the gas-flaring variants) are additive: ADM1 = sum of ADM2.
  * ntl_max: ADM1 = max of ADM2 maxima (exact).
  * ntl_mean is a mean over *valid* (non-NA) pixels, so the valid-pixel count
    of ADM2 i in period t is exactly sum_it / mean_it whenever mean_it > 0.
    When mean_it == 0 (sum is then 0 too) we use T_i * (1 - prop_na_it), where
    T_i = median_t[ sum / mean / (1 - prop_na) ] is the static total pixel
    count (stable to 0.14% median relative range across months).
    ADM1 mean = sum(ntl_sum) / sum(valid)  - exact pixel-weighted mean.
  * Quality shares are pixel-weighted with T_i.
  * coverage = sum(valid) / sum(T): share of ADM1 pixels with a valid value.
  * Medians and percentiles cannot be recovered from ADM2 summaries and are
    NOT published.
  * Gas-flaring variants: only sums are published (their pixel counts per
    sub-area are not recoverable reliably).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
OUT = ROOT / "docs" / "data"

SUM_COLS = ["ntl_sum", "ntl_nogf_5km_sum", "ntl_nogf_10km_sum",
            "ntl_gf_5km_sum", "ntl_gf_10km_sum"]
Q_COLS = ["ntl_quality_prop_na", "ntl_quality_prop_0_good",
          "ntl_quality_prop_1_poor", "ntl_quality_prop_2_gapfilled"]
ID_COLS = ["ISO_A3", "NAM_0", "ADM1CD_c", "NAM_1"]
READ_COLS = ID_COLS + ["ADM2CD_c", "n_gasflaring_locs", "ntl_mean", "ntl_max"] + SUM_COLS + Q_COLS


def pixel_weights(df: pd.DataFrame) -> pd.Series:
    """Static total pixel count per ADM2 from sum/mean/(1-prop_na)."""
    ok = (df.ntl_mean > 0) & (df.ntl_quality_prop_na < 0.99)
    t = df.loc[ok, "ntl_sum"] / df.loc[ok, "ntl_mean"] / (1 - df.loc[ok, "ntl_quality_prop_na"])
    return t.groupby(df.loc[ok, "ADM2CD_c"]).median().rename("T")


def aggregate(df: pd.DataFrame, time_col: str, T: pd.Series) -> pd.DataFrame:
    df = df.join(T, on="ADM2CD_c")
    df["T"] = df["T"].fillna(0.0)          # 14 ADM2 never lit: weight unknown -> 0
    # exact valid-pixel count where recoverable (sum/mean); for dark units
    # (mean == 0, hence sum == 0) fall back to T * (1 - prop_na)
    est = df["T"] * (1 - df["ntl_quality_prop_na"].fillna(1.0))
    exact = df["ntl_sum"] / df["ntl_mean"].where(df["ntl_mean"] > 0)
    df["valid"] = exact.fillna(est)
    for q in Q_COLS:
        df[q + "_w"] = df[q].fillna(0.0) * df["T"]
    # gas-flaring sums are NaN where an ADM2 has no flare buffer; NaN -> 0 in the
    # sum, but keep NaN at ADM1 when *no* ADM2 had a value
    keys = ["ISO_A3", "ADM1CD_c", time_col]
    g = df.groupby(keys, sort=True)
    out = g[SUM_COLS].sum(min_count=1)
    out["ntl_max"] = g["ntl_max"].max()
    # NB: in the source, n_gasflaring_locs is a COUNTRY-level count repeated on
    # every ADM2 row (constant within each ISO_A3), despite the docs saying "in
    # the ADM unit". Summing it would be wrong, so it is carried as a country value.
    out["n_gasflaring_locs_country"] = g["n_gasflaring_locs"].first()
    out["n_adm2"] = g["ADM2CD_c"].nunique()
    tsum = g["T"].sum()
    vsum = g["valid"].sum()
    out["n_pixels"] = tsum.round().astype("int64")
    out["ntl_mean"] = np.where(vsum > 0, out["ntl_sum"] / vsum.where(vsum > 0), np.nan)
    out["coverage"] = np.clip(np.where(tsum > 0, vsum / tsum.where(tsum > 0), np.nan), 0, 1)
    for q in Q_COLS:
        out[q] = np.where(tsum > 0, g[q + "_w"].sum() / tsum.where(tsum > 0), np.nan)
    out = out.reset_index()
    names = df.drop_duplicates("ADM1CD_c").set_index("ADM1CD_c")[["NAM_0", "NAM_1"]]
    out = out.join(names, on="ADM1CD_c")
    # ADM1 named "Administrative unit not available" = country has no ADM1 tier
    na = out["NAM_1"].str.contains("not available", case=False, na=False)
    out.loc[na, "NAM_1"] = out.loc[na, "NAM_0"] + " (no ADM1 tier)"
    order = ["ISO_A3", "NAM_0", "ADM1CD_c", "NAM_1", time_col,
             "ntl_sum", "ntl_mean", "ntl_max", "ntl_nogf_5km_sum", "ntl_nogf_10km_sum",
             "ntl_gf_5km_sum", "ntl_gf_10km_sum", "n_gasflaring_locs_country", "coverage",
             *Q_COLS, "n_pixels", "n_adm2"]
    return out[order]


def round_floats(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ["ntl_sum", "ntl_nogf_5km_sum", "ntl_nogf_10km_sum", "ntl_gf_5km_sum", "ntl_gf_10km_sum", "ntl_max"]:
        df[c] = df[c].round(3)
    df["ntl_mean"] = df["ntl_mean"].round(5)
    for c in ["coverage", *Q_COLS]:
        df[c] = df[c].round(5)
    return df


def validate(adm2: pd.DataFrame, adm1: pd.DataFrame, time_col: str) -> dict:
    """Check that ADM1 sums reproduce country totals from ADM2 exactly."""
    c2 = adm2.groupby(["ISO_A3", time_col]).ntl_sum.sum()
    c1 = adm1.groupby(["ISO_A3", time_col]).ntl_sum.sum()
    rel = ((c1 - c2).abs() / c2.where(c2 > 1)).max()
    # mean must lie within [min, max] of its ADM2 means (sanity of weighting)
    lo = adm2.groupby(["ADM1CD_c", time_col]).ntl_mean.min()
    hi = adm2.groupby(["ADM1CD_c", time_col]).ntl_mean.max()
    m = adm1.set_index(["ADM1CD_c", time_col]).ntl_mean
    lo, hi = lo.reindex(m.index), hi.reindex(m.index)
    bad =((m < lo * (1 - 1e-6) - 1e-9) | (m > hi * (1 + 1e-6) + 1e-9)).sum()
    return {"rows": int(len(adm1)), "adm1": int(adm1.ADM1CD_c.nunique()),
            "countries": int(adm1.ISO_A3.nunique()), "max_rel_err_country_sum": float(rel),
            "adm1_mean_outside_adm2_range": int(bad)}


def write_outputs(adm1: pd.DataFrame, label: str, time_col: str):
    (OUT / label).mkdir(parents=True, exist_ok=True)
    adm1.to_parquet(OUT / f"adm1_{label}_all.parquet", index=False, compression="zstd")
    adm1.to_csv(OUT / f"adm1_{label}_all.csv.gz", index=False, compression="gzip")
    for iso, d in adm1.groupby("ISO_A3"):
        d.to_csv(OUT / label / f"{iso}.csv", index=False)


def write_site_series(monthly: pd.DataFrame, annual: pd.DataFrame):
    """Compact per-country JSON for the browser charts."""
    sdir = OUT / "series"
    sdir.mkdir(parents=True, exist_ok=True)
    months = sorted(monthly["date"].unique())
    years = sorted(annual["year"].unique())
    index = []
    for iso, dm in monthly.groupby("ISO_A3"):
        da = annual[annual.ISO_A3 == iso]
        regions = []
        for code, r in dm.groupby("ADM1CD_c"):
            r = r.set_index("date").reindex(months)
            ra = da[da.ADM1CD_c == code].set_index("year").reindex(years)
            def arr(s, nd):
                return [None if pd.isna(v) else round(float(v), nd) for v in s]
            regions.append({
                "code": code,
                "name": dm.loc[dm.ADM1CD_c == code, "NAM_1"].iloc[0],
                "m_sum": arr(r["ntl_sum"], 1), "m_mean": arr(r["ntl_mean"], 4),
                "m_nogf": arr(r["ntl_nogf_5km_sum"], 1), "m_cov": arr(r["coverage"], 3),
                "a_sum": arr(ra["ntl_sum"], 1), "a_mean": arr(ra["ntl_mean"], 4),
                "a_nogf": arr(ra["ntl_nogf_5km_sum"], 1),
            })
        payload = {"iso": iso, "name": dm["NAM_0"].iloc[0],
                   "months": [str(m)[:7] for m in months], "years": [int(y) for y in years],
                   "regions": regions}
        (sdir / f"{iso}.json").write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        index.append({"iso": iso, "name": payload["name"], "n_adm1": len(regions),
                      "adm1": [{"code": r["code"], "name": r["name"]} for r in regions]})
    index.sort(key=lambda x: x["name"])
    (OUT / "adm1_index.json").write_text(json.dumps(index, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("reading monthly ADM2 ...", flush=True)
    m2 = pd.read_parquet(RAW / "ntl_adm2_monthly_all.parquet", columns=READ_COLS + ["date"])
    T = pixel_weights(m2)
    print(f"  pixel weights for {len(T)} / {m2.ADM2CD_c.nunique()} ADM2", flush=True)
    m1 = aggregate(m2, "date", T)
    vm = validate(m2, m1, "date")
    m1 = round_floats(m1)
    print("  monthly:", vm, flush=True)

    print("reading annual ADM2 ...", flush=True)
    a2 = pd.read_csv(RAW / "ntl_adm2_annual.csv", usecols=lambda c: c in set(READ_COLS + ["year"]),
                     dtype={"ADM1CD_c": str, "ADM2CD_c": str, "ISO_A3": str})
    a1 = aggregate(a2, "year", T)
    va = validate(a2, a1, "year")
    a1 = round_floats(a1)
    print("  annual:", va, flush=True)

    m1["date"] = pd.to_datetime(m1["date"]).dt.strftime("%Y-%m")
    write_outputs(m1, "monthly", "date")
    write_outputs(a1, "annual", "year")
    write_site_series(m1, a1)
    meta = {"source": "World Bank Space2Stats - Monthly & Annual Black Marble Nighttime Lights (dataset 0066940, v2)",
            "source_url": "https://datacatalog.worldbank.org/search/dataset/0066940",
            "months": [m1.date.min(), m1.date.max()], "years": [int(a1.year.min()), int(a1.year.max())],
            "monthly": vm, "annual": va,
            "adm2_with_pixel_weight": int(len(T)), "adm2_total": int(m2.ADM2CD_c.nunique())}
    (OUT / "build_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    sys.exit(main())
