# -*- coding: utf-8 -*-
"""临时排查：已结清贷款的 lgd_net 为什么不是 0。查清后删。"""
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


show('已结清贷款 lgd_net 的分布', """
    SELECT CASE WHEN lgd_net < 0.001 THEN '0（正常）'
                WHEN lgd_net < 0.01  THEN '(0, 0.01)'
                WHEN lgd_net < 0.05  THEN '[0.01, 0.05)'
                WHEN lgd_net < 0.2   THEN '[0.05, 0.2)'
                ELSE '>= 0.2' END AS 档位,
           COUNT(*) AS 笔数
    FROM loans WHERE status_group='已结清' GROUP BY 1 ORDER BY 1
""")

show('lgd_net 最大的几笔已结清贷款', """
    SELECT ROUND(loan_amnt,0) AS 放款本金, ROUND(total_rec_prncp,2) AS 已收本金,
           ROUND(total_rec_int,2) AS 已收利息, ROUND(recoveries,2) AS 回收,
           ROUND(loss_net,2) AS 净损失, ROUND(lgd_net,4) AS 净损失率,
           ROUND(out_prncp,2) AS 剩余本金, issue_year, term_m, loan_status
    FROM loans WHERE status_group='已结清' ORDER BY lgd_net DESC LIMIT 15
""")

show('这些"已结清但本金没收全"的笔数', """
    SELECT COUNT(*) AS 已结清总数,
           SUM(CASE WHEN total_rec_prncp < loan_amnt * 0.99 THEN 1 ELSE 0 END) AS 本金收回不足99pct,
           SUM(CASE WHEN total_rec_prncp > loan_amnt * 1.01 THEN 1 ELSE 0 END) AS 本金超收
    FROM loans WHERE status_group='已结清'
""")

show('按原始状态拆分这些异常笔', """
    SELECT loan_status, issue_year, COUNT(*) AS n,
           ROUND(AVG(1 - total_rec_prncp/loan_amnt), 4) AS 平均未收比例,
           ROUND(AVG(total_rec_int/loan_amnt), 4) AS 平均利息占本金比
    FROM loans
    WHERE status_group='已结清' AND total_rec_prncp < loan_amnt * 0.99
    GROUP BY 1,2 ORDER BY n DESC LIMIT 15
""")
