# -*- coding: utf-8 -*-
"""
第 4 课：用 SQL 做真正的业务分析（基础聚合篇）

━━━ 这一课的目标 ━━━
    不是"学会 SQL 语法"，而是「用 SQL 回答业务问题」。

━━━ ⚠️ 关于本文件里的「解读要点」━━━
    第一版我把解读【提前写好】了，然后才跑数据 —— 结果三处都写错了。
    现在文件里的解读都是【跑完之后】修正过的。

    这是本课最重要的一课：
        不要先写结论再看数据。
        所有"我觉得应该是……"都必须跑一条 SQL 验证。

运行方式（仓库根目录下）：
    python src/04_business_analysis.py
"""

import sqlite3
import textwrap
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "processed" / "retail.db"


def ask(con, question: str, sql: str) -> pd.DataFrame:
    """执行一条 SQL，并把「业务问题 → SQL → 结果」完整打印出来。"""
    print("\n" + "=" * 78)
    print(f"❓ 业务问题：{question}")
    print("=" * 78)
    print("SQL:")
    print(textwrap.indent(sql.strip(), "    "))
    df = pd.read_sql(sql, con)
    print("\n结果:")
    print(textwrap.indent(df.to_string(index=False), "    "))
    return df


con = sqlite3.connect(DB)

print("""
╔══════════════════════════════════════════════════════════════════════════╗
║  第 4 课：用 SQL 回答业务问题                                              ║
║                                                                          ║
║  记住 SQL 的执行顺序（和书写顺序不一样！）：                                ║
║                                                                          ║
║      FROM → WHERE → GROUP BY → HAVING → SELECT → ORDER BY → LIMIT        ║
║                                                                          ║
║  这个顺序解释了两件新手最常困惑的事：                                       ║
║    1. 为什么 WHERE 里不能用聚合函数（如 SUM()）—— 那时还没分组             ║
║    2. 为什么 HAVING 可以 —— 它在 GROUP BY 之后执行                        ║
╚══════════════════════════════════════════════════════════════════════════╝
""")


# ---------------------------------------------------------------
# Q1
# ---------------------------------------------------------------
ask(
    con,
    "这家店整体经营情况如何？两个口径的客单价差多少？",
    """
    SELECT '全部订单'        AS 口径,
           COUNT(DISTINCT Invoice)                          AS 订单数,
           ROUND(SUM(Amount), 2)                            AS 总销售额,
           ROUND(SUM(Amount) / COUNT(DISTINCT Invoice), 2)  AS 客单价
    FROM sales

    UNION ALL

    SELECT '仅已知客户订单',
           COUNT(DISTINCT Invoice),
           ROUND(SUM(Amount), 2),
           ROUND(SUM(Amount) / COUNT(DISTINCT Invoice), 2)
    FROM sales_known
    """,
)
print("""
    💡 解读要点（跑完数据后修正）：
       · 客单价 = 销售额 ÷ 订单数，是零售业最核心的指标之一
       · 两个口径差 8.29%（523.31 vs 479.95）—— 我原稿凭直觉写了"几乎一样"，
         被数据打脸。8% 在零售业已经是不小的差距。
       · 往下追一步（见 Q7）：匿名订单的客单价其实【更高】，
         这推翻了"匿名客户都是小单"的常见假设。
""")


# ---------------------------------------------------------------
# Q2
# ---------------------------------------------------------------
ask(
    con,
    "销售额的月度趋势如何？有没有明显的季节性？",
    """
    SELECT substr(InvoiceDate, 1, 7)  AS 月份,
           COUNT(DISTINCT Invoice)    AS 订单数,
           ROUND(SUM(Amount), 2)      AS 销售额
    FROM sales
    GROUP BY 月份
    ORDER BY 月份
    """,
)
print("""
    💡 解读要点：
       · substr(InvoiceDate, 1, 7) 从 '2011-03-15 10:20:00' 里截出 '2011-03'
         —— 这是 SQL 里最常用的日期处理技巧，务必记住
       · 明显的季节性：每年 9~11 月销售额爬升，11 月达到峰值。
         这家店卖的是礼品/家居装饰，11 月对应圣诞备货季，完全合理。
       · ⚠️ 首尾两个月不完整：数据从 2009-12-01 开始、到 2011-12-09 结束。
         2009-12 只有一个月、2011-12 只有 9 天。做同比时绝不能直接拿来比。
""")


