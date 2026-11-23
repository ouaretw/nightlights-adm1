# Audit of Night Lights ADM1 v2.0.0 → v2.1.0 (2026-11-23)

**Scope.** The whole repository at v2.0.0, plus the public site:

- pipeline, products and schemas;
- aggregation rules;
- crosswalks;
- economic integration;
- downloads and hosting;
- documentation.

The work responded to external economist feedback: compare lights with IMF groups and GDP, look at subnational disparities in China, separate population from development, consider other satellite indicators, and decide whether to restrict data.

The v1.1 audit (findings A1–A12) is kept below. All of its fixes remain in place.

## Inventory (inspected, not assumed)

- **Source.** World Bank Space2Stats 0066940: ADM2 monthly 2012-01 to 2025-12 and official annual 2012–2024. 39,366 districts in 240 ISO codes.
  - Variables: sum, mean, max, median, q05, q95, five gas-flare variants, four quality shares and a national flare count.
  - Checksums are in `build_meta.json`.
- **Products.**
  - `adm2`, `adm1_wb` (exact) and `adm1_gadm41` (graded crosswalk), each monthly, annual and annual-from-monthly.
  - DOSE V2.14 panel; BEA and IBGE crosswalks.
  - CSV, Parquet and Stata formats. 2,874 files at v2.0.0: Pages carries 727 MB, release v2.0.0 carries about 1 GB.
- **Aggregation** (`ntl_core.py`):
  - exact sums;
  - exact coverage-weighted means (Σ sum ÷ Σ `w_valid`);
  - no medians or percentiles above ADM2.
  This already satisfies the requirement that ADM1 medians must not be built from ADM2 medians.
- **Licences.** CC BY 4.0 for the source, WB boundaries, DOSE and WDI. GADM is non-commercial with no redistribution, and is not redistributed. Details are in `docs/DATA_SOURCES.md`.
- **Tests.** 34 pytest tests; browser checks for the explorer and pages.

## Strengths kept

- Exact sums and weighted means.
- Missing data handled explicitly (no-data sums set to NA).
- Flagged estimated weights.
- Separate annual products.
- Graded crosswalk and documented DOSE links.
- Checksummed manifest and immutable releases.
- Pages contain no invented numbers.

## Findings

