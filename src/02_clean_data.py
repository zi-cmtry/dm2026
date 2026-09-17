# -*- coding: utf-8 -*-
"""
第 2 课：数据清洗

━━━ 这一课最重要的一句话 ━━━
    清洗的目标不是"得到一份干净数据"，
    而是"根据不同分析目的，得到几份各自合适的数据"。

━━━ 具体决策（也是面试会被问到的）━━━
    1. Excel 读一次太慢(70秒) → 立刻转存 CSV 缓存(3秒)
    2. 不急着删数据，先给每一行"打标签"，分类之后再按需筛选
    3. Customer ID 缺失的 20% 不能删！它们含真实销售额
       - 做「交易分析」（销售额/商品排名）→ 保留
       - 做「用户分析」（RFM/留存/复购）→ 必须排除，因为不知道是谁
    4. 取消单（Invoice 以 C 开头）单独存一张表，用于算取消率

运行方式（仓库根目录下）：
    python src/02_clean_data.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "online_retail_II.xlsx"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

LINE = "=" * 72
CACHE = OUT / "raw_combined.csv"


def section(title: str) -> None:
    print("\n" + LINE)
    print(title)
    print(LINE)


# ---------------------------------------------------------------
# 步骤 1：读取 + 立刻缓存成 CSV
#   第一次跑要读 Excel（慢），之后直接读 CSV（快）
# ---------------------------------------------------------------
section("步骤 1：读取数据")

if CACHE.exists():
    print(f"发现缓存 {CACHE.name}，直接读取（秒开）")
    df = pd.read_csv(CACHE, parse_dates=["InvoiceDate"])
else:
    print("第一次运行：读取 Excel，约需 1~2 分钟……")
    sheets = pd.read_excel(RAW, sheet_name=None, engine="openpyxl")
    df = pd.concat(sheets.values(), ignore_index=True)
    # 列名规范化：去掉空格，方便后面写 SQL
    df.columns = [c.strip().replace(" ", "_") for c in df.columns]
    df.to_csv(CACHE, index=False)
    print(f"已缓存为 {CACHE.name}（以后读它就快了）")

print(f"原始数据：{len(df):,} 行 × {df.shape[1]} 列")
print(f"日期范围：{df['InvoiceDate'].min()}  ~  {df['InvoiceDate'].max()}")


# ---------------------------------------------------------------
# 步骤 2：派生新列
#   原始数据里没有"金额"，得自己算 —— 这是分析的基础指标
# ---------------------------------------------------------------
section("步骤 2：派生列（Amount 金额、IsCancelled 是否取消）")

df["Amount"] = (df["Quantity"] * df["Price"]).round(2)
df["IsCancelled"] = df["Invoice"].astype(str).str.upper().str.startswith("C")

print("新增两列：")
print("  Amount      = Quantity × Price   （销售额，原数据里没有）")
print("  IsCancelled = Invoice 是否以 C 开头（C = Cancellation 取消单）")


# ---------------------------------------------------------------
# 步骤 3：打标签，而不是删除
#   np.select 按顺序判断，命中第一个条件就停
# ---------------------------------------------------------------
section("步骤 3：给每一行打类型标签（关键：不删数据）")

# ⚠️ np.select 是「按顺序匹配，命中即停」。
#    所以条件的先后顺序会直接改变结果，必须穷举所有情况并排好优先级。
#    第一版我把 (Quantity < 0) 排在 (Price <= 0) 前面，
#    结果「负数量 + 零价格」的库存核销行被误标成了"退货"。
df["RowType"] = np.select(
    [
        df["IsCancelled"],                            # ① 取消单（C 开头）
        (df["Quantity"] < 0) & (df["Price"] > 0),     # ② 有金额的退货
        (df["Quantity"] < 0) & (df["Price"] == 0),    # ③ 库存核销（不涉及钱）
        (df["Quantity"] >= 0) & (df["Price"] <= 0),   # ④ 赠品 / 零价单
    ],
    [
        "取消单",
        "退货(有金额)",
        "库存核销",
        "零价或负价",
    ],
    default="正常销售",
)

# 验证表：每一类的「单价区间」都必须符合它的业务含义，
# 对不上就说明分类逻辑写错了。
summary = (
    df.groupby("RowType")
    .agg(
        行数=("RowType", "size"),
        占比=("RowType", lambda s: round(len(s) / len(df) * 100, 2)),
        金额合计=("Amount", lambda s: round(s.sum(), 2)),
        数量合计=("Quantity", "sum"),
        最低单价=("Price", "min"),
        最高单价=("Price", "max"),
    )
    .sort_values("行数", ascending=False)
)
print(summary.to_string())
print()
print("↑ 读这张表的方法：每一类的「单价区间」都应该对得上它的标签。")
print("  「库存核销」如果单价不是 0，或者「正常销售」出现负单价，就是分类写错了。")


# ---------------------------------------------------------------
# 步骤 4：按用途拆分数据
# ---------------------------------------------------------------
section("步骤 4：按分析用途拆分")

# ① 交易分析用：所有真实成交（含匿名客户）
sales = df[df["RowType"] == "正常销售"].copy()

# ② 用户分析用：真实成交 且 知道是谁买的
sales_known = sales[sales["Customer_ID"].notna()].copy()

# ③ 取消单：单独存，用于算取消率
cancelled = df[df["IsCancelled"]].copy()

lost_revenue = sales[sales["Customer_ID"].isna()]["Amount"].sum()

print(f"① 交易分析表 sales                  : {len(sales):>9,} 行   金额 {sales['Amount'].sum():>15,.2f}")
print(f"② 用户分析表 sales_known            : {len(sales_known):>9,} 行   金额 {sales_known['Amount'].sum():>15,.2f}")
print(f"③ 取消单表   cancelled              : {len(cancelled):>9,} 行   金额 {cancelled['Amount'].sum():>15,.2f}")
print()
print(f"⚠️  被排除在用户分析之外的匿名成交金额：{lost_revenue:,.2f}")

if sales["Amount"].sum() > 0:
    print(f"    占全部销售额的 {lost_revenue / sales['Amount'].sum() * 100:.2f}%")
print()
print("    ↑ 这就是为什么不能简单删掉它们：")
print("      如果删了，交易分析会凭空少掉这一大块营收。")
print("      但做 RFM 时又必须排除 —— 因为不知道这些是谁买的。")
print("      同一份原始数据，两种分析，两种取舍。")


# ---------------------------------------------------------------
# 步骤 5：落盘
# ---------------------------------------------------------------
section("步骤 5：保存清洗结果")

sales.to_csv(OUT / "sales.csv", index=False)
sales_known.to_csv(OUT / "sales_known.csv", index=False)
cancelled.to_csv(OUT / "cancellations.csv", index=False)

for name in ["sales.csv", "sales_known.csv", "cancellations.csv"]:
    p = OUT / name
    print(f"  {name:<22} {p.stat().st_size / 1024 / 1024:>7.2f} MB")


# ---------------------------------------------------------------
# 步骤 6：清洗前后对比
# ---------------------------------------------------------------
section("步骤 6：清洗前后对比（写报告时要用）")

n_before = len(df)
n_after = len(sales)

print(f"清洗前总行数        : {n_before:>10,}")
print(f"正常销售行数        : {n_after:>10,}  ({n_after / n_before * 100:.2f}%)")
print(f"被排除的行数        : {n_before - n_after:>10,}  ({(n_before - n_after) / n_before * 100:.2f}%)")
print()
print(f"清洗前总金额(含退货) : {df['Amount'].sum():>15,.2f}")
print(f"清洗后销售额        : {sales['Amount'].sum():>15,.2f}")
print()
print(f"独立订单数          : {sales['Invoice'].nunique():>10,}")
print(f"独立商品数          : {sales['StockCode'].nunique():>10,}")
print(f"已知客户数          : {sales_known['Customer_ID'].nunique():>10,.0f}")
print(f"覆盖国家数          : {sales['Country'].nunique():>10,}")

print("\n" + LINE)
print("第 2 课结束。下一课：把这些数据装进 SQLite，开始写 SQL。")
print(LINE)
