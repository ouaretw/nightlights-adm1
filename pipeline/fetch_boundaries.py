"""Download simplified World Bank Official Boundaries (WB-GAD) ADM0/ADM1 from
the public ArcGIS FeatureServer referenced in github.com/worldbank/WB_GAD,
and write web-ready GeoJSON for the site map.

Outputs (docs/data/geo/):
    adm0_world.geojson       coarse country outlines (overview map)
    adm1/<ISO3>.geojson      ADM1 polygons per country (loaded on demand)
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

import requests

BASE = ("https://services.arcgis.com/iQ1dY19aHwbSDYIF/ArcGIS/rest/services/"
        "World_Bank_Global_Administrative_Divisions/FeatureServer")
ROOT = Path(__file__).resolve().parents[1]
RAWGEO = ROOT / "raw" / "geo"
OUT = ROOT / "build" / "site" / "data" / "geo"


def fetch_layer(layer: int, fields: str, offset_deg: float, precision: int, page: int = 200) -> list[dict]:
    feats, start = [], 0
    while True:
        params = {"where": "1=1", "outFields": fields, "outSR": 4326, "f": "geojson",
                  "maxAllowableOffset": offset_deg, "geometryPrecision": precision,
                  "resultOffset": start, "resultRecordCount": page, "orderByFields": "FID"}
        for attempt in range(5):
            try:
                r = requests.get(f"{BASE}/{layer}/query", params=params, timeout=180)
                r.raise_for_status()
                js = r.json()
                if "features" not in js:
                    raise RuntimeError(str(js)[:300])
                break
            except Exception as e:  # noqa: BLE001
                print("  retry", attempt, e, flush=True)
                time.sleep(5 * (attempt + 1))
        else:
            raise SystemExit(f"layer {layer} failed at offset {start}")
        feats += js["features"]
        print(f"  layer {layer}: {len(feats)} features", flush=True)
        if len(js["features"]) < page:
            return feats
        start += page


def main():
    RAWGEO.mkdir(parents=True, exist_ok=True)
    (OUT / "adm1").mkdir(parents=True, exist_ok=True)

    adm1 = fetch_layer(2, "ISO_A3,NAM_0,NAM_1,ADM1CD_c", offset_deg=0.01, precision=3)
    (RAWGEO / "wb_gad_adm1_simplified.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": adm1}), encoding="utf-8")
    by_iso = defaultdict(list)
    for f in adm1:
        p = f["properties"]
        if f.get("geometry") is None:
            continue
        by_iso[p["ISO_A3"]].append({"type": "Feature", "geometry": f["geometry"],
                                    "properties": {"code": p["ADM1CD_c"], "name": p["NAM_1"]}})
    for iso, fs in by_iso.items():
        (OUT / "adm1" / f"{iso}.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": fs}, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8")

    adm0 = fetch_layer(1, "ISO_A3,NAM_0,WB_STATUS", offset_deg=0.05, precision=2)
    fs0 = [{"type": "Feature", "geometry": f["geometry"],
            "properties": {"iso": f["properties"]["ISO_A3"], "name": f["properties"]["NAM_0"]}}
           for f in adm0 if f.get("geometry")]
    (OUT / "adm0_world.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": fs0}, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8")

    # NDLSA (areas of non-determined legal status) - drawn as hatched/neutral on the map
    nd = fetch_layer(5, "*", offset_deg=0.05, precision=2)
    fsn = [{"type": "Feature", "geometry": f["geometry"], "properties": {}} for f in nd if f.get("geometry")]
    (OUT / "ndlsa.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": fsn}, separators=(",", ":")), encoding="utf-8")
    print("countries with ADM1 geometry:", len(by_iso), "adm1 features:", len(adm1), "adm0:", len(fs0), "ndlsa:", len(fsn))


if __name__ == "__main__":
    main()
