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
