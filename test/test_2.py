from pathlib import Path

import pandas as pd

INPUT_DIR = Path("D:/Temp/test_data/ledgers/温州工厂")

# amount_local 已由 apply_drcr_sign 写好符号：S(借)为正，H(贷)为负，
# 所以单个凭证所有行相加应接近 0，不需要再按 drcr 分别取数。
BALANCE_TOL = 0.01

OUTPUT_CSV = INPUT_DIR / "balance_check_unbalanced.csv"


def view_pickle(input_dir: Path = INPUT_DIR):
    for file in input_dir.glob("*.pkl"):
        print(file.name)
        print(pd.read_pickle(file).columns)


def unbalanced_vouchers(df: pd.DataFrame) -> pd.DataFrame:
    """按凭证汇总借贷金额，返回不平（|差额| > BALANCE_TOL）的凭证。

    输出每个凭证的 S(借)/H(贷) 合计与净差额；若出现 S/H 以外的 drcr 值，
    会多出对应列并计入差额，便于发现符号没被正确写入的行。
    """
    totals = pd.pivot_table(
        df,
        index="voucher_id",
        columns="drcr",
        values="amount_local",
        aggfunc="sum",
        fill_value=0,
    )
    totals["diff"] = totals.sum(axis=1)
    return totals.loc[(totals["diff"] > BALANCE_TOL) | (totals["diff"] < -BALANCE_TOL)]


def view_parquet(input_dir: Path = INPUT_DIR, output_csv: Path = OUTPUT_CSV):
    frames = []
    for file in input_dir.glob("*.parquet"):
        # 只读校验用到的列，比整表 36 列快很多
        file_df = pd.read_parquet(
            file, columns=["voucher_id", "drcr", "amount_local"]
        )
        bad = unbalanced_vouchers(file_df)
        print(
            file.name,
            f"行数={len(file_df):,}",
            f"凭证数={file_df['voucher_id'].nunique():,}",
            f"不平={len(bad)}",
        )
        if not bad.empty:
            bad.insert(0, "source_parquet", file.name)
            frames.append(bad)

    if not frames:
        print("所有凭证借贷平衡，无需导出")
        return

    result = pd.concat(frames).reset_index()
    # 按文件名、凭证号排序
    result = result.sort_values(["source_parquet", "voucher_id"], kind="stable")
    result.to_csv(output_csv, index=False, encoding="utf-8-sig", float_format="%.2f")
    print(f"不平凭证共 {len(result)} 条 -> {output_csv}")


view_parquet()
