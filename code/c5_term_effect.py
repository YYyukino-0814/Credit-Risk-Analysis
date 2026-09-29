# -*- coding: utf-8 -*-
"""c5_term_effect.py —— 期限到底是不是风险因子：两个维度，两个相反的答案。

⚠️ 这张图是【返工重写】的。第一版直接拿"不分等级的 36 期 vs 60 期违约率"
   画折线，算出 60 期是 36 期的 1.38~1.74 倍，写成了"期限是独立于等级的
   第二个风险轴"。**那个结论是错的**，是典型的辛普森悖论：

       36 期里 A 级占 25.4%，60 期里 A 级只占 3.7%
       36 期里 E/F/G 合计 3.8%，60 期里高达 19.7%

   也就是说，"选 60 期的人本来信用分就更低"。把两拨人的等级构成拉平之后，
   60 期的 24 期违约率从 15.75% 掉到 10.09%，反而比 36 期的 10.91% 还低。
   等级构成解释了 117% 的差距——全部，还多出来一点。

   错误的地方在于：**期限只是看起来相关，真正相关的是"谁会选长期限"**。

但返工之后发现了一个【真的】期限效应，在另一个维度上：
   违约概率 PD —— 拉平等级后没差别
   违约损失率 LGD —— 拉平等级后，60 期仍稳定高出约 9 个百分点，七个等级无一例外

这个反差是这一节最有价值的地方：同一份数据，问"这批人会不会出事"
和问"出事了窟窿有多大"，答案完全相反。而业务含义也相反——前者是审批问题，
后者是产品结构和期限定价的问题。
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib.pyplot as plt
import numpy as np
import viz

d = viz.load('sql_02_vintage', 7)
g36 = d[d['期限'] == 36].set_index('信用等级')
g60 = d[d['期限'] == 60].set_index('信用等级')
grades = list('ABCDEFG')

# 三个数全部从结果7 推出来，不手抄任何一个：
#   36 期实际   = 按 36 期自己的等级权重加权
#   60 期实际   = 按 60 期自己的等级权重加权
#   60 期拉平   = 把 60 期的等级违约率，套到 36 期的等级权重上（直接标准化）
w36 = g36.loc[grades, '笔数'] / g36.loc[grades, '笔数'].sum()
w60 = g60.loc[grades, '笔数'] / g60.loc[grades, '笔数'].sum()
r36 = g36.loc[grades, '二十四期违约率']
r60 = g60.loc[grades, '二十四期违约率']

v36 = float((w36 * r36).sum())
v60 = float((w60 * r60).sum())
v60_std = float((w36 * r60).sum())

fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.8, 6.0),
                               gridspec_kw={'width_ratios': [1, 1.25]})

# ── 面板A：辛普森悖论 ──
# 第 1、3 根同色：它们才是可比的（都建立在 36 期的等级构成上）。
# 第 2 根换色：它是"看起来很高"的那个，颜色和位置一起提示它不对劲。
bars = [v36, v60, v60_std]
cols = [viz.S1, viz.S2, viz.S1]
axL.bar([0, 1, 2], bars, width=0.58, color=cols, zorder=3)

axL.set_xticks([0, 1, 2])
axL.set_xticklabels(['36 期\n（实际）', '60 期\n（未控制等级）', '60 期\n（等级构成拉平）'])
axL.set_ylabel('24 期累计违约率（%）')
axL.set_ylim(0, max(bars) * 1.30)
viz.dress(axL)
viz.title(axL, '把等级构成拉平，差距就没了',
          '同一个 24 期账龄 · 全样本 · 只看违约概率')

for xi, v in zip([0, 1, 2], bars):
    axL.text(xi, v + max(bars) * 0.03, f'{v:.2f}%', ha='center', va='bottom',
             fontsize=10, color=viz.INK, fontweight='bold')

axL.annotate('', xy=(1, v60), xytext=(1, v60_std),
             arrowprops=dict(arrowstyle='<->', color=viz.INK, linewidth=1.2))
# 文字必须落在橙柱【左边】——柱子占 0.71~1.29，
# 锚在 0.92 右对齐会让右半截字压进柱身里。
axL.text(0.66, (v60 + v60_std) / 2, f'{v60 - v60_std:.1f}pp\n全是等级构成',
         ha='right', va='center', fontsize=9.2, color=viz.INK)

# ── 面板B：LGD 上的期限差距是真的 ──
x = np.arange(len(grades))
w = 0.37
axR.bar(x - w / 2, g36.loc[grades, '违约损失率LGD'], width=w, color=viz.S1,
        label='36 期', zorder=3)
axR.bar(x + w / 2, g60.loc[grades, '违约损失率LGD'], width=w, color=viz.S2,
        label='60 期', zorder=3)

axR.set_xticks(x)
axR.set_xticklabels(grades)
axR.set_xlabel('信用等级')
axR.set_ylabel('违约损失率 LGD（违约时损失的本金比例）')
axR.set_ylim(0, 0.86)
viz.dress(axR)
viz.title(axR, '但"违约时亏多少"上，期限的差距是真的',
          '七个等级无一例外，60 期都要多亏 7~11 个百分点')
axR.legend(loc='upper left', frameon=False, fontsize=9.8, ncol=2)

fig.text(0.5, -0.03,
         '为什么 LGD 会差这么多：同样在第 24 个月违约，36 期贷款已经还掉约三分之二本金，'
         '60 期才还掉四成——\n剩下的窟窿自然差一大截。这不是客户质量问题，是摊还速度的算术。'
         '所以期限对定价的影响要走 LGD 那条路进来，不能靠"把长期限的违约率上调"来补。',
         ha='center', fontsize=9, color=viz.MUTED)

viz.save(fig, 'c5_term_effect.png')

print(f'\n24 期违约率：36 期 {v36:.2f}%  60 期（未控制）{v60:.2f}%  '
      f'60 期（拉平）{v60_std:.2f}%')
print(f'等级构成解释了 {v60 - v60_std:.2f}pp / {v60 - v36:.2f}pp '
      f'= {100 * (v60 - v60_std) / (v60 - v36):.0f}%')
print('\n各等级 LGD：')
for g in grades:
    a, b = g36.loc[g, '违约损失率LGD'], g60.loc[g, '违约损失率LGD']
    print(f'  {g}: 36 期 {a:.4f}  60 期 {b:.4f}  差 {b - a:+.4f}')
