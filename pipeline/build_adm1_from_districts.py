"""Map outlines for World Bank ADM1 units built from their own districts.

build_geo_match.py attaches today's WB-GAD ADM1 polygon to a source ADM1 unit only
when code and name agree; in countries whose ADM1 layer was renumbered or
reorganised since the source vintage (e.g. Brazil, Kazakhstan, Viet Nam) nothing
is drawn. Here the outline of such a unit is instead the union of the current
WB-GAD ADM2 polygons that its own source districts were located on by
build_gadm.py (geom_ref 'ADM2:<code>'; methods code_name, name, adm1_as_current_adm2).
That outline is, by construction, the area the unit's data were summed over.

Rules (no guessing):
  * a unit keeps its existing outline if it is 'matched_code_name' or
    'matched_name_renumbered';
  * an ADM2 polygon referenced by districts of more than one ADM1 unit is
    ambiguous and never used;
  * 'built_from_districts'          every district of the unit has an unambiguous polygon;
  * 'built_from_districts_partial'  >= 90% of the unit's 2020 light and >= 75% of its
    districts have one (flagged approx; replaces nothing better);
  * otherwise the previous status (approximate outline or unmapped) is kept.

Reads : raw/geo/wb_gad_adm2.parquet, raw/ntl_adm2_annual.csv,
        build/crosswalks/crosswalk_adm2_to_gadm41.csv, build/crosswalks/geo_match_wb_adm1.csv,
        build/site/data/geo/adm1/<ISO3>.geojson
Writes: the same adm1 GeoJSONs and geo_match_wb_adm1.csv (+ _summary.json), updated.
"""
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import numpy as np
import shapely
import shapely.geometry

ROOT = Path(__file__).resolve().parents[1]
XW = ROOT / "build" / "crosswalks"
GDIR = ROOT / "build" / "site" / "data" / "geo" / "adm1"
KEEP = {"matched_code_name", "matched_name_renumbered"}


def fill_slivers(geom, max_hole=0.005):
    """Remove interior rings smaller than max_hole deg² (~60 km²): these are gaps
    between adjacent district polygons in the source layer, not real enclaves."""
    polys = [geom] if geom.geom_type == "Polygon" else list(getattr(geom, "geoms", []))
    out = [shapely.Polygon(p.exterior, [r for r in p.interiors if shapely.Polygon(r).area >= max_hole])
           for p in polys if p.geom_type == "Polygon"]
    return shapely.union_all(out) if out else geom


def clean(geom):
    """Fill sliver gaps, simplify, round to 0.001 deg and return a valid (Multi)Polygon."""
    g = shapely.make_valid(fill_slivers(geom).simplify(0.005, preserve_topology=True))
    g = shapely.make_valid(shapely.transform(g, lambda c: np.round(c, 3)))
    if g.geom_type == "GeometryCollection":
        g = shapely.union_all([x for x in g.geoms if x.geom_type in ("Polygon", "MultiPolygon")])
    return g


