# Validation report — Night Lights ADM1 v3.0.0 (2026-11-23)

v3.0.0 has the same data and analysis as v2.1.0; it adds password protection (A10).

The report has two parts:

- **Part A** lists checks that were executed, with their results.
- **Part B** lists checks that are proposed but not completed.

Every number in Part A is read from a file that the build writes:

- `build/site/data/v2/validation.json`, written by `pipeline/validate.py`.
- `validation_aggregation_rules.json`, written by `pipeline/qa/aggregation_rules_benchmark.py`.
- `analysis/models.json` and `analysis/module_a.json`, written by `pipeline/build_analysis.py`.

All published files carry SHA-256 checksums in `manifest.json`.

## A. Executed

### A1. Automated test suite (`pytest tests`): 49 passed

| File | Tests | What they check |
|---|---|---|
| `test_core.py` | unit tests on synthetic data | Exact sums; coverage-weighted means; "no valid pixel" sums set to missing (NA); estimated-weight flags; transforms. |
| `test_source_assumptions.py` | source facts S1–S7 | Grid completeness, with the one known missing row. The `sum/mean` identity. No-data encoded as 0. Quality shares sum to 1. Gas-flare count is national. |
| `test_outputs.py` | built products | Unique keys. ADM2 → ADM1 parent consistency. Country totals reconcile. Manifest files exist and their hashes match. |
| `test_analysis.py` (new in 2.1) | 15 | Listed below. |

`test_analysis.py` checks:

- One row per economy and year.
- National sums equal the sum of the ADM1 sums.
- National means equal Σ sum ÷ Σ weight.
- World totals are preserved when Taiwan is split out of China.
- A national value is missing (NA) only when a unit containing pixels lacks data.
- The IMF table has 41 advanced, 155 EMDE, 20 euro-area and 7 G7 economies.
- IMF groups in the national panel agree with the IMF table.
- WDI values match the raw API rows for a sample of 200 economy-years.
- The site JSON equals the downloadable panel, for national and DOSE values.
- Every ADM1 unit appears in the analysis JSON.
- Model sample sizes can be reproduced from the panel.
- No median or percentile column exists above ADM2.

### A2. Arithmetic and missing data (`validation.json`)

- Country totals: ADM1 against source districts, maximum relative difference 0.0 (before rounding).
- 6,180 World Bank province-months have no valid pixel at all. v1 published them as 0; they are now NA.
- Quality shares sum to 1 within 1e-6.
- 53,303 province-months involve an estimated pixel weight. This bounds the change in the mean at 0.67% for the median province-month and 2.7% at the 90th percentile.

### A3. Exact rules compared with simple ADM2 → ADM1 collapses (new in 2.1)

The `space2stats-stata` package (`query_s2s.ado`, lines 129–134 as of 2026-11-23) runs `collapse (sum) ntl_sum … (mean) ntl_mean ntl_median ntl_q05 ntl_q95`.

| Comparison | Sample | Result |
|---|---|---|
| Unweighted mean of district means vs the exact coverage-weighted mean | 30,057 World Bank ADM1 unit-years with ≥ 2 districts | Median difference +31%. The difference exceeds 10% in 78% of unit-years and 50% in 43%. The unweighted value is higher in 75%. |
| Mean of district medians vs a median extracted directly from pixels | 150 unit-years, 47 high-grade GADM units, 5 countries, 2021–23 | Within 10% in 47%. Errors run from −66% (5th percentile) to +1,385% (95th). Spearman correlation 0.60. |
| Exact mean vs the directly extracted median | same 150 | Median difference −68%: a mean is not a median. |
| Province-months where a plain sum reads 0 because no district has valid data | 602,615 province-months | 6,180 |
| Province-months where some districts have no valid data, so a plain sum is understated | same | 2,155 |

The median comparison is indicative only. The reference prototype does not document its pixel set, and in several of its files its own mean is below its median.

### A4. Agreement with direct raster extraction (`validation.json` → benchmark)

The reference is the World Bank `blackmarble-stata` prototype, extracted directly to GADM 4.1 ADM1 (2021–2023).

- **Sample:** 126 GADM units (411 unit-years), compared through the crosswalk. 84 benchmark unit-years have no counterpart in our data.
- **Correlation:** 0.996 between log sums.
- **Ratio of our values to the direct extraction:** median 1.054 (5th–95th percentile 0.82–1.62). For high-grade units only, median 1.050 (0.87–1.31).
- **Share of units within 5% / 10%:** 37% / 65%.
- **Possible reasons for the gap:** different collections, land/water masks or coverage rules. The two pipelines cannot be told apart from crosswalk error with these files.

