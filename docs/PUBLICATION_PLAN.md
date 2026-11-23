# Publication plan (draft, 2026-11-23)

This is a plan, not a manuscript. It proposes a data paper and sets out what must be true before it is submitted. Results quoted here are from `docs/VALIDATION_REPORT.md`, Part A (executed). Everything in Part B there is still open.

## 1. Working title, and the conditions for using it

The proposed title, *"A harmonized and validated global ADM1 nighttime-light panel for subnational economic research"*, is **not yet defensible in full**:

- **"Harmonized"** is supported for World Bank ADM1 units (exact) and for GADM 4.1 units (a graded crosswalk).
- **"Validated"** is supported only in part:
  - aggregation identities are tested;
  - a 13-country direct-extraction benchmark gives a log correlation of 0.996, but a median level gap of about 5% that is unexplained.

A title that is accurate today:

> *Exactly aggregated, quality-flagged ADM1 nighttime-light statistics from the World Bank Space2Stats Black Marble tables, linked to subnational economic data*

Use the stronger title only after items B1–B3 of the validation report are done: pixel-level medians, direct extraction to World Bank ADM1 polygons, and confirmation of the Black Marble collection.

## 2. Motivation

- Subnational economic data (regional GDP, DOSE, national statistical offices) are mostly published at ADM1.
- The World Bank Black Marble tables are published at ADM2.
- Researchers who collapse them themselves face three choices that change results:
  - how to average means;
  - what to do with medians;
  - how to treat the source's zero-coded missing values.
- They must also join World Bank units to the GADM-based units that economic datasets use.

## 3. Existing landscape (checked 2026-11-23)

| Tool | What it provides at ADM1 | Limitation relevant here |
|---|---|---|
| World Bank `space2stats-stata` (`query_s2s`, `adm_level(1)` / `(0)`) | On-the-fly collapse of the same district tables | Means, medians and percentiles are **unweighted averages** of district values (`query_s2s.ado`, lines 129–134). Zero-coded missing sums are added as zeros. World Bank units only. |
| World Bank `blackmarble-stata`, `blackmarbler`, `blackmarblepy` | Direct extraction from Black Marble rasters to any polygon, so true medians are possible | Requires raster processing per user and query; no ready global panel; no economic linkage |
| Space2Stats API | Hexagon-level statistics summarised to user geometries | Per-query; ADM1 panels are not distributed as files |
| DOSE V2.14 | Regional GDP for about 1,660 regions | Contains no nighttime lights |

## 4. Actual novelty: what can be claimed

1. **Correct ADM1 means at scale.** The coverage-weighted mean is an exact identity in the source; the unweighted alternative differs by more than 10% in 78% of ADM1 unit-years (A3). Publishing no median or percentile above ADM2 is itself a methodological statement, backed by the benchmark.
2. **Explicit missing data.** 6,180 province-months that a plain sum reports as zero light are set to missing; 2,155 more are flagged as partial.
3. **Linkage to economic geographies.** A graded GADM 4.1 crosswalk, and DOSE linkage of 1,632 of 1,667 regions with recorded link methods. No name-only joins without a flag.
4. **A versioned, checksummed panel** at ADM2, ADM1 and ADM0 (with IMF and WDI variables), with reproducible code and tests.

Claims that cannot be made:

- a new satellite product;
- higher accuracy than direct raster extraction;
- that lights measure GDP;
- any causal finding.

## 5. Construction workflow (for the paper)

1. Source download with checksums.
2. ADM2 correction: missing values (NA), weights, flags.
3. Exact ADM1 aggregation.
4. GADM crosswalk with grades.
5. DOSE linkage.
6. National panel.
7. Validation.
8. Release with manifest and checksums, on Pages and as GitHub release assets.

Code paths are in `README.md` → *Rebuild*.

## 6. Quality assessment and validation (prioritised)

| Priority | Item | Status |
|---|---|---|
| 1 | Arithmetic identities, missing-data handling, key uniqueness, parent–child nesting | Done (tests) |
| 2 | Exact rules vs simple collapses | Done (A3) |
| 3 | Direct-extraction benchmark (13 countries, GADM) | Done; level gap unexplained |
| 4 | Confirm Black Marble collection with the World Bank | Open |
| 5 | Pixel-level ADM1 medians, stratified sample, to quantify median error properly | Open |
| 6 | Direct extraction to World Bank ADM1 polygons, to separate crosswalk error from processing differences | Open |
| 7 | Comparison with `space2stats-stata` output on identical queries, run in Stata rather than reimplemented | Open |
| 8 | Coverage-sensitivity analysis for monthly data at high latitudes | Partly done (flags); analysis open |

## 7. Demonstration of economic applications

These are short, descriptive illustrations, using the Module A and C results in the validation report:

- lights separate IMF advanced economies from EMDE (AUC about 0.82 for mean radiance) but barely rank advanced economies among themselves;
- total radiance scales with both population and GDP per capita, with unequal elasticities across countries and elasticities of about 0.8–0.9 within countries;
- predictive holdout errors are reported.

Each result would be reported with spatial-dependence diagnostics and the caveats in the Methods page (§6). None is the paper's contribution; they show that the panel is usable.

## 8. Limitations (to state in the paper)

- The source boundary vintage is old.
- GADM values are approximations.
- The Black Marble collection is unknown.
- The Suomi NPP series ends on 2026-11-02.
- Observations are affected by clouds, snow, aurora, flares and saturation.
- Monthly and annual products differ.
- Medians are unavailable above ADM2.
- Radiance is not GDP.

## 9. Data availability and reproducibility

- **Data:** CC BY 4.0. Large files are GitHub release assets (immutable per version); smaller files are on the project site.
- **Code:** MIT, with `pytest` tests and browser checks.
- **Archive:** a Zenodo archive with a DOI is to be created at submission; none exists yet.
- **Third-party data:** GADM geometries are not redistributed; DOSE, WDI and IMF are cited.

## 10. Candidate venues (depending on what validation shows)

- **Data descriptor:** *Scientific Data* (Data Descriptor), *Data in Brief*, *Geoscience Data Journal*.
- **Methods note on aggregation rules:** a short note in a remote-sensing or applied-economics methods outlet, if the median and weighting results are substantial after item 5.
- **Not suitable:** a general economics journal on this dataset alone, because there is no new economic finding.

## 11. Before submission

- [ ] Validation items 4–7.
- [ ] Authorship and contributions agreed by all contributors.
- [ ] Zenodo DOI minted and added to `CITATION.cff`.
- [ ] Freeze a release version; the paper cites that version only.