def main():
    xw = pd.read_csv(XW / "crosswalk_adm2_to_gadm41.csv", dtype=str, keep_default_na=False)
    audit = pd.read_csv(XW / "geo_match_wb_adm1.csv", dtype=str, keep_default_na=False)
    light = (pd.read_csv(ROOT / "raw" / "ntl_adm2_annual.csv", usecols=["ADM2CD_c", "year", "ntl_sum"])
             .query("year == 2020").set_index("ADM2CD_c").ntl_sum.clip(lower=0).fillna(0))

    xw["poly"] = xw.geom_ref.where(xw.geom_ref.str.startswith("ADM2:"), "").str[5:]
    owners = xw[xw.poly != ""].groupby("poly").WB_ADM1CD_c.nunique()
    ambiguous = set(owners[owners > 1].index)
    xw.loc[xw.poly.isin(ambiguous), "poly"] = ""
    xw["light"] = xw.ADM2CD_c.map(light).fillna(0)
    xw["has"] = xw.poly != ""

    per = xw.groupby("WB_ADM1CD_c").agg(n=("has", "size"), n_has=("has", "sum"),
                                         l_all=("light", "sum"),
                                         l_has=("light", lambda s: s[xw.loc[s.index, "has"]].sum()))
    per["light_share"] = (per.l_has / per.l_all).where(per.l_all > 0, per.n_has / per.n)
    per["status"] = None
    per.loc[per.n_has == per.n, "status"] = "built_from_districts"
    part = (per.n_has < per.n) & (per.light_share >= 0.9) & (per.n_has / per.n >= 0.75)
    per.loc[part, "status"] = "built_from_districts_partial"

    audit = audit.set_index("ADM1CD_c")
    todo = [c for c in per.index[per.status.notna()] if audit.at[c, "map_status"] not in KEEP]
    # a partial district outline never replaces an existing (approximate) outline
    todo = [c for c in todo if not (per.at[c, "status"] == "built_from_districts_partial"
                                    and audit.at[c, "map_status"].startswith("matched"))]

    wb2 = gpd.read_parquet(ROOT / "raw" / "geo" / "wb_gad_adm2.parquet").set_index("ADM2CD_c")
    need = xw[xw.WB_ADM1CD_c.isin(todo) & xw.has]
    geoms = {}
    for code, g in need.groupby("WB_ADM1CD_c"):
        polys = [shapely.make_valid(wb2.at[p, "geometry"]) for p in g.poly.unique() if p in wb2.index]
        if polys:
            geoms[code] = clean(shapely.union_all(polys))

    by_iso = {}
    for code, geom in geoms.items():
        by_iso.setdefault(audit.at[code, "ISO_A3"], []).append((code, per.at[code, "status"], geom))

    name = audit.NAM_1_ntl.to_dict()
    skipped_overlap = []
    for iso, items in by_iso.items():
        p = GDIR / f"{iso}.geojson"
        fc = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"type": "FeatureCollection", "features": []}
        replaced = {c for c, _, _ in items}
        fc["features"] = [f for f in fc["features"] if f["properties"]["code"] not in replaced]
        # outlines kept from build_geo_match: a district-built outline must not sit on top of one
        kept = shapely.union_all([shapely.make_valid(shapely.geometry.shape(f["geometry"])) for f in fc["features"]]) \
            if fc["features"] else None
        for code, status, geom in items:
            if kept is not None and geom.area > 0 and geom.intersection(kept).area / geom.area > 0.05:
                skipped_overlap.append(code)
                audit.at[code, "map_status"] = "unmapped_overlaps_existing_outline"
                continue
            gj = json.loads(shapely.to_geojson(geom))
            fc["features"].append({"type": "Feature", "geometry": gj, "properties": {
                "code": code, "name": name[code], "approx": status.endswith("partial"), "outline": status}})
            audit.at[code, "map_status"] = status
            audit.at[code, "NAM_1_current_boundaries"] = ""
            audit.at[code, "ADM1CD_c_current_boundaries"] = ""
        if fc["features"]:
            p.write_text(json.dumps(fc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print("district outlines skipped (overlap an existing outline):", skipped_overlap)

    audit = audit.reset_index()[["ISO_A3", "ADM1CD_c", *[c for c in audit.columns if c != "ISO_A3"]]]
    audit.to_csv(XW / "geo_match_wb_adm1.csv", index=False, encoding="utf-8")
    s = audit.map_status.value_counts().to_dict()
    mapped = audit.assign(m=~audit.map_status.str.startswith("unmapped")).groupby("ISO_A3").m.mean()
    summary = {"status_counts": s, "units_with_outline": int((~audit.map_status.str.startswith("unmapped")).sum()),
               "units_total": len(audit), "countries_fully_mapped": int((mapped == 1).sum()),
               "countries_partly_mapped": int(((mapped > 0) & (mapped < 1)).sum()),
               "countries_unmapped": int((mapped == 0).sum()),
               "ambiguous_adm2_polygons_not_used": len(ambiguous)}
    (XW / "geo_match_wb_adm1_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
