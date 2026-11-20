"""Quick look at the raw World Bank ADM2 Black Marble parquet."""
import pandas as pd
import pyarrow.parquet as pq

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 80)
pd.set_option("display.max_rows", 200)

f = pq.ParquetFile(r"D:\nightlights_adm1\raw\ntl_adm2_monthly_all.parquet")
print(f.metadata.num_rows, "rows;", f.metadata.num_row_groups, "row groups")
print(f.schema_arrow)
print(f.read_row_group(0).slice(0, 3).to_pandas().T)
