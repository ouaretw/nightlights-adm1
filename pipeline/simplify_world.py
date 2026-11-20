"""Shrink the ADM0 world outline + NDLSA layer for the overview map."""
from pathlib import Path

import geopandas as gpd

GEO = Path(__file__).resolve().parents[1] / "docs" / "data" / "geo"
for name, tol in [("adm0_world", 0.15), ("ndlsa", 0.05)]:
    p = GEO / f"{name}.geojson"
    g = gpd.read_file(p)
    g["geometry"] = g.geometry.simplify(tol, preserve_topology=True)
    g = g[~g.geometry.is_empty]
    g.to_file(p, driver="GeoJSON", COORDINATE_PRECISION=2)
    print(name, len(g), round(p.stat().st_size / 1e6, 2), "MB")
