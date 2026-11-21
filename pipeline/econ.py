"""Economic-data compatibility: link the nighttime-lights districts to the
regions of subnational economic datasets, then aggregate with the same exact
rules (ntl_core). Never relies on names alone without saying so.

DOSE V2.14 (Wenz et al. 2023; Zenodo 20035157; CC BY 4.0)
  DOSE identifies regions with GADM 3.6-style GID_1. Each DOSE region is
  linked to a set of source districts:
    gadm_id        GID_1 exists in GADM 4.1 and the names agree
    gadm_id_suffix GADM 4.1 uses suffix _2 for the same unit (COL, URY)
    gadm_manual    verified renumbering (CHL.13_1 -> CHL.14_1, IDN.15_1 -> IDN.34_1,
                   IND.14_1 -> Z01.14_1); still name-checked
    dose_geometry  region drawn by DOSE itself (DOSE_additional_regions gpkg):
                   districts whose located outline lies >= 50% inside it
    gadm_name      no ID match; unique, near-exact name match within the country (flagged)
    unlinked       none of the above (listed, never guessed)
  A district can belong to more than one DOSE region where DOSE itself keeps
  overlapping old/new units (e.g. Morocco's pre- and post-2015 regions).

US BEA (state GeoFIPS) and Brazil IBGE (UF codes): 1:1 name crosswalks to
GADM 4.1 GID_1, verified by exact normalised name equality.
"""
from __future__ import annotations

import io
import json
import re
import unicodedata
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

import ntl_core as core
from build_gadm import name_score

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
EA = 6933
MANUAL = {"CHL.13_1": "CHL.14_1", "IDN.15_1": "IDN.34_1", "IND.14_1": "Z01.14_1",
          "UKR.12_1": "UKR.11_1"}   # DOSE Kyiv City = GADM 4.1 Kiev City (renumbered)


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def gadm_table():
    g = gpd.read_parquet(RAW / "gadm" / "gadm41_adm1.parquet")
    return g


# Same GID_1, different language/rename - each entry checks that the GADM 4.1
# unit at that ID really is the expected one (normalised GADM NAME_1).
SAME_ID_RENAMED = {   # value = expected prefix of the normalised GADM 4.1 NAME_1
    "MEX.9_1": "distritofederal",          # Ciudad de México = former Distrito Federal
    "BEL.2_1": "vlaanderen", "BEL.3_1": "wallonie",      # Vlaams Gewest, Région wallonne
    "CHE.16_1": "sanktgallen", "IRL.11_1": "laois", "BLR.3_1": "grodno", "KGZ.3_1": "chuy",
    "CHL.8_1": "libertadorgeneralbernardoohi",           # Bernardo O'Higgins
    "CZE.1_1": "jihocesky", "CZE.2_1": "jihomoravsky", "CZE.6_1": "liberecky", "CZE.7_1": "moravskoslezsky",
    "CZE.8_1": "olomoucky", "CZE.10_1": "plzensky", "CZE.13_1": "ustecky", "CZE.14_1": "zlinsky",
    "DEU.14_1": "sachsen", "ESP.13_1": "islasbaleares",
    "HRV.4_1": "gradzagreb", "HRV.19_1": "vukovarskosrijemska",
    "IND.25_1": "nctofdelhi", "IRN.16_1": "kohgiluyeh", "MNG.14_1": "hovsgol", "MNG.20_1": "tov",
    "MOZ.5_1": "maputocity",
    "RUS.2_1": "altay", "RUS.47_1": "nizhegorod", "RUS.55_1": "perm", "RUS.56_1": "primorye",
    "RUS.71_1": "tuva", "RUS.82_1": "yevrey", "RUS.83_1": "zabaykalye",
    "SVN.5_1": "notranjskokraska",         # statistical region renamed Primorsko-notranjska in 2015
    "UKR.4_1": "crimea",
}


