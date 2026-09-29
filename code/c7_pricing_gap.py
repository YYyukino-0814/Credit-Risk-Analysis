# -*- coding: utf-8 -*-
"""c7_pricing_gap.py —— 定价缺口：利率涨幅有没有覆盖住风险涨幅。

⚠️ 这张图的核心是【期望损失涨幅】而不是【违约率涨幅】。
   违约率涨 1pp，不代表需要涨价 1pp——违约的贷款还能收回四成多
   （实测 LGD ≈ 0.55）。经过 LGD 折算之后，需要补的价差几乎减半。
   直接把两个 pp 相减会把缺口高估近一倍，结论会从"基本跟上了"
   错判成"严重跟不上"。这是不会报错的错，只能靠想清楚口径避免。

柱子用【有正有负】的横向条形：这张图的读法是"缺口在零线的哪一侧"，
横向排列让等级从上到下依次排开，比竖向柱更容易对照。
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib.pyplot as plt
import numpy as np
import viz

d = viz.load('sql_03_pricing', 4)
grades = d['信用等级'].values
gap = d['定价缺口pp'].values
risk = d['期望损失涨幅pp'].values
price = d['利率涨幅pp'].values

fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.6, 5.8),
                               gridspec_kw={'width_ratios': [1, 1.05]})

# ── 面板A：缺口在零线哪一侧 ──
y = np.arange(len(grades))
# 正值 = 涨价超过了风险（定价充分/过度）；负值 = 没跟上（定价不足）
colors = [viz.S3 if v >= 0 else viz.S2 for v in gap]
axL.barh(y, gap, color=colors, height=0.62, zorder=3)
axL.axvline(0, color=viz.AXIS, linewidth=1.1, zorder=2)

axL.set_yticks(y)
axL.set_yticklabels(grades)
axL.invert_yaxis()          # A 在最上面，和等级表的读法一致
axL.set_xlabel('定价缺口（百分点）· 正值 = 涨价幅度超过风险涨幅')
viz.dress(axL, xgrid=True, ygrid=False)
viz.title(axL, '问题不在高风险端，在 B / C 级',
          '2018 相对 2010–2011 的变化 · 已按 LGD 折算')

# 数值标签一律用【偏移点】定位，不用数据坐标。
# 用数据坐标会在不同的 x 量程下得到不同的像素间距——短柱的标签贴住柱身，
# 长柱的标签飘出去老远。写成 offset points 就是恒定的 6 像素缝。
for i, v in enumerate(gap):
    axL.annotate(f'{v:+.2f}', xy=(v, i), xytext=(7 if v >= 0 else -7, 0),
                 textcoords='offset points',
                 va='center', ha='left' if v >= 0 else 'right',
                 fontsize=9, color=viz.INK, fontweight='bold')

axL.set_xlim(gap.min() - 0.62, gap.max() + 0.46)

# 图例两种状态直接写文字，比放两个色块省读者的对照功夫。
# 放在右上角：A~C 三行的柱子都在零线附近，右侧那一大片是空的。
axL.text(0.98, 0.97, '绿 = 涨价超过风险（定价充分）\n橙 = 涨价没跟上（定价不足）',
         transform=axL.transAxes, ha='right', va='top',
         fontsize=8.8, color=viz.MUTED, linespacing=1.6)

# ── 面板B：需要补多少 vs 实际补了多少 ──
# 分组柱，不用堆叠——两个量是"应然"和"实然"的对照关系，不是相加关系。
w = 0.37
axR.bar(y - w / 2, risk, width=w, color=viz.S2, label='风险涨幅（经 LGD 折算）', zorder=3)
axR.bar(y + w / 2, price, width=w, color=viz.S1, label='实际利率涨幅', zorder=3)
axR.axhline(0, color=viz.AXIS, linewidth=1.0, zorder=2)

# 纵轴往下留出空间：A 级的两个涨幅都是微负的（−0.00 / −0.04），
# 如果纵轴从 0 起，A 那两根会整个看不见，读者会以为"A 级没数据"。
axR.set_ylim(min(risk.min(), price.min()) - 0.45,
             max(risk.max(), price.max()) + 0.7)

axR.set_xticks(y)
axR.set_xticklabels(grades)
axR.set_xlabel('信用等级')
axR.set_ylabel('相对 2010–2011 的变化（百分点）')
viz.dress(axR)
viz.title(axR, '两个涨幅的对照', '橙柱高于蓝柱 = 涨价没跟上风险')
axR.legend(loc='upper left', frameon=False, fontsize=9.5)

fig.text(0.5, -0.03,
         '读法：先看左图缺口在零线的哪一侧。B 级最值得注意——它的风险涨了 0.70pp（已折算），'
         '利率却一分没涨（−0.04），是唯一一个明显没跟上的等级。',
         ha='center', fontsize=9, color=viz.MUTED)

viz.save(fig, 'c7_pricing_gap.png')

print('\n定价缺口明细：')
for i, g in enumerate(grades):
    print(f'  {g}: 风险涨幅 {risk[i]:+6.2f}pp  利率涨幅 {price[i]:+6.2f}pp  '
          f'缺口 {gap[i]:+6.2f}pp')
