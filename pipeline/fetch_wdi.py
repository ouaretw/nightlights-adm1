"""Download national indicators from the World Bank World Development Indicators API.

Writes raw/econ/wdi/<indicator>.json (API response pages, untouched) and
raw/econ/wdi/countries.json (economy metadata: ISO3, name, region, income
level, aggregate flag), plus fetch_log.json with URLs, dates and SHA-256.

Indicators (WDI codes):
  SP.POP.TOTL        Population, total
  NY.GDP.PCAP.PP.KD  GDP per capita, PPP (constant 2021 international $)
  NY.GDP.MKTP.PP.KD  GDP, PPP (constant 2021 international $)
  NY.GDP.PCAP.KD     GDP per capita (constant 2015 US$)
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "raw" / "econ" / "wdi"
API = "https://api.worldbank.org/v2"
INDICATORS = ["SP.POP.TOTL", "NY.GDP.PCAP.PP.KD", "NY.GDP.MKTP.PP.KD", "NY.GDP.PCAP.KD"]
YEARS = "2012:2024"


def get(url: str):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - retry transient API errors
            if attempt == 3:
                raise
            time.sleep(2 + 3 * attempt)


def fetch_all(path: str) -> list:
    rows, page = [], 1
    while True:
        url = f"{API}/{path}{'&' if '?' in path else '?'}format=json&per_page=20000&page={page}"
        meta, data = get(url)
        rows += data or []
        if page >= meta["pages"]:
            return rows
        page += 1


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log = {"retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": {}}
    jobs = {"countries.json": "country"}
    jobs.update({f"{i}.json": f"country/all/indicator/{i}?date={YEARS}" for i in INDICATORS})
    for fname, path in jobs.items():
        rows = fetch_all(path)
        p = OUT / fname
        p.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        log["files"][fname] = {"url": f"{API}/{path}", "n_records": len(rows),
                               "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        print(fname, len(rows))
    (OUT / "fetch_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
