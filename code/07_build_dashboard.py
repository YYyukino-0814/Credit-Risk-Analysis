# -*- coding: utf-8 -*-
"""C6 · 用 output/tableau 的 9 张聚合表生成「五屏看板」成品。

设计依据：分析文档/06_看板搭建说明.md（逐屏布局、配色规则、必须标注的话）
配色依据：code/viz.py（经过色盲安全校验的调色板）

产出：
  output/dashboard/五屏看板.html          单文件、离线可看、屏 4 可点击联动
  output/charts/dashboard_1_overview.png  五张截图（命名按说明 §九）
  output/charts/dashboard_2_quality.png
  output/charts/dashboard_3_pricing.png
  output/charts/dashboard_4_segments.png
  output/charts/dashboard_5_actions.png

用法：
    python code/07_build_dashboard.py

⚠️ 三条硬约束（说明 §二），改图时必须守住：
  1. 绝不用双轴图：量纲不同的两个量拆成两张图。
  2. 分类色最多 3 个；第 4 类及以上并成灰，或者（有序变量）改用单色阶。
  3. 两个及以上系列必须有图例；文字不穿系列颜色。
"""
import io
import os
import re
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import numpy as np
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, 'output', 'tableau')
DASH = os.path.join(BASE, 'output', 'dashboard')
CHARTS = os.path.join(BASE, 'output', 'charts')

# ---------------- 配色（与 viz.py 一致） ----------------
SURFACE = '#fcfcfb'
INK = '#0b0b0b'
INK2 = '#52514e'
MUTED = '#898781'
GRID = '#e1e0d9'
AXIS = '#c3c2b7'
S1 = '#2a78d6'      # 分类槽位 1 · 蓝
S2 = '#eb6834'      # 分类槽位 2 · 橙（语义：风险 / 没跟上）
S3 = '#1baf7a'      # 分类槽位 3 · 青
RESID = '#c3c2b7'   # 兜底灰（"剩下的"，不是一个新类别）

# 逾期等级 A–G 是【有序】变量：用单色阶而不是 7 个分类色
GRADE_RAMP = ['#c7dcf5', '#9dc3ea', '#72a9de', '#4a8fd0',
              '#2a78d6', '#1c5cae', '#104281']
# 12 个放款队列按「时期」归成 3 组（说明 §四）
ERA = [('早期 2007–2010', '#c8ccd2'),
       ('中期 2011–2015', S1),
       ('近期 2016–2018', S2)]

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
    'figure.dpi': 150,
    'svg.fonttype': 'none',      # SVG 里文字保持文字（可选中、体积小）
})


# ============================================================
# 读取 9 张聚合表
# ============================================================
def read(name):
    return pd.read_csv(os.path.join(SRC, name), encoding='utf-8-sig')


def load_all():
    d = {}
    s1 = read('s1_overview.csv')
    is_total = s1['放款年'].astype(str).str.startswith('合计')
    d['s1_total'] = s1[is_total].iloc[0]          # 指标卡用：只留合计行
    d['s1_year'] = s1[~is_total].reset_index(drop=True)   # 图用：排除合计行
    d['s2a'] = read('s2a_vintage_curve.csv')
    d['s2b'] = read('s2b_grade_mix.csv')
    d['s2c'] = read('s2c_effect_split.csv')
    d['s3a'] = read('s3a_grade_term.csv')
    d['s3b'] = read('s3b_cohort_pnl.csv')
    d['s3c'] = read('s3c_pricing_gap.csv')
    d['s4'] = read('s4_segments.csv')
    d['s5'] = read('s5_actions.csv')
    return d


# ============================================================
# 版式小工具
# ============================================================
def dress(ax, xgrid=False, ygrid=True):
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    ax.spines['left'].set_color(AXIS)
    ax.spines['bottom'].set_color(AXIS)
    if ygrid:
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    if xgrid:
        ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def ptitle(ax, title, sub=None):
    # 不用 set_title：标题和副标题要分行，用两个 text 才不会互相压
    ax.text(0, 1.078 if sub else 1.02, title, transform=ax.transAxes,
            fontsize=11.5, fontweight='bold', color=INK, va='bottom')
    if sub:
        ax.text(0, 1.016, sub, transform=ax.transAxes, fontsize=9,
                color=MUTED, va='bottom')


def callout(fig, x, y, w, h, text, edge=S2):
    """图上的「必须标注」方框——本看板最重要的东西（见说明 §十）。"""
    ax = fig.add_axes([x, y, w, h])
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_facecolor('#fdf6f1' if edge == S2 else '#f4f7fb')
    for side in ax.spines.values():
        side.set_color(edge)
        side.set_linewidth(1.0)
    ax.text(0.05, 0.5, text, transform=ax.transAxes, fontsize=8.8,
            color=INK2, va='center', ha='left', wrap=True)
    return ax


# ============================================================
# 各面板的画法（SVG 和 PNG 共用同一个函数）
# ============================================================
def plot_capital(ax, d):
    y = d['s1_year']
    ax.bar(y['放款年'].astype(int).astype(str), y['放款本金_百万'],
           color=S1, width=0.68, zorder=3)
    for i, v in enumerate(y['放款本金_百万']):
        if v > 3000:
            ax.text(i, v + 180, f'{v:,.0f}', ha='center', fontsize=8,
                    color=INK2)
    dress(ax)
    ax.set_ylabel('放款本金（百万美元）', fontsize=9)
    ax.tick_params(axis='x', rotation=60)
    ptitle(ax, '图 1-A1 · 放款规模逐年放大',
           '2007 年 5 百万 → 2018 年 7,936 百万')


def plot_rate(ax, d):
    y = d['s1_year']
    ax.plot(y['放款年'].astype(int).astype(str), y['平均利率'],
            marker='o', markersize=4.5, linewidth=2, color=S1, zorder=4)
    dress(ax)
    ax.set_ylim(11, 15.2)
    ax.set_ylabel('平均利率 %', fontsize=9)
    ax.tick_params(axis='x', rotation=60)
    ptitle(ax, '图 1-A2 · 平均利率没有跟着规模走',
           '12 年里在 11.8% ~ 14.5% 之间摆动，没有趋势')


