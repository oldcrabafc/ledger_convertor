"""Validation and conversion report helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .config import GroupConfig


def validate_frame(df: pd.DataFrame, config: GroupConfig) -> dict[str, Any]:
    required = set(config.validation.required_columns)
    required.update(target for target, rule in config.fields.items() if rule.required)
    missing = sorted(required - set(df.columns))
    return {
        "group": config.name,
        "config_version": config.version,
        "rows": int(len(df)),
        "columns": list(df.columns),
        "missing_required_columns": missing,
        "status": "error" if missing else "ok",
    }


def write_report(report: dict[str, Any], path: str) -> None:
    import json

    with open(path, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, default=str)
