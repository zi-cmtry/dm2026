# -*- coding: utf-8 -*-
"""
第 7 课：客户流失预测（机器学习）

━━━ 这一课和你在学校学的机器学习有什么不同？━━━
    课上的机器学习：老师给你一个干净的 CSV，有 X 和 y，你调 sklearn。
    真实工作的机器学习：【y 要你自己定义】。

    这一课最重要的一句话：
        定义标签（什么算"流失"）比选模型重要 10 倍。

━━━ 核心方法：观察期 / 表现期 切分 ━━━
    ┌─────────────── 观察期 ───────────────┬──── 表现期 ────┐
    2009-12 ──────────────────────── 2011-06 │ 2011-07 ── 2011-12

    · 用【观察期】的行为构造特征 X（他过去怎么买的）
    · 用【表现期】是否有购买来打标签 y（他后来还回来吗）
    · 两个窗口绝不重叠 ← 这是防数据泄漏的关键

━━━ 你会学到的 ━━━
    1. 怎么把交易流水变成一行一个客户的"特征表"
    2. 观察期/表现期切分（防数据泄漏）
    3. 类别不平衡下为什么不能看准确率
    4. AUC 是什么，怎么解读
    5. 特征重要性 → 翻译成业务动作

运行方式（仓库根目录下）：
    python src/07_流失预测.py
"""

import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 不开窗口，只存图片
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# 让图里能正常显示中文
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "processed" / "retail.db"
FIG = ROOT / "reports" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

OBS_END = "2011-06-30"     # 观察期结束（也是预测时点）
PERF_END = "2011-12-31"    # 表现期结束

LINE = "=" * 80


def section(t: str) -> None:
    print("\n" + LINE)
    print(t)
    print(LINE)


print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║  第 7 课：客户流失预测                                                        ║
║                                                                              ║
║  业务问题：站在 2011 年 6 月底，我能不能提前识别出                          ║
║            「接下来半年不会再来的客户」，从而提前做召回？                       ║
║                                                                              ║
║  这个问题如果答对了，就是实打实的钱：                                          ║
║  召回一个老客户的成本，远低于拉一个新客户。                                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

con = sqlite3.connect(DB)


# ---------------------------------------------------------------
# 步骤 1：构造特征表 + 标签
# ---------------------------------------------------------------
section(f"步骤 1：构造特征表（观察期 = 2009-12-01 ~ {OBS_END}）")

FEATURE_SQL = f"""
WITH 观察期行为 AS (
    SELECT Customer_ID                          AS 客户ID,
           MIN(InvoiceDate)                     AS 首购时间,
           MAX(InvoiceDate)                     AS 最近购买时间,
           COUNT(DISTINCT Invoice)              AS 订单数,
           SUM(Amount)                          AS 总消费,
           COUNT(DISTINCT StockCode)            AS 商品种类数,
           COUNT(DISTINCT substr(InvoiceDate,1,10)) AS 购买天数,
           AVG(Amount)                          AS 平均单笔金额
    FROM sales_known
    WHERE InvoiceDate <= '{OBS_END} 23:59:59'
    GROUP BY Customer_ID
),
表现期回购 AS (
    -- ⚠️ 这里必须起别名。CTE 对外只暴露它 SELECT 输出的列名，
    --    不写 AS 客户ID 的话，外界看到的是 Customer_ID，JOIN 时就对不上。
    SELECT DISTINCT Customer_ID AS 客户ID
    FROM sales_known
    WHERE InvoiceDate > '{OBS_END} 23:59:59'
)
SELECT b.客户ID,
       -- 客户年龄 = 从首购到预测时点过了多少天
       CAST(julianday('{OBS_END}') - julianday(b.首购时间) AS INTEGER)   AS 客户年龄天数,
       -- R：距今最近一次购买过了多少天
       CAST(julianday('{OBS_END}') - julianday(b.最近购买时间) AS INTEGER) AS 距上次购买天数,
       b.订单数,
       ROUND(b.总消费, 2)                                                  AS 总消费,
       b.商品种类数,
       b.购买天数,
       ROUND(b.平均单笔金额, 2)                                            AS 平均单笔金额,
       -- 购买频率：平均每 30 天下几单
       ROUND(b.订单数 * 30.0
             / NULLIF(CAST(julianday('{OBS_END}') - julianday(b.首购时间) AS INTEGER), 0), 3) AS 月均订单数,
       -- 平均购买间隔天数
       ROUND(CAST(julianday('{OBS_END}') - julianday(b.首购时间) AS INTEGER) * 1.0
             / b.订单数, 1)                                                AS 平均购买间隔,
       CASE WHEN p.客户ID IS NULL THEN 1 ELSE 0 END                        AS 是否流失
FROM 观察期行为 b
LEFT JOIN 表现期回购 p ON b.客户ID = p.客户ID
"""

