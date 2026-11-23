* Merge DOSE V2.14 regional GDP with NASA Black Marble nighttime lights (Night Lights ADM1 v2)
* Ready-made panel: DOSE rows 2012-2019 already joined with lights on DOSE region IDs.
* Requires: Stata 16+; reghdfe (ssc install reghdfe) for the last step.
* Since v3.0 the site is password-protected: sign in, download the files named below from the
* Economic integration page, and set `base' to the folder where you saved them.

local base "."

* --- Option A: the ready-to-merge panel ---------------------------------------
import delimited "`base'/panel_dose_v2_14_ntl.csv", clear case(preserve) encoding(utf8)

* --- Option B: your own DOSE copy + lights on DOSE regions (2012-2024) ---------
* import delimited "DOSE_V2.14.csv", clear case(preserve) encoding(utf8)
* tempfile dose
* save `dose'
* import delimited "`base'/ntl_for_dose_regions_annual.csv", clear case(preserve) encoding(utf8)
* merge 1:1 GID_1 year using `dose', keep(match)

* Quality screen: linked regions, good pixel coverage, no absorbed GADM units
keep if !inlist(ntl_link_method, "unlinked", "linked_but_no_district")
keep if coverage >= 0.8 & ntl_link_absorbs == ""

gen ln_grp = ln(grp_pc_usd * pop)
gen ln_ntl = ln(ntl_sum)
label var ln_ntl "log Black Marble radiance sum (official annual composite)"

* Descriptive association with region and year fixed effects (not a causal estimate)
reghdfe ln_grp ln_ntl, absorb(GID_1 year) vce(cluster GID_1)
