"""Schema-driven ledger cleaning pipeline."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import polars as pl

from ledger_config import (
    ConfigMap,
    DrcrConfig,
    FieldSpec,
    PipelineConfig,
    load_config,
    load_pipeline_config,
    resolve_config_dtype,
)


@dataclass(frozen=True)
class ResolvedFieldSpec:
    target: str
    source_columns: tuple[str, ...]
    dtype: str
    kind: str = "single"
    prefix: str | None = None

    def source_dtype_requirements(self) -> tuple[tuple[str, str], ...]:
        return tuple((column, self.dtype) for column in self.source_columns)

    def build_output_expression(self) -> pl.Expr:
        return pl.col(self.source_columns[0]).alias(self.target)

    def build_prefix_expression(self) -> pl.Expr | None:
        if self.prefix is None:
            return None
        return _build_prefix_expression(self.target, self.prefix)


@dataclass(frozen=True)
class ColumnLayout:
    columns: tuple[str, ...]
    positions: dict[str, int]
    non_null_by_col: dict[str, int]

    @classmethod
    def from_frame(cls, df: pl.DataFrame) -> "ColumnLayout":
        columns = tuple(df.columns)
        nulls = df.null_count().row(0)
        return cls(
            columns=columns,
            positions={name: idx for idx, name in enumerate(columns)},
            non_null_by_col={
                col: df.height - int(nnull) for col, nnull in zip(columns, nulls)
            },
        )


class LedgerPipeline:
    """High-level orchestrator for the ledger normalization stages."""

    def __init__(self, config: PipelineConfig):
        self.config = config

    @classmethod
    def from_config_map(cls, config: ConfigMap) -> "LedgerPipeline":
        return cls(load_pipeline_config(config))

    def run(
        self, file: str | Path
    ) -> tuple[pl.DataFrame, tuple[ResolvedFieldSpec, ...]]:
        data = load_ledger_data(file)
        return self.transform(data)

    def transform(
        self, data: pl.DataFrame
    ) -> tuple[pl.DataFrame, tuple[ResolvedFieldSpec, ...]]:
        data = standardize_string_columns(data)
        resolved_specs = resolve_field_specs(data, self.config.field_specs)
        typed_data = process_column_dtypes(data, resolved_specs)
        output = build_output_frame(typed_data, resolved_specs)
        output = apply_resolved_prefixes(output, resolved_specs)

        if self.config.drcr is not None:
            output = set_drcr_sign(output, drcr_mapping=self.config.drcr)
            output = drop_zero_amount_rows(output, self.config.drcr.amount_columns)

        return output, resolved_specs


def load_ledger_data(file: str | Path) -> pl.DataFrame:
    """Load the source ledger workbook."""

    return pl.read_excel(source=str(file))


def pl_info(df: pl.DataFrame) -> None:
    """Print dataframe info, similar to pandas' ``df.info()``."""

    print("Shape:", df.shape)
    nulls = df.null_count().row(0)
    print(f"{'Column':<20} {'dtype':<10} {'non-null':>10} {'null':>10}")
    for col, dtype, nnull in zip(df.columns, df.dtypes, nulls):
        print(
            f"{col:<20} {str(dtype):<10} {int(df.height - nnull):>10} {int(nnull):>10}"
        )
    print("Memory (bytes):", df.estimated_size())


def standardize_string_columns(ledger_df: pl.DataFrame) -> pl.DataFrame:
    """Trim whitespace and convert empty strings to nulls in all string columns."""

    string_cols = [col for col, dtype in ledger_df.schema.items() if dtype == pl.Utf8]
    if not string_cols:
        return ledger_df

    return ledger_df.with_columns(
        [
            pl.when(pl.col(col).str.strip_chars() == "")
            .then(None)
            .otherwise(pl.col(col).str.strip_chars())
            .alias(col)
            for col in string_cols
        ]
    )