df = pd.read_sql(FEATURE_SQL, con)
print(f"样本数（客户数）: {len(df):,}")
print(f"特征列          : {[c for c in df.columns if c not in ('客户ID', '是否流失')]}")
print(f"\n前 5 行预览:")
print(df.head().to_string(index=False))

churn_rate = df["是否流失"].mean()
print(f"""
💡 标签定义说明（这一步比选模型重要得多）：
   · 我们站在 {OBS_END} 做预测，往回看构造特征，往前看定义标签
   · 「流失」= 观察期内有购买，但 {OBS_END} 之后到 {PERF_END} 一次都没买
   · 流失率 = {churn_rate:.2%}  ← {'类别不平衡，不能只看准确率！' if churn_rate < 0.4 or churn_rate > 0.6 else '分布较均衡'}

   ⚠️ 如果我把"流失"定义成"3 个月没买"，流失率会立刻变成另一个数字，
      模型的难度和业务含义都会变。所以标签定义必须写进报告，说明理由。
""")


# ---------------------------------------------------------------
# 步骤 2：切分训练/测试集
# ---------------------------------------------------------------
section("步骤 2：切分数据集（以及为什么不能随便切）")

FEATURES = [
    "客户年龄天数",
    "距上次购买天数",
    "订单数",
    "总消费",
    "商品种类数",
    "购买天数",
    "平均单笔金额",
    "月均订单数",
    "平均购买间隔",
]

X = df[FEATURES].fillna(0)
y = df["是否流失"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, random_state=42, stratify=y
)

print(f"训练集: {len(X_train):,} 条   测试集: {len(X_test):,} 条")
print(f"训练集流失率: {y_train.mean():.2%}   测试集流失率: {y_test.mean():.2%}")

print("""
💡 关于数据泄漏（Data Leakage）—— 面试高频考点：

   最危险的做法：把【表现期的信息】混进特征里。
   比如把"客户总消费"算成了包含表现期的全量数据 ——
   模型会表现得异常好（AUC 0.99），但上线就废，因为预测时你根本
   拿不到未来数据。

   我们的做法：特征只取自观察期，标签取自表现期，两者时间不重叠。
   这就是「时间切分」的思想，比随机切分更贴近真实业务。

   另外 stratify=y 保证训练集和测试集的流失比例一致 ——
   类别不平衡时这个参数很重要。
""")


# ---------------------------------------------------------------
# 步骤 3：训练两个模型对比
# ---------------------------------------------------------------
section("步骤 3：训练模型（逻辑回归 vs 随机森林）")

# 逻辑回归对量纲敏感，需要标准化
scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s = scaler.transform(X_test)

models = {
    "逻辑回归": (LogisticRegression(max_iter=2000, random_state=42), X_train_s, X_test_s),
    "随机森林": (RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1), X_train, X_test),
}

results = {}
for name, (model, xtr, xte) in models.items():
    model.fit(xtr, y_train)
    proba = model.predict_proba(xte)[:, 1]
    pred = model.predict(xte)
    auc = roc_auc_score(y_test, proba)
    acc = (pred == y_test).mean()
    results[name] = {"model": model, "proba": proba, "pred": pred, "auc": auc, "acc": acc}
    print(f"  {name:<10} 准确率 {acc:.4f}   AUC {auc:.4f}")

