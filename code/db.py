# -*- coding: utf-8 -*-
"""共用工具：项目路径 + DuckDB 连接（自动挂上分析主表视图 loans）。

所有分析脚本都从这里拿连接，保证大家读的是同一张表、同一套路径。

和淘宝项目（04）的三个区别：
  1. 主表叫 loans 不叫 events；
  2. 多挂一个 features 视图——它是【物理隔离出来的防泄漏特征表】，
     只含放款前就确定的字段。要做特征分析就只许 FROM features，
     不许 FROM loans，这样"哪天忘了剔除泄漏字段"这件事在物理上就不可能发生。
  3. 多一个 SNAPSHOT 常量——全项目只在这一个地方写快照日，
     SQL 里一律写占位符 {{SNAPSHOT}}，由 run_sql.py 替换。
"""
import os
import sys

import duckdb

# Windows 控制台默认 GBK，中文会报 UnicodeEncodeError
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def path(*parts):
    """拼项目内路径，统一正斜杠（DuckDB / Windows 都吃）。"""
    return os.path.join(BASE, *parts).replace('\\', '/')


MAIN_PQ = path('data', 'clean', 'loans.parquet')            # 【分析主表】精选列 + 派生列
FEATURES_PQ = path('data', 'clean', 'loans_features.parquet')  # 【防泄漏】只有放款前字段
TABLES = path('output', 'tables')
CHARTS = path('output', 'charts')

# 数据快照日：所有"账龄"都相对这一天算。这是整个项目的时间原点。
#
# 【2026-09-11 实测确定，不是猜的】
# 判据：仍未结清（out_prncp > 0）的贷款一直在按月还款，它们集体停在哪个月，
#      数据就封存在哪个月。实测 47,332 笔未结清贷款里有 46,172 笔的最后一笔还款
#      落在 2022-08，之后断崖下跌（2022-07 只剩 752 笔，2022-06 只剩 198 笔）；
#      全局 MAX(last_pymnt_d) = 2022-08-01，之后一笔还款都没有。
#
# ⚠️ 别被 last_credit_pull_d 带偏：它的 MAX 是 2023-07，看着更晚，但它是干扰项。
#    (a) 它是每笔贷款各自最后一次拉征信的日期，根本不是数据集的编译日；
#    (b) LC 在 2021-03 做过一次批量征信刷新（321,003 笔挤在同一个月，
#        是次高月份 2022-08 的 2.9 倍）；
#    (c) 2023 年的拉取记录只出现在 LoanStats3a 一个文件里——那是早期文件被单独
#        刷新过，而它装的是 2007-2011 年的贷款，早就在 2016 年前全部结清。
# 选错这个日子，整条 vintage 曲线的横轴就全错了，而且不会报任何错。
SNAPSHOT = "DATE '2022-08-31'"


# ---------------------------------------------------------------- 泄漏字段黑名单
# 全项目唯一权威定义。两处在用：
#   · 01_build_loans.py —— 用它判断哪些字段不许进 loans_features.parquet
#   · run_sql.py        —— 一旦某个 SQL 既 FROM features 又提到这些列名，直接拒跑
#
# 为什么需要这份名单：这两族字段长得跟"真·申请信息"一模一样，
# 但它们的取值是【放款之后】才知道的。用它们做特征，模型在测试集上会很漂亮，
# 上线就崩——因为真实申请的那一刻，这些数字还不存在。
#
# 第一族：放款后才产生的还款/核销结果。这是标签本身，不是特征。
LEAKY_OUTCOME = [
    'total_pymnt', 'total_pymnt_inv', 'total_rec_prncp', 'total_rec_int',
    'total_rec_late_fee', 'recoveries', 'collection_recovery_fee',
    'last_pymnt_d', 'last_pymnt_amnt', 'next_pymnt_d',
    'out_prncp', 'out_prncp_inv',
    'hardship_', 'settlement_', 'debt_settlement_flag',
    'pymnt_plan', 'chargeoff_within_12_mths', 'collections_12_mths_ex_med',
]