### A5. Official annual composite vs monthly data

Sample: 41,849 province-years with 12 months of data. The ratio of the official annual sum to the mean monthly sum has median 0.861 (5th–95th percentile 0.089–0.992). The two products are kept separate.

### A6. National panel and economic joins (new in 2.1)

- **Coverage:** 241 economies, 2012–2024.
  - 194 have an IMF group.
  - 197 have WDI GDP per capita.
  - Tonga and Samoa are in the IMF list but not in the lights source.
- **Taiwan:** the source's China unit "Taiwan Sheng" is reported as TWN. China in the panel has 31 ADM1 units.
- **Units without pixels:** BRA014 ("Name Unknown") and three US Minor Outlying Islands units contain no pixel and contribute nothing.
- **Niue:** its only unit has no pixel, so its national value is NA in all 13 years.
- **Names:** a naming bug (Australia labelled "Ashmore and Cartier Islands") was found by the browser checks and fixed before publication. Names now use the most frequent source name per code, and a test covers it.

### A7. Exploratory results as computed

These are associations, not effects. Countries use WDI GDP per capita (PPP, constant 2021 international $). Regions use DOSE gross regional product (GRP) per capita (constant 2015 US$).

**Module A (2022): advanced economies vs EMDE (emerging market and developing economies).**

| Measure | Separation (AUC, 95% bootstrap) | Spearman with ln GDP pc: all · advanced · EMDE |
|---|---|---|
| Mean radiance | 0.82 [0.75, 0.88] | 0.73 · 0.12 · 0.72 (n = 197 / 40 / 149) |
| Total radiance | 0.72 [0.64, 0.80] | 0.40 · −0.05 · 0.41 |
| Radiance per person | 0.84 [0.78, 0.89] | 0.84 · −0.02 · 0.86 |
| Per person, gas flares excluded | 0.85 [0.79, 0.90] | 0.85 · −0.02 · 0.87 |

What this shows:

- Lights order EMDE economies by income.
- They barely order advanced economies among themselves.
- The two groups overlap: for mean radiance, 15% of EMDE are above the advanced median.

**Module C: log(total radiance) ~ log(population) + log(GDP per capita).**

| Specification | n | log population [95% CI] | log GDP pc [95% CI] | R² | Notes |
|---|---|---|---|---|---|
| Countries, 2022 (HC3) | 197 | 1.00 [0.92, 1.08] | 1.30 [1.17, 1.44] | 0.87 | Equal elasticities rejected (p = 0.0001). Moran's I of residuals 0.27 (p = 0.001). |
| Countries pooled 2012–2024, year effects, clustered by country | 2,554 | 1.00 [0.93, 1.08] | 1.36 [1.22, 1.49] | 0.87 | |
| Countries, within-country (country + year effects) | 2,554 | 1.44 [0.94, 1.93] | 0.69 [0.48, 0.90] | 0.995 | |
| DOSE regions pooled, year effects | 11,144 | 0.86 [0.77, 0.96] | 0.81 [0.59, 1.02] | 0.71 | |
| DOSE regions, within-country | 11,144 | 0.91 [0.80, 1.01] | 0.82 [0.66, 0.97] | 0.90 | |
| China, 31 provinces, 2012–19 | 248 | 0.80 [0.69, 0.91] | 0.76 [0.57, 0.95] | 0.88 | Moran's I 0.20 (p = 0.025). |
| India, 32 regions | 247 | 1.15 [1.04, 1.25] | 0.79 [0.49, 1.09] | 0.94 | |
| Australia, 8 regions | 64 | 0.93 [0.85, 1.02] | 1.34 [0.92, 1.75] | 0.98 | Too few clusters; descriptive only. |
| United States, 51 states | 408 | 0.84 [0.60, 1.08] | 0.07 [−0.58, 0.71] | 0.65 | Moran's I 0.21 (p = 0.007). |

What the table shows:

- **Countries:** population and GDP per capita are both strongly associated with total radiance, and the elasticities differ.
- **Regions within countries:** both coefficients are close to 0.8–0.9.
- **Spatial dependence:** significant Moran's I means the cross-section standard errors are understated.

**Out-of-sample error (RMSE in log points; training-mean null in brackets).**

| Holdout design | Population only | GDP pc only | Both | Both + country effects |
|---|---|---|---|---|
| Countries, leave one World Bank region out [null 2.90] | 2.15 | 2.57 | 1.05 | — |
| Countries, train 2012–18 / test 2019+ [null 2.72] | 1.78 | 2.50 | 0.98 | 0.36 |
| DOSE regions, leave one country out [null 1.93] | 1.45 | 1.72 | 1.07 | — |
| DOSE regions, train 2012–16 / test 2017–19 [null 1.86] | 1.34 | 1.67 | 1.02 | 0.63 |

