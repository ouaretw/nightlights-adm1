"""Re-key the nighttime-lights ADM1 tables to GADM 4.1 ADM1 (GID_1), the
boundary set used by most subnational economic datasets (e.g. DOSE uses GADM).

Each SOURCE ADM2 unit (older WB-GAD vintage) is located, then assigned whole
to the GADM ADM1 unit it overlaps most:

  1 code_name      same ADM2 code and same name in today's WB-GAD ADM2 layer
  2 name           unique name match within the country (ADM1 name agreeing first)
  3 adm1_outline   source ADM1 outline (safe match from build_geo_match) lies
                   >= 90% inside one GADM unit
  4 single_unit    GADM has only one unit for the country
  otherwise        unassigned (light reported as unassigned in QA)

Overlaps are computed in an equal-area projection (EPSG:6933).
Aggregation itself is done by build_v2.py with ntl_core (same exact rules).

Outputs (build/crosswalks/):
  crosswalk_adm2_to_gadm41.csv         one row per source ADM2
  qa_by_country.csv                    assigned light share, empty GADM units
  qa_summary.json
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from build_geo_match import same_name

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
OUT = ROOT / "build" / "crosswalks"
EA = 6933

# Kunrei -> Hepburn (Japan) and common Slavic adjectival endings
_TRANSLIT = [("tyoo", "cho"), ("syuu", "shu"), ("syoo", "sho"), ("ty", "ch"), ("sy", "sh"), ("zy", "j"),
             ("si", "shi"), ("ti", "chi"), ("tu", "tsu"), ("hu", "fu"), ("zi", "ji"), ("oo", "o"), ("uu", "u"),
             ("yy", "i"), ("ky", "ki")]
_ADMIN_WORD = re.compile(r"(oblast|oblysy|oblys|megye|ken|prefecture)$")
_SLAVIC_END = re.compile(r"(skaya|skiy|ska)$")


def _n(s: str) -> str:
    """ASCII letters only; drop one trailing admin word, then one Slavic
    adjectival ending (each at most once, so stems are never over-stripped)."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z]", "", s)
    s = _ADMIN_WORD.sub("", s)
    if len(s) >= 6:
        s = _SLAVIC_END.sub("", s)
    return s


def name_score(a: str, b: str) -> float:
    """Similarity of two place names after transliteration/suffix normalisation."""
    na, nb = _n(a), _n(b)
    if not na or not nb:
        return 0.0
    best = SequenceMatcher(None, na, nb).ratio()
    ta = na
    for x, y in _TRANSLIT:
        ta = ta.replace(x, y)
    best = max(best, SequenceMatcher(None, ta, nb).ratio())
    k = len(os.path.commonprefix([na, nb]))
    if k >= 10 or (k >= 5 and k >= 0.8 * min(len(na), len(nb))):
        best = max(best, 0.9)
    # short stems: the longer name is the shorter plus at most 2 letters (sum|s'ka ~ sumy)
    short, long_ = sorted((na, nb), key=len)
    if len(short) >= 3 and long_.startswith(short) and len(long_) - len(short) <= 2:
        best = max(best, 0.9)
    return best


def sibling_vote(xw: pd.DataFrame) -> pd.DataFrame:
    """Unassigned ADM2 follow their source-ADM1 siblings when >=90% of the
    located siblings (>=2) fall in one GADM unit."""
    done = xw[xw.GID_1.notna() & xw.method.isin(["code_name", "name", "adm1_outline", "adm1_as_current_adm2"])]
    votes = done.groupby(["ADM1CD_c", "GID_1"]).size().rename("n").reset_index()
    tot = votes.groupby("ADM1CD_c").n.transform("sum")
    votes["frac"] = votes.n / tot
    win = votes[(votes.frac >= 0.9) & (tot >= 2)].set_index("ADM1CD_c").GID_1
    sel = xw.GID_1.isna() & xw.ADM1CD_c.isin(win.index)
    xw.loc[sel, "GID_1"] = xw.loc[sel, "ADM1CD_c"].map(win)
    xw.loc[sel, "method"] = "sibling_vote"
    xw.loc[sel, "share"] = np.nan
    return xw