def plot_status(ax, d):
    y = d['s1_year'].copy()
    tot = y['已结清'] + y['已核销'] + y['未决']
    pct = pd.DataFrame({
        '已结清': y['已结清'] / tot * 100,
        '已核销': y['已核销'] / tot * 100,
        '未决': y['未决'] / tot * 100,
    })
    x = y['放款年'].astype(int).astype(str)
    bottom = np.zeros(len(y))
    for name, color in [('已结清', S1), ('已核销', S2), ('未决', S3)]:
        ax.bar(x, pct[name], bottom=bottom, color=color, width=0.7,
               label=name, zorder=3)
        bottom += pct[name].to_numpy()
    for i, v in enumerate(pct['未决']):
        if v > 1:
            ax.text(i, 100 - v / 2, f'{v:.1f}', ha='center', va='center',
                    fontsize=7.5, color='#ffffff', fontweight='bold')
    dress(ax)
    ax.set_ylim(0, 112)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_ylabel('占该年放款笔数 %', fontsize=9)
    ax.tick_params(axis='x', rotation=60)
    ax.legend(loc='lower center', bbox_to_anchor=(0.5, -0.42), ncol=3,
              frameon=False, fontsize=9)
    ptitle(ax, '图 1-B · 三种状态的占比（100% 堆叠）',
           '每年三段之和 = 100%；柱顶绿色那一段是「还没判」')


def plot_vintage(ax, d):
    df = d['s2a']
    labels = []
    for era_name, color in ERA:
        lo, hi = (2007, 2010) if '早期' in era_name else \
                 (2011, 2015) if '中期' in era_name else (2016, 2018)
        for year, g in df[(df['放款年'] >= lo) & (df['放款年'] <= hi)].groupby('放款年'):
            g = g.sort_values('账龄月')
            ax.plot(g['账龄月'], g['累计违约率_官方口径'], color=color,
                    linewidth=1.6, alpha=0.85, zorder=3)
            last = g.iloc[-1]
            labels.append([float(last['账龄月']), float(last['累计违约率_官方口径']),
                           str(int(year)), color])
        # 只给每个时期做一次图例
        ax.plot([], [], color=color, linewidth=2.4, label=era_name)
    # 12 个年份标签挤在同一个横坐标上，必须撑开，否则叠成一团
    labels.sort(key=lambda t: t[1])
    for i in range(1, len(labels)):
        if labels[i][1] - labels[i - 1][1] < 1.08:
            labels[i][1] = labels[i - 1][1] + 1.08
    for x0, y0, name, color in labels:
        ax.text(x0 + 1.5, y0, name, fontsize=7.8, color=color, va='center')
    dress(ax)
    ax.set_xlabel('账龄月（从放款起算，不是日历月）', fontsize=9)
    ax.set_ylabel('累计违约率 %', fontsize=9)
    ax.set_xlim(0, 42)
    ax.set_ylim(0, 31)
    ax.legend(frameon=False, fontsize=9, loc='upper left')
    ptitle(ax, '图 2-A · 队列曲线（Vintage）— 整个项目最重要的一张',
           '横轴是账龄月：12 个队列对齐到同一起点才可比')


def plot_grade_mix(ax, d):
    df = d['s2b']
    piv = df.pivot_table(index='放款年', columns='等级',
                         values='等级占比_百分比', aggfunc='sum')
    grades = [g for g in ['A', 'B', 'C', 'D', 'E', 'F', 'G'] if g in piv.columns]
    piv = piv[grades]
    x = piv.index.astype(int).astype(str)
    bottom = np.zeros(len(piv))
    for i, g in enumerate(grades):
        ax.bar(x, piv[g], bottom=bottom, color=GRADE_RAMP[i], width=0.72,
               label=g, zorder=3, edgecolor=SURFACE, linewidth=0.6)
        bottom += piv[g].to_numpy()
    dress(ax)
    ax.set_ylim(0, 100)
    ax.set_ylabel('等级占比 %', fontsize=9)
    ax.tick_params(axis='x', rotation=60)
    ax.legend(loc='lower center', bbox_to_anchor=(0.5, -0.5), ncol=7,
              frameon=False, fontsize=8.5, title='信用等级',
              title_fontsize=8.5)
    ab = piv[['A', 'B']].sum(axis=1) if 'B' in piv.columns else piv['A']
    pk = int(ab.idxmax())
    after = ab.loc[pk:]           # 见顶之后才是「塌陷」，别拿 2007 年当最低点
    tr = int(after.idxmin())
    note = (f'A+B 级占比：{pk} 年见顶 {ab.max():.1f}% → '
            f'{tr} 年见底 {after.min():.1f}%（恶化的结构性原因）')
    ptitle(ax, '图 2-B · 等级构成：辛普森悖论的证据', note)


def plot_effect(ax, d):
    df = d['s2c']
    piv = df.pivot_table(index='放款年', columns='效应', values='贡献pp')
    order = ['结构效应', '组内效应', '交互项']
    order = [c for c in order if c in piv.columns]
    x = piv.index.astype(int).astype(str)
    pos = np.zeros(len(piv))
    neg = np.zeros(len(piv))
    colors = [S1, S2, S3]
    for i, e in enumerate(order):
        v = piv[e].to_numpy()
        base = np.where(v >= 0, pos, neg)
        ax.bar(x, v, bottom=base, color=colors[i], width=0.7, label=e, zorder=3)
        pos = pos + np.where(v >= 0, v, 0)
        neg = neg + np.where(v < 0, v, 0)
    ax.axhline(0, color=AXIS, linewidth=1)
    dress(ax)
    ax.set_ylabel('对总变化的贡献（个百分点）', fontsize=9)
    ax.tick_params(axis='x', rotation=60)
    ax.legend(frameon=False, fontsize=9, loc='upper right')
    ptitle(ax, '图 2-C · 效应拆解：恶化有多少来自等级内部',
           '三段相加 = 该年相对基准期的总变化')


def plot_grade_term(ax, d):
    df = d['s3a']
    grades = sorted(df['信用等级'].unique())
    terms = sorted(df['期限'].unique())
    x = np.arange(len(grades))
    w = 0.36
    for i, t in enumerate(terms):
        sub = df[df['期限'] == t].set_index('信用等级').reindex(grades)
        ax.bar(x + (i - 0.5) * w, sub['毛价差'], width=w,
               color=S1 if i == 0 else S2, label=f'{t} 期', zorder=3)
        for xi, v in zip(x + (i - 0.5) * w, sub['毛价差']):
            if not np.isnan(v):
                ax.text(xi, v + 0.12, f'{v:.1f}', ha='center', fontsize=7.6,
                        color=INK2)
    dress(ax)
    ax.set_xticks(x)
    ax.set_xticklabels(grades)
    ax.set_xlabel('信用等级', fontsize=9)
    ax.set_ylabel('毛价差（百分点）', fontsize=9)
    ax.set_ylim(0, 9)
    ax.legend(frameon=False, fontsize=9, ncol=2, loc='upper right')
    ptitle(ax, '图 3-A · 等级 × 期限的毛价差',
           'A/B/C 两个期限几乎等高；D 级以上 60 期明显矮一截')


