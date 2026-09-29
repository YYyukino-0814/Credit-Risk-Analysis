# -*- coding: utf-8 -*-
"""c10_cohort_pnl.py —— 各放款年实际赚了多少，以及为什么最后两年不能看。

这张图要防的是一个很容易犯的错：把 2017、2018 的净收益率和成熟队列
并排画出来，读者会得出"近年也在稳定赚钱"的结论。而实际上这两批贷款
的坏账还没爆完——利息收了一半，损失才刚开始，两个量都被右删失截断，
算出来的数字既可能虚高也可能虚低，和成熟队列【根本不可比】。

所以处理方式是：
    成熟队列（最年轻的也走满 60 期）→ 实色蓝柱
    未成熟队列 → 灰色 + 斜纹，并在图上直接写明不可比
右图给出"为什么不可比"的证据：每批贷款到快照日实际能观察到多少个月。

⚠️ 斜纹不是装饰。颜色本身在黑白打印和色盲视角下会失效，
   斜纹是第二重编码，保证"这两根和别的不一样"这个信息无论如何都传得到。
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib.pyplot as plt
import numpy as np
import viz

d = viz.load('sql_03_pricing', 2)
years = d['放款年'].astype(int).values
net = d['净收益率'].values
mob = d['最短可观察账龄'].values
mature = (d['已走完全周期'] == '是').values

MATURE_C, IMMATURE_C = viz.S1, viz.RESID

fig, (axL, axR) = plt.subplots(1, 2, figsize=(14.0, 6.0),
                               gridspec_kw={'width_ratios': [1.25, 1]})

# ── 面板A：各队列净收益率 ──
x = np.arange(len(years))
colors = [MATURE_C if m else IMMATURE_C for m in mature]
hatch = ['' if m else '///' for m in mature]
for xi, v, c, h in zip(x, net, colors, hatch):
    axL.bar(xi, v, width=0.66, color=c, hatch=h,
            edgecolor=viz.SURFACE if h else 'none', linewidth=0.6, zorder=3)

axL.axhline(0, color=viz.AXIS, linewidth=1.0, zorder=2)
axL.set_xticks(x)
axL.set_xticklabels([str(y) for y in years])
axL.set_xlabel('放款年')
axL.set_ylabel('净收益率（利息收入 − 净损失，占放款本金 %）')
axL.set_ylim(min(net.min() - 3.2, -7), max(net) * 1.22)
viz.dress(axL)
viz.title(axL, '2007–2008 那两批是亏的，2013 那批最赚',
          '全周期账务口径 · 斜纹柱 = 未走完 60 期，不可比')

# 把最差那年的亏损直接标出来——负值柱不标数字很容易被忽略
for i in range(len(years)):
    if net[i] < 0:
        axL.text(x[i], net[i] - 0.7, f'{net[i]:.1f}', ha='center', va='top',
                 fontsize=9, color=viz.INK, fontweight='bold')

# 未成熟段单独圈出来说明，不给读者自行解读的空间
i_first_imm = int(np.where(~mature)[0][0])
axL.annotate('坏账还没爆完\n这两个数不能拿去比',
             xy=(x[i_first_imm] + 0.7, max(net) * 0.72),
             xytext=(x[i_first_imm] - 1.15, max(net) * 1.02),
             fontsize=9, color=viz.INK, ha='center', va='bottom',
             arrowprops=dict(arrowstyle='-', color=viz.MUTED, linewidth=0.9))

# 两个状态需要说明：不是两个"系列"，是对同一序列的可信度分层。
# ⚠️ 必须放【左上角】：左下角正是 2007/2008 两根负值柱和它们的数值标签所在，
#    第一版放在左下角，"实心 =" 那行字直接压穿了 "-5.1"。
axL.text(0.015, 0.97,
         '实心 = 已走完全周期，可比\n斜纹灰 = 未走完，不可比',
         transform=axL.transAxes, ha='left', va='top',
         fontsize=8.8, color=viz.MUTED, linespacing=1.6)

# ── 面板B：为什么不可比 ──
colors = [MATURE_C if m else IMMATURE_C for m in mature]
hatch = ['' if m else '///' for m in mature]
for xi, v, c, h in zip(x, mob, colors, hatch):
    axR.bar(xi, v, width=0.66, color=c, hatch=h,
            edgecolor=viz.SURFACE if h else 'none', linewidth=0.6, zorder=3)

axR.axhline(60, color=viz.INK, linewidth=1.4, linestyle=(0, (5, 3)), zorder=4)

axR.set_xticks(x)
axR.set_xticklabels([str(y) for y in years])
axR.set_xlabel('放款年')
axR.set_ylabel('到快照日最短可观察账龄（月）')
axR.set_ylim(0, max(mob) * 1.18)
# 横轴右侧留出空位放"60 期"这条线的说明。
# ⚠️ 不能靠右端直接写——2016 那根柱子有 68 个月高，标签会横穿柱子。
#    2018 那根只有 44 个月，它上方（y 46~62）才是唯一干净的地方。
axR.set_xlim(-0.6, 12.9)
axR.text(12.8, 61.5, '走完全周期 = 60 期', ha='right', va='bottom',
         fontsize=9.2, color=viz.INK)
viz.dress(axR)
viz.title(axR, '只有 2007–2016 越过了 60 期这条线',
          '取每年队列里【最短】的那笔——有一笔没走完，整年就不可比')

fig.text(0.5, -0.03,
         '为什么用"最短"而不是平均：净收益率是按年度合计算的，'
         '只要这一年里还有贷款没走完，分子分母就都被截断了。\n'
         '用平均值会让 2017 年看起来"基本走完"（平均账龄不低），但只要有少数几笔还在跑，'
         '这一年的损失率就还在变，和已经定型的年份没法放在一起比。',
         ha='center', fontsize=9, color=viz.MUTED)

viz.save(fig, 'c10_cohort_pnl.png')

print('\n各队列实际盈亏：')
for i, y in enumerate(years):
    print(f'  {y}: 净收益率 {net[i]:6.2f}%  最短账龄 {mob[i]:3d} 月  '
          f'{"可比" if mature[i] else "不可比"}')
