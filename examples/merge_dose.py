"""Merge DOSE V2.14 regional GDP with NASA Black Marble nighttime lights (Night Lights ADM1 v2).
pip install pandas pyarrow linearmodels
"""
import numpy as np
import pandas as pd

BASE = "https://ouaretw.github.io/nightlights-adm1/data/v2"

# Ready-made panel: DOSE rows 2012-2019 joined with lights on DOSE region IDs
panel = pd.read_parquet(f"{BASE}/econ/dose/panel_dose_v2_14_ntl.parquet")

# Or: lights on DOSE regions (2012-2024) joined with your own DOSE copy
# ntl = pd.read_parquet(f"{BASE}/econ/dose/ntl_for_dose_regions_annual.parquet")
# panel = pd.read_csv("DOSE_V2.14.csv").merge(ntl, on=["GID_1", "year"], how="inner")

est = panel[
    ~panel.ntl_link_method.isin(["unlinked", "linked_but_no_district"])
    & (panel.coverage >= 0.8)
    & (panel.ntl_link_absorbs.fillna("") == "")
    & (panel.ntl_sum > 0) & (panel.grp_pc_usd > 0)
].assign(ln_grp=lambda d: np.log(d.grp_pc_usd * d["pop"]), ln_ntl=lambda d: np.log(d.ntl_sum))

# Descriptive association with region and year fixed effects (not causal)
from linearmodels.panel import PanelOLS  # noqa: E402

m = PanelOLS.from_formula("ln_grp ~ ln_ntl + EntityEffects + TimeEffects", est.set_index(["GID_1", "year"]))
print(m.fit(cov_type="clustered", cluster_entity=True))

# Any GADM 4.1-keyed dataset: join on GID_1 + year
gadm = pd.read_parquet(f"{BASE}/adm1_gadm41/adm1_gadm41_annual_global.parquet")