def plot_cohort_pnl(ax, d):
    df = d['s3b']
    x = df['放款年'].astype(int).astype(str)
    colors = [S1 if c == '可比' else RESID for c in df['是否可比']]
    ax.bar(x, df['净收益率'], color=colors, width=0.68, zorder=3)
    for i, (v, c) in enumerate(zip(df['净收益率'], df['是否可比'])):
        ax.text(i, v + (0.45 if v >= 0 else -0.9), f'{v:.1f}', ha='center',
                fontsize=7.8, color=INK2 if c == '可比' else MUTED)
    ax.axhline(0, color=AXIS, linewidth=1)
    dress(ax)
    ax.set_ylabel('净收益率 %', fontsize=9)
    ax.tick_params(axis='x', rotation=60)
    ax.set_ylim(-8, 18)
    ax.plot([], [], color=S1, linewidth=8, label='已走完全周期（可比）')
    ax.plot([], [], color=RESID, linewidth=8, label='未走完（不可比）')
    ax.legend(frameon=False, fontsize=8.8, loc='lower right')
    ptitle(ax, '图 3-B · 各队列实际盈亏 — 灰色两个数不可比',
           '2017–2018 利息只收了一半、坏账还没爆完，不能读成「变差」')


def plot_pricing_gap(ax, d):
    df = d['s3c'].iloc[::-1]
    colors = [S2 if v < 0 else RESID for v in df['定价缺口pp']]
    y = np.arange(len(df))
    ax.barh(y, df['定价缺口pp'], color=colors, height=0.62, zorder=3)
    for yi, v in zip(y, df['定价缺口pp']):
        ax.text(v + (0.08 if v >= 0 else -0.08), yi, f'{v:+.2f}',
                va='center', ha='left' if v >= 0 else 'right',
                fontsize=8.4, color=INK2)
    ax.axvline(0, color=AXIS, linewidth=1)
    dress(ax, xgrid=True, ygrid=False)
    ax.set_yticks(y)
    ax.set_yticklabels(df['信用等级'])
    ax.set_xlim(-1.4, 4.0)
    ax.set_xlabel('定价缺口（百分点）= 利率涨幅 − 期望损失涨幅', fontsize=9)
    ax.plot([], [], color=S2, linewidth=8, label='没跟上（负缺口）')
    ax.plot([], [], color=RESID, linewidth=8, label='跟上了')
    ax.legend(frameon=False, fontsize=8.8, loc='lower left')
    ptitle(ax, '图 3-C · 定价缺口：B / C 级是「温和恶化」的漏网之鱼',
           '真正的缺口在中间两个等级，不在风险最高的等级')


def plot_bins(ax, df, feature, hide_ylabel=False):
    """屏 4-A · 某个特征的各分箱违约率 + 95% 置信区间。"""
    g = df[df['特征'] == feature].copy()
    g['分箱'] = g['分箱'].astype(str)
    # 不能按分箱名排序（"10" 会排在 "2" 前面）：按违约率排，看图更清楚
    g = g.sort_values('违约率', ascending=True).reset_index(drop=True)
    y = np.arange(len(g))
    lo = g['违约率'] - g['违约率下界95']
    hi = g['违约率上界95'] - g['违约率']
    top = float(g['违约率上界95'].max()) * 1.30
    ax.errorbar(g['违约率'], y, xerr=[lo, hi], fmt='o', markersize=6,
                color=S1, ecolor=INK2, elinewidth=1.3, capsize=3.5, zorder=4)
    for yi, (v, n, w) in enumerate(zip(g['违约率'], g['笔数'], g['区间宽度'])):
        ax.text(v, yi + 0.30, f'{v:.2f}%', ha='center', fontsize=8.2,
                color=INK2, fontweight='bold')
        ax.text(top, yi, f'{int(n):,} 笔',
                ha='right', va='center', fontsize=7.6, color=MUTED)
    dress(ax, xgrid=True, ygrid=False)
    ax.set_yticks(y)
    ax.set_yticklabels(g['分箱'], fontsize=9)
    ax.set_ylim(-0.7, len(g) - 0.3)
    ax.set_xlim(0, top)
    ax.set_xlabel('违约率 %（横线 = 95% 置信区间，右侧字 = 该箱样本量）',
                  fontsize=9)
    iv = g['IV'].iloc[0]
    ivg = g['IV分级'].iloc[0]
    wid = g['区间宽度'].median()
    ptitle(ax, f'{feature} · {len(g)} 个分箱',
           f'IV = {iv:.4f}（{ivg}）　·　置信区间宽度中位数 {wid:.2f} 个百分点')


def fmt_iv(v):
    return f'{v:.4f}' if v >= 0.0001 else f'{v:.2e}'


def unit_of(name):
    """监控基期值的单位：含「差」的是价差 / 损失差（pp），否则是比率（%）。"""
    s = str(name)
    return '%' if ('率' in s and '差' not in s) else 'pp'


def card_rows(s5, name):
    """某一屏建议在卡片里显示的行：(维度, 指标, 数值+单位, 年化缺口, 敞口)。

    建议 1 在 s5_actions 里没有细项行动行（它的金额只出现在文档 05 第四节），
    所以退回显示它的监控基期值行，避免卡片空着。
    """
    acts = s5[s5['指标'].notna() & (s5['建议'] == name)]
    out = [(str(r.维度), str(r.指标), f'{r.数值:g} {r.单位}',
            f'{r.年化缺口_百万美元:,.2f}', f'{r.敞口_百万美元:,.1f}')
           for r in acts.itertuples()]
    if out:
        return out
    mon = s5[s5['监控指标'].notna() & (s5['建议'] == name)]
    return [(str(r.维度), str(r.监控指标).split('（')[0],
             f'{r.数值:g} {unit_of(r.监控指标)}', '—', '—')
            for r in mon.itertuples()]


# ============================================================
# 单文件 HTML
# ============================================================
_SVG_SEQ = [0]


