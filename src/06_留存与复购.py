# -*- coding: utf-8 -*-
"""
第 6 课：留存率与复购分析

━━━ 为什么这一课对找工作最重要？━━━
    上一课的 RFM 描述的是「客户现在值多少钱」。
    这一课回答的是「客户会留下来吗」—— 这是互联网公司最关心的问题。

    面试数据分析岗，几乎必问：
        「留存率怎么算？」
        「什么是同期群分析（Cohort Analysis）？」
        「复购率低怎么排查？」

━━━ 三个核心概念 ━━━
    复购率   : 买过 2 次及以上的客户占比
    留存率   : 首购之后，第 N 个月还在买的客户占比
    同期群   : 把客户按「首次购买的月份」分组，追踪每组后续表现
              （Cohort Analysis，也叫队列分析）

━━━ SQL 技巧 ━━━
    CTE (WITH ... AS)  把复杂查询拆成几步，像搭积木
    自连接 (SELF JOIN) 同一张表 JOIN 自己 —— 留存分析的基础
    条件聚合           SUM(CASE WHEN ... THEN 1 ELSE 0 END) 做漏斗

运行方式（仓库根目录下）：
    python src/06_留存与复购.py
"""

import sqlite3
import textwrap
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "processed" / "retail.db"


def ask(con, question: str, sql: str, note: str = "") -> pd.DataFrame:
    print("\n" + "=" * 90)
    print(f"❓ {question}")
    print("=" * 90)
    print("SQL:")
    print(textwrap.indent(sql.strip(), "    "))
    df = pd.read_sql(sql, con)
    print("\n结果:")
    print(textwrap.indent(df.to_string(index=False), "    "))
    if note:
        print(textwrap.indent(note.strip(), "    "))
    return df


con = sqlite3.connect(DB)

print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║  第 6 课：留存率与复购分析                                                    ║
║                                                                              ║
║  两个最容易被混为一谈的指标：                                                  ║
║                                                                              ║
║    复购率 = 有多少比例的人买了第二次   → 一个「静态」快照                       ║
║    留存率 = 首购后第 N 个月还有多少人活着 → 一条「动态」曲线                    ║
║                                                                              ║
║  区别在哪？复购率告诉你「结果」，留存率告诉你「什么时候掉的人」。                  ║
║  运营需要的恰恰是后者 —— 知道第 1 个月就掉了 80%，才能针对性动作。               ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")


# ---------------------------------------------------------------
# Q1：复购率
# ---------------------------------------------------------------
ask(
    con,
    "整体复购率是多少？",
    """
    WITH 客户订单数 AS (
        SELECT Customer_ID              AS 客户ID,
               COUNT(DISTINCT Invoice)  AS 订单数
        FROM sales_known
        GROUP BY Customer_ID
    )
    SELECT COUNT(*)                                                   AS 客户总数,
           SUM(CASE WHEN 订单数 >= 2 THEN 1 ELSE 0 END)               AS 复购客户数,
           ROUND(SUM(CASE WHEN 订单数 >= 2 THEN 1 ELSE 0 END) * 100.0
                 / COUNT(*), 2)                                       AS 复购率,
           ROUND(AVG(订单数), 2)                                      AS 人均订单数
    FROM 客户订单数
    """,
    """
    💡 技术点：
       · WITH ... AS (...) 叫 CTE（公用表表达式），把查询拆成"先算这个、再算那个"。
         复杂 SQL 写成一坨嵌套子查询没人看得懂，CTE 是专业写法的标志。
       · SUM(CASE WHEN 条件 THEN 1 ELSE 0 END) 是「条件计数」的标准写法，
         等价于 COUNT(*) FILTER (WHERE ...) 但兼容性更好 —— 面试常考。
    """,
)


