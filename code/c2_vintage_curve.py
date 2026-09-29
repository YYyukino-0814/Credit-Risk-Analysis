# -*- coding: utf-8 -*-
"""c2_vintage_curve.py —— 全项目的核心图：固定账龄下的队列违约率。

这张图要回答的就一句话：把账龄控制住之后，晚放的款是不是更安全？

画法上的两个决定：
  1. 用【季度】而不是年度。年度粒度会把"某一年之内质量转向"这件事抹平——
     实测谷底在 2010Q1、峰值在 2016Q3，按年看只能看到 2010 和 2016，
     中间的拐点全丢了。
  2. 横轴用【等距的队列序号】而不是日期。因为 2007–2013 的季度样本极小
     （2007Q2 只有 24 笔），按日期排会把左边挤成一团。
     等距排布让每一格都有同样的宽度，配上下面的样本量注释，
     读者能自己判断哪一段可信。
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib.pyplot as plt
import numpy as np
import viz

df = viz.load('sql_02_vintage', 2)
df = df[df['可观察笔数'] >= 500].reset_index(drop=True)   # 样本太小的季度不画
x = np.arange(len(df))
lab = df['队列'].values
cov = df['二十四期官方违约率'].values
los = df['二十四期损失口径率'].values
cnt = df['可观察笔数'].values

fig, ax = plt.subplots(figsize=(13.2, 6.0))

# 两个系列 → 必须有图例（dataviz 硬规则），身份不能只靠颜色。
# 2px 线，点用 8px 以上的标记。
ax.plot(x, cov, color=viz.S1, linewidth=2.0, marker='o', markersize=4.2,
        markeredgecolor=viz.SURFACE, markeredgewidth=1.0, label='官方状态口径', zorder=4)
ax.plot(x, los, color=viz.S2, linewidth=2.0, marker='o', markersize=4.2,
        markeredgecolor=viz.SURFACE, markeredgewidth=1.0, label='损失口径', zorder=3)

# 每 4 个季度（=每年）标一个横轴刻度，全标会糊成一片
step = 4
ticks = list(range(0, len(df), step))
ax.set_xticks(ticks)
ax.set_xticklabels([lab[i] for i in ticks], rotation=45, ha='right')

ax.set_ylabel('24 期累计违约率（%）')
ax.set_ylim(0, max(cov.max(), los.max()) * 1.28)
viz.dress(ax)
viz.title(ax, '把账龄控制住之后：2010–2013 最好，2015–2016 最差，之后回落',
          '各季度队列在【第 24 个月】的累计违约率 · 只看可观察到 24 期的贷款')

# 关键拐点直接标注——这几个数就是结论本身，不该让读者去轴上估。
# ⚠️ 偏移量必须用 textcoords='offset points'（点坐标），
#    不能直接写进 xytext（那是【数据坐标】）。写成数据坐标的话
#    "18.66 + 34 = 52" 会跑到纵轴外面去，bbox_inches='tight' 为了把它装进来
#    会把整张图拉成一条竖长条——踩过一次，图变成了 1732×2424 的怪东西。
imin = int(np.argmin(cov))                       # 谷底 2010Q1
# ⚠️ 不能直接用 argmax 找峰值：全序列的最大值在 2008Q1（金融危机），
#    那是【谷底之前】的事。要找的是"谷底之后的最差点"，所以要限制在 imin 之后。
imax = imin + int(np.argmax(cov[imin:]))         # 谷底之后的峰值 2016Q3

for i, txt, dy, va in ((imin, '谷底', -40, 'top'),
                       (imax, '谷底之后的最差', 34, 'bottom'),
                       (len(df) - 1, '最新', 34, 'bottom')):
    ax.annotate(f'{txt} {lab[i]}\n{cov[i]:.1f}%',
                xy=(x[i], cov[i]), xytext=(0, dy), textcoords='offset points',
                ha='center', va=va, fontsize=9, color=viz.INK, fontweight='bold',
                arrowprops=dict(arrowstyle='-', color=viz.MUTED, linewidth=0.9))

# 单独标出谷底之前的那一段（金融危机），说明它不在主叙事里
ax.annotate(f'金融危机队列 {lab[0]} {cov[0]:.1f}%',
            xy=(x[0], cov[0]), xytext=(6, -6), textcoords='offset points',
            ha='left', va='top', fontsize=8.5, color=viz.MUTED)

# 阴影只盖【谷底 → 谷底之后的最差】这一段，也就是真正的恶化区间。
# （第一版写成 argmax 到 argmin，结果阴影盖在了改善段上，标签和图形自相矛盾。）
ax.axvspan(x[imin], x[imax], color=viz.S2, alpha=0.055, zorder=1)

ax.legend(loc='upper right', frameon=False, fontsize=10)
fig.text(0.5, -0.02,
         '读法：横轴每个季度只取一个点，所有队列都看它们第 24 个月时的表现——'
         '大家站在同一账龄上比，才不会被"近年的还没到期"骗到。',
         ha='center', fontsize=9, color=viz.MUTED)

viz.save(fig, 'c2_vintage_curve.png')

# 顺带把样本量打出来，方便判断哪一段可信
print('\n各队列可观察笔数（判断可信度用）：')
for i in (0, 4, 12, 24, 36, len(df) - 1):
    print(f'  {lab[i]}  {cnt[i]:>8,} 笔   官方 {cov[i]:.2f}%')
