# -*- coding: utf-8 -*-
"""c9_margin_trend.py —— 放款价差这几年被挤扁了多少。

左图把【平均利率】和【期望损失率】画在同一根轴上，两条线之间的垂直距离
就是毛价差。这样画比直接画一个"价差"数字更有说服力——读者能亲眼看到
距离是怎么一点点合上的。

⚠️ 这里【不能】用双轴。利率和损失率都是百分点，本来就在同一个量纲上，
   双轴只会制造一个"看起来两条线交叉了"的假象，而那个交叉点毫无意义。

右图单看价差本身的绝对水平。它是本节的核心结论：2013 年还有 8.79 个点的
毛价差，2015 年只剩 5.32——两年时间被挤掉三分之一，之后再没回来。
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib.pyplot as plt
import numpy as np
import viz

d = viz.load('sql_03_pricing', 5)
# 2007–2009 每年只有几百笔甚至几十笔，线画出来是噪声，不参与任何结论
d = d[d['放款年'] >= 2010].reset_index(drop=True)

years = d['放款年'].astype(int).values
rate = d['平均利率'].values
spread = d['毛价差pp'].values
exp_loss = rate - spread          # 期望损失率 = 利率 − 毛价差，不另外算一遍

fig, (axL, axR) = plt.subplots(1, 2, figsize=(14.0, 6.0),
                               gridspec_kw={'width_ratios': [1.3, 1]})

# ── 面板A：利率与期望损失率，距离 = 价差 ──
axL.plot(years, rate, color=viz.S1, linewidth=2.2, marker='o', markersize=5,
         markeredgecolor=viz.SURFACE, markeredgewidth=1.2,
         label='平均放款利率', zorder=4)
axL.plot(years, exp_loss, color=viz.S2, linewidth=2.2, marker='o', markersize=5,
         markeredgecolor=viz.SURFACE, markeredgewidth=1.2,
         label='期望损失率（24 期违约率 × LGD）', zorder=4)

# ⚠️ 标【峰值年】和【谷底年】，不能图省事标首尾。
#    首尾两年（2010 的 6.55 和 2018 的 6.17）价差几乎一样，
#    标这两根会画出两条几乎等长的箭头，读者得出的结论会是"没变化"——
#    而真实的收缩全发生在中间：2013 的 8.79 塌到 2015 的 5.32。
i_hi = int(np.argmax(spread))
i_lo = i_hi + int(np.argmin(spread[i_hi:]))
for i in (i_hi, i_lo):
    axL.annotate('', xy=(years[i], rate[i]), xytext=(years[i], exp_loss[i]),
                 arrowprops=dict(arrowstyle='<->', color=viz.INK, linewidth=1.1))
    axL.text(years[i] + 0.14, (rate[i] + exp_loss[i]) / 2, f'{spread[i]:.1f}pp',
             fontsize=9.4, color=viz.INK, fontweight='bold', va='center',
             zorder=6)

axL.set_xticks(years)
axL.set_xticklabels([str(y) for y in years])
axL.set_xlim(years.min() - 0.5, years.max() + 0.7)
# 纵轴下限往下放一截：蓝线从左下角一路窜到右上角，
# 图例放哪儿都会压线，只有把底部腾空才有一块真正干净的地方。
axL.set_ylim(exp_loss.min() - 2.6, rate.max() + 0.9)
axL.set_ylabel('年化（%）')
viz.dress(axL)
viz.title(axL, '利率和期望损失率一起涨，但速度不一样',
          '两条线之间的距离 = 毛价差 · 24 期口径 · 对全部队列可用')
axL.legend(loc='lower right', frameon=False, fontsize=9.5)

# ── 面板B：价差本身 ──
# 峰谷两根上色、其余走中性灰：这不是三个"系列"，而是同一条序列里
# 被单独点名的两个时点，所以不给它们分类色。
colors = [viz.RESID] * len(years)
colors[i_hi] = viz.S1
colors[i_lo] = viz.S2
axR.bar(years, spread, width=0.62, color=colors, zorder=3)

axR.set_xticks(years)
axR.set_xticklabels([str(y) for y in years])
axR.set_xlim(years.min() - 0.6, years.max() + 0.6)
axR.set_xlabel('放款年')
axR.set_ylabel('毛价差（百分点）')
axR.set_ylim(0, spread.max() * 1.26)
viz.dress(axR)
viz.title(axR, f'价差在 {years[i_lo] - years[i_hi]} 年内被挤掉 '
               f'{100 * (1 - spread[i_lo] / spread[i_hi]):.0f}%',
          f'{years[i_hi]} 年 {spread[i_hi]:.2f}pp → {years[i_lo]} 年 {spread[i_lo]:.2f}pp，'
          f'到 {years[-1]} 年也只回到 {spread[-1]:.2f}pp')

for yy, v in zip(years, spread):
    axR.text(yy, v + spread.max() * 0.025, f'{v:.1f}', ha='center', va='bottom',
             fontsize=8.8, color=viz.MUTED)

fig.text(0.5, -0.03,
         '口径提醒：这里的"期望损失率"是 24 期违约率乘平均 LGD 的【一阶近似】，'
         '不扣资金成本与运营成本，只回答"价差够不够覆盖预期损失"。\n'
         '它的好处是对 2010–2018 全部队列都算得出来，所以这一节看的是【走势】而不是绝对水平。',
         ha='center', fontsize=9, color=viz.MUTED)

viz.save(fig, 'c9_margin_trend.png')

print('\n各年风险与定价：')
for i, y in enumerate(years):
    print(f'  {y}: 利率 {rate[i]:6.3f}%  期望损失 {exp_loss[i]:6.3f}%  '
          f'价差 {spread[i]:5.3f}pp')
