# -*- coding: utf-8 -*-
"""c12_discrimination.py —— 每个特征能把人分得多开。

IV 是个抽象的合成数，业务方看不懂。这张图把它翻译成一句人话：
**"用这个特征，最好的一批和最差的一批，违约率差几个百分点？"**

画法用"哑铃图"（range plot）：每个特征一条横线，左端是最好分箱、
右端是最差分箱，两个端点各点一个圆。比分组柱更适合这里，
因为要读的是【一条线有多长】，而不是每根柱子有多高——
18 个特征 × 2 个分箱 = 36 根柱子，读者根本比不过来。

⚠️ 端点只取"最好"和"最差"两个箱子，这会让短跨度的特征看起来也比实际的好一点，
   因为它是从所有箱子里挑出来的极值。所以这张图读的是【上界】：
   "就算把最有利和最不利的两群人挑出来比，也就差这么多。"
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import viz
import db

r = pd.read_csv(os.path.join(db.TABLES, 'seg_iv_rank.csv'))
r['跨度'] = r['最差箱违约率'] - r['最好箱违约率']
r = r.sort_values('跨度', ascending=False).reset_index(drop=True)

lo = r['最好箱违约率'].values
hi = r['最差箱违约率'].values
y = np.arange(len(r))

fig, ax = plt.subplots(figsize=(13.2, 7.6))

# 连线用中性灰：它表达的是"距离"，不是第三个类别，不该占用分类色。
for i in y:
    ax.plot([lo[i], hi[i]], [i, i], color=viz.AXIS, linewidth=2.2,
            solid_capstyle='round', zorder=2)

ax.scatter(lo, y, s=74, color=viz.S1, zorder=4,
           edgecolor=viz.SURFACE, linewidth=1.5, label='最好分箱')
ax.scatter(hi, y, s=74, color=viz.S2, zorder=4,
           edgecolor=viz.SURFACE, linewidth=1.5, label='最差分箱')

# 整体平均违约率做参照线：让读者知道这条哑铃是挂在哪个水平上的。
# 取中位数而不是第一个——各特征因为缺失值处理不同，覆盖的笔数略有出入
# （有的是 2,260,668 笔、有的少几百笔），取中位数避免被某个特殊特征带偏。
avg = float(r['违约率'].median())
ax.axvline(avg, color=viz.MUTED, linewidth=1.0, linestyle=(0, (4, 3)), zorder=1)
# 标注放【顶部】：底部那一行是"申请类型"，它的两个端点都紧贴在平均线附近，
# 标签放那里会和那根最短的哑铃挤在一起。
ax.text(avg + 0.25, 0.15, f'全样本平均 {avg:.2f}%', ha='left', va='top',
        fontsize=8.6, color=viz.MUTED)

ax.set_yticks(y)
ax.set_yticklabels(r['特征'].values, fontsize=9.6)
ax.invert_yaxis()
ax.set_xlabel('24 期违约率（%）')
ax.set_xlim(0, hi.max() * 1.12)
viz.dress(ax, xgrid=True, ygrid=False)
viz.title(ax, '能把人分得多开：一个特征，一道悬崖',
          '每个特征取最好与最差的分箱 · 全样本 226 万笔')

# 只标最后一行的跨度——它是结论的落点，标多了反而看不清重点
i_last = len(r) - 1
ax.annotate(f'跨度只有 {r["跨度"].iloc[i_last]:.1f} 个百分点',
            xy=(hi[i_last], i_last), xytext=(26, 0),
            textcoords='offset points', ha='left', va='center',
            fontsize=9, color=viz.INK)
ax.annotate(f'跨度 {r["跨度"].iloc[0]:.1f} 个百分点',
            xy=(lo[0], 0), xytext=(26, 12), textcoords='offset points',
            ha='left', va='bottom', fontsize=9.4, color=viz.INK,
            fontweight='bold')

ax.legend(loc='lower right', frameon=False, fontsize=9.8)

# 图注里的数字全部从数据里取，不手写——
# 手写的数字一旦数据重跑就会过期，而且过期了不会报错，只是安静地变成假的。
fig.text(0.5, -0.02,
         f'读法：看每条线有多长。信用等级的跨度是 {r["跨度"].iloc[0]:.0f} 个百分点，'
         f'第二梯队最好的{str(r["特征"].iloc[1]).split(" ", 1)[1]}只有 '
         f'{r["跨度"].iloc[1]:.0f} 个百分点，\n'
         f'而排在最末的{str(r["特征"].iloc[-1]).split(" ", 1)[1]}跨度只有 '
         f'{r["跨度"].iloc[-1]:.1f} 个百分点——'
         f'把它的两个分箱当成"不同风险群体"对待，是没有依据的。',
         ha='center', fontsize=9, color=viz.MUTED)

viz.save(fig, 'c12_discrimination.png')

print('各特征的违约率跨度：')
for _, row in r.iterrows():
    print(f'  {row["特征"]:14s} {row["最好箱违约率"]:6.2f}% → '
          f'{row["最差箱违约率"]:6.2f}%   跨度 {row["跨度"]:5.2f}pp   '
          f'（{row["最好箱"]} → {row["最差箱"]}）')