def locate(src: pd.DataFrame, wb2: gpd.GeoDataFrame, wb1: gpd.GeoDataFrame, gm: pd.DataFrame) -> gpd.GeoDataFrame:
    """Attach a geometry + method to each source ADM2."""
    geom, method, ref = {}, {}, {}
    wb2_by_code = wb2.set_index("ADM2CD_c")
    n_cur_adm1 = wb1.groupby("ISO_A3").ADM1CD_c.nunique()
    for iso, sub in src.groupby("ISO_A3"):
        cur = wb2[wb2.ISO_A3 == iso]
        adm1_reorganised = sub.ADM1CD_c.nunique() != n_cur_adm1.get(iso, -1)
        used = set()
        # pass 1: code + name
        for r in sub.itertuples():
            if r.ADM2CD_c in wb2_by_code.index:
                c = wb2_by_code.loc[r.ADM2CD_c]
                if c.ISO_A3 == iso and same_name(r.NAM_2, c.NAM_2):
                    geom[r.ADM2CD_c], method[r.ADM2CD_c] = c.geometry, "code_name"
                    ref[r.ADM2CD_c] = f"ADM2:{r.ADM2CD_c}"
                    used.add(r.ADM2CD_c)
        # pass 2: unique name match (prefer agreeing ADM1 name)
        for r in sub.itertuples():
            if r.ADM2CD_c in geom:
                continue
            pool = cur[~cur.ADM2CD_c.isin(used)]
            if pool.empty:
                continue
            hit = pool[pool.NAM_2.map(lambda n: same_name(r.NAM_2, n)).astype(bool)]
            if hit.empty:
                continue
            agree = hit[hit.NAM_1.map(lambda n: same_name(r.NAM_1, n) or name_score(r.NAM_1, n) >= 0.9).astype(bool)]
            # where the ADM1 tier is unchanged, the province must agree too
            # (avoids e.g. Asahi-cho in Aichi -> Asahi in Chiba)
            hit = agree if (len(agree) or not adm1_reorganised) else hit
            if len(hit) == 1:
                h = hit.iloc[0]
                geom[r.ADM2CD_c], method[r.ADM2CD_c] = h.geometry, "name"
                ref[r.ADM2CD_c] = f"ADM2:{h.ADM2CD_c}"
                used.add(h.ADM2CD_c)
    # pass 2b: the old "ADM1" is today's ADM2 (AZE rayons, LVA novads, UGA
    # districts): find the source ADM1 name among current ADM2 names (unique)
    for (iso, a1), sub in src[~src.ADM2CD_c.isin(geom)].groupby(["ISO_A3", "ADM1CD_c"]):
        cur = wb2[wb2.ISO_A3 == iso]
        if cur.empty:
            continue
        nm = sub.NAM_1.iloc[0]
        hit = cur[cur.NAM_2.map(lambda n: name_score(nm, n) >= 0.92).astype(bool)]
        if len(hit) == 1:
            for code in sub.ADM2CD_c:
                geom[code], method[code] = hit.geometry.iloc[0], "adm1_as_current_adm2"
                ref[code] = f"ADM2:{hit.ADM2CD_c.iloc[0]}"
    # pass 3: source ADM1 outline (only safe, non-approximate matches)
    ok = gm[gm.map_status.isin(["matched_code_name", "matched_name_renumbered"])]
    adm1_geom = wb1.set_index("ADM1CD_c").geometry
    for r in src[~src.ADM2CD_c.isin(geom)].itertuples():
        m = ok[ok.ADM1CD_c == r.ADM1CD_c]
        if len(m) and m.iloc[0].ADM1CD_c_current_boundaries in adm1_geom.index:
            geom[r.ADM2CD_c] = adm1_geom.loc[m.iloc[0].ADM1CD_c_current_boundaries]
            method[r.ADM2CD_c] = "adm1_outline"
            ref[r.ADM2CD_c] = f"ADM1:{m.iloc[0].ADM1CD_c_current_boundaries}"
    g = src.copy()
    g["method"] = g.ADM2CD_c.map(method)
    g["geom_ref"] = g.ADM2CD_c.map(ref)
    g = gpd.GeoDataFrame(g, geometry=g.ADM2CD_c.map(geom), crs=4326)
    return g