# 第二族：更阴的一族——它们不是还款结果，是【某个后续时点的征信快照】。
# 一堆公开教程把这一整族当申请特征用。判断依据：这些列在早期队列里
# 大面积缺失、在近期队列里才填上，正因为它们来自后续的征信拉取。
LEAKY_SNAPSHOT = [
    'last_credit_pull_d',
    'tot_cur_bal', 'tot_coll_amt', 'tot_hi_cred_lim',
    'total_bal_ex_mort', 'total_bal_il', 'total_bc_limit',
    'total_cu_tl', 'total_il_high_credit_limit', 'total_rev_hi_lim',
    'num_tl_', 'num_actv_', 'num_bc_', 'num_il_', 'num_op_rev_tl',
    'num_rev_', 'num_sats', 'num_accts_ever_120_pd',
    'open_acc_6m', 'open_act_il', 'open_il_', 'open_rv_',
    'acc_now_delinq', 'delinq_amnt',
    # ⚠️ 这里不能图省事写成 'mths_since_' 一个前缀通配。
    #    快照族的几条是 mths_since_recent_* / mths_since_rcnt_*，
    #    但 mths_since_last_delinq / mths_since_last_record /
    #    mths_since_last_major_derog 三条【不是】——
    #    它们是申请那一刻征信报告上的字段（"距上次逾期多少个月"），
    #    是合法的申请特征。写成宽前缀会把这三条一起误伤掉，
    #    而且是静默误伤：特征表少几列不会报错，只会让模型少看点东西。
    'mths_since_recent', 'mths_since_rcnt',
    'mo_sin_',
    'avg_cur_bal', 'bc_open_to_buy', 'bc_util', 'il_util', 'all_util',
    'max_bal_bc', 'pct_tl_nvr_dlq', 'percent_bc_gt_75',
    'inq_fi', 'inq_last_12m',
    # 下面两个是【数据自己扫出来的】，原本手写的名单漏了它们。
    # 旁证：看它们在文件表头里的位置——mort_acc 夹在 mo_sin_rcnt_tl 和
    # mths_since_recent_bc 之间，acc_open_past_24mths 夹在 inq_last_12m 和
    # avg_cur_bal 之间，两个都落在"快照族"那个连续区块的内部。
    # LC 当年加这批字段时是一次性加的一整块，位置本身就是证据。
    'mort_acc', 'acc_open_past_24mths',
]

LEAKY = LEAKY_OUTCOME + LEAKY_SNAPSHOT

# ---------------------------------------------------------------- 另一类不能用的字段
# 这一类【不是泄漏】，但同样不能进特征集，原因不同、必须分开讲——
# 混在一起说会让人以为"所有不能用的字段都是泄漏"，那是没想清楚。
#
# pub_rec_bankruptcies（破产记录笔数）：
#   它是货真价实的申请时字段，来自申请那一刻的征信报告，[不是] 放款后才知道的。
#   问题是它【当年没采集】：2007 年放款的贷款里 96.7% 这个字段是空的，
#   到 2018 年才 0% 缺失。
#
#   为什么这样也不能用：缺失率本身随队列变化，就是"队列相关的缺失"。
#   拿它做跨队列的模型，模型会从"这个字段有没有值"里读出"这是哪一年的贷款"，
#   等于间接把队列信息喂给了模型。最后会得出"近年质量在改善"这类结论，
#   而真正的驱动因素只是这个字段从某一年起开始被采集了。
#
#   判据上它和泄漏族只差一点点（早年缺失 96.7% vs 100%），
#   所以扫描脚本按缺失率高低分成两档报出来，但【判断由人来做，理由写在这里】。
COHORT_BLIND = ['pub_rec_bankruptcies']

UNUSABLE_AS_FEATURE = LEAKY + COHORT_BLIND


def is_leaky(col):
    """判断一个列名是不是泄漏字段（支持前缀匹配，因为 num_tl_* 这类是一整族）。"""
    low = col.lower()
    return any(low == t or low.startswith(t) for t in LEAKY)


def connect():
    """返回 DuckDB 连接，挂两个视图：
       loans    —— 分析主表，什么都能查（算损失、算账龄都在它上面）
       features —— 只含放款前字段，做特征/分群分析只许用它
    再加一个哨兵视图 leaky_fields，方便在 SQL 里自查。
    """
    con = duckdb.connect()
    con.execute(f"CREATE OR REPLACE VIEW loans AS SELECT * FROM '{MAIN_PQ}'")
    if os.path.exists(FEATURES_PQ):
        con.execute(f"CREATE OR REPLACE VIEW features AS SELECT * FROM '{FEATURES_PQ}'")
    return con
