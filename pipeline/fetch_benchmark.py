"""Download the World Bank blackmarble-stata prototype extractions: NASA Black
Marble annual composites extracted DIRECTLY from the raster to GADM 4.1 ADM1
polygons (exactextractr). Used only as an independent benchmark for our
ADM2 -> GADM ADM1 aggregation (validation report); not redistributed.

Source: https://github.com/worldbank/blackmarble-stata (public S3 bucket).
Output: raw/benchmark/bm_stata_<ISO>_<year>.dta
"""
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "raw" / "benchmark"
BASE = "https://wb-blackmarble.s3.us-east-2.amazonaws.com/gadm_410/ADM_1/{iso}/blackmarble/annual/{year}.dta"
ISOS = ["AFG", "AGO", "AIA", "ALA", "ALB", "AND", "ARE", "ARG", "ARM", "ASM", "ATF", "ATG", "AUS",
        "AUT", "AZE", "BDI", "BEL", "BEN", "BFA", "BGD", "BGR", "BHR", "DZA", "MAR", "USA", "IND"]
YEARS = [2012, 2013, 2019, 2020, 2021, 2022, 2023, 2024]

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    got = []
    for iso in ISOS:
        for y in YEARS:
            r = requests.get(BASE.format(iso=iso, year=y), timeout=60)
            if r.status_code == 200:
                (OUT / f"bm_stata_{iso}_{y}.dta").write_bytes(r.content)
                got.append(f"{iso}-{y}")
    print(len(got), "files:", got)