def dtype_matches(actual_dtype: pl.DataType, target_dtype: pl.DataType) -> bool:
    """Compare dtypes with a safe string fallback."""

    return (
        actual_dtype == target_dtype
        or str(actual_dtype).lower() == str(target_dtype).lower()
    )


def _resolve_right_neighbor_column(layout: ColumnLayout, anchor_col: str) -> str:
    """Find the validated right-neighbor column for an anchor column."""

    if anchor_col not in layout.positions:
        raise ValueError(f"{anchor_col} 信息不匹配！")

    anchor_idx = layout.positions[anchor_col]
    if anchor_idx + 1 >= len(layout.columns):
        raise ValueError(f"{anchor_col} 后面没有可匹配的匿名列！")

    successor_col = layout.columns[anchor_idx + 1]
    if layout.non_null_by_col[anchor_col] != layout.non_null_by_col[successor_col]:
        raise ValueError(f"{anchor_col} 信息不匹配！")

    return successor_col


def _resolve_single_field(spec: FieldSpec, layout: ColumnLayout) -> ResolvedFieldSpec:
    source_col = str(spec.source)
    if source_col not in layout.positions:
        raise ValueError(f"Missing required source column: {source_col}")

    return ResolvedFieldSpec(
        target=spec.target,
        source_columns=(source_col,),
        dtype=spec.dtype,
        kind=spec.kind,
        prefix=spec.prefix,
    )


def _resolve_right_neighbor_field(
    spec: FieldSpec, layout: ColumnLayout
) -> ResolvedFieldSpec:
    allowed_targets = {"vendor_name", "customer_name"}
    if spec.target not in allowed_targets:
        raise ValueError(
            f"right_neighbor only supports targets {sorted(allowed_targets)}, got '{spec.target}'"
        )

    source_col = _resolve_right_neighbor_column(layout, str(spec.source))
    return ResolvedFieldSpec(
        target=spec.target,
        source_columns=(source_col,),
        dtype=spec.dtype,
        kind=spec.kind,
        prefix=spec.prefix,
    )


FIELD_RESOLVERS: dict[str, Callable[[FieldSpec, ColumnLayout], ResolvedFieldSpec]] = {
    "single": _resolve_single_field,
    "right_neighbor": _resolve_right_neighbor_field,
}


def resolve_field_specs(
    df: pl.DataFrame, field_specs: Sequence[FieldSpec]
) -> tuple[ResolvedFieldSpec, ...]:
    """Resolve configured field specs against the actual dataframe columns."""

    layout = ColumnLayout.from_frame(df)
    resolved: list[ResolvedFieldSpec] = []
    seen_targets: set[str] = set()

    for spec in field_specs:
        if spec.target in seen_targets:
            raise ValueError(f"Duplicate target field in config: {spec.target}")
        seen_targets.add(spec.target)

        try:
            resolver = FIELD_RESOLVERS[spec.kind]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported field kind '{spec.kind}' for target '{spec.target}'"
            ) from exc

        resolved.append(resolver(spec, layout))

    return tuple(resolved)


def _build_source_dtype_map(
    resolved_specs: Sequence[ResolvedFieldSpec],
) -> dict[str, str]:
    """Build a source-column-to-dtype map from resolved specs."""

    source_dtypes: dict[str, str] = {}
    for spec in resolved_specs:
        for source_col, expected_dtype in spec.source_dtype_requirements():
            existing = source_dtypes.get(source_col)
            if existing is not None and existing != expected_dtype:
                raise ValueError(
                    f"Conflicting dtype requirements for source column '{source_col}': {existing} vs {expected_dtype}"
                )
            source_dtypes[source_col] = expected_dtype
    return source_dtypes


