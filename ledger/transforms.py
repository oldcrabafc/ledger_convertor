"""Reusable Pandas transformations for group-specific ledger files."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .config import DrcrRule, FieldRule, GroupConfig


def clean_string_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for column in result.select_dtypes(include=["object", "string"]).columns:
        values = result[column].astype("string").str.strip()
        result[column] = values.mask(values.eq(""), pd.NA)
    return result


def _cast_series(series: pd.Series, dtype: str) -> pd.Series:
    token = dtype.strip().lower()
    if token in {"string", "utf8", "str", "object"}:
        return series.astype("string")
    if token in {"date", "datetime", "datetime64", "datetime64[ns]"}:
        return pd.to_datetime(series, errors="coerce")
    if token in {"float", "float64", "decimal", "number"}:
        cleaned = series.astype("string").str.replace(",", "", regex=False)
        return pd.to_numeric(cleaned, errors="coerce")
    if token in {"int", "int64", "integer"}:
        numeric = pd.to_numeric(series, errors="coerce")
        return numeric.astype("Int64")
    if token in {"bool", "boolean"}:
        return series.astype("boolean")
    raise ValueError(f"Unsupported configured dtype: {dtype}")


def resolve_source_columns(df: pd.DataFrame, config: GroupConfig) -> dict[str, str]:
    positions = {name: index for index, name in enumerate(df.columns)}
    non_null = df.notna().sum()
    resolved: dict[str, str] = {}
    for target, rule in config.fields.items():
        if rule.source not in positions:
            raise ValueError(f"Missing source column for '{target}': {rule.source}")
        source = rule.source
        if rule.kind == "right_neighbor":
            index = positions[source]
            if index + 1 >= len(df.columns):
                raise ValueError(f"No right-neighbor column after '{source}'")
            candidate = str(df.columns[index + 1])
            if int(non_null[source]) != int(non_null[candidate]):
                raise ValueError(f"Right-neighbor column does not match '{source}': {candidate}")
            source = candidate
        resolved[target] = source
    return resolved


def apply_field_rules(df: pd.DataFrame, config: GroupConfig) -> pd.DataFrame:
    resolved = resolve_source_columns(df, config)
    typed = df.copy()
    for target, rule in config.fields.items():
        source = resolved[target]
        typed[source] = _cast_series(typed[source], rule.dtype)

    output = pd.DataFrame(index=typed.index)
    for target, rule in config.fields.items():
        values = typed[resolved[target]].copy()
        if rule.prefix is not None:
            values = values.astype("string")
            values = values.where(values.isna(), rule.prefix + values)
        output[target] = values
    return output


def apply_processing_rules(df: pd.DataFrame, config: GroupConfig) -> pd.DataFrame:
    result = df.copy()
    processing = config.processing
    for column in processing.fill_forward:
        if column in result.columns:
            result[column] = result[column].ffill()

    if config.drcr:
        result = apply_drcr_sign(result, config.drcr, config.validation.allow_unknown_drcr)

    if processing.remove_voided and processing.voided_column in result.columns:
        result = result.loc[~result[processing.voided_column].isin(processing.voided_values)].copy()
    if processing.remove_closing and processing.closing_column in result.columns:
        pattern = "|".join(pd.Series(processing.closing_prefixes).map(lambda value: f"^{value}").tolist())
        if pattern:
            result = result.loc[~result[processing.closing_column].astype("string").str.contains(pattern, na=False, regex=True)].copy()
    if processing.drop_zero_amount_rows and config.drcr:
        amounts = [column for column in config.drcr.amount_columns if column in result.columns]
        if amounts:
            numeric = result[amounts].apply(pd.to_numeric, errors="coerce").fillna(0)
            result = result.loc[numeric.ne(0).any(axis=1)].copy()
    return result


def apply_drcr_sign(df: pd.DataFrame, rule: DrcrRule, allow_unknown: bool = True) -> pd.DataFrame:
    if rule.column not in df.columns:
        raise ValueError(f"DR/CR column not found: {rule.column}")
    result = df.copy()
    values = result[rule.column]
    unknown = values.notna() & ~values.isin(rule.debit_values + rule.credit_values)
    if unknown.any() and not allow_unknown:
        raise ValueError(f"Unknown DR/CR values: {sorted(values[unknown].astype(str).unique())}")
    for column in rule.amount_columns:
        if column not in result.columns:
            continue
        amount = pd.to_numeric(result[column], errors="coerce")
        result[column] = amount.mask(values.isin(rule.credit_values), -amount)
    return result


def add_source_metadata(df: pd.DataFrame, source_file: str, config: GroupConfig) -> pd.DataFrame:
    result = df.copy()
    result.insert(0, "_source_row", result.index + 1)
    result.insert(0, "_source_file", source_file)
    result["_group"] = config.name
    result["_config_version"] = config.version
    result["_conversion_time"] = pd.Timestamp.now(tz="UTC")
    return result.reset_index(drop=True)
