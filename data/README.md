# data/ · 数据说明

> **这个目录不在仓库里。**
> 原始 csv/zip 与中间 parquet 合计约 **2.6 GB**，超过 GitHub 单文件 100 MB 的上限，
> 所以仓库里只保留这份说明。

和淘宝项目不一样的地方：**这份数据的下载是脚本化的**，不需要手动去网站上找文件。

---

## 一、原始数据：一条命令下完

```bash
python code/00_fetch_data.py --check   # 先探测链接通不通，不下载
python code/00_fetch_data.py           # 再下缺的那些，已存在的不重复下
```

产物：`data/raw/LoanStats*.csv.zip`（原始文件只读，解压在 `01_build_loans.py` 里做）。

**为什么用直链而不是 Kaggle**：LendingClub 官网的文件是**按季度/半年切分**的，
直链免登录、可脚本化、可重跑；Kaggle 上那个 `accepted_2007_to_2018Q4.csv`
是同一批数据的合并版，但要登录，而且 1.6 GB 全塞一个文件反而不好管。

16 个文件的命名规律：

| 年份 | 文件 |
|---|---|
| 2007–2011 | `LoanStats3a.csv.zip` |
| 2012–2013 | `LoanStats3b.csv.zip` |
| 2014 | `LoanStats3c.csv.zip` |
| 2015 | `LoanStats3d.csv.zip` |
| 2016–2018 | `LoanStats_YYYYQn.csv.zip`（每季一个，共 12 个） |

---

## 二、运行环境

```bash
pip install duckdb pandas numpy matplotlib scipy pyarrow
```

项目在 Windows + Python 3.13 上跑通。

---

## 三、复现顺序

```bash
# 1. 建库 —— 解压 + 合并 + 派生字段，约 3 分钟
#    产出 data/clean/loans.parquet（分析主表）
#         data/clean/loans_features.parquet（物理隔离的防泄漏特征表）
python code/01_build_loans.py

# 2. 自检 —— 15 项，应该全绿
python code/00_selfcheck.py

# 3. 各节 SQL —— 结果落到 output/tables/
python code/run_sql.py sql/sql_01_overview.sql
python code/run_sql.py sql/sql_02_vintage.sql
python code/run_sql.py sql/sql_02b_vintage_mix.sql
python code/run_sql.py sql/sql_03_pricing.sql
python code/run_sql.py sql/sql_04_segments.sql
python code/run_sql.py sql/sql_05_actions.sql

# 4. 统计检验 —— 依赖第 3 步的 sql_04 结果
python code/04_segment_stats.py         # IV / 卡方 / Cramér's V / Wilson 区间 / 时间分半

# 5. 画图 —— 依赖第 3、4 步（c1 ~ c13 依次对应 13 张结论图）
python code/c1_status_by_year.py
python code/c2_vintage_curve.py
# ... 以此类推

# 6. 看板数据源（9 张 csv）+ 五屏成品
python code/06_build_tableau_tables.py
python code/07_build_dashboard.py
```

**依赖关系是干净的**：SQL 只依赖 parquet，统计脚本只依赖 SQL 结果，画图只依赖前两者。
没有任何一步会回头改上一步的东西，所以可以单独重跑任何一节。

> 不想跑数据也完全可以：`output/` 里的 13 张结论图、9 组取数结果、
> 9 张看板数据源，以及 `output/dashboard/五屏看板.html` 都已经随仓库提交了。
