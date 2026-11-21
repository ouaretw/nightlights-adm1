"""Build release v2 data products from the raw Space2Stats ADM2 tables.

Products (build/site/data/v2/ unless noted):
  adm2/        native ADM2 observations (source values; no-data sums -> NA),
               with WB parent ADM1 and GADM 4.1 parent (crosswalk) columns
  adm1_wb/     exact aggregation to the source's World Bank ADM1 units
  adm1_gadm41/ aggregation to GADM 4.1 ADM1 via the ADM2 crosswalk
each with  monthly / annual (official NASA annual composite) /
           annual_from_monthly (derived; kept separate from the composite)

Formats: per-country Parquet (snappy, browser-readable) + CSV on the site;
global Parquet + CSV.gz on the site when small enough; Stata .dta and
large bundles in build/release/ (GitHub Release assets).
A manifest with size + sha256 of every file is written for the website.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ntl_core as core  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
SITE = ROOT / "build" / "site"
DATA = SITE / "data" / "v2"
REL = ROOT / "build" / "release"
XW = ROOT / "build" / "crosswalks"
VERSION = "2.0.0"
PAGES_MAX = 95e6          # keep single files below GitHub's 100 MB limit


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load():
    print("loading raw ...", flush=True)
    m = pd.read_parquet(RAW / "ntl_adm2_monthly_all.parquet", columns=core.SOURCE_COLS + ["date"])
    m["date"] = pd.to_datetime(m["date"]).dt.strftime("%Y-%m")
    a = pd.read_csv(RAW / "ntl_adm2_annual.csv", usecols=lambda c: c in set(core.SOURCE_COLS + ["year"]),
                    dtype={"ADM1CD_c": str, "ADM2CD_c": str, "ISO_A3": str})
    return m, a


def adm1_names(m: pd.DataFrame) -> pd.DataFrame:
    n = m.drop_duplicates("ADM1CD_c").set_index("ADM1CD_c")[["NAM_0", "NAM_1"]].copy()
    na = n.NAM_1.str.contains("not available", case=False, na=False)
    n["adm1_tier"] = np.where(na, "none (country-level unit)", "adm1")
    n.loc[na, "NAM_1"] = n.loc[na, "NAM_0"] + " (no ADM1 tier)"
    return n


def finish_time(df: pd.DataFrame, time_col: str) -> pd.DataFrame:
    if time_col == "date":
        df.insert(df.columns.get_loc("date") + 1, "year", df["date"].str[:4].astype(int))
        df.insert(df.columns.get_loc("year") + 1, "month", df["date"].str[5:7].astype(int))
    return df


ADM1_ORDER = ["ntl_sum", "ntl_mean", "ntl_max", "ntl_nogf_5km_sum", "ntl_nogf_10km_sum", "ntl_gf_5km_sum",
              "ntl_gf_10km_sum", "coverage", "w_valid", "w_total", "w_valid_estimated_share", *core.Q_VARS,
              "n_adm2", "n_adm2_no_valid_data", "n_gasflaring_locs_country"]


def build_adm1(prep_m, prep_a, key_cols, name_df, label, extra=None):
    keys = ["ISO_A3"] + key_cols
    out = {}
    m1 = core.aggregate(prep_m, keys, "date")
    a1 = core.aggregate(prep_a, keys, "year")
    out["_recon_monthly_country_sum"] = m1.groupby("ISO_A3").ntl_sum.sum()   # before rounding
    afm = core.annual_from_monthly(m1, keys)
    m1 = core.add_transforms(m1, keys, "date", annual=False)
    a1 = core.add_transforms(a1, keys, "year", annual=True)
    for name, d, t in (("monthly", m1, "date"), ("annual", a1, "year"), ("annual_from_monthly", afm, "year")):
        d = d.join(name_df, on=key_cols[0])
        if extra is not None:
            d = d.join(extra, on=key_cols[0])
        lead = ["ISO_A3", "NAM_0" if "NAM_0" in d else "COUNTRY"] + key_cols + [c for c in name_df.columns if c not in ("NAM_0",)]
        lead = [c for c in dict.fromkeys(lead) if c in d.columns]
        rest = [c for c in d.columns if c not in lead and c != t]
        if name != "annual_from_monthly":
            rest = [c for c in ADM1_ORDER if c in rest] + [c for c in rest if c not in ADM1_ORDER]
        d = finish_time(core.round_output(d[lead + [t] + rest]), t)
        out[name] = d
    recon_sum = out.pop("_recon_monthly_country_sum")
    out = {"_recon": recon_sum, **out}
    print(f"  {label}: monthly {len(out['monthly']):,}  annual {len(out['annual']):,}  "
          f"annual_from_monthly {len(out['annual_from_monthly']):,}", flush=True)
    return out


def write_product(tables: dict, sub: str, manifest: list, dta: bool = True, float32: bool = False):
    """Site: per-country Parquet (snappy, read by the explorer) for everything;
    per-country CSV only where small (ADM1 annual files); otherwise per-country
    CSV is produced by the explorer from the Parquet, and bundled in the release."""
    REL.mkdir(parents=True, exist_ok=True)
    for freq, d in tables.items():
        if float32:     # source values are float32; storing them as float32 loses nothing
            d = d.astype({c: "float32" for c in d.columns if d[c].dtype == "float64"})
        base = DATA / sub / freq
        base.mkdir(parents=True, exist_ok=True)
        site_csv = sub != "adm2" and freq != "monthly"
        zip_csv = sub != "adm2" and freq == "monthly"
        zf = zipfile.ZipFile(REL / f"{sub}_{freq}_by_country_csv.zip", "w", zipfile.ZIP_DEFLATED) if zip_csv else None
        for iso, g in d.groupby("ISO_A3"):
            g.to_parquet(base / f"{iso}.parquet", index=False, compression="snappy")
            if site_csv:
                g.to_csv(base / f"{iso}.csv", index=False, encoding="utf-8")
            if zf:
                zf.writestr(f"{sub}_{freq}_{iso}.csv", g.to_csv(index=False))
        if zf:
            zf.close()
        gp = DATA / sub / f"{sub}_{freq}_global.parquet"
        d.to_parquet(gp, index=False, compression="zstd")
        gc = DATA / sub / f"{sub}_{freq}_global.csv.gz"
        d.to_csv(gc, index=False, compression="gzip", encoding="utf-8")
        for p in (gp, gc):
            if p.stat().st_size > PAGES_MAX:          # too big for Pages -> release asset
                shutil.move(str(p), REL / p.name)
        if dta and (sub != "adm2" or freq == "annual"):
            REL.mkdir(parents=True, exist_ok=True)
            tmp = REL / f"{sub}_{freq}_global.dta"
            s = d.copy()
            for c in s.columns:
                if s[c].dtype == object:
                    s[c] = s[c].fillna("").astype(str)
                elif s[c].dtype == bool:
                    s[c] = s[c].astype("int8")
            s.to_stata(tmp, write_index=False, version=118, convert_strl=[])
            with zipfile.ZipFile(REL / f"{sub}_{freq}_global.dta.zip", "w", zipfile.ZIP_DEFLATED) as z:
                z.write(tmp, tmp.name)
            tmp.unlink()


def main():
    if DATA.exists():
        shutil.rmtree(DATA)
    if REL.exists():
        shutil.rmtree(REL)
    DATA.mkdir(parents=True)
    m, a = load()
    T = core.total_weights(m)
    print(f"total weights recovered for {len(T):,} / {m.ADM2CD_c.nunique():,} ADM2", flush=True)
    pm, pa = core.prepare_adm2(m, T), core.prepare_adm2(a, T)

    xw = pd.read_csv(XW / "crosswalk_adm2_to_gadm41.csv", dtype=str)
    xw["overlap_share"] = pd.to_numeric(xw["overlap_share"])
    gmap = xw.set_index("ADM2CD_c")[["GID_1", "NAME_1", "method", "overlap_share"]]

    # ---------------- ADM1, World Bank units (exact, no crosswalk)
    names = adm1_names(m)
    wb = build_adm1(pm, pa, ["ADM1CD_c"], names, "adm1_wb")

    # ---------------- ADM1, GADM 4.1 (crosswalk)
    def rekey(p):
        d = p.join(gmap[["GID_1"]], on="ADM2CD_c")
        return d[d.GID_1.notna()]
    direct = {"code_name", "name", "single_unit"}
    q = xw[xw.GID_1.notna()].groupby("GID_1").agg(
        NAME_1=("NAME_1", "first"),
        xw_n_adm2=("ADM2CD_c", "size"),
        xw_min_overlap=("overlap_share", "min"),
        xw_methods=("method", lambda s: ";".join(sorted(set(s)))),
        xw_share_adm2_located_directly=("method", lambda s: round(float(s.isin(direct).mean()), 4)),
    )
    emp = pd.read_csv(XW / "gadm_units_without_data.csv", dtype=str, keep_default_na=False)
    emp = emp[(emp.absorbed_by_GID_1 != "") & (emp.GID_1 != "")]
    absorbs = emp.groupby("absorbed_by_GID_1").GID_1.agg(";".join)
    q["xw_absorbs_units"] = q.index.map(absorbs).fillna("")
    q["xw_match_quality"] = np.where((q.xw_share_adm2_located_directly == 1) & (q.xw_min_overlap.fillna(1) >= 0.9)
                                     & (q.xw_absorbs_units == ""),
                                     "high", np.where(q.xw_share_adm2_located_directly >= 0.5, "medium", "low"))
    cn = m.drop_duplicates("ISO_A3").set_index("ISO_A3")["NAM_0"]
    gname = q[["NAME_1"]]
    gq = q.drop(columns="NAME_1")
    gadm = build_adm1(rekey(pm), rekey(pa), ["GID_1"], gname, "adm1_gadm41", extra=gq)
    recon_sums = {"adm1_wb": wb.pop("_recon"), "adm1_gadm41": gadm.pop("_recon")}
    for d in gadm.values():
        d.insert(1, "NAM_0", d["ISO_A3"].map(cn))

    # ---------------- ADM2 native
    def adm2_table(p, t, annual):
        d = p.join(gmap.rename(columns={"GID_1": "GADM41_GID_1", "NAME_1": "GADM41_NAME_1",
                                        "method": "GADM41_xw_method", "overlap_share": "GADM41_xw_overlap"}),
                   on="ADM2CD_c")
        d = d.rename(columns={"n_gasflaring_locs": "n_gasflaring_locs_country"})
        d = core.add_transforms(d, ["ADM2CD_c"], t, annual=annual)
        lead = core.ID_VARS + ["GADM41_GID_1", "GADM41_NAME_1", "GADM41_xw_method", "GADM41_xw_overlap", t]
        body = ["has_valid_data", "ntl_sum", "ntl_mean", "ntl_median", "ntl_max", "ntl_q05", "ntl_q95",
                "ntl_nogf_5km_sum", "ntl_nogf_10km_sum", "ntl_gf_5km_sum", "ntl_gf_10km_sum",
                *core.Q_VARS, "w_valid", "w_valid_estimated", "w_total", "w_total_estimated",
                "n_gasflaring_locs_country"]
        # transforms only in the annual ADM2 file (monthly: users derive them; keeps the files small)
        rest = [c for c in d.columns if c.startswith(("ln_", "asinh_", "dln_", "pct_change"))] if annual else []
        return finish_time(core.round_output(d[lead + body + rest].sort_values(["ADM2CD_c", t])), t)
    adm2 = {"monthly": adm2_table(pm, "date", False), "annual": adm2_table(pa, "year", True)}
    print(f"  adm2: monthly {len(adm2['monthly']):,}  annual {len(adm2['annual']):,}", flush=True)

    # ---------------- reconciliation (arithmetic checks recorded with the release)
    recon = {}
    for lbl, tabs, src in (("adm1_wb", wb, pm), ("adm1_gadm41", gadm, rekey(pm))):
        s_src = src.groupby("ISO_A3").ntl_sum.sum()
        s_out = recon_sums[lbl]
        recon[lbl] = {"max_rel_diff_country_total": float(((s_out - s_src).abs() / s_src.where(s_src > 1)).max()),
                      "note": "computed before rounding; published values are rounded to 4 decimals"}
    tot = pm.ntl_sum.sum()
    recon["adm1_gadm41"]["share_world_light_monthly_assigned"] = float(rekey(pm).ntl_sum.sum() / tot)

    # ---------------- write
    manifest = []
    print("writing ...", flush=True)
    write_product(wb, "adm1_wb", manifest)
    write_product(gadm, "adm1_gadm41", manifest)
    write_product(adm2, "adm2", manifest, dta=True, float32=True)
    # crosswalks + QA tables to the site
    xdir = DATA / "crosswalks"
    xdir.mkdir(parents=True, exist_ok=True)
    for f in ["crosswalk_adm2_to_gadm41.csv", "qa_by_country.csv", "gadm_units_without_data.csv",
              "qa_summary.json", "geo_match_wb_adm1.csv"]:
        shutil.copy(XW / f, xdir / f)
    q.reset_index().to_csv(xdir / "gadm41_adm1_match_quality.csv", index=False, encoding="utf-8")

    # economic-data compatibility (DOSE V2.14; US BEA / Brazil IBGE crosswalks)
    import econ
    econ_summary = {"dose": econ.build_dose(pa, xw, DATA / "econ" / "dose", REL),
                    "national": econ.build_national(DATA / "econ" / "national")}
    print(json.dumps(econ_summary, indent=1), flush=True)
    import schema
    schema.write(DATA)

    # per-country ADM2 CSV bundle for the release (site keeps Parquet + CSV per country)
    meta = {"version": VERSION, "built": date.today().isoformat(),
            "source": {"dataset": "World Bank Space2Stats - Monthly & Annual Black Marble Nighttime Lights",
                       "catalog_id": "0066940", "catalog_version": "2",
                       "url": "https://datacatalog.worldbank.org/search/dataset/0066940",
                       "files": {f.name: {"bytes": f.stat().st_size, "sha256": sha256(f)}
                                 for f in [RAW / "ntl_adm2_monthly_all.parquet", RAW / "ntl_adm2_annual.csv"]}},
            "coverage": {"months": [m.date.min(), m.date.max()], "years_official_annual": [int(a.year.min()), int(a.year.max())]},
            "reconciliation": recon}
    (DATA / "build_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(json.dumps(recon, indent=2))
    place_globals()
    write_manifest()


def place_globals():
    """Hosting policy (GitHub Pages ~1 GB): the site keeps per-country Parquet (explorer)
    and annual global Parquet; all global CSV.gz and monthly global Parquet go to the release."""
    REL.mkdir(parents=True, exist_ok=True)
    for sub in ("adm1_wb", "adm1_gadm41", "adm2"):
        for p in (DATA / sub).glob(f"{sub}_*_global.*"):
            if p.name.endswith(".csv.gz") or p.name.startswith(f"{sub}_monthly_global") or p.stat().st_size > PAGES_MAX:
                shutil.move(str(p), REL / p.name)


def write_manifest():
    files = []
    for p in sorted(DATA.rglob("*")):
        if p.is_file() and p.name != "manifest.json":
            files.append({"path": p.relative_to(SITE).as_posix(), "bytes": p.stat().st_size,
                          "sha256": sha256(p), "host": "pages"})
    for p in sorted(REL.glob("*")):
        files.append({"path": p.name, "bytes": p.stat().st_size, "sha256": sha256(p), "host": "release",
                      "url": f"https://github.com/ouaretw/nightlights-adm1/releases/download/v{VERSION}/{p.name}"})
    (DATA / "manifest.json").write_text(json.dumps({"version": VERSION, "files": files}, indent=1), encoding="utf-8")
    site_mb = sum(f["bytes"] for f in files if f["host"] == "pages") / 1e6
    rel_mb = sum(f["bytes"] for f in files if f["host"] == "release") / 1e6
    print(f"site data {site_mb:,.0f} MB, release assets {rel_mb:,.0f} MB, files {len(files)}")


if __name__ == "__main__":
    main()
