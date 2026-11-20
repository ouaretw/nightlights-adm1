"""Audit the GADM crosswalk: name-based assignments listed for eyeballing,
and an ADM1-consistency check for the ADM2 name pass."""
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
pd.set_option("display.width", 220)
pd.set_option("display.max_rows", 500)
xw = pd.read_csv(ROOT / "docs/data/gadm/crosswalk_adm2_to_gadm41.csv")
print(xw.method.value_counts().to_dict())
a = xw[xw.method == "adm1_name"].drop_duplicates("WB_ADM1CD_c")
print("adm1_name assignments:", len(a))
print(a[["ISO_A3", "WB_NAM_1", "NAME_1"]].to_string())

# ADM2 'name' pass: does the matched current ADM2 sit in a same-named ADM1?
wb2 = gpd.read_parquet(ROOT / "raw/geo/wb_gad_adm2.parquet")
import sys
sys.path.insert(0, str(ROOT / "pipeline"))
from build_geo_match import same_name  # noqa: E402
n = xw[xw.method == "name"]
print("ADM2 name-pass rows:", len(n))
# Majority GID_1 per source ADM1 vs each name-matched ADM2's GID_1
maj = xw[xw.GID_1.notna()].groupby("WB_ADM1CD_c").GID_1.agg(lambda s: s.value_counts().index[0])
n = n.assign(maj=n.WB_ADM1CD_c.map(maj))
odd = n[n.GID_1 != n.maj]
print("name-pass ADM2 landing outside their ADM1's majority GADM unit:", len(odd))
print(odd[["ISO_A3", "WB_NAM_1", "NAM_2", "NAME_1", "overlap_share"]].head(40).to_string())

# biggest remaining unassigned light
a2 = pd.read_csv(ROOT / "raw/ntl_adm2_annual.csv", usecols=["ADM2CD_c", "year", "ntl_sum"])
l = a2[a2.year == 2024].set_index("ADM2CD_c").ntl_sum
un = xw[xw.method == "unassigned"].assign(light=lambda d: d.ADM2CD_c.map(l))
print("unassigned share of world light 2024:", round(un.light.sum() / l.sum(), 4))
print(un.groupby(["ISO_A3", "WB_NAM_1"]).light.sum().sort_values(ascending=False).head(25))
print(xw[xw.method.isin(["adm1_as_current_adm2", "cross_border"])].groupby(["method", "ISO_A3"]).size().head(30))