# ---------------------------------------------------------------
# Q2：购买次数分布
# ---------------------------------------------------------------
ask(
    con,
    "客户买过几次？分布是长尾还是两极？",
    """
    WITH 客户订单数 AS (
        SELECT Customer_ID AS 客户ID, COUNT(DISTINCT Invoice) AS 订单数
        FROM sales_known GROUP BY Customer_ID
    )
    SELECT CASE
             WHEN 订单数 = 1            THEN '1.只买过1次'
             WHEN 订单数 BETWEEN 2 AND 4 THEN '2.买过2-4次'
             WHEN 订单数 BETWEEN 5 AND 9 THEN '3.买过5-9次'
             WHEN 订单数 BETWEEN 10 AND 29 THEN '4.买过10-29次'
             ELSE                           '5.买过30次以上'
           END                              AS 购买次数区间,
           COUNT(*)                         AS 客户数,
           ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM 客户订单数), 2) AS 占比
    FROM 客户订单数
    GROUP BY 购买次数区间
    ORDER BY 购买次数区间
    """,
    """
    💡 解读要点（跑完数据后修正 —— 这个文件里我又猜错了一次）：
       · 我原稿写的是"只买过 1 次的人占比最大，是典型长尾结构"。
         实际最大的是 2-4 次（35.62%），只买过 1 次的是 27.61%。
       · 为什么不是长尾？因为这是一家【B 端批发商】，
         客户本来就是反复进货的零售商家。互联网消费品才是
         "买一次就走"的长尾 —— B 端和 C 端的客户结构完全不同。
       · ⚠️ 教训：不要拿"行业常识"直接套在具体数据上。
         先看数据，再谈常识。这是本项目里第四次预写解读被推翻。
       · 真正值得关注的是那 27.61% 只买过一次的客户 ——
         他们是"首购未转化"人群，是复购运营的目标。
    """,
)


# ---------------------------------------------------------------
# Q3：同期群留存矩阵（本课核心）
# ---------------------------------------------------------------
ask(
    con,
    "核心：按首次购买月份分组，看每批客户的留存曲线（同期群分析）",
    """
    WITH 首购月 AS (
        -- ① 每个客户第一次购买是哪个月 —— 这决定了它属于哪个"队列"
        SELECT Customer_ID                    AS 客户ID,
               MIN(substr(InvoiceDate, 1, 7)) AS 首购月
        FROM sales_known
        GROUP BY Customer_ID
    ),
    活跃记录 AS (
        -- ② 自连接：把每个客户的每一次消费，都贴上"他属于哪个队列"的标签
        --    这是留存分析的核心步骤：明细 × 归属
        SELECT DISTINCT
               f.首购月,
               s.Customer_ID                AS 客户ID,
               substr(s.InvoiceDate, 1, 7)  AS 活跃月
        FROM sales_known s
        JOIN 首购月 f ON s.Customer_ID = f.客户ID
    ),
    月序聚合 AS (
        -- ③ 算出每个客户每次消费距首购过了几个月
        SELECT 首购月,
               活跃月,
               (CAST(substr(活跃月, 1, 4) AS INTEGER)
                - CAST(substr(首购月, 1, 4) AS INTEGER)) * 12
               + (CAST(substr(活跃月, 6, 2) AS INTEGER)
                  - CAST(substr(首购月, 6, 2) AS INTEGER))       AS 月序,
               COUNT(DISTINCT 客户ID)                            AS 活跃人数
        FROM 活跃记录
        GROUP BY 首购月, 活跃月
    ),
    队列规模 AS (
        -- ④ 每个队列一开始有多少人（分母）
        SELECT 首购月, COUNT(*) AS 队列人数 FROM 首购月 GROUP BY 首购月
    )
    -- ⑤ 行转列：把"月序"从行变成列，做出经典的留存矩阵
    SELECT a.首购月                                                     AS 首购月,
           z.队列人数                                                   AS 队列人数,
           ROUND(MAX(CASE WHEN a.月序 = 0 THEN a.活跃人数 END) * 100.0 / z.队列人数, 1) AS M0,
           ROUND(MAX(CASE WHEN a.月序 = 1 THEN a.活跃人数 END) * 100.0 / z.队列人数, 1) AS M1,
           ROUND(MAX(CASE WHEN a.月序 = 2 THEN a.活跃人数 END) * 100.0 / z.队列人数, 1) AS M2,
           ROUND(MAX(CASE WHEN a.月序 = 3 THEN a.活跃人数 END) * 100.0 / z.队列人数, 1) AS M3,
           ROUND(MAX(CASE WHEN a.月序 = 4 THEN a.活跃人数 END) * 100.0 / z.队列人数, 1) AS M4,
           ROUND(MAX(CASE WHEN a.月序 = 5 THEN a.活跃人数 END) * 100.0 / z.队列人数, 1) AS M5,
           ROUND(MAX(CASE WHEN a.月序 = 6 THEN a.活跃人数 END) * 100.0 / z.队列人数, 1) AS M6
    FROM 月序聚合 a
    JOIN 队列规模 z ON a.首购月 = z.首购月
    GROUP BY a.首购月, z.队列人数
    ORDER BY a.首购月
    LIMIT 15
    """,
    """
    💡 怎么读这张表？（这是面试能加分的地方）

       · 每一行 = 一批"同期入伍"的客户（首购月相同）
       · M0 是首购当月，永远是 100%（分母就是他自己）
       · M1 是首购后第 1 个月还在买的比例 —— 【这是最关键的一个数字】
       · M2~M6 是后续月份

       · 横着看：一条队列的生命周期衰减曲线
       · 竖着看：不同月份进来的客户，质量有没有变化

       💡 技术点拆解：
          ① 首购月：MIN() 分组，给每个客户打上队列标签
          ② 自连接：让每一笔交易都知道自己属于哪个队列 ← 留存分析的灵魂
          ③ 月序：用整数年月做差算月份间隔（SQLite 没有 datediff）
          ④ 分母：队列规模必须单独算，否则比例会错
          ⑤ 行转列：CASE WHEN + MAX 是 SQL 里的经典透视表写法
    """,
)


