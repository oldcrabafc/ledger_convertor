'''
convert KH excel ledger to parquet format for faster loading and processing in the future.
'''

from pathlib import Path
import pandas as pd


DROP_COLS = ['业务范围', '客户_2', '客户_3']
RENAME_COLS = {
    '凭证编号': 'voucher_no',
    '凭证日期': 'voucher_date',
    '过帐日期': 'posting_date',
    '总帐帐目': 'ac_code',
    'unnamed:_8': 'ac_caption',
    '本币金额': 'amount',
    '客户': 'customer_code',
    '客户_1': 'customer_name',
    '供应商': 'supplier_code',
    '供应商_1': 'supplier_name',
    '文本': 'summary'
}


def normalize_column_names(columns) -> list[str]:
    """Normalize column labels by trimming spaces and replacing separators."""
    return [str(col).strip().lower().replace(" ", "_").replace(".", "_") for col in columns]


def load_and_cache_excel(file_path: str | Path) -> None:
    """Load an Excel file into a pandas DataFrame and cache it as a pickle file."""
    file_path = Path(file_path)
    df = pd.read_excel(file_path, dtype=str)
    cache_path = file_path.with_suffix('.pkl')
    df.to_pickle(cache_path)


def load_pickle(file_path: str | Path) -> pd.DataFrame:
    """Load a pickled DataFrame from a file."""
    return pd.read_pickle(file_path)


def is_in_columns(df: pd.DataFrame, columns: list[str]) -> bool:
    """Check if all specified columns are in the DataFrame."""
    return all(col in df.columns for col in columns)


def get_missing_columns(df: pd.DataFrame, columns) -> list[str]:
    """Return columns that are missing from the DataFrame."""
    return [col for col in columns if col not in df.columns]


def drop_and_rename_columns(df: pd.DataFrame, drop_cols=DROP_COLS,
                            rename_cols=RENAME_COLS) -> pd.DataFrame:
    """Drop unnecessary columns and rename the remaining columns."""
    missing = get_missing_columns(df, rename_cols.keys())
    if missing:
        raise ValueError(f"Some columns to rename are not in the DataFrame: {missing}")
    df = df.drop(columns=drop_cols, errors='ignore')
    df = df.rename(columns=rename_cols)
    return df


def covnert_date_columns(df: pd.DataFrame, date_col: list[str]) -> pd.DataFrame:
    """Convert specified columns to datetime format."""
    missing = get_missing_columns(df, date_col)
    if missing:
        raise ValueError(f"Some date columns are not in the DataFrame: {missing}")
    for col in date_col:
        df[col] = pd.to_datetime(df[col], errors='coerce')
    return df


def convert_numeric_columns(
    df: pd.DataFrame,
    numeric_cols: list[str],
    decimal_places: int = 2,
) -> pd.DataFrame:
    """Convert specified columns to numeric format, removing commas and rounding."""
    missing = get_missing_columns(df, numeric_cols)
    if missing:
        raise ValueError(f"Some numeric columns are not in the DataFrame: {missing}")
    for col in numeric_cols:
        cleaned = df[col].astype('string').str.replace(',', '', regex=False)
        df[col] = pd.to_numeric(cleaned, errors='coerce').round(decimal_places)
    return df


def any_duplicate_voucher_no(df: pd.DataFrame, month_col: str = 'posting_date', voucher_col: str = 'voucher_no') -> bool:
    """Check if there are any duplicate voucher numbers in different months in the DataFrame."""
    if voucher_col not in df.columns:
        raise ValueError(f"Column '{voucher_col}' is not in the DataFrame.")
    if month_col not in df.columns:
        raise ValueError(f"Column '{month_col}' is not in the DataFrame.")

    # Normalize to month granularity, then check whether any voucher spans multiple months.
    month_series = pd.to_datetime(df[month_col], errors='coerce').dt.to_period('M')
    valid = df[voucher_col].notna() & month_series.notna()
    if not valid.any():
        return False

    month_count = month_series.loc[valid].groupby(df.loc[valid, voucher_col]).nunique()
    return (month_count > 1).any()

def clean_ledger(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and standardize the ledger DataFrame."""

    df.columns = normalize_column_names(df.columns)
    df = drop_and_rename_columns(df)
    df = covnert_date_columns(df, date_col=['voucher_date', 'posting_date'])
    df = convert_numeric_columns(df, numeric_cols=['amount'])
    if any_duplicate_voucher_no(df):
        print("Warning: There are duplicate voucher numbers across different months.")
    else:
        print("No duplicate voucher numbers across different months.")
    return df




if __name__ == "__main__":
    excel_file = Path("D:/Temp/logistic/GZH-LG2/EG-总账行项目1-12.XLSX")
    # load_and_cache_excel(excel_file)
    pickle_file = excel_file.with_suffix('.pkl')
    df = load_pickle(pickle_file)
    df = clean_ledger(df)
    # print(df.info())
    # # print(df.head(5))
    # for col in df.columns:
    #     print(f"{col}: {df[col].dtype}")
    parquet_file = excel_file.with_suffix('.parquet')
    df.to_parquet(parquet_file, index=False)
