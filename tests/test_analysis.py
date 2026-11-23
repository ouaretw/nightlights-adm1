"""Checks for the economic-analysis layer (pipeline/build_analysis.py outputs).

Covers: unique keys, exact national aggregation, IMF and WDI joins, consistency
between the downloadable national panel and the JSON the charts read, model
sample sizes, and the logs-of-positive-values rule.
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "build" / "site" / "data" / "v2"
AN = DATA / "analysis"
pytestmark = pytest.mark.skipif(not (AN / "national.json").exists(), reason="analysis build not present")


@pytest.fixture(scope="module")
def nat():
    return pd.read_parquet(DATA / "adm0" / "ntl_adm0_annual_econ.parquet")


@pytest.fixture(scope="module")
def adm1():
    return pd.read_parquet(DATA / "adm1_wb" / "adm1_wb_annual_global.parquet")


def close(a, b, rel=5e-5):
    if a is None or (isinstance(a, float) and math.isnan(a)):
        return b is None or (isinstance(b, float) and math.isnan(b))
    return b is not None and abs(a - b) <= rel * max(abs(a), abs(b), 1e-12)


def test_unique_iso_year(nat):
    assert not nat.duplicated(["iso3", "year"]).any()
    assert nat.iso3.str.fullmatch(r"[A-Z]{3}").all()


def test_national_sums_equal_adm1_sums(nat, adm1):
    a = adm1.copy()
    a["iso3"] = np.where((a.ISO_A3 == "CHN") & (a.NAM_1 == "Taiwan Sheng"), "TWN", a.ISO_A3)
    s = a.groupby(["iso3", "year"]).agg(s=("ntl_sum", "sum"), w=("w_valid", "sum")).reset_index()
    m = nat.merge(s, on=["iso3", "year"])
    ok = m.ntl_sum.notna()
    assert ok.sum() > 3000
    assert np.allclose(m.ntl_sum[ok], m.s[ok], rtol=1e-9)
    # mean undefined (NA) when no valid weight is recoverable (dark territories, e.g. ASM)
    assert np.allclose(m.ntl_mean[ok], (m.s / m.w.where(m.w > 0))[ok], rtol=1e-9, equal_nan=True)
    # world total is preserved (TWN split moves light, never loses it)
    for y in (2012, 2022):
        assert math.isclose(nat[nat.year == y].ntl_sum.sum(), adm1[adm1.year == y].ntl_sum.sum(), rel_tol=1e-9)


def test_missing_national_value_only_when_a_unit_with_pixels_lacks_data(nat):
    na = nat[nat.ntl_sum.isna()]
    # either a unit with pixels lacks data, or no unit contains a pixel at all (Niue)
    assert ((na.n_adm1_missing > 0) | (na.n_adm1_without_pixels == na.n_adm1)).all()
    assert nat[nat.n_adm1_missing > 0].ntl_sum.isna().all()


def test_economy_names(nat):
    nm = nat.drop_duplicates("iso3").set_index("iso3").country
    assert nm["AUS"] == "Australia" and nm["ESP"] == "Spain" and nm["FRA"] == "France" and nm["GBR"] == "United Kingdom"
    assert nm["TWN"] == "Taiwan"


def test_taiwan_split_from_china(nat, adm1):
    t = nat[(nat.iso3 == "TWN") & (nat.year == 2020)].iloc[0]
    tw = adm1[(adm1.ISO_A3 == "CHN") & (adm1.NAM_1 == "Taiwan Sheng") & (adm1.year == 2020)].ntl_sum.iloc[0]
    assert math.isclose(t.ntl_sum, tw, rel_tol=1e-12)
    assert t.imf_group == "advanced" and pd.isna(t["pop"])
    assert nat[(nat.iso3 == "CHN") & (nat.year == 2020)].n_adm1.iloc[0] == 31


def test_imf_join():
    g = pd.read_csv(AN / "imf_weo_2023apr_groups.csv")
    assert (g.imf_group == "advanced").sum() == 41 and (g.imf_group == "emde").sum() == 155
    assert g.iso3.is_unique
    assert g[g.imf_group == "advanced"].euro_area.sum() == 20
    assert set(g[g.g7].iso3) == {"USA", "JPN", "DEU", "FRA", "ITA", "GBR", "CAN"}
    for iso in ("HRV", "KOR", "SGP", "PRI", "MAC"):
        assert g.set_index("iso3").loc[iso, "imf_group"] == "advanced"
    for iso in ("CHN", "IND", "BRA", "RUS", "SAU", "TUR"):
        assert g.set_index("iso3").loc[iso, "imf_group"] == "emde"


def test_imf_group_in_panel_matches_table(nat):
    g = pd.read_csv(AN / "imf_weo_2023apr_groups.csv").set_index("iso3").imf_group
    p = nat.drop_duplicates("iso3").set_index("iso3").imf_group
    both = p.index.intersection(g.index)
    assert (p[both] == g[both]).all()
    assert (p[~p.index.isin(g.index)] == "not_classified").all()
    assert set(g.index) - set(p.index) == {"TON", "WSM"}   # not in the lights source (documented)


def test_wdi_values_joined_by_iso_and_year(nat):
    raw = json.loads((ROOT / "raw" / "econ" / "wdi" / "SP.POP.TOTL.json").read_text(encoding="utf-8"))
    v = {(r["countryiso3code"], int(r["date"])): r["value"] for r in raw if r["value"] is not None}
    sub = nat.dropna(subset=["pop"])
    assert len(sub) > 2500
    for r in sub.sample(200, random_state=1).itertuples():
        assert r.pop == v[(r.iso3, r.year)]


def test_site_json_matches_download(nat):
    j = json.loads((AN / "national.json").read_text(encoding="utf-8"))
    years = j["years"]
    for iso in ("USA", "CHN", "IND", "AUS", "NGA", "TWN", "BRA"):
        e = j["economies"][iso]
        d = nat[nat.iso3 == iso].set_index("year")
        for k, col in (("sum", "ntl_sum"), ("mean", "ntl_mean"), ("pop", "pop"), ("gdppc", "gdp_pc_ppp")):
            for i, y in enumerate(years):
                a = d.loc[y, col] if y in d.index else None
                a = None if a is None or pd.isna(a) else float(a)
                assert close(a, e[k][i]), (iso, k, y, a, e[k][i])


def test_dose_json_matches_panel():
    j = json.loads((AN / "dose_regions.json").read_text(encoding="utf-8"))
    p = pd.read_parquet(DATA / "econ" / "dose" / "panel_dose_v2_14_ntl.parquet")
    for gid in ("CHN.1_1", "IND.10_1", "AUS.5_1"):
        r, d = j["regions"][gid], p[p.GID_1 == gid].set_index("year")
        for i, y in enumerate(j["years"]):
            for k, col in (("pop", "pop"), ("grppc", "grp_pc_usd_2015"), ("sum", "ntl_sum")):
                a = d.loc[y, col] if y in d.index else None
                a = None if a is None or pd.isna(a) else float(a)
                assert close(a, r[k][i]), (gid, k, y)


def test_adm1_json_covers_every_unit(adm1):
    j = json.loads((AN / "adm1_annual.json").read_text(encoding="utf-8"))
    assert set(j["units"]) == set(adm1.ADM1CD_c)
    u = j["units"]["DZA001"]
    d = adm1[adm1.ADM1CD_c == "DZA001"].set_index("year")
    for i, y in enumerate(j["years"]):
        assert close(float(d.loc[y, "ntl_sum"]), u["sum"][i])


def test_model_sample_sizes_reproduce(nat):
    m = json.loads((AN / "models.json").read_text(encoding="utf-8"))
    x = m["national"]["cross_sections"]["ntl_sum"]["2022"]
    d = nat[(nat.year == 2022) & (nat.iso3 != "TWN")]
    n = ((d.ntl_sum > 0) & (d["pop"] > 0) & (d.gdp_pc_ppp > 0)).sum()
    assert x["n"] == n
    assert 0 <= x["r2"] <= 1
    for c in x["coef"].values():
        assert c["ci95"][0] < c["b"] < c["ci95"][1]
    # within-country model nests the pooled one: weakly higher R²
    p = m["national"]["pooled"]
    assert p["both_country_fe"]["r2"] >= p["both"]["r2"]
    s = m["subnational_dose"]["sample"]
    assert s["n_obs"] == m["subnational_dose"]["pooled"]["both_pooled"]["n"]


def test_module_a_counts(nat):
    a = json.loads((AN / "module_a.json").read_text(encoding="utf-8"))["by_year"]["2022"]["ntl_mean"]
    d = nat[(nat.year == 2022) & (nat.ntl_mean > 0)]
    assert a["advanced"]["n"] == (d.imf_group == "advanced").sum()
    assert a["emde"]["n"] == (d.imf_group == "emde").sum()
    assert 0 <= a["separation"]["auc"] <= 1


def test_no_medians_published_above_adm2(nat):
    assert not [c for c in nat.columns if "median" in c or c.startswith("ntl_q")]


def test_aggregation_rules_report():
    r = json.loads((DATA / "validation_aggregation_rules.json").read_text(encoding="utf-8"))
    assert r["unweighted_vs_exact_mean_wb_adm1"]["unit_years"] > 10000
    assert r["monthly_no_data"]["all_districts_without_valid_data"] == 6180     # matches AUDIT A1
