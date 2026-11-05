"""Group-configured Pandas ledger conversion pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .cache import load_input
from .config import GroupConfig, load_config
from .transforms import add_source_metadata, apply_field_rules, apply_processing_rules, clean_string_columns
from .validation import validate_frame


class LedgerPipeline:
    def __init__(self, config: GroupConfig):
        self.config = config

    @classmethod
    def from_config_file(cls, path: str | Path) -> "LedgerPipeline":
        return cls(load_config(path))

    def run(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        cache_path: str | Path | None = None,
        refresh_cache: bool = False,
        report_path: str | Path | None = None,
    ) -> dict[str, Any]:
        raw, _cache_file = load_input(
            input_path,
            self.config,
            cache_path=cache_path,
            refresh_cache=refresh_cache,
        )
        raw = raw.reset_index(drop=True)
        raw = clean_string_columns(raw)
        output = apply_field_rules(raw, self.config)
        output = apply_processing_rules(output, self.config)
        output = add_source_metadata(output, str(input_path), self.config)
        report = validate_frame(output, self.config)
        if report["status"] == "error":
            raise ValueError(f"Validation failed: {report['missing_required_columns']}")

        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        output.to_parquet(destination, index=False)
        report["output_file"] = str(destination)
        report["output_rows"] = int(len(output))
        if report_path:
            from .validation import write_report

            report_file = Path(report_path)
            report_file.parent.mkdir(parents=True, exist_ok=True)
            write_report(report, str(report_file))
        return report
