"""Single source of truth for the data dictionary (written to CSV/JSON and
rendered on the Documentation page). `products` lists where a column appears:
adm2, adm1_wb, adm1_gadm41; `freq` = m (monthly), a (official annual),
afm (annual from monthly)."""
from __future__ import annotations

import json
from pathlib import Path

ALL1 = ["adm1_wb", "adm1_gadm41"]
ALL = ["adm2", "adm1_wb", "adm1_gadm41"]

COLUMNS = [
    # identifiers
    ("ISO_A3", "id", ALL, "m,a,afm", "", "Country code (World Bank ISO 3166-1 alpha-3 usage).", "source"),
    ("NAM_0", "id", ALL, "m,a,afm", "", "Country name (World Bank).", "source"),
    ("ADM1CD_c", "id", ["adm2", "adm1_wb"], "m,a,afm", "", "World Bank ADM1 code, boundary vintage used by the source table (older than today's WB-GAD; some codes were reused for different units since).", "source"),
    ("NAM_1", "id", ["adm2", "adm1_wb"], "m,a,afm", "", "World Bank ADM1 name. '<country> (no ADM1 tier)' where the source has no ADM1 subdivision.", "source"),
    ("adm1_tier", "id", ["adm1_wb"], "m,a,afm", "", "'adm1' or 'none (country-level unit)'.", "derived"),
    ("ADM2CD_c", "id", ["adm2"], "m,a", "", "World Bank ADM2 code (source vintage).", "source"),
    ("NAM_2", "id", ["adm2"], "m,a", "", "World Bank ADM2 name.", "source"),
    ("GID_1", "id", ["adm1_gadm41"], "m,a,afm", "", "GADM 4.1 ADM1 identifier. Join key for GADM-based economic data.", "crosswalk"),
    ("NAME_1", "id", ["adm1_gadm41"], "m,a,afm", "", "GADM 4.1 ADM1 name (from GADM's JSON export, which drops some spaces; join on GID_1).", "crosswalk"),
    ("GADM41_GID_1", "id", ["adm2"], "m,a", "", "GADM 4.1 ADM1 unit this district is assigned to (empty if unassigned).", "crosswalk"),
    ("GADM41_NAME_1", "id", ["adm2"], "m,a", "", "Name of that GADM unit.", "crosswalk"),
    ("GADM41_xw_method", "qa", ["adm2"], "m,a", "", "How the district was located: code_name, name, adm1_outline, adm1_as_current_adm2, sibling_vote, adm1_name, single_unit, unassigned.", "crosswalk"),
    ("GADM41_xw_overlap", "qa", ["adm2"], "m,a", "share", "Area share of the located district inside the assigned GADM unit (empty for name/vote methods).", "crosswalk"),
    ("date", "time", ALL, "m", "YYYY-MM", "Month of observation.", "source"),
    ("year", "time", ALL, "m,a,afm", "", "Year.", "source"),
    ("month", "time", ALL, "m", "", "Month number (1-12).", "derived"),
    # radiance
    ("ntl_sum", "ntl", ALL, "m,a", "nW·cm⁻²·sr⁻¹ × px", "Sum of radiance over valid pixels (coverage-weighted). NA when no pixel had valid data (the source stores 0 there).", "exact"),
    ("ntl_mean", "ntl", ALL, "m,a", "nW·cm⁻²·sr⁻¹", "Mean radiance over valid pixels. At ADM1: Σ ntl_sum / Σ w_valid (exact coverage-weighted mean).", "exact"),
    ("ntl_max", "ntl", ALL, "m,a", "nW·cm⁻²·sr⁻¹", "Maximum pixel radiance.", "exact"),
    ("ntl_median", "ntl", ["adm2"], "m,a", "nW·cm⁻²·sr⁻¹", "Median pixel radiance. ADM2 only: not aggregable from district summaries.", "source"),
    ("ntl_q05", "ntl", ["adm2"], "m,a", "nW·cm⁻²·sr⁻¹", "5th percentile. ADM2 only.", "source"),
    ("ntl_q95", "ntl", ["adm2"], "m,a", "nW·cm⁻²·sr⁻¹", "95th percentile. ADM2 only.", "source"),
    ("ntl_nogf_5km_sum", "ntl", ALL, "m,a", "nW·cm⁻²·sr⁻¹ × px", "Sum excluding pixels within 5 km of a gas-flaring site.", "exact"),
    ("ntl_nogf_10km_sum", "ntl", ALL, "m,a", "nW·cm⁻²·sr⁻¹ × px", "Sum excluding pixels within 10 km of a gas-flaring site.", "exact"),
    ("ntl_gf_5km_sum", "ntl", ALL, "m,a", "nW·cm⁻²·sr⁻¹ × px", "Sum over pixels within 5 km of a gas-flaring site (ntl_gf + ntl_nogf = ntl_sum).", "exact"),
    ("ntl_gf_10km_sum", "ntl", ALL, "m,a", "nW·cm⁻²·sr⁻¹ × px", "Sum over pixels within 10 km of a gas-flaring site.", "exact"),
    # quality
    ("has_valid_data", "qa", ["adm2"], "m,a", "bool", "False when the source reports no valid pixel (prop_na = 1).", "derived"),
    ("coverage", "qa", ALL1, "m,a", "share", "Valid share of the unit's pixels: Σ w_valid / Σ w_total.", "exact*"),
    ("w_valid", "qa", ALL, "m,a", "px (fractional)", "Coverage-weighted count of valid pixels, recovered as ntl_sum / ntl_mean (exact identity when mean > 0).", "exact*"),
    ("w_total", "qa", ALL, "m,a", "px (fractional)", "Coverage-weighted count of all pixels: w_valid / (1 − prop_na), or the unit's median when not recoverable.", "exact*"),
    ("w_valid_estimated", "qa", ["adm2"], "m,a", "bool", "True when w_valid had to be estimated (valid but completely dark row: mean = sum = 0).", "derived"),
    ("w_total_estimated", "qa", ["adm2"], "m,a", "bool", "True when w_total is the unit's median rather than recovered from the row.", "derived"),
    ("w_valid_estimated_share", "qa", ALL1, "m,a", "share", "Share of the unit's valid weight that is estimated. Non-zero only when dark and lit districts are mixed; ntl_mean is then approximate.", "derived"),
    ("ntl_quality_prop_na", "qa", ALL, "m,a", "share", "Share of pixels with no valid observation.", "exact*"),
    ("ntl_quality_prop_0_good", "qa", ALL, "m,a", "share", "Share of pixels whose composite used more than 3 good-quality nights.", "exact*"),
    ("ntl_quality_prop_1_poor", "qa", ALL, "m,a", "share", "Share of pixels whose composite used 3 or fewer good-quality nights.", "exact*"),
    ("ntl_quality_prop_2_gapfilled", "qa", ALL, "m,a", "share", "Share of pixels gap-filled from earlier data.", "exact*"),
    ("n_adm2", "qa", ALL1, "m,a", "count", "Number of source districts aggregated.", "derived"),
    ("n_adm2_no_valid_data", "qa", ALL1, "m,a", "count", "Districts with no valid pixel in the period.", "derived"),
    ("n_gasflaring_locs_country", "qa", ALL, "m,a", "count", "Gas-flaring locations in the COUNTRY (the source repeats a national count on every row).", "source"),
    # crosswalk quality
    ("xw_n_adm2", "qa", ["adm1_gadm41"], "m,a,afm", "count", "Source districts assigned to this GADM unit.", "crosswalk"),
    ("xw_min_overlap", "qa", ["adm1_gadm41"], "m,a,afm", "share", "Smallest overlap share among its geometrically located districts.", "crosswalk"),
    ("xw_methods", "qa", ["adm1_gadm41"], "m,a,afm", "", "Set of location methods used for its districts.", "crosswalk"),
    ("xw_share_adm2_located_directly", "qa", ["adm1_gadm41"], "m,a,afm", "share", "Share of its districts placed by code/name with own outline (vs coarser methods).", "crosswalk"),
    ("xw_absorbs_units", "qa", ["adm1_gadm41"], "m,a,afm", "", "GADM units with no district of their own whose light is contained in this unit (e.g. Kiev City inside Kiev). Merge them with this unit before comparing with economic data.", "crosswalk"),
    ("xw_match_quality", "qa", ["adm1_gadm41"], "m,a,afm", "", "high = all districts located directly, ≥90% overlap and absorbs no other unit; medium = ≥50% direct; low otherwise.", "crosswalk"),
    # transforms
    ("ln_ntl_sum", "transform", ALL, "m,a", "", "log(ntl_sum); NA when ntl_sum ≤ 0.", "derived"),
    ("asinh_ntl_sum", "transform", ALL, "m,a", "", "Inverse hyperbolic sine of ntl_sum (defined at 0).", "derived"),
    ("ln_ntl_mean", "transform", ALL, "m,a", "", "log(ntl_mean).", "derived"),
    ("asinh_ntl_mean", "transform", ALL, "m,a", "", "asinh(ntl_mean).", "derived"),
    ("ln_ntl_nogf_5km_sum", "transform", ALL, "m,a", "", "log of the flare-excluded sum.", "derived"),
    ("asinh_ntl_nogf_5km_sum", "transform", ALL, "m,a", "", "asinh of the flare-excluded sum.", "derived"),
    ("dln_ntl_sum", "transform", ALL, "a", "", "Year-on-year change in log ntl_sum (consecutive years only).", "derived"),
    ("pct_change_ntl_sum", "transform", ALL, "a", "share", "Year-on-year relative change of ntl_sum.", "derived"),
    ("dln_ntl_nogf_5km_sum", "transform", ALL, "a", "", "Year-on-year change in log flare-excluded sum.", "derived"),
    ("pct_change_ntl_nogf_5km_sum", "transform", ALL, "a", "share", "Year-on-year relative change of flare-excluded sum.", "derived"),
    # annual from monthly
    ("n_months", "afm", ALL1, "afm", "count", "Months present in the year.", "derived"),
    ("n_months_with_data", "afm", ALL1, "afm", "count", "Months with any valid pixel.", "derived"),
    ("ntl_sum_monthly_mean", "afm", ALL1, "afm", "nW·cm⁻²·sr⁻¹ × px", "Average of monthly ntl_sum over months with data. Not the NASA annual composite.", "derived"),
    ("ntl_nogf_5km_sum_monthly_mean", "afm", ALL1, "afm", "nW·cm⁻²·sr⁻¹ × px", "Average monthly flare-excluded sum.", "derived"),
    ("ntl_mean_from_monthly", "afm", ALL1, "afm", "nW·cm⁻²·sr⁻¹", "Σ monthly sums / Σ monthly valid weights.", "derived"),
    ("coverage_monthly_mean", "afm", ALL1, "afm", "share", "Average monthly coverage.", "derived"),
]

FIELDS = ["column", "group", "products", "frequencies", "unit", "description", "status"]
STATUS = {
    "source": "copied from the source table",
    "exact": "exact aggregation of source values",
    "exact*": "exact where the weight is recoverable; flagged when estimated",
    "derived": "computed here from other columns",
    "crosswalk": "depends on the geographic crosswalk (approximate by nature)",
}


def as_records():
    return [dict(zip(FIELDS, (c, g, ",".join(p), f, u, d, s))) for c, g, p, f, u, d, s in COLUMNS]


def write(out_dir: Path):
    import csv
    out_dir.mkdir(parents=True, exist_ok=True)
    recs = as_records()
    with open(out_dir / "data_dictionary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(recs)
    (out_dir / "data_dictionary.json").write_text(
        json.dumps({"status_legend": STATUS, "columns": recs}, indent=1, ensure_ascii=False), encoding="utf-8")
