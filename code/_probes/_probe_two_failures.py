# -*- coding: utf-8 -*-
"""临时排查：自检第 3、5 两项为什么没过。查清后删。"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

con = db.connect()


def show(title, sql):
    print(f'\n=== {title} ===')
    print(con.execute(sql).fetchdf().to_string())


show('A1 已核销却有剩余本金的样本', """
    SELECT ROUND(out_prncp,2) AS 剩余本金, ROUND(loan_amnt,0) AS 放款本金,
           ROUND(total_rec_prncp,2) AS 已收本金, ROUND(recoveries,2) AS 回收,
           issue_year, loan_status, term_m
    FROM loans WHERE status_group = '已核销' AND out_prncp > 0
    ORDER BY out_prncp DESC LIMIT 25
""")

show('A2 按放款年分布', """
    SELECT issue_year, COUNT(*) AS 笔数, ROUND(SUM(out_prncp),2) AS 剩余本金合计,
           ROUND(AVG(out_prncp),2) AS 平均剩余
    FROM loans WHERE status_group = '已核销' AND out_prncp > 0
    GROUP BY 1 ORDER BY 1
""")

show('A3 这 22 笔的 loan_status 原始值', """
    SELECT loan_status, COUNT(*) AS n
    FROM loans WHERE status_group = '已核销' AND out_prncp > 0 GROUP BY 1
""")

show('A4 对照：已核销全体的 out_prncp 分布', """
    SELECT COUNT(*) AS 总笔数,
           SUM(CASE WHEN out_prncp = 0 THEN 1 ELSE 0 END) AS 余额为零,
           SUM(CASE WHEN out_prncp > 0 THEN 1 ELSE 0 END) AS 余额为正,
           SUM(CASE WHEN out_prncp BETWEEN -0.01 AND 0.01 THEN 1 ELSE 0 END) AS 近似零
    FROM loans WHERE status_group = '已核销'
""")

show('B1 净损失为负的程度', """
    SELECT ROUND(MIN(loss_net),2) AS 最负, ROUND(AVG(loss_net),2) AS 均值,
           COUNT(*) AS 笔数,
           SUM(CASE WHEN loss_net > -1 THEN 1 ELSE 0 END) AS 不足1元,
           SUM(CASE WHEN loss_net < -100 THEN 1 ELSE 0 END) AS 超100元,
           SUM(CASE WHEN loss_net < -1000 THEN 1 ELSE 0 END) AS 超1000元,
           ROUND(SUM(loss_net)/1e3,1) AS 合计千元
    FROM loans WHERE status_group = '已核销' AND loss_net < -0.01
""")

show('B2 负损失按原始状态', """
    SELECT loan_status, COUNT(*) AS n, ROUND(AVG(loss_net),2) AS 均值损失,
           ROUND(MIN(loss_net),2) AS 最负, ROUND(AVG(lgd_net),4) AS 平均净损失率
    FROM loans WHERE status_group = '已核销' AND loss_net < -0.01
    GROUP BY 1 ORDER BY n DESC
""")

show('B3 超收的来源：多收的本金 vs 回收款', """
    SELECT ROUND(AVG(loan_amnt),0) AS 平均本金,
           ROUND(AVG(total_rec_prncp - loan_amnt),2) AS 平均多收本金,
           ROUND(AVG(recoveries),2) AS 平均回收款,
           ROUND(AVG(total_rec_late_fee),2) AS 平均滞纳金,
           SUM(CASE WHEN total_rec_prncp > loan_amnt + 0.01 THEN 1 ELSE 0 END) AS 本金就超收的,
           SUM(CASE WHEN recoveries > 0 THEN 1 ELSE 0 END) AS 有回收款的
    FROM loans WHERE status_group = '已核销' AND loss_net < -0.01
""")

show('B4 全量：本金就超收的笔数（不分状态）', """
    SELECT status_group, COUNT(*) AS n,
           SUM(CASE WHEN total_rec_prncp > loan_amnt + 0.01 THEN 1 ELSE 0 END) AS 本金超收,
           SUM(CASE WHEN total_rec_prncp > loan_amnt * 1.05 THEN 1 ELSE 0 END) AS 超收5pct以上
    FROM loans GROUP BY 1
""")
