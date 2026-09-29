# -*- coding: utf-8 -*-
"""
00_selfcheck.py — 全项目自检。任何时候都能跑，改完任何东西都该跑一遍。

为什么单独写这个脚本：
    这个项目最长的一句话结论（"放款质量在变好还是变坏"）建立在一串数字上。
    如果中间某一环静默错了——比如未决贷款被当成了"好"、账龄算错一个月、
    特征表里混进了一个放款后才有的字段——后面所有图和结论都会跟着错，
    而且【不会报错】。错误会一路漂漂亮亮地走到面试官面前。

    所以把"怎样才算对"写成可执行的断言。断言过了不代表结论对，
    但断言不过就一定有问题，而且问题会在它产生的那一刻就被发现。

用法：
    python code/00_selfcheck.py
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db


def main():
    con = db.connect()
    rows = []

    def add(name, ok, detail):
        rows.append(ok)
        print(f'  {"✅" if ok else "❌"} {name}')
        print(f'       {detail}')

    print('\n═══ 数据完整性 ═══')

    # ── 1. 行数守恒：三种状态必须不多不少拼成全集 ──
    # 这是最基础的一条。任何一个 CASE WHEN 写漏了一种状态，总数就对不上。
    r = con.execute("""
        SELECT COUNT(*) AS 总,
               SUM(CASE WHEN status_group='已结清' THEN 1 ELSE 0 END) AS 结清,
               SUM(CASE WHEN status_group='已核销' THEN 1 ELSE 0 END) AS 核销,
               SUM(CASE WHEN status_group='未决'   THEN 1 ELSE 0 END) AS 未决
        FROM loans
    """).fetchdf().iloc[0]
    s = r['结清'] + r['核销'] + r['未决']
    add('行数守恒：已结清 + 已核销 + 未决 = 总数', s == r['总'],
        f"{r['结清']:,} + {r['核销']:,} + {r['未决']:,} = {s:,}，主表 {r['总']:,}")

    # ── 2. 未决的标签必须是 NULL 而不是 0 ──
    # 这条看着琐碎，其实是全项目最容易犯、后果最严重的错：
    # 把 Current/Late/Grace 当成"没违约=0"会严重低估违约率，
    # 而年轻队列未决占比更高，正好制造出一个假的"质量在改善"。
    n = con.execute(
        "SELECT COUNT(*) FROM loans WHERE status_group='未决' AND outcome IS NOT NULL"
    ).fetchone()[0]
    add('未决贷款的 outcome 是 NULL 而不是 0', n == 0, f'违例 {n:,} 笔')

    # ── 3. 账务恒等式（本项目的 LGD 全建立在它上面）──
    # 实测结论：结清与核销的贷款，剩余本金一律归零；未结清的必有剩余本金。
    # 正因为核销后 out_prncp 归零，净损失才能直接写成
    #     loan_amnt − total_rec_prncp − recoveries
    # 而不是去猜"核销时还剩多少本金没还"。
    #
    # ⚠️ 第一版断言写成"已核销的 out_prncp 必须全为 0"，结果报 22 笔违例。
    #    查下去发现【不是脏数据，是我自己的归并逻辑没说全】：
    #    这 22 笔的原始状态全是 Default（一笔 Charged Off 都没有），
    #    它们满足一条更强的恒等式 total_rec_prncp + out_prncp = loan_amnt。
    #    Default = 已违约但核销流程还没走完 → 余额自然还挂着。
    #    所以断言按状态拆开验：真正不能再有的余额是 Charged Off 的。
    r = con.execute("""
        SELECT SUM(CASE WHEN loan_status LIKE 'Charged Off%' AND out_prncp > 0
                        THEN 1 ELSE 0 END) AS 核销仍有余额,
               SUM(CASE WHEN status_group='已结清' AND out_prncp > 0 THEN 1 ELSE 0 END) AS 结清仍有余额,
               SUM(CASE WHEN status_group='已核销' AND out_prncp > 0
                        THEN ABS(total_rec_prncp + out_prncp - loan_amnt) END) AS 未走完流程的最大偏离
        FROM loans
    """).fetchdf().iloc[0]
    ok3 = (r['核销仍有余额'] == 0 and r['结清仍有余额'] == 0
           and (r['未走完流程的最大偏离'] is None or r['未走完流程的最大偏离'] < 0.01))
    add('账务恒等式：Charged Off/结清后剩余本金归零；Default 则满足 已收+剩余=本金',
        bool(ok3),
        f"Charged Off 仍有余额 {r['核销仍有余额']:,} 笔，结清仍有余额 {r['结清仍有余额']:,} 笔；"
        f"尚未走完核销流程的 Default 笔数 {r['未走完流程的最大偏离'] is not None and '有' or '无'}"
        f"，这些笔的 |已收本金+剩余本金−放款本金| 最大 {r['未走完流程的最大偏离'] or 0:.4f} 元")

    # ── 4. 结清的贷款，收回本金应该等于放款本金 ──
    # 一条独立的交叉验证：如果算错了列（比如把 funded_amnt 当 loan_amnt），
    # 这里会立刻炸出来。
    r = con.execute("""
        SELECT AVG(ABS(total_rec_prncp - loan_amnt) / loan_amnt) AS 平均相对偏差,
               SUM(CASE WHEN ABS(total_rec_prncp - loan_amnt) / loan_amnt > 0.01
                        THEN 1 ELSE 0 END) AS 偏差超1pct笔数,
               COUNT(*) AS 结清笔数
        FROM loans WHERE status_group='已结清' AND loan_amnt > 0
    """).fetchdf().iloc[0]
    add('交叉验证：已结清贷款的收回本金 ≈ 放款本金',
        r['偏差超1pct笔数'] / r['结清笔数'] < 0.02,
        f"平均相对偏差 {r['平均相对偏差']*100:.3f}%，"
        f"偏差超 1% 的 {r['偏差超1pct笔数']:,} / {r['结清笔数']:,} 笔")

    # ── 5. 净损失的上下界，两个方向分开验 ──
    # 上界（硬约束）：净损失绝不能超过本金——超了就是算错了分母。
    #    实测 0 笔，这条是干净的。
    # 下界（有解释的软约束）：净损失可以为负，但必须【全部能被回收款解释】。
    #    第一版断言写成"负损失必须为 0"，报 2,578 笔违例。查下去同样不是脏数据：
    #    实测"本金超收笔数 = 0"（total_rec_prncp 从不超过 loan_amnt），
    #    超收全部来自 recoveries —— 催收按【含利息的总债务】打折回收，
    #    而 total_rec_prncp 只记本金，所以回收款会超过剩余本金。
    #    所以下界断言改成"负损失必须伴随着回收款，且占比 < 1%"，
    #    这才是真正该守住的东西：一旦哪天负损失里冒出没回收款的，
    #    或者占比突然变大，就说明口径出事了。
    r = con.execute("""
        SELECT COUNT(*) AS 核销总数,
               SUM(CASE WHEN loss_net > loan_amnt + 0.01 THEN 1 ELSE 0 END) AS 超本金,
               SUM(CASE WHEN loss_net < -0.01 THEN 1 ELSE 0 END) AS 负损失,
               SUM(CASE WHEN loss_net < -0.01 AND recoveries <= 0 THEN 1 ELSE 0 END) AS 负损失但无回收,
               SUM(CASE WHEN total_rec_prncp > loan_amnt + 0.01 THEN 1 ELSE 0 END) AS 本金超收
        FROM loans WHERE status_group='已核销' AND loan_amnt > 0
    """).fetchdf().iloc[0]
    ratio = r['负损失'] / r['核销总数']
    add('已核销贷款：净损失不超本金，负损失全部由回收款解释且占比 < 1%',
        r['超本金'] == 0 and r['负损失但无回收'] == 0 and ratio < 0.01,
        f"{r['核销总数']:,} 笔核销：超本金 {r['超本金']:,} 笔；"
        f"负损失 {r['负损失']:,} 笔（{ratio*100:.2f}%），其中无回收款的 {r['负损失但无回收']:,} 笔；"
        f"本金超收 {r['本金超收']:,} 笔（应为 0，超收只该来自回收款）")

    # ── 5b. 官方状态标签与账务数字的对不上，必须被如实记录 ──
    # 这是本项目最重要的一条"数据质量限制"，值得单独一条断言盯着。
    #
    # 事实：有一批贷款状态是 Fully Paid（官方口径 = 好客户、PD 记 0），
    #       但本金从未收全。已排除债务和解与 hardship（这两类标记全部为 N）。
    # 危害：它【不是均匀分布】——几乎全部落在 2007–2011。
    #       官方口径下 2008 年核销率 20.73%，算上这批就是 38.15%，
    #       等于把金融危机那一年最该冒出来的信号抹掉了一半。
    #
    # 这条断言不是"检查错误"，而是【把这个偏离的规模钉死】：
    # 一旦哪天它变大或跑到近年队列去，说明我的口径或者数据理解出了新问题。
    r = con.execute("""
        SELECT COUNT(*) AS 已定标签,
               SUM(CASE WHEN loss_occurred = 1 AND outcome = 0 THEN 1 ELSE 0 END) AS 结清却亏钱,
               ROUND(SUM(CASE WHEN loss_occurred = 1 AND outcome = 0
                              THEN loss_net ELSE 0 END)/1e6, 2) AS 未计损失_百万,
               ROUND(100.0*SUM(CASE WHEN loss_occurred = 1 AND outcome = 0
                                    THEN 1 ELSE 0 END)/COUNT(*), 4) AS 占比,
               SUM(CASE WHEN issue_year >= 2013 AND loss_occurred = 1
                        AND outcome = 0 THEN 1 ELSE 0 END) AS 近年笔数
        FROM loans WHERE outcome IS NOT NULL
    """).fetchdf().iloc[0]
    add('标签噪声已量化：结清却亏钱的贷款占比 < 0.5%，且集中在早年',
        r['占比'] < 0.5 and r['近年笔数'] / r['已定标签'] < 0.0005,
        f"{r['已定标签']:,} 笔已定标签中，标为结清但净损失 > 0 的 {r['结清却亏钱']:,.0f} 笔"
        f"（{r['占比']:.3f}%），合计未计入的损失 {r['未计损失_百万']:.2f} 百万元；"
        f"其中 2013 年及以后仅 {r['近年笔数']:,.0f} 笔 —— 确认集中在早年")

    print('\n═══ 字段解析 ═══')

    # ── 6. 利率解析成功率 ──
    # int_rate 原值是 " 8.07%"，解析失败会变成 NULL，进而在所有利率分析里静默消失。
    r = con.execute("""
        SELECT COUNT(*) AS 总, COUNT(int_rate) AS 非空,
               MIN(int_rate) AS 最小, MAX(int_rate) AS 最大
        FROM loans
    """).fetchdf().iloc[0]
    add('int_rate 解析成功率 > 99%', r['非空'] / r['总'] > 0.99,
        f"{r['非空']:,}/{r['总']:,} = {r['非空']/r['总']*100:.2f}%，"
        f"取值范围 {r['最小']:.2f}% ~ {r['最大']:.2f}%")

    # ── 7. 期限只有 36 / 60 两种 ──
    # 若冒出来个 3 或 360，说明 term 的解析出了岔子，所有按期限分层的分析都废了。
    r = con.execute("""
        SELECT term_m, COUNT(*) AS 笔数 FROM loans GROUP BY 1 ORDER BY 1
    """).fetchdf()
    ok = set(r['term_m'].dropna().astype(int)) <= {36, 60}
    add('期限 term_m 只有 36 和 60 两种',
        ok, '；'.join(f'{int(a)} 期 {b:,} 笔' for a, b in zip(r['term_m'], r['笔数'])))

    # ── 8. 信用等级越高利率越低（严格单调）──
    # 这是对"等级"这个字段最朴素的常识检验。若不单调，要么解析错了，
    # 要么数据有问题——无论哪种，后面拿 grade 做的所有分组都不成立。
    g = con.execute("""
        SELECT grade, AVG(int_rate) AS 平均利率, COUNT(*) AS 笔数
        FROM loans WHERE grade IS NOT NULL GROUP BY 1 ORDER BY 1
    """).fetchdf()
    bad = [(g['grade'][i], g['平均利率'][i], g['平均利率'][i + 1])
           for i in range(len(g) - 1) if g['平均利率'][i] >= g['平均利率'][i + 1]]
    add('各信用等级平均利率严格单调递增（A 最低 G 最高）', not bad,
        '  '.join(f'{a}:{b:.2f}%' for a, b in zip(g['grade'], g['平均利率']))
        + (f'　⚠️ 反常处 {bad}' if bad else ''))

    print('\n═══ 时间与账龄 ═══')

    # ── 9. 事件时点不能晚于快照日 ──
    # 这条守着整个 vintage 分析的时间原点。若某笔贷款的最后一笔还款
    # 超过了快照日，说明快照日定错了（本项目的快照日是实测出来的，不是文档给的，
    # 所以更需要这条断言兜住）。
    snap = con.execute(f'SELECT {db.SNAPSHOT}').fetchone()[0]
    r = con.execute(f"""
        SELECT MAX(last_pymnt_date) AS 最晚还款, MAX(issue_date) AS 最晚放款,
               SUM(CASE WHEN last_pymnt_date > {db.SNAPSHOT} THEN 1 ELSE 0 END) AS 超快照笔数
        FROM loans
    """).fetchdf().iloc[0]
    add('还款/放款时点不晚于快照日', r['超快照笔数'] == 0,
        f"快照日 {snap}，最晚还款 {r['最晚还款']}，最晚放款 {r['最晚放款']}，"
        f"超快照 {r['超快照笔数']:,} 笔")

    # ── 10. 账龄不能超过可观察上限 ──
    # mob_event 是"用最后一笔还款代理的事件时点"，它必须落在该笔贷款的
    # 可观察窗口（mob_obs）之内。后面的 vintage 网格全靠这个不等式来
    # 判断"这一格到底看不看得见"。
    r = con.execute("""
        SELECT SUM(CASE WHEN mob_event > mob_obs THEN 1 ELSE 0 END) AS 越界,
               SUM(CASE WHEN mob_obs < 0 THEN 1 ELSE 0 END) AS 负账龄,
               MAX(mob_obs) AS 最大可观察账龄, MIN(mob_obs) AS 最小可观察账龄
        FROM loans
    """).fetchdf().iloc[0]
    add('事件账龄 ≤ 可观察账龄（vintage 网格的可观察判据）',
        r['越界'] == 0 and r['负账龄'] == 0,
        f"越界 {r['越界']:,} 笔，负账龄 {r['负账龄']:,} 笔，"
        f"可观察账龄范围 {r['最小可观察账龄']} ~ {r['最大可观察账龄']} 个月")

    print('\n═══ 防泄漏 ═══')

    # ── 11. 特征表与"不可用字段"名单交集必须为空 ──
    if os.path.exists(db.FEATURES_PQ):
        cols = [c[0] for c in con.execute(
            f"DESCRIBE SELECT * FROM '{db.FEATURES_PQ}'").fetchall()]
        hits = sorted({c for c in cols if c in db.UNUSABLE_AS_FEATURE})
        add('特征表列名与"不可用字段"名单交集为空', not hits,
            f'{len(cols)} 列，命中 {hits if hits else "（无）"}'
            f'（名单 = LEAKY {len(db.LEAKY)} 项 + COHORT_BLIND {len(db.COHORT_BLIND)} 项）')
    else:
        add('特征表列名与"不可用字段"名单交集为空', False, f'{db.FEATURES_PQ} 还不存在')

    # ── 12. 两张表行数一致 ──
    # 特征表是主表的一个投影，任何行数差异都意味着 JOIN 或过滤写错了。
    a = con.execute('SELECT COUNT(*) FROM loans').fetchone()[0]
    b = con.execute(f"SELECT COUNT(*) FROM '{db.FEATURES_PQ}'").fetchone()[0]
    add('主表与特征表行数一致', a == b, f'主表 {a:,}，特征表 {b:,}')

    # ── 13. 自发的主键必须唯一 ──
    # ⚠️ 这项检查原本是写成 JOIN ON id 的，那是个真踩过的坑：
    #    LC 公开文件的 id 和 member_id 两列【全部 226 万行都是空的】，
    #    拿 id 做 JOIN 会 join 出零行，然后"不一致笔数 = 0"，
    #    断言绿油油地通过——但它其实什么都没验。
    #    凡是"数差异条数"的断言，都必须同时确认比对了多少行，否则零行比对
    #    和完美一致长得一模一样。这里改成先查 loan_key 唯一性，再按它比对。
    dup = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT loan_key FROM loans GROUP BY 1 HAVING COUNT(*) > 1
        )
    """).fetchone()[0]
    nkey = con.execute('SELECT COUNT(DISTINCT loan_key) FROM loans').fetchone()[0]
    add('自发主键 loan_key 唯一（无标识数据集的替代方案）', dup == 0,
        f'{nkey:,} 个不同 loan_key / {a:,} 行，重复键 {dup:,} 个')

    # ── 14. 标签在两张表里必须一致 ──
    # 特征表是要拿去给模型用的，如果它的 outcome 和主表对不上，
    # 模型学到的就不是我们要它学的东西。
    r = con.execute(f"""
        SELECT COUNT(*) AS 比对行数,
               SUM(CASE WHEN l.outcome IS DISTINCT FROM f.outcome THEN 1 ELSE 0 END) AS 不一致
        FROM loans l JOIN '{db.FEATURES_PQ}' f ON l.loan_key = f.loan_key
    """).fetchdf().iloc[0]
    add('主表与特征表的 outcome 标签一致（按 loan_key 对齐）',
        r['比对行数'] == a and r['不一致'] == 0,
        f'比对上 {r["比对行数"]:,}/{a:,} 行，标签不一致 {r["不一致"]:,} 笔'
        + ('' if r['比对行数'] == a else '　❌ 比对行数不等于总行数，说明有行没对上'))

    # ── 汇总 ──
    n_ok = sum(rows)
    print(f'\n═══ 自检结果：{n_ok}/{len(rows)} 项通过 ═══')
    if n_ok < len(rows):
        print('❌ 有断言没过。不要绕过去继续往下做——')
        print('   这些断言存在的意义，就是在错误还看得见的时候把它拦下来。')
        sys.exit(1)
    print('✅ 全部通过。')


if __name__ == '__main__':
    main()