# ---------------------------------------------------------------
# Q3
# ---------------------------------------------------------------
ask(
    con,
    "哪些国家贡献了主要销售额？（只看销售额超过 10 万的）",
    """
    SELECT Country                    AS 国家,
           COUNT(DISTINCT Invoice)    AS 订单数,
           ROUND(SUM(Amount), 2)      AS 销售额
    FROM sales
    GROUP BY Country
    HAVING SUM(Amount) > 100000
    ORDER BY 销售额 DESC
    """,
)
print("""
    💡 WHERE 和 HAVING 的区别（面试高频）：
       · WHERE  在分组【之前】过滤「行」   →  WHERE Amount > 100
       · HAVING 在分组【之后】过滤「组」   →  HAVING SUM(Amount) > 100000
       下面这个写法是错的，可以自己试着跑一下看看报什么错：
           WHERE SUM(Amount) > 100000     ← 报错！此时还没分组

    💡 业务解读：
       · 英国本土占 85%，这是一家以英国为主的批发商
       · EIRE（爱尔兰）排第二 —— 注意这里是 EIRE 而不是 Ireland，
         同一国家的不同写法是真实数据里极常见的坑
""")


# ---------------------------------------------------------------
# Q4
# ---------------------------------------------------------------
ask(
    con,
    "卖得最好的 10 个商品是什么？",
    """
    SELECT StockCode                AS 商品编码,
           MAX(Description)         AS 商品名,
           SUM(Quantity)            AS 总销量,
           ROUND(SUM(Amount), 2)    AS 销售额
    FROM sales
    GROUP BY StockCode
    ORDER BY 销售额 DESC
    LIMIT 10
    """,
)
print("""
    💡 两个细节：
       · 为什么用 MAX(Description) 而不是 Description？
         因为同一 StockCode 可能对应多个写法略有差异的商品名。
         在 GROUP BY 里，非聚合列必须被"聚合掉"，这是 SQL 的硬规则。
       · ORDER BY 可以用 SELECT 里定义的别名（销售额），
         因为 ORDER BY 在 SELECT 之后执行 —— 正好对应开头的执行顺序

    💡 业务解读（跑完才知道）：
       · 榜单里混进了 'M'（Manual 手工调整）、'DOT'（DOTCOM POSTAGE 邮费）、
         'POST'（POSTAGE 邮费）—— 【这三行不是商品，是费用项！】
       · 真实分析里应该把它们剔除，否则商品排行榜是错的。
         这是数据清洗没做干净留下的尾巴，也是真实工作的常态：
         你永远无法在清洗阶段预见所有问题，分析时才会发现。
       · 剔除费用项后，真正的销冠是 85123A（白色挂心烛台），
         销量 96,147 件、销售额 £263,109.67
""")


# ---------------------------------------------------------------
# Q5
# ---------------------------------------------------------------
ask(
    con,
    "一周里哪几天生意最好？",
    """
    SELECT CASE strftime('%w', InvoiceDate)
             WHEN '0' THEN '周日'  WHEN '1' THEN '周一'
             WHEN '2' THEN '周二'  WHEN '3' THEN '周三'
             WHEN '4' THEN '周四'  WHEN '5' THEN '周五'
             ELSE '周六'
           END                        AS 星期,
           COUNT(DISTINCT Invoice)    AS 订单数,
           ROUND(SUM(Amount), 2)      AS 销售额,
           ROUND(SUM(Amount) / COUNT(DISTINCT Invoice), 2) AS 客单价
    FROM sales
    GROUP BY strftime('%w', InvoiceDate)
    ORDER BY strftime('%w', InvoiceDate)
    """,
)
print("""
    💡 解读要点（跑完数据后修正）：
       · strftime('%w', 日期) 返回 0~6 表示周日~周六
       · CASE WHEN 是 SQL 里的 if-else，把编码翻译成人看得懂的文字
       · 我原稿写的是"周六是 0 订单"，实际是 30 单。
         进一步查证：这 30 单【全部集中在 2009-12-05 这一天】，
         其余所有周六都是 0。所以真相是：
             这家批发商周六不营业，只有开业首月破例过一次。
       · 周五、周四订单量最大，周一客单价最高。
       · ⚠️ 关键教训：一个月里出现 1 天的异常值，就足以让
         "周六销售额 = 9,803" 这种结论产生误导。看数字一定要看分布。
""")


