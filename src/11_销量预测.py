# -*- coding: utf-8 -*-
"""
第 11 课：销售额时间序列预测

━━━ 业务问题 ━━━
    未来几个月的销售额大概是多少？
    → 备货、排产、现金流规划都要看它。

━━━ 这一课最重要的态度：诚实面对数据量 ━━━
    ⚠️ 我们只有 24 个月的月度数据。
    季节性周期是 12 个月，24 个月 = 只有 2 个完整周期。
    这对季节模型来说【非常少】。

    很多人会硬跑一个看起来很专业的模型，然后给出精确到小数的预测数字 ——
    这是不负责任的。正确的做法是：
        · 用多个方法做对比，看它们是否一致
        · 明确说明不确定性
        · 把「数据量不足」写进局限性

━━━ 三种方法（从简单到复杂）━━━
    ① 季节朴素法   ŷ(t) = y(t-12)          ← 基线。如果复杂模型打不过它，说明模型没用
    ② Holt-Winters 指数平滑                 ← 经典时间序列方法
    ③ 线性回归 + 月度哑变量                  ← 把季节性当成特征喂给模型

运行方式（仓库根目录下）：
    python src/11_销量预测.py
"""

import sqlite3
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.seasonal import seasonal_decompose

warnings.filterwarnings("ignore")

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "processed" / "retail.db"
FIG = ROOT / "reports" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

LINE = "=" * 84


def section(t: str) -> None:
    print("\n" + LINE)
    print(t)
    print(LINE)


print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║  第 11 课：销售额时间序列预测                                                  ║
║                                                                              ║
║  时间序列和普通机器学习最大的区别：                                             ║
║    普通 ML：样本之间【相互独立】（今天这个客户和明天那个没关系）                 ║
║    时间序列：样本之间【有顺序、有依赖】（这个月的销售额和上个月有关）              ║
║                                                                              ║
║  所以【绝对不能随机打乱切分训练集/测试集】—— 那等于用未来预测过去。              ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

con = sqlite3.connect(DB)

# ---------------------------------------------------------------
# 步骤 1：构建月度序列
# ---------------------------------------------------------------
section("步骤 1：构建月度销售额序列")

ts = pd.read_sql(
    """
    SELECT substr(InvoiceDate, 1, 7) AS 月份,
           ROUND(SUM(Amount), 2)     AS 销售额,
           COUNT(DISTINCT Invoice)   AS 订单数
    FROM sales
    GROUP BY 月份
    ORDER BY 月份
    """,
    con,
).set_index("月份")

print(f"  原始序列共 {len(ts)} 个月：{ts.index[0]} ~ {ts.index[-1]}")
print()
print(ts.to_string())

print("""
    ⚠️ 立刻发现两个问题：
       ① 2011-12 的数据只到 12 月 9 日 —— 是个【残缺月】，必须剔除，
          否则会被模型当成"12 月销售暴跌"，污染季节性判断。
       ② 剔除后剩 24 个月，正好 2 个完整周期 —— 对季节模型来说仍然偏少。
""")

# 剔除残缺月
ts = ts.iloc[:-1]
ts.index = pd.PeriodIndex(ts.index, freq="M")

series = ts["销售额"]
print(f"  清洗后序列：{len(series)} 个月  ({series.index[0]} ~ {series.index[-1]})")
print(f"  月均销售额：£{series.mean():,.0f}   标准差：£{series.std():,.0f}")


# ---------------------------------------------------------------
# 步骤 2：分解趋势与季节性
# ---------------------------------------------------------------
section("步骤 2：把序列拆成「趋势 + 季节 + 残差」")

decomp = seasonal_decompose(series.values, model="additive", period=12)

print(f"  趋势项波动范围  : £{decomp.trend[~np.isnan(decomp.trend)].min():,.0f} ~ £{decomp.trend[~np.isnan(decomp.trend)].max():,.0f}")
print(f"  季节项波动范围  : £{np.nanmin(decomp.seasonal):,.0f} ~ £{np.nanmax(decomp.seasonal):,.0f}")

# ⚠️ 踩坑记录：decomp.seasonal 是【按下标】与输入序列对齐的，不是按自然月对齐！
#    我们的序列从 2009-12 开始，所以 seasonal[0] 是 12 月、seasonal[11] 是 11 月。
#    第一版我直接用 range(1,13) 当标签，导致整个季节性解读错位了一格
#    （把 12 月的 +635,932 标成了"11月"）。
#    验证方法：11 月实际值减趋势 ≈ +637,000，与修正后的数值吻合。
start_month = series.index[0].month
seasonal_idx = pd.Series(
    decomp.seasonal[:12],
    index=[(start_month - 1 + i) % 12 + 1 for i in range(12)],
).sort_index()

print(f"\n  各月的季节性偏移（相对全年均值）：")
for m, v in seasonal_idx.items():
    bar = "█" * int(abs(v) / 8000)
    sign = "+" if v >= 0 else "-"
    print(f"    {str(m) + '月':>4}  {sign}£{abs(v):>9,.0f}  {bar}")

