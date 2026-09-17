# -*- coding: utf-8 -*-
"""
第 1 课：认识数据

目标：在清洗之前，先搞清楚「这份数据到底长什么样」。

为什么必须先做这步？
    不了解数据就开始清洗，等于闭着眼睛做手术。
    你得先知道每一列的业务含义，才能判断哪些异常"该删"、哪些"该留"。

运行方式（在仓库根目录 dm2026/ 下执行）：
    python src/01_数据探查.py
"""

from pathlib import Path

import pandas as pd

# 让输出别换行、别省略列，方便在终端里看
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 50)

LINE = "=" * 72

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "online_retail_II.xlsx"

print(LINE)
print("读取 Excel —— 约 100 万行，第一次读会比较慢，耐心等 1~2 分钟")
print(LINE)

# sheet_name=None 表示「读取所有工作表」，返回 {表名: DataFrame} 的字典
sheets = pd.read_excel(RAW, sheet_name=None, engine="openpyxl")

print(f"\n发现 {len(sheets)} 个工作表：")
total = 0
for name, df in sheets.items():
    total += len(df)
    print(f"  「{name}」 -> {len(df):>9,} 行 × {df.shape[1]} 列")
print(f"  合计            {total:>9,} 行")

first = list(sheets.values())[0]

print("\n" + LINE)
print("① 列名与数据类型")
print(LINE)
print(first.dtypes.to_string())

print("\n" + LINE)
print("② 前 5 行原始数据")
print(LINE)
print(first.head().to_string())

print("\n" + LINE)
print("③ 每列缺失值情况")
print(LINE)
missing = first.isna().sum()
pct = (missing / len(first) * 100).round(2)
for col in first.columns:
    bar = "#" * int(pct[col] / 2)
    print(f"  {col:<14} 缺失 {missing[col]:>8,} 条 ({pct[col]:>5.2f}%) {bar}")

print("\n" + LINE)
print("④ 数值列的基本统计")
print(LINE)
print(first.describe().to_string())

print("\n" + LINE)
print("⑤ 几个需要立刻警惕的信号")
print(LINE)

qty = first["Quantity"]
price = first["Price"]

print(f"  Quantity 为负数的行       : {(qty < 0).sum():>9,}  （这些是退货，不是错误！）")
print(f"  Quantity 为 0 的行        : {(qty == 0).sum():>9,}")
print(f"  Price 为负数的行          : {(price < 0).sum():>9,}  （人工调整/坏账）")
print(f"  Price 为 0 的行           : {(price == 0).sum():>9,}  （赠品？测试单？）")
print(f"  Customer ID 缺失的行      : {first['Customer ID'].isna().sum():>9,}  （不知道是谁买的）")

invoice = first["Invoice"].astype(str)
print(f"  Invoice 以 C 开头的行     : {invoice.str.startswith('C').sum():>9,}  （C = Cancellation，取消单）")

print("\n" + LINE)
print("第 1 课结束。带着这些问题进入第 2 课：")
print("  · 缺失 Customer ID 的订单，该删掉还是保留？")
print("  · 负数的 Quantity 是错误还是退货？怎么区分？")
print("  · Invoice 以 C 开头的单子要怎么处理？")
print(LINE)