def namespace_svg(s, tag):
    """给一个 SVG 里所有 id 打上前缀，并同步改写引用。

    ⚠️ 这个步骤不能省：一张 HTML 里内嵌 27 个 matplotlib SVG，
    每个都有 `figure_1` / `axes_1` / `patch_1` 这种同名 id。
    HTML 的 id 必须全文档唯一，重名会让 `url(#...)` / `xlink:href="#..."`
    解析到别的图上的定义，表现是"图看着对、局部却被裁没了"。
    """
    ids = sorted(set(re.findall(r'id="([^"]+)"', s)), key=len, reverse=True)
    for i in ids:
        s = s.replace(f'id="{i}"', f'id="{tag}-{i}"')
        s = s.replace(f'url(#{i})', f'url(#{tag}-{i})')
        s = s.replace(f'xlink:href="#{i}"', f'xlink:href="#{tag}-{i}"')
        s = s.replace(f'href="#{i}"', f'href="#{tag}-{i}"')
    return s


def fig_to_svg(fig):
    buf = io.StringIO()
    fig.savefig(buf, format='svg', bbox_inches='tight', pad_inches=0.08)
    plt.close(fig)
    s = buf.getvalue()
    s = s[s.index('<svg'):]
    # 去掉 matplotlib 塞进来的 metadata（含生成日期和库版本号，交付物里不需要）
    s = re.sub(r'<metadata>.*?</metadata>', '', s, flags=re.S)
    # 让 SVG 跟着容器宽度缩放（保留 viewBox）
    s = re.sub(r'(<svg[^>]*?)\swidth="[^"]*"', r'\1', s, count=1)
    s = re.sub(r'(<svg[^>]*?)\sheight="[^"]*"', r'\1', s, count=1)
    s = s.replace('<svg', '<svg class="viz"', 1)
    _SVG_SEQ[0] += 1
    return namespace_svg(s, f'svg{_SVG_SEQ[0]}')


def svg_of(fn, *args, figsize=(6.4, 3.6), **kw):
    fig, ax = plt.subplots(figsize=figsize)
    fn(ax, *args, **kw)
    return fig_to_svg(fig)


