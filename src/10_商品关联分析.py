# -*- coding: utf-8 -*-
"""
第 10 课：商品关联分析（购物篮分析）

━━━ 业务问题 ━━━
    哪些商品经常被一起买？
    → 答案直接变成「捆绑销售」「关联推荐」「货架摆放」的策略。

━━━ 三个核心指标（面试必考）━━━
    支持度 Support(A→B)    = 同时含 A 和 B 的订单数 / 总订单数
                              「这个组合有多常见？」
    置信度 Confidence(A→B) = 同时含 A 和 B 的订单数 / 含 A 的订单数
                              「买了 A 的人里，有多少也买了 B？」
    提升度 Lift(A→B)       = Confidence(A→B) / Support(B)
                              「买 A 对买 B 到底有没有促进作用？」

    ⭐ 提升度是三个里最重要的：
        Lift > 1  买了 A 确实更可能买 B（正相关，值得捆绑）
        Lift = 1  两者独立（没有关联，绑了也没用）
        Lift < 1  买了 A 反而不太会买 B（互斥，比如竞品）

    ⚠️ 新手最容易犯的错：只看置信度就下结论。
       如果 B 本身就是爆款（人人都买），那 Confidence(A→B) 天然很高，
       但这不代表 A 和 B 有关联 —— 必须用 Lift 校正。

━━━ 算法思路：Apriori 的第一步是「剪枝」━━━
    40,077 张发票，每张平均 26 个商品 → 两两组合约 1300 万对，直接算会爆炸。
    所以先筛掉不频繁的商品，只在「频繁项」之间找组合。

运行方式（仓库根目录下）：
    python src/10_商品关联分析.py
"""

import sqlite3
import textwrap
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "processed" / "retail.db"

# 费用项 / 非商品编码，必须排除（第 4 课发现的）
NON_PRODUCT = ("M", "DOT", "POST", "D", "C2", "BANK CHARGES", "PADS", "AMAZONFEE", "S", "CRUK")

MIN_INVOICES = 150   # 商品至少要出现在这么多张发票里，才参与组合

LINE = "=" * 84


def section(t: str) -> None:
    print("\n" + LINE)
    print(t)
    print(LINE)


con = sqlite3.connect(DB)

print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║  第 10 课：商品关联分析（购物篮分析）                                          ║
║                                                                              ║
║  你肯定见过「买了这个的人还买了……」—— 那个推荐位背后就是这个算法。            ║
║  电商、超市、内容平台，全都靠它做捆绑和推荐。                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

# ---------------------------------------------------------------
# 步骤 1：构建购物篮
# ---------------------------------------------------------------
section("步骤 1：把交易流水变成「购物篮」——一行一张发票，一列一个商品")

placeholders = ", ".join(["?"] * len(NON_PRODUCT))

basket_sql = f"""
WITH 频繁商品 AS (
    -- 剪枝：先找出足够频繁的商品，只在它们之间找组合
    SELECT StockCode
    FROM sales
    WHERE StockCode NOT IN ({placeholders})
    GROUP BY StockCode
    HAVING COUNT(DISTINCT Invoice) >= ?
)
SELECT DISTINCT s.Invoice AS 发票号, s.StockCode AS 商品编码
FROM sales s
JOIN 频繁商品 f ON s.StockCode = f.StockCode
"""

basket = pd.read_sql(basket_sql, con, params=(*NON_PRODUCT, MIN_INVOICES))
n_invoices = basket["发票号"].nunique()
n_items = basket["商品编码"].nunique()

print(f"  频繁商品（出现在 >= {MIN_INVOICES} 张发票里）: {n_items} 个")
print(f"  涉及的发票数                              : {n_invoices:,} 张")
print()
print("  购物篮长这样（前 8 行）:")
print(textwrap.indent(basket.head(8).to_string(index=False), "    "))

total_all = con.execute("SELECT COUNT(DISTINCT Invoice) FROM sales").fetchone()[0]
print(f"""
    💡 注意分母的选择：
       支持度可以除以「全部发票数」({total_all:,})，
       也可以除以「含频繁商品的发票数」({n_invoices:,})。

       我们用后者 —— 因为我们只在频繁商品范围内找规律，
       分母保持一致才不会被大量长尾商品稀释。
       ⚠️ 但报告里必须写明用的是哪个分母，否则数字没法复现。
""")


