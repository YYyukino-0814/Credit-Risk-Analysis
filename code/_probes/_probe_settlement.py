# -*- coding: utf-8 -*-
"""临时排查：已结清但本金没收全的 1663 笔，是不是债务和解。查清后删。"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

con = db.connect()

# 1. 主表里有哪些 settlement / hardship 相关列
cols = [c[0] for c in con.execute('DESCRIBE SELECT * FROM loans').fetchall()]
print('主表里与和解/困难相关的列：')
print(' ', [c for c in cols if 'settle' in c.lower() or 'hardship' in c.lower()])


def show(title, sql):
    print(f'\n=== {title} ===')
    try:
        print(con.execute(sql).fetchdf().to_string())
    except Exception as e:
        print(f'  查询失败：{e}')


# 2. 直接回原始表看这几列（主表可能没选进来）
print('\n=== 原始宽表里的 settlement / hardship 列 ===')
raw_cols = [c[0] for c in con.execute(
    f"DESCRIBE SELECT * FROM '{db.path('data','clean','loans_raw.parquet')}'").fetchall()]
rel = [c for c in raw_cols if 'settle' in c.lower() or 'hardship' in c.lower()
       or 'debt' in c.lower()]
print(' ', rel)

# 原始表全是 VARCHAR，要显式转。raw 与主表行序一致（主表就是 SELECT 出来的），
# 所以用行号 JOIN 回原始宽表拿和解字段。
RAW = db.path('data', 'clean', 'loans_raw.parquet')
show('这 1663 笔的和解/困难标记（按行号回接原始宽表）', f"""
    WITH r AS (
        SELECT row_number() OVER () AS rn,
               debt_settlement_flag, settlement_status,
               TRY_CAST(total_rec_prncp AS DOUBLE) AS rec_prncp,
               TRY_CAST(loan_amnt AS DOUBLE) AS amt,
               loan_status
        FROM '{RAW}'
    ), m AS (
        SELECT row_number() OVER () AS rn, status_group, loan_status AS st
        FROM loans
    )
    SELECT r.debt_settlement_flag, r.settlement_status, COUNT(*) AS n
    FROM m JOIN r USING (rn)
    WHERE m.status_group = '已结清' AND r.rec_prncp < r.amt * 0.99
    GROUP BY 1, 2 ORDER BY n DESC
""")

show('对照：全部已结清贷款的和解标记分布', f"""
    SELECT debt_settlement_flag, COUNT(*) AS n
    FROM '{RAW}' WHERE loan_status LIKE 'Fully Paid%'
    GROUP BY 1 ORDER BY n DESC
""")

show('这 1663 笔的 hardship_flag', f"""
    WITH r AS (
        SELECT row_number() OVER () AS rn, hardship_flag,
               TRY_CAST(total_rec_prncp AS DOUBLE) AS rec_prncp,
               TRY_CAST(loan_amnt AS DOUBLE) AS amt
        FROM '{RAW}'
    ), m AS (
        SELECT row_number() OVER () AS rn, status_group FROM loans
    )
    SELECT r.hardship_flag, COUNT(*) AS n
    FROM m JOIN r USING (rn)
    WHERE m.status_group = '已结清' AND r.rec_prncp < r.amt * 0.99
    GROUP BY 1 ORDER BY n DESC
""")