### A8. Website checks: headless Edge over the DevTools protocol, site served locally

| Script | Result | Coverage |
|---|---|---|
| `tests/browser/check_explorer.py` | 47/47 | Map, selection, region details, all seven views, exports, filters, zero vs missing, GADM state, ADM2, keyboard. The first run failed at its first map load because the local test server dropped connections (`ConnectionResetError` in its log). The rerun passed 47/47. |
| `tests/browser/check_pages.py` | 50/50 | Home map, including the new country view, per-person values and WDI tooltip. All 54 download-picker combinations; every local link HEAD 200. Internal links on 8 pages. No horizontal overflow at 1440/1024/768/390 px on 8 pages. Mobile toggles. No JS errors. |
| `tests/browser/check_analysis.py` | 43/43 | All charts drawn. Exported CSVs equal the panel files (mean and per-person values, ADM1 ranking). Rankings sorted. China shows 31 provinces with Taiwan separate. Countries without DOSE show a message and no estimate. DOSE region counts equal the panel. Australia has 8 regions. Model and cross-validation tables present. Mobile overflow. Explorer region context: rank, WDI, DOSE. |

### A9. Files unchanged from v2.0.0

The v2.0.0 and v2.1.0 manifests were compared:

- All 2,874 files listed in v2.0.0 have identical SHA-256 checksums.
- Release-asset URLs still point to `releases/download/v2.0.0/` and are unchanged.
- 11 files are new.

### A10. Password protection (v3.0.0) — `tests/browser/check_secure.py`: 39/39

Run against the encrypted build served by `tests/browser/pages_server.py`, which, like GitHub Pages, answers missing paths with `404.html`.

**Without signing in:**
- Plain page and data paths are not served.
- `.enc` files contain no readable page text or data.
- `auth.json` holds only salts, the iteration count, the wrapped content keys and test values.
- Data used by v2 is encrypted under the v2 key; v3-only files under the v3 key.

**Signing in:**
- A deep link is redirected to sign-in, keeping its target page and `#hash`.
- A wrong password is rejected.
- The correct password opens the requested page.

**Signed in:**
- The explorer reads Parquet through the decrypting worker.
- File size and SHA-256 after decryption equal `manifest.json`.
- Byte-range requests return 206 with the correct bytes.
- v3 home, analysis, download and about pages work, with no JS errors.
- The version bar switches to v2.
- The v2 explorer and home map work on the shared data; v2 pages read the v2.0.0 manifest; the v2 bar links back to v3.
- Old addresses (`/explore.html#…`) reach v3.

**After signing out:**
- Pages require the password again.
- Data requests are refused (401).

**With the v2-only password:**
- A v3 deep link opens the same page in v2, with its `#hash`; a v3-only page (analysis) opens the v2 home page; old addresses reach v2.
- The version bar has no link to v3.
- v3 pages, v3-only data files and the v3 manifest are refused (403); the v2.0.0 manifest and shared files decrypt with correct SHA-256.
- No JS errors; after signing out, v2 requires the password again.

## B. Proposed, not completed

1. **Pixel-level ADM1 medians** for a stratified sample of countries (e.g. with `blackmarbler`). This would give a real median benchmark, replacing the indicative prototype comparison.
2. **Direct extraction to the World Bank ADM1 polygons**, rather than GADM, to separate crosswalk error from processing differences in the 5% level gap.
3. **Confirm the Black Marble collection (C1 or C2)** with the World Bank. Re-run the benchmark if it differs from the prototype.
4. **Independent subnational GDP beyond DOSE.** Candidates include official statistics such as NBS China provincial yearbooks or BEA, for years after 2019, where DOSE ends. These must be documented sources, not lights-derived estimates.
5. **Spatially robust inference:**
   - Conley standard errors, or spatial-block bootstrap, for the cross-sections.
   - Spatial-block cross-validation finer than World Bank regions.
6. **IMF classification by vintage.** Apply each WEO edition's groups to its own year, instead of the April 2023 list for every year.
7. **Sensitivity to coverage.** Exclude low-coverage unit-years from Module C, and drop gas-flare-dominated countries entirely.
8. **NOAA-20/21 continuation** after the end of Suomi NPP, including a cross-sensor overlap test.
9. **Downloaded-file vs chart consistency** for every country and measure. Section A8 checks a sample.