# ---------------------------------------------------------------
# Q6
# ---------------------------------------------------------------
ask(
    con,
    "订单取消率是多少？",
    """
    SELECT (SELECT COUNT(DISTINCT Invoice) FROM sales)         AS 正常订单数,
           (SELECT COUNT(DISTINCT Invoice) FROM cancellations) AS 取消订单数,
           ROUND(
               (SELECT COUNT(DISTINCT Invoice) FROM cancellations) * 100.0
               / ((SELECT COUNT(DISTINCT Invoice) FROM sales)
                  + (SELECT COUNT(DISTINCT Invoice) FROM cancellations))
           , 2)                                                AS 取消率百分比
    """,
)
print("""
    💡 解读要点（这一条我查了三轮才搞清楚）：
       · 取消率 17.14%，这家店的取消率相当高，值得关注
       · 那能不能把取消单 JOIN 回原订单，看"客户取消了什么"？
         【答案是：不能。】我做了三轮验证：
             取消单号去掉 C 之后（如 C489449 → 489449），
             在正常订单里匹配到 0 / 8,292 个。
         去看原始数据才发现：正常单号序列里 489449 是【空缺】的，
         也就是说 —— 被取消订单的原正数行，根本不在这个数据集里。

         所以取消分析只能做到"总量和趋势"层面，
         做不到"这笔取消对应哪笔订单"的明细层面。
         这个限制必须写进报告，否则就是过度解读数据。
""")


# ---------------------------------------------------------------
# Q7
# ---------------------------------------------------------------
ask(
    con,
    "匿名订单（没有 Customer ID）到底是什么客户？",
    """
    SELECT CASE WHEN Customer_ID IS NULL THEN '匿名订单' ELSE '已知客户' END AS 订单类型,
           COUNT(DISTINCT Invoice)                          AS 订单数,
           ROUND(SUM(Amount), 2)                            AS 销售额,
           ROUND(SUM(Amount) / COUNT(DISTINCT Invoice), 2)  AS 客单价
    FROM sales
    GROUP BY 1
    ORDER BY 客单价 DESC
    """,
)
print("""
    💡 这是一个【真正有价值】的发现：
       · 匿名订单只占订单数的 7.8%，却贡献了 15.4% 的销售额
       · 更关键的是客单价：匿名订单约为已知客户的 2 倍以上

       这说明【匿名不代表低价值】。常见解释是：
           → 电话下单 / 传真下单的大宗批发客户，系统里没记客户号
           → 这类订单金额大、频次低

       · 如果没有第 2 课那个"不删数据、先打标"的决定，
         这一整块业务就永远不会被发现 —— 它们会被当成脏数据扔掉。
       · ⚠️ 注意分寸：以上是【假设】，不是结论。要证实它，
         需要拿到订单来源或客户类型字段。报告里要写"推测"而不是"证明"。
""")

con.close()

print("\n" + "=" * 78)
print("第 4 课结束。你现在已经能用 SQL 回答 7 个真实的业务问题了。")
print("下一课：窗口函数 —— RFM 用户分层（面试最高频的 SQL 题）")
print("=" * 78)

print("""
━━━ 给你自己的练习 ━━━
    1. 把 Q2 改成按「季度」看趋势
       （提示：substr(InvoiceDate,1,4) 拿年，再配合 CASE 判断月份）
    2. 把 Q4 的费用项（StockCode 为 'M' / 'DOT' / 'POST'）剔除后重排榜单，
       看看真正的 Top 10 是什么
    3. 自己加一个查询：每个国家的客单价排名
    写不出来没关系，改改上面的 SQL 试，报错了贴给我。
""")
