"""Configuration models and TOML loading for group-specific ledgers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass(frozen=True)
class FieldRule:
    source: str
    dtype: str = "string"
    required: bool = False
    kind: str = "single"
    prefix: str | None = None


@dataclass(frozen=True)
class DrcrRule:
    column: str
    debit_values: tuple[Any, ...]
    credit_values: tuple[Any, ...]
    amount_columns: tuple[str, ...]


@dataclass(frozen=True)
class ProcessingRule:
    fill_forward: tuple[str, ...] = ()
    remove_voided: bool = False
    voided_column: str | None = None
    voided_values: tuple[Any, ...] = ()
    remove_closing: bool = False
    closing_column: str | None = None
    closing_prefixes: tuple[str, ...] = ()
    drop_zero_amount_rows: bool = False


@dataclass(frozen=True)
class ValidationRule:
    required_columns: tuple[str, ...] = ()
    allow_unknown_drcr: bool = True


@dataclass(frozen=True)
class GroupConfig:
    name: str
    version: str
    fields: dict[str, FieldRule]
    sheet_name: str | int = 0
    header_row: int = 0
    processing: ProcessingRule = field(default_factory=ProcessingRule)
    drcr: DrcrRule | None = None
    validation: ValidationRule = field(default_factory=ValidationRule)


def _as_tuple(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return (value,)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"Configuration section '{name}' must be a table")
    return value


def load_config(path: str | Path) -> GroupConfig:
    config_path = Path(path)
    with config_path.open("rb") as stream:
        raw = tomllib.load(stream)

    group = _mapping(raw.get("group"), "group")
    input_rule = _mapping(raw.get("input"), "input")
    raw_fields = _mapping(raw.get("fields"), "fields")
    if not raw_fields:
        raise ValueError(f"{config_path}: [fields] must contain at least one field")

    fields: dict[str, FieldRule] = {}
    for target, raw_rule in raw_fields.items():
        rule = _mapping(raw_rule, f"fields.{target}")
        source = rule.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"fields.{target}.source must be a non-empty string")
        kind = str(rule.get("kind", "single")).strip() or "single"
        if kind not in {"single", "right_neighbor"}:
            raise ValueError(f"Unsupported field kind '{kind}' for fields.{target}")
        fields[str(target)] = FieldRule(
            source=source,
            dtype=str(rule.get("dtype", "string")),
            required=bool(rule.get("required", False)),
            kind=kind,
            prefix=str(rule["prefix"]) if rule.get("prefix") is not None else None,
        )

    raw_processing = _mapping(raw.get("processing"), "processing")
    processing = ProcessingRule(
        fill_forward=tuple(str(value) for value in _as_tuple(raw_processing.get("fill_forward"))),
        remove_voided=bool(raw_processing.get("remove_voided", False)),
        voided_column=raw_processing.get("voided_column"),
        voided_values=_as_tuple(raw_processing.get("voided_values")),
        remove_closing=bool(raw_processing.get("remove_closing", False)),
        closing_column=raw_processing.get("closing_column"),
        closing_prefixes=tuple(str(value) for value in _as_tuple(raw_processing.get("closing_prefixes"))),
        drop_zero_amount_rows=bool(raw_processing.get("drop_zero_amount_rows", False)),
    )

    raw_drcr = _mapping(raw.get("drcr"), "drcr") if raw.get("drcr") is not None else None
    drcr = None
    if raw_drcr:
        column = raw_drcr.get("column")
        if not isinstance(column, str) or not column:
            raise ValueError("drcr.column must be a non-empty string")
        drcr = DrcrRule(
            column=column,
            debit_values=_as_tuple(raw_drcr.get("debit_values")),
            credit_values=_as_tuple(raw_drcr.get("credit_values")),
            amount_columns=tuple(str(value) for value in _as_tuple(raw_drcr.get("amount_columns"))),
        )

    raw_validation = _mapping(raw.get("validation"), "validation")
    validation = ValidationRule(
        required_columns=tuple(str(value) for value in _as_tuple(raw_validation.get("required_columns"))),
        allow_unknown_drcr=bool(raw_validation.get("allow_unknown_drcr", True)),
    )
    name = str(group.get("name", config_path.stem))
    version = str(group.get("version", "v1"))
    return GroupConfig(
        name=name,
        version=version,
        fields=fields,
        sheet_name=input_rule.get("sheet_name", 0),
        header_row=int(input_rule.get("header_row", 0)),
        processing=processing,
        drcr=drcr,
        validation=validation,
    )
