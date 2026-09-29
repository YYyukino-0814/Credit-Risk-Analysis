# -*- coding: utf-8 -*-
"""SQL 执行器：跑一个 sql/*.sql 文件，把每个结果集打印出来并存成 csv。

用法：
    python code/run_sql.py sql/sql_02_vintage.sql

约定：
  - sql 文件里用分号分隔多个结果集（注释行以 -- 开头）；
  - 每个结果存到 output/tables/<文件名>_r1.csv, _r2.csv ...
  - SQL 里可直接 FROM loans —— 那是分析主表；
  - SQL 里写 {{SNAPSHOT}} 会被替换成 db.SNAPSHOT（快照日全项目只有一个来源）。

⚠️ 写 SQL 的两条硬约束（继承自淘宝项目，切分器决定的）：
  - 不能有【行内】注释，-- 必须独占一行；
  - 字符串里不能出现分号。
  违反的话语句会被切错，而且不报错，只会安静地少跑几个结果集。

相比淘宝项目的两个增强：
  1. {{SNAPSHOT}} 占位符替换 —— 快照日不再散落在各个 SQL 里；
  2. 泄漏护栏 —— 一个 SQL 只要 FROM features，又提到任何放款后字段，
     直接拒跑。把"记得别泄漏"从纪律变成机制。
"""
import os
import sys

import db


def split_statements(text):
    """去掉整行注释，再按分号切成一条条 SQL。"""
    kept = [ln for ln in text.splitlines() if not ln.strip().startswith('--')]
    return [s.strip() for s in '\n'.join(kept).split(';') if s.strip()]


def guard_leakage(text, tag):
    """防泄漏护栏：FROM features 的 SQL 里不许出现任何放款后字段。

    只在 SQL 真的用到 features 视图时才检查——在 loans 上算损失、算账龄
    本来就要用到这些列（recoveries 是损失的分子），那是合法的。
    判据见 db.py 里 LEAKY 的注释。
    """
    if 'features' not in text:
        return
    hits = sorted({t for t in db.LEAKY if t in text})
    if hits:
        raise SystemExit(
            f'\n❌ {tag} 用了 features 视图，但里面提到了放款后才知道的字段：\n'
            f'   {hits}\n\n'
            f'   这些字段在真实申请的那一刻还不存在，当特征用就是数据泄漏。\n'
            f'   完整名单见 code/db.py 的 LEAKY_OUTCOME / LEAKY_SNAPSHOT。\n'
        )


def main():
    if len(sys.argv) < 2:
        raise SystemExit('用法：python code/run_sql.py sql/sql_02_vintage.sql')

    sql_file = sys.argv[1]
    if not os.path.isabs(sql_file):
        sql_file = os.path.join(db.BASE, sql_file)
    tag = os.path.splitext(os.path.basename(sql_file))[0]

    text = open(sql_file, encoding='utf-8').read()

    # 增强1：快照日占位符替换
    n_sub = text.count('{{SNAPSHOT}}')
    text = text.replace('{{SNAPSHOT}}', db.SNAPSHOT)

    # 增强2：泄漏护栏
    guard_leakage(text, tag)

    con = db.connect()
    os.makedirs(db.TABLES, exist_ok=True)

    statements = split_statements(text)
    print(f'>>> {tag}：共 {len(statements)} 个结果集'
          + (f'（快照日占位符替换 {n_sub} 处）' if n_sub else '') + '\n')

    for i, stmt in enumerate(statements, 1):
        df = con.execute(stmt).fetchdf()
        print(f'—— 结果 {i} ——')
        print(df.to_string(index=False))
        print()
        df.to_csv(os.path.join(db.TABLES, f'{tag}_r{i}.csv'),
                  index=False, encoding='utf-8-sig')

    print(f'已存 output/tables/{tag}_r*.csv')


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
