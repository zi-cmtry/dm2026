# -*- coding: utf-8 -*-
"""
第 5 课：窗口函数 + RFM 用户分层

━━━ 为什么这一课最重要？━━━
    去面试数据分析岗，SQL 环节被问得最多的就是：
        「用窗口函数把用户按价值分层」
        「算一下每个用户的累计消费 / 排名 / 环比」
    因为窗口函数是区分「会写 SQL」和「只会 SELECT」的分水岭。

━━━ 窗口函数 vs 聚合函数 ━━━
    聚合函数 (GROUP BY)：
        把多行「压成」一行 —— 你看不到原始明细了
        SELECT Country, SUM(Amount) FROM sales GROUP BY Country;
        → 43 行（每个国家一行）

    窗口函数 (OVER)：
        「保留」每一行，同时在旁边附上一个计算值
        SELECT Invoice, Amount, SUM(Amount) OVER (PARTITION BY Invoice) FROM sales;
        → 104 万行（一行都没少，但每行多了一列"本单总额"）

    一句话记住：GROUP BY 是压缩，窗口函数是加列。

━━━ 这一课会用到的窗口函数 ━━━
    NTILE(n)    把数据均分成 n 档（RFM 打分就用它）
    ROW_NUMBER() 连续排名，不并列
    RANK()       并列排名，会跳号
    LAG()/LEAD() 取上一行 / 下一行（算环比、留存）

运行方式（仓库根目录下）：
    python src/05_rfm_analysis.py
"""

import sqlite3
import textwrap
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "processed" / "retail.db"


