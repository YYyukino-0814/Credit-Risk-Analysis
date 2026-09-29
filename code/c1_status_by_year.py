# -*- coding: utf-8 -*-
"""c1_status_by_year.py —— 认识数据的第一张图：放款规模与状态构成。

画两个面板，而不是一张图叠两个纵轴，原因很实在：
    "放款笔数"从 2007 年的 603 笔涨到 2018 年的 495,242 笔，差 800 倍；
    "各状态占比"永远在 0~100% 之间。把这两个量塞进一张双轴图，
    读者会被两条毫无关系的曲线误导——这是图表里最常见也最严重的错误。
    两个量纲不同，就画两张图（small multiples），共享横轴。

面板A 回答"这个盘子有多大、长得有多快"；
面板B 回答"每一年的贷款现在走到哪一步了"——后者才是删失的证据。
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib.pyplot as plt
import numpy as np
import viz

df = viz.load('sql_01_overview', 2)
years = df['放款年'].astype(int).values
n = df['放款笔数'].values
paid, chg, cur = df['已结清'].values, df['已核销'].values, df['未决'].values
tot = paid + chg + cur

fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.6, 5.4))

# ── 面板A：放款笔数 ──
# 单系列，标题已经说明了它是什么，所以不需要图例。
axL.bar(years, n, color=viz.ORD[1], width=0.68, zorder=3)
axL.set_xticks(years)
axL.set_xticklabels([str(y) for y in years], rotation=45, ha='right')
axL.set_ylabel('放款笔数')
axL.set_ylim(0, n.max() * 1.12)      # 顶部留白给标注，否则首尾数字会贴到图边
viz.dress(axL)
viz.title(axL, '放款规模：12 年涨了 800 倍',
          'Lending Club 公开账本，2007–2018 共 226.1 万笔')

# 只给首尾两年直接标数值——每个柱子都标数字是噪音，但两端要让人一眼看到量级差
for i in (0, len(years) - 1):
    axL.text(years[i], n[i] + n.max() * 0.02, f'{n[i]:,}',
             ha='center', va='bottom', fontsize=9, color=viz.INK2, zorder=4)
# 线性纵轴下 2007–2013 的柱子几乎看不见，这是"差 800 倍"的必然结果，
# 与其偷偷换成会误导人的对数轴，不如直接说明。
axL.annotate('2013 年以前的柱子\n在线性轴下几乎不可见\n（本身也是结论）',
             xy=(years[5], n[5]), xytext=(years[1], n.max() * 0.42),
             fontsize=8.5, color=viz.MUTED, ha='left',
             arrowprops=dict(arrowstyle='-', color=viz.AXIS, linewidth=0.9))

# ── 面板B：状态构成（百分比堆叠）──
# 三个系列 → 必须有图例（dataviz 硬规则：≥2 个系列必须有图例，
# 身份绝不能只靠颜色传达）。
p_paid, p_chg, p_cur = paid / tot * 100, chg / tot * 100, cur / tot * 100

# 堆叠段之间留 2px 底色缝隙：不留缝的话相邻两块颜色直接相接，
# 中间那道分界线就没了，读者要靠猜才知道每一段从哪开始。
SEP = dict(width=0.68, edgecolor=viz.SURFACE, linewidth=1.6, zorder=3)
axR.bar(years, p_paid, color=viz.S1, label='已结清', **SEP)
axR.bar(years, p_chg, bottom=p_paid, color=viz.S2, label='已核销', **SEP)
axR.bar(years, p_cur, bottom=p_paid + p_chg, color=viz.S3, label='未决', **SEP)

axR.set_xticks(years)
axR.set_xticklabels([str(y) for y in years], rotation=45, ha='right')
axR.set_ylim(0, 100)
axR.set_ylabel('占当年放款笔数（%）')
viz.dress(axR)
viz.title(axR, '近年队列的"未决"占比陡增',
          '这是右删失存在的第一证据，不是质量变差的证据')

# 青绿 S3 对浅底色只有 2.74:1，低于 3:1 —— 按 relief 规则配直接数值标签，
# 让"未决"这条信息不只靠颜色传达。
for i in range(len(years)):
    if p_cur[i] >= 1:
        axR.text(years[i], p_paid[i] + p_chg[i] + p_cur[i] / 2,
                 f'{p_cur[i]:.1f}%', ha='center', va='center',
                 fontsize=8.5, color=viz.INK, fontweight='bold', zorder=4)

axR.legend(loc='lower left', frameon=False, fontsize=9.5, ncols=3,
           bbox_to_anchor=(0, -0.32))

# 一句话读图提示，直接写在图上——图是要单独发给别人也能看懂的
fig.text(0.5, -0.06,
         '读法：2017–2018 的"未决"不是坏账，是【还没到期】。把它们当成"没违约=好客户"会凭空造出一个"质量在改善"的假象。',
         ha='center', fontsize=9, color=viz.MUTED)

viz.save(fig, 'c1_status_by_year.png')