print(f"""
    💡 怎么读季节性：
       · 正的月份说明「这个月天然比全年平均高」
       · 本次结果：11 月最高（+£{seasonal_idx[11]:,.0f}），2 月最低（£{seasonal_idx[2]:,.0f}）
       · 11 月对应圣诞备货季 —— 这个规律【不是模型学出来的，是业务决定的】，
         所以它稳定、可预测，也值得写进报告
       · ⚠️ 但注意：数据只覆盖 2 年，每月的季节性只有 2 个样本，
         所以这个季节性估计的置信度【很低】，不能当铁律
""")


# ---------------------------------------------------------------
# 步骤 3：建模对比（时间切分，不打乱）
# ---------------------------------------------------------------
section("步骤 3：三种方法对比（时间切分：前 19 个月训练，后 5 个月测试）")

HOLDOUT = 5
train, test = series.iloc[:-HOLDOUT], series.iloc[-HOLDOUT:]

print(f"  训练集: {train.index[0]} ~ {train.index[-1]}  ({len(train)} 个月)")
print(f"  测试集: {test.index[0]} ~ {test.index[-1]}  ({len(test)} 个月)")


def mape(y_true, y_pred) -> float:
    """平均绝对百分比误差 —— 时间序列最常用的评价指标"""
    y_true, y_pred = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    return float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100)


predictions: dict[str, np.ndarray] = {}

# ── 方法 ①：季节朴素法 ────────────────────────────────
pred_naive = series.values[-HOLDOUT - 12: -12]
predictions["① 季节朴素法"] = pred_naive

# ── 方法 ②：Holt-Winters 指数平滑 ──────────────────────
try:
    hw = ExponentialSmoothing(
        train.values,
        trend="add",
        seasonal="add",
        seasonal_periods=12,
        initialization_method="estimated",
    ).fit()
    predictions["② Holt-Winters"] = hw.forecast(HOLDOUT)
except Exception as exc:  # 数据太少时可能拟合失败
    print(f"  [跳过 Holt-Winters] {exc}")

# ── 方法 ③：线性回归 + 月度哑变量 ──────────────────────
def make_features(idx: pd.PeriodIndex) -> pd.DataFrame:
    return pd.DataFrame({
        "趋势": np.arange(len(idx)),
        "月份": idx.month,
    })


X_train = pd.get_dummies(make_features(train.index), columns=["月份"], drop_first=True)
lr = LinearRegression().fit(X_train, train.values)

X_test = pd.get_dummies(make_features(test.index), columns=["月份"], drop_first=True)
X_test = X_test.reindex(columns=X_train.columns, fill_value=0)
predictions["③ 线性回归+月度"] = lr.predict(X_test)


# ── 评估 ──────────────────────────────────────────────
section("步骤 3b：评估结果")

rows = []
for name, pred in predictions.items():
    rows.append({
        "方法": name,
        "MAPE(%)": round(mape(test.values, pred), 2),
        "MAE(£)": round(float(np.mean(np.abs(test.values - pred))), 0),
    })

result = pd.DataFrame(rows).sort_values("MAPE(%)")
print(result.to_string(index=False))

print("\n  逐月实际 vs 预测：")
compare = pd.DataFrame({"实际": test.values}, index=[str(i) for i in test.index])
for name, pred in predictions.items():
    compare[name] = np.round(pred, 0)
print(compare.to_string())

best = result.iloc[0]["方法"]
print(f"""
    💡 怎么读这张表：

       · 「季节朴素法」是最重要的基线 —— 它只做一件事：
         拿去年同月的数字当预测。**任何复杂模型都应该打得过它**，
         打不过就说明复杂模型是浪费。

       · 只有 5 个测试点，MAPE 的方差很大。
         一个月的异常就能让排名翻转 —— 所以不要过度解读小数点后的差异。

       · 本次最优：{best}
""")


# ---------------------------------------------------------------
# 步骤 4：用全量数据重训，预测未来
# ---------------------------------------------------------------
section("步骤 4：用全部 24 个月重训，预测未来 3 个月")

future_idx = pd.period_range(series.index[-1] + 1, periods=3, freq="M")

final_preds = {}
try:
    hw_full = ExponentialSmoothing(
        series.values, trend="add", seasonal="add",
        seasonal_periods=12, initialization_method="estimated",
    ).fit()
    final_preds["Holt-Winters"] = hw_full.forecast(3)
except Exception as exc:
    print(f"  [Holt-Winters 全量拟合失败] {exc}")

X_all = pd.get_dummies(make_features(series.index), columns=["月份"], drop_first=True)
lr_full = LinearRegression().fit(X_all, series.values)
X_fut = pd.get_dummies(make_features(future_idx), columns=["月份"], drop_first=True)
X_fut = X_fut.reindex(columns=X_all.columns, fill_value=0)
final_preds["线性回归+月度"] = lr_full.predict(X_fut)

