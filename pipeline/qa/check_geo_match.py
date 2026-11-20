"""Compare ADM1 codes in the NTL table vs the FeatureServer geometry."""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
geo = json.loads((ROOT / "raw" / "geo" / "wb_gad_adm1_simplified.geojson").read_text(encoding="utf-8"))
g = pd.DataFrame([f["properties"] for f in geo["features"]])
print("geo features", len(g), "unique codes", g.ADM1CD_c.nunique(), "null geom",
      sum(f.get("geometry") is None for f in geo["features"]))
ntl = pd.read_parquet(ROOT / "docs" / "data" / "adm1_annual_all.parquet", columns=["ISO_A3", "ADM1CD_c", "NAM_1"]).drop_duplicates("ADM1CD_c")
a, b = set(ntl.ADM1CD_c), set(g.ADM1CD_c)
print("ntl adm1", len(a), "in geo", len(a & b), "ntl-only", len(a - b), "geo-only", len(b - a))
only = ntl[~ntl.ADM1CD_c.isin(b)]
print(only.ISO_A3.value_counts().head(30))
print(only.head(15))
print(g[~g.ADM1CD_c.isin(a)].head(15))
sizes = sorted(((p.stat().st_size, p.name) for p in (ROOT / "docs" / "data" / "geo" / "adm1").glob("*.geojson")), reverse=True)
print("adm1 geojson total MB", round(sum(s for s, _ in sizes) / 1e6, 1), "largest", sizes[:5])
print("adm0 MB", round((ROOT / "docs" / "data" / "geo" / "adm0_world.geojson").stat().st_size / 1e6, 2))

import unicodedata
def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in s if ch.isalnum())
m = ntl.merge(g[["ADM1CD_c", "NAM_1"]], on="ADM1CD_c", suffixes=("_ntl", "_geo"))
m["same"] = m.NAM_1_ntl.map(norm) == m.NAM_1_geo.map(norm)
print("matched codes", len(m), "same name", int(m.same.sum()))
print(m[~m.same].head(40).to_string())
print(m[~m.same].ISO_A3.value_counts().head(20))
