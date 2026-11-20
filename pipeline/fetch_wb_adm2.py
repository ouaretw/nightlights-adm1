"""Download current WB-GAD ADM2 polygons (lightly simplified) from the public
FeatureServer. Used only internally to locate source ADM2 units; not served.

Output: raw/geo/wb_gad_adm2.parquet (GeoParquet)
"""
from pathlib import Path

import geopandas as gpd

from fetch_boundaries import fetch_layer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "raw" / "geo" / "wb_gad_adm2.parquet"

if __name__ == "__main__":
    feats = fetch_layer(3, "ISO_A3,ADM1CD_c,NAM_1,ADM2CD_c,NAM_2", offset_deg=0.002, precision=4, page=1000)
    g = gpd.GeoDataFrame.from_features([f for f in feats if f.get("geometry")], crs=4326)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    g.to_parquet(OUT)
    print("ADM2 features:", len(g), "->", OUT)
