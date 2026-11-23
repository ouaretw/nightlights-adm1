"""Render the static portal into build/site from templates + generated data.

Every number on the pages comes from files written by the pipeline
(build_meta.json, manifest.json, validation.json, crosswalk/DOSE summaries,
data_dictionary.json). Download tables are rendered from the manifest, so no
link can point to a file that does not exist.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
SITE = ROOT / "build" / "site"
DATA = SITE / "data" / "v2"

NAV = [("explore.html", "Explore", "explore"), ("analysis.html", "Economic Analysis", "analysis"),
       ("download.html", "Data & Downloads", "download"), ("methods.html", "Methods", "methods"), ("about.html", "About", "about")]
# pages that live under a navigation section (URLs kept stable)
NAV_ACTIVE = {"integration": "download", "docs": "download"}
LINK_MEANING = {
    "gadm_id": "same GID_1 in GADM 4.1, names agree",
    "gadm_id_suffix": "GADM 4.1 uses suffix _2 for the same unit",
    "gadm_manual": "researched renumbering (e.g. Santiago CHL.13_1 → CHL.14_1)",
    "gadm_id_name_missing": "same GID_1; GADM 4.1 has no name to check (England, Cork, Zuid-Holland)",
    "gadm_name": "unique near-exact name match within the country",
    "dose_geometry": "DOSE's own polygon; districts ≥50% inside",
    "linked_but_no_district": "linked, but the unit receives no source district (absorbed by a neighbour)",
    "unlinked": "no reliable link; left out rather than guessed",
}
CHANGELOG = [
    {"version": "2.1.0", "date": "2026-11-23", "text": "Economic Analysis workspace (IMF WEO April 2023 groups, WDI population and GDP, DOSE regions; exploratory models with "
     "clustered errors, Moran's I and holdout validation); national (ADM0) panel; aggregation-rule benchmark against unweighted collapses; "
     "ADM0 view on the home map; About page with licences and future indicators. Release files unchanged (v2.0.0 assets)."},
    {"version": "2.0.0", "date": "2026-11-21", "text": "Native ADM2 product; no-data sums set to missing instead of 0; flagged estimated pixel weights; "
     "official annual and monthly-derived annual kept separate; log/asinh transforms and year-on-year changes; GADM 4.1 match grades and absorbed-unit flags; "
     "DOSE V2.14 linkage and ready-to-merge panel; US BEA and Brazil IBGE crosswalks; Stata files; validation report incl. direct-extraction benchmark; new portal."},
    {"version": "1.1.0", "date": "2026-11-20", "text": "GADM 4.1 ADM1 version via an ADM2 crosswalk."},
    {"version": "1.0.0", "date": "2026-11-20", "text": "First release: World Bank ADM1 aggregation and explorer."},
]


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def download_groups(man, version):
    files = man["files"]
    def pick(pred):
        out = []
        for f in files:
            if not pred(f["path"]):
                continue
            name = f["path"].split("/")[-1]
            freq = next((k for k in ("annual_from_monthly", "monthly", "annual") if k in name), "")
            fmt = ("Stata (zip)" if name.endswith(".dta.zip") else "Stata" if name.endswith(".dta") else "Parquet" if name.endswith(".parquet")
                   else "CSV (gzip)" if name.endswith(".csv.gz") else "CSV bundle (zip)" if name.endswith(".zip") else "CSV" if name.endswith(".csv") else "JSON")
            href = f.get("url") or f["path"]
            out.append({"name": name, "freq": freq.replace("_", " "), "fmt": fmt, "size": human(f["bytes"]),
                        "host": "GitHub release" if f["host"] == "release" else "this site", "sha256": f["sha256"], "href": href})
        return sorted(out, key=lambda x: (x["freq"], x["fmt"]))
    glob_ = lambda sub: (lambda p: (p.startswith(f"data/v2/{sub}/{sub}_") or p.startswith(f"{sub}_")) and "/" not in p.replace(f"data/v2/{sub}/", ""))
    return [
        {"id": "adm1_gadm41", "title": "ADM1 · GADM 4.1", "tag": "for economic data", "tagclass": "approx",
         "note": "Keyed on GID_1. Districts assigned to GADM 4.1 units; graded per unit (xw_match_quality).",
         "files": pick(glob_("adm1_gadm41")), "per_country": "data/v2/adm1_gadm41/<frequency>/<ISO3>.parquet (and .csv for annual files); or export from the explorer."},
        {"id": "adm1_wb", "title": "ADM1 · World Bank units", "tag": "exact", "tagclass": "exact",
         "note": "Keyed on ADM1CD_c. Exact aggregation of the source districts.",
         "files": pick(glob_("adm1_wb")), "per_country": "data/v2/adm1_wb/<frequency>/<ISO3>.parquet (and .csv for annual files); or export from the explorer."},
        {"id": "adm2", "title": "ADM2 · native districts", "tag": "source", "tagclass": "native",
         "note": "Keyed on ADM2CD_c. Source observations (float32, as in the source) with corrected no-data handling, weights and GADM parent.",
         "files": pick(glob_("adm2")), "per_country": "data/v2/adm2/<frequency>/<ISO3>.parquet; CSV for any country from the explorer."},
        {"id": "econ", "title": "Economic integration", "tag": "", "tagclass": "",
         "note": "DOSE V2.14 panel and links; national crosswalks.",
         "files": pick(lambda p: p.startswith("data/v2/econ/") and not p.endswith(".json")), "per_country": ""},
        {"id": "analysis", "title": "National panel and economic analysis", "tag": "new in 2.1", "tagclass": "exact",
         "note": "Keyed on iso3 + year. National lights (exact sums of ADM1) with IMF WEO April 2023 groups and WDI population/GDP; "
                 "the files behind the Economic Analysis page.",
         "files": pick(lambda p: p.startswith("data/v2/adm0/") or (p.startswith("data/v2/analysis/") and not p.endswith("summary.json"))), "per_country": ""},
        {"id": "crosswalks", "title": "Crosswalks, QA and documentation", "tag": "", "tagclass": "",
         "note": "District → GADM crosswalk, match quality, coverage QA, map-outline audit, data dictionary, validation.",
         "files": pick(lambda p: p.startswith("data/v2/crosswalks/") or p in ("data/v2/data_dictionary.csv", "data/v2/data_dictionary.json",
                                                                               "data/v2/validation.json", "data/v2/validation_benchmark_units.csv",
                                                                               "data/v2/validation_aggregation_rules.json",
                                                                               "data/v2/build_meta.json")), "per_country": ""},
    ]


def country_index():
    a1 = pd.read_parquet(DATA / "adm1_wb" / "adm1_wb_annual_global.parquet", columns=["ISO_A3", "NAM_0", "ADM1CD_c"])
    g1 = pd.read_parquet(DATA / "adm1_gadm41" / "adm1_gadm41_annual_global.parquet", columns=["ISO_A3", "GID_1"])
    a2 = pd.read_parquet(DATA / "adm2" / "annual", columns=["ISO_A3", "ADM2CD_c"]) if (DATA / "adm2" / "annual").exists() else None
    idx = []
    for iso, d in a1.groupby("ISO_A3"):
        idx.append({"iso": iso, "name": d.NAM_0.iloc[0], "n_adm1_wb": int(d.ADM1CD_c.nunique()),
                    "n_adm1_gadm": int(g1[g1.ISO_A3 == iso].GID_1.nunique()),
                    "n_adm2": int(a2[a2.ISO_A3 == iso].ADM2CD_c.nunique()) if a2 is not None else None,
                    "map_adm1": (SITE / "data" / "geo" / "adm1" / f"{iso}.geojson").exists(),
                    "map_adm2": (SITE / "data" / "geo" / "adm2" / f"{iso}.geojson").exists()})
    idx.sort(key=lambda x: x["name"])
    (DATA / "index.json").write_text(json.dumps(idx, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    return idx


def main():
    meta = json.loads((DATA / "build_meta.json").read_text(encoding="utf-8"))
    man = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    val = json.loads((DATA / "validation.json").read_text(encoding="utf-8"))
    dose = json.loads((DATA / "econ" / "dose" / "dose_link_summary.json").read_text(encoding="utf-8"))
    agg = json.loads((DATA / "validation_aggregation_rules.json").read_text(encoding="utf-8"))
    an_sum = json.loads((DATA / "analysis" / "summary.json").read_text(encoding="utf-8"))
    national = json.loads((DATA / "econ" / "national" / "national_crosswalks_summary.json").read_text(encoding="utf-8"))
    qa = json.loads((DATA / "crosswalks" / "qa_summary.json").read_text(encoding="utf-8"))
    dic = json.loads((DATA / "data_dictionary.json").read_text(encoding="utf-8"))
    idx = country_index()
    meta["version"] = man["version"]
    stats = {"countries": len(idx), "adm2": sum(c["n_adm2"] or 0 for c in idx),
             "adm1_wb": sum(c["n_adm1_wb"] for c in idx), "adm1_gadm": qa["gadm_adm1_units_with_data"],
             "months": 168, "gadm_share": qa["world_light_assigned_share"]}
    citation = (f"Ouaret, W. (2026). Night Lights ADM1: NASA Black Marble nighttime lights for ADM1 and ADM2 units, "
                f"ready to merge with subnational economic data (v{man['version']}). https://ouaretw.github.io/nightlights-adm1/")
    bibtex = "\n".join([
        "@misc{ouaret2026nightlightsadm1,",
        "  author       = {Ouaret, Walid},",
        "  title        = {Night Lights {ADM1}: {NASA} Black Marble nighttime lights for {ADM1} and {ADM2} units, ready to merge with subnational economic data},",
        "  year         = {2026},",
        f"  version      = {{{man['version']}}},",
        r"  howpublished = {\url{https://ouaretw.github.io/nightlights-adm1/}},",
        "  note         = {Derived from World Bank Space2Stats dataset 0066940 (CC BY 4.0) and NASA Black Marble}",
        "}"])
    mf = {f["path"]: {"size": human(f["bytes"]), "href": f.get("url") or f["path"]} for f in man["files"]}
    afm = pd.read_parquet(DATA / "adm1_wb" / "adm1_wb_annual_from_monthly_global.parquet", columns=["year"]).year
    picker_meta = {"months": meta["coverage"]["months"], "years_official_annual": meta["coverage"]["years_official_annual"],
                   "years_afm": [int(afm.min()), int(afm.max())], "version": man["version"]}
    ex_dir = ROOT / "examples"
    examples = {"stata": (ex_dir / "merge_dose.do").read_text(encoding="utf-8"),
                "r": (ex_dir / "merge_dose.R").read_text(encoding="utf-8"),
                "python": (ex_dir / "merge_dose.py").read_text(encoding="utf-8")}
    dose_unlinked = sum(v for k, v in dose["dose_regions_by_link_method"].items() if k in ("unlinked", "linked_but_no_district"))

    env = Environment(loader=FileSystemLoader(SRC / "templates"), autoescape=select_autoescape(["html"]))
    dose_linked = dose["dose_regions"] - dose_unlinked
    common = {"nav": NAV, "meta": meta, "root": "", "citation": citation, "bibtex": bibtex,
              "release_version": man.get("release_version", man["version"]), "agg": agg, "mf": mf}
    an_files = [(p, l) for p, l in (("data/v2/adm0/ntl_adm0_annual_econ.csv", "national panel (CSV)"),
                                     ("data/v2/adm0/ntl_adm0_annual_econ.parquet", "Parquet"),
                                     ("data/v2/adm0/ntl_adm0_annual_econ_dictionary.csv", "columns"),
                                     ("data/v2/analysis/imf_weo_2023apr_groups.csv", "IMF groups"),
                                     ("data/v2/analysis/models.json", "model estimates (JSON)")) if p in mf]
    pages = {
        "analysis": ("Economic analysis", "Exploratory analyses of nighttime lights with IMF country groups, WDI population and GDP, and DOSE regional GDP.",
                     {"an_files": an_files, "an_sum": an_sum}),
        "about": ("About", "Purpose, contribution relative to existing World Bank tools, contributors, licences, project status and future indicators.", {}),
        "index": ("Nighttime lights for subnational economic research", "Explore and download NASA Black Marble nighttime-light statistics for states, provinces and districts worldwide, with documented crosswalks and data-quality indicators.",
                  {"stats": stats, "dose_linked": dose_linked, "dose_total": dose["dose_regions"]}),
        "explore": ("Explore data", "Interactive maps, time series, quality and exports by country, level and boundary system.", {}),
        "integration": ("Economic integration", "Crosswalks and ready-to-merge panels for DOSE, GADM-based data, US BEA and Brazil IBGE.",
                        {"dose": dose, "national": national, "dose_unlinked": dose_unlinked, "dose_linked": dose_linked, "link_meaning": LINK_MEANING,
                         "examples": examples}),
        "download": ("Download", "Choose a dataset by level, frequency, scope and format; every file with its size and SHA-256 checksum.",
                     {"groups": download_groups(man, man["version"]), "picker_meta": picker_meta, "n_files": len(man["files"])}),
        "methods": ("Methods and validation", "Aggregation method, tested source assumptions, validation results and limitations.",
                    {"val": val, "models_years": an_sum["years"]}),
        "docs": ("Documentation", "Data dictionary, file layout, licences and version history.",
                 {"columns": dic["columns"], "status": dic["status_legend"], "changelog": CHANGELOG}),
    }
    for key, (title, desc, ctx) in pages.items():
        html = env.get_template(f"{key}.html").render(page=key, nav_active=NAV_ACTIVE.get(key, key), title=title, description=desc, **common, **ctx)
        (SITE / f"{key}.html").write_text(html, encoding="utf-8")
    # assets, examples
    shutil.copytree(SRC / "assets", SITE / "assets", dirs_exist_ok=True)
    shutil.copytree(ex_dir, SITE / "examples", dirs_exist_ok=True)
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file()) / 1e6
    print(f"site rendered: {len(pages)} pages, {size:,.0f} MB total")


if __name__ == "__main__":
    main()
