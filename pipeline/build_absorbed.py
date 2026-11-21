"""Refine 'which GADM unit absorbed the light of a GADM unit with no district'.

Input : build/crosswalks/gadm_units_without_data.csv (from build_gadm.py, with the
        located-district overlap result), raw/gadm/gadm41_adm1.parquet
Rules : absorption_basis =
          district_overlap  a located source district covers >= 30% of the empty unit
          neighbour         otherwise, the same-country GADM unit WITH data that shares the
                            longest border (inference, e.g. Kiev City -> Kiev oblast when
                            the oblast's districts were placed by name, not by outline)
          none              no neighbour with data (islands, disputed fragments)
Output: same CSV, with absorbed_by_GID_1 and absorption_basis rewritten.
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
XW = ROOT / "build" / "crosswalks"
EA = 6933


def main():
    emp = pd.read_csv(XW / "gadm_units_without_data.csv", dtype=str, keep_default_na=False)
    xw = pd.read_csv(XW / "crosswalk_adm2_to_gadm41.csv", dtype=str, keep_default_na=False)
    with_data = set(xw.loc[xw.GID_1 != "", "GID_1"])
    gadm = gpd.read_parquet(ROOT / "raw" / "gadm" / "gadm41_adm1.parquet").drop_duplicates("GID_1").to_crs(EA)
    gadm["geometry"] = gadm.geometry.make_valid()
    g = gadm.set_index("GID_1")
    basis, absorbed = [], []
    for r in emp.itertuples():
        if r.GID_1.startswith("Z") or r.GID_1 in ("?", ""):
            # GADM disputed-zone fragments / placeholders: whether the World Bank
            # source covers them at all is unknown -> never attributed
            basis.append("disputed_or_placeholder"); absorbed.append(""); continue
        cover = float(r.absorbing_district_covers_share) if r.absorbing_district_covers_share else 0.0
        if r.absorbed_by_GID_1 and cover >= 0.3:
            basis.append("district_overlap"); absorbed.append(r.absorbed_by_GID_1); continue
        if r.GID_1 not in g.index or g.loc[r.GID_1].geometry is None:
            basis.append("none"); absorbed.append(""); continue
        geom = g.loc[r.GID_1].geometry
        nb = gadm[(gadm.WB_ISO_A3 == r.WB_ISO_A3) & gadm.GID_1.isin(with_data) & gadm.intersects(geom.buffer(50))]
        if nb.empty:
            basis.append("none"); absorbed.append(""); continue
        shared = nb.geometry.intersection(geom.boundary.buffer(50)).length
        absorbed.append(nb.loc[shared.idxmax(), "GID_1"]); basis.append("neighbour")
    emp["absorbed_by_GID_1"] = absorbed
    emp["absorption_basis"] = basis
    emp.to_csv(XW / "gadm_units_without_data.csv", index=False, encoding="utf-8")
    print(emp.absorption_basis.value_counts().to_dict())
    print(emp[emp.WB_ISO_A3.isin(["UKR", "IND", "KOR", "CHN"])][["GID_1", "NAME_1", "absorbed_by_GID_1", "absorption_basis"]].to_string())


if __name__ == "__main__":
    main()
