"""Command-line entry point for ledger conversion."""

from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import LedgerPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a group ledger to Parquet")
    parser.add_argument("--config", required=True, help="Group TOML configuration")
    parser.add_argument("--input", required=True, help="Excel or Pickle input file")
    parser.add_argument("--output", required=True, help="Parquet output file")
    parser.add_argument("--cache", help="Optional Pickle cache path")
    parser.add_argument("--report", help="Optional JSON quality report path")
    parser.add_argument("--refresh-cache", action="store_true", help="Rebuild Pickle from Excel")
    args = parser.parse_args()

    report = LedgerPipeline.from_config_file(args.config).run(
        input_path=args.input,
        output_path=args.output,
        cache_path=args.cache,
        refresh_cache=args.refresh_cache,
        report_path=args.report,
    )
    print(f"Converted {report['output_rows']} rows to {Path(args.output)}")


if __name__ == "__main__":
    main()
