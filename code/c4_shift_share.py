# -*- coding: utf-8 -*-
"""c4_shift_share.py —— 把"变差"拆成两块：客群下沉 vs 风控失灵。

这是全项目最有价值的一张图。同样是"违约率上升 3.5 个百分点"，
成因不同、对策完全相反：
    结构效应大 → 平台主动下沉客群。这是【业务决策】，只要定价补得回来就没问题。
    组内效应大 → 同一个信用等级内部风险也变高了。这是【风控模型失效】，
                等级失去区分度，定价的地基就塌了。

画法：分组柱（结构 / 组内）而不是堆叠柱——因为结构效应在 2018 年
【变成了负数】，堆叠柱遇到负值会画出自相矛盾的长度，读者会被彻底带偏。
总量用中性色的标记单独叠上去，不参与分组。
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib.pyplot as plt
import numpy as np
import viz

d = viz.load('sql_02b_vintage_mix', 3)
# 2007–2009 样本太小且早于基准期，画进来只会让左端噪声盖过主叙事
d = d[d['放款年'] >= 2010].reset_index(drop=True)

years = d['放款年'].astype(int).values
mix = d['结构效应pp'].values
ins = d['组内效应pp'].values
tot = d['总变化pp'].values

x = np.arange(len(years))
w = 0.36

fig, ax = plt.subplots(figsize=(12.4, 6.2))

# 两个系列 → 必须有图例
ax.bar(x - w / 2, mix, width=w, color=viz.S1, label='结构效应（客群构成变化）', zorder=3)
ax.bar(x + w / 2, ins, width=w, color=viz.S2, label='组内效应（同等级内部风险变化）', zorder=3)

# 零线画出来——有负值的图必须让人一眼看到正负分界在哪
ax.axhline(0, color=viz.AXIS, linewidth=1.0, zorder=2)

# 总量用中性色标记：它不是第三个系列，是前两者的合计，所以不给分类色
ax.plot(x, tot, linestyle='none', marker='D', markersize=7,
        markerfacecolor=viz.INK, markeredgecolor=viz.SURFACE, markeredgewidth=1.4,
        label='总变化（合计）', zorder=5)

ax.set_xticks(x)
ax.set_xticklabels([str(y) for y in years])
ax.set_ylabel('相对 2010–2011 基准的变化（百分点）')
# ⚠️ set_ylim 第一个参数是【下限】。原来写成 set_ylim(上限, None)，
#    导致 y 轴从 5.47 起步、所有柱子被挤出可视区（图是空白的）。
ax.set_ylim(None, tot.max() * 1.42 if tot.max() > 0 else 1)   # 顶部留白给注解
viz.dress(ax)
viz.title(ax, '违约率上升的成因：几乎全部来自"同等级内部变差"',
          'Shift-share 分解 · 基准期 = 2010–2011 · 24 期固定账龄 · 正值 = 比基准期差')

# 只给最后一年直接标数值——它是结论的落点
i = len(years) - 1
ax.annotate(f'2018 年结构效应已经\n转为负（客群反而更好），\n组内效应却仍有 +{ins[i]:.1f}pp',
            xy=(x[i] + w / 2, ins[i]), xytext=(-14, 26),
            textcoords='offset points', ha='right', va='bottom',
            fontsize=9, color=viz.INK,
            arrowprops=dict(arrowstyle='-', color=viz.MUTED, linewidth=0.9))

ax.legend(loc='upper left', frameon=False, fontsize=9.8)
fig.text(0.5, -0.02,
         '读法：橙色柱子（组内效应）几乎撑起了全部变化，'
         '而蓝色（结构效应）在 2018 年已经是负的——客群在往优质走，违约率却还在升。',
         ha='center', fontsize=9, color=viz.MUTED)

viz.save(fig, 'c4_shift_share.png')
