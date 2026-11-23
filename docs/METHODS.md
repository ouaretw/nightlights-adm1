# Methods — Night Lights ADM1 v2.1.0

This file is the methods summary. Column-level detail is in `docs/DATA_DESCRIPTOR.md` and `data/v2/data_dictionary.csv`. Validation results are in `docs/VALIDATION_REPORT.md`.

## 1. Source

The source is World Bank Space2Stats *Monthly & Annual Black Marble Nighttime Lights* (dataset 0066940, CC BY 4.0). It provides NASA Black Marble VNP46A3 (monthly) and VNP46A4 (annual) radiance, already summarised for 39,366 World Bank ADM2 districts:

- monthly, 2012-01 to 2025-12;
- official annual composites, 2012–2024.

Each district row carries:

- radiance: sum, mean, max, median, 5th and 95th percentiles;
- shares of valid, good, poor and gap-filled pixels;
- gas-flare-masked variants;
- a national count of gas-flaring locations.

Source checksums are recorded in `build_meta.json` and `pipeline/source_lock.json`.

## 2. Aggregation rules (`pipeline/ntl_core.py`, tested)

| Statistic | ADM1 / ADM0 rule | Status |
|---|---|---|
| `ntl_sum` and the gas-flare sums | Σ of district sums (districts partition the unit) | Exact |
| `ntl_max` | max of district maxima | Exact |
| `ntl_mean` | Σ sum ÷ Σ `w_valid`, where `w_valid = sum / mean` is the district's valid-pixel coverage weight (an identity in the source) | Exact; flagged where the weight is estimated |
| Quality shares | Weighted by total weight `w_valid / (1 − prop_na)` | Exact where recoverable, else flagged |
| Median and percentiles | **Not produced** above ADM2 | Not derivable from district summaries |
| `n_gasflaring_locs` | National count, repeated | Source definition |

Notes on missing and dark data:

- **No valid pixel.** When a district has no valid pixel, the source stores `sum = 0`. That value is set to NA, and the unit's `n_adm2_no_valid_data` counts it.
- **Valid but completely dark.** When a district is valid but completely dark, its `w_valid` cannot be recovered from the row. It is estimated as total weight × (1 − share missing) and flagged (`w_valid_estimated_share`). Sums are never affected.
- **Monthly vs annual.** Official annual composites (`annual`) and annual values derived from months (`annual_from_monthly`) are separate products.

## 3. Geographies

- **World Bank ADM1 (`adm1_wb`).** A strict group-by of districts on the source's `ADM1CD_c`, so it is exact. The source uses an older World Bank boundary vintage.
- **GADM 4.1 ADM1 (`adm1_gadm41`).** Each district is assigned whole to the GADM 4.1 unit it overlaps most, using a layered crosswalk (code and name, then geometry). Every unit is graded `high`, `medium` or `low`. Absorbed units are flagged. GADM geometries are never redistributed.
- **Map outlines (display only).** A unit keeps today's World Bank outline where its code and name still agree. Otherwise its outline is the union of the current district polygons its own districts were matched to. Ambiguous polygons are never used.
- **DOSE regions.** DOSE regions are linked to source districts by GADM ID with a name check, by DOSE's own polygons, or by a unique near-exact name. Every link records its method, and unlinked regions are listed, not guessed.

## 4. National panel (ADM0, new in 2.1; `pipeline/build_analysis.py`)

- **Sums and means.** National sums are the sums of the ADM1 sums. The national mean is Σ sum ÷ Σ `w_valid`.
- **When the national value is missing.** If any unit that contains pixels lacks valid data in a year, the national value is NA. A partial total is never published.
- **Units with no pixels.** Units with `w_total = 0` (e.g. BRA014) contribute nothing and are counted in `n_adm1_without_pixels`.
- **Economy definitions.** These follow the IMF and WDI:
  - the source's China unit "Taiwan Sheng" is reported as TWN;
  - other boundary conventions are left as in the source and noted per row (`national_definition_note`): Western Sahara within Morocco's units, Crimea, Abkhazia and northern Cyprus.
- **Joins.** All joins are by ISO3 and year:
  - **IMF:** WEO April 2023 Statistical Appendix, Tables B and E. Names are parsed from the PDF, the counts 41/155 and the regional counts are asserted, and names are matched to ISO3 through the World Bank country list plus an explicit table. The build fails if any name is unmatched.
  - **WDI:** `SP.POP.TOTL`, `NY.GDP.PCAP.PP.KD`, `NY.GDP.MKTP.PP.KD`, `NY.GDP.PCAP.KD`.
- **Per person.** Per-person radiance is `ntl_sum / pop`. It is never computed where WDI does not report population.

## 5. Economic analysis

### Module A — lights and development

For each year and measure:

- the median and IQR for advanced economies and for EMDE;
- AUC from the Mann–Whitney test, with a 95% bootstrap interval (1,000 resamples, fixed seed);
- overlap shares;
- Spearman and Pearson (log) correlations with ln GDP per capita, overall and within each group.

Only positive values are used. The IMF grouping is a single vintage (April 2023), applied to all years.

### Module B — subnational disparities

- Rankings, distributions and indexed time series use World Bank ADM1 units.
- Disparity statistics are descriptive and unweighted across units: max/min, P90/P10, coefficient of variation, and the share of light in the brightest 20% of units.
- Regional GDP per capita and population come from DOSE V2.14 (2012–2019), shown on DOSE's own regions with their link method. Countries without DOSE coverage show no economic values.

### Module C — population versus development

- **Model.** OLS of `log(ntl_sum) ~ log(pop) + log(GDP per capita)` on positive values only. Exclusions are counted, and no constant is added to zeros.
  - Countries are fitted by year (HC3 errors), pooled with year effects, and within country (country and year effects), with errors clustered by country.
  - DOSE regions are fitted pooled, within country, and by country (clustered by region; flagged when there are fewer than 20 clusters).
- **Equal-elasticity test.** A Wald test of whether the two elasticities are equal, i.e. whether total radiance scales with GDP alone.
- **Spatial dependence.** Moran's I of residuals, using the k nearest centroids (countries k = 5; regions k = 4) and 999 permutations.
- **Prediction checks.**
  - Countries: leave one World Bank region out, and train 2012–2018 / test 2019 onward.
  - DOSE regions: leave one country out, and train 2012–2016 / test 2017–2019.
  - Results are reported as RMSE in log points against a training-mean baseline.
- **No circularity.** No GDP is distributed to units using lights.

## 6. Limitations

See the Methods page, §6 ("Known limitations"), on the website. In short:

- radiance is not GDP;
- means and medians differ, and only means are published above ADM2;
- clouds, snow, aurora, flares, fires and saturation affect observations;
- products and sensors are not interchangeable;
- boundaries change over time;
- associations are not effects;
- missing economic data are never estimated;
- the Suomi NPP series ends on 2026-11-02.
