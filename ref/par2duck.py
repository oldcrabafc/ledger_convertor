"""Convert a parquet file to a DuckDB file."""

from __future__ import annotations

from pathlib import Path

import duckdb


def convert_parquet_to_duckdb(
    input_path: str | Path,
    output_path: str | Path,
    table_name: str = "ledger",
) -> Path:
    """Read a parquet file and write it as a DuckDB database file."""
    source = Path(input_path).expanduser()
    target = Path(output_path).expanduser()

    if not source.exists():
        raise FileNotFoundError(f"Parquet file not found: {source}")

    if source.suffix.lower() not in {".parquet", ".pq", ".pqt"}:
        raise ValueError(f"Expected a parquet file, got: {source}")

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()

    with duckdb.connect(str(target)) as conn:
        conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet(?)", [str(source)])
        conn.execute("CHECKPOINT")
        conn.execute("VACUUM")

    return target


def main(input_path, output_path, table_name) -> None:


    output = convert_parquet_to_duckdb(input_path, output_path, table_name)
    print(f"Saved: {output}")


if __name__ == "__main__":
    input_path = "D:/Temp/test_data/ledger_cache/profilm_NB_ledger_260930.parquet"
    output_path = "D:/Temp/test_data/ledger_db/profilm_nb.duckdb"
    table_name = "ledger_260930"

    main(
        input_path,
        output_path,
        table_name
    )
