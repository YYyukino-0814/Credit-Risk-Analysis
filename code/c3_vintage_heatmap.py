# -*- coding: utf-8 -*-
"""c3_vintage_heatmap.py —— vintage 网格：队列 × 账龄，一眼看两个方向。

这是风控行业最标准的一张图，因为它把两个维度放在同一个画面里：
    横着读一行  = 这个队列随着时间推移，坏账怎么累积（成熟速度）
    竖着读一列  = 在同一个账龄上，不同队列谁好谁坏（质量趋势）
读 vintage 图只看一个方向是不够的，两个方向合起来才是完整的判断。

配色用【单色相浅到深】（sequential），因为这里表达的是"量的大小"，
不是"身份"。用彩虹色或分类色会让读者以为不同格子是不同类别。
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
import viz

df = viz.load('sql_02_vintage', 1)
piv = df.pivot(index='放款年', columns='账龄月', values='官方累计违约率')
mobs = list(piv.columns)
years = list(piv.index)
M = piv.values

# 单色相序数色阶：从画布底色渐变到深蓝。不用彩虹——那是分类色的用法。
cmap = LinearSegmentedColormap.from_list(
    'ord_blue', [viz.SURFACE, viz.ORD[0], viz.ORD[1], viz.ORD[2]])

fig, ax = plt.subplots(figsize=(8.4, 7.0))
im = ax.imshow(M, cmap=cmap, aspect='auto', vmin=0, vmax=np.nanmax(M))

ax.set_xticks(range(len(mobs)))
ax.set_xticklabels([f'{m}期' for m in mobs])
ax.set_yticks(range(len(years)))
ax.set_yticklabels([str(y) for y in years])
ax.set_xlabel('账龄（放款后第几个月）')
ax.set_ylabel('放款队列（年）')

# 每格直接标数值。热力图的颜色只能给个大概，要引用具体数字还得靠标签；
# 而且色盲读者、黑白打印时，标签是唯一的兜底。
for i in range(len(years)):
    for j in range(len(mobs)):
        v = M[i, j]
        if np.isnan(v):
            # 空白格必须【显式】说明为什么没有值，不能让读者以为数据丢了。
            # 这里不会出现 NaN（SQL 里 WHERE mob_obs >= k 已经保证了可观察性），
            # 但保留这个分支以防以后改窗口。
            ax.text(j, i, '—', ha='center', va='center', fontsize=9, color=viz.MUTED)
            continue
        # 深底用白字、浅底用黑字，否则数字会糊在背景里
        dark = v > np.nanmax(M) * 0.58
        ax.text(j, i, f'{v:.1f}', ha='center', va='center', fontsize=9.5,
                color='#ffffff' if dark else viz.INK,
                fontweight='bold' if dark else 'normal')

for s in ax.spines.values():
    s.set_visible(False)
ax.tick_params(length=0)

# 色条单独放，标注单位
cb = fig.colorbar(im, ax=ax, fraction=0.036, pad=0.03)
cb.set_label('累计违约率（%）', fontsize=9.5, color=viz.INK2)
cb.outline.set_visible(False)
cb.ax.tick_params(length=0, labelsize=9)

viz.title(ax, 'Vintage 网格：横着看成熟速度，竖着看质量趋势',
          '每一格 = 该队列到该账龄时的累计违约率 · 只看得到的那一刻（可观察性已保证）')

fig.text(0.5, -0.03,
         '读法：最右一列（36期）从上往下 = 站在同一账龄上比质量。'
         '最低的是 2010–2013，最高的是 2015–2016。\n'
         '这一版网格没有空格子，是因为最年轻的 2018 队列也有 44 个月历史，36 期对全部队列都可观察——'
         '这是先确认过可观察性才画的。60 期就做不到了，见口径文档第四节。',
         ha='center', fontsize=8.8, color=viz.MUTED)

viz.save(fig, 'c3_vintage_heatmap.png')
