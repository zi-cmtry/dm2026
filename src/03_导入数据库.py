# -*- coding: utf-8 -*-
"""
第 3 课：把数据装进 SQLite —— 第一次真正写 SQL

━━━ 为什么要装进数据库？━━━
    1. SQL 是数据分析岗最重要的一项技能，面试必考、工作天天用
    2. 数据落库后可以加索引，几百万行也能毫秒级查询
    3. 一次导入，之后随便查，不用每次重新读 CSV

━━━ 这一课你会见到 SQL 的三大类语句 ━━━
    DDL (定义)  : CREATE TABLE / CREATE INDEX
    DML (操作)  : INSERT
    DQL (查询)  : SELECT

运行方式（仓库根目录下）：
    python src/03_导入数据库.py
"""

import sqlite3
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
DB = PROC / "retail.db"

LINE = "=" * 72


def section(title: str) -> None:
    print("\n" + LINE)
    print(title)
    print(LINE)


# ---------------------------------------------------------------
# 步骤 1：读取清洗结果
# ---------------------------------------------------------------
section("步骤 1：读取清洗后的 CSV")

TABLES = ["sales", "sales_known", "cancellations"]
frames: dict[str, pd.DataFrame] = {}

for name in TABLES:
    # 显式声明文本列的 dtype —— 不是因为有 bug，而是为了让行为「可预测」。
    # CSV 没有类型信息，pandas 只能靠猜：
    #   Invoice 里有 '489434' 也有 'C489434'，它会先猜成数字、再发现字符串，
    #   于是分块推断出「混合类型」并抛 DtypeWarning。
    # 我们明知这列是标识符（不是数字），就直接告诉它，别让它猜。
    df = pd.read_csv(
        PROC / f"{name}.csv",
        parse_dates=["InvoiceDate"],
        dtype={
            "Invoice": str,
            "StockCode": str,
            "Description": str,
            "Country": str,
        },
    )
    frames[name] = df
    print(f"  {name:<16} {len(df):>10,} 行 × {df.shape[1]} 列")


# ---------------------------------------------------------------
# 步骤 2：建表
#   注意：SQLite 有「类型亲和性」，但显式写出类型仍然非常重要 ——
#   它既是文档（告诉读代码的人这列是什么），也影响存储和索引效率。
# ---------------------------------------------------------------
section("步骤 2：CREATE TABLE —— 显式声明每一列的类型")

SCHEMA = """
CREATE TABLE {table} (
    Invoice      TEXT,      -- 发票号；C 开头 = 取消单
    StockCode    TEXT,      -- 商品编码
    Description  TEXT,      -- 商品名称（可能缺失）
    Quantity     INTEGER,   -- 数量；负数表示退货/核销
    InvoiceDate  TEXT,      -- 时间，存成 'YYYY-MM-DD HH:MM:SS' 字符串
    Price        REAL,      -- 单价
    Customer_ID  REAL,      -- 客户编号；可为 NULL
    Country      TEXT,      -- 国家
    Amount       REAL,      -- 派生列 = Quantity * Price
    IsCancelled  INTEGER,   -- 0 / 1
    RowType      TEXT       -- 行类型标签
);
"""

print("我们要建的表结构（拿 sales 举例）：")
print(SCHEMA.format(table="sales"))

print("""
📌 SQL 类型小抄（SQLite 版）：
   TEXT    文本       INTEGER  整数
   REAL    浮点数     BLOB     二进制
   SQLite 没有专门的「日期类型」，所以我们把时间存成 ISO 字符串
   —— 这样排序和比较依然是正确的（'2020-01-02' < '2020-01-03'）
""")


# ---------------------------------------------------------------
# 步骤 3：导入数据
# ---------------------------------------------------------------
section("步骤 3：INSERT —— 把数据灌进去")

con = sqlite3.connect(DB)

for name in TABLES:
    df = frames[name].copy()

    # ⚠️ 两个必须做的转换：
    #   1) datetime -> 字符串（SQLite 不认 datetime 对象）
    #   2) NaN -> None（否则会存成 'nan' 字符串，后面查询全乱套）
    df["InvoiceDate"] = df["InvoiceDate"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df["IsCancelled"] = df["IsCancelled"].astype(int)
    df = df.astype(object).where(pd.notna(df), None)

    cols = list(df.columns)
    colnames = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(["?"] * len(cols))

    t0 = time.time()
    con.execute(f'DROP TABLE IF EXISTS "{name}"')
    con.execute(SCHEMA.format(table=name))
    con.executemany(
        f'INSERT INTO "{name}" ({colnames}) VALUES ({placeholders})',
        df.itertuples(index=False, name=None),
    )
    con.commit()
    elapsed = time.time() - t0

    n = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    print(f"  {name:<16} 导入 {n:>10,} 行   耗时 {elapsed:.1f} 秒")


# ---------------------------------------------------------------
# 步骤 4：建索引
# ---------------------------------------------------------------
section("步骤 4：CREATE INDEX —— 为什么加了索引查询会快几百倍")

INDEXES = [
    ("idx_sales_invoice", "sales", "Invoice"),
    ("idx_sales_customer", "sales", "Customer_ID"),
    ("idx_sales_date", "sales", "InvoiceDate"),
    ("idx_sales_stock", "sales", "StockCode"),
    ("idx_known_customer", "sales_known", "Customer_ID"),
    ("idx_known_date", "sales_known", "InvoiceDate"),
]

for idx_name, table, column in INDEXES:
    con.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON "{table}"({column})')
    print(f"  {idx_name:<22} ON {table}({column})")
con.commit()

print("""
📌 索引是什么？
   没有索引时，数据库要「一行一行翻」找到你要的数据 —— 这叫全表扫描。
   有索引时，它像书的目录一样直接跳到位置。

   代价：索引占额外磁盘空间，且每次 INSERT 都要更新索引。
   所以不要给每一列都建索引，只给「经常出现在 WHERE / JOIN 里」的列建。
""")

con.close()


# ---------------------------------------------------------------
# 步骤 5：第一次查询，尝个鲜
# ---------------------------------------------------------------
section("步骤 5：第一次 SELECT —— 打招呼")

con = sqlite3.connect(DB)

print("【查询 1】看看表长什么样")
print("SQL> SELECT * FROM sales LIMIT 3;\n")
print(pd.read_sql("SELECT * FROM sales LIMIT 3", con).to_string(index=False))

print("\n【查询 2】一共多少行？多少笔订单？")
print("SQL> SELECT COUNT(*) AS 明细行数, COUNT(DISTINCT Invoice) AS 订单数 FROM sales;\n")
q2 = """
SELECT COUNT(*)                  AS 明细行数,
       COUNT(DISTINCT Invoice)   AS 订单数
FROM sales
"""
print(pd.read_sql(q2, con).to_string(index=False))

print("\n【查询 3】销售额 Top 5 国家")
print("SQL> SELECT Country, SUM(Amount) ... GROUP BY Country ORDER BY ... LIMIT 5;\n")
q3 = """
SELECT Country,
       ROUND(SUM(Amount), 2) AS 销售额
FROM sales
GROUP BY Country
ORDER BY 销售额 DESC
LIMIT 5
"""
print(pd.read_sql(q3, con).to_string(index=False))

con.close()

print("\n" + LINE)
print("第 3 课结束。数据库文件：data/processed/retail.db")
print("下一课：用 SQL 做真正的业务分析。")
print(LINE)
