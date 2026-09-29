# -*- coding: utf-8 -*-
"""c13_stability.py —— 前五年有效的规律，后五年还作数吗。

这是整节的最后一道关：一个特征"有用"不只是要显著，
还得**在时间上稳定**。某个分箱在前段违约率低、后段突然变高，
说明这个规律可能只是那一年的特殊情况，拿去建模会翻车。

⚠️ 分半必须按【时间】切，不能随机切。
   随机切是把同一时期的贷款分到两边——两个子集几乎一模一样
   （都是同一个宏观环境、同一套审批标准），当然会得到"高度一致"的结论。
   那不是验证，是自我抄袭。按时间切才是真的样本外测试：
   用 2010–2014 看到的规律，去检验 2015–2018 还在不在。

图上的读法很直接：
   点落在对角线上  → 两个时期一样，规律稳定
   点在对角线上方  → 后段更差（违约率变高了）
   点在对角线下方  → 后段更好

⚠️ 只有三个特征能画：时间分半表里只保留了分箱数够多、
   且两段都有足够样本的特征。分箱只有 2 个的特征算不了秩相关
   （两个点永远共线，相关系数恒为 1，没有信息量）。
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
import viz
import db

MIN_N = 500
st = pd.read_csv(os.path.join(db.TABLES, 'sql_04_segments_r3.csv'))
st.columns = ['特征', '分箱', '时段', '笔数', '违约率']
st = st[st['笔数'] >= MIN_N]
piv = st.pivot_table(index=['特征', '分箱'], columns='时段',
                     values='违约率').dropna().reset_index()

# 三个特征三种颜色 —— 正好是分类色的上限，不需要并成"其他"
FEATS = ['01 借款用途', '02 信用等级', '03 负债收入比']
COLOR = {FEATS[0]: viz.S1, FEATS[1]: viz.S2, FEATS[2]: viz.S3}
LABEL = {FEATS[0]: '借款用途', FEATS[1]: '信用等级', FEATS[2]: '负债收入比'}

fig, ax = plt.subplots(figsize=(10.6, 8.4))

lo = min(piv['前段 2010-2014'].min(), piv['后段 2015-2018'].min()) - 1.5
hi = max(piv['前段 2010-2014'].max(), piv['后段 2015-2018'].max()) + 2.0

# 对角线画在最底层：它是参照，不是数据
ax.plot([lo, hi], [lo, hi], color=viz.AXIS, linewidth=1.4,
        linestyle=(0, (5, 3)), zorder=1)
ax.text(hi - 0.6, hi - 1.6, '两段一样', ha='right', va='top',
        fontsize=9, color=viz.MUTED)

for f in FEATS:
    g = piv[piv['特征'] == f]
    rho, _ = stats.spearmanr(g['前段 2010-2014'], g['后段 2015-2018'])
    # 秩相关直接写进图例标签，省掉一块单独的说明文字。
    # ⚠️ 不要用"画一个空散点占位、再事后去重"的写法——
    #    两个标签文本不同，按文本去重根本合并不了，图例会变成六项。
    ax.scatter(g['前段 2010-2014'], g['后段 2015-2018'],
               s=64, color=COLOR[f], label=f'{LABEL[f]}（秩相关 {rho:.2f}）',
               edgecolor=viz.SURFACE, linewidth=1.4, zorder=4)

# 只标出两个极端点：信用等级的 A（最安全）和 G（最高危）
for _, row in piv[piv['特征'] == FEATS[1]].iterrows():
    if row['分箱'] in ('A', 'G'):
        ax.annotate(row['分箱'],
                    xy=(row['前段 2010-2014'], row['后段 2015-2018']),
                    xytext=(9, -4), textcoords='offset points',
                    fontsize=10.5, fontweight='bold', color=COLOR[FEATS[1]])

ax.set_xlim(lo, hi)
ax.set_ylim(lo, hi)
ax.set_xlabel('前段 2010–2014 的 24 期违约率（%）')
ax.set_ylabel('后段 2015–2018 的 24 期违约率（%）')
ax.set_aspect('equal')
viz.dress(ax, xgrid=True, ygrid=True)
# 标题不能说"完全一致"——信用等级和负债收入比是 1.00，
# 但借款用途只有 0.86，有两三个箱换了位置。说"守住"是准确的，说"完全一致"不是。
viz.title(ax, '前段看到的次序，后段基本守住了',
          '按时间分半 · 每个点是一个分箱 · 点在线上方 = 后段更差')

ax.legend(loc='upper left', frameon=False, fontsize=10)

fig.text(0.5, -0.01,
         '读法：所有点都贴近对角线，次序没有乱——前段违约率高的分箱，后段依然高。\n'
         '同时几乎所有的点都在对角线上方，说明整体风险水平在后段抬升了'
         '（这正是第二节的结论，这里换了个角度又看到一次）。',
         ha='center', fontsize=9, color=viz.MUTED)

viz.save(fig, 'c13_stability.png')

print('分箱违约率：前段 vs 后段')
for f in FEATS:
    g = piv[piv['特征'] == f].sort_values('前段 2010-2014', ascending=False)
    rho, p = stats.spearmanr(g['前段 2010-2014'], g['后段 2015-2018'])
    print(f'\n  【{LABEL[f]}】秩相关 {rho:.3f}（p = {p:.4f}）')
    for _, row in g.iterrows():
        print(f'    {str(row["分箱"]):16s} '
              f'{row["前段 2010-2014"]:6.2f}% → {row["后段 2015-2018"]:6.2f}%')