# ---------------------------------------------------------------
# 步骤 2：用 SQL 自连接找出商品对
# ---------------------------------------------------------------
section("步骤 2：SQL 自连接 —— 找出同一张发票里的商品对")

PAIR_SQL = f"""
WITH 频繁商品 AS (
    SELECT StockCode
    FROM sales
    WHERE StockCode NOT IN ({placeholders})
    GROUP BY StockCode
    HAVING COUNT(DISTINCT Invoice) >= ?
),
篮子 AS (
    SELECT DISTINCT s.Invoice AS 发票号, s.StockCode AS 编码
    FROM sales s
    JOIN 频繁商品 f ON s.StockCode = f.StockCode
),
商品对 AS (
    -- 自连接：让同一张发票里的商品两两配对
    -- a.编码 < b.编码 是关键：这样每对只出现一次，不会算成 (A,B) 和 (B,A) 两遍
    SELECT a.编码 AS A, b.编码 AS B, COUNT(DISTINCT a.发票号) AS 共现发票数
    FROM 篮子 a
    JOIN 篮子 b ON a.发票号 = b.发票号 AND a.编码 < b.编码
    GROUP BY a.编码, b.编码
),
单品 AS (
    SELECT 编码, COUNT(DISTINCT 发票号) AS 单品发票数 FROM 篮子 GROUP BY 编码
)
SELECT p.A                AS 商品A,
       p.B                AS 商品B,
       p.共现发票数        AS 共现发票数,
       sa.单品发票数       AS A发票数,
       sb.单品发票数       AS B发票数
FROM 商品对 p
JOIN 单品 sa ON p.A = sa.编码
JOIN 单品 sb ON p.B = sb.编码
WHERE p.共现发票数 >= 80
"""

# ⚠️ 踩坑记录：SQLite 不允许「命名参数 :name」和「位置参数 ?」混用在同一条语句里。
#    第一版我写了 :n_total 又想用序列传参，直接报 ProgrammingError。
#    总发票数在 Python 侧本来就是已知常量，读完之后加一列最简单。
pairs = pd.read_sql(PAIR_SQL, con, params=(*NON_PRODUCT, MIN_INVOICES))
pairs["总发票数"] = n_invoices

print(f"  共现发票数 >= 80 的商品对: {len(pairs):,} 个")
print()
print("  自连接的结果长这样（前 8 行）:")
print(textwrap.indent(pairs.head(8).to_string(index=False), "    "))

print("""
    💡 三个技术点：
       ① 自连接（SELF JOIN）= 同一张表 JOIN 自己。
          这是购物篮、留存、层级结构分析的通用套路。
       ② a.编码 < b.编码 是去重的关键。
          没有它，A-B 和 B-A 会被当成两对，结果全部翻倍。
       ③ COUNT(DISTINCT a.发票号) 而不是 COUNT(*)
          因为连接后每张发票会出现多次，必须去重计数。
""")

if pairs.empty:
    con.close()
    raise SystemExit("没有找到符合条件的商品对，请调低 MIN_INVOICES 或降低共现门槛。")


# ---------------------------------------------------------------
# 步骤 3：计算三个指标
# ---------------------------------------------------------------
section("步骤 3：计算支持度 / 置信度 / 提升度")

pairs["支持度"] = (pairs["共现发票数"] / pairs["总发票数"]).round(4)
pairs["置信度_A到B"] = (pairs["共现发票数"] / pairs["A发票数"]).round(4)
pairs["置信度_B到A"] = (pairs["共现发票数"] / pairs["B发票数"]).round(4)
pairs["提升度"] = (pairs["置信度_A到B"] / (pairs["B发票数"] / pairs["总发票数"])).round(2)

# 补上商品名
names = pd.read_sql(
    f"""SELECT StockCode, MAX(Description) AS 名称 FROM sales
        WHERE StockCode NOT IN ({placeholders}) GROUP BY StockCode""",
    con, params=NON_PRODUCT,
).set_index("StockCode")["名称"]

pairs["商品A名"] = pairs["商品A"].map(names).str.slice(0, 30)
pairs["商品B名"] = pairs["商品B"].map(names).str.slice(0, 30)

show_cols = ["商品A", "商品A名", "商品B", "商品B名", "共现发票数", "支持度", "置信度_A到B", "提升度"]

