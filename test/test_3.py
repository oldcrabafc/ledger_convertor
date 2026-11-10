"""从 pickle 缓存重新载入原始 Excel 数据，校验每个凭证借贷是否平衡。

pickle 是转换前的原始缓存（ledger/cache.py 用 read_excel(dtype=str) 生成），
所以这里用的是源表字段名，且金额都是未加符号的正数：
借/贷标识 -> S(贷方) / H(借方)，本位币金额 -> 金额。
平衡条件因此是 借方合计 == 贷方合计，而不是带符号求和为 0。
"""

from pathlib import Path

import pandas as pd

INPUT_DIR = Path("D:/Temp/test_data/ledgers/温州工厂")
OUTPUT_CSV = INPUT_DIR / "balance_check_raw_unbalanced.csv"

VOUCHER = "凭证编号"
DRCR = "借/贷标识"
AMOUNT = "本位币金额"
DEBIT, CREDIT = "S", "H"
BALANCE_TOL = 0.01


def load_raw(pickle_path: Path) -> pd.DataFrame:
    """读回原始行列，只保留校验用到的 3 列。"""
    frame = pd.DataFrame(pd.read_pickle(pickle_path))
    missing = [col for col in (VOUCHER, DRCR, AMOUNT) if col not in frame.columns]
    if missing:
        raise KeyError(f"{pickle_path.name} 缺少列: {missing}")

    return pd.DataFrame(
        {
            VOUCHER: frame[VOUCHER].astype("string").str.strip(),
            DRCR: frame[DRCR].astype("string").str.strip(),
            AMOUNT: frame[AMOUNT].astype("string").str.strip(),
        }
    )


def check_pickle(pickle_path: Path) -> pd.DataFrame:
    """按凭证汇总借贷合计，打印诊断并返回不平的凭证。"""
    df = load_raw(pickle_path)
    work = df.assign(amount=pd.to_numeric(df[AMOUNT], errors="coerce"))

    # 金额本应是正数，这里核实一下，避免符号/格式问题被汇总掩盖
    negative = work.loc[work["amount"] < 0]
    unparseable = work.loc[work[AMOUNT].notna() & work["amount"].isna()]
    unknown = work.loc[~work[DRCR].isin([DEBIT, CREDIT])]

    totals = pd.pivot_table(
        work,
        index=VOUCHER,
        columns=DRCR,
        values="amount",
        aggfunc="sum",
        fill_value=0,
    ).reindex(columns=[DEBIT, CREDIT], fill_value=0)
    totals = totals.rename(columns={DEBIT: "借方合计", CREDIT: "贷方合计"})
    totals["差额"] = totals["借方合计"] - totals["贷方合计"]

    bad = totals.loc[
        (totals["差额"] > BALANCE_TOL) | (totals["差额"] < -BALANCE_TOL)
    ].copy()
    bad.insert(0, "source_pickle", pickle_path.name)

    print(
        pickle_path.name,
        f"行数={len(work):,}",
        f"凭证数={len(totals):,}",
        f"不平={len(bad)}",
        f"负数金额={len(negative)}",
        f"无法解析金额={len(unparseable)}",
    )
    if len(negative):
        print("  负数金额示例:", negative[AMOUNT].head(5).tolist())
    if len(unparseable):
        print("  无法解析金额示例:", unparseable[AMOUNT].head(5).tolist())
    if len(unknown):
        codes = sorted(unknown[DRCR].dropna().unique().tolist())
        print(f"  注意: 非 {DEBIT}/{CREDIT} 标识 {len(unknown)} 行 -> {codes}")
    return bad


def check_directory(input_dir: Path = INPUT_DIR, output_csv: Path = OUTPUT_CSV):
    frames = []
    for pickle_path in sorted(input_dir.glob("*.pkl")):
        frames.append(check_pickle(pickle_path))

    total_bad = sum(len(bad) for bad in frames)
    if total_bad == 0:
        print("所有凭证借贷平衡，无需导出")
        return

    result = pd.concat(frames).reset_index()
    # 按文件名、凭证号排序
    result = result.sort_values(["source_pickle", VOUCHER], kind="stable")
    try:
        result.to_csv(output_csv, index=False, encoding="utf-8-sig", float_format="%.2f")
    except PermissionError:
        print(f"写入失败（文件被占用，多半是 Excel 开着它）: {output_csv}")
        print(result.to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
        return
    print(f"不平凭证共 {len(result)} 条 -> {output_csv}")


check_directory()
