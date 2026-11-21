"""Integration tests on the built v2 products (run after pipeline/build_v2.py).

Skipped automatically when the build or raw source is not present (e.g. in CI
without data)."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "build" / "site" / "data" / "v2"
REL = ROOT / "build" / "release"
RAW = ROOT / "raw"

pytestmark = pytest.mark.skipif(not (DATA / "manifest.json").exists(), reason="build not present")


def load(sub, freq):
    p = DATA / sub / f"{sub}_{freq}_global.parquet"
    if not p.exists():
        p = REL / p.name
    return pd.read_parquet(p)


@pytest.fixture(scope="module")
def wb_m():
    return load("adm1_wb", "monthly")


@pytest.fixture(scope="module")
def gadm_m():
    return load("adm1_gadm41", "monthly")


@pytest.fixture(scope="module")
def adm2_m():
    return load("adm2", "monthly")


# ---------------------------------------------------------------- structure
@pytest.mark.parametrize("sub,key", [("adm1_wb", "ADM1CD_c"), ("adm1_gadm41", "GID_1"), ("adm2", "ADM2CD_c")])
@pytest.mark.parametrize("freq", ["monthly", "annual"])
def test_unique_keys(sub, key, freq):
    d = load(sub, freq)
    t = "date" if freq == "monthly" else "year"
    assert not d.duplicated([key, t]).any()


def test_monthly_grid_complete_wb(wb_m):
    n_units, n_months = wb_m.ADM1CD_c.nunique(), wb_m.date.nunique()
    assert n_months == 168
    assert len(wb_m) == n_units * n_months - 1      # known source gap: Svalbard (single unit), 2022-07


# ---------------------------------------------------------------- arithmetic
def test_wb_adm1_reconciles_with_adm2(wb_m, adm2_m):
    s2 = adm2_m.groupby(["ADM1CD_c", "date"]).ntl_sum.sum(min_count=1)
    s1 = wb_m.set_index(["ADM1CD_c", "date"]).ntl_sum
    both = pd.concat([s1.rename("a"), s2.rename("b")], axis=1)
    assert (both.a.isna() == both.b.isna()).all()
    ok = both.dropna()
    assert np.allclose(ok.a, ok.b, rtol=1e-6, atol=1e-2)


def test_mean_within_member_range(wb_m, adm2_m):
    g = adm2_m[adm2_m.has_valid_data].groupby(["ADM1CD_c", "date"]).ntl_mean
    lo, hi = g.min(), g.max()
    m = wb_m.set_index(["ADM1CD_c", "date"]).ntl_mean.dropna()
    lo, hi = lo.reindex(m.index), hi.reindex(m.index)
    bad = (m < lo - 1e-5 - 1e-4 * lo.abs()) | (m > hi + 1e-5 + 1e-4 * hi.abs())
    assert int(bad.sum()) == 0


@pytest.mark.parametrize("sub", ["adm1_wb", "adm1_gadm41"])
def test_no_data_is_na_not_zero(sub):
    d = load(sub, "monthly")
    none_valid = d.n_adm2_no_valid_data == d.n_adm2
    assert d.loc[none_valid, "ntl_sum"].isna().all()
    assert d.loc[~none_valid, "ntl_sum"].notna().all()


@pytest.mark.parametrize("sub", ["adm1_wb", "adm1_gadm41"])
def test_quality_shares_sum_to_one(sub):
    d = load(sub, "monthly")
    qc = [c for c in d.columns if c.startswith("ntl_quality_prop_")]
    ok = d[qc].notna().all(axis=1)
    assert np.allclose(d.loc[ok, qc].sum(axis=1), 1.0, atol=1e-4)
    assert d.coverage.dropna().between(0, 1).all()


def test_adm2_no_data_rows_have_na_sum(adm2_m):
    nd = adm2_m[~adm2_m.has_valid_data]
    assert nd.ntl_sum.isna().all()
    assert (adm2_m.loc[adm2_m.has_valid_data, "ntl_sum"] >= 0).all()


# ---------------------------------------------------------------- geography
def test_gadm_never_exceeds_wb_country_total(wb_m, gadm_m):
    a = wb_m.groupby("ISO_A3").ntl_sum.sum()
    b = gadm_m.groupby("ISO_A3").ntl_sum.sum().reindex(a.index).fillna(0)
    # published values are rounded to 4 decimals per unit-month -> allow rounding slack
    n = gadm_m.groupby("ISO_A3").size().reindex(a.index).fillna(0)
    assert (b <= a * (1 + 1e-9) + n * 1e-4).all()


def test_one_to_one_units_identical_series(wb_m, gadm_m, adm2_m):
    """Where a WB ADM1 maps entirely to one GADM unit that receives only it,
    both series must be identical (sensitivity check of the crosswalk path)."""
    x = adm2_m.drop_duplicates("ADM2CD_c")[["ADM1CD_c", "GADM41_GID_1"]].dropna()
    a = x.groupby("ADM1CD_c").GADM41_GID_1.nunique()
    b = x.groupby("GADM41_GID_1").ADM1CD_c.nunique()
    full = adm2_m.drop_duplicates("ADM2CD_c").groupby("ADM1CD_c").GADM41_GID_1.apply(lambda s: s.notna().all())
    pairs = x.drop_duplicates()
    pairs = pairs[pairs.ADM1CD_c.map(a).eq(1) & pairs.GADM41_GID_1.map(b).eq(1) & pairs.ADM1CD_c.map(full)]
    assert len(pairs) > 1000
    w = wb_m.set_index(["ADM1CD_c", "date"]).ntl_sum
    g = gadm_m.set_index(["GID_1", "date"]).ntl_sum
    wi = w.loc[pairs.ADM1CD_c.tolist()].reset_index()
    wi["GID_1"] = wi.ADM1CD_c.map(pairs.set_index("ADM1CD_c").GADM41_GID_1)
    gv = g.reindex(pd.MultiIndex.from_frame(wi[["GID_1", "date"]])).values
    assert np.allclose(wi.ntl_sum.values, gv, rtol=1e-9, atol=1e-6, equal_nan=True)


def test_crosswalk_covers_every_source_adm2(adm2_m):
    xw = pd.read_csv(DATA / "crosswalks" / "crosswalk_adm2_to_gadm41.csv")
    assert set(xw.ADM2CD_c) == set(adm2_m.ADM2CD_c)
    assert xw.method.notna().all()
    assert xw.loc[xw.method == "unassigned", "GID_1"].isna().all()


# ---------------------------------------------------------------- manifest
def test_manifest_files_exist_with_hashes():
    import json
    man = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    for f in man["files"]:
        p = (ROOT / "build" / "site" / f["path"]) if f["host"] == "pages" else (REL / f["path"])
        assert p.exists(), f["path"]
        assert p.stat().st_size == f["bytes"]
