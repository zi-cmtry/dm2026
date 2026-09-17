# dm2026 — 数据挖掘与机器学习练手项目

成都理工大学 · 大数据管理与应用 · 大二

这个仓库记录我从零开始做数据分析项目的全过程。目标不是「写很多代码」，
而是把下面这条链路**完整走通至少一遍**：

```
取数  →  清洗  →  存储(SQL)  →  分析/建模  →  可视化  →  讲出结论
```

要求：每一段代码我都能讲清楚为什么这么写。面试和保研答辩只会盯着**能讲透的那一个项目**问。

---

## 目录结构

```
dm2026/
├── README.md              # 你正在看的这个
├── requirements.txt       # 依赖清单
├── .gitignore             # 哪些文件不传 GitHub
│
├── data/
│   ├── raw/               # 原始数据（只读，绝不手改）
│   └── processed/         # 清洗后的数据
│
├── notebooks/             # Jupyter，用来探索和试错
├── src/                   # 正式代码，能直接跑的
│   └── first_data_demo.py
├── output/                # 图表、导出结果
└── reports/               # 报告、PPT
```

**为什么 `data/raw` 要单独放并且不许改？**
因为数据分析最怕的一件事是：改完数据发现算错了，却回不到原始状态。
`raw` 永远保持原样，所有清洗结果写到 `processed`。这条规矩能救命。

---

## 环境

- Python 3.14.3（Windows）
- 核心库：numpy / pandas / scikit-learn / matplotlib / seaborn / scipy
- 数据库：SQLite（Python 内置，练 SQL 零门槛）

安装依赖：

```bash
pip install -r requirements.txt
```

---

## 快速开始

```bash
# 从仓库根目录运行
python src/first_data_demo.py
```

它会输出环境自检信息，然后用 **pandas 和 SQL 各做一遍同样的分组聚合**——
对照着看，你会发现 `groupby` 和 `GROUP BY` 是同一件事的两种写法。

---

## 进度

- [x] 开发环境搭建（Python + 库依赖）
- [x] git 安装与全局配置
- [x] 第一个可运行脚本：`src/first_data_demo.py`
- [ ] 确定主线项目方向
- [ ] 拿到第一份真实数据
- [ ] 数据入库 + 用 SQL 做分析
- [ ] 特征工程与建模
- [ ] 可视化看板
- [ ] 项目报告

---

## 笔记

遇到的关键问题和解决过程记在这里，方便以后回看。

### 2026 · 环境踩坑

- `D:\deepseek` 目录无法写入：该目录所有者是 `BUILTIN\Administrators`，
  普通用户只有 `RX`（读+执行）权限。**结论：项目目录一律放在用户目录下。**
- Windows 上 git 默认会把中文文件名显示成八进制转义（`\346\226\207`），
  需要 `git config --global core.quotepath false` 关掉。
