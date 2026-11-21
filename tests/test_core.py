"""Unit tests for the aggregation arithmetic on synthetic data with known answers."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import ntl_core as core  # noqa: E402


def make(rows):
    base = {"ISO_A3": "AAA", "NAM_0": "A", "NAM_1": "P", "NAM_2": "D", "n_gasflaring_locs": 3,
            "ntl_max": 1.0, "ntl_median": 0.5, "ntl_q05": 0.0, "ntl_q95": 1.0,
            "ntl_nogf_5km_sum": np.nan, "ntl_nogf_10km_sum": np.nan,
            "ntl_gf_5km_sum": np.nan, "ntl_gf_10km_sum": np.nan,
            "ntl_quality_prop_0_good": 0.0, "ntl_quality_prop_1_poor": 0.0, "ntl_quality_prop_2_gapfilled": 0.0}
    df = pd.DataFrame([{**base, **r} for r in rows])
    df["ntl_nogf_5km_sum"] = df["ntl_nogf_5km_sum"].fillna(df["ntl_sum"])
    df["ntl_quality_prop_0_good"] = 1 - df["ntl_quality_prop_na"].fillna(1)
    return df


# Two lit districts with fractional weights 100.5 and 300.25 -> exact pooled mean
LIT = [
    {"ADM1CD_c": "P1", "ADM2CD_c": "D1", "date": "2020-01", "ntl_sum": 201.0, "ntl_mean": 2.0, "ntl_quality_prop_na": 0.0},
    {"ADM1CD_c": "P1", "ADM2CD_c": "D2", "date": "2020-01", "ntl_sum": 1201.0, "ntl_mean": 4.0, "ntl_quality_prop_na": 0.0},
]


def run(rows, T=None):
    df = make(rows)
    T = core.total_weights(df) if T is None else T
    return core.aggregate(core.prepare_adm2(df, T), ["ISO_A3", "ADM1CD_c"], "date")


def test_sum_exact_and_mean_coverage_weighted():
    out = run(LIT)
    r = out.iloc[0]
    assert r.ntl_sum == pytest.approx(1402.0)
    # weights: 201/2 = 100.5 and 1201/4 = 300.25
    assert r.w_valid == pytest.approx(400.75)
    assert r.ntl_mean == pytest.approx(1402.0 / 400.75)
    assert r.w_valid_estimated_share == 0
    assert r.coverage == pytest.approx(1.0)


def test_mean_lies_within_member_means():
    r = run(LIT).iloc[0]
    assert 2.0 <= r.ntl_mean <= 4.0


def test_no_valid_data_sum_becomes_na_not_zero():
    rows = [{"ADM1CD_c": "P1", "ADM2CD_c": "D1", "date": "2020-06", "ntl_sum": 0.0, "ntl_mean": np.nan,
             "ntl_quality_prop_na": 1.0}]
    T = pd.Series({"D1": 100.0}, name="T")
    r = run(rows, T).iloc[0]
    assert np.isnan(r.ntl_sum) and np.isnan(r.ntl_mean)
    assert r.coverage == 0
    assert r.n_adm2_no_valid_data == 1


def test_partial_missing_reduces_coverage_and_keeps_sum():
    rows = LIT[:1] + [{"ADM1CD_c": "P1", "ADM2CD_c": "D2", "date": "2020-01", "ntl_sum": 0.0, "ntl_mean": np.nan,
                       "ntl_quality_prop_na": 1.0}]
    T = pd.Series({"D1": 100.5, "D2": 300.25}, name="T")
    r = run(rows, T).iloc[0]
    assert r.ntl_sum == pytest.approx(201.0)
    assert r.ntl_mean == pytest.approx(2.0)
    assert r.coverage == pytest.approx(100.5 / 400.75)


def test_dark_unit_weight_is_estimated_and_flagged():
    rows = LIT[:1] + [{"ADM1CD_c": "P1", "ADM2CD_c": "D3", "date": "2020-01", "ntl_sum": 0.0, "ntl_mean": 0.0,
                       "ntl_quality_prop_na": 0.2}]
    T = pd.Series({"D1": 100.5, "D3": 50.0}, name="T")
    r = run(rows, T).iloc[0]
    assert r.w_valid == pytest.approx(100.5 + 40.0)          # 50 * (1 - 0.2)
    assert r.w_valid_estimated_share == pytest.approx(40.0 / 140.5)
    assert r.ntl_mean == pytest.approx(201.0 / 140.5)


def test_quality_shares_weighted_and_sum_to_one():
    rows = [dict(LIT[0], ntl_quality_prop_na=0.5, ntl_sum=100.5, ntl_mean=2.0),
            dict(LIT[1], ntl_quality_prop_na=0.0)]
    r = run(rows).iloc[0]
    # D1: valid 50.25 of total 100.5 ; D2: valid 300.25 of 300.25
    assert r.ntl_quality_prop_na == pytest.approx(50.25 / 400.75)
    total = r[["ntl_quality_prop_na", "ntl_quality_prop_0_good", "ntl_quality_prop_1_poor",
               "ntl_quality_prop_2_gapfilled"]].sum()
    assert total == pytest.approx(1.0)


def test_always_dark_unit_with_unknown_weight_is_zero_not_na():
    rows = [{"ADM1CD_c": "P1", "ADM2CD_c": "D9", "date": "2020-01", "ntl_sum": 0.0, "ntl_mean": 0.0,
             "ntl_quality_prop_na": 0.0}]
    T = pd.Series(dtype=float, name="T")              # weight never recoverable
    r = run(rows, T).iloc[0]
    assert r.ntl_sum == 0.0 and r.ntl_mean == 0.0
    assert np.isnan(r.coverage)                        # unknown, not 0


def test_quality_shares_ignore_districts_without_quality():
    rows = [dict(LIT[0]), dict(LIT[1], ntl_quality_prop_na=np.nan, ntl_quality_prop_0_good=np.nan)]
    df = make(rows)
    df.loc[1, ["ntl_quality_prop_na", "ntl_quality_prop_0_good"]] = np.nan
    r = core.aggregate(core.prepare_adm2(df, core.total_weights(df)), ["ISO_A3", "ADM1CD_c"], "date").iloc[0]
    total = r[["ntl_quality_prop_na", "ntl_quality_prop_0_good", "ntl_quality_prop_1_poor",
               "ntl_quality_prop_2_gapfilled"]].sum()
    assert total == pytest.approx(1.0)


def test_max_is_max_of_members():
    rows = [dict(LIT[0], ntl_max=7.0), dict(LIT[1], ntl_max=9.5)]
    assert run(rows).iloc[0].ntl_max == 9.5


def test_transforms_and_yoy_only_for_consecutive_years():
    df = pd.DataFrame({"k": ["a"] * 3, "year": [2012, 2013, 2015], "ntl_sum": [1.0, np.e, 5.0],
                       "ntl_mean": [1.0, 1.0, 0.0], "ntl_nogf_5km_sum": [1.0, 1.0, 1.0]})
    t = core.add_transforms(df, ["k"], "year", annual=True)
    assert t.ln_ntl_sum.iloc[1] == pytest.approx(1.0)
    assert t.dln_ntl_sum.iloc[1] == pytest.approx(1.0)
    assert np.isnan(t.dln_ntl_sum.iloc[2])            # 2013 -> 2015 not consecutive
    assert np.isnan(t.ln_ntl_mean.iloc[2])            # log(0) -> NA
    assert t.asinh_ntl_mean.iloc[2] == 0.0            # asinh(0) = 0
