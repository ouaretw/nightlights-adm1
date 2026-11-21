"""Build only the economic-integration products (DOSE, national crosswalks)."""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import econ  # noqa: E402
import ntl_core as core  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "build" / "site" / "data" / "v2"


def main():
    a = pd.read_csv(ROOT / "raw" / "ntl_adm2_annual.csv", usecols=lambda c: c in set(core.SOURCE_COLS + ["year"]),
                    dtype={"ADM1CD_c": str, "ADM2CD_c": str, "ISO_A3": str})
    m = pd.read_parquet(ROOT / "raw" / "ntl_adm2_monthly_all.parquet",
                        columns=["ADM2CD_c", "ntl_sum", "ntl_mean", "ntl_quality_prop_na"])
    T = core.total_weights(m)
    del m
    pa = core.prepare_adm2(a, T)
    xw = pd.read_csv(ROOT / "build" / "crosswalks" / "crosswalk_adm2_to_gadm41.csv", dtype=str)
    s1 = econ.build_dose(pa, xw, DATA / "econ" / "dose", ROOT / "build" / "release")
    s2 = econ.build_national(DATA / "econ" / "national")
    print(json.dumps({"dose": s1, "national": s2}, indent=2))


if __name__ == "__main__":
    main()
