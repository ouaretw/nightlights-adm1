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

Each product comes in `monthly` (2012-01 to 2025-12) and `annual` (NASA's official annual composite, 2012–2024). The ADM1
products also have `annual_from_monthly`, which is derived from monthly data and kept separate. Economic linkage covers
DOSE V2.14 (a ready-to-merge panel), plus US BEA and Brazil IBGE crosswalks.

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
               econ.py (DOSE, BEA, IBGE), validate.py, schema.py (data dictionary), fetch_*.py, check_sources.py
site_src/      templates + assets for the portal; build_site.py renders build/site
tests/         unit tests (synthetic), source-assumption tests, output tests
examples/      merge_dose.{do,R,py}
docs/          AUDIT.md, DATA_DESCRIPTOR.md, RELEASE.md
scripts/       publish_pages.sh
```

## Rebuild

```bash
pip install -r pipeline/requirements.txt
mkdir -p raw && cd raw
curl -LO https://datacatalogfiles.worldbank.org/ddh-published/0066940/DR0095701/ntl_adm2_monthly_all.parquet
curl -LO https://datacatalogfiles.worldbank.org/ddh-published/0066940/DR0095685/ntl_adm2_annual.csv
cd ..
python pipeline/fetch_boundaries.py && python pipeline/fetch_wb_adm2.py && python pipeline/fetch_gadm.py
python pipeline/simplify_world.py && python pipeline/build_geo_match.py && python pipeline/build_gadm.py
python pipeline/build_absorbed.py && python pipeline/build_adm2_geo.py
# economic sources: see docs/RELEASE.md (DOSE V2.14 from Zenodo 20035157, BEA SAGDP, IBGE states)
python pipeline/build_v2.py && python pipeline/fetch_benchmark.py && python pipeline/validate.py
python site_src/build_site.py
pytest tests
```

## Licence and citation

Derived data CC BY 4.0; code MIT. GADM boundaries are used only to build the crosswalk and are never redistributed.
Please cite this dataset (`CITATION.cff`), the World Bank source dataset and Román et al. (2018). Related tools:
`space2stats-stata` (on-the-fly ADM1 collapse of the same source) and `blackmarble-stata`, `blackmarbler` and
`blackmarblepy` (direct raster extraction).
