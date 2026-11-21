"""Per-country ADM2 outlines for the web map (World Bank Official Boundaries,
CC BY 4.0). A district is drawn only when its source code AND name match
today's WB-GAD ADM2 layer (crosswalk method 'code_name'). Nothing else is
drawn; other districts appear in tables, charts and downloads only.

Reads : raw/geo/wb_gad_adm2.parquet, build/crosswalks/crosswalk_adm2_to_gadm41.csv
Writes: build/site/data/geo/adm2/<ISO3>.geojson, build/crosswalks/geo_match_wb_adm2_summary.json
"""
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "site" / "data" / "geo" / "adm2"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    xw = pd.read_csv(ROOT / "build" / "crosswalks" / "crosswalk_adm2_to_gadm41.csv", dtype=str)
    keep = xw[xw.method == "code_name"][["ISO_A3", "ADM2CD_c", "NAM_2", "method"]]
    wb2 = gpd.read_parquet(ROOT / "raw" / "geo" / "wb_gad_adm2.parquet")
    by_code = wb2.set_index("ADM2CD_c")
    rows = []
    for r in keep.itertuples():
        if r.method == "code_name" and r.ADM2CD_c in by_code.index:
            geom = by_code.loc[r.ADM2CD_c].geometry
            rows.append((r.ISO_A3, r.ADM2CD_c, r.NAM_2, False, geom))
    g = gpd.GeoDataFrame(rows, columns=["iso", "code", "name", "approx", "geometry"], crs=4326)
    g["geometry"] = g.geometry.simplify(0.004, preserve_topology=True)
    g = g[~g.geometry.is_empty]
    sizes = {}
    for iso, d in g.groupby("iso"):
        p = OUT / f"{iso}.geojson"
        d[["code", "name", "approx", "geometry"]].to_file(p, driver="GeoJSON", COORDINATE_PRECISION=3)
        sizes[iso] = p.stat().st_size
    summary = {"adm2_drawn": int(len(g)), "adm2_total": int(len(xw)),
               "countries": len(sizes), "total_mb": round(sum(sizes.values()) / 1e6, 1),
               "largest": sorted(sizes.items(), key=lambda kv: -kv[1])[:5]}
    (ROOT / "build" / "crosswalks" / "geo_match_wb_adm2_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
