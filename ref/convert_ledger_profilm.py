"""从序时账缓存文件读取、解析、清理并输出汇总结果。"""

import argparse
from pathlib import Path

import pandas as pd

BASE_DIR = Path("D:/Temp/test_data/ledger_cache")
DATA_DIR = BASE_DIR
DEFAULT_AMOUNT_COLUMNS = ("原币金额", "借方金额", "贷方金额")


def get_cache(file: Path | str) -> pd.DataFrame:
    """读取缓存文件并返回 DataFrame。"""
    file = Path(file)
    if not file.exists():
        raise FileNotFoundError(f"缓存文件不存在: {file}")
    return pd.read_pickle(file)


def normalize_amount_columns(df: pd.DataFrame, amount_cols: list[str] | None = None) -> pd.DataFrame:
    """将金额列转换为数值类型。"""
    df = df.copy()
    if amount_cols is None:
        amount_cols = list(DEFAULT_AMOUNT_COLUMNS)

    for col in amount_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def add_voucher_number(df: pd.DataFrame) -> pd.DataFrame:
    """根据日期和凭证字号生成凭证号。"""
    df = df.copy()
    if "日期" not in df.columns:
        return df

    if {"凭证字", "凭证号"}.issubset(df.columns):
        date_series = pd.to_datetime(df["日期"], errors="coerce")
        voucher_no = (
            date_series.dt.strftime("%y-%m").fillna("")
            + "-"
            + df["凭证字"].fillna("").astype(str)
            + "-"
            + df["凭证号"].fillna("").astype(str)
        )
        if "凭证编号" in df.columns:
            df["凭证编号"] = voucher_no
        else:
            df.insert(df.columns.get_loc("日期") + 1, "凭证编号", voucher_no)
    return df


def ffill_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """对指定列执行前向填充。"""
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = df[col].ffill()
    return df


def enrich_ledger(df: pd.DataFrame) -> pd.DataFrame:
    """执行序时账的基础清洗和字段补充。"""
    df = df.copy()

    df = ffill_columns(df, list(df.columns[:3]) + ["摘要"])
    df = normalize_amount_columns(df)
    df = add_voucher_number(df)
    # df = expand_auxiliary_columns(df)

    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"], errors="coerce")

    if "科目编码" in df.columns:
        df["一级科目编码"] = df["科目编码"].astype(str).str[:4]

    if "科目全名" in df.columns:
        df["一级科目"] = df["科目全名"].astype(str).str.split("_").str[0]
    elif "科目名称" in df.columns:
        df["一级科目"] = df["科目名称"].astype(str).str.split("_").str[0]

    return df


def remove_closing_and_voided(df: pd.DataFrame) -> pd.DataFrame:
    """移除结转本和已作废凭证。"""
    print(f"Original records: {len(df)}")

    if "摘要" in df.columns:
        df = df.loc[~df["摘要"].fillna("").astype(str).str.startswith("结转本")].copy()
        print(f"After removing closing records: {len(df)}")

    if "凭证状态" in df.columns:
        df = df[~(df["凭证状态"].fillna("").astype(str) == "已作废")].copy()
        print(f"After removing voided records: {len(df)}")

    return df


def save_ledger(df: pd.DataFrame, output_path: str | Path) -> Path:
    """按目标后缀保存 DataFrame。"""
    output_path = Path(output_path)
    print(f"Saving ledger to {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    suffix = output_path.suffix.lower()
    if suffix == ".pkl":
        df.to_pickle(output_path)
    elif suffix == ".csv":
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
    elif suffix == ".parquet":
        try:
            df.to_parquet(output_path, index=False)
        except ImportError as exc:
            raise SystemExit(
                "Parquet output requires 'pyarrow' or 'fastparquet'. "
                "Install it with: python -m pip install pyarrow\n"
                "or: python -m pip install -r requirements.txt"
            ) from exc
    else:
        raise ValueError(f"不支持的输出格式: {output_path.suffix}")

    return output_path


def resolve_output_path(
    source_path: Path,
    value: str | None,
    default_suffix: str,
    cache_dir: str | Path = DATA_DIR,
) -> Path:
    """将输出参数解析为具体文件路径。支持：文件名、文件类型、无后缀的名称。"""
    if value is None:
        return source_path.with_suffix(default_suffix)

    raw = str(value).strip()
    if not raw:
        return source_path.with_suffix(default_suffix)

    if raw.lower() in {"parquet", "csv"}:
        return source_path.with_suffix(f".{raw.lower()}")

    candidate = Path(raw)
    if candidate.suffix:
        return candidate if candidate.is_absolute() else Path(cache_dir) / candidate

    if candidate.name == raw:
        return (Path(cache_dir) / candidate).with_suffix(default_suffix)

    return candidate if candidate.is_absolute() else Path(cache_dir) / candidate


def build_output_path(
    source_file: str | Path,
    output_file: str | None = None,
    output_format: str = "parquet",
    cache_dir: str | Path = DATA_DIR,
) -> Path:
    """返回最终输出文件路径。支持输出文件名或输出格式。"""
    source_path = Path(source_file)
    if not source_path.is_absolute():
        source_path = Path(cache_dir) / source_path

    fmt = output_format.lower()
    if fmt not in {"parquet", "csv"}:
        raise ValueError(f"不支持的输出格式: {output_format}")

    if output_file is None or not str(output_file).strip():
        return source_path.with_suffix(f".{fmt}")

    raw = str(output_file).strip()
    if raw.lower() in {"parquet", "csv"}:
        return source_path.with_suffix(f".{raw.lower()}")

    candidate = Path(raw)
    if candidate.suffix:
        if candidate.is_absolute():
            return candidate
        return Path(cache_dir) / candidate

    if candidate.is_absolute():
        return candidate.with_suffix(f".{fmt}")
    return (Path(cache_dir) / candidate).with_suffix(f".{fmt}")


def main(
    source_file: str | Path,
    output_file: str | None = None,
    output_format: str = "parquet",
) -> None:
    """运行完整清洗，并保存最终清理结果。"""
    source_path = Path(source_file)
    if not source_path.is_absolute():
        source_path = Path(DATA_DIR) / source_path

    output_path = build_output_path(source_path, output_file, output_format)

    df_parsed = enrich_ledger(get_cache(source_path))
    df_parsed.info()

    df_clean = remove_closing_and_voided(df_parsed)
    df_clean.info()
    save_ledger(df_clean, output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="读取缓存的序时账并输出最终清理结果")
    parser.add_argument("source_file", help="缓存文件名（相对 BASE_DIR）或绝对路径")
    parser.add_argument(
        "output_file",
        nargs="?",
        default=None,
        help="输出文件名或输出格式，例如：result.csv、result.parquet、csv、parquet。默认与 source 同名，.parquet",
    )
    parser.add_argument(
        "--output-format",
        choices=("parquet", "csv"),
        default="parquet",
        help="输出格式，默认 parquet",
    )

    args = parser.parse_args()

    main(
        source_file=args.source_file,
        output_file=args.output_file,
        output_format=args.output_format,
    )
