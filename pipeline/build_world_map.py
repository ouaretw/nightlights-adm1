"""World ADM1 overview map for the landing page.

Inputs (already built):
  build/site/data/geo/adm1/{ISO}.geojson         World Bank ADM1 outlines (only units whose
                                                  code and name agree; see build_geo_match.py)
  build/site/data/v2/adm1_wb/adm1_wb_annual_global.parquet   official annual composites

Outputs:
  build/site/data/geo/world_adm1.geojson      all outlines merged and simplified for world scale
                                               (0.05 deg; islands < 0.01 deg2 dropped unless they are
                                               a unit's largest part). Display only.
  build/site/data/geo/world_adm1_values.json  per-unit annual mean radiance and sum of lights for
                                               the units that have an outline (display copy)

Values are copied from the published annual file, unchanged except for rounding to
4 significant digits for display; nothing is interpolated.
"""
import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import MultiPolygon

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "build" / "site"
GEO = SITE / "data" / "geo"
DATA = SITE / "data" / "v2"


def sig(v, n=4):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return None
    v = float(v)
    return 0 if v == 0 else float(f"{v:.{n}g}")


def trim(geom, amin=0.01, hole_min=0.05):
    """World-scale display: drop tiny islands (always keeping a unit's largest
    polygon) and holes < hole_min deg² (lakes, slivers). Units are drawn
    largest first, so a small enclave unit still shows on top of its host."""
    if geom is None or geom.geom_type not in ("Polygon", "MultiPolygon"):
        return geom
    ps = sorted([geom] if geom.geom_type == "Polygon" else geom.geoms, key=lambda x: -x.area)
    keep = [ps[0]] + [x for x in ps[1:] if x.area >= amin]
    keep = [shapely.Polygon(x.exterior, [r for r in x.interiors if shapely.Polygon(r).area >= hole_min]) for x in keep]
    return MultiPolygon(keep) if len(keep) > 1 else keep[0]


def polys_only(geom, grid=0.01):
    """Snap to a grid and keep only polygonal parts (display geometry). Units
    that would vanish at this grid (tiny islands, city states) are retried at a
    finer grid so that every unit stays on the map."""
    for gs in (grid, 0.001, 0):
        try:
            g = shapely.make_valid(geom)
            g = shapely.set_precision(g, gs) if gs else g
        except shapely.errors.GEOSException:
            continue
        if g.geom_type not in ("Polygon", "MultiPolygon"):
            parts = [x for x in getattr(g, "geoms", []) if x.geom_type in ("Polygon", "MultiPolygon")]
            g = shapely.union_all(parts) if parts else None
        if g is not None and not g.is_empty and g.geom_type in ("Polygon", "MultiPolygon"):
            return g
    return None


def main():
    parts = []
    for p in sorted((GEO / "adm1").glob("*.geojson")):
        g = gpd.read_file(p)
        if len(g):
            g["iso"] = p.stem
            parts.append(g[["code", "iso", "geometry"]])
    world = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:4326")
    world = world.assign(_a=world.geometry.area).sort_values("_a", ascending=False).drop(columns="_a")
    simple = world.geometry.apply(trim).simplify(0.05, preserve_topology=True)
    world["geometry"] = [polys_only(s) or polys_only(o, 0.001) for s, o in zip(simple, world.geometry)]
    lost = world[world.geometry.isna()].code.tolist()
    assert not lost, f"units lost in simplification: {lost}"
    out_geo = GEO / "world_adm1.geojson"
    feats = [{"type": "Feature", "properties": {"code": c, "iso": i},
              "geometry": json.loads(shapely.to_geojson(shapely.transform(g, lambda xy: np.round(xy, 3))))}
             for c, i, g in zip(world.code, world.iso, world.geometry)]
    out_geo.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")), encoding="utf-8")

    d = pd.read_parquet(DATA / "adm1_wb" / "adm1_wb_annual_global.parquet",
                        columns=["ISO_A3", "NAM_0", "ADM1CD_c", "NAM_1", "year", "ntl_mean", "ntl_sum", "coverage"])
    years = sorted(int(y) for y in d.year.unique())
    d = d[d.ADM1CD_c.isin(set(world.code))]
    units = {}
    for code, g in d.groupby("ADM1CD_c"):
        g = g.set_index("year").reindex(years)
        first = g.dropna(subset=["NAM_1"]).iloc[0]
        units[code] = {"iso": first.ISO_A3, "country": first.NAM_0, "name": first.NAM_1,
                       "mean": [sig(v) for v in g.ntl_mean], "sum": [sig(v) for v in g.ntl_sum],
                       "cov": [sig(v, 3) for v in g.coverage]}
    out = {"source": "adm1_wb_annual_global (official annual composites), World Bank ADM1 units",
           "years": years, "n_units_mapped": len(units),
           "n_units_total": int(pd.read_parquet(DATA / "adm1_wb" / "adm1_wb_annual_global.parquet",
                                                columns=["ADM1CD_c"]).ADM1CD_c.nunique()),
           "units": units}
    out_val = GEO / "world_adm1_values.json"
    out_val.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"{len(world)} outlines -> {out_geo.stat().st_size / 1e6:.2f} MB; "
          f"{len(units)} units x {len(years)} years -> {out_val.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