def ask(con, question: str, sql: str, note: str = "") -> pd.DataFrame:
    print("\n" + "=" * 78)
    print(f"❓ {question}")
    print("=" * 78)
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
╔══════════════════════════════════════════════════════════════════════════╗
║  第 5 课：RFM 用户分层                                                    ║
║                                                                          ║
║  RFM 是零售业最经典的用户价值模型，三个字母分别代表：                        ║
║                                                                          ║
║    R = Recency   最近一次消费距今多久   → 越近越好（客户还活着）             ║
║    F = Frequency 消费频次               → 越多越好（客户有粘性）             ║
║    M = Monetary  累计消费金额           → 越多越好（客户有价值）             ║
║                                                                          ║
║  它的价值在于：把 5878 个客户从「一堆数字」变成「8 类可以分别对待的人」。      ║
║  运营拿到这份名单，才知道预算该花在谁身上。                                  ║
╚══════════════════════════════════════════════════════════════════════════╝
""")


# ---------------------------------------------------------------
# 第 1 步：算每个客户的 R / F / M 原始值
# ---------------------------------------------------------------
ask(
    con,
    "第 1 步：把每个客户压缩成一行（R、F、M 三个原始值）",
    """
    SELECT Customer_ID                AS 客户ID,
           MAX(InvoiceDate)           AS 最近购买时间,
           COUNT(DISTINCT Invoice)    AS 购买次数,
           ROUND(SUM(Amount), 2)      AS 总消费
    FROM sales_known
    GROUP BY Customer_ID
    ORDER BY 总消费 DESC
    LIMIT 5
    """,
    """
    💡 注意这一步用的是【聚合函数】GROUP BY —— 因为它要把
       一个客户的多条交易记录压成一行。窗口函数做不了这件事。
       两个工具解决不同问题，不是替代关系。
    """,
)


# ---------------------------------------------------------------
# 第 2 步：打分
# ---------------------------------------------------------------
ask(
    con,
    "第 2 步：用 NTILE(5) 把每个指标均分成 5 档，得到 R/F/M 三个分数",
    """
    WITH snapshot AS (
        -- 因为数据是 2011 年的历史数据，不能用"今天"当基准，
        -- 要用数据集里最后一个交易日的次日作为"观察截止日"
        SELECT date(MAX(InvoiceDate), '+1 day') AS 截止日
        FROM sales_known
    ),
    base AS (
        SELECT Customer_ID              AS 客户ID,
               MAX(InvoiceDate)         AS 最近购买,
               COUNT(DISTINCT Invoice)  AS F_购买次数,
               SUM(Amount)              AS M_总消费
        FROM sales_known
        GROUP BY Customer_ID
    ),
    scored AS (
        SELECT b.*,
               CAST(julianday((SELECT 截止日 FROM snapshot)) - julianday(b.最近购买) AS INTEGER) AS R_天数,

               -- R：最近购买时间【越晚】越好，所以要 DESC
               NTILE(5) OVER (ORDER BY julianday(b.最近购买) DESC) AS R分,
               -- F、M：数值【越大】越好，用默认 ASC
               NTILE(5) OVER (ORDER BY b.F_购买次数)               AS F分,
               NTILE(5) OVER (ORDER BY b.M_总消费)                 AS M分
        FROM base b
    )
    SELECT 客户ID,
           R_天数,
           ROUND(F_购买次数, 0)   AS F_购买次数,
           ROUND(M_总消费, 2)     AS M_总消费,
           R分, F分, M分
    FROM scored
    ORDER BY M_总消费 DESC
    LIMIT 8
    """,
    """
    💡 三个关键点：

       1) 【快照日】非常重要。RFM 里的"最近"必须以数据集的最后一天为基准，
          不能用系统当前日期 —— 否则 2011 年的数据算出来 R 全是 5000 多天，
          所有客户都被判成"流失"，分层完全失效。

       2) NTILE(5) 的意思是"均分成 5 档，各占 20%"。
          注意 R 用的是 ORDER BY 最近购买 DESC —— 最近的排第 1 组，
          但 NTILE 从 1 开始编号，所以最近的拿到 1 分而不是 5 分，
          和 F、M 的方向相反！

       3) 上面的写法【有 bug】，先别急着抄。看下一条。
    """,
)


# ---------------------------------------------------------------
# 第 3 步：修正 R 的方向（自己发现 bug 的过程）
# ---------------------------------------------------------------
ask(
    con,
    "第 3 步：验证 —— R 分到底谁高谁低？（这一步暴露了上一步的 bug）",
    """
    WITH snapshot AS (
        SELECT date(MAX(InvoiceDate), '+1 day') AS 截止日 FROM sales_known
    ),
    base AS (
        SELECT Customer_ID AS 客户ID,
               MAX(InvoiceDate) AS 最近购买,
               COUNT(DISTINCT Invoice) AS F_购买次数,
               SUM(Amount) AS M_总消费
        FROM sales_known GROUP BY Customer_ID
    )
    SELECT CASE WHEN NTILE(5) OVER (ORDER BY julianday(最近购买) DESC) = 1
                THEN 'NTILE 第1组（最近购买的那批人）'
                ELSE NULL END AS 分组,
           MIN(最近购买) AS 组内最早购买,
           MAX(最近购买) AS 组内最晚购买
    FROM base
    """,
    """
    💡 上面这段会返回两行：第 1 组和第 NULL 组。
       重点看第 1 组的"组内最晚购买"—— 它应该是全表最晚的日期，
       也就是【最近还在消费的客户】。

       而 NTILE 给这组编号 1，不是 5。
       所以直接用 NTILE 的返回值当 R 分，会把"最活跃的客户"打成 1 分，
       分层结果【完全反过来】。

       修正方法：用 6 - NTILE(...) 把方向翻过来。
    """,
)


# ---------------------------------------------------------------
# 第 4 步：正确的 RFM 分层
# ---------------------------------------------------------------
rfm_sql = """
WITH snapshot AS (
    SELECT date(MAX(InvoiceDate), '+1 day') AS 截止日 FROM sales_known
),
base AS (
    SELECT Customer_ID              AS 客户ID,
           MAX(InvoiceDate)         AS 最近购买,
           COUNT(DISTINCT Invoice)  AS F次数,
           SUM(Amount)              AS M金额
    FROM sales_known
    GROUP BY Customer_ID
),
scored AS (
    SELECT 客户ID,
           CAST(julianday((SELECT 截止日 FROM snapshot)) - julianday(最近购买) AS INTEGER) AS R天数,
           F次数,
           M金额,
           -- ⚠️ R 要用 6 减去 NTILE：最近的客户要得高分（5 分）
           6 - NTILE(5) OVER (ORDER BY julianday(最近购买) DESC) AS R分,
           NTILE(5) OVER (ORDER BY F次数)                        AS F分,
           NTILE(5) OVER (ORDER BY M金额)                        AS M分
    FROM base
),
segmented AS (
    SELECT *,
           CASE
             WHEN R分 >= 4 AND F分 >= 4 AND M分 >= 4 THEN '1.重要价值客户'
             WHEN R分 >= 4 AND F分 <  4 AND M分 >= 4 THEN '2.重要发展客户'
             WHEN R分 <  4 AND F分 >= 4 AND M分 >= 4 THEN '3.重要保持客户'
             WHEN R分 <  4 AND F分 <  4 AND M分 >= 4 THEN '4.重要挽留客户'
             WHEN R分 >= 4 AND F分 >= 4 AND M分 <  4 THEN '5.一般价值客户'
             WHEN R分 >= 4 AND F分 <  4 AND M分 <  4 THEN '6.一般发展客户'
             WHEN R分 <  4 AND F分 >= 4 AND M分 <  4 THEN '7.一般保持客户'
             ELSE                                        '8.一般挽留客户'
           END AS 客户分层
    FROM scored
)
SELECT 客户分层                       AS 客户分层,
       COUNT(*)                       AS 客户数,
       ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM scored), 2) AS 客户占比,
       ROUND(SUM(M金额), 2)           AS 消费总额,
       ROUND(SUM(M金额) * 100.0 / (SELECT SUM(M金额) FROM scored), 2) AS 消费占比,
       ROUND(AVG(R天数), 0)           AS 平均R天数,
       ROUND(AVG(F次数), 1)           AS 平均购买次数,
       ROUND(AVG(M金额), 2)           AS 平均消费