def names_agree(a, gname, gvar, gid=None):
    """'yes' / 'unknown' (GADM 4.1 has no name for this ID) / 'no'."""
    if gid in SAME_ID_RENAMED and _norm(gname).startswith(SAME_ID_RENAMED[gid]):
        return "yes"
    if gname is None or str(gname).strip() in ("", "NA"):
        return "unknown"
    names = [gname] + [v for v in str(gvar or "").split("|") if v and v != "NA"]
    if max(name_score(a, n) for n in names) >= 0.85:
        return "yes"
    # containment only for long names (avoids Kiev ~ Kiev City, Maputo ~ Maputo City)
    na = _norm(a)
    for n in names:
        nn = _norm(n)
        short, long_ = sorted((na, nn), key=len)
        if len(short) >= 8 and short in long_:
            return "yes"
    return "no"


def located_geometries(xw: pd.DataFrame) -> gpd.GeoDataFrame:
    """Rebuild each district's located outline from its geometry reference."""
    wb2 = gpd.read_parquet(RAW / "geo" / "wb_gad_adm2.parquet").set_index("ADM2CD_c").geometry
    wb1 = gpd.read_file(RAW / "geo" / "wb_gad_adm1_simplified.geojson").set_index("ADM1CD_c").geometry
    rows = []
    for r in xw.dropna(subset=["geom_ref"]).itertuples():
        lvl, code = r.geom_ref.split(":", 1)
        geom = (wb2 if lvl == "ADM2" else wb1).get(code)
        if geom is not None:
            rows.append((r.ADM2CD_c, r.ISO_A3, lvl, geom))
    return gpd.GeoDataFrame(rows, columns=["ADM2CD_c", "ISO_A3", "ref_level", "geometry"], crs=4326)


def link_dose(xw: pd.DataFrame):
    dose = pd.read_csv(RAW / "econ" / "dose" / "DOSE_V2.14.csv", low_memory=False)
    regions = (dose.dropna(subset=["GID_1"]).groupby(["GID_0", "GID_1"])
               .agg(region=("region", "first"), country=("country", "first"),
                    first_year=("year", "min"), last_year=("year", "max")).reset_index())
    gadm = gadm_table().drop_duplicates("GID_1").set_index("GID_1")
    custom = gpd.read_file(RAW / "econ" / "dose" / "DOSE_additional_regions_V2_14.gpkg")
    custom_ids = set(custom.GID_1)
    x = xw.copy()
    members, links = [], []

    def add(dose_id, adm2_codes, method, detail=""):
        for c in adm2_codes:
            members.append((dose_id, c, method))
        links.append({"DOSE_GID_1": dose_id, "link_method": method, "detail": detail, "n_adm2": len(adm2_codes)})

    by_gid = x.dropna(subset=["GID_1"]).groupby("GID_1").ADM2CD_c.apply(list).to_dict()
    for r in regions.itertuples():
        gid = r.GID_1
        if gid in custom_ids:
            continue            # handled by geometry below
        cand = [(gid, "gadm_id"), (gid[:-2] + "_2" if gid.endswith("_1") else None, "gadm_id_suffix"),
                (MANUAL.get(gid), "gadm_manual")]
        done = False
        for g41, how in cand:
            if not g41 or g41 not in gadm.index:
                continue
            agree = names_agree(r.region, gadm.loc[g41, "NAME_1"], gadm.loc[g41, "VARNAME_1"], g41)
            if how == "gadm_manual":           # researched renumbering; recorded as such
                agree = "yes" if agree != "no" else "manual"
            if agree in ("yes", "manual"):
                add(gid, by_gid.get(g41, []), how, g41)
                done = True
                break
            if agree == "unknown" and how == "gadm_id":   # GADM 4.1 lacks a name at this ID
                add(gid, by_gid.get(g41, []), "gadm_id_name_missing", g41)
                done = True
                break
        if done:
            continue
        # unique near-exact name match within the country
        G = gadm[gadm.GID_0 == r.GID_0]
        sc = sorted(((max(name_score(r.region, n) for n in [row.NAME_1] + [v for v in str(row.VARNAME_1 or "").split("|") if v and v != "NA"]), g)
                     for g, row in G.iterrows()), reverse=True)
        if sc and sc[0][0] >= 0.92 and (len(sc) == 1 or sc[1][0] <= sc[0][0] - 0.05):
            add(gid, by_gid.get(sc[0][1], []), "gadm_name", sc[0][1])
        else:
            links.append({"DOSE_GID_1": gid, "link_method": "unlinked",
                          "detail": f"GID {gid} not in GADM 4.1 with agreeing name", "n_adm2": 0})

    # DOSE's own geometry: overlay located district outlines
    loc = located_geometries(x)
    loc_ea = loc.to_crs(EA)
    loc_ea["geometry"] = loc_ea.geometry.make_valid()
    loc_ea["_a"] = loc_ea.area
    cust = custom[custom.GID_1.isin(regions.GID_1)].to_crs(EA)
    cust["geometry"] = cust.geometry.make_valid()
    for r in cust.itertuples():
        L = loc_ea[loc_ea.ISO_A3 == r.GID_0]
        L = L[L.intersects(r.geometry)]
        if L.empty:
            links.append({"DOSE_GID_1": r.GID_1, "link_method": "unlinked", "detail": "no located district inside DOSE polygon", "n_adm2": 0})
            continue
        share = L.intersection(r.geometry).area / L["_a"]
        inside = L.loc[share >= 0.5]
        # coarse ADM1-level references can only be trusted when they sit almost fully inside
        inside = inside[(inside.ref_level == "ADM2") | (share.loc[inside.index] >= 0.9)]
        add(r.GID_1, inside.ADM2CD_c.tolist(), "dose_geometry", f"{len(inside)} districts >=50% inside")
    mem = pd.DataFrame(members, columns=["DOSE_GID_1", "ADM2CD_c", "link_method"]).drop_duplicates()
    lk = pd.DataFrame(links).merge(regions.rename(columns={"GID_1": "DOSE_GID_1"}), on="DOSE_GID_1", how="right")
    lk["link_method"] = lk["link_method"].fillna("unlinked")
    # a linked GADM unit may also contain the light of smaller GADM units that got no district
    emp = pd.read_csv(ROOT / "build" / "crosswalks" / "gadm_units_without_data.csv", dtype=str, keep_default_na=False)
    emp = emp[(emp.absorbed_by_GID_1 != "") & (emp.GID_1 != "")]
    absorbs = emp.groupby("absorbed_by_GID_1").GID_1.agg(";".join)
    lk["gadm_unit_absorbs"] = np.where(lk.link_method.str.startswith("gadm"), lk.detail.map(absorbs), np.nan)
    lk["gadm_unit_absorbs"] = lk["gadm_unit_absorbs"].fillna("")
    lk.loc[(lk.link_method != "unlinked") & (lk.n_adm2 == 0), "link_method"] = "linked_but_no_district"
    return dose, regions, mem, lk


