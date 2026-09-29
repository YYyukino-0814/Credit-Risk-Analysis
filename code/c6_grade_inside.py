# -*- coding: utf-8 -*-
"""c6_grade_inside.py —— 打开"组内效应"这个黑箱：到底哪个等级变差了。

c4 证明了恶化主要来自等级内部，但"组内效应 +3.5pp"是个笼统的和。
这张图把它拆到每个等级上，回答三个具体问题：
    1. 是每个等级都变差了，还是只有某几个变差？
    2. 变差的幅度和等级高低有关系吗？
    3. 与此同时，客群构成到底往哪边挪了？

配色说明：A~G 是【有序】的（A 最安全 → G 最高危），不是并列的类别，
所以用单色相浅→深渐变，而不是 7 种分类色。用分类色会让人以为
A 和 G 是"两种不同的东西"，而它们其实是同一根轴的两端。
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
import numpy as np
import viz

GRADES = list('ABCDEFG')
# 7 档有序渐变：浅 = A（安全），深 = G（高危）。
# ⚠️ 色阶下限【不能取画布底色】——第一版从 SURFACE 起渐，结果 A 级那条线
#    几乎融进背景，读者根本看不见最低那条。取调色板里已验证的浅蓝 ORD[0] 起步，
#    保证最浅的一档仍是有对比度的实色。
ramp = LinearSegmentedColormap.from_list(
    'grade_blue', [viz.ORD[0], viz.ORD[1], viz.ORD[2]])
COLOR = {g: ramp(i / (len(GRADES) - 1)) for i, g in enumerate(GRADES)}

r1 = viz.load('sql_02b_vintage_mix', 1)
r1 = r1[r1['放款年'] >= 2010]
years = sorted(r1['放款年'].unique())
piv = r1.pivot(index='放款年', columns='等级', values='二十四期违约率')

r2 = viz.load('sql_02b_vintage_mix', 2)
r2 = r2[r2['放款年'] >= 2010]
mix = r2.pivot(index='放款年', columns='等级', values='占比')

fig, (axL, axR) = plt.subplots(1, 2, figsize=(14.0, 6.0),
                               gridspec_kw={'width_ratios': [1.5, 1]})

# ── 面板A：各等级的组内违约率 ──
x = np.arange(len(years))
for g in GRADES:
    y = piv[g].values
    axL.plot(x, y, color=COLOR[g], linewidth=2.0, marker='o', markersize=4.4,
             markeredgecolor=viz.SURFACE, markeredgewidth=1.0, zorder=3)
    # 直接在线尾标等级字母：7 条线用图例框会占掉一大块，而且读者还得来回对照。
    # 直接标注让"哪条是哪条"当场就知道。
    axL.text(x[-1] + 0.18, y[-1], g, color=COLOR[g], fontsize=10.5,
             fontweight='bold', va='center', ha='left')

axL.set_xticks(x)
axL.set_xticklabels([str(y) for y in years])
axL.set_xlim(-0.4, len(years) - 1 + 0.7)
axL.set_ylabel('24 期累计违约率（%）')
viz.dress(axL)
viz.title(axL, '每一个等级都变差了——A 到 G 无一例外',
          '组内违约率 · 固定 24 期账龄 · 深色 = 高风险等级')

# ── 面板B：客群构成怎么挪的 ──
# 对比基准期（2010–2011）和最后一年（2018），比画完整时间序列更直观：
# 我们要回答的是"净挪动方向"，不是"每年挪多少"。
base = mix.loc[[2010, 2011]].mean()
last = mix.loc[2018]
xs = np.arange(len(GRADES))
w = 0.38
axR.bar(xs - w / 2, base[GRADES].values, width=w, color=viz.MUTED,
        label='2010–2011 基准', zorder=3)
axR.bar(xs + w / 2, last[GRADES].values, width=w, color=viz.S1,
        label='2018', zorder=3)

axR.set_xticks(xs)
axR.set_xticklabels(GRADES)
axR.set_xlabel('信用等级')
axR.set_ylabel('占当年放款笔数（%）')
viz.dress(axR)
viz.title(axR, '客群反而在往优质走', '2018 对比基准期')

axR.annotate('A/B 合计 54% → 56%\nF/G 合计 3.9% → 0.8%',
             xy=(5.6, 20), fontsize=9, color=viz.INK, ha='center',
             bbox=dict(boxstyle='round,pad=0.5', facecolor=viz.SURFACE,
                       edgecolor=viz.AXIS, linewidth=0.8))
axR.legend(loc='upper right', frameon=False, fontsize=9.5)

fig.text(0.5, -0.03,
         '读法：左图每条线都在往上走 = 组内风险全面上升；右图高档位占比在下降 = 客群结构在改善。\n'
         '两张图放在一起就是结论：违约率上升不是因为多放了高风险的人，而是因为同一个等级已经不能代表同样的风险了。',
         ha='center', fontsize=9, color=viz.MUTED)

viz.save(fig, 'c6_grade_inside.png')

print('\n各等级 2010–2011 平均 vs 2018 的组内违约率：')
for g in GRADES:
    b = piv.loc[[2010, 2011], g].mean()
    print(f'  {g}: {b:6.2f}% → {piv.loc[2018, g]:6.2f}%   '
          f'（{piv.loc[2018, g] - b:+.2f}pp）')
