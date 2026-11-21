"""Attach map geometry to ADM1 units only where it is safe.

The NTL table was built on an older WB-GAD vintage than the geometry served by
the public FeatureServer, and ADM1 codes were re-used across vintages
(e.g. ALB005 = Diber in the NTL table, Fier in the current boundaries).
A polygon is therefore attached only when the code matches AND the names agree
(after normalisation / fuzzy comparison). Everything else is data-only.

Reads : raw/geo/wb_gad_adm1_simplified.geojson, raw/ntl_adm2_monthly_all.parquet
Writes: build/site/data/geo/adm1/<ISO3>.geojson (matched polygons only),
        build/crosswalks/geo_match_wb_adm1.csv (audit of every ADM1 unit)
"""
from __future__ import annotations

import json
import re
import shutil
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GEO_RAW = ROOT / "raw" / "geo" / "wb_gad_adm1_simplified.geojson"
OUT = ROOT / "build" / "site" / "data"
XW = ROOT / "build" / "crosswalks"

STOP = r"\b(saint|st|ste|sainte|province|provincia|prov|region|regione|regiao|district|oblast|oblys|governorate|" \
       r"county|state|estado|department|departamento|municipality|parish|city|economic|kraj|voivodeship|" \
       r"prefecture|ken|to|fu|do|shi|sheng|zizhiqu|autonomous|of|the|and|de|du|la|le|d|dc|df|federal)\b"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(STOP, " ", s)
    return re.sub(r"\s+", "", s)


def same_name(a: str, b: str) -> bool:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb or (len(min(na, nb, key=len)) >= 4 and (na in nb or nb in na)):
        return True
    return SequenceMatcher(None, na, nb).ratio() >= 0.85


def main():
    geo = json.loads(GEO_RAW.read_text(encoding="utf-8"))["features"]
    gdf = {f["properties"]["ADM1CD_c"]: f for f in geo if f.get("geometry")}
    geo_by_iso: dict[str, list] = {}
    for f in geo:
        geo_by_iso.setdefault(f["properties"]["ISO_A3"], []).append(f)

    ntl = pd.read_parquet(ROOT / "raw" / "ntl_adm2_monthly_all.parquet", columns=["ISO_A3", "ADM1CD_c", "NAM_1"]) \
            .drop_duplicates("ADM1CD_c")
    n_per_iso = ntl.groupby("ISO_A3").size()
    rows, keep = [], {}
    for iso, sub in ntl.groupby("ISO_A3"):
        gfs = geo_by_iso.get(iso, [])
        same_count = len(gfs) == len(sub)
        near_count = abs(len(gfs) - len(sub)) <= 3 and len(sub) >= 10
        used, assign = set(), {}
        if same_count or near_count:
            # pass 1: same code and same name. If the unit count differs slightly
            # (a few splits/merges), the outline is flagged approximate.
            tag = "matched_code_name" if same_count else "matched_code_name_approx"
            for r in sub.itertuples():
                f = gdf.get(r.ADM1CD_c)
                if f is not None and (same_name(r.NAM_1, f["properties"]["NAM_1"]) or (same_count and len(sub) == 1)):
                    assign[r.ADM1CD_c] = (f, tag)
                    used.add(r.ADM1CD_c)
        if same_count:
            # pass 2: renumbered units - unique name match within the country
            for r in sub.itertuples():
                if r.ADM1CD_c in assign:
                    continue
                cands = [f for f in gfs if f["properties"]["ADM1CD_c"] not in used
                         and same_name(r.NAM_1, f["properties"]["NAM_1"])]
                if len(cands) == 1:
                    assign[r.ADM1CD_c] = (cands[0], "matched_name_renumbered")
                    used.add(cands[0]["properties"]["ADM1CD_c"])
        for r in sub.itertuples():
            f, status = assign.get(r.ADM1CD_c, (None, None))
            if status is None:
                status = "unmapped_unit_count_differs" if not (same_count or near_count) else "unmapped_no_confident_match"
            rows.append({"ISO_A3": iso, "ADM1CD_c": r.ADM1CD_c, "NAM_1_ntl": r.NAM_1,
                         "n_adm1_ntl_vintage": len(sub), "n_adm1_current_boundaries": len(gfs),
                         "NAM_1_current_boundaries": f["properties"]["NAM_1"] if f else None,
                         "ADM1CD_c_current_boundaries": f["properties"]["ADM1CD_c"] if f else None,
                         "map_status": status})
            if f is not None:
                keep.setdefault(iso, []).append({"type": "Feature", "geometry": f["geometry"],
                                                 "properties": {"code": r.ADM1CD_c, "name": r.NAM_1,
                                                                "approx": status.endswith("approx")}})
    audit = pd.DataFrame(rows)
    XW.mkdir(parents=True, exist_ok=True)
    audit.to_csv(XW / "geo_match_wb_adm1.csv", index=False, encoding="utf-8")

    gdir = OUT / "geo" / "adm1"
    shutil.rmtree(gdir, ignore_errors=True)
    gdir.mkdir(parents=True)
    for iso, fs in keep.items():
        (gdir / f"{iso}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": fs},
                                                        separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    s = audit.map_status.value_counts().to_dict()
    per = audit.assign(m=audit.map_status.str.startswith("matched")).groupby("ISO_A3").m.mean()
    summary = {"status_counts": s, "countries_fully_mapped": int((per == 1).sum()),
               "countries_partly_mapped": int(((per > 0) & (per < 1)).sum()),
               "countries_unmapped": int((per == 0).sum())}
    (XW / "geo_match_wb_adm1_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("least-mapped:", per.sort_values().head(25).round(2).to_dict())


if __name__ == "__main__":
    main()
