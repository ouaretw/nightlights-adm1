# Night Lights ADM1

NASA Black Marble nighttime lights for **ADM1 and ADM2** units, ready to merge with subnational economic data.

**Portal:** https://ouaretw.github.io/nightlights-adm1/ · **Releases:** https://github.com/ouaretw/nightlights-adm1/releases

The World Bank publishes Black Marble statistics for districts (ADM2) in
[Space2Stats dataset 0066940](https://datacatalog.worldbank.org/search/dataset/0066940). Most subnational economic data
are reported for ADM1. This repository builds three clearly labelled products from that source:

| Product | Key | Nature |
|---|---|---|
| `adm2` | `ADM2CD_c` | Native source observations. "No valid pixel" sums are set to missing instead of 0. Adds weights and the GADM parent. |
| `adm1_wb` | `ADM1CD_c` | **Exact** aggregation to the source's World Bank provinces (strict nesting). |
| `adm1_gadm41` | `GID_1` | Aggregation to GADM 4.1 provinces through a district crosswalk, **graded per unit**. |
| `adm0/ntl_adm0_annual_econ` | `iso3` + `year` | National sums and means (exact sums of ADM1), joined to IMF WEO April 2023 groups and WDI population/GDP (new in 2.1). |

Each product comes in `monthly` (2012-01 to 2025-12) and `annual` (NASA's official annual composite, 2012–2024). The ADM1
products also have `annual_from_monthly`, which is derived from monthly data and kept separate. Economic linkage covers
DOSE V2.14 (a ready-to-merge panel), plus US BEA and Brazil IBGE crosswalks.

The portal has five sections:

- **Explore:** world map at country and province level, plus a country explorer.
- **Economic Analysis:** lights and IMF groups; subnational disparities, with China as the default; population versus development, with exploratory models.
- **Data & Downloads.**
- **Methods.**
- **About.**

## What this adds to the World Bank tools

`space2stats-stata` already collapses the same district tables to ADM1, but it averages district means, medians and percentiles **without weights** and adds zero-coded missing sums. Here:

- means are exact coverage-weighted means;
- no median or percentile is published above ADM2;
- missing values stay missing.

The unweighted and exact means differ by more than 10% in 78% of ADM1 unit-years (`docs/VALIDATION_REPORT.md`, A3). Direct raster tools (`blackmarbler`, `blackmarble-stata`) remain the choice for custom polygons and true medians.

## Method in one paragraph

- **Sums and maxima** are aggregated exactly.
- **Means:** the source's means are coverage-weighted over valid pixels, so `w_valid = sum / mean` is an identity. A provincial mean `Σ sum / Σ w_valid` is therefore the exact coverage-weighted mean. Weights that had to be estimated (completely dark districts) are flagged.
- **Quality shares** are weighted by total weight.
- **Medians and percentiles** exist only at ADM2.

Every assumption about the source is a test in `tests/test_source_assumptions.py`. Full details: `docs/AUDIT.md`,
the Methods page, and `build/site/data/v2/validation.json`.

## Repository layout

```
pipeline/      ntl_core.py (tested aggregation), build_v2.py (products), build_gadm.py (crosswalk),
               econ.py (DOSE, BEA, IBGE), validate.py, schema.py (data dictionary), fetch_*.py, check_sources.py,
               fetch_wdi.py + build_imf_groups.py + build_analysis.py (national panel and Economic Analysis),
               qa/aggregation_rules_benchmark.py (exact rules vs unweighted collapses)
site_src/      templates + assets for the portal; build_site.py renders build/site
tests/         unit tests (synthetic), source-assumption tests, output tests, analysis tests;
               tests/browser/check_*.py drive headless Edge against a local copy of the site
examples/      merge_dose.{do,R,py}
docs/          AUDIT.md, METHODS.md, VALIDATION_REPORT.md, PUBLICATION_PLAN.md, DATA_SOURCES.md,
               DATA_DESCRIPTOR.md, RELEASE.md, SITE_REDESIGN.md
scripts/       publish_pages.sh
```

<a id="rebuild"></a>
## Rebuild

```bash
pip install -r pipeline/requirements.txt
mkdir -p raw && cd raw
curl -LO https://datacatalogfiles.worldbank.org/ddh-published/0066940/DR0095701/ntl_adm2_monthly_all.parquet
curl -LO https://datacatalogfiles.worldbank.org/ddh-published/0066940/DR0095685/ntl_adm2_annual.csv
cd ..
python pipeline/fetch_boundaries.py && python pipeline/fetch_wb_adm2.py && python pipeline/fetch_gadm.py
python pipeline/simplify_world.py && python pipeline/build_geo_match.py && python pipeline/build_gadm.py
python pipeline/build_absorbed.py && python pipeline/build_adm1_from_districts.py && python pipeline/build_adm2_geo.py
# economic sources: see docs/RELEASE.md (DOSE V2.14 from Zenodo 20035157, BEA SAGDP, IBGE states)
python pipeline/build_v2.py && python pipeline/build_world_map.py && python pipeline/run_econ.py
python pipeline/fetch_benchmark.py && python pipeline/validate.py
# economic analysis (2.1): WDI from the World Bank API; IMF groups parsed from the WEO April 2023
# Statistical Appendix PDF saved as raw/econ/imf/weo_2023apr_statsappendix.pdf (URL in docs/DATA_SOURCES.md)
python pipeline/fetch_wdi.py && python pipeline/build_imf_groups.py && python pipeline/build_analysis.py
python pipeline/qa/aggregation_rules_benchmark.py
python -c "import sys; sys.path.insert(0, 'pipeline'); import build_v2; build_v2.write_manifest()"
python site_src/build_site.py
pytest tests
# optional browser checks (needs Microsoft Edge + websocket-client):
python -m http.server 8766 --directory build/site &   # then, in tests/browser:
python check_explorer.py && python check_pages.py && python check_analysis.py
```

## Deploy

1. **Site and smaller data files.** Run `PYTHON=python bash scripts/publish_pages.sh`. It force-pushes `build/site` to the orphan `gh-pages` branch, stored byte-for-byte so checksums match `manifest.json`. GitHub Pages must serve *gh-pages / (root)*, under the `/nightlights-adm1/` path.
2. **Large files.** These are assets of the GitHub release named by `RELEASE_VERSION` in `pipeline/build_v2.py` (currently `v2.0.0`; unchanged in 2.1). If the large files change, create a **new** release and bump `RELEASE_VERSION`. Never replace assets of an existing release.
3. **Versioning.** Follow `docs/RELEASE.md`.

## Licence and citation

Derived data CC BY 4.0; code MIT. GADM boundaries are used only to build the crosswalk and are never redistributed.
Please cite this dataset (`CITATION.cff`), the World Bank source dataset and Román et al. (2018). Related tools:
`space2stats-stata` (on-the-fly ADM1 collapse of the same source) and `blackmarble-stata`, `blackmarbler` and
`blackmarblepy` (direct raster extraction).