def process_column_dtypes(
    df: pl.DataFrame, resolved_specs: Sequence[ResolvedFieldSpec]
) -> pl.DataFrame:
    """Cast source columns to their configured dtypes."""

    cast_exprs: list[pl.Expr] = []
    for col, expected_dtype in _build_source_dtype_map(resolved_specs).items():
        if col not in df.columns:
            raise ValueError(f"Source column '{col}' not found during type validation")

        target_dtype = resolve_config_dtype(expected_dtype)
        actual_dtype = df.schema[col]
        if dtype_matches(actual_dtype, target_dtype):
            continue

        cast_exprs.append(pl.col(col).cast(target_dtype).alias(col))

    return df.with_columns(cast_exprs) if cast_exprs else df


def build_output_frame(
    df: pl.DataFrame, resolved_specs: Sequence[ResolvedFieldSpec]
) -> pl.DataFrame:
    """Build the canonical output frame from resolved field specs."""
    return df.select([spec.build_output_expression() for spec in resolved_specs])


def _build_prefix_expression(column: str, prefix_value: str) -> pl.Expr:
    value_expr = pl.col(column).cast(pl.Utf8).str.strip_chars()
    return (
        pl.when(value_expr.is_not_null() & (value_expr != ""))
        .then(pl.concat_str([pl.lit(str(prefix_value)), value_expr]))
        .otherwise(None)
        .alias(column)
    )


def apply_resolved_prefixes(
    df: pl.DataFrame, resolved_specs: Sequence[ResolvedFieldSpec]
) -> pl.DataFrame:
    """Apply prefixes declared on resolved specs to the output frame."""

    prefix_exprs = [
        expr
        for spec in resolved_specs
        if spec.target in df.columns
        for expr in [spec.build_prefix_expression()]
        if expr is not None
    ]
    return df.with_columns(prefix_exprs) if prefix_exprs else df


def set_drcr_sign(
    df: pl.DataFrame, drcr_mapping: DrcrConfig | None = None
) -> pl.DataFrame:
    """Set the sign of amount columns based on the DR/CR column."""

    if drcr_mapping is None:
        pipeline_config = load_pipeline_config(load_config())
        drcr_mapping = pipeline_config.drcr
        if drcr_mapping is None:
            return df

    if drcr_mapping.column not in df.columns:
        raise ValueError(f"DR/CR column '{drcr_mapping.column}' not found")

    sign_exprs: list[pl.Expr] = []
    for col in drcr_mapping.amount_columns:
        if col not in df.columns:
            continue

        sign_exprs.append(
            pl.when(pl.col(drcr_mapping.column) == drcr_mapping.debit)
            .then(pl.col(col))
            .when(pl.col(drcr_mapping.column) == drcr_mapping.credit)
            .then(-pl.col(col))
            .otherwise(pl.col(col))
            .alias(col)
        )

    return df.with_columns(sign_exprs) if sign_exprs else df


def drop_zero_amount_rows(df: pl.DataFrame, amount_cols: Sequence[str]) -> pl.DataFrame:
    """Drop rows where all specified amount columns are zero."""

    existing_amount_cols = [col for col in amount_cols if col in df.columns]
    if not existing_amount_cols:
        return df

    condition = pl.any_horizontal(
        [pl.col(col).fill_null(0) != 0 for col in existing_amount_cols]
    )
    return df.filter(condition)


def process_ledger(
    file: str | Path, config: ConfigMap | None = None
) -> tuple[pl.DataFrame, tuple[ResolvedFieldSpec, ...]]:
    """Load and standardize ledger data, then project it to the canonical schema."""

    pipeline = LedgerPipeline.from_config_map(
        load_config() if config is None else config
    )
    return pipeline.run(file)


if __name__ == "__main__":
    excel_file = r"D:\Temp\yihai_data\ledger\重庆供应链_FY25_1-12.XLSX"
    processed_data, resolved_specs = process_ledger(excel_file)
    print("Processed data shape:", processed_data.shape)
    # print("Resolved field specs:", resolved_specs)
    processed_data.write_parquet("processed_ledger.parquet")
