# Data sources

Every input, where it comes from, its licence, and how this project uses it.

Retrieval dates and checksums:

- source data: `build/site/data/v2/build_meta.json` and `pipeline/source_lock.json`;
- WDI: `raw/econ/wdi/fetch_log.json`;
- IMF: `raw/econ/imf/weo_2023apr_groups_meta.json`.

| Source | Version / retrieval | Access | Licence / terms | Use here | Redistributed? |
|---|---|---|---|---|---|
| World Bank Space2Stats *Monthly & Annual Black Marble Nighttime Lights* | dataset 0066940; files `ntl_adm2_monthly_all.parquet`, `ntl_adm2_annual.csv` (checksums in `build_meta.json`) | https://datacatalog.worldbank.org/search/dataset/0066940 | CC BY 4.0 | All radiance values | Derived form (ADM2 corrected, ADM1, ADM0), with attribution |
| NASA Black Marble VNP46A3 / VNP46A4 (Román et al. 2018, doi:10.1016/j.rse.2018.03.017) | Via the World Bank product; collection not stated by the source | https://blackmarble.gsfc.nasa.gov/ | NASA open data policy | Underlying product | No (cited) |
| World Bank Official Boundaries (ADM0/1/2) | Retrieved by `pipeline/fetch_boundaries.py`, `fetch_wb_adm2.py` | World Bank Data Catalog | CC BY 4.0 | Map outlines; geometric crosswalk | Simplified display copy |
| GADM 4.1 | Retrieved by `pipeline/fetch_gadm.py` | https://gadm.org | Free for academic and non-commercial use; **no redistribution** | Crosswalk construction; DOSE centroids for Moran's I | **No** (codes and names only) |
| DOSE V2.14 (Wenz et al. 2023, *Scientific Data* 10, 425) | Zenodo record 20035157 | https://zenodo.org/records/20035157 | CC BY 4.0 | Regional GRP per capita and population, 2012–2019 overlap | Joined panel, with citation |
| World Bank WDI: `SP.POP.TOTL`, `NY.GDP.PCAP.PP.KD`, `NY.GDP.MKTP.PP.KD`, `NY.GDP.PCAP.KD` | API, retrieved 2026-11-23 (`fetch_wdi.py`) | https://api.worldbank.org/v2 | CC BY 4.0 | National population and GDP | Yes, in the national panel |
| IMF *World Economic Outlook*, April 2023, Statistical Appendix, Tables B and E | PDF SHA-256 `a380fed5…`, parsed by `build_imf_groups.py` | https://www.imf.org/-/media/files/publications/weo/2023/april/english/statsappendix.pdf | IMF copyright and usage terms | Advanced / EMDE group and region per economy | Membership table (ISO3, IMF name, group), with citation |
| US BEA SAGDP | `SAGDP.zip` | https://apps.bea.gov/regional/zip/SAGDP.zip | Public domain (US government) | State GeoFIPS ↔ GADM crosswalk | Crosswalk only |
| IBGE states API | `estados.json` | https://servicodados.ibge.gov.br/api/v1/localidades/estados | Open data | UF code ↔ GADM crosswalk | Crosswalk only |
| World Bank `blackmarble-stata` prototype extractions | 13 countries × 2021–2023 (`fetch_benchmark.py`) | Public S3 (see `fetch_benchmark.py`) | World Bank terms of the repository | Validation benchmark only | No |

## Three layers of ownership

1. **Source observations** (NASA, World Bank). Public. This project claims no exclusivity over them.
2. **Derived data and code** (this repository). Data are released under CC BY 4.0 and code under MIT. Versioned, with checksums. A Zenodo DOI is planned but has not been minted yet.
3. **Analyses, interpretations and manuscripts.** The exploratory analyses on the website are public. Manuscripts in preparation are kept outside this repository until publication; this does not restrict access to layers 1 and 2.

## Sources considered and not integrated

| Source | Reason |
|---|---|
| WorldPop, GHSL population | Not yet ingested. Would provide ADM1 population globally, but these products are partly modelled from nighttime lights, so they cannot independently validate lights. |
| Global Data Lab SHDI | Requires a GDL login, non-commercial terms, and no published GDL → GADM correspondence (integration page) |
| OECD TL2 regional statistics | No public OECD boundary file found; US TL2 is covered by the BEA states, and most other OECD regional GDP already enters DOSE |
| Lights-downscaled GDP grids | Excluded: validating lights against GDP built from lights would be circular. |
| Other Earth-observation indicators (NDVI, LST, Sentinel-2, Landsat) | Documented under *Future indicators* on the About page; none is ingested. |
