from pathlib import Path
import polars as pl

def ledger_schema(excel_file: str) -> pl.Schema:
    df = pl.read_excel(excel_file)
    return df.schema

def scan_all_ledgers(excel_dir: str) -> dict[str, pl.Schema]:
    schemas = {}
    for excel_file in Path(excel_dir).glob("*.xlsx"):
        schemas[excel_file.name] = ledger_schema(str(excel_file))
    return schemas

if __name__ == "__main__":
    excel_dir = "D:/Temp/yihai_data/ledger"  # 替换为你的 Excel 文件夹路径
    schemas = scan_all_ledgers(excel_dir)
    for name, schema in schemas.items():
        print(f"{name}: {schema}")
        print("-" * 40)