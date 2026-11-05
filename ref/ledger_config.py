"""Configuration parsing for the ledger pipeline.

This module contains dataclasses and functions to load and validate the TOML
configuration. It is intentionally separated from the cleaning logic so callers
can read/inspect configuration without importing heavy processing code.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for older Python
    import tomli as tomllib  # type: ignore[import-not-found]

import polars as pl

DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.toml")

ConfigMap = Mapping[str, Any]


def resolve_config_dtype(dtype_str: str) -> pl.DataType:
    """Resolve config dtype strings to Polars dtypes.

    This is intentionally placed in the config module: the mapping from config
    token -> Polars dtype is a configuration concern and callers should import
    this function instead of duplicating the logic.
    """

    token = str(dtype_str).strip()
    if not token:
        raise ValueError("Empty dtype in config")

    pl_type = getattr(pl, token, None)
    if pl_type is not None:
        return pl_type

    raise ValueError(
        f"Unsupported dtype '{dtype_str}'. Use canonical Polars names like Utf8, Float64, Int64, Boolean, Date, Datetime"
    )


@dataclass(frozen=True)
class FieldSpec:
    target: str
    source: Any
    dtype: str
    kind: str = "single"
    prefix: str | None = None


@dataclass(frozen=True)
class DrcrConfig:
    column: str
    debit: Any
    credit: Any
    amount_columns: tuple[str, ...]


@dataclass(frozen=True)
class PipelineConfig:
    field_specs: tuple[FieldSpec, ...]
    drcr: DrcrConfig | None


@lru_cache(maxsize=1)
def load_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load the pipeline config lazily."""

    path = Path(config_path)
    if path.suffix.lower() != ".toml":
        raise ValueError(f"Unsupported config format '{path.suffix}'. Use .toml")

    with path.open("rb") as f:
        return tomllib.load(f)


def get_config_section(config: ConfigMap, section: str) -> Any:
    try:
        return config[section]
    except KeyError as exc:
        raise KeyError(f"Missing required config section: {section}") from exc


def _ensure_mapping(value: Any, section: str) -> Mapping[str, Any]:
    """Ensure the given value is a mapping for the named config section."""

    if not isinstance(value, Mapping):
        raise TypeError(f"Config section '{section}' must be a mapping")
    return value


def _ensure_sequence(value: Any, section: str) -> Sequence[Any]:
    """Ensure the given value is a sequence (excluding strings)."""

    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"Config section '{section}' must be a sequence")
    return value


def _parse_field_spec(
    target: str, raw_entry: Any, *, source_override: Any = None
) -> FieldSpec:
    """Parse one configured target field into a FieldSpec."""

    section = f"required_columns.{target}"
    entry = _ensure_mapping(raw_entry, section)

    if "dtype" not in entry:
        raise KeyError(f"Config section '{section}' must contain 'dtype'")

    kind = str(entry.get("kind", "single")).strip() or "single"
    source = entry.get("source", source_override)
    prefix = entry.get("prefix")

    if source is None:
        raise KeyError(f"Config section '{section}' must contain 'source'")
    if kind not in {"single", "right_neighbor"}:
        raise ValueError(f"Unsupported field kind '{kind}' in section '{section}'")
    if isinstance(source, Mapping):
        raise TypeError(
            f"Config section '{section}.source' must be a string when kind is '{kind}'"
        )

    source = str(source)
    kind = "right_neighbor" if kind == "right_neighbor" else "single"

    return FieldSpec(
        target=str(target),
        source=source,
        dtype=str(entry["dtype"]),
        kind=kind,
        prefix=str(prefix) if prefix is not None else None,
    )


def _parse_required_columns(config: ConfigMap) -> tuple[FieldSpec, ...]:
    required_columns = _ensure_mapping(
        get_config_section(config, "required_columns"), "required_columns"
    )
    return tuple(
        _parse_field_spec(str(target), raw_entry)
        for target, raw_entry in required_columns.items()
    )


def _parse_drcr_config(raw_drcr: Any) -> DrcrConfig | None:
    """Parse the DR/CR configuration block."""

    if raw_drcr is None:
        return None

    drcr_root = _ensure_mapping(raw_drcr, "drcr")
    # Support both legacy flat format [drcr] and nested format [drcr.single].
    drcr = (
        _ensure_mapping(drcr_root["single"], "drcr.single")
        if "single" in drcr_root
        else drcr_root
    )
    required_keys = {"column", "debit", "credit", "amount_columns"}
    if not required_keys <= set(drcr):
        raise KeyError(
            "Config section 'drcr' (or 'drcr.single') must contain 'column', 'debit', 'credit', and 'amount_columns'"
        )

    amount_columns = _ensure_sequence(drcr["amount_columns"], "drcr.amount_columns")
    return DrcrConfig(
        column=str(drcr["column"]),
        debit=drcr["debit"],
        credit=drcr["credit"],
        amount_columns=tuple(str(col) for col in amount_columns),
    )


def load_pipeline_config(config: ConfigMap) -> PipelineConfig:
    """Parse runtime config into the internal pipeline representation."""

    if "required_columns" not in config:
        raise KeyError("Config must contain 'required_columns'")

    return PipelineConfig(
        field_specs=_parse_required_columns(config),
        drcr=_parse_drcr_config(config.get("drcr")),
    )