| # | Finding | Evidence | Action |
|---|---|---|---|
| B1 | **The contribution relative to World Bank tools was asserted, not measured.** `space2stats-stata` already offers ADM0, ADM1 and ADM2 collapses of the same source. | `query_s2s.ado`, lines 129–134: `collapse (sum) … (mean) ntl_mean ntl_median ntl_q05 ntl_q95`. Unweighted means and medians; zero-coded missing values added as zeros. | Quantified (`pipeline/qa/aggregation_rules_benchmark.py`). The unweighted mean differs from the exact mean by more than 10% in 78% of ADM1 unit-years. The mean of district medians is within 10% of a directly extracted median in 47% of cases. The About page and `PUBLICATION_PLAN.md` state the difference without claiming novelty beyond it. |
| B2 | **No national panel and no economic classification.** Development comparisons could not be made reproducibly. | — | `data/v2/adm0/ntl_adm0_annual_econ`: exact national sums and means joined by ISO3 to the IMF WEO April 2023 groups (parsed from the IMF PDF, counts asserted) and WDI population and GDP. |
| B3 | **The China code includes Taiwan.** The source's CHN has 32 ADM1 units, including "Taiwan Sheng"; the IMF and WDI treat Taiwan separately. | `adm1_wb_annual_global` | Taiwan reported as TWN in the national panel and analysis; other boundary conventions noted per row (`national_definition_note`). |
| B4 | **Zero-pixel units.** BRA014 ("Name Unknown") and three US Minor Outlying Islands units contain no pixel, so their sums are always NA. A strict "any unit missing → national NA" rule would have removed Brazil from every year. | `w_total = 0` | Units without pixels are counted (`n_adm1_without_pixels`) and contribute nothing. Other missing units still make the national value NA. |
| B5 | **Country names taken from the first row.** AUS was labelled "Ashmore and Cartier Islands (Aus.)"; ESP, FRA and GBR were also affected. Found by browser checks before publication. | `check_analysis.py` | The most frequent source name per code is used; a test covers it. |
| B6 | **Version bump would break release links.** Release URLs were built from the site version, so v2.1.0 would have linked to a release that does not exist. | `build_v2.write_manifest` | `RELEASE_VERSION` is kept separate. All v2.0.0 checksums and URLs are verified unchanged. |
| B7 | **The economic integration was a merge guide, not an analysis workspace.** | Site | New Economic Analysis page (Modules A–C), with uncertainty, Moran's I and holdout validation. Integration page kept under Data & Downloads (URL unchanged). |
| B8 | **Spatial dependence.** Residuals of country cross-sections are spatially autocorrelated (Moran's I about 0.27, p = 0.001). | `models.json` | Reported next to the estimates. Spatially robust inference is listed as proposed (validation report B5). |
| B9 | **A single IMF vintage** (April 2023) is applied to all years. | — | Documented on the page and in the data; per-vintage classification proposed (validation report B6). |
| B10 | **DOSE overlapping regions.** DOSE keeps some old and new units (e.g. Morocco's pre- and post-2015 regions), so one district can sit in two DOSE regions. | `econ.py` docstring | Documented. Regression samples follow DOSE's own region-years; pooled estimates are clustered by country. |
| B11 | **Restricting public access** was suggested in the feedback. | — | Not done. Source data are public and the derived data are CC BY 4.0. The About page and `DATA_SOURCES.md` separate source, derived data and manuscripts. No exclusivity is claimed. |

## Priorities after 2.1

1. Pixel-level medians and direct extraction to World Bank ADM1 polygons.
2. Confirm the Black Marble collection with the World Bank.
3. Spatially robust inference.
4. Per-vintage IMF groups.
5. NOAA-20/21 continuation after Suomi NPP.
6. Zenodo DOI.

---

# Audit of Night Lights ADM1 v1.1 (2026-11-20)

Scope: repository `ouaretw/nightlights-adm1` at tag `v1.1.0`. It covers the pipeline, the published data, the
crosswalks and the website. Every finding below was checked against the source data with `pipeline/qa/audit_v1.py`
and the scripts in `pipeline/qa/`.

## What v1.1 already did correctly (kept in v2)

- **Strict nesting.** The ADM2 → World Bank ADM1 aggregation is a pure group-by. Every ADM2 has one ADM1 code, with no duplicate rows.
- **Exact sums.** Sums and maxima are exact. Country totals reconcile with the source to ~1e-16.
- **Mean weighting.** The mean is weighted by `sum / mean`, not averaged across districts. This is correct, though v1 documented the reason wrongly (see A2).
- **Medians and percentiles** were already left out at ADM1.
- **Gas-flaring count.** `n_gasflaring_locs` was correctly identified as a national count.
- **Map safety.** Polygons are drawn only on a code and name match, because ADM1 codes have been reused across boundary vintages.
- **GADM crosswalk.** The layered GADM 4.1 crosswalk assigns 97.8% of world light, and unassigned districts are listed.

## Findings and fixes

| # | Finding | Evidence | Effect in v1.1 | Fix in v2 |
|---|---|---|---|---|
| A1 | **No-data encoded as zero.** When a district has no valid pixel, the source stores `ntl_sum = 0` (with `prop_na = 1` and `ntl_mean` missing). | All 45,834 rows with a missing mean have sum = 0 and prop_na = 1. | **6,180 World Bank province-months were published as 0 light instead of missing** (mostly high-latitude summers). | Sums are set to missing whenever no pixel is valid, at ADM2 and ADM1. `has_valid_data` and `n_adm2_no_valid_data` are added. Tested. |
| A2 | **Wrong rationale.** The source weights are fractional coverage weights, so `sum / mean` is not an integer (only 2% of rows are within 0.01 of an integer). v1 called this a "pixel count". | `qa/audit_v1.py` | Wording only. The aggregation was right: `Σ sum / Σ (sum/mean)` is the exact coverage-weighted mean. | Renamed to `w_valid` / `w_total` and documented as an identity. |
| A3 | **Estimated weights not flagged.** When a district is valid but completely dark (mean = sum = 0; 119,298 rows), its weight cannot be recovered and was estimated without any flag. | | 53,589 province-months include some estimated weight. Only means of provinces that mix dark and lit districts are affected; sums never are. | Kept as an explicitly flagged estimate: `w_valid_estimated` (ADM2) and `w_valid_estimated_share` (ADM1). The size of the effect is in the validation report. |
| A4 | **Quality-share denominators.** Shares sum to 1 over all pixels, including missing ones. | Quantiles of the row sums are 1.0. | Correct in v1, which used a static pixel total. | Uses the total weight recovered per row (`w_valid / (1 − prop_na)`), falling back to the static total only when it can't be recovered, and flags that (`w_total_estimated`). |
| A5 | **Annual composite and monthly data not separated.** v1 offered only NASA's annual composite and didn't explain how it differs from monthly data. | | Users could mix them. | `annual` (official composite) and `annual_from_monthly` (derived, with `n_months_with_data`) are now separate products. |
| A6 | **Missing source row.** One row is absent from the source: SJM001001 (Svalbard), 2022-07. | Grid check | No effect on totals. | Documented. The test expects exactly this gap. |
| A7 | **Crosswalk name normaliser over-stripped Slavic endings** ("Cherkas'ka" → "cher"). | `qa/debug_gadm.py` | The Cherkasy and Sumy oblasts were unassigned. | Fixed. Each kind of suffix is now stripped at most once, plus a short-stem rule. 200 countries now have 100% of their light assigned. |
| A8 | **Absorbed GADM units not flagged.** Some GADM units are smaller than the source districts (e.g. Kiev City inside the source's Kyiv oblast), so their light ends up in the neighbouring unit. | `gadm_units_without_data.csv` | A merge with GADM-keyed data would silently compare a city-plus-province total with a province-only GDP figure. | Each absorbed unit's receiving unit is identified by geometry where a located district covers at least 30% of it. Otherwise it's inferred from the neighbouring unit sharing the longest border; `absorption_basis` records which. GADM disputed-zone fragments are never attributed. New columns `xw_absorbs_units` and `gadm_unit_absorbs`; such units can't be graded "high". |
| A9 | **No match grade.** GADM units had no single quality grade. | | Users had to interpret method lists themselves. | `xw_match_quality` (high / medium / low) and `xw_share_adm2_located_directly`. |
| A10 | **ADM2 not published.** v1 had no ADM2 product. | | Users had to fetch the source separately. | Native ADM2 product: source values, corrected no-data, weights, and the GADM parent with its matching method. |
| A11 | **Reproducibility.** Source checksums were not recorded, there were no tests, and the data history lived inside `main`. | | A source revision could go unnoticed. | `build_meta.json` records SHA-256 of the source. Added: `source_lock.json`, a weekly watcher, unit, source-assumption and output tests, versioned releases, and an orphan `gh-pages` branch for data. |
| A12 | **No economic linkage.** There was no link to economic datasets beyond GADM. | | The project's purpose was only half met. | DOSE V2.14 linkage and ready-to-merge panel; US BEA and Brazil IBGE crosswalks; GDL and OECD documented as not available. |

## Limitations that remain (documented, not fixed)

- **Approximate GADM version.** It is a crosswalk, not a raster re-extraction. Districts are assigned whole, so units cut by GADM borders carry some misallocated light. This is graded per unit.
- **Unknown collection.** The source doesn't say which Black Marble collection (C1 or C2) it uses.
- **Series end.** Suomi NPP stopped delivering observations on 2026-11-02, so the source series will end. Continuing it needs NOAA-20 (VJ146), which this source doesn't use.
- **Gas-flare variants** can only be published as sums at ADM1.
- **Validation coverage.** Direct-extraction validation is limited to the 13 countries × 3 years that the World Bank prototype publishes.
