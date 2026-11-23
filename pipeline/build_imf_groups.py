"""IMF World Economic Outlook country classification, April 2023 edition.

Source: IMF, World Economic Outlook, April 2023, Statistical Appendix,
Table B (Advanced Economies by Subgroup) and Table E (Emerging Market and
Developing Economies by Region ...).
  https://www.imf.org/-/media/files/publications/weo/2023/april/english/statsappendix.pdf
The PDF is kept in raw/econ/imf/ with its SHA-256. Member names are parsed from
the PDF text, not typed by hand; the stated group counts (41 advanced, 155
EMDE; regional 30/15/33/32/45) are asserted. Names are matched to ISO3 through
the World Bank country list (raw/econ/wdi/countries.json) plus the explicit
table NAME_FIX below; every name must resolve or the build fails.

Output: raw/econ/imf/weo_2023apr_groups.csv
  iso3, imf_name, imf_group (advanced | emde), imf_region, euro_area, g7
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IMF = ROOT / "raw" / "econ" / "imf"
PDF = IMF / "weo_2023apr_statsappendix.pdf"
URL = "https://www.imf.org/-/media/files/publications/weo/2023/april/english/statsappendix.pdf"
REGIONS = {"Emerging and Developing Asia": 30, "Emerging and Developing Europe": 15,
           "Latin America and the Caribbean": 33, "Middle East and Central Asia": 32,
           "Sub-Saharan Africa": 45}
# IMF spelling -> ISO3 where the World Bank name differs
NAME_FIX = {
    "Korea": "KOR", "Hong Kong SAR": "HKG", "Macao SAR": "MAC", "Taiwan Province of China": "TWN",
    "The Netherlands": "NLD", "Slovak Republic": "SVK", "Czech Republic": "CZE",
    "Lao P.D.R.": "LAO", "Micronesia": "FSM", "Vietnam": "VNM", "Türkiye": "TUR", "Russia": "RUS",
    "The Bahamas": "BHS", "St. Kitts and Nevis": "KNA", "St. Lucia": "LCA",
    "St. Vincent and the Grenadines": "VCT", "Venezuela": "VEN", "Iran": "IRN", "Egypt": "EGY",
    "Syria": "SYR", "Yemen": "YEM", "Kyrgyz Republic": "KGZ", "West Bank and Gaza": "PSE",
    "Democratic Republic of the Congo": "COD", "Republic of Congo": "COG", "Côte d’Ivoire": "CIV",
    "The Gambia": "GMB", "São Tomé and Príncipe": "STP", "Cabo Verde": "CPV", "Eswatini": "SWZ",
    "Kosovo": "XKX", "Moldova": "MDA", "North Macedonia": "MKD", "Brunei Darussalam": "BRN",
    "Bolivia": "BOL", "Somalia": "SOM", "South Sudan": "SSD", "Puerto Rico": "PRI", "Nauru": "NRU",
}
SKIP = {"Net External", "Position1", "Heavily Indebted", "Poor Countries2", "Per Capita", "Income",
        "Classification3", ". . .", "*", "•", "Major Currency Areas", "Euro Area",
        "Major Advanced Economies", "Other Advanced Economies", "WORLD ECONOMIC OUTLOOK: A ROCKY RECOVERY",
        "STATISTICAL APPENDIX", "International Monetary Fund | April 2023"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def lines(text: str):
    """Clean, joined name lines (continuations end with a trailing space)."""
    out, carry = [], ""
    for raw in text.split("\n"):
        s = raw.replace(" ", " ").replace("\t", " ")
        if not s.strip():
            continue
        st = s.strip()
        if st in SKIP or re.fullmatch(r"\d{3}", st) or st.startswith("=== page") or st.startswith("Table "):
            continue
        if carry:
            st, carry = (carry + " " + st).strip(), ""
        if s.endswith(" ") and not s.endswith("  ") and st not in REGIONS and len(st.split()) >= 2 \
                and st.split()[-1] in ("the", "of", "and"):
            carry = st
            continue
        out.append(re.sub(r"(?<=[A-Za-z])\d$", "", st))   # footnote digits: "Macao SAR2"
    return out


MISSING = []


def main():
    doc = fitz.open(PDF)
    text = "\n".join(f"=== page {i}\n" + doc[i].get_text() for i in range(len(doc)))
    b = text[text.index("Table B. Advanced Economies by Subgroup"):text.index("Table C. European Union")]
    b = b[:b.index("1On July 1, 1997")]
    b_lines = lines(b)
    euro_part = b[b.index("Euro Area\nAustria"):b.index("Major Advanced Economies")]
    euro = set(lines(euro_part.replace("Euro Area\n", "", 1)))
    g7 = set(lines(b[b.index("Major Advanced Economies"):b.index("Other Advanced Economies")]))
    advanced = list(dict.fromkeys(n for n in b_lines))
    assert len(advanced) == 41, (len(advanced), advanced)
    assert len(euro) == 20 and len(g7) == 7, (euro, g7)

    # Table E spans the two pages after Table D; regions are headings
    start = text.index("=== page 8")
    e = text[start:]
    e = e[:e.index("\n1Net external position")] if "\n1Net external position" in e else e
    region, emde = None, []
    for ln in lines(e):
        if ln in REGIONS:
            region = ln
            continue
        if ln.startswith(("Emerging Market and Developing Economies", "and Per Capita")):
            continue
        if region and not re.match(r"^\d", ln):
            emde.append((ln, region))
        if region == "Sub-Saharan Africa" and ln == "Zimbabwe":
            break
    counts = pd.Series([r for _, r in emde]).value_counts().to_dict()
    assert counts == REGIONS, counts
    assert len(emde) == 155

    wb = json.loads((ROOT / "raw" / "econ" / "wdi" / "countries.json").read_text(encoding="utf-8"))
    by_name = {norm(c["name"]): c["id"] for c in wb if c["region"]["value"] != "Aggregates"}
    fix = {norm(k): v for k, v in NAME_FIX.items()}

    def iso(name):
        k = norm(name)
        if k in fix:
            return fix[k]
        if k in by_name:
            return by_name[k]
        MISSING.append(name); return None

    rows = [{"iso3": iso(n), "imf_name": n, "imf_group": "advanced", "imf_region": "Advanced Economies",
             "euro_area": n in euro, "g7": n in g7} for n in advanced]
    rows += [{"iso3": iso(n), "imf_name": n, "imf_group": "emde", "imf_region": r,
              "euro_area": False, "g7": False} for n, r in emde]
    if MISSING:
        raise KeyError(f"IMF names not matched to ISO3: {MISSING}")
    df = pd.DataFrame(rows)
    assert df.iso3.is_unique, df[df.iso3.duplicated(keep=False)]
    df.to_csv(IMF / "weo_2023apr_groups.csv", index=False)
    meta = {"source": "IMF World Economic Outlook, April 2023, Statistical Appendix, Tables B and E",
            "url": URL, "pdf_sha256": hashlib.sha256(PDF.read_bytes()).hexdigest(),
            "n_advanced": int((df.imf_group == "advanced").sum()), "n_emde": int((df.imf_group == "emde").sum()),
            "regions": counts,
            "note": "Classification is the IMF's analytical grouping as of the April 2023 WEO; it is not a "
                    "continuous income measure and is applied unchanged to all years in the analysis."}
    (IMF / "weo_2023apr_groups_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
