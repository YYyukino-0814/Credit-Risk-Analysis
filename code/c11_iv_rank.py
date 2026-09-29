# -*- coding: utf-8 -*-
"""c11_iv_rank.py —— 放款前能拿到的信息里，到底哪些真的能预测违约。

IV（信息值）是把"这个特征在多大程度上把好客户和坏客户分开"
压缩成一个数的做法。好处是所有特征用的是同一把尺子，
分类的、数值的都放在一起比，不用各说各的。

⚠️ 这张图必须分两个面板，不能只用一张。
   IV 从 0.3966 一路掉到 0.0000，跨度 262 倍。
   一张线性图里，除了第一根柱子其他的全是贴着轴的一条线，
   根本分不出"有点用"和"完全没用"——而第二梯队内部的排序
   恰恰是这一节最有业务价值的部分。
   面板B 把信用等级拿掉重新缩放，第二梯队才看得见。

⚠️ 这里没有用对数轴。柱状图的长度必须和数值成正比，
   对数轴会让"两倍"看起来和"十倍"差不多，是柱状图的经典误用。
   要看清小值就换一张图（面板B），不是把轴压弯。
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

rank = pd.read_csv(os.path.join(db.TABLES, 'seg_iv_rank.csv'))
rank = rank.sort_values('IV', ascending=False).reset_index(drop=True)

# IV 的经验分级线（业界惯例，不是硬标准，写在图里让读者自己判断）
CUTS = [(0.02, '几乎无用'), (0.10, '弱'), (0.30, '中等'), (0.50, '强')]

fig, (axA, axB) = plt.subplots(1, 2, figsize=(14.4, 7.4),
                               gridspec_kw={'width_ratios': [1, 1.05]})

def draw(ax, sub, ylabels, colors, xmax, show_cuts):
    y = np.arange(len(sub))
    ax.barh(y, sub['IV'].values, color=colors, height=0.66, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(ylabels, fontsize=9.4)
    ax.invert_yaxis()
    ax.set_xlim(0, xmax)
    ax.set_xlabel('IV（信息值）· 越大越能区分好坏客户')
    viz.dress(ax, xgrid=True, ygrid=False)
    for i, v in enumerate(sub['IV'].values):
        ax.text(v + xmax * 0.012, i, f'{v:.4f}', va='center', ha='left',
                fontsize=8.6, color=viz.MUTED)
    if show_cuts:
        for c, name in CUTS[:3]:
            if c < xmax:
                ax.axvline(c, color=viz.AXIS, linewidth=1.0,
                           linestyle=(0, (4, 3)), zorder=2)
                # 分级名放在【轴的底部】。放顶部会撞上副标题——
                # 副标题本来就占着标题下方那一行，两者叠在一起看不清。
                ax.text(c, len(sub) - 0.15, name, ha='center', va='top',
                        fontsize=8.2, color=viz.MUTED)

# ── 面板A：全部 18 个，线性标度 —— 看"一枝独秀" ──
# 只有第一根上色：这一面板要传达的信息就是"它和其他的不是一回事"。
cols_a = [viz.S1] + [viz.RESID] * (len(rank) - 1)
draw(axA, rank, rank['特征'].values, cols_a, rank['IV'].max() * 1.22, False)
# 关键数字直接写进副标题，不在图内另加注解——
# 图上唯一空旷的地方就是第一根柱子正上方，而那里正好是副标题的位置。
viz.title(axA, '一个特征，一道悬崖',
          f'信用等级 IV = {rank["IV"].iloc[0]:.4f}，其余 17 个全在 '
          f'{rank["IV"].iloc[1]:.4f} 以下 · 全样本 226 万笔')

# ── 面板B：去掉第一名之后重新缩放 ──
rest = rank.iloc[1:].reset_index(drop=True)
cols_b = [viz.ORD[2] if v >= 0.02 else viz.RESID for v in rest['IV'].values]
# 前两名用深色点出来：它们是第二梯队里唯一"有点用"的
cols_b[0] = cols_b[1] = viz.ORD[2]
draw(axB, rest, rest['特征'].values, cols_b, rest['IV'].max() * 1.25, True)
viz.title(axB, '第二梯队内部：只有两个还算能看',
          '已去掉信用等级 · 虚线是 IV 的常用分级线 · 深色 = 达到"弱"及以上')

fig.text(0.5, -0.02,
         '读法：IV 的经验分级是 <0.02 几乎无用、0.02~0.10 弱、0.10~0.30 中等、>0.30 强。\n'
         '18 个特征里只有信用等级达到"强"，其余最多只是"弱"——'
         '和第三节约 3 倍的风险跨度相比，第二梯队最好的（半年查询次数）只有 1.95 倍。',
         ha='center', fontsize=9, color=viz.MUTED)

viz.save(fig, 'c11_iv_rank.png')

print(rank[['特征', 'IV', 'IV分级', 'CramersV', '倍数']]
      .to_string(index=False, float_format=lambda x: f'{x:.4f}'))
