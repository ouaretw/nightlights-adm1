"""Tests that the source data still satisfy the assumptions S1-S7 documented in
pipeline/ntl_core.py. If the World Bank revises the dataset, these fail loudly
instead of the pipeline silently producing wrong numbers."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RAW = Path(__file__).resolve().parents[1] / "raw"
pytestmark = pytest.mark.skipif(not (RAW / "ntl_adm2_monthly_all.parquet").exists(), reason="raw source not present")

COLS = ["ISO_A3", "ADM1CD_c", "ADM2CD_c", "date", "n_gasflaring_locs", "ntl_sum", "ntl_mean",
        "ntl_quality_prop_na", "ntl_quality_prop_0_good", "ntl_quality_prop_1_poor", "ntl_quality_prop_2_gapfilled"]


@pytest.fixture(scope="module")
def m():
    return pd.read_parquet(RAW / "ntl_adm2_monthly_all.parquet", columns=COLS)


def test_s1_grid(m):
    assert m.ADM2CD_c.nunique() == 39366
    assert m.date.nunique() == 168
    assert len(m) == 39366 * 168 - 1          # known gap: SJM001001 2022-07
    assert not m.duplicated(["ADM2CD_c", "date"]).any()
    assert (m.groupby("ADM2CD_c").ADM1CD_c.nunique() == 1).all()   # strict nesting


def test_s2_weight_identity_stable(m):
    ok = (m.ntl_mean > 0) & (m.ntl_quality_prop_na < 0.99)
    t = m.loc[ok, "ntl_sum"] / m.loc[ok, "ntl_mean"] / (1 - m.loc[ok, "ntl_quality_prop_na"])
    g = t.groupby(m.loc[ok, "ADM2CD_c"])
    rel = (g.max() - g.min()) / g.median()
    assert rel.median() < 0.01                 # total weight ~ constant across months


def test_s3_no_valid_pixel_encoding(m):
    nan_mean = m[m.ntl_mean.isna()]
    assert (nan_mean.ntl_sum == 0).all()
    # prop_na = 1, or quality not reported at all (rare all-NaN quality rows)
    assert (nan_mean.ntl_quality_prop_na.isna() | (nan_mean.ntl_quality_prop_na >= 0.999999)).all()


def test_s4_dark_rows_have_zero_sum(m):
    assert (m.loc[m.ntl_mean == 0, "ntl_sum"] == 0).all()


def test_s5_quality_shares_sum_to_one(m):
    q = m[[c for c in COLS if c.startswith("ntl_quality")]].dropna()
    assert np.allclose(q.sum(axis=1), 1.0, atol=1e-4)


def test_s6_flaring_count_is_national(m):
    assert (m.groupby("ISO_A3").n_gasflaring_locs.nunique() == 1).all()
