# -*- coding: utf-8 -*-
"""c8_grade_pnl.py —— 各等级的实际盈亏：哪个等级在赚钱。

这张图用的是【全周期账务口径】，不是上一张的 24 期一阶近似：
利息是真实收到的（total_rec_int），损失是真实发生的（loss_net），
不依赖任何模型假设。代价是【只能用在已经走完 60 期的队列上】，
所以这里只包含 2007–2016 年的放款。这一点必须写在图注里，
不然读者会拿它去和 2018 年的定价表对照，那是两个不同的东西。

左图看"收的"和"亏的"怎么一起涨，右图看最后剩下多少。
右侧的倒 U 形是本节最反直觉的地方：最高危的 G 级不是最赚钱的，
也不是最亏的——它靠 38% 的利息硬扛住了 32% 的损失，只剩 6.6%。
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib.pyplot as plt
import numpy as np
import viz

d = viz.load('sql_03_pricing', 3)
grades = d['信用等级'].values
inc = d['利息收入率'].values
loss = d['净损失率'].values
net = d['净收益率'].values

x = np.arange(len(grades))
w = 0.37

fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.8, 6.0),
                               gridspec_kw={'width_ratios': [1.28, 1]})

# ── 面板A：收入与损失两个量 ──
# 分组柱，不堆叠：这两个量是相减关系不是相加关系，堆叠柱会让人误读成"合计"。
axL.bar(x - w / 2, inc, width=w, color=viz.S1, label='利息收入率', zorder=3)
axL.bar(x + w / 2, loss, width=w, color=viz.S2, label='净损失率', zorder=3)

axL.set_xticks(x)
axL.set_xticklabels(grades)
axL.set_xlabel('信用等级')
axL.set_ylabel('占放款本金（%）')
viz.dress(axL)
viz.title(axL, '高等级靠"收得多"扛住"亏得多"',
          '全周期账务口径 · 仅 2007–2016 已走完 60 期的放款')

axL.set_ylim(0, inc.max() * 1.12)   # 顶部留白给图例
axL.legend(loc='upper left', frameon=False, fontsize=9.8)
# G 级那句话【不放图里】。G 的橙柱顶（31.8）比 F 的蓝柱顶（37.0）还低，
# 任何贴着 G 橙柱往上写的注解都会落在 F 的蓝柱上。底部图注已经说了同一件事，
# 在图里再写一遍是重复，只会多一处压字。

# ── 面板B：净收益率 ──
# 单系列，不需要图例。柱子按倒 U 排，峰值的 D 级用深一档的蓝点出来。
# ⚠️ 不能拿 S1 去和高亮色配——viz.ORD[1] 的值就是 '#2a78d6'，和 S1 是同一个颜色，
#    第一版写成 ORD[1] vs S1，七根柱子长得一模一样，高亮等于没做。
#    走单色相浅→深的序数阶：中间调 ORD[1]，峰值 ORD[2]。
peak = int(np.argmax(net))
COL_PEAK, COL_OTHER = viz.ORD[2], viz.ORD[1]
colors = [COL_OTHER] * len(grades)
colors[peak] = COL_PEAK
axR.bar(x, net, width=0.6, color=colors, zorder=3)
# 峰值不再另加"峰值"二字——深色柱子 + 加粗的数值标签已经点明了，
# 再加一行字会和数值标签叠在一起，也要多花读者一次注视。

axR.set_xticks(x)
axR.set_xticklabels(grades)
axR.set_xlabel('信用等级')
axR.set_ylabel('净收益率（占放款本金 %）')
axR.set_ylim(0, net.max() * 1.28)
viz.dress(axR)
viz.title(axR, '净收益率是个倒 U 形', '中间等级 D 最高，两端都低')

for i, v in enumerate(net):
    axR.text(i, v + net.max() * 0.03, f'{v:.1f}', ha='center', va='bottom',
             fontsize=9.2, color=viz.INK,
             fontweight='bold' if i == peak else 'normal')

fig.text(0.5, -0.03,
         '读法：右图的倒 U 不是"中间等级更安全"——左图显示 C/D 的损失率明显低于 E/F/G，'
         '同时利率还没被推得太高，两头都占。\n'
         'G 级虽然名义利率最高（21.45%），但损失率吃掉 31.8 个点，最终只剩 6.6，是全部等级里最薄的。',
         ha='center', fontsize=9, color=viz.MUTED)

viz.save(fig, 'c8_grade_pnl.png')

print('\n各等级全周期盈亏：')
for i, g in enumerate(grades):
    print(f'  {g}: 利息 {inc[i]:6.2f}%  损失 {loss[i]:6.2f}%  净 {net[i]:6.2f}%')
