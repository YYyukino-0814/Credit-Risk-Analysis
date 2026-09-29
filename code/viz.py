# -*- coding: utf-8 -*-
"""共用画图样式。

所有图都从这里取颜色和版式，保证：
  · 全项目一套颜色，不会各画各的；
  · 色板经过色盲安全校验（见下），不是随手挑的好看颜色。

色板校验记录（用 dataviz 技能的校验脚本跑过）：
  · 序数蓝阶 ORD 3 档：单色相、亮度单调、浅端对底色 2.06:1 —— ALL PASS
  · 分类槽位 1-3（S1/S2/S3）：最差相邻对 CVD ΔE 9.2、常视 ΔE 24.0 —— ALL PASS
  · 分类槽位 1-4 会失败（黄橙相邻，常视 ΔE 13.7 < 15），所以本项目【最多用 3 个分类色】，
    第 4 类一律并成"其他"或改用中性灰 RESID。
  · 青绿 S3 对浅底色只有 2.74:1，低于 3:1 —— 所以凡是用了 S3 的图，
    必须配图例或直接数值标签（relief 规则），不能只靠颜色区分。
"""
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

# ---------- 颜色 ----------
SURFACE = '#fcfcfb'   # 画布底色
INK     = '#0b0b0b'   # 主文字
INK2    = '#52514e'   # 次文字
MUTED   = '#898781'   # 坐标轴标签
GRID    = '#e1e0d9'   # 网格（发丝线，实线）
AXIS    = '#c3c2b7'   # 基线
S1      = '#2a78d6'   # 分类槽位1 蓝
S2      = '#eb6834'   # 分类槽位2 橙
S3      = '#1baf7a'   # 分类槽位3 青
RESID   = '#c3c2b7'   # 残差兜底灰（不是一类，是"剩下的"）
ORD     = ['#86b6ef', '#2a78d6', '#104281']  # 序数蓝阶（浅->深）

plt.rcParams.update({
    'font.sans-serif': ['Microsoft YaHei', 'SimHei'],
    'axes.unicode_minus': False,
    'figure.facecolor': SURFACE,
    'axes.facecolor': SURFACE,
    'savefig.facecolor': SURFACE,
    'axes.edgecolor': AXIS,
    'axes.linewidth': 0.8,
    'grid.color': GRID,
    'grid.linewidth': 0.8,
    'grid.linestyle': '-',
    'text.color': INK,
    'axes.labelcolor': INK2,
    'xtick.color': MUTED,
    'ytick.color': MUTED,
    'xtick.labelsize': 9.5,
    'ytick.labelsize': 9.5,
    'figure.dpi': 160,
})


def dress(ax, xgrid=False, ygrid=True):
    """统一的"退后"处理：去掉多余边框，网格做发丝线。"""
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    ax.spines['left'].set_color(AXIS)
    ax.spines['bottom'].set_color(AXIS)
    ax.set_axisbelow(True)
    # 注意：grid(False, color=...) 仍会把网格打开，所以关的时候不能带线型参数
    for axis, on in ((ax.xaxis, xgrid), (ax.yaxis, ygrid)):
        if on:
            axis.grid(True, color=GRID, linewidth=0.8)
        else:
            axis.grid(False)
    ax.tick_params(length=0)


def title(ax, main, sub=None):
    """主标题 + 副标题。副标题必须和主标题错开，否则两行字会压在一起。"""
    ax.set_title(main, fontsize=14, color=INK, pad=32 if sub else 12,
                 loc='left', fontweight='bold')
    if sub:
        ax.text(0, 1.0, sub, transform=ax.transAxes, fontsize=9.5,
                color=MUTED, va='bottom')


def load(tag, r):
    """读 run_sql.py 导出的结果集 csv。图的数据源永远是 SQL，不手抄。"""
    return pd.read_csv(os.path.join(db.TABLES, f'{tag}_r{r}.csv'))


def save(fig, name):
    os.makedirs(db.CHARTS, exist_ok=True)
    out = os.path.join(db.CHARTS, name)
    fig.tight_layout()
    fig.savefig(out, bbox_inches='tight')
    plt.close(fig)
    print(f'已存 {name}')
