"""Why are JPN / UKR ADM2 unassigned in the GADM crosswalk?"""
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
ROOT = Path(__file__).resolve().parents[2]
pd.set_option("display.width", 220)
xw = pd.read_csv(ROOT / "docs/data/gadm/crosswalk_adm2_to_gadm41.csv")
gm = pd.read_csv(ROOT / "docs/data/geo_match.csv")
for iso in ["JPN", "UKR", "KAZ", "HUN"]:
    x = xw[xw.ISO_A3 == iso]
    print(iso, x.method.value_counts().to_dict())
    print(x[x.method == "unassigned"].head(4)[["WB_ADM1CD_c", "WB_NAM_1", "ADM2CD_c", "NAM_2"]].to_string())
    print(gm[gm.ISO_A3 == iso].map_status.value_counts().to_dict())
wb1 = gpd.read_file(ROOT / "raw/geo/wb_gad_adm1_simplified.geojson")
gadm = gpd.read_parquet(ROOT / "raw/gadm/gadm41_adm1.parquet")
j = gm[(gm.ISO_A3 == "JPN") & gm.map_status.str.startswith("matched")].iloc[0]
print(j.to_dict())
geom = wb1[wb1.ADM1CD_c == j.ADM1CD_c_current_boundaries].to_crs(6933)
G = gadm[gadm.WB_ISO_A3 == "JPN"].to_crs(6933)
ov = gpd.overlay(geom[["ADM1CD_c", "geometry"]], G[["GID_1", "NAME_1", "geometry"]], how="intersection")
ov["share"] = ov.area / geom.area.iloc[0]
print(ov.sort_values("share", ascending=False)[["GID_1", "NAME_1", "share"]].head(3))
print("valid wb geom:", geom.is_valid.all(), "area km2", geom.area.iloc[0] / 1e6)