def assign(located: gpd.GeoDataFrame, gadm: gpd.GeoDataFrame) -> pd.DataFrame:
    """Largest-overlap GADM unit for each located ADM2, within the same country."""
    rows = []
    loc_ea = located[located.geometry.notna()].to_crs(EA)
    loc_ea["geometry"] = loc_ea.geometry.make_valid()
    gadm_ea = gadm.to_crs(EA)
    gadm_ea["geometry"] = gadm_ea.geometry.make_valid()
    for iso, L in loc_ea.groupby("ISO_A3"):
        G = gadm_ea[gadm_ea.WB_ISO_A3 == iso]
        if G.empty:
            continue
        L = L.assign(_a=L.geometry.area)
        try:
            ov = gpd.overlay(L[["ADM2CD_c", "_a", "geometry"]], G[["GID_1", "geometry"]], how="intersection", keep_geom_type=True)
        except Exception:  # noqa: BLE001 - fall back to buffered geometries
            L2 = L.assign(geometry=L.buffer(0))
            ov = gpd.overlay(L2[["ADM2CD_c", "_a", "geometry"]], G[["GID_1", "geometry"]].assign(geometry=G.buffer(0)),
                             how="intersection", keep_geom_type=True)
        if ov.empty:
            continue
        ov["share"] = ov.geometry.area / ov["_a"]
        best = ov.sort_values("share", ascending=False).drop_duplicates("ADM2CD_c")
        rows.append(best[["ADM2CD_c", "GID_1", "share"]])
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["ADM2CD_c", "GID_1", "share"])
    # cross-border pass: located units with no same-country GADM overlap
    # (e.g. Taiwan is under CHN in WB-GAD but a separate country in GADM)
    weak_same = set(out.loc[out.share < 0.5, "ADM2CD_c"])
    rest = loc_ea[~loc_ea.ADM2CD_c.isin(out.ADM2CD_c) | loc_ea.ADM2CD_c.isin(weak_same)]
    if len(rest):
        rest = rest.assign(_a=rest.geometry.area)
        # only into GADM countries that do not exist separately in the WB data
        wb_isos = set(located.ISO_A3)
        cand = gadm_ea[~gadm_ea.WB_ISO_A3.isin(wb_isos)]
        cand = cand[cand.intersects(rest.union_all())]
        ov = gpd.overlay(rest[["ADM2CD_c", "_a", "geometry"]], cand[["GID_1", "geometry"]], how="intersection", keep_geom_type=True)
        if len(ov):
            ov["share"] = ov.geometry.area / ov["_a"]
            best = ov.sort_values("share", ascending=False).drop_duplicates("ADM2CD_c")
            best = best[best.share >= 0.9]
            out = out[~out.ADM2CD_c.isin(best.ADM2CD_c)]
            out = pd.concat([out, best[["ADM2CD_c", "GID_1", "share"]].assign(cross_border=True)], ignore_index=True)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("loading inputs ...", flush=True)
    m2 = pd.read_parquet(RAW / "ntl_adm2_monthly_all.parquet", columns=["ISO_A3", "NAM_0", "ADM1CD_c", "NAM_1", "ADM2CD_c", "NAM_2"])
    src = m2.drop_duplicates("ADM2CD_c")[["ISO_A3", "NAM_0", "ADM1CD_c", "NAM_1", "ADM2CD_c", "NAM_2"]].reset_index(drop=True)
    wb2 = gpd.read_parquet(RAW / "geo" / "wb_gad_adm2.parquet")
    wb1 = gpd.read_file(RAW / "geo" / "wb_gad_adm1_simplified.geojson")
    gm = pd.read_csv(ROOT / "build" / "crosswalks" / "geo_match_wb_adm1.csv")
    gadm = gpd.read_parquet(RAW / "gadm" / "gadm41_adm1.parquet")
    # GADM files Hong Kong / Macao as units of China; WB has them as territories
    alias = gadm[gadm.GID_1.isin(["CHN.HKG", "CHN.MAC"])].copy()
    alias["WB_ISO_A3"] = alias.GID_1.str[-3:]
    gadm = pd.concat([gadm, alias], ignore_index=True)
    # GADM 4.1 JSON exports drop spaces in names ("MaeHongSon"); restore for display
    for c in ("NAME_1", "COUNTRY"):
        gadm[c] = gadm[c].str.replace(r"(?<=[a-zà-ÿ])(?=[A-ZÀ-Þ])", " ", regex=True)

    print("locating source ADM2 ...", flush=True)
    located = locate(src, wb2, wb1, gm)
    print(located.method.value_counts(dropna=False).to_dict(), flush=True)

    print("overlaying with GADM ...", flush=True)
    best = assign(located, gadm)
    xw = located.drop(columns="geometry").merge(best, on="ADM2CD_c", how="left")
    if "cross_border" in xw:
        xw.loc[xw.cross_border.fillna(False).astype(bool), "method"] = "cross_border"
        xw = xw.drop(columns="cross_border")
    # coarse locations must sit >= 90% in one GADM unit
    weak = xw.method.isin(["adm1_outline", "adm1_as_current_adm2"]) & (xw.share < 0.9)
    xw.loc[weak, ["GID_1", "share"]] = [np.nan, np.nan]
    xw = sibling_vote(xw)
    # source ADM1 name -> GADM NAME_1 / VARNAME_1 (transliteration variants),
    # for ADM2 still unassigned; only where source ADM1 units are not coarser
    # than GADM's (country unit count >= GADM count - 3), unique clear best.
    n_src = src.groupby("ISO_A3").ADM1CD_c.nunique()
    n_gad = gadm.groupby("WB_ISO_A3").GID_1.nunique()
    todo = xw[xw.GID_1.isna()].drop_duplicates("ADM1CD_c")[["ISO_A3", "ADM1CD_c", "NAM_1"]]
    hits = {}
    for r in todo.itertuples():
        if n_src.get(r.ISO_A3, 0) < n_gad.get(r.ISO_A3, 0) - 3:
            continue
        G = gadm[(gadm.WB_ISO_A3 == r.ISO_A3) & (gadm.GID_1 != "?")]
        scores = []
        for gr in G.itertuples():
            names = [gr.NAME_1] + [v for v in str(gr.VARNAME_1 or "").split("|") if v and v != "NA"]
            scores.append((max(name_score(r.NAM_1, n) for n in names), gr.GID_1))
        scores.sort(reverse=True)
        if scores and scores[0][0] >= 0.9 and (len(scores) == 1 or scores[1][0] <= scores[0][0] - 0.05):
            hits[r.ADM1CD_c] = scores[0][1]
    sel = xw.GID_1.isna() & xw.ADM1CD_c.isin(hits)
    xw.loc[sel, "GID_1"] = xw.loc[sel, "ADM1CD_c"].map(hits)
    xw.loc[sel, "method"] = "adm1_name"
    xw.loc[sel, "share"] = np.nan
    # single-unit countries
    one = gadm.groupby("WB_ISO_A3").GID_1.agg(["nunique", "first"])
    single = one[one["nunique"] == 1]["first"]
    fill = xw.GID_1.isna() & xw.ISO_A3.isin(single.index)
    xw.loc[fill, "GID_1"] = xw.loc[fill, "ISO_A3"].map(single)
    xw.loc[fill, "method"] = "single_unit"
    xw.loc[fill, "share"] = 1.0
    xw.loc[xw.GID_1.isna(), "method"] = "unassigned"
    names = gadm.drop_duplicates("GID_1").set_index("GID_1")[["NAME_1", "ENGTYPE_1", "COUNTRY"]]
    xw = xw.join(names, on="GID_1")
    xw = xw.rename(columns={"ADM1CD_c": "WB_ADM1CD_c", "NAM_1": "WB_NAM_1", "share": "overlap_share"})
    xw["overlap_share"] = xw["overlap_share"].round(4)
    xw.to_csv(OUT / "crosswalk_adm2_to_gadm41.csv", index=False, encoding="utf-8")
    print(xw.method.value_counts().to_dict(), flush=True)

    key = xw.set_index("ADM2CD_c")[["GID_1", "NAME_1", "COUNTRY"]]
    a2 = pd.read_csv(RAW / "ntl_adm2_annual.csv", usecols=["ISO_A3", "ADM2CD_c", "year", "ntl_sum"],
                     dtype={"ADM2CD_c": str, "ISO_A3": str})

    # ---- QA: share of each country's light that was assigned, empty GADM units
    tot = a2.groupby("ISO_A3").ntl_sum.sum()
    got = a2.join(key, on="ADM2CD_c").dropna(subset=["GID_1"]).groupby("ISO_A3").ntl_sum.sum()
    qa = pd.DataFrame({"light_assigned_share": (got / tot).reindex(tot.index).fillna(0).round(4)})
    n_g = gadm.groupby("WB_ISO_A3").GID_1.nunique()
    n_hit = xw.dropna(subset=["GID_1"]).groupby("ISO_A3").GID_1.nunique()
    qa["gadm_units"] = n_g.reindex(qa.index).fillna(0).astype(int)
    qa["gadm_units_with_data"] = n_hit.reindex(qa.index).fillna(0).astype(int)
    qa["gadm_units_without_data"] = qa.gadm_units - qa.gadm_units_with_data
    qa["adm2_unassigned"] = xw[xw.method == "unassigned"].groupby("ISO_A3").size().reindex(qa.index).fillna(0).astype(int)
    qa.index.name = "ISO_A3"
    qa.to_csv(OUT / "qa_by_country.csv", encoding="utf-8")
    empty = gadm[~gadm.GID_1.isin(xw.GID_1.dropna())][["WB_ISO_A3", "GID_1", "NAME_1", "ENGTYPE_1", "geometry"]].copy()
    # which GADM unit absorbed each empty unit's light: the unit assigned to the
    # located district covering most of the empty unit's area
    gid_of = xw.set_index("ADM2CD_c").GID_1
    loc = located[located.geometry.notna()].to_crs(EA)
    loc["geometry"] = loc.geometry.make_valid()
    emp = gpd.GeoDataFrame(empty, crs=4326).to_crs(EA)
    emp["geometry"] = emp.geometry.make_valid()
    absorbed_by, cover = [], []
    for r in emp.itertuples():
        L = loc[(loc.ISO_A3 == r.WB_ISO_A3) & loc.intersects(r.geometry)] if r.geometry is not None else loc.iloc[0:0]
        if L.empty or r.geometry.area == 0:
            absorbed_by.append(None); cover.append(None); continue
        a = L.intersection(r.geometry).area
        best = a.idxmax()
        absorbed_by.append(gid_of.get(L.loc[best, "ADM2CD_c"]))
        cover.append(round(float(a.max() / r.geometry.area), 4))
    empty = empty.drop(columns="geometry")
    empty["absorbed_by_GID_1"] = absorbed_by
    empty["absorbing_district_covers_share"] = cover
    empty.to_csv(OUT / "gadm_units_without_data.csv", index=False, encoding="utf-8")

    world_share = float(got.sum() / tot.sum())
    summary = {
        "gadm_version": "4.1", "source_adm2": int(len(xw)),
        "adm2_by_method": xw.method.value_counts().to_dict(),
        "gadm_adm1_units_total": int(gadm.GID_1.nunique()),
        "gadm_adm1_units_with_data": int(xw.GID_1.nunique()),
        "world_light_assigned_share": round(world_share, 5),
        "countries_100pct_assigned": int((qa.light_assigned_share >= 0.9999).sum()),
        "countries_below_95pct": qa.index[qa.light_assigned_share < 0.95].tolist(),
        "adm2_overlap_share_quantiles": xw.overlap_share.quantile([0.01, 0.05, 0.1, 0.5]).round(3).to_dict(),
    }
    (OUT / "qa_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
