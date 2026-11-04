"""
Convert an Excel workbook to a pickle cache.

This script reads values from a source Excel file and writes a pickle cache.
It supports:
- direct function calls in Python
- command-line arguments
- a local `.env` file next to the script for quick configuration

Example `.env` file (same folder as this script):
    SOURCE=D:/Datasets/audit_projects/raw/KH/ledger.xlsx
    OUTPUT=ledger_FY24
    ROOT_DIR=D:/Temp/test_data/ledger_cache

Usage:
    python cache_ledger.py
    python cache_ledger.py --source "D:/data/ledger.xlsx" --output-name "ledger_FY24"
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

DEFAULT_CACHE_ROOT = Path("D:/Temp/test_data/ledger_cache")
ENV_FILE_NAME = ".env"


def sanitize_component(value: str | None) -> str:
    """Normalize a file name component for safe filesystem use."""
    if value is None:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip())
    return cleaned.strip("._")


def load_env_config(env_path: str | Path | None = None) -> dict[str, str]:
    """Load configuration from .env in the same directory as this script."""
    config_path = Path(env_path) if env_path else Path(__file__).resolve().with_name(ENV_FILE_NAME)
    load_dotenv(dotenv_path=config_path, override=False)

    env_values: dict[str, str] = {}
    for key in ("SOURCE", "OUTPUT", "ROOT_DIR"):
        value = os.getenv(key)
        if value is not None:
            env_values[key.lower()] = value
    return env_values


def normalize_output_path(
    source: str | Path,
    output: str,
    cache_root: str | Path = DEFAULT_CACHE_ROOT,
) -> Path:
    """Build a pickle output path under the cache directory."""
    source_path = Path(source)

    if not output or not str(output).strip():
        target_name = source_path.stem
    else:
        target_name = Path(str(output)).name

    for suffix in (".pkl", ".xlsx", ".xls", ".xlsm"):
        if target_name.lower().endswith(suffix):
            target_name = target_name[: -len(suffix)]
            break

    target_name = sanitize_component(target_name)
    output_dir = Path(cache_root)
    output_dir.mkdir(parents=True, exist_ok=True)

    return output_dir / f"{target_name}.pkl"


def main(
    source: str | Path,
    output: str,
    root_dir: str | Path = DEFAULT_CACHE_ROOT,
) -> Path:
    """Read an Excel workbook and save it as a pickle cache file."""
    source_path = Path(source).expanduser()
    if not source_path.exists():
        raise FileNotFoundError(f"Excel file not found: {source_path}")

    try:
        df = pd.read_excel(source_path, dtype=str)
    except ImportError as exc:
        raise SystemExit(
            "Excel support requires 'openpyxl'. Install it with: "
            "python -m pip install openpyxl\n"
            "or: python -m pip install -r requirements.txt"
        ) from exc

    output_path = normalize_output_path(
        source=source_path,
        output=output,
        cache_root=root_dir,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_pickle(output_path)
    print(f"Saved to: {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Excel xlsx to pickle.")
    parser.add_argument("--source", default=None, help="Input Excel file path, for example: D:/Datasets/data/ledger.xlsx")
    parser.add_argument("--output-name", default=None, help="Target file name without extension, for example: ledger_FY24")
    parser.add_argument("--root-dir", default=None, help="Base directory for storing the pickle cache")
    args = parser.parse_args()

    env_values = load_env_config()

    source_value = args.source or env_values.get("source")
    output_value = args.output_name or env_values.get("output")
    root_dir_value = args.root_dir or env_values.get("root_dir")

    if not source_value or not output_value:
        missing = []
        if not source_value:
            missing.append("SOURCE")
        if not output_value:
            missing.append("OUTPUT")
        raise SystemExit(f"Missing required config: {', '.join(missing)}. Please set them in .env or pass command-line arguments.")

    main(
        source=source_value,
        output=output_value,
        root_dir=root_dir_value or DEFAULT_CACHE_ROOT,
    )
