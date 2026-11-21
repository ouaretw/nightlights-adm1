"""Detect revisions of the upstream sources without downloading them.

Compares HTTP metadata (Content-Length, Last-Modified, ETag) of the World Bank
Space2Stats files and the DOSE "latest" Zenodo record against
pipeline/source_lock.json. Exit code 0 = unchanged, 10 = changed (details
printed as Markdown for a GitHub issue). Never modifies data or releases:
a detected change must lead to a NEW versioned build.

  python pipeline/check_sources.py            # check
  python pipeline/check_sources.py --update   # rewrite the lock after a new release
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

LOCK = Path(__file__).resolve().parent / "source_lock.json"
SOURCES = {
    "wb_monthly_parquet": "https://datacatalogfiles.worldbank.org/ddh-published/0066940/DR0095701/ntl_adm2_monthly_all.parquet",
    "wb_annual_csv": "https://datacatalogfiles.worldbank.org/ddh-published/0066940/DR0095685/ntl_adm2_annual.csv",
    "wb_variable_doc": "https://datacatalogfiles.worldbank.org/ddh-published/0066940/DR0095677/Data_Description_and_Variables.pdf",
}
DOSE_LATEST = "https://zenodo.org/api/records/16313760/versions/latest"


def head(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "nightlights-adm1-source-check"})
    with urllib.request.urlopen(req, timeout=60) as r:
        h = r.headers
        return {"content_length": h.get("Content-Length"), "last_modified": h.get("Last-Modified"), "etag": h.get("ETag")}


def dose_latest():
    req = urllib.request.Request(DOSE_LATEST, headers={"User-Agent": "nightlights-adm1-source-check", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.load(r)
    return {"record_id": str(d.get("id")), "version": d.get("metadata", {}).get("version"),
            "publication_date": d.get("metadata", {}).get("publication_date")}


def current():
    out = {k: head(u) for k, u in SOURCES.items()}
    out["dose_latest"] = dose_latest()
    return out


def main():
    now = current()
    if "--update" in sys.argv or not LOCK.exists():
        LOCK.write_text(json.dumps(now, indent=2), encoding="utf-8")
        print("lock written")
        return 0
    old = json.loads(LOCK.read_text(encoding="utf-8"))
    changes = []
    for k, v in now.items():
        for f, val in v.items():
            if old.get(k, {}).get(f) != val:
                changes.append(f"| `{k}` | {f} | `{old.get(k, {}).get(f)}` | `{val}` |")
    if not changes:
        print("sources unchanged")
        return 0
    print("## Upstream source changed\n\nA new versioned build is needed (do not overwrite the existing release).\n")
    print("| source | field | locked | now |\n|---|---|---|---|")
    print("\n".join(changes))
    return 10


if __name__ == "__main__":
    sys.exit(main())