def build_html(D):
    t = D['s1_total']
    s5 = D['s5']
    feats = (D['s4'].groupby('特征', sort=False)
             .agg(IV=('IV', 'max'), 级别=('IV分级', 'first'),
                  分箱数=('分箱', 'size'))
             .reset_index().sort_values('IV', ascending=False)
             .reset_index(drop=True))
    iv_max = float(feats['IV'].max())

    def esc(x):
        return (str(x).replace('&', '&amp;').replace('<', '&lt;')
                .replace('>', '&gt;'))

    # ---------- 屏 1 ----------
    cards = [
        ('总放款笔数', f"{t['放款笔数']:,.0f}", '笔', '2007–2018'),
        ('总放款本金', f"{t['放款本金_百万']:,.1f}", '百万美元（约 340 亿）', '合计行口径'),
        ('加权平均利率', f"{t['平均利率']:.2f}", '%', '加权，不是把 12 年利率相加'),
        ('加权未决占比', f"{t['未决占比_百分比']:.2f}", '%', '2018 单年是 7.7%，别混'),
    ]
    card_html = ''.join(
        f'<div class="card"><span class="label">{esc(a)}</span>'
        f'<span class="value">{esc(b)}<em>{esc(c)}</em></span>'
        f'<span class="hint">{esc(d)}</span></div>'
        for a, b, c, d in cards)

    s1_html = f"""
<section id="s1" class="screen active">
  <div class="shead"><h2>1 · 放款总览</h2>
    <p>2007–2018 共 226 万笔、340 亿美元　·　平均单笔 15,047 美元</p></div>
  <div class="cards">{card_html}</div>
  <div class="grid2">
    <figure>{svg_of(plot_capital, D)}<figcaption>放款规模逐年放大 —— 这是「分母在变」的证据，后面每一屏都要记得这件事。</figcaption></figure>
    <figure>{svg_of(plot_rate, D)}<figcaption>利率没有跟着规模走。量纲和规模不同，所以拆成两张图，不做双轴。</figcaption></figure>
  </div>
  <figure class="wide">{svg_of(plot_status, D, figsize=(9.2, 4.2))}
    <figcaption>每一年三段相加 = 100%。柱顶绿色那一段（未决）是「还没判」，不是「质量变差」。</figcaption></figure>
  <aside class="warn"><b>必须标注：</b>2017–2018 队列尚未结清，占比不可与早期队列直接比较。
  不加这句，看图的人一定会得出「近年质量在改善」的结论——那只是时间不够，不是风险变低。</aside>
</section>"""

    # ---------- 屏 2 ----------
    s2_html = f"""
<section id="s2" class="screen">
  <div class="shead"><h2>2 · 放款质量</h2>
    <p>趋势是倒 U 形，恶化来自等级内部　·　数据源 s2a / s2b / s2c</p></div>
  <figure class="wide">{svg_of(plot_vintage, D, figsize=(9.2, 4.3))}
    <figcaption>横轴是账龄月不是日历月——这是 vintage 曲线的全部意义。若用日历月，2018 队列只会画出一小段，看起来像违约率暴涨。</figcaption></figure>
  <div class="grid2">
    <figure>{svg_of(plot_grade_mix, D, figsize=(6.4, 4.0))}
      <figcaption>等级是<b>有序</b>变量，所以用单色阶（浅→深），不是 7 个分类色——分类色最多 3 个是硬规则。</figcaption></figure>
    <figure>{svg_of(plot_effect, D, figsize=(6.4, 4.0))}
      <figcaption>三段相加 = 该年相对基准期的总变化。组内效应占大头，说明恶化不是「客群变差」造成的。</figcaption></figure>
  </div>
  <aside class="note"><b>读法：</b>2-A 看趋势、2-B 回答「构成变了多少」、2-C 回答「总变化里多少是构成、多少是真实恶化」。
  三张图缺任何一张，结论都会被追问倒。</aside>
</section>"""

    # ---------- 屏 3 ----------
    s3_html = f"""
<section id="s3" class="screen">
  <div class="shead"><h2>3 · 定价与收益</h2>
    <p>B / C 级没跟上，60 期漏掉了 LGD　·　数据源 s3a / s3b / s3c</p></div>
  <div class="grid2">
    <figure>{svg_of(plot_grade_term, D, figsize=(6.4, 3.9))}
      <figcaption>D 级往上，36 期和 60 期的柱子明显分叉 —— 这就是「用 36 期的价差补贴 60 期的风险」。</figcaption></figure>
    <figure>{svg_of(plot_pricing_gap, D, figsize=(6.4, 3.9))}
      <figcaption>缺口 = 利率涨幅 − 期望损失涨幅。负值（橙色）= 没跟上，全部落在 B / C 级。</figcaption></figure>
  </div>
  <figure class="wide">{svg_of(plot_cohort_pnl, D, figsize=(9.2, 3.9))}
    <figcaption>灰色的两个队列<b>不可比</b>：利息只收了一半、坏账还没爆完。连成一条线会被读成「近年也很赚钱」。</figcaption></figure>
  <aside class="warn"><b>必须标注：</b>缺口 = 利率涨幅 − 期望损失涨幅（已按 LGD 折算）。
  <b>不折算 LGD 的话七个等级全是负缺口，结论会完全反过来。</b></aside>
</section>"""

    # ---------- 屏 4（交互） ----------
    bin_panels = []
    for i, f in enumerate(feats['特征']):
        svg = svg_of(plot_bins, D['s4'], f, figsize=(6.6, max(2.6, 0.62 * feats.loc[i, '分箱数'] + 1.5)))
        on = ' on' if i == 0 else ''
        bin_panels.append(
            f'<div class="binpanel{on}" data-feature="{esc(f)}">{svg}</div>')
    iv_rows = []
    for i, r in enumerate(feats.itertuples()):
        w = r.IV / iv_max * 100
        cls = 'strong' if r.级别 == '强' else ('weak' if r.级别 == '弱' else 'none')
        sel = ' sel' if i == 0 else ''
        iv_rows.append(
            f'<div class="ivrow{sel}" data-feature="{esc(r.特征)}">'
            f'<span class="ivname">{esc(r.特征)}</span>'
            f'<span class="ivtrack"><i class="refline" style="left:5.04%"></i>'
            f'<i class="refline" style="left:25.21%"></i>'
            f'<i class="refline" style="left:75.63%"></i>'
            f'<i class="ivbar {cls}" style="width:{w:.2f}%"></i></span>'
            f'<span class="ivval">{fmt_iv(r.IV)}</span>'
            f'<span class="ivtag {cls}">{esc(r.级别)}</span></div>')

    s4_html = f"""
<section id="s4" class="screen">
  <div class="shead"><h2>4 · 风险分群</h2>
    <p>18 个字段里只有信用等级真正管用　·　数据源 s4_segments（94 行，字段 × 分箱）</p></div>
  <aside class="hint"><b>这一屏可以点：</b>点左边任意一根柱子，右边立刻换成那个字段的分箱违约率与 95% 置信区间。
  这就是「一个看板」和「一堆图」的区别。</aside>
  <div class="grid4">
    <div class="ivpanel">
      <h3>图 4-B · IV 排名</h3>
      <p class="tiny">按 IV 降序　·　虚线在 0.02 / 0.10 / 0.30（几乎无用 / 弱 / 中等）</p>
      <div class="ivlist">{''.join(iv_rows)}</div>
      <p class="tiny legend">IV 是<b>单变量</b>指标，不做任何控制。<b>IV 低不等于没用，只等于「单独用没用」</b>——
      借款用途 IV 只有 0.0202，但屏 3 能看到它在等级内部仍有独立信息。</p>
    </div>
    <div class="binpanel-box">
      <h3 id="bintitle">图 4-A · 分箱违约率与 95% 置信区间</h3>
      <p class="tiny" id="binsub"></p>
      {''.join(bin_panels)}
    </div>
  </div>
  <aside class="note"><b>区间是这个屏的价值所在。</b>没有区间，「婚礼这个用途违约率只有 8.83%」看起来像一条结论；
  有区间（7.75% ~ 10.05%）才知道这个箱子只有 2,355 笔，不能当结论用。</aside>
</section>"""

    # ---------- 屏 5 ----------
    acts = s5[s5['指标'].notna()].copy()
    mon = s5[s5['监控指标'].notna()].copy()
    # 三条建议的年化缺口 / 敞口：来自 分析文档/05_行动建议.md 第四节（s5 表里行动 1 未单列金额）
    head = [('1 B/C 级定价缺口', 2145, 4340, '利率矩阵（未来放款）'),
            ('2 六十期期限价', 9615, 5500, '利率矩阵 / 准入规则'),
            ('3 用途纳入规则', 995, 410, '定价与额度规则')]
    cols = []
    for name, gap, exp, lever in head:
        trs = ''.join(
            f"<tr><td>{esc(a)}</td><td>{esc(b)}</td>"
            f"<td class='num'>{esc(c)}</td>"
            f"<td class='num'>{esc(d)}</td><td class='num'>{esc(e)}</td></tr>"
            for a, b, c, d, e in card_rows(s5, name))
        cols.append(f"""
      <div class="action">
        <h3>{esc(name)}</h3>
        <div class="gapbig"><span>{gap:,}</span> 万美元 / 年</div>
        <p class="tiny">敞口 {exp:,} 百万美元　·　能动手的地方：{esc(lever)}</p>
        <table><thead><tr><th>维度</th><th>指标</th><th>数值</th><th>年化缺口<br>（百万美元）</th><th>敞口<br>（百万美元）</th></tr></thead>
        <tbody>{trs}</tbody></table>
      </div>""")
    mon_rows = ''.join(
        f"<tr><td>{esc(r.建议)}</td><td>{esc(r.监控指标)}</td>"
        f"<td class='num'>{r.数值:g} {unit_of(r.监控指标)}</td></tr>"
        for r in mon.itertuples())

    s5_html = f"""
<section id="s5" class="screen">
  <div class="shead"><h2>5 · 行动看板</h2>
    <p>三条建议，年化缺口合计量级约 1 亿美元　·　数据源 s5_actions</p></div>
  <div class="actions">{''.join(cols)}</div>
  <table class="monitor"><caption>监控基期值 —— 建议落地后按季重跑 sql_05_actions.sql，数值朝预期方向动 = 生效</caption>
    <thead><tr><th>建议</th><th>监控指标</th><th>基期值</th></tr></thead>
    <tbody>{mon_rows}</tbody></table>
  <aside class="warn"><b>不能相加：</b>三条缺口简单相加是 <b>1.28 亿美元</b>，
  但三条的敞口有重叠，<b>直接相加是重复计算</b>；对外只能说「合计量级约 1 亿美元」。
  换个口径看：占 340 亿美元本金的 <b>0.38%</b>——这个数不大，正是它可信的理由。</aside>
  <aside class="note"><b>为什么只给基期值、不给目标值？</b>因为涨价之后客群会变、竞争反应会变，
  「应该涨到多少」算不出来。能给的只有基期值和方向，剩下的要靠真实数据反馈来调。</aside>
</section>"""

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>信贷风险分析 · 五屏看板</title>
<style>
:root {{
  --surface:{SURFACE}; --ink:{INK}; --ink2:{INK2}; --muted:{MUTED};
  --grid:{GRID}; --axis:{AXIS}; --s1:{S1}; --s2:{S2}; --s3:{S3}; --resid:{RESID};
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--surface); color:var(--ink);
  font:14px/1.65 "Microsoft YaHei","SimHei",system-ui,sans-serif; }}
