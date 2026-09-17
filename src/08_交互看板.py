# -*- coding: utf-8 -*-
"""
第 8 课：Streamlit 交互看板

━━━ 为什么要做看板？━━━
    面试时你说"我做了个分析项目"，面试官只能听你讲。
    但如果你甩一个链接说"这是在线看板，您可以自己点"，效果完全不同。

    看板还解决一个真实问题：
        业务方不会跑 SQL。他们只要能点、能筛、能看图的界面。
        数据分析师的核心交付物之一就是看板。

━━━ 什么是 Streamlit？━━━
    用纯 Python 写网页，不用学 HTML/CSS/JS。
    数据科学领域最流行的快速出图工具。

运行方式（仓库根目录下）：
    pip install streamlit
    streamlit run src/08_交互看板.py

    浏览器会自动打开 http://localhost:8501
    按 Ctrl+C 停止服务。

━━━ 三个核心概念 ━━━
    st.cache_data   缓存查询结果，别每次刷新都重查数据库
    st.sidebar      侧边栏放筛选器
    st.columns      把页面分成几列，做 KPI 卡片
"""

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "processed" / "retail.db"

st.set_page_config(
    page_title="电商用户行为分析看板",
    page_icon="🛒",
    layout="wide",
)


# ---------------------------------------------------------------
# 数据访问层
#   @st.cache_data 是 Streamlit 最重要的性能工具：
#   同一个 SQL + 同一组参数，只查一次数据库，之后直接返回缓存。
#   没有它，每次拖动筛选器都要重查 100 万行，界面会卡死。
# ---------------------------------------------------------------
@st.cache_data(show_spinner=False)
def run_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    con = sqlite3.connect(DB)
    try:
        return pd.read_sql(sql, con, params=params)
    finally:
        con.close()


@st.cache_data(show_spinner=False)
def get_date_bounds() -> tuple:
    df = run_query("SELECT MIN(InvoiceDate) AS mn, MAX(InvoiceDate) AS mx FROM sales")
    return pd.to_datetime(df.loc[0, "mn"]).date(), pd.to_datetime(df.loc[0, "mx"]).date()


@st.cache_data(show_spinner=False)
def get_countries() -> list:
    return run_query("SELECT DISTINCT Country FROM sales ORDER BY Country")["Country"].tolist()


# ---------------------------------------------------------------
# 侧边栏筛选器
# ---------------------------------------------------------------
st.sidebar.title("🔍 筛选条件")

min_day, max_day = get_date_bounds()
all_countries = get_countries()

sel_countries = st.sidebar.multiselect(
    "国家 / 地区",
    options=all_countries,
    default=all_countries,
    help="默认全选。想只看英国就把其他的删掉。",
)

date_range = st.sidebar.date_input(
    "日期范围",
    value=(min_day, max_day),
    min_value=min_day,
    max_value=max_day,
)

st.sidebar.divider()
st.sidebar.caption(
    "数据源：UCI Online Retail II\n\n"
    "106 万行真实交易记录\n\n"
    "2009-12-01 ~ 2011-12-09"
)

# 拼装 WHERE 条件
conditions, params = ["1=1"], []
if sel_countries:
    placeholders = ", ".join(["?"] * len(sel_countries))
    conditions.append(f"Country IN ({placeholders})")
    params.extend(sel_countries)
if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    conditions.append("InvoiceDate >= ? AND InvoiceDate <= ?")
    params.extend([f"{date_range[0]} 00:00:00", f"{date_range[1]} 23:59:59"])

WHERE = " AND ".join(conditions)
P = tuple(params)


# ---------------------------------------------------------------
# 页面标题
# ---------------------------------------------------------------
st.title("🛒 电商用户行为分析看板")
st.caption("基于 UCI Online Retail II 真实交易数据 ｜ 数据探查 → 清洗 → SQL 分析 → 建模")

if not sel_countries:
    st.warning("请至少选择一个国家 / 地区。")
    st.stop()


# ---------------------------------------------------------------
# KPI 卡片
# ---------------------------------------------------------------
kpi = run_query(
    f"""
    SELECT COUNT(DISTINCT Invoice)                            AS 订单数,
           COUNT(DISTINCT Customer_ID)                        AS 客户数,
           ROUND(SUM(Amount), 2)                              AS 销售额,
           ROUND(SUM(Amount) / COUNT(DISTINCT Invoice), 2)    AS 客单价,
           SUM(Quantity)                                      AS 销售件数,
           COUNT(DISTINCT StockCode)                          AS 商品种类
    FROM sales
    WHERE {WHERE}
    """,
    P,
).iloc[0]

c1, c2, c3, c4 = st.columns(4)
c1.metric("💰 销售额", f"£{kpi['销售额']:,.0f}")
c2.metric("📦 订单数", f"{kpi['订单数']:,.0f}")
c3.metric("👥 客户数", f"{kpi['客户数']:,.0f}")
c4.metric("🧾 客单价", f"£{kpi['客单价']:,.2f}")

st.divider()


# ---------------------------------------------------------------
# 趋势图
# ---------------------------------------------------------------
st.subheader("📈 销售额月度趋势")