# ---------------------------------------------------------------
# Q4：留存曲线的整体形态
# ---------------------------------------------------------------
ask(
    con,
    "把所有队列平均起来，这家店的留存曲线长什么样？",
    """
    WITH 首购月 AS (
        SELECT Customer_ID AS 客户ID, MIN(substr(InvoiceDate, 1, 7)) AS 首购月
        FROM sales_known GROUP BY Customer_ID
    ),
    活跃记录 AS (
        SELECT DISTINCT f.首购月, s.Customer_ID AS 客户ID,
               substr(s.InvoiceDate, 1, 7) AS 活跃月
        FROM sales_known s JOIN 首购月 f ON s.Customer_ID = f.客户ID
    ),
    月序聚合 AS (
        SELECT 首购月, 客户ID,
               (CAST(substr(活跃月,1,4) AS INTEGER) - CAST(substr(首购月,1,4) AS INTEGER)) * 12
               + (CAST(substr(活跃月,6,2) AS INTEGER) - CAST(substr(首购月,6,2) AS INTEGER)) AS 月序
        FROM 活跃记录
    ),
    队列规模 AS (SELECT 首购月, COUNT(*) AS 队列人数 FROM 首购月 GROUP BY 首购月),
    留存 AS (
        SELECT a.月序,
               a.首购月,
               COUNT(DISTINCT a.客户ID) * 100.0 / z.队列人数 AS 留存率
        FROM 月序聚合 a JOIN 队列规模 z ON a.首购月 = z.首购月
        WHERE a.月序 BETWEEN 0 AND 6
        GROUP BY a.月序, a.首购月
    )
    SELECT 月序                                     AS 首购后第N月,
           COUNT(*)                                 AS 参与统计的队列数,
           ROUND(AVG(留存率), 1)                     AS 平均留存率,
           ROUND(MIN(留存率), 1)                     AS 最低,
           ROUND(MAX(留存率), 1)                     AS 最高
    FROM 留存
    GROUP BY 月序
    ORDER BY 月序
    """,
    """
    💡 解读要点：
       · 看 M0 → M1 的断崖。如果从 100% 掉到 20% 左右，
         说明【大部分客户买完就走】，这在一锤子买卖的批发/礼品行业很常见。
       · 再看 M1 之后：如果曲线开始走平（比如稳定在 20% 上下），
         说明留下来的是"真客户"，他们形成了稳定复购。
         这条走平的线叫「留存平台期」，是健康业务的重要标志。
       · 如果 M1 之后继续往 0 掉 → 说明没有真正的忠诚客户，业务模式有问题。
       · ⚠️ 两个必须写进报告的统计陷阱（不写清楚，报告就是错的）：

         陷阱一【右删失】：越靠后的月份，能观察到它的队列越少
         （数据只到 2011-12）。所以 M5、M6 参与统计的队列更少，
         样本更小，可信度下降。

         陷阱二【左截断】—— 这个更隐蔽，也更致命：
         2009-12 那一批（955 人）的 M1 留存高达 35.3%，是全场最高。
         但【这一行不可信】：因为数据从 2009-12-01 才开始，
         这批人的"首次购买"很可能不是真的首次 ——
         他们可能已经是买了好几年的老客户，只是数据从这时才有记录。
         这个现象叫「不朽时间偏倚 / 左截断」。

         → 结论：看队列留存趋势时，必须从 2010-01 开始看，
           把 2009-12 这一行剔除。任何"数据窗口起点"都会制造假的优质队列。
         → 这也解释了为什么 2010-01 的 20.6% 比 2009-12 的 35.3% 低这么多：
           不是客户质量变差了，是统计口径变诚实了。
    """,
)


