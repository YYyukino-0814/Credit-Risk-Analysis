# -*- coding: utf-8 -*-
"""_probe_term_confound.py —— 核对"60 期风险是 36 期的 1.4~1.7 倍"这个结论。

起因：写第三节定价表时发现，sql_03 结果1 里同一等级内部
36 期和 60 期的 24 期违约率几乎一样（E 级 24.81 vs 24.93），
但 sql_02 结果5（不分等级、只看年×期限）却显示 60 期高出一大截。

这两个数不可能同时对。跑一遍直接标准化，看差异到底来自哪里。

三组数：
  (a) 合并算 —— 不分等级，直接按期限汇总。这是"天真口径"。
  (b) 标准化 —— 把两个期限的等级构成强行拉平（都用 36 期的等级权重），
                再算一遍 60 期的违约率。这一步把"等级构成"这个混淆项剔掉。
  (c) 组内加权 —— 只在同一个(年, 等级)格子内部比，再加权平均。
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import duckdb
import db

con = duckdb.connect()

BASE = """
SELECT issue_year AS y, grade AS g, term_m AS t, COUNT(*) AS n,
       SUM(CASE WHEN outcome=1 AND mob_event<=24 THEN 1 ELSE 0 END) AS bad,
       SUM(CASE WHEN outcome=1 THEN lgd_net ELSE 0 END) AS lgd_sum,
       SUM(CASE WHEN outcome=1 THEN 1 ELSE 0 END) AS def_n
FROM read_parquet(?) WHERE mob_obs >= 24 GROUP BY 1,2,3
"""
cell = con.execute(BASE, [db.MAIN_PQ]).df()

print('=' * 68)
print('【一】合并口径：不分等级，直接按期限汇总')
print('=' * 68)
tot = cell.groupby('t')[['n', 'bad']].sum()
for t, row in tot.iterrows():
    print(f'  {int(t):2d} 期: {int(row.n):>9,} 笔，24 期违约率 '
          f'{100 * row.bad / row.n:6.2f}%')
r36 = tot.loc[36, 'bad'] / tot.loc[36, 'n']
r60 = tot.loc[60, 'bad'] / tot.loc[60, 'n']
print(f'  → 倍数 {r60 / r36:.3f} 倍   （这就是 sql_02 结果5 得到的 1.4~1.7 倍）')

print()
print('=' * 68)
print('【二】两个期限的等级构成，差别有多大')
print('=' * 68)
mix = cell.pivot_table(index='g', columns='t', values='n', aggfunc='sum').fillna(0)
mix_pct = 100 * mix / mix.sum()
print(mix_pct.round(2).to_string())
print('  36 期里 A 级占 %.1f%%，60 期里只占 %.1f%%'
      % (mix_pct.loc['A', 36], mix_pct.loc['A', 60]))
print('  36 期里 E/F/G 合计 %.1f%%，60 期里高达 %.1f%%'
      % (mix_pct.loc[['E', 'F', 'G'], 36].sum(),
         mix_pct.loc[['E', 'F', 'G'], 60].sum()))

print()
print('=' * 68)
print('【三】直接标准化：把 60 期的等级构成换成 36 期的')
print('=' * 68)
g36 = cell[cell.t == 36].groupby('g')[['n', 'bad']].sum()
g60 = cell[cell.t == 60].groupby('g')[['n', 'bad']].sum()
w36 = (g36.n / g36.n.sum()).reindex(g60.index)
rate60 = g60.bad / g60.n
std60 = float((w36 * rate60).sum())
print(f'  60 期原始（按自己的等级构成）  : {100 * r60:6.2f}%')
print(f'  60 期标准化（换成 36 期的构成）: {100 * std60:6.2f}%')
print(f'  36 期实际                      : {100 * r36:6.2f}%')
print(f'  → 等级构成贡献了 {100 * (r60 - std60):.2f} 个百分点，'
      f'占总差距 {100 * (r60 - r36):.2f}pp 的 '
      f'{100 * (r60 - std60) / (r60 - r36):.0f}%')

print()
print('=' * 68)
print('【四】组内加权：(年, 等级) 格子内部比，再加权')
print('=' * 68)
p = cell.pivot_table(index=['y', 'g'], columns='t',
                     values=['n', 'bad'], aggfunc='sum').fillna(0)
p = p[(p[('n', 36)] > 0) & (p[('n', 60)] > 0)]
p['r36'] = p[('bad', 36)] / p[('n', 36)]
p['r60'] = p[('bad', 60)] / p[('n', 60)]
p['w'] = p[('n', 36)] + p[('n', 60)]
wr36 = float((p.w * p.r36).sum() / p.w.sum())
wr60 = float((p.w * p.r60).sum() / p.w.sum())
print(f'  加权组内 36 期: {100 * wr36:6.2f}%')
print(f'  加权组内 60 期: {100 * wr60:6.2f}%')
print(f'  → 组内倍数 {wr60 / wr36:.3f}')

print()
print('=' * 68)
print('【五】同样的三口径，换成看 LGD（净损失率）')
print('=' * 68)
cell['lgd'] = cell.lgd_sum / cell.def_n.replace(0, None)
L36 = float((cell[cell.t == 36].n * cell[cell.t == 36].lgd).sum()
            / cell[cell.t == 36].n.sum())
L60 = float((cell[cell.t == 60].n * cell[cell.t == 60].lgd).sum()
            / cell[cell.t == 60].n.sum())
g36l = cell[cell.t == 36].groupby('g').apply(
    lambda x: (x.n * x.lgd).sum() / x.n.sum(), include_groups=False)
g60l = cell[cell.t == 60].groupby('g').apply(
    lambda x: (x.n * x.lgd).sum() / x.n.sum(), include_groups=False)
w36l = g36.n / g36.n.sum()
std60l = float((w36l.reindex(g60l.index) * g60l).sum())
print(f'  36 期 LGD            : {L36:.4f}')
print(f'  60 期 LGD（原始）    : {L60:.4f}')
print(f'  60 期 LGD（标准化后）: {std60l:.4f}')
print(f'  → LGD 的差距【没有】被等级构成解释掉：'
      f'标准化后仍有 {std60l - L36:+.4f}')