def aggregate_dose(pa: pd.DataFrame, mem: pd.DataFrame, lk: pd.DataFrame, xw: pd.DataFrame) -> pd.DataFrame:
    d = pa.merge(mem[["DOSE_GID_1", "ADM2CD_c"]], on="ADM2CD_c", how="inner")
    out = core.aggregate(d, ["DOSE_GID_1"], "year")
    out = core.add_transforms(out, ["DOSE_GID_1"], "year", annual=True)
    # link quality: share of member districts located directly (code/name with own outline)
    direct = xw.set_index("ADM2CD_c").method.isin(["code_name", "name"])
    q = mem.assign(direct=mem.ADM2CD_c.map(direct)).groupby("DOSE_GID_1").direct.mean().rename("share_adm2_located_directly")
    meta = lk.set_index("DOSE_GID_1")[["GID_0", "region", "link_method", "detail", "gadm_unit_absorbs"]]
    out = out.join(meta, on="DOSE_GID_1").join(q, on="DOSE_GID_1")
    lead = ["GID_0", "DOSE_GID_1", "region", "link_method", "detail", "gadm_unit_absorbs",
            "share_adm2_located_directly", "year"]
    return core.round_output(out[lead + [c for c in out.columns if c not in lead]])


def build_dose(pa, xw, out_dir: Path, rel_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    dose, regions, mem, lk = link_dose(xw)
    ntl = aggregate_dose(pa, mem, lk, xw)
    ntl = ntl.rename(columns={"DOSE_GID_1": "GID_1"})
    # ready-to-merge panel: DOSE rows for the overlapping years, left-joined with lights
    keep_dose = ["country", "region", "GID_0", "GID_1", "year", "pop", "grp_pc_usd", "grp_pc_usd_2015",
                 "grp_pc_lcu2015_usd", "grp_pc_lcu", "ag_grp_pc_usd", "man_grp_pc_usd", "serv_grp_pc_usd", "version"]
    dsub = dose[keep_dose][dose.year >= 2012]
    lights = ntl.drop(columns=["GID_0", "region"]).rename(columns={"link_method": "ntl_link_method", "detail": "ntl_link_detail",
                                                                   "gadm_unit_absorbs": "ntl_link_absorbs"})
    panel = dsub.merge(lights, on=["GID_1", "year"], how="left")
    lk.to_csv(out_dir / "dose_region_links.csv", index=False, encoding="utf-8")
    mem.to_csv(out_dir / "dose_region_members_adm2.csv", index=False, encoding="utf-8")
    for name, d in (("ntl_for_dose_regions_annual", ntl), ("panel_dose_v2_14_ntl", panel)):
        d.to_parquet(out_dir / f"{name}.parquet", index=False, compression="snappy")
        d.to_csv(out_dir / f"{name}.csv", index=False, encoding="utf-8")
        s = d.copy()
        for c in s.columns:
            if s[c].dtype == object:
                s[c] = s[c].fillna("").astype(str)
        tmp = out_dir / f"{name}.dta"
        s.to_stata(tmp, write_index=False, version=118)
    summary = {
        "dose_version": "V2.14 (Zenodo 20035157)",
        "dose_regions": int(len(regions)),
        "dose_regions_by_link_method": lk.link_method.value_counts().to_dict(),
        "panel_rows_2012_on": int(len(panel)),
        "panel_rows_with_lights": int(panel.ntl_sum.notna().sum()),
        "panel_years": [int(panel.year.min()), int(panel.year.max())],
    }
    (out_dir / "dose_link_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def build_national(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    gadm = gadm_table()
    res = {}
    # US BEA states
    z = zipfile.ZipFile(RAW / "econ" / "bea" / "SAGDP.zip")
    f = [n for n in z.namelist() if n.startswith("SAGDP1__ALL_AREAS")][0]
    bea = pd.read_csv(z.open(f), encoding="latin-1", dtype=str, usecols=["GeoFIPS", "GeoName"]).drop_duplicates()
    bea["GeoFIPS"] = bea.GeoFIPS.str.strip().str.strip('"')
    bea = bea[bea.GeoFIPS.fillna("").str.match(r"^\d{2}000$")]
    bea = bea[(bea.GeoFIPS != "00000") & (bea.GeoFIPS.astype(int) < 90000)]      # states + DC only
    us = gadm[gadm.WB_ISO_A3 == "USA"][["GID_1", "NAME_1"]].assign(k=lambda d: d.NAME_1.map(_norm))
    bea = bea.assign(k=bea.GeoName.str.replace("*", "", regex=False).map(_norm))
    m = bea.merge(us, on="k", how="outer", indicator=True)
    m["match"] = m._merge.map({"both": "exact_name", "left_only": "bea_only", "right_only": "gadm_only"})
    m[["GID_1", "NAME_1", "GeoFIPS", "GeoName", "match"]].to_csv(out_dir / "crosswalk_gadm41_usa_bea_fips.csv", index=False, encoding="utf-8")
    res["usa_bea"] = m.match.value_counts().to_dict()
    # Brazil IBGE UF
    uf = pd.DataFrame(json.loads((RAW / "econ" / "ibge" / "estados.json").read_text(encoding="utf-8")))
    uf = uf.assign(k=uf.nome.map(_norm))[["id", "sigla", "nome", "k"]]
    br = gadm[gadm.WB_ISO_A3 == "BRA"][["GID_1", "NAME_1"]].assign(k=lambda d: d.NAME_1.map(_norm))
    m = uf.merge(br, on="k", how="outer", indicator=True)
    m["match"] = m._merge.map({"both": "exact_name", "left_only": "ibge_only", "right_only": "gadm_only"})
    m = m.rename(columns={"id": "IBGE_UF_code", "sigla": "UF", "nome": "IBGE_name"})
    m[["GID_1", "NAME_1", "IBGE_UF_code", "UF", "IBGE_name", "match"]].to_csv(out_dir / "crosswalk_gadm41_bra_ibge_uf.csv", index=False, encoding="utf-8")
    res["bra_ibge"] = m.match.value_counts().to_dict()
    (out_dir / "national_crosswalks_summary.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    return res