header {{ padding:26px 32px 0; border-bottom:1px solid var(--grid); }}
h1 {{ margin:0 0 4px; font-size:21px; letter-spacing:.2px; }}
header .sub {{ margin:0 0 16px; color:var(--muted); font-size:12.5px; }}
.tabs {{ display:flex; gap:4px; flex-wrap:wrap; }}
.tabs button {{ appearance:none; border:1px solid var(--grid); background:#fff;
  border-bottom:none; border-radius:8px 8px 0 0; padding:9px 16px; cursor:pointer;
  font:13px/1 "Microsoft YaHei",sans-serif; color:var(--ink2); position:relative; top:1px; }}
.tabs button:hover {{ color:var(--ink); }}
.tabs button.active {{ background:var(--surface); color:var(--ink); font-weight:700;
  border-bottom:1px solid var(--surface); }}
main {{ padding:22px 32px 60px; max-width:1320px; }}
.screen {{ display:none; }}
.screen.active {{ display:block; }}
.shead h2 {{ margin:0 0 2px; font-size:18px; }}
.shead p {{ margin:0 0 18px; color:var(--muted); font-size:12.5px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr));
  gap:14px; margin-bottom:20px; }}
.card {{ background:#fff; border:1px solid var(--grid); border-radius:10px;
  padding:14px 16px; display:flex; flex-direction:column; gap:2px; }}
.card .label {{ color:var(--muted); font-size:12.5px; }}
.card .value {{ color:var(--s1); font-size:27px; font-weight:700; letter-spacing:.4px; }}
.card .value em {{ font-size:12.5px; font-style:normal; color:var(--ink2);
  font-weight:400; margin-left:6px; }}
.card .hint {{ color:var(--muted); font-size:11.5px; }}
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
figure {{ margin:0 0 16px; background:#fff; border:1px solid var(--grid);
  border-radius:10px; padding:12px 14px 8px; }}
figure.wide {{ padding-bottom:6px; }}
figcaption {{ color:var(--muted); font-size:12px; padding:6px 2px 8px;
  border-top:1px solid var(--grid); margin-top:6px; }}
.viz {{ width:100%; height:auto; display:block; }}
.warn,.note,.hint {{ border-radius:9px; padding:12px 15px; font-size:13px;
  margin:6px 0 14px; }}