FROM segmented
GROUP BY 客户分层
ORDER BY 消费总额 DESC
"""

ask(con, "第 4 步：正确的 RFM 八分层（这是最终交付物）", rfm_sql)

print("""
    💡 现在读这张表 —— 这才是 RFM 的真正价值所在：

       · 看「客户占比」和「消费占比」的对比。
         如果头部 1~2 类客户只占 20~30% 的人数，却贡献了 60%+ 的消费，
         那就验证了零售业经典的「二八法则」。

       · 看「平均R天数」。
         "重要挽留客户"这一类的 R 天数会明显偏大 ——
         这些人曾经很有价值，但已经很久没来了。
         他们是最值得投入营销预算的一群人：
         已经证明过消费能力，只是快流失了。

       · 这就是「分层」的意义：把 5878 个客户从一堆数字
         变成 8 类可以【分别制定策略】的人。
""")

# ---------------------------------------------------------------
# 第 5 步：运营建议
# ---------------------------------------------------------------
ask(
    con,
    "第 5 步：每类客户该做什么？（把数据翻译成动作）",
    """
    WITH snapshot AS (SELECT date(MAX(InvoiceDate),'+1 day') AS 截止日 FROM sales_known),
    base AS (
        SELECT Customer_ID AS 客户ID, MAX(InvoiceDate) AS 最近购买,
               COUNT(DISTINCT Invoice) AS F次数, SUM(Amount) AS M金额
        FROM sales_known GROUP BY Customer_ID
    ),
    scored AS (
        SELECT 客户ID, F次数, M金额,
               6 - NTILE(5) OVER (ORDER BY julianday(最近购买) DESC) AS R分,
               NTILE(5) OVER (ORDER BY F次数) AS F分,
               NTILE(5) OVER (ORDER BY M金额) AS M分
        FROM base
    ),
    seg AS (
        SELECT *, CASE
             WHEN R分>=4 AND F分>=4 AND M分>=4 THEN '重要价值客户'
             WHEN R分>=4 AND F分< 4 AND M分>=4 THEN '重要发展客户'
             WHEN R分< 4 AND F分>=4 AND M分>=4 THEN '重要保持客户'
             WHEN R分< 4 AND F分< 4 AND M分>=4 THEN '重要挽留客户'
             WHEN R分>=4 AND F分>=4 AND M分< 4 THEN '一般价值客户'
             WHEN R分>=4 AND F分< 4 AND M分< 4 THEN '一般发展客户'
             WHEN R分< 4 AND F分>=4 AND M分< 4 THEN '一般保持客户'
             ELSE '一般挽留客户' END AS 客户分层
        FROM scored
    )
    SELECT 客户分层, COUNT(*) AS 客户数,
           CASE 客户分层
             WHEN '重要价值客户' THEN 'VIP 待遇：专属客服、优先发货、新品试用'
             WHEN '重要发展客户' THEN '提频次：满减券、组合套餐、会员积分'
             WHEN '重要保持客户' THEN '防流失：一对一回访、大额专属折扣'
             WHEN '重要挽留客户' THEN '重激活：强力召回券 + 电话触达（最紧急）'
             WHEN '一般价值客户' THEN '维持：常规营销活动覆盖即可'
             WHEN '一般发展客户' THEN '培养：低门槛首单券，先建立习惯'
             WHEN '一般保持客户' THEN '低成本维护：邮件/短信月报'
             ELSE                '顺其自然：不投预算，避免浪费'
           END AS 运营策略
    FROM seg
    GROUP BY 客户分层
    ORDER BY 客户数 DESC
    """)

con.close()

print("\n" + "=" * 78)
print("第 5 课结束。你已经掌握了面试最高频的 SQL 技能：窗口函数 + RFM。")
print("下一课：留存率与复购分析（自连接 / CTE）")
print("=" * 78)

print("""
━━━ 面试会怎么问？（提前准备）━━━
    Q: 你这个 RFM 的分档阈值是怎么定的？
    A: 用 NTILE(5) 均分，保证每档人数相同。
       业务上也可以按经验阈值（比如 R < 30 天算高），
       但均分的好处是不依赖主观判断，且对数据分布不敏感。

    Q: 为什么 R 要写 6 - NTILE(...)？
    A: 因为 NTILE 按最近购买时间倒序编号，最近的人拿到 1。
       而 R 的定义是「越近越好」，所以要用 6 减去它翻转为 5 分。
       ← 这个问题答出来，面试官会认为你真的动手做过

    Q: 8 个分层为什么用 4 分做分界？
    A: 5 档取 4 分以上算"高"，是 RFM 的常见做法。
       你也可以用 3 分做分界得到更均衡的分布。
       关键是【在报告里说明你的选择】，而不是随便定。
""")