# ---------------------------------------------------------------
# Q5：客户生命周期漏斗
# ---------------------------------------------------------------
ask(
    con,
    "客户从「首次购买」到「核心客户」的漏斗，转化率是多少？",
    """
    WITH 客户订单数 AS (
        SELECT Customer_ID AS 客户ID, COUNT(DISTINCT Invoice) AS 订单数
        FROM sales_known GROUP BY Customer_ID
    ),
    总数 AS (SELECT COUNT(*) AS n FROM 客户订单数)
    SELECT '① 全部成交客户'      AS 漏斗阶段, COUNT(*) AS 人数,
           '100%'                AS 累计转化率
    FROM 客户订单数
    UNION ALL
    SELECT '② 复购（≥2单）',
           SUM(CASE WHEN 订单数 >= 2 THEN 1 ELSE 0 END),
           ROUND(SUM(CASE WHEN 订单数 >= 2 THEN 1 ELSE 0 END) * 100.0 / (SELECT n FROM 总数), 1) || '%'
    FROM 客户订单数
    UNION ALL
    SELECT '③ 高频（≥5单）',
           SUM(CASE WHEN 订单数 >= 5 THEN 1 ELSE 0 END),
           ROUND(SUM(CASE WHEN 订单数 >= 5 THEN 1 ELSE 0 END) * 100.0 / (SELECT n FROM 总数), 1) || '%'
    FROM 客户订单数
    UNION ALL
    SELECT '④ 忠诚（≥10单）',
           SUM(CASE WHEN 订单数 >= 10 THEN 1 ELSE 0 END),
           ROUND(SUM(CASE WHEN 订单数 >= 10 THEN 1 ELSE 0 END) * 100.0 / (SELECT n FROM 总数), 1) || '%'
    FROM 客户订单数
    UNION ALL
    SELECT '⑤ 核心（≥50单）',
           SUM(CASE WHEN 订单数 >= 50 THEN 1 ELSE 0 END),
           ROUND(SUM(CASE WHEN 订单数 >= 50 THEN 1 ELSE 0 END) * 100.0 / (SELECT n FROM 总数), 1) || '%'
    FROM 客户订单数
    """,
    """
    💡 关于「漏斗」的一个重要认知：

       真正的转化漏斗需要【每一步的用户明细】（比如：进店1000人 → 加购200人
       → 下单50人）。我们这份数据只有成交记录，没有浏览/加购行为，
       所以做不出电商那种"浏览→加购→支付"的漏斗。

       但我们可以做「客户生命周期漏斗」—— 用购买次数分层，
       看客户从新客到核心客户的逐级留存。这是在没有埋点数据时
       最接近漏斗的分析方法。

       ⚠️ 面试时要诚实说明这个区别。被问到"你做过漏斗分析吗"，
          如果硬说自己做过"浏览-加购-下单"漏斗，追问细节必然露馅。
          正确的答法是：说明你的数据有什么、你能做什么、以及为什么。
    """)

con.close()

print("\n" + "=" * 94)
print("第 6 课结束。你现在掌握了留存率、复购率、同期群分析 —— 互联网数据分析的三大基础。")
print("下一课：客户流失预测（用上你的机器学习课）")
print("=" * 94)

print("""
━━━ 面试会怎么问？━━━
    Q: 留存率怎么算？
    A: 先按 MIN(购买时间) 给每个客户打上"首购月"标签（这就是同期群），
       再统计每个客户在各个月份的活跃情况，用当月活跃人数除以队列总人数。

    Q: 为什么要做同期群，而不是只看整体留存？
    A: 整体留存会把不同时期进来的客户混在一起。比如你 3 月做了大促，
       拉来一批只看不买的客户，这批人会拉低整体留存，
       让你误以为"产品变差了"。同期群能隔离出「每批客户的真实表现」。

    Q: 复购率低怎么排查？
    A: 先看购买次数分布确认是不是长尾；再看留存曲线的断点在哪 —
       如果 M0→M1 就掉了 80%，问题是首次体验/商品力；
       如果 M3 之后才掉，问题是复购触达/会员运营。

━━━ 给你自己的练习 ━━━
    1. 把 Q3 的 LIMIT 15 去掉，看看后面那些队列（2011年下半年进来的）
       留存率是变好还是变差
    2. 改 Q1，按「国家」分别算复购率，看看哪个国家的客户最忠诚
    3. 挑战题：算「客户平均购买间隔天数」
       （提示：先算出每个客户每笔订单的日期，再用 LAG 窗口函数取上一单日期）
""")