.warn {{ background:#fdf6f1; border:1px solid var(--s2); }}
.note {{ background:#f4f7fb; border:1px solid var(--s1); }}
.hint {{ background:#f2f8f5; border:1px solid var(--s3); }}
.grid4 {{ display:grid; grid-template-columns:minmax(330px,0.85fr) 1.15fr;
  gap:16px; align-items:start; }}
.ivpanel,.binpanel-box {{ background:#fff; border:1px solid var(--grid);
  border-radius:10px; padding:14px 16px; }}
.ivpanel h3,.binpanel-box h3 {{ margin:0 0 2px; font-size:13.5px; }}
.tiny {{ font-size:11.5px; color:var(--muted); margin:4px 0 12px; }}
.ivlist {{ display:flex; flex-direction:column; gap:3px; }}
.ivrow {{ display:grid; grid-template-columns:96px 1fr 62px 52px; gap:8px;
  align-items:center; padding:3px 6px; border-radius:6px; cursor:pointer;
  border-left:3px solid transparent; }}
.ivrow:hover {{ background:#f7f9fc; }}
.ivrow.sel {{ background:#fdf6f1; border-left-color:var(--s2); }}
.ivname {{ font-size:12px; color:var(--ink2); }}
.ivtrack {{ position:relative; height:14px; background:#f1f3f6; border-radius:3px; }}
.ivbar {{ display:block; height:100%; border-radius:3px; }}
.ivbar.strong {{ background:var(--s1); }}
.ivbar.weak {{ background:var(--resid); }}
.ivbar.none {{ background:#e4e7eb; }}
.refline {{ position:absolute; top:-2px; bottom:-2px; width:1px;
  background:var(--axis); }}
.ivval {{ font-size:11.5px; color:var(--ink2); text-align:right;
  font-variant-numeric:tabular-nums; }}
.ivtag {{ font-size:10.5px; text-align:center; border-radius:20px; padding:1px 0; }}
.ivtag.strong {{ background:#e8f1fb; color:var(--s1); }}
.ivtag.weak {{ background:#f1f3f6; color:var(--ink2); }}
.ivtag.none {{ background:#f6f7f9; color:var(--muted); }}
.legend {{ margin-top:10px; }}
.binpanel {{ display:none; }}
.binpanel.on {{ display:block; }}
.actions {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr));
  gap:16px; margin-bottom:18px; }}
.action {{ background:#fff; border:1px solid var(--grid); border-radius:10px;
  padding:14px 16px; }}
.action h3 {{ margin:0 0 8px; font-size:14px; }}
.gapbig {{ font-size:12.5px; color:var(--ink2); margin-bottom:6px; }}
.gapbig span {{ font-size:24px; font-weight:700; color:var(--s2); }}
table {{ width:100%; border-collapse:collapse; font-size:12px; }}
th,td {{ border-bottom:1px solid var(--grid); padding:6px 7px; text-align:left; }}
th {{ color:var(--muted); font-weight:500; font-size:11.5px; }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
table.monitor {{ background:#fff; border:1px solid var(--grid);
  border-radius:10px; overflow:hidden; margin-bottom:16px; }}
table.monitor caption {{ caption-side:top; text-align:left; padding:12px 14px 8px;
  color:var(--ink2); font-size:12.5px; font-weight:700; }}
table.monitor th,table.monitor td {{ padding:8px 14px; }}
footer {{ padding:0 32px 40px; color:var(--muted); font-size:12px; max-width:1320px; }}
@media (max-width:900px) {{ .grid2,.grid4 {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<header>
  <h1>信贷风险分析 · 五屏看板</h1>
  <p class="sub">LendingClub 2007–2018　·　226 万笔、340 亿美元　·　数据源 output/tableau 的 9 张聚合表
  　·　配色与 code/viz.py 一致（已过色盲安全校验）</p>
  <nav class="tabs">
    <button data-tab="s1" class="active">1 放款总览</button>
    <button data-tab="s2">2 放款质量</button>
    <button data-tab="s3">3 定价与收益</button>
    <button data-tab="s4">4 风险分群</button>
    <button data-tab="s5">5 行动看板</button>
  </nav>
</header>
<main>
{s1_html}
{s2_html}
{s3_html}
{s4_html}
{s5_html}
</main>
<footer>
  <p><b>三条贯穿全看板的规则：</b>① 绝不用双轴图（量纲不同就拆图）；② 分类色最多 3 个，第 4 类并成灰，
  有序变量（信用等级 A–G）改用单色阶；③ 两个及以上系列必须有图例，文字不穿系列颜色。</p>
  <p>本看板由 <code>code/07_build_dashboard.py</code> 从 <code>output/tableau/*.csv</code> 生成，可重复运行。
  截图存档见 <code>output/charts/dashboard_1~5_*.png</code>。</p>
</footer>
<script>
(function () {{
  var tabs = document.querySelectorAll('.tabs button');
  tabs.forEach(function (b) {{
    b.addEventListener('click', function () {{
      tabs.forEach(function (x) {{ x.classList.remove('active'); }});
      b.classList.add('active');
      document.querySelectorAll('.screen').forEach(function (s) {{
        s.classList.toggle('active', s.id === b.dataset.tab);
      }});
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }});
  }});

  // 屏 4 的联动：点 IV 柱子 → 下面那张图换成该字段的分箱
  var rows = document.querySelectorAll('.ivrow');
  var panels = document.querySelectorAll('.binpanel');
  var title = document.getElementById('bintitle');
  var sub = document.getElementById('binsub');
  function pick(feature) {{
    rows.forEach(function (r) {{
      r.classList.toggle('sel', r.dataset.feature === feature);
    }});
    panels.forEach(function (p) {{
      p.classList.toggle('on', p.dataset.feature === feature);
    }});
    title.textContent = '图 4-A · ' + feature + ' 的分箱违约率与 95% 置信区间';
    sub.textContent = '每一个点是一个分箱，横线是 95% 置信区间，右侧数字是该箱样本量';
  }}
  rows.forEach(function (r) {{
    r.addEventListener('click', function () {{ pick(r.dataset.feature); }});
  }});
  if (rows.length) {{ pick(rows[0].dataset.feature); }}
}})();
</script>
</body>
</html>
"""
    os.makedirs(DASH, exist_ok=True)
    out = os.path.join(DASH, '五屏看板.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    return out


# ============================================================
# 五张截图（说明 §九 的命名）
# ============================================================
def screen_figure(title, sub):
    fig = plt.figure(figsize=(15.4, 9.2))
    fig.text(0.035, 0.965, title, fontsize=19, fontweight='bold', color=INK,
             va='top')
    fig.text(0.035, 0.932, sub, fontsize=11.5, color=MUTED, va='top')
    return fig


def shot_1(D, path):
    fig = screen_figure('放款总览', '2007–2018 共 226 万笔、340 亿美元　·　源 s1_overview')
    gs = GridSpec(3, 4, figure=fig, left=0.070, right=0.975, top=0.855,
                  bottom=0.075, hspace=1.05, wspace=0.45,
                  height_ratios=[0.85, 1.5, 1.5])
    t = D['s1_total']
    cards = [(f"{t['放款笔数']:,.0f}", '总放款笔数'),
             (f"{t['放款本金_百万']:,.1f}", '总放款本金（百万美元）'),
             (f"{t['平均利率']:.2f}%", '加权平均利率'),
             (f"{t['未决占比_百分比']:.2f}%", '加权未决占比')]
    for i, (v, lab) in enumerate(cards):
        ax = fig.add_subplot(gs[0, i])
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_facecolor('#ffffff')
        for side in ax.spines.values():
            side.set_color(GRID)
        ax.text(0.5, 0.66, v, transform=ax.transAxes, ha='center', fontsize=20,
                fontweight='bold', color=S1)
        ax.text(0.5, 0.26, lab, transform=ax.transAxes, ha='center',
                fontsize=10, color=INK2)
    plot_capital(fig.add_subplot(gs[1, 0:2]), D)
    plot_rate(fig.add_subplot(gs[1, 2:4]), D)
    plot_status(fig.add_subplot(gs[2, 0:3]), D)
    callout(fig, 0.735, 0.085, 0.24, 0.20,
            '必须标注\n2017–2018 队列尚未结清，占比不可\n与早期队列直接比较。\n'
            '不标这句，会被读成「近年质量在改善」\n——那只是时间不够。')
    fig.savefig(path, dpi=150)
    plt.close(fig)


def shot_2(D, path):
    fig = screen_figure('放款质量（Vintage）',
                        '趋势是倒 U 形，恶化来自等级内部　·　源 s2a / s2b / s2c')
    gs = GridSpec(2, 2, figure=fig, left=0.062, right=0.975, top=0.855,
                  bottom=0.095, hspace=0.80, wspace=0.28,
                  height_ratios=[1.15, 1.0])
    plot_vintage(fig.add_subplot(gs[0, :]), D)
    plot_grade_mix(fig.add_subplot(gs[1, 0]), D)
    plot_effect(fig.add_subplot(gs[1, 1]), D)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def shot_3(D, path):
    fig = screen_figure('定价与收益',
                        'B / C 级没跟上，60 期漏掉了 LGD　·　源 s3a / s3b / s3c')
    gs = GridSpec(2, 3, figure=fig, left=0.065, right=0.975, top=0.855,
                  bottom=0.095, hspace=0.85, wspace=0.4,
                  height_ratios=[1.0, 1.0])
    plot_grade_term(fig.add_subplot(gs[0, 0:2]), D)
    plot_pricing_gap(fig.add_subplot(gs[0, 2]), D)
    plot_cohort_pnl(fig.add_subplot(gs[1, 0:2]), D)
    callout(fig, 0.672, 0.085, 0.303, 0.20,
            '必须标注\n缺口 = 利率涨幅 − 期望损失涨幅（已按 LGD 折算）。\n'
            '不折算 LGD 的话七个等级全是负缺口，\n结论会完全反过来。')
    fig.savefig(path, dpi=150)
    plt.close(fig)


def shot_4(D, path):
    fig = screen_figure('风险分群',
                        '18 个字段里只有信用等级真正管用　·　源 s4_segments（94 行，字段 × 分箱）')
    gs = GridSpec(1, 2, figure=fig, left=0.105, right=0.975, top=0.835,
                  bottom=0.09, wspace=0.34, width_ratios=[1.25, 0.85])
    ax = fig.add_subplot(gs[0, 0])
    feats = (D['s4'].groupby('特征', sort=False)
             .agg(IV=('IV', 'max'), 级别=('IV分级', 'first'))
             .reset_index().sort_values('IV', ascending=True).reset_index(drop=True))
    colors = [S1 if g == '强' else (RESID if g == '弱' else '#e4e7eb')
              for g in feats['级别']]
    y = np.arange(len(feats))
    ax.barh(y, feats['IV'], color=colors, height=0.62, zorder=3)
    for yi, v in zip(y, feats['IV']):
        ax.text(v + 0.006, yi, fmt_iv(v), va='center', fontsize=8, color=INK2)
    for xv, lab in [(0.02, '0.02 几乎无用'), (0.10, '0.10 弱'), (0.30, '0.30 中等')]:
        ax.axvline(xv, color=AXIS, linewidth=1, linestyle='--', zorder=2)
        ax.text(xv, len(feats) - 0.55, lab, fontsize=8, color=MUTED,
                rotation=0, ha='center', va='bottom')
    dress(ax, xgrid=True, ygrid=False)
    ax.set_yticks(y)
    ax.set_yticklabels(feats['特征'], fontsize=9)
    ax.set_ylim(-0.7, len(feats) + 0.45)
    ax.set_xlim(0, 0.47)
    ax.set_xlabel('IV（信息量）', fontsize=9)
    ptitle(ax, '图 4-B · IV 排名：只有信用等级越过了 0.30',
           '橙色高亮 = 本屏默认展示的字段')
    ax.add_patch(plt.Rectangle((0, len(feats) - 1 - 0.42), 0.47, 0.84,
                               fill=False, edgecolor=S2, linewidth=1.6))
    plot_bins(fig.add_subplot(gs[0, 1]), D['s4'], '01 信用等级')
    fig.savefig(path, dpi=150)
    plt.close(fig)


def shot_5(D, path):
    fig = screen_figure('行动看板',
                        '三条建议，年化缺口合计量级约 1 亿美元　·　源 s5_actions')
    s5 = D['s5']
    acts = s5[s5['指标'].notna()]
    mon = s5[s5['监控指标'].notna()]
    head = [('1 B/C 级定价缺口', 2145, 4340, '利率矩阵（未来放款）'),
            ('2 六十期期限价', 9615, 5500, '利率矩阵 / 准入规则'),
            ('3 用途纳入规则', 995, 410, '定价与额度规则')]
    gs = GridSpec(1, 3, figure=fig, left=0.035, right=0.975, top=0.845,
                  bottom=0.375, wspace=0.26)
    for i, (name, gap, exp, lever) in enumerate(head):
        ax = fig.add_subplot(gs[0, i])
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_facecolor('#ffffff')
        for side in ax.spines.values():
            side.set_color(GRID)
        ax.text(0.03, 0.94, name, transform=ax.transAxes, fontsize=12.5,
                fontweight='bold', color=INK, va='top')
        ax.text(0.03, 0.80, f'{gap:,}', transform=ax.transAxes, fontsize=20,
                fontweight='bold', color=S2, va='top')
        ax.text(0.03, 0.655, '万美元 / 年', transform=ax.transAxes,
                fontsize=10, color=INK2, va='top')
        ax.text(0.03, 0.55, f'敞口 {exp:,} 百万美元', transform=ax.transAxes,
                fontsize=9.5, color=MUTED, va='top')
        ax.text(0.03, 0.465, f'能动手：{lever}', transform=ax.transAxes,
                fontsize=9.5, color=MUTED, va='top')
        cols_x = [(0.03, 'left'), (0.21, 'left'), (0.62, 'right'),
                  (0.81, 'right'), (0.99, 'right')]
        for (cx, ha), lab in zip(cols_x, ['维度', '指标', '数值',
                                          '年化缺口', '敞口']):
            ax.text(cx, 0.375, lab, transform=ax.transAxes, fontsize=8,
                    color=MUTED, va='top', ha=ha)
        yy = 0.295
        for a, b, c, dd, e in card_rows(s5, name):
            for (cx, ha), val in zip(cols_x, [a, b, c, dd, e]):
                ax.text(cx, yy, val, transform=ax.transAxes, fontsize=8.6,
                        color=INK2, va='top', ha=ha)
            yy -= 0.078
    ax = fig.add_axes([0.035, 0.10, 0.60, 0.22])
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_facecolor('#ffffff')
    for side in ax.spines.values():
        side.set_color(GRID)
    ax.text(0.025, 0.92, '监控基期值 —— 建议落地后按季重跑 sql_05_actions.sql，数值朝预期方向动 = 生效',
            transform=ax.transAxes, fontsize=10.5, fontweight='bold',
            color=INK, va='top')
    yy = 0.72
    for r in mon.itertuples():
        ax.text(0.025, yy, str(r.建议), transform=ax.transAxes, fontsize=9.5,
                color=INK2, va='top')
        ax.text(0.30, yy, str(r.监控指标), transform=ax.transAxes, fontsize=9.5,
                color=INK2, va='top')
        ax.text(0.975, yy, f'{r.数值:g} {r.单位}', transform=ax.transAxes,
                fontsize=9.5, color=INK2, va='top', ha='right')
        yy -= 0.115
    callout(fig, 0.655, 0.10, 0.32, 0.22,
            '不能相加\n三条缺口简单相加是 1.28 亿美元，但三条的\n'
            '敞口有重叠，直接相加是重复计算。\n'
            '对外只能说「合计量级约 1 亿美元」——\n占 340 亿本金的 0.38%，不大，正是它可信的理由。')
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    D = load_all()
    out = build_html(D)
    os.makedirs(CHARTS, exist_ok=True)
    shots = [('dashboard_1_overview.png', shot_1),
             ('dashboard_2_quality.png', shot_2),
             ('dashboard_3_pricing.png', shot_3),
             ('dashboard_4_segments.png', shot_4),
             ('dashboard_5_actions.png', shot_5)]
    for name, fn in shots:
        p = os.path.join(CHARTS, name)
        fn(D, p)
        print(f'  ✔ {os.path.relpath(p, BASE)}')
    size = os.path.getsize(out) / 1024
    print(f'  ✔ {os.path.relpath(out, BASE)}  ({size:,.0f} KB)')
    print('五屏看板生成完成。')


if __name__ == '__main__':
    main()
