"""Excel to Pickle caching and input loading."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import GroupConfig


def cache_excel_to_pickle(
    excel_path: str | Path,
    pickle_path: str | Path | None = None,
    config: GroupConfig | None = None,
) -> Path:
    """Read Excel once and persist the raw frame as a Pickle cache."""

    source = Path(excel_path).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"Excel file not found: {source}")
    target = Path(pickle_path).expanduser() if pickle_path else source.with_suffix(".pkl")
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet_name = config.sheet_name if config else 0
    header = config.header_row if config else 0
    frame = pd.read_excel(source, sheet_name=sheet_name, header=header, dtype=str)
    frame.to_pickle(target)
    return target


def load_input(
    input_path: str | Path,
    config: GroupConfig,
    *,
    cache_path: str | Path | None = None,
    refresh_cache: bool = False,
) -> tuple[pd.DataFrame, Path]:
    """Load Pickle directly, or create/refresh the adjacent Pickle for Excel."""

    source = Path(input_path).expanduser()
    if source.suffix.lower() in {".pkl", ".pickle"}:
        if not source.exists():
            raise FileNotFoundError(f"Pickle file not found: {source}")
        return pd.read_pickle(source), source

    if source.suffix.lower() not in {".xlsx", ".xls", ".xlsm"}:
        raise ValueError(f"Unsupported input format: {source.suffix}")

    target = Path(cache_path).expanduser() if cache_path else source.with_suffix(".pkl")
    cache_is_stale = not target.exists() or source.stat().st_mtime > target.stat().st_mtime
    if refresh_cache or cache_is_stale:
        cache_excel_to_pickle(source, target, config)
    return pd.read_pickle(target), target
