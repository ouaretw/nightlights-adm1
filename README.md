# Night Lights ADM1

NASA Black Marble nighttime lights aggregated to **first-level administrative units (ADM1)**
for 240 countries and territories: monthly 2012-01 to 2025-12, annual 2012–2024.

**Website and downloads:** https://ouaretw.github.io/nightlights-adm1/

The World Bank publishes Black Marble statistics at ADM2 (district) level
([Space2Stats, dataset 0066940](https://datacatalog.worldbank.org/search/dataset/0066940)).
Most subnational economic data are reported at ADM1, so this repository aggregates the ADM2 tables
to ADM1 and serves the result as an explorable, downloadable dataset.

## Files (in `docs/data/`)

| File | Content |
|---|---|
| `adm1_monthly_all.parquet` / `.csv.gz` | 602,615 rows: 3,587 ADM1 × 168 months |
| `adm1_annual_all.parquet` / `.csv.gz` | 46,631 rows: 3,587 ADM1 × 13 years (NASA annual composites) |
| `monthly/<ISO3>.csv`, `annual/<ISO3>.csv` | Per-country extracts |
| `geo_match.csv` | Whether and how each ADM1 unit is drawn on the web map |
| `build_meta.json` | Validation results of the last build |

Keys: `ISO_A3`, `ADM1CD_c` (World Bank Official Boundaries codes, vintage used by the source table).

## Method

* ADM2 units nest exactly in ADM1 (each `ADM2CD_c` has one `ADM1CD_c`), so aggregation is a group-by.
* **Sums** (`ntl_sum`, gas-flaring variants) and **max** are exact. Country totals match the ADM2 source to < 1e-15 relative error.
* **Mean** is pixel-weighted. Each ADM2's valid-pixel count is recovered as `sum / mean`. For completely dark units it is `T × (1 − prop_na)`, with `T` the static pixel count. Every ADM1 mean lies within the range of its ADM2 means.
* **Quality shares** are pixel-weighted. `coverage` is the share of pixels with a valid value.
* **Not published:** medians and percentiles, which cannot be recovered at ADM1 from ADM2 summaries.
* **Source quirk:** `n_gasflaring_locs` is constant across every ADM2 of a country, so it is a national count, not a per-unit one. It is published as `n_gasflaring_locs_country` and not summed.

### Map geometry

The source table was built on an older vintage of the World Bank boundaries than the one the public
FeatureServer serves today, and some ADM1 codes were reused for different units (e.g. `ALB005`).
`pipeline/build_geo_match.py` draws a polygon only when code and name agree, or when names match
one-to-one in a country with an unchanged unit count. 2,641 of 3,587 units are drawn, 366 of them
flagged as approximate. **The data files are complete regardless of map status.**

## Rebuild

```bash
# 1. download the source (≈1.2 GB, not committed)
mkdir -p raw && cd raw
curl -LO https://datacatalogfiles.worldbank.org/ddh-published/0066940/DR0095701/ntl_adm2_monthly_all.parquet
curl -LO https://datacatalogfiles.worldbank.org/ddh-published/0066940/DR0095685/ntl_adm2_annual.csv
cd ..
pip install -r pipeline/requirements.txt
python pipeline/aggregate_adm1.py      # ADM1 tables + site series
python pipeline/fetch_boundaries.py    # simplified WB boundaries (ArcGIS FeatureServer)
python pipeline/build_geo_match.py     # safe code/name matching for the map
python pipeline/simplify_world.py      # shrink the world outline
```

QA scripts used during development are in `pipeline/qa/`.

## Licence and citation

Derived data: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Code: MIT.
Source: World Bank, *Space2Stats – Monthly & Annual Black Marble Nighttime Lights* (CC BY 4.0);
NASA Black Marble (Román et al., 2018, *Remote Sensing of Environment* 210:113–143).
Boundaries: World Bank Official Boundaries (CC BY 4.0). The boundaries do not imply any judgement on
the legal status of any territory. Not an official World Bank or NASA product. See `CITATION.cff`.
