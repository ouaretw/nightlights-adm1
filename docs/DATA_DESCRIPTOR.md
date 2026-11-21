# Data descriptor (draft)

**Title:** Night Lights ADM1: NASA Black Marble nighttime lights for first- and second-level administrative units,
linked to subnational economic data

**Target venues:**
- *Scientific Data*, "Data Descriptor": requires a public repository with a DOI, a technical-validation section and usage notes.
- *Data in Brief*, "Data Article": a shorter format that suits a companion to a research paper.

Recommendation: Scientific Data if the validation is extended (see Open items); otherwise Data in Brief.

**Authors:** Walid Ouaret (to be confirmed: co-authors, affiliations, CRediT roles).

---

## Abstract (≤170 words)

Nighttime lights are widely used as a proxy for subnational economic activity. The World Bank aggregates NASA Black
Marble radiance to 39,366 second-level administrative units (ADM2), but most subnational economic statistics are
reported for first-level units (ADM1). We present a dataset that provides:
- the native ADM2 observations with corrected no-data handling;
- an exact aggregation to the source's World Bank ADM1 units, with coverage-weighted means and propagated quality shares;
- an aggregation to GADM 4.1 ADM1 units through a graded district-level crosswalk;
- a linkage to DOSE V2.14 regional GDP, with a ready-to-merge panel.

Data are monthly (2012–2025) and annual (2012–2024) for 240 countries and territories, with gas-flare-excluded series,
quality indicators and log/asinh transforms. Every source assumption the method relies on is tested automatically, and
results are validated against direct raster extractions and regional GDP. Files are distributed as CSV, Parquet and
Stata with an interactive portal.

## Background & Summary

- **The problem.** Economic data are reported at ADM1, while the World Bank Black Marble statistics are at ADM2. A
  simple average of district means is biased, and quality information is usually lost.
- **Prior art (cite):**
  - World Bank `space2stats-stata`: on-the-fly ADM1 collapse of the same tables, using unweighted means and without quality shares.
  - `blackmarble-stata`: a prototype of direct GADM 4.1 ADM1 extraction, covering a few countries and years.
  - `blackmarbler` / `blackmarblepy`: on-demand extraction, which needs a NASA token.
  - GLocal (Harvard Growth Lab, 2024): EOG VIIRS on GADM 3.6.
  - EOG VNL rasters.
- **Contribution (narrow claim):** an exactly weighted, quality-propagating ADM1 aggregation of the Space2Stats Black
  Marble tables; corrected native ADM2 data; a documented GADM 4.1 and DOSE linkage; versioned, citable files.

## Methods

1. **Source** (dataset 0066940 v2; SHA-256 in `build_meta.json`).
2. **Source properties S1–S7** (see `pipeline/ntl_core.py`), each tested on every build.
3. **Aggregation:**
   - sums and maxima: exact;
   - `w_valid = sum / mean`: an identity for coverage-weighted means;
   - provincial mean = `Σ sum / Σ w_valid`;
   - quality shares weighted by `w_total`;
   - no-data handling;
   - flagged estimated weights.
4. **Annual products:** the official NASA annual composite, and annual values derived from monthly data (kept separate).
5. **GADM 4.1 crosswalk.** Each district is located through a layered process:
   1. code and name;
   2. unique name with province agreement;
   3. old-province outline, at ≥90% overlap;
   4. old province identified as a current ADM2;
   5. sibling vote, at ≥90% agreement;
   6. province name with transliteration.

   Districts are then assigned whole by largest overlap in an equal-area projection (EPSG:6933). Each unit gets a
   match grade; absorbed units are detected geometrically.
5a. **Map outlines (display only).** A World Bank ADM1 unit is drawn with today's WB-GAD outline when code and name agree;
   otherwise its outline is the union of the current ADM2 polygons its own districts were located on (never using a polygon
   claimed by two provinces, never overlapping an outline already drawn). 3,195 of 3,587 units have an outline.
6. **DOSE V2.14 linkage.** Each region is linked by one of: GADM ID with a name check; a suffix fix; a researched
   renumbering; an explicitly verified rename; DOSE's own polygons with a ≥50% district overlay; or a unique name.
   Regions with reused IDs are left unlinked. Results:

   | Link method | Regions |
   |---|---|
   | `gadm_id` | 1,456 |
   | `dose_geometry` | 91 |
   | Other methods | see `dose_link_summary.json` |
   | Unlinked or without districts | ~60 |

7. **National crosswalks:** BEA FIPS (51/51 exact) and IBGE UF (27/27 exact).

## Data Records

Repository: GitHub release vX.Y.Z plus a Zenodo DOI (to be minted). Each record is listed with its size and checksum
in `manifest.json`:
- the three products × frequencies, keyed on `ADM2CD_c`, `ADM1CD_c` and `GID_1`;
- the crosswalk and QA tables;
- the DOSE panel;
- the data dictionary.

## Technical Validation

Numbers come from `validation.json`:
- **Arithmetic reconciliation** with the source.
- **Mean-in-range** test.
- **Quality-share closure:** shares sum to 1.
- **No-data handling.**
- **Effect of estimated weights** on means.
- **Crosswalk sensitivity:** light share by placement method; identical series for one-to-one units.
- **Agreement with direct raster extraction:** blackmarble-stata, 13 countries, 2021–2023.
- **Official annual vs monthly-derived** values.
- **Descriptive association with DOSE regional GDP:** cross-section and two-way fixed effects. Not causal.

## Usage Notes

- Filter on `coverage`.
- Prefer `ntl_nogf_5km_sum` where gas flaring matters.
- Use `GID_1` to join GADM-keyed data, and check `xw_match_quality` and `xw_absorbs_units`.
- Stata, R and Python examples are provided.
- **Series end.** The Suomi NPP Black Marble series ends in late 2026. Continuation needs NOAA-20 VJ146 products.

## Code Availability

Repository URL; MIT licence; Python 3.11+, pandas, pyarrow, geopandas; tests run in CI.

## Open items before submission

- [ ] Confirm the Black Marble collection (C1/C2) with the World Bank (data@worldbank.org).
- [ ] Mint the Zenodo DOI for the release and add it to CITATION.cff.
- [ ] Optional: extend the validation with direct extractions (`blackmarbler` + GADM 4.1) for a stratified sample of
  countries, especially low-grade units. This needs a NASA Earthdata token.
- [ ] Decide authorship and the target journal.
- [ ] Report the PDF typo upstream: the `ntl_gf_10km` variables are described as "within 5km".