final_preds["季节朴素法"] = series.values[-12:-9]

forecast = pd.DataFrame({"月份": [str(i) for i in future_idx]})
for name, p in final_preds.items():
    forecast[name] = np.round(p, 0).astype(int)
forecast["三种方法均值"] = forecast[list(final_preds)].mean(axis=1).round(0).astype(int)
forecast["最小"] = forecast[list(final_preds)].min(axis=1)
forecast["最大"] = forecast[list(final_preds)].max(axis=1)

print(forecast.to_string(index=False))

print(f"""
    💡 为什么给「区间」而不是给一个数：

       三种方法的预测差异，本身就反映了不确定性。
       给运营报「下个月大约 £{forecast['三种方法均值'].iloc[0]:,.0f}，
       区间 £{forecast['最小'].iloc[0]:,.0f} ~ £{forecast['最大'].iloc[0]:,.0f}」，
       远比报一个精确到个位的数字【更有用、也更诚实】。

       ⚠️ 这个预测的可信度【不高】，原因必须写进报告：
          · 只有 24 个月 = 2 个完整季节周期，样本极少
          · 数据是 2011 年以前的，外部环境已经完全变了
          · 没有纳入促销、竞品、宏观经济等外生变量
          它的价值在于【演示方法】，不在于【真的拿去备货】。
""")


# ---------------------------------------------------------------
# 步骤 5：画图
# ---------------------------------------------------------------
section("步骤 5：出图")

fig, axes = plt.subplots(2, 1, figsize=(13, 8), height_ratios=[2, 1])

ax = axes[0]
x = np.arange(len(series))
ax.plot(x, series.values, "o-", label="实际销售额", color="#2E6DA4", linewidth=2, markersize=4)
test_x = np.arange(len(train), len(series))
ax.plot(test_x, test.values, "o", color="#D96A1F", label="测试集实际值", markersize=7, zorder=5)
for i, (name, pred) in enumerate(predictions.items()):
    ax.plot(test_x, pred, "s--", label=f"预测·{name}", markersize=5, alpha=0.85)

fut_x = np.arange(len(series), len(series) + 3)
ax.plot(fut_x, forecast["三种方法均值"], "k^--", label="未来 3 个月预测", markersize=8)
ax.fill_between(fut_x, forecast["最小"], forecast["最大"], color="grey", alpha=0.2, label="预测区间")

ticks = list(range(0, len(series), 3)) + [len(series) - 1]
ax.set_xticks(ticks)
ax.set_xticklabels([str(series.index[i]) for i in ticks], rotation=45, ha="right")
ax.set_ylabel("销售额 (£)")
ax.set_title("月度销售额：历史走势 · 模型对比 · 未来预测", fontsize=14)
ax.legend(fontsize=9)
ax.grid(alpha=0.3)

ax2 = axes[1]
ax2.bar(range(12), seasonal_idx.values,
        color=["#D96A1F" if v > 0 else "#4C78A8" for v in seasonal_idx.values])
ax2.axhline(0, color="black", linewidth=0.8)
ax2.set_xticks(range(12))
ax2.set_xticklabels([f"{m}月" for m in seasonal_idx.index])
ax2.set_ylabel("季节性偏移 (£)")
ax2.set_title("各月季节性偏移（正=旺季，负=淡季）", fontsize=12)
ax2.grid(alpha=0.3, axis="y")

plt.tight_layout()
out_png = FIG / "sales_forecast.png"
plt.savefig(out_png, dpi=130)
plt.close()
print(f"  📊 图表已保存: {out_png.relative_to(ROOT)}")

con.close()

print("\n" + LINE)
print("第 11 课结束。项目全部内容完成。")
print(LINE)

print("""
━━━ 时间序列的面试考点 ━━━
    Q: 时间序列能不能随机切分训练集测试集？
    A: 绝对不能。样本有时间依赖，随机切分会让模型"看到未来"，评估结果虚高。
       正确做法是按时间顺序切分（本项目：前 19 个月训练、后 5 个月测试）。

    Q: 为什么要跟「季节朴素法」比？
    A: 它是零成本基线。如果花大力气做的模型打不过"照抄去年同月"，
       说明模型没有捕捉到任何额外信息。

    Q: 时间序列的评估指标为什么常用 MAPE 而不是 RMSE？
    A: MAPE 是相对误差，业务方更容易理解（"平均偏了 8%"）。
       但 MAPE 在真实值接近 0 时会爆炸，所以要看场景选。

━━━ 给你自己的练习 ━━━
    1. 把 HOLDOUT 从 5 改成 8，看三个方法的排名会变吗
    2. 加一个外生特征：当月订单数，喂给线性回归（提示：预测时也得先预测订单数，
       这就变成了"多步预测"问题）
    3. 挑战题：用 sklearn 的 TimeSeriesSplit 做滚动回测，
       得到 5 折的 MAPE 均值，比单次切分可信得多
""")
