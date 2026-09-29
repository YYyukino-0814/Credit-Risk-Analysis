# -*- coding: utf-8 -*-
"""临时排查：这 1663 笔标签噪声对早期队列违约率的影响有多大。查清后删。"""
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


show('按年：官方核销率 vs 把"结清但损失本金"也算上后的核销率', """
    SELECT issue_year,
           COUNT(*) AS 放款笔数,
           SUM(CASE WHEN outcome = 1 THEN 1 ELSE 0 END) AS 官方核销,
           SUM(CASE WHEN outcome = 1 OR (outcome = 0 AND loss_net > 0.01)
                    THEN 1 ELSE 0 END) AS 含标签噪声,
           ROUND(100.0 * SUM(CASE WHEN outcome = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS 官方核销率,
           ROUND(100.0 * SUM(CASE WHEN outcome = 1 OR (outcome = 0 AND loss_net > 0.01)
                                  THEN 1 ELSE 0 END) / COUNT(*), 2) AS 含噪声核销率
    FROM loans WHERE outcome IS NOT NULL GROUP BY 1 ORDER BY 1
""")

show('早期队列的绝对影响', """
    SELECT SUM(CASE WHEN outcome = 0 AND loss_net > 0.01 THEN 1 ELSE 0 END) AS 结清却损失本金,
           ROUND(SUM(CASE WHEN outcome = 0 AND loss_net > 0.01 THEN loss_net ELSE 0 END)/1e6, 2) AS 未计入的本金损失_百万,
           COUNT(*) AS 已定标签总数,
           ROUND(100.0*SUM(CASE WHEN outcome = 0 AND loss_net > 0.01 THEN 1 ELSE 0 END)/COUNT(*), 4) AS 占比
    FROM loans WHERE outcome IS NOT NULL
""")

show('这批噪声按年占当年放款的比例', """
    SELECT issue_year, COUNT(*) AS 噪声笔数,
           ROUND(100.0*COUNT(*)/MAX(年放款), 2) AS 占当年放款比
    FROM loans l
    JOIN (SELECT issue_year AS y, COUNT(*) AS 年放款 FROM loans GROUP BY 1) t
      ON l.issue_year = t.y
    WHERE outcome = 0 AND loss_net > 0.01
    GROUP BY 1 ORDER BY 1
""")