print("""
💡 为什么必须看 AUC，不能只看准确率？

   假设流失率是 30%。如果我写一个蠢模型「全部预测为不流失」，
   准确率 = 70%。听起来不错？但它一个流失客户都抓不到，毫无价值。

   AUC 衡量的是「模型把流失客户排在非流失客户前面的能力」：
      0.5 = 瞎猜      0.7 = 可用      0.8+ = 好      0.9+ = 优秀
   而且 AUC 不受类别比例影响，所以不平衡数据下它是首选指标。
""")


# ---------------------------------------------------------------
# 步骤 4：详细评估
# ---------------------------------------------------------------
section("步骤 4：看混淆矩阵和分类报告（比一个数字信息量大得多）")

best_name = max(results, key=lambda k: results[k]["auc"])
best = results[best_name]
print(f"最优模型: {best_name}  (AUC = {best['auc']:.4f})\n")

cm = confusion_matrix(y_test, best["pred"])
print("混淆矩阵（行=真实，列=预测）:")
print(pd.DataFrame(
    cm,
    index=["真实:未流失", "真实:流失"],
    columns=["预测:未流失", "预测:流失"],
).to_string())

tn, fp, fn, tp = cm.ravel()
print(f"""
   TN={tn}  FP={fp}  FN={fn}  TP={tp}

   召回率(Recall) = TP/(TP+FN) = {tp/(tp+fn):.3f}  ← 该抓的流失客户抓到了多少
   精确率(Precision) = TP/(TP+FP) = {tp/(tp+fp) if (tp+fp) else 0:.3f}  ← 抓出来的人里有多少是真流失

💡 业务上怎么选？看「漏掉一个流失客户」和「误报一个」哪个更贵：
   · 召回券成本很低 → 宁可多抓（提高 Recall，容忍低 Precision）
   · 一对一电话回访成本高 → 必须准（提高 Precision）
   这不是技术问题，是业务问题。面试答出这一层，说明你懂业务。
""")

print(classification_report(y_test, best["pred"], target_names=["未流失", "流失"], digits=3))


# ---------------------------------------------------------------
# 步骤 5：特征重要性
# ---------------------------------------------------------------
section("步骤 5：哪些特征最影响流失？（把模型翻译成业务语言）")

rf = results["随机森林"]["model"]
imp = pd.DataFrame({
    "特征": FEATURES,
    "重要性": rf.feature_importances_,
}).sort_values("重要性", ascending=False)

print(imp.to_string(index=False))

print("""
💡 怎么解读特征重要性：
   排在前面的特征，就是「最该盯住的预警信号」。
   比如如果"距上次购买天数"排第一，那业务动作就很明确：
   一旦客户超过 X 天没下单，就自动触发召回。
   这就是模型落地的方式 —— 不是跑个 AUC 就完事，而是产出【规则】。
""")

# 画图
fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

axes[0].barh(imp["特征"][::-1], imp["重要性"][::-1], color="#4C78A8")
axes[0].set_title(f"{best_name} — 特征重要性", fontsize=13)
axes[0].set_xlabel("重要性")

for name in results:
    fpr, tpr, _ = roc_curve(y_test, results[name]["proba"])
    axes[1].plot(fpr, tpr, label=f"{name} (AUC={results[name]['auc']:.3f})", linewidth=2)
axes[1].plot([0, 1], [0, 1], "k--", linewidth=1, label="随机猜测 (AUC=0.5)")
axes[1].set_xlabel("假正率 FPR")
axes[1].set_ylabel("真正率 TPR")
axes[1].set_title("ROC 曲线对比", fontsize=13)
axes[1].legend()
axes[1].grid(alpha=0.3)

plt.tight_layout()
out_png = FIG / "churn_model.png"
plt.savefig(out_png, dpi=130)
plt.close()
print(f"📊 图表已保存: {out_png.relative_to(ROOT)}")


