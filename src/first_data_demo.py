# -*- coding: utf-8 -*-
"""
第一个文件：环境自检 + 一个最小的「数据分析闭环」

运行方式：
    python first_data_demo.py

这个文件故意做得很小，但它一次串起了三件事：
    1. 确认 Python 和各个库能正常 import
    2. 用 pandas 做分组聚合
    3. 用 SQL 做同一件事 —— 对照着看，SQL 就没那么抽象了
"""

import sqlite3
import sys

import matplotlib
import numpy as np
import pandas as pd
import sklearn

LINE = "=" * 48

print(LINE)
print("【环境自检】")
print(f"Python        {sys.version.split()[0]}")
print(f"numpy         {np.__version__}")
print(f"pandas        {pd.__version__}")
print(f"scikit-learn  {sklearn.__version__}")
print(f"matplotlib    {matplotlib.__version__}")
print(f"sqlite3       {sqlite3.sqlite_version}")
print(LINE)

# ---------------------------------------------------------------
# 1. 造一份小小的「房源」数据
#    真实项目里这些数据来自 CSV / 数据库 / 爬虫，这里先手写
# ---------------------------------------------------------------
df = pd.DataFrame(
    {
        "区域": ["武侯区", "成华区", "武侯区", "锦江区", "成华区", "锦江区"],
        "面积": [89.0, 76.5, 120.0, 65.0, 95.5, 143.0],
        "单价": [18500, 15200, 21000, 24000, 14800, 26500],
    }
)
df["总价万"] = (df["面积"] * df["单价"] / 10000).round(1)

print("\n【原始数据】")
print(df.to_string(index=False))

# ---------------------------------------------------------------
# 2. pandas 分组聚合 —— 按区域算套数和均价
# ---------------------------------------------------------------
summary = (
    df.groupby("区域")
    .agg(套数=("总价万", "size"), 均价万=("总价万", "mean"))
    .round(1)
)
print("\n【pandas 做的分组聚合】")
print(summary.to_string())

# ---------------------------------------------------------------
# 3. 同一件事，用 SQL 再做一遍
#    to_sql 把 DataFrame 塞进一个内存数据库，表名 house
#    然后用 GROUP BY 聚合 —— 和你以后查 MySQL 的写法一模一样
# ---------------------------------------------------------------
con = sqlite3.connect(":memory:")
df.to_sql("house", con, index=False)

sql = """
SELECT 区域,
       COUNT(*)            AS 套数,
       ROUND(AVG(总价万), 1) AS 均价万
FROM house
GROUP BY 区域
ORDER BY 均价万 DESC
"""

print("\n【SQL 做的同一件事 —— 你在学的那个】")
print(pd.read_sql(sql, con).to_string(index=False))
con.close()

print("\n" + LINE)
print("环境正常：pandas 和 SQL 都跑通了")
print(LINE)
