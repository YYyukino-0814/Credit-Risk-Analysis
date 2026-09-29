# -*- coding: utf-8 -*-
"""06_build_tableau_tables.py —— 把五节的分析结果整理成 Tableau 能直接吃的表。

【为什么要有这一步，而不是让 Tableau 直接连数据库】
  1. Tableau 连 DuckDB 在别人机器上要装驱动；连 csv 什么都不用装。
  2. 看板的每个格子只该看到【它需要的那几列】。把 100 多列的主表丢给 Tableau，
     等于让每个看图的人自己判断"这列能不能用"——总有一次会有人拿
     total_pymnt 去和放款额比，然后得出一个漂亮的、完全错的转化率。
  3. 整理的动作本身是一次检查：列名改成人话、口径写进文件名、
     不可比的格子显式标出来。做这一步的时候经常会发现前面漏掉的东西。

【输出】output/tableau/ 下 7 个 csv，对应 5 屏看板：
    屏1 放款总览        s1_overview.csv
    屏2 放款质量        s2a_vintage_curve.csv / s2b_grade_mix.csv / s2c_effect_split.csv
    屏3 定价与收益      s3a_grade_term.csv / s3b_cohort_pnl.csv / s3c_pricing_gap.csv
    屏4 风险分群        s4_segments.csv
    屏5 行动看板        s5_actions.csv

⚠️ 一律 utf-8-sig 编码。Tableau 在中文 Windows 上读不带 BOM 的 utf-8
   会把表头认成乱码，而且是静默的——图表能出，只是每列都叫"锟斤拷"。
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import pandas as pd

import db

OUT = db.path('output', 'tableau')


def read(name):
    return pd.read_csv(os.path.join(db.TABLES, name))


def save(df, fname, note=''):
    """存表并打印一行摘要。任何一张表都不许空着出去。"""
    if df.empty:
        raise SystemExit(f'❌ {fname} 是空的——上游的 SQL 或统计脚本没跑')
    path = os.path.join(OUT, fname)
    df.to_csv(path, index=False, encoding='utf-8-sig')
    n_null = int(df.isna().sum().sum())
    print(f'  {fname:28s} {df.shape[0]:5d} 行 × {df.shape[1]:2d} 列'
          + (f'   ⚠️ {n_null} 个空值' if n_null else ''))


def main():
    os.makedirs(OUT, exist_ok=True)
    print(f'输出目录：{OUT}\n')

    # ────────────────────────────────── 屏1 · 放款总览
    print('【屏1】放款总览')
    r2 = read('sql_01_overview_r2.csv')
    # 只留画图用得上的列。最低/最高利率这类极值列对看板没用，
    # 而且容易被当成"典型值"误读。
    s1 = r2[['放款年', '放款笔数', '放款本金_百万', '平均利率', '平均单笔',
             '未决占比', '六十期占比', 'AB级占比', '已结清', '已核销', '未决']].copy()
    s1 = s1.rename(columns={'放款笔数': '放款笔数', '未决占比': '未决占比_百分比'})
    # 加一行合计：看板上放一个"总量"卡片比让用户自己心算强。
    total = pd.DataFrame([{
        '放款年': '合计（2007-2018）',
        '放款笔数': int(s1['放款笔数'].sum()),
        '放款本金_百万': round(s1['放款本金_百万'].sum(), 1),
        '平均利率': round(np.average(s1['平均利率'], weights=s1['放款笔数']), 2),
        '平均单笔': round(s1['放款本金_百万'].sum() * 1e6 / s1['放款笔数'].sum(), 0),
        '未决占比_百分比': round(np.average(s1['未决占比_百分比'],
                                            weights=s1['放款笔数']), 2),
        '六十期占比': round(np.average(s1['六十期占比'], weights=s1['放款笔数']), 2),
        'AB级占比': round(np.average(s1['AB级占比'], weights=s1['放款笔数']), 2),
        '已结清': int(s1['已结清'].sum()), '已核销': int(s1['已核销'].sum()),
        '未决': int(s1['未决'].sum()),
    }])
    s1 = pd.concat([s1, total], ignore_index=True)
    save(s1, 's1_overview.csv')

    # ────────────────────────────────── 屏2 · 放款质量
    print('\n【屏2】放款质量')
    # 队列曲线：放款年 × 账龄月。横轴是账龄不是日历，这是 vintage 图的关键。
    v = read('sql_02_vintage_r1.csv')
    s2a = v.rename(columns={'官方累计违约率': '累计违约率_官方口径',
                            '损失口径累计率': '累计违约率_损失口径'})
    save(s2a, 's2a_vintage_curve.csv')

    # 等级构成：这是第二节那个辛普森悖论的证据表，必须单独一屏能调出来。
    g = read('sql_02b_vintage_mix_r1.csv')
    share = read('sql_02b_vintage_mix_r2.csv')[['放款年', '等级', '占比']]
    s2b = g.merge(share, on=['放款年', '等级'], how='left')
    s2b = s2b[['放款年', '等级', '放款笔数', '占比', '平均利率', '二十四期违约率']]
    s2b = s2b.rename(columns={'占比': '等级占比_百分比'})
    save(s2b, 's2b_grade_mix.csv')

    # 结构 / 组内效应拆解：总变化 = 结构效应 + 组内效应 + 交互项
    e = read('sql_02b_vintage_mix_r3.csv')
    # 转成长表，Tableau 画堆叠柱时要的是长表不是宽表。
    long = e.melt(id_vars=['放款年', '实际违约率', '基准期违约率', '总变化pp'],
                  value_vars=['结构效应pp', '组内效应pp', '交互项pp'],
                  var_name='效应', value_name='贡献pp')
    long['效应'] = long['效应'].str.replace('pp', '', regex=False)
    save(long, 's2c_effect_split.csv')

    # ────────────────────────────────── 屏3 · 定价与收益
    print('\n【屏3】定价与收益')
    p = read('sql_03_pricing_r1.csv')
    p = p.rename(columns={'平均净损失率': '违约损失率LGD', '毛价差pp': '毛价差'})
    save(p, 's3a_grade_term.csv')

    c = read('sql_03_pricing_r2.csv')
    # 折线图必须有这个布尔维度：没有它，2017-2018 那两个未成熟队列
    # 会和平坦的成熟队列连成一条线，看起来像"近年很赚钱"。
    c['是否可比'] = np.where(c['已走完全周期'] == '是', '可比', '不可比（未走完）')
    save(c, 's3b_cohort_pnl.csv')

    gp = read('sql_03_pricing_r4.csv')
    save(gp, 's3c_pricing_gap.csv')

    # ────────────────────────────────── 屏4 · 风险分群
    print('\n【屏4】风险分群')
    bins = pd.read_csv(os.path.join(db.TABLES, 'seg_bins.csv'))
    rank = pd.read_csv(os.path.join(db.TABLES, 'seg_iv_rank.csv'))
    s4 = bins[['特征', '分箱', '笔数', '违约率', '下界', '上界', '区间宽度']].merge(
        rank[['特征', 'IV', 'IV分级', 'CramersV', 'p值']], on='特征', how='left')
    s4 = s4.rename(columns={'下界': '违约率下界95', '上界': '违约率上界95'})
    # 排序要在表里定好：Tableau 的默认字母序会把"01 信用等级"排对、
    # 但把"10 年收入"排到"02 期限"前面时也不会报错——数字前缀已经处理了这点，
    # 这里再显式排一次，保证打开就是想要的顺序。
    s4['特征序'] = s4['特征'].str.slice(0, 2).astype(int)
    s4 = s4.sort_values(['特征序', '分箱']).drop(columns='特征序')
    save(s4, 's4_segments.csv')

    # ────────────────────────────────── 屏5 · 行动看板
    print('\n【屏5】行动看板')
    a = read('sql_05_actions_r2.csv')      # 60 期应补价差
    a = a.rename(columns={'年化少收_百万': '年化缺口_百万美元'})
    b = read('sql_05_actions_r3.csv')      # 小微经营贷超额损失
    b = b.rename(columns={'年化超额损失_百万': '年化缺口_百万美元'})
    m = read('sql_05_actions_r4.csv')      # 监控基期值
    m = m.rename(columns={'基期值': '数值'})

    # 把三块拼成一张长表：看板上三个建议排成三列，每列底下挂自己的指标。
    rows = []
    for _, r in a.iterrows():
        rows.append({'建议': '2 六十期期限价', '维度': f'{r["信用等级"]} 级',
                     '指标': '应补价差', '数值': r['应补价差pp'], '单位': 'pp',
                     '年化缺口_百万美元': r['年化缺口_百万美元'],
                     '敞口_百万美元': r['六十期本金_百万']})
    for _, r in b.iterrows():
        rows.append({'建议': '3 用途纳入规则', '维度': str(r['等级组']),
                     '指标': '超额违约', '数值': r['超额违约pp'], '单位': 'pp',
                     '年化缺口_百万美元': r['年化缺口_百万美元'],
                     '敞口_百万美元': r['本金_百万']})
    s5 = pd.DataFrame(rows)
    s5 = pd.concat([s5, m.assign(维度='全样本', 年化缺口_百万美元=np.nan,
                                敞口_百万美元=np.nan)], ignore_index=True)
    save(s5, 's5_actions.csv')

    print(f'\n全部完成。5 屏看板的数据源都在 {OUT}')


if __name__ == '__main__':
    main()
