# Merge DOSE V2.14 regional GDP with NASA Black Marble nighttime lights (Night Lights ADM1 v2)
# install.packages(c("arrow", "dplyr", "fixest"))
library(arrow)
library(dplyr)

# Since v3.0 the site is password-protected: sign in, download the files named below from the
# Economic integration page, and set base to the folder where you saved them.
base <- "."

# Ready-made panel (DOSE rows 2012-2019 joined with lights on DOSE region IDs)
panel <- read_parquet(file.path(base, "panel_dose_v2_14_ntl.parquet"))

# Or: lights on DOSE regions, 2012-2024, to join with your own DOSE copy
# ntl  <- read_parquet(file.path(base, "ntl_for_dose_regions_annual.parquet"))
# dose <- read.csv("DOSE_V2.14.csv")
# panel <- inner_join(dose, ntl, by = c("GID_1", "year"))

est <- panel |>
  filter(!ntl_link_method %in% c("unlinked", "linked_but_no_district"),
         coverage >= 0.8, ntl_link_absorbs == "",
         ntl_sum > 0, grp_pc_usd > 0) |>
  mutate(ln_grp = log(grp_pc_usd * pop), ln_ntl = log(ntl_sum))

# Descriptive association with region and year fixed effects (not causal)
fixest::feols(ln_grp ~ ln_ntl | GID_1 + year, data = est, cluster = ~GID_1)

# Any GADM 4.1-keyed dataset: join on GID_1 + year
gadm <- read_parquet(file.path(base, "adm1_gadm41_annual_global.parquet"))