trend = run_query(
    f"""
    SELECT substr(InvoiceDate, 1, 7) AS 月份,
           ROUND(SUM(Amount), 2)     AS 销售额,
           COUNT(DISTINCT Invoice)   AS 订单数
    FROM sales
    WHERE {WHERE}
    GROUP BY 月份
    ORDER BY 月份
    """,
    P,
)
if not trend.empty:
    st.line_chart(trend.set_index("月份")[["销售额"]], height=320)
    st.caption(
        "⚠️ 首尾月份不完整（2009-12 只有一个月、2011-12 只有 9 天），"
        "做同比时不能直接比较。"
    )
else:
    st.info("当前筛选条件下没有数据。")


# ---------------------------------------------------------------
# 国家 / 商品排行
# ---------------------------------------------------------------
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("🌍 销售额 Top 10 国家")
    top_country = run_query(
        f"""
        SELECT Country AS 国家, ROUND(SUM(Amount), 2) AS 销售额
        FROM sales WHERE {WHERE}
        GROUP BY Country ORDER BY 销售额 DESC LIMIT 10
        """,
        P,
    )
    st.bar_chart(top_country.set_index("国家"), height=340)

with col_right:
    st.subheader("🏆 销售额 Top 10 商品")
    top_product = run_query(
        f"""
        SELECT StockCode AS 商品编码,
               MAX(Description) AS 商品名,
               ROUND(SUM(Amount), 2) AS 销售额
        FROM sales WHERE {WHERE}
        GROUP BY StockCode ORDER BY 销售额 DESC LIMIT 10
        """,
        P,
    )
    top_product["标签"] = top_product["商品名"].str.slice(0, 22)
    st.bar_chart(top_product.set_index("标签")[["销售额"]], height=340)
    st.caption("⚠️ 榜单中 'Manual' / 'POSTAGE' / 'DOTCOM POSTAGE' 是费用项不是商品，真实分析应剔除。")


# ---------------------------------------------------------------
# RFM 分层
# ---------------------------------------------------------------
st.divider()
st.subheader("👥 RFM 客户分层")

RFM_SQL = f"""
WITH 基表 AS (
    SELECT Customer_ID AS 客户ID,
           MAX(InvoiceDate) AS 最近购买,
           COUNT(DISTINCT Invoice) AS F次数,
           SUM(Amount) AS M金额
    FROM sales_known WHERE {WHERE}
    GROUP BY Customer_ID
),
打分 AS (
    SELECT 客户ID, F次数, M金额,
           6 - NTILE(5) OVER (ORDER BY julianday(最近购买) DESC) AS R分,
           NTILE(5) OVER (ORDER BY F次数) AS F分,
           NTILE(5) OVER (ORDER BY M金额) AS M分
    FROM 基表
),
分层 AS (
    SELECT *, CASE
        WHEN R分>=4 AND F分>=4 AND M分>=4 THEN '重要价值客户'
        WHEN R分>=4 AND F分< 4 AND M分>=4 THEN '重要发展客户'
        WHEN R分< 4 AND F分>=4 AND M分>=4 THEN '重要保持客户'
        WHEN R分< 4 AND F分< 4 AND M分>=4 THEN '重要挽留客户'
        WHEN R分>=4 AND F分>=4 AND M分< 4 THEN '一般价值客户'
        WHEN R分>=4 AND F分< 4 AND M分< 4 THEN '一般发展客户'
        WHEN R分< 4 AND F分>=4 AND M分< 4 THEN '一般保持客户'
        ELSE '一般挽留客户' END AS 客户分层
    FROM 打分
)
SELECT 客户分层,
       COUNT(*) AS 客户数,
       ROUND(SUM(M金额), 2) AS 消费总额,
       ROUND(SUM(M金额) * 100.0 / (SELECT SUM(M金额) FROM 分层), 1) AS 消费占比
FROM 分层
GROUP BY 客户分层
ORDER BY 消费总额 DESC
"""

with st.spinner("正在计算 RFM 分层……"):
    rfm = run_query(RFM_SQL, P)

if not rfm.empty:
    r1, r2 = st.columns([3, 2])
    with r1:
        st.bar_chart(rfm.set_index("客户分层")[["消费总额"]], height=340)
    with r2:
        st.dataframe(rfm, use_container_width=True, hide_index=True)
    st.caption(
        "💡 看「客户占比」和「消费占比」的差距 —— 少数核心客户贡献大部分营收，"
        "这就是分层运营的依据。"
    )
else:
    st.info("当前筛选条件下没有可进行 RFM 分析的客户数据。")


# ---------------------------------------------------------------
# 明细数据
# ---------------------------------------------------------------
with st.expander("📋 查看明细数据（前 500 行）"):
    detail = run_query(
        f"""
        SELECT Invoice AS 发票号, StockCode AS 商品编码, Description AS 商品名,
               Quantity AS 数量, InvoiceDate AS 时间, Price AS 单价,
               Amount AS 金额, Country AS 国家
        FROM sales WHERE {WHERE}
        ORDER BY InvoiceDate DESC
        LIMIT 500
        """,
        P,
    )
    st.dataframe(detail, use_container_width=True, hide_index=True)
    st.caption(f"当前筛选条件下的明细共 {kpi['订单数']:,.0f} 笔订单，此处仅展示最近 500 行。")

st.divider()
st.caption(
    "项目仓库：github.com/zi-cmtry/dm2026 ｜ "
    "技术栈：Python · pandas · SQLite · scikit-learn · Streamlit"
)
