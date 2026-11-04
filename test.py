import polars as pl

df = pl.read_parquet("processed_ledger.parquet")

print(df.head())
print(df.tail())
# easy to read with excel
df.to_pandas().to_csv("out.csv", index=False, encoding="utf-8-sig")
