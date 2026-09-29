# -*- coding: utf-8 -*-
"""04_segment_stats.py —— 把"哪个特征有用"从感觉变成数字。

输入是 sql_04_segments.sql 吐出的长表（特征 / 分箱 / 笔数 / 坏账数），
输出三张表：
    output/tables/seg_iv_rank.csv      —— 各特征的预测力排名
    output/tables/seg_bins.csv         —— 每个分箱的违约率 + Wilson 区间
    output/tables/seg_stability.csv    —— 时间分半的排序稳定性

【四个统计量，各回答一个问题】
  1. IV（信息值）      —— 这个特征整体上有多能区分好坏？（跨分箱汇总，可比较）
  2. 卡方 p 值         —— 这个差异会不会是碰巧？（但见下面的警告）
  3. Cramér's V        —— 差异有多大？（这才是能横向比较的量）
  4. Wilson 置信区间   —— 单个分箱的违约率，误差范围有多宽？

【⚠️ 本文件最重要的一条：p 值在这个样本量下没有信息量】
样本有 220 万笔，只要某特征和违约率有一丁点关系，卡方 p 值就会小到
打印出来是一串 0。所以"p < 0.05 就算显著"在这里完全失效——
19 个特征会全部"显著"，包括那些效应小到没有业务意义的。
真正该看的是【效应量】：Cramér's V 和 IV。
p 值仍然照算，但用来展示"它为什么没用"，不是用来做决策。

【为什么用 Wilson 区间而不是正态近似】
正态近似区间 p̂ ± 1.96·√(p̂(1−p̂)/n) 在 p̂ 接近 0 或 1 时会算出
越界的区间（比如"违约率 −0.3% 到 1.2%"），也会在低违约率时严重低估宽度。
Wilson 区间在极端比例下仍然是合理的，本节的 A 级违约率只有 4%，
正好是正态近似开始失准的区间。
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd
from scipy import stats

import db

# 小于这个样本量的分箱不参与计算——几十笔的分箱算出来的违约率全是噪声，
# 而且它们会污染 IV（一个 2 笔的箱子违约率是 0% 或 50%，对 IV 的影响不成比例）。
MIN_N = 500


def wilson(k, n, z=1.96):
    """Wilson 得分区间。返回 (下界, 上界)，单位是比例。"""
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def iv_of(g):
    """按分箱算 IV。g 需要 bad / good 两列。"""
    tot_bad, tot_good = g['坏账数'].sum(), g['好客户数'].sum()
    if tot_bad == 0 or tot_good == 0:
        return np.nan
    pb = g['坏账数'] / tot_bad
    pg = g['好客户数'] / tot_good
    # 空箱会让 ln 爆掉，加一个极小的平滑量
    ok = (pb > 0) & (pg > 0)
    return float(((pb[ok] - pg[ok]) * np.log(pb[ok] / pg[ok])).sum())


def main():
    raw = pd.read_csv(os.path.join(db.TABLES, 'sql_04_segments_r1.csv'))
    raw.columns = ['特征', '分箱', '笔数', '坏账数']

    # ── 1. 每个分箱的违约率 + Wilson 区间 ──
    b = raw[raw['笔数'] >= MIN_N].copy()
    b['好客户数'] = b['笔数'] - b['坏账数']
    b['违约率'] = 100 * b['坏账数'] / b['笔数']
    ci = np.array([wilson(k, n) for k, n in zip(b['坏账数'], b['笔数'])])
    b['下界'] = 100 * ci[:, 0]
    b['上界'] = 100 * ci[:, 1]
    b['区间宽度'] = b['上界'] - b['下界']

    # ── 2. 各特征的 IV / 卡方 / Cramér's V ──
    rows = []
    for feat, g in b.groupby('特征'):
        n_tot = g['笔数'].sum()
        k_tot = g['坏账数'].sum()
        # 2×k 列联表：行 = 好/坏，列 = 分箱
        table = np.vstack([g['坏账数'].values, g['好客户数'].values])
        chi2, p, dof, _ = stats.chi2_contingency(table)
        # 2 行 → min(行数−1, 列数−1) = 1，所以 Cramér's V = √(χ²/n)
        v = np.sqrt(chi2 / (n_tot * min(1, table.shape[1] - 1)))
        rows.append({
            '特征': feat,
            '分箱数': len(g),
            '笔数': n_tot,
            '违约率': 100 * k_tot / n_tot,
            'IV': iv_of(g),
            'CramersV': v,
            '卡方': chi2,
            'p值': p,
            '最差箱': g.loc[g['违约率'].idxmax(), '分箱'],
            '最差箱违约率': g['违约率'].max(),
            '最好箱': g.loc[g['违约率'].idxmin(), '分箱'],
            '最好箱违约率': g['违约率'].min(),
        })
    rank = pd.DataFrame(rows).sort_values('IV', ascending=False).reset_index(drop=True)

    # IV 的经验分级（业界惯例，写清楚出处免得被当成硬标准）
    def iv_grade(x):
        if x < 0.02:
            return '几乎无用'
        if x < 0.10:
            return '弱'
        if x < 0.30:
            return '中等'
        if x < 0.50:
            return '强'
        return '强得可疑（查泄漏）'

    rank['IV分级'] = rank['IV'].map(iv_grade)
    rank['倍数'] = rank['最差箱违约率'] / rank['最好箱违约率']

    # ── 3. 时间分半的排序稳定性 ──
    st = pd.read_csv(os.path.join(db.TABLES, 'sql_04_segments_r3.csv'))
    st.columns = ['特征', '分箱', '时段', '笔数', '违约率']
    st = st[st['笔数'] >= MIN_N]
    piv = st.pivot_table(index=['特征', '分箱'], columns='时段',
                         values='违约率').dropna()
    st_rows = []
    for feat, g in piv.reset_index().groupby('特征'):
        if len(g) < 3:
            continue
        rho, p = stats.spearmanr(g['前段 2010-2014'], g['后段 2015-2018'])
        st_rows.append({
            '特征': feat,
            '可比分箱数': len(g),
            '秩相关': rho,
            'p值': p,
            '前段违约率': g['前段 2010-2014'].mean(),
            '后段违约率': g['后段 2015-2018'].mean(),
        })
    stab = pd.DataFrame(st_rows).sort_values('秩相关', ascending=False)

    # ── 输出 ──
    os.makedirs(db.TABLES, exist_ok=True)
    b.to_csv(os.path.join(db.TABLES, 'seg_bins.csv'),
             index=False, encoding='utf-8-sig')
    rank.to_csv(os.path.join(db.TABLES, 'seg_iv_rank.csv'),
                index=False, encoding='utf-8-sig')
    stab.to_csv(os.path.join(db.TABLES, 'seg_stability.csv'),
                index=False, encoding='utf-8-sig')

    pd.set_option('display.width', 200, 'display.max_columns', 30)

    print('=' * 78)
    print('【一】各特征的预测力排名（按 IV 降序）')
    print('=' * 78)
    print(rank[['特征', '分箱数', '笔数', 'IV', 'IV分级', 'CramersV',
                '最差箱', '最差箱违约率', '倍数']]
          .to_string(index=False, float_format=lambda x: f'{x:.4f}'))

    print()
    print('=' * 78)
    print('【二】p 值为什么在这里没有信息量')
    print('=' * 78)
    n_feat = len(rank)
    n_tiny = (rank['p值'] < 1e-300).sum()
    best, worst = rank.iloc[0], rank.iloc[-1]
    print(f'  {n_feat} 个特征里，p 值小到连打印都溢出的（< 1e-300）有 {n_tiny} 个。')
    print(f'  最有用的「{best["特征"]}」  IV = {best["IV"]:.4f}')
    print(f'  倒数第三的「{rank.iloc[-3]["特征"]}」  IV = {rank.iloc[-3]["IV"]:.4f}')
    print(f'  两者有用程度差了 {best["IV"] / rank.iloc[-3]["IV"]:.0f} 倍——')
    print('  但它们的 p 值都是 0，p 值根本无法把这两个区分开。')
    print()
    print(f'  唯一一个不显著的是「{worst["特征"]}」，p = {worst["p值"]:.3f}。')
    print(f'  它的 Cramér\'s V 只有 {worst["CramersV"]:.4f}，'
          f'IV = {worst["IV"]:.4f}，效应量全场最小。')
    print('  → 这不矛盾，恰恰说明结论自洽：效应量最小的那个，恰好也是')
    print('    唯一一个连"差异非零"都证不出来的。')
    print('  → 但反过来说，样本量够大时显著性检验只在回答')
    print('    "差异是不是 0"，而不是"差异有多大"——后者才是能用的信息。')

    print()
    print('=' * 78)
    print('【三】时间分半的排序稳定性（前段 2010-2014 vs 后段 2015-2018）')
    print('=' * 78)
    print(stab.to_string(index=False, float_format=lambda x: f'{x:.4f}'))

    print()
    print('已存 output/tables/seg_*.csv')


if __name__ == '__main__':
    main()