print("【按提升度排序 Top 15】—— 最强的关联关系")
top_lift = pairs.nlargest(15, "提升度")[show_cols]
print(textwrap.indent(top_lift.to_string(index=False), "    "))

print("\n【按共现发票数排序 Top 15】—— 最常见的组合")
top_count = pairs.nlargest(15, "共现发票数")[show_cols]
print(textwrap.indent(top_count.to_string(index=False), "    "))

print("""
    💡 这两张表要对照着看，它们回答的是不同问题：

       · 按「共现次数」排 → 最常一起出现的组合（量大，适合做捆绑促销）
       · 按「提升度」排   → 关联最强的组合（哪怕量小，也说明有真实关联）
""")


# ---------------------------------------------------------------
# 步骤 4：验证提升度的意义
# ---------------------------------------------------------------
section("步骤 4：为什么必须看提升度？（用一个反例说明）")

# 找出「置信度高但提升度低」的组合
misleading = pairs[(pairs["置信度_A到B"] >= 0.6) & (pairs["提升度"] < 1.5)].nlargest(
    8, "置信度_A到B"
)[show_cols]

if not misleading.empty:
    print("  这些组合的「置信度」很高，但「提升度」很低 —— 是假关联：")
    print(textwrap.indent(misleading.to_string(index=False), "    "))
    print("""
    💡 怎么读：
       置信度高说明「买了 A 的人大多也买了 B」。
       但如果 B 本身就是人人都买的爆款，那这个高置信度毫无信息量 ——
       提升度接近 1 就说明：买 A 对买 B 没有任何促进作用。

       这就是「关联规则」里最经典的陷阱：
       ⭐ 只看置信度会得出错误的业务结论，必须用提升度校正。
       面试里能主动说出这一点，直接和其他候选人拉开差距。
""")
else:
    print("  当前阈值下没有找到「高置信度 + 低提升度」的典型反例。")
    print("  （这本身也是个发现：说明这份数据里商品间的关联普遍是真实的）")


# ---------------------------------------------------------------
# 步骤 5：落盘
# ---------------------------------------------------------------
section("步骤 5：保存结果")

out = ROOT / "reports" / "商品关联规则.csv"
pairs.sort_values("提升度", ascending=False).to_csv(out, index=False, encoding="utf-8-sig")
print(f"  已保存 {len(pairs):,} 条关联规则 -> {out.relative_to(ROOT)}")

con.close()

print("\n" + LINE)
print("第 10 课结束。你现在掌握了购物篮分析的完整方法。")
print(LINE)

print("""
━━━ 业务落地：把规则变成钱 ━━━
    · 提升度高 + 共现量大  → 做「组合套餐」，直接提高客单价
    · 提升度高 + 共现量小  → 做「关联推荐」（买了 A 的人还买了 B）
    · 提升度 < 1（互斥）   → 说明是替代品，别放一起促销，会自相残杀

━━━ 面试会怎么问？━━━
    Q: Apriori 算法你了解吗？
    A: 核心是「逐层剪枝」——先找出频繁 1 项集，再由它生成候选 2 项集，
       反复迭代。关键是「一个项集如果不频繁，它的超集一定也不频繁」，
       所以可以大量剪枝。
       ⭐ 这里要主动补一句「本项目因为组合爆炸（1300 万对），
          我用的是 SQL 自连接 + 频繁项预筛，本质是 Apriori 的第一步剪枝」。

    Q: 支持度、置信度、提升度有什么区别？
    A: 见本文件开头的定义。核心是：支持度看「普遍性」，
       置信度看「条件概率」，提升度看「是否真的有促进作用」。

    Q: 提升度怎么算的？
    A: Lift(A→B) = Confidence(A→B) / Support(B)。分母是 B 自身的支持度。

━━━ 给你自己的练习 ━━━
    1. 把 MIN_INVOICES 从 150 调到 300，看关联规则怎么变（提示：项越少，规则越少但越强）
    2. 加一个筛选：只看提升度 > 2 的规则，人工判断这些组合在业务上说得通吗
    3. 挑战题：把「共现发票数 >= 80」换成不同阈值，观察结果稳定性
       —— 阈值敏感度高说明规则不稳健，不能直接拿去用
""")
