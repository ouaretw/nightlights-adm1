"""Download GADM 4.1 ADM1 polygons per country (level 0 where a country has
no level 1). GADM licence forbids redistribution, so these stay in raw/ and
only GID codes + names are published.

Output: raw/gadm/gadm41_<ISO>_<lvl>.json, raw/gadm/gadm41_adm1.parquet
"""
import io
import json
import time
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw" / "gadm"
URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_{iso}_{lvl}.json.zip"
# WB ISO_A3 -> GADM GID_0 where they differ
ISO_MAP = {"XKX": "XKO", "ROU": "ROU", "TLS": "TLS", "SSD": "SSD", "PSE": "PSE"}


def get(iso: str, lvl: int):
    p = RAW / f"gadm41_{iso}_{lvl}.json"
    if p.exists():
        return p
    for attempt in range(4):
        r = requests.get(URL.format(iso=iso, lvl=lvl), timeout=180)
        if r.status_code == 404:
            return None
        if r.ok:
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                p.write_bytes(z.read(z.namelist()[0]))
            return p
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"{iso} L{lvl}: HTTP {r.status_code}")


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    isos = list(pd.read_parquet(ROOT / "raw" / "ntl_adm2_monthly_all.parquet", columns=["ISO_A3"]).ISO_A3.unique())
    isos += ["TWN"]  # in WB-GAD Taiwan sits under CHN; GADM has it as its own country
    parts, missing = [], []
    for iso in sorted(isos):
        g_iso = ISO_MAP.get(iso, iso)
        p, lvl = get(g_iso, 1), 1
        if p is None:
            p, lvl = get(g_iso, 0), 0
        if p is None:
            missing.append(iso)
            continue
        g = gpd.read_file(p)
        if lvl == 0:
            g = g.rename(columns={"GID_0": "GID_0", "COUNTRY": "COUNTRY"})
            g["GID_1"], g["NAME_1"], g["ENGTYPE_1"] = g["GID_0"], g["COUNTRY"], "Country (no GADM level 1)"
            g["VARNAME_1"] = None
        if "VARNAME_1" not in g:
            g["VARNAME_1"] = None
        g["WB_ISO_A3"] = iso
        g["gadm_level"] = lvl
        parts.append(g[["WB_ISO_A3", "GID_0", "COUNTRY", "GID_1", "NAME_1", "VARNAME_1", "ENGTYPE_1", "gadm_level", "geometry"]])
    out = pd.concat(parts, ignore_index=True)
    out = gpd.GeoDataFrame(out, crs=4326)
    out.to_parquet(RAW / "gadm41_adm1.parquet")
    print("GADM units:", len(out), "countries:", out.WB_ISO_A3.nunique(), "missing:", missing)


if __name__ == "__main__":
    main()