# ---------------------------------------------------------------
# 步骤 6：把模型变成可执行的名单
# ---------------------------------------------------------------
section("步骤 6：输出高风险客户名单（模型真正的交付物）")

df["流失概率"] = best["model"].predict_proba(
    scaler.transform(X) if best_name == "逻辑回归" else X
)[:, 1]

high_risk = df.nlargest(20, "流失概率")[
    ["客户ID", "距上次购买天数", "订单数", "总消费", "流失概率", "是否流失"]
].copy()
high_risk["流失概率"] = high_risk["流失概率"].round(3)

print("流失风险最高的 20 位客户（按模型打分排序）:")
print(high_risk.to_string(index=False))

caught = int(high_risk["是否流失"].sum())
print(f"\n  ↑ 这 20 人里，实际真的流失了 {caught} 人（命中率 {caught / 20:.0%}）")

total_value = high_risk["总消费"].sum()
print(f"""
💡 这里有一个【极易犯的错误】—— 我第一版就犯了，必须记下来：

   第一版我写的是：df[df["是否流失"] == 0]
   也就是"先只看最终没有流失的客户，再从里面挑风险最高的 20 个"。

   ⚠️ 这是【用未来信息筛选今天的名单】—— 典型的数据泄漏！
   站在 2011-06-30，你根本不知道谁会在下半年流失。
   真实场景里你只能拿【当下的全部客户】打分，按概率排序去打电话。

   正确做法就是上面的代码：完全不碰「是否流失」这一列，
   直接按「流失概率」取 Top 20。标签只用来事后验证命中率。

   这条和面试里"什么是数据泄漏"是同一个考点，
   但大多数人只会背定义，说不出这种具体形态。

💡 这才是模型的最终交付物 —— 一份【运营可以直接拿去打电话的名单】。
   这 20 位客户在观察期的累计消费是 £{total_value:,.2f}。
   如果按经验能挽回 30%，就是 £{total_value * 0.3:,.2f} 的直接收益。

   ⚠️ 另外注意：名单里几乎都是「只买过 1 次、且已经 400+ 天没来」的客户。
      这说明模型学到的最强信号就是"买一次 + 长期沉默"。
      但这类客户本身价值低，召回性价比可能不高。
      真正该做的下一步是：在【高消费客户】里筛出高流失概率的人，
      那才是值得花电话费的名单。
""")

con.close()

print("\n" + LINE)
print("第 7 课结束。你已经走完了一个完整的机器学习项目：定义标签 → 特征工程 →")
print("时间切分 → 建模 → 评估 → 特征解释 → 输出业务名单。")
print("下一课：Streamlit 交互看板")
print(LINE)

print("""
━━━ 面试会怎么问？━━━
    Q: 你这个模型的 y 是怎么定义的？
    A: 站在 2011-06-30 做预测，观察期构造特征，表现期（后半年）无购买记为流失。
       标签定义比模型选择重要，因为它决定了业务含义。

    Q: 为什么 AUC 只有 0.7 几，是不是模型不好？
    A: 客户流失本质上有随机性，而且我们只有交易数据，没有客服记录、
       营销触达记录等特征。0.7~0.8 在客户流失预测里是正常水平。
       真正要证明价值的是「用这个名单做召回，收益是否大于成本」。

    Q: 怎么做防止数据泄漏？
    A: 时间切分。特征只用观察期数据，标签用表现期数据，两个窗口不重叠。
       另外要注意聚合特征不能跨越切分点 —— 这是最常见的泄漏来源。

━━━ 给你自己的练习 ━━━
    1. 把预测时点从 2011-06-30 改成 2011-03-31，重跑一遍，
       看 AUC 变化大不大（提示：改 OBS_END）
    2. 加一个新特征：客户买过多少个"高价值商品"（比如单价 > 10 的）
    3. 挑战题：把 model.predict 的阈值从 0.5 改成 0.3，
       看召回率和精确率怎么变 —— 这直接对应运营策略的选择
""")
