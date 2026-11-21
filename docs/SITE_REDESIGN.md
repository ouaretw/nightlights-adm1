# Portal redesign — "Scientific Cartography" (2026-11-21)

Presentation-only change. No dataset, calculation, crosswalk, validation rule or release file was
modified; the manifest, SHA-256 checksums, release URLs and per-file paths are unchanged. The only
pipeline change is that the display copy of the home-page map data
(`build/site/data/geo/world_adm1_values.json`, written by `pipeline/build_world_map.py`) now also
carries each unit's annual valid-pixel coverage for the tooltip.

## What changed

| Area | Before | After |
|---|---|---|
| Design system | Navy/blue, dark hero, dark map panel | Light palette (#F8FAFC / #11263B / #197D91 / #E5AD4E / #DCE6ED), IBM Plex Sans + Mono, Source Serif 4 for prose; tokens and reusable components in `site_src/assets/css/site.css` |
| Home | Long introduction, dark map | Headline, two actions, large light world ADM1 map (real data), coverage strip, three workflows, attribution + citation + concise limitations |
| Maps | Continuous log ramp; missing and filtered both grey | Shared module `carto.js`: 7 labelled quantile classes with limits fixed across periods; explicit swatches for observed zero, no valid observation, excluded by quality filter, area without a unit outline, non-determined legal status; zoom/pan/reset buttons (Ctrl/⌘ + wheel); country search and zoom on the home map |
| Explorer | Flat control list; selection list below | Primary filters (country, level, boundary system, period, indicator) + collapsible *Advanced* (frequency, time window, coverage threshold, estimated-weight and all-districts exclusions, GADM grade) + *Export*; collapsible filters on mobile; region details panel (value, unit, coverage, quality flags, crosswalk grade, change vs previous official composite, mini time series, region CSV); comparison chips; units without outlines listed under the map; keyboard selection from the table |
| Charts | No axis titles; values to 3 significant digits | Axis titles with units and frequency; exact (6 significant digits) tooltips; markers for isolated points; hollow markers for values excluded by filters; "Export view data (CSV)" on every view |
| Annual change | Δ log only | Interval shown (y−1 → y); Δ log / absolute / percent; base variable choice; counts of units omitted for missing years, zero base (percent undefined) or zero light (log undefined); official annual composites only |
| Download | Long tables | Picker (level → frequency → scope → format) resolving to files in `manifest.json`, with exact size in bytes, host, SHA-256, absolute URL, coverage, key, caveats and variable list; real alternatives when a combination is not published; full catalogue kept under "All files" |
| Integration | One table | DOSE featured (recommended file, geography and join key, linkage meter and method table, panel in CSV/Parquet/Stata), copy/download merge code, other built integrations, planned/unsupported table |
| Methods / Docs | — | New "Boundaries, crosswalk and map outlines" section (`methods.html#outlines`); BibTeX + copy buttons; on-page navigation; CITATION.cff version 2.0.0 |

## Bugs fixed along the way

* Explorer "full files" links pointed to per-country monthly CSVs that are not published (404). Links are now built from the manifest only.
* Years were displayed with a thousands separator ("2,012") in the table (also present before the redesign).
* A period with no valid pixel was labelled "excluded by filter"; missing now takes precedence.
* When the chosen month had no valid data anywhere, no default regions were selected.

## Verification (executed 2026-11-21 against `build/site` served locally)

* `pytest tests` — 34 passed.
* `tests/browser/check_explorer.py` — 47/47: map load, click-to-select/focus, region details, zoom, all seven views,
  CSV exports (filtered rows, view data, region), period/indicator/filters, observed zero (AFG006, 2018), missing month
  (Norway, 2024-06), GADM no-map state and crosswalk fields, boundary switching, ADM2, annual-from-monthly, unit-without-outline
  list, keyboard selection.
* `tests/browser/check_pages.py` — 37/37: home map tooltip/indicator/year/country zoom/deep link; download picker over all 54
  combinations (40 resolve to one file, the rest show real alternatives; every local link HEAD 200); internal links on all six
  pages; no horizontal overflow at 1440, 1024, 768 and 390 px; mobile filter and navigation toggles; no JavaScript errors.
* All 22 GitHub release/repository links return HTTP 200.
* Values: explorer tables for DZA (WB annual), BRA (GADM annual), KEN (ADM2 annual) and NOR (WB monthly) compared with the
  pre-redesign tables and with the Parquet files: identical rows and missing cells; new display within 5×10⁻⁶ of the
  Parquet values; old display within 0.5% (it rounded to 3 significant digits).

## Unresolved / known issues

* Map units are not individually keyboard-focusable; keyboard users select regions from the table view or the country box.
* Some GADM 4.1 names lack spaces as published in the source data (e.g. "Riode Janeiro"); left unchanged because this is data.
* Map outlines exist for 3,195 of 3,587 World Bank ADM1 units; GADM units have no map (licence).
* The explorer does not react to manual edits of the URL hash after load (reload the page).
