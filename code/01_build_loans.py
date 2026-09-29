# -*- coding: utf-8 -*-
"""
01_build_loans.py — 建库：Lending Club 原始 csv → parquet

输入：data/raw/LoanStats*.csv.zip      原始下载件（只读不改）
输出：data/clean/loans_raw.parquet     全列无损缓存（全 VARCHAR）
      data/clean/loans.parquet         【分析主表】精选列 + 派生列
      data/clean/loans_features.parquet【防泄漏】只含放款前字段
      output/tables/*.csv             体检结果

分五个阶段，每阶段幂等（产物已存在就跳过），可以中断重跑。

── CSV 的三个格式坑（已实测，不处理必崩）────────────────────────
1) 第 1 行是法务声明 "Notes offered by Prospectus (https://...)"，
   【第 2 行才是表头】，数据从第 3 行起。所以 read_csv 要 skip=1。
2) 文件末尾有两行汇总垃圾：
       Total amount funded in policy code 1: 460296150
       Total amount funded in policy code 2: 0
   不清掉会被当成数据行，类型推断直接崩。
3) 所有列都是字符串：int_rate = "10.65%"、term = " 36 months"（带前导空格）、
   issue_d = "Dec-2011"、emp_length = "10+ years"。
   所以【先全 VARCHAR 落一遍 parquet】，所有类型转换集中在阶段 3 一处做，
   报错只在一个地方报，不会散落在十几个脚本里。

── 为什么不抽样 ────────────────────────────────────────────
淘宝项目抽 10% 是因为有 1 亿行。这份数据 226 万行 × ~150 列，
DuckDB 内存里直接跑得动，全量进主表。
"""
import csv
import os
import sys
import glob
import time
import hashlib
import zipfile

import duckdb

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

RAW_DIR = db.path('data', 'raw')
RAW_PQ = db.path('data', 'clean', 'loans_raw.parquet')
MAIN_PQ = db.path('data', 'clean', 'loans.parquet')
FEATURES_PQ = db.path('data', 'clean', 'loans_features.parquet')
TABLES = db.TABLES


def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


# ──────────────────────────────────────────────────────────── 幂等判据
# 刚开始只拿"源文件清单"当判据：清单没变就跳过。这拦得住"数据没到齐就建库"，
# 但拦不住一个更阴的情况——【改了建库脚本本身，产物却没重建】。
#
# 实测踩到过：给 lgd_net 加了 [0,1] 截断，重跑脚本，日志打印"阶段3 跳过"，
# 主表里还是旧的未截断版本。脚本绿油油地跑完，数据却没变——如果没注意到
# 那行"跳过"，后面所有用到 lgd_net 的分析都会基于旧口径，而且不报任何错。
#
# 所以判据里必须带上【脚本自己的指纹】：脚本或 db.py 一改，产物就作废重算。
# db.py 也要算进去，因为泄漏黑名单定义在它里面——改黑名单必须让特征表重建。
def _code_fingerprint():
    h = hashlib.sha256()
    for p in (os.path.abspath(__file__), os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db.py')):
        with open(p, 'rb') as f:
            h.update(f.read())
    return h.hexdigest()[:16]


def _stamp_text():
    """产物的"出生证明"：源文件清单 + 建库代码指纹。"""
    src = open(RAW_PQ + '.sources.txt', encoding='utf-8').read().strip()
    return f'{src}\n# code_fingerprint={_code_fingerprint()}'


def _up_to_date(target):
    """产物存在，且出生证明与当前状态一致，才算"最新"。"""
    stamp = target + '.stamp'
    if not (os.path.exists(target) and os.path.exists(stamp)):
        return False
    try:
        return open(stamp, encoding='utf-8').read().strip() == _stamp_text()
    except OSError:
        return False


def _write_stamp(target):
    with open(target + '.stamp', 'w', encoding='utf-8') as f:
        f.write(_stamp_text())


def stage0_extract():
    """解压所有 LoanStats*.csv.zip。已解压过的跳过。"""
    zips = sorted(glob.glob(os.path.join(RAW_DIR, 'LoanStats*.csv.zip')))
    if not zips:
        raise SystemExit(f'❌ {RAW_DIR} 下没有 LoanStats*.csv.zip，先去下载')

    log(f'阶段0 解压：找到 {len(zips)} 个 zip')
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            for info in zf.infolist():
                out = os.path.join(RAW_DIR, info.filename)
                if os.path.exists(out) and os.path.getsize(out) == info.file_size:
                    continue
                log(f'  解压 {info.filename}（{info.file_size/1048576:.1f} MB）')
                zf.extract(info, RAW_DIR)
    csvs = sorted(glob.glob(os.path.join(RAW_DIR, 'LoanStats*.csv')))
    log(f'  待入库 csv：{len(csvs)} 个')
    return csvs


def stage1_raw_parquet(csvs):
    """全列 VARCHAR 落一份无损 parquet。只在这里解析一次 csv，之后都读 parquet。

    这里开了 ignore_errors：不让一两行垃圾把整个读入顶崩。但光开它，
    被丢掉的行是【静默】的——丢了多少、丢的是什么，全不知道。

    原本想用 DuckDB 的 store_rejects 把跳过的行记下来，实测不行：
    REJECTS_TABLE 和 UNION_BY_NAME 不能同时用（各期文件列不完全一致，
    union_by_name 是必须的）。于是改成更强的做法——下面用 Python 的 csv
    模块【独立复算一遍】：它是跟 DuckDB 完全不同的一个解析器，
    两边对上了才说明真没丢数据，这比让 DuckDB 自己交代自己更有说服力。
    """
    # 防呆：不能只看 parquet 在不在就跳过。今天只有 2 个源文件时跑通了，
    # 明天 16 个文件到齐再跑，若无脑跳过，就会拿一份残缺数据做完全部分析还不报错。
    # 所以把"这份 parquet 是用哪些源文件、多少行建的"记在清单里，对不上就重建。
    manifest = RAW_PQ + '.sources.txt'
    want = '\n'.join(os.path.basename(p) for p in csvs)
    if os.path.exists(RAW_PQ) and os.path.exists(manifest):
        if open(manifest, encoding='utf-8').read().strip() == want.strip():
            log(f'阶段1 跳过（{os.path.basename(RAW_PQ)} 已存在，'
                f'且源文件清单与当前 {len(csvs)} 个文件一致）')
            return
        log(f'阶段1 源文件清单变了（清单记录 vs 当前 {len(csvs)} 个），重建 parquet')
    elif os.path.exists(RAW_PQ):
        log('阶段1 有 parquet 但没有源文件清单，来路不明，重建')

    log(f'阶段1 读 {len(csvs)} 个 csv 落 {os.path.basename(RAW_PQ)}（全 VARCHAR）...')
    con = duckdb.connect()
    # 路径列表直接喂给 read_csv
    files = ', '.join(f"'{p.replace(chr(92), '/')}'" for p in csvs)
    con.execute(f"""
        COPY (
            SELECT * FROM read_csv(
                [{files}],
                skip=1,              -- 跳过第 1 行法务声明，第 2 行当表头
                all_varchar=true,    -- 全按字符串读，避免 % / " months" / Dec-2011 让推断崩
                header=true,
                union_by_name=true,  -- 各期文件列不完全一样，按列名对齐
                filename=true,       -- 记下每行来自哪个文件，用来查各期年份有没有重叠
                ignore_errors=true   -- 第 3 个坑：行中间夹着 "Loans that do not meet the credit policy"
            )
            WHERE loan_status IS NOT NULL
              AND loan_status <> 'loan_status'   -- 防某个文件中间重复了一次表头
        ) TO '{RAW_PQ}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    n = con.execute(f"SELECT COUNT(*) FROM '{RAW_PQ}'").fetchone()[0]
    log(f'  完成：{n:,} 行')

    # ── 独立复算：用 Python csv 模块从源文件数一遍，和 DuckDB 的结果对账 ──
    # 用 csv 模块数【记录数】而不是数物理行：desc / emp_title 这类字段里可能
    # 自带换行，按行数会把一条记录数成两条，对账就假报警。csv 模块按引号规则
    # 切分，才是和 DuckDB 同一个口径。
    # 三类行分开数，且每一类都打印原文——跳过的必须是垃圾行，不能混进真数据。
    print('\n  独立复算对账（Python csv 模块 vs DuckDB，防"丢了数据还不知道"）：')
    all_ok = True
    for p in csvs:
        with open(p, encoding='utf-8', errors='replace') as f:
            rows = list(csv.reader(f))
        body = rows[2:]                       # 第 1 行法务声明、第 2 行表头，都去掉
        ncol = len(rows[1])
        si = rows[1].index('loan_status')
        short, dup_hdr, good = [], [], 0
        for rec in body:
            if len(rec) != ncol:
                short.append(rec)
            elif rec[si] in ('', 'loan_status'):
                dup_hdr.append(rec)
            else:
                good += 1
        kept = con.execute(
            f"SELECT COUNT(*) FROM '{RAW_PQ}' WHERE filename = '{p.replace(chr(92), '/')}'"
        ).fetchone()[0]
        ok = good == kept
        all_ok &= ok
        print(f'    {os.path.basename(p):<30s} 源文件 {len(body):>7,} 条'
              f' − 列数不对 {len(short):>3d} − 重复表头/空状态 {len(dup_hdr):>3d}'
              f' = 有效 {good:>7,}'
              f' | parquet {kept:>7,}  | {"✅" if ok else "❌ 对不上，要查"}')
        for rec in short + dup_hdr:
            head = (rec[0] if rec else '')[:80]
            print(f'        跳过：{head!r}')
    print(f'    总结论：{"✅ 两边完全一致，没有看不见的数据损失" if all_ok else "❌ 有出入，先查清楚再往下做"}')

    with open(manifest, 'w', encoding='utf-8') as f:
        f.write(want + '\n')
    log(f'  已记源文件清单 {os.path.basename(manifest)}（{len(csvs)} 个文件）')


def stage2_diagnose(con):
    """阶段2 体检——这里要出计划里 D1 的四个待实测未知量。"""
    log('阶段2 体检')
    con.execute(f"CREATE OR REPLACE VIEW r AS SELECT * FROM '{RAW_PQ}'")

    cols = [c[0] for c in con.execute("DESCRIBE r").fetchall()]
    n = con.execute('SELECT COUNT(*) FROM r').fetchone()[0]
    log(f'  列数 {len(cols)}，行数 {n:,}')
    print('\n===== 全部列名 =====')
    for i in range(0, len(cols), 6):
        print('  ' + '  '.join(f'{c:<28s}' for c in cols[i:i + 6]))

    print('\n===== 未知量1：各文件的年份覆盖（查有没有重叠，重叠了要按 id 去重）=====')
    print(con.execute("""
        SELECT regexp_extract(filename, 'LoanStats[^/]*') AS 来源文件,
               SUBSTR(issue_d, -4) AS 放款年,
               COUNT(*) AS 笔数
        FROM r
        WHERE issue_d IS NOT NULL
        GROUP BY 1, 2 ORDER BY 1, 2
    """).fetchdf().to_string(index=False))

    # ⚠️ 字符串不能直接 MAX：last_credit_pull_d 形如 "Dec-2011"，
    #    按字典序比大小会得出 "Sep-2018" > "Dec-2019" 这种荒谬结论。
    #    必须先用 strptime 解释成真正的日期再取最大值。
    print('\n===== 未知量2：数据快照日（整个项目的时间原点，错了全盘皆错）=====')
    print(con.execute("""
        SELECT MAX(strptime(last_credit_pull_d, '%b-%Y')) AS 征信最后拉取,
               MAX(strptime(last_pymnt_d,       '%b-%Y')) AS 最后一笔还款,
               MAX(strptime(issue_d,            '%b-%Y')) AS 最后一笔放款
        FROM r
    """).fetchdf().to_string(index=False))

    # ⚠️⚠️ 上面这个 MAX 里藏着本项目最阴的一个坑，两个字段会给出两个不同的答案：
    #   · last_credit_pull_d 的 MAX = 2023-07，但它是【干扰项】：
    #       (a) 它是每笔贷款各自最后一次拉征信的日期，不是数据集的编译日；
    #       (b) LC 在 2021-03 做过一次批量征信刷新（321,003 笔挤在同一个月），
    #           会把"最大拉取日"整个带偏；
    #       (c) 2023 年的拉取记录只出现在 LoanStats3a 这一个文件里——
    #           那是 LC 早期文件被单独刷新过，而它装的是 2007-2011 年的贷款，
    #           早在 2016 年前就全部结清，刷新与否不影响任何结果。
    #   · last_pymnt_d 的 MAX = 2022-08，这才是【真答案】。
    # 下面这个查询是决定性证据：仍未结清的贷款中，绝大多数的最后一笔还款
    # 落在 2022-08，之后断崖——说明文件是在 2022 年 8 月之后不久编译封存的。
    print('\n  —— 决定性证据：仍未结清的贷款，最后一笔还款落在哪个月 ——')
    print('     （未结清的贷款一直在按月还款，它们集体停在哪个月，数据就封存在哪个月）')
    print(con.execute("""
        SELECT strftime(strptime(last_pymnt_d, '%b-%Y'), '%Y-%m') AS 年月,
               COUNT(*) AS 笔数
        FROM r
        WHERE TRY_CAST(out_prncp AS DOUBLE) > 0 AND last_pymnt_d IS NOT NULL
        GROUP BY 1 ORDER BY 1 DESC LIMIT 10
    """).fetchdf().to_string(index=False))
    print('  → 快照日取 2022-08-31（db.SNAPSHOT 已按此设定）')

    print('\n  —— 各文件自己的最后还款月（确认没有哪个文件的封存日更晚）——')
    print(con.execute("""
        SELECT regexp_extract(filename, 'LoanStats[^/]*') AS 来源文件,
               strftime(MAX(strptime(last_pymnt_d, '%b-%Y')), '%Y-%m') AS 最后还款月,
               strftime(MAX(strptime(issue_d,      '%b-%Y')), '%Y-%m') AS 最后放款月,
               COUNT(*) AS 笔数
        FROM r GROUP BY 1 ORDER BY 1
    """).fetchdf().to_string(index=False))

    print('\n===== 未知量3：账务恒等式（Charged Off 的 out_prncp 是不是 0）=====')
    print(con.execute("""
        SELECT loan_status AS 状态,
               COUNT(*) AS 笔数,
               SUM(CASE WHEN TRY_CAST(out_prncp AS DOUBLE) = 0 THEN 1 ELSE 0 END) AS 未还本金为0,
               SUM(CASE WHEN TRY_CAST(out_prncp AS DOUBLE) > 0 THEN 1 ELSE 0 END) AS 未还本金大于0,
               ROUND(AVG(TRY_CAST(REPLACE(int_rate,'%','') AS DOUBLE)), 2) AS 平均利率
        FROM r
        WHERE loan_status IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC
    """).fetchdf().to_string(index=False))

    # date_diff('month', 起, 止)：DuckDB 没有 months_between（Postgres 的写法）
    print('\n===== 未知量4：核销滞后（放款 → 最后一笔还款，隔了多少个月）=====')
    lag = con.execute("""
        SELECT date_diff('month',
                   strptime(issue_d,      '%b-%Y'),
                   strptime(last_pymnt_d, '%b-%Y')) AS 距放款月数,
               COUNT(*) AS 笔数
        FROM r
        WHERE loan_status LIKE 'Charged Off%'
          AND last_pymnt_d IS NOT NULL AND issue_d IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """).fetchdf()
    print(lag.to_string(index=False))
    tot = lag['笔数'].sum()
    p90 = lag[lag['笔数'].cumsum() >= tot * 0.9]['距放款月数'].min()
    print(f'  → 坏账的"最后一笔还款"距放款：中位数 {lag[lag["笔数"].cumsum() >= tot*0.5]["距放款月数"].min():.0f} 个月，'
          f'90% 分位 {p90:.0f} 个月')
    print('  ⚠️ 这不是违约日。违约发生在最后一笔还款【之后】，真实核销滞后更长，')
    print('     所以后面算账龄时要承认：曲线的尾部会被这个滞后系统性截短。')

    print('\n===== 关键字段缺失率 =====')
    keys = ['loan_amnt', 'funded_amnt', 'term', 'int_rate', 'installment', 'grade',
            'sub_grade', 'emp_length', 'home_ownership', 'annual_inc',
            'verification_status', 'loan_status', 'purpose', 'addr_state', 'dti',
            'delinq_2yrs', 'fico_range_low', 'fico_range_high', 'revol_util',
            'total_acc', 'open_acc', 'pub_rec', 'mort_acc',
            'total_pymnt', 'total_rec_prncp', 'recoveries', 'out_prncp',
            'last_pymnt_d', 'total_bal_ex_mort', 'tot_cur_bal', 'num_tl_120dpd_2m']
    parts = [f"SELECT '{k}' AS 字段, COUNT({k}) AS 非空, COUNT(*) AS 总数 FROM r"
             for k in keys if k in cols]
    print(con.execute(' UNION ALL '.join(parts)).fetchdf()
          .assign(缺失率=lambda d: ((1 - d['非空'] / d['总数']) * 100).round(2))
          .to_string(index=False))

    stage_leak_scan(con, cols)


def stage_leak_scan(con, cols):
    """让数据自己招供哪些字段是"后来才有的"。

    起因：体检时发现 mort_acc / tot_cur_bal / total_bal_ex_mort 三个字段的缺失率
    精确地等于 42,535/268,801 = 15.82% —— 恰好是 3a 那个文件的行数占比。
    也就是说这三个字段在最早期的文件里 100% 为空、在近期文件里全有值。

    这不是巧合。一个"申请时就该有的字段"不可能只在后来的年份才出现。
    一个字段满足"早期vintage全空 + 近期vintage全有"，只有两种解释：
      (a) 它是放款后的某个时点（征信快照 / 账务结果）才产生的值；
      (b) 它是 LC 后来才加入采集范围的新字段——那它在早期数据里必然缺失，
          同样不能当特征用。
    两种解释的结论一样：**不能进特征集**。

    所以与其靠我手写一份黑名单（会漏、会过时），不如直接扫全部 145 列，
    让数据自己把这份名单交出来。实际名单最后与 db.LEAKY 对照，
    对不上的地方打印出来——多出来的说明我漏了，少的说明我多心了。
    """
    print('\n===== 泄漏字段自动扫描（只靠数据，不靠我手写的名单）=====')
    years = con.execute("""
        SELECT MIN(SUBSTR(issue_d,-4)) AS 最早年, MAX(SUBSTR(issue_d,-4)) AS 最晚年
        FROM r WHERE issue_d IS NOT NULL
    """).fetchdf().iloc[0]
    y0, y1 = years['最早年'], years['最晚年']
    print(f'  用 {y0} 年（最早）对比 {y1} 年（最晚）的缺失率')

    # ⚠️ 列名一律用双引号包起来：LC 的列里有 desc、url 这种 SQL 保留字，
    #    不包引号会直接语法报错（desc 是 ORDER BY 的关键词）。
    parts = []
    for c in cols:
        if c in ('filename', 'loan_status'):
            continue
        parts.append(f"""
            SELECT '{c}' AS 字段,
                   AVG(CASE WHEN "{c}" IS NULL OR "{c}" = '' THEN 1.0 ELSE 0.0 END)
                       FILTER (WHERE SUBSTR(issue_d,-4) = '{y0}') AS 早年缺失率,
                   AVG(CASE WHEN "{c}" IS NULL OR "{c}" = '' THEN 1.0 ELSE 0.0 END)
                       FILTER (WHERE SUBSTR(issue_d,-4) = '{y1}') AS 晚年缺失率
            FROM r
        """)
    df = con.execute(' UNION ALL '.join(parts)).fetchdf()
    df['早年缺失率'] = df['早年缺失率'].fillna(-1)
    df['晚年缺失率'] = df['晚年缺失率'].fillna(-1)
    # 按早年缺失率高低分两档报。
    # 100% 缺失 = 当年根本没有这个字段 → 放款后快照；
    # 90%~99% 缺失 = 当年采了但基本没填 → 不是泄漏，是"当年没采集"。
    # 两者都不能当特征，但【原因不同】，必须分开讲，不能混为一谈。
    def _m(c, col):
        return df.loc[df['字段'] == c, col].iloc[0]

    # 判据只看【早年缺失率】，不再附加"晚年缺失要低"这个条件。
    # 原因是吃过一次亏：快照族里有几条（mths_since_recent_inq /
    # mths_since_recent_revol_delinq 等）在近期年份也是大面积空的——
    # 因为 borrowers 没有近期查询记录时这个字段本来就是空，属于【结构性缺失】。
    # 附加"晚年缺失 < 10%"会把它们整批漏掉，而且漏得悄无声息。
    # 而"某一年里一列全空"本身就是充分证据：那一年压根没有这个字段。
    suspect = df[df['早年缺失率'] > 0.9].sort_values(
        ['早年缺失率', '字段'], ascending=[False, True])

    tier1 = [c for c in suspect['字段'] if _m(c, '早年缺失率') >= 0.999]
    tier2 = [c for c in suspect['字段'] if _m(c, '早年缺失率') < 0.999]

    print(f'\n  【档一】早年 100% 缺失、近年几乎全有 —— 放款后才产生的快照或结果：'
          f'{len(tier1)} 个')
    for c in tier1:
        tag = '已在 LEAKY' if db.is_leaky(c) else '★★ LEAKY 里没有，要补'
        print(f'    {c:<40s} 早年 {_m(c,"早年缺失率")*100:5.1f}%  '
              f'晚年 {_m(c,"晚年缺失率")*100:5.1f}%   {tag}')

    print(f'\n  【档二】早年基本缺失、近年才有 —— 不是泄漏，是当年没采集：{len(tier2)} 个')
    for c in tier2:
        tag = ('已在 COHORT_BLIND' if c in db.COHORT_BLIND
               else ('在 LEAKY' if db.is_leaky(c) else '★★ 两个名单都没有，要判'))
        print(f'    {c:<40s} 早年 {_m(c,"早年缺失率")*100:5.1f}%  '
              f'晚年 {_m(c,"晚年缺失率")*100:5.1f}%   {tag}')

    missed = [c for c in suspect['字段'] if not db.is_leaky(c)]
    print(f'\n  ① 扫出来但我两个名单里都没有的：{missed if missed else "（无）"}')
    print('     → 逐个判断：是放款后快照（进 LEAKY），还是当年没采集（进 COHORT_BLIND）。')
    print('       两种都不能进特征集，但理由不同，混着说等于没想清楚。')
    extra = [t for t in db.LEAKY if t.endswith('_')
             and not any(str(c).startswith(t) for c in cols)]
    print(f'  ② 我黑名单里写了、但数据里根本没这种前缀的：{extra if extra else "（无）"}')
    print('     → 属于"多心了"，不影响正确性，可以精简掉。')
    df.to_csv(f'{TABLES}/leak_scan.csv', index=False, encoding='utf-8-sig')
    print(f'\n  完整对比已存 output/tables/leak_scan.csv')


# ══════════════════════════════════════════════════════════════════
# 字段角色总表 —— 全项目"哪个字段是什么角色"的唯一权威定义
# ══════════════════════════════════════════════════════════════════
# 三种角色，泾渭分明：
#   放款前 · 申请那一刻就确定   → 可以当特征
#   放款后 · 结果与损失         → 只能当分子/标签，进特征就是数据泄漏
#   放款后 · 征信快照（最阴）   → 名单由 stage_leak_scan 从数据里扫出来，见 db.LEAKY

# ── 放款前：分类特征 ──
FEAT_TEXT = ['grade', 'sub_grade', 'emp_title', 'emp_length', 'home_ownership',
             'verification_status', 'purpose', 'title', 'zip_code', 'addr_state',
             'application_type', 'initial_list_status']

# ── 放款前：数值特征 ──
FEAT_NUM = ['loan_amnt', 'funded_amnt', 'funded_amnt_inv', 'installment', 'annual_inc',
            'dti', 'delinq_2yrs',
            # ⚠️ 这里原本还写着 fico_range_low / fico_range_high，实测【这两列不存在】。
            #    LC 官网公布的 LoanStats 文件里没有 FICO 分数（我一开始是按数据字典
            #    想当然写的，没有实测——正是本项目反复在防的那种错误）。
            #    没有 FICO 不影响分析：grade / sub_grade 是 LC 自己按风险给的分级，
            #    在放款那一刻就定了，做风险分群比 FICO 更贴业务。
            'inq_last_6mths', 'mths_since_last_delinq', 'mths_since_last_record',
            'open_acc', 'pub_rec', 'revol_bal', 'revol_util', 'total_acc',
            'pub_rec_bankruptcies', 'tax_liens']

# ── 放款后：还款与损失的结果字段（是合法的分子，是非法的特征）──
OUT_NUM = ['out_prncp', 'total_pymnt', 'total_rec_prncp', 'total_rec_int',
           'total_rec_late_fee', 'recoveries', 'collection_recovery_fee',
           'last_pymnt_amnt']

# ── 放款后：日期 ──
OUT_DATE = ['last_pymnt_d', 'next_pymnt_d', 'last_credit_pull_d']


def _num(c):
    """数值列转换：LC 的数值列全是字符串，空串要变成 NULL 而不是 0。"""
    return f'TRY_CAST(NULLIF(TRIM("{c}"), \'\') AS DOUBLE) AS "{c}"'


def _pct(c):
    """百分比列：int_rate 是 " 8.07%"，去掉百分号再转数。"""
    return f'TRY_CAST(REPLACE(TRIM("{c}"), \'%\', \'\') AS DOUBLE) AS "{c}"'


def _mon(c):
    """月份列：issue_d 是 "Dec-2011"，解析成当月 1 号的 DATE。
       不解析的话它是字符串，MAX() 会按字典序比大小，静默给出错误答案。

       列名去掉尾部的 _d 再加 _date：issue_d → issue_date、
       last_pymnt_d → last_pymnt_date。比 issue_d_date 好读。
    """
    base = c[:-2] if c.endswith('_d') else c
    return f'TRY_CAST(strptime(TRIM("{c}"), \'%b-%Y\') AS DATE) AS "{base}_date"'


# 状态归并：LC 的 loan_status 有 7 种，另外加两条历史变体。
# 「Does not meet the credit policy. Status:X」是被拒之后又被放款的边缘客群，
# 必须显式映射回 X——漏掉它们会系统性低估 2007-2013 的损失，
# 而且会以莫名其妙的第三类出现在图上。
STATUS_CASE = """
    CASE
        WHEN loan_status LIKE 'Fully Paid%'                              THEN '已结清'
        WHEN loan_status LIKE 'Does not meet the credit policy. Status:Fully Paid'      THEN '已结清'
        WHEN loan_status IN ('Charged Off', 'Default')                   THEN '已核销'
        WHEN loan_status LIKE 'Does not meet the credit policy. Status:Charged Off'     THEN '已核销'
        WHEN loan_status LIKE 'Does not meet the credit policy. Status:Default'         THEN '已核销'
        ELSE '未决'
    END
"""


def stage3_build_main(con):
    """建【分析主表】loans.parquet：精选列 + 派生列。

    这里集中做所有类型转换。源 CSV 里全是字符串（" 8.07%"、" 36 months"、
    "Dec-2011"），如果散在十几个脚本里各转各的，出错也会散在十几个地方。
    """
    if _up_to_date(MAIN_PQ):
        log(f'阶段3 跳过（{os.path.basename(MAIN_PQ)} 已是最新）')
        return

    log(f'阶段3 建分析主表 {os.path.basename(MAIN_PQ)} ...')

    # ── 先核一遍字段清单，缺哪个一次说清楚 ──
    # 这道检查是被 FICO 那次教训加的：我按 Lending Club 的数据字典写了
    # fico_range_low / fico_range_high，一直没验，直到建表时 SQL 深处才报
    # "列不存在"，而且报的是个很难懂的绑定错误。与其在深处炸，不如在这里
    # 把不存在的列一次性列出来——顺手也防住了拼写错误。
    raw_cols = {c[0] for c in con.execute(
        f"DESCRIBE SELECT * FROM '{RAW_PQ}'").fetchall()}
    want = set(FEAT_TEXT + FEAT_NUM + OUT_NUM + OUT_DATE
               + ['issue_d', 'earliest_cr_line', 'loan_status', 'term', 'emp_length'])
    missing = sorted(want - raw_cols)
    if missing:
        raise SystemExit(
            f'❌ 字段清单里这些列在原始数据里不存在：{missing}\n'
            f'   要么是拼错了，要么这份文件根本没有这一列——\n'
            f'   别照着数据字典想当然，先 DESCRIBE 一下。')

    # ⚠️ 两个空列，别去找它们：id 和 member_id 在全部 226 万行里【一列全空】。
    #    Lending Club 的公开文件出于隐私考虑把这两列整列抹掉了。
    #    后果：这份数据没有任何唯一标识——
    #      · 不能按 id 去重（所幸 16 个文件的年份互不重叠，本来也不需要去重）
    #      · 不能跟任何外部数据关联
    #      · 写自检时【不能 JOIN ON id】，那样会 join 出零行、断言假通过
    #        （本项目真踩过这个坑，见 00_selfcheck.py 第 13 项）
    #    所以下面自己造一个 loan_key：把几个足以区分一笔贷款的业务字段
    #    拼起来取哈希。两笔不同贷款在这些字段上全部相同的概率可以忽略。
    # ── 内层：只做类型转换 ──
    # LC 的 CSV 全是字符串，这一步把 " 8.07%"、"Dec-2011" 这类转成真正的数值和日期。
    # 单独拆一层是因为：同层 SELECT 里，后面引用的名字会被前面的【别名截胡】——
    # 比如把 loan_amnt 转成数值并起名叫 loan_amnt 之后，同一层里再写 loan_amnt
    # 指的就不再是原始字符串列了，DuckDB 直接报"引用了尚未定义的列"。
    # 拆成两层，这类问题整类消失。
    inner = ['regexp_extract(filename, \'LoanStats[^/]*\') AS "src_file"']
    inner += [_pct(c) for c in ['int_rate', 'revol_util']]
    # revol_util 既在 FEAT_NUM 里又要按百分比解析，所以先排掉，避免重复定义列名
    inner += [_num(c) for c in FEAT_NUM + OUT_NUM if c not in ('revol_util',)]
    inner += [_mon(c) for c in ['issue_d', 'earliest_cr_line'] + OUT_DATE]
    inner += [f'"{c}"' for c in FEAT_TEXT]
    inner += [
        '"loan_status"',
        'TRY_CAST(regexp_extract("term", \'(\\d+)\', 1) AS INT) AS "term_m"',
        # emp_length = "< 1 year" / "10+ years" / "n/a" → 年数。
        # "< 1 year" 抽出来是 1，其实该是 0 到 1 之间，当作 1 处理，口径文档已注明。
        'TRY_CAST(regexp_extract("emp_length", \'(\\d+)\', 1) AS INT) AS "emp_years"',
    ]

    # ── 外层：做派生 ──
    # loan_key 用【转换后】的列拼，避免依赖原始字符串格式
    key_fields = ['loan_amnt', 'funded_amnt', 'installment', 'int_rate', 'annual_inc',
                  'dti', 'grade', 'sub_grade', 'purpose', 'zip_code', 'emp_length',
                  'term_m', 'issue_date']
    key_expr = ('md5(concat_ws(\'|\', src_file, '
                + ', '.join(f'"{c}"' for c in key_fields) + ')) AS "loan_key"')

    outer = [
        '*', key_expr,
        # ── 队列标识：常用到，直接在主表里建好，免得每个 SQL 各算一遍 ──
        'YEAR(issue_date) AS "issue_year"',
        'date_trunc(\'quarter\', issue_date)::DATE AS "issue_q"',
        """strftime(issue_date, '%Y') || 'Q'
           || CAST(quarter(issue_date) AS VARCHAR) AS "issue_q_label\"""",
        # ── 账龄与可观察性 ──
        # mob_obs：这笔贷款最多能被观察到几个月（放款日 → 快照日）。
        #          它是后面 vintage 网格的"可观察上限"，决定哪一格能发、哪一格必须空着。
        f'date_diff(\'month\', issue_date, {db.SNAPSHOT}) AS "mob_obs"',
        # mob_event：用"最后一笔还款"代理事件时点，距放款几个月。
        # 是【代理】不是真违约日——真违约在最后一笔还款之后，见阶段2实测与口径文档。
        'date_diff(\'month\', issue_date, "last_pymnt_date") AS "mob_event"',
        # ── 状态与标签 ──
        f'{STATUS_CASE} AS "status_group"',
        f'''CASE {STATUS_CASE}
              WHEN '已结清' THEN 0 WHEN '已核销' THEN 1 ELSE NULL END AS "outcome"''',
        # ── 损失拆分 ──
        # 账务恒等式已在阶段2验证：Charged Off 的 out_prncp 一律归零
        # （唯一的 22 个例外全是 Default 状态，核销流程还没走完，
        #   它们满足 total_rec_prncp + out_prncp = loan_amnt 这条更强的恒等式）。
        # 所以净损失可以直接这么写，不必去猜"核销那刻还剩多少本金"。
        'loan_amnt - total_rec_prncp AS "loss_gross"',
        # loss_net 保留原值，【不截断】——它是账实相符的记录，截了就是篡改数据。
        'loan_amnt - total_rec_prncp - recoveries AS "loss_net"',
        # lgd_net 截断到 [0,1]，因为它要拿去算期望损失（PD × LGD × EAD），
        # 负值会在那里变成一个"能倒赚的贷款"，把组合层面的损失算少。
        #
        # 为什么会为负（实测 2,578 笔，占核销的 0.67%）：
        #   实测"本金超收笔数 = 0"，即 total_rec_prncp 从不超过 loan_amnt，
        #   超收全部来自 recoveries。原因是催收按【含利息的总债务】打折回收，
        #   而 total_rec_prncp 只记本金部分，所以回收款会超过剩余本金。
        #   平均超收 2.8%，即单笔层面回收款平均覆盖了 102.8% 的未收本金。
        # 截断表示"这笔贷款没有造成本金损失"——业务上成立，口径上要写明。
        '''GREATEST(0, LEAST(1,
             (loan_amnt - total_rec_prncp - recoveries) / NULLIF(loan_amnt, 0)
           )) AS "lgd_net"''',
        # ── 损失口径的标签（与官方 PD 口径并列的第二把尺子）──
        # 【为什么需要第二把尺子】
        # 实测发现 3,032 笔贷款状态是 Fully Paid（官方口径 = 好客户、PD 记 0），
        # 但本金从未收全、out_prncp 却已归零，净损失合计 955 万元。
        # 已排除债务和解与 hardship（这两类标记全部为 'N'），
        # 最像是 LC 早期的账务销账处理，但【从数据本身无法最终判定】。
        #
        # 危害在于它【不是均匀分布】：几乎全部落在 2007–2011。
        # 实测 2008 年队列官方核销率 20.73%，把这批算上就是 38.15%——
        # 官方口径把金融危机那一年最该冒出来的信号抹掉了一半。
        # 拿官方口径直接画 vintage 曲线，会系统性地把早期队列画得比实际安全。
        #
        # 所以主表【两条标签都给】：outcome 守官方口径（对外数字要和 LC 官方对得上），
        # loss_occurred 守损失口径（有没有真的亏钱）。分析时两个都跑，差异本身就是结论。
        # 未决贷款还没走完，两条都必须是 NULL。
        '''CASE WHEN status_group = '未决' THEN NULL
                 WHEN loan_amnt - total_rec_prncp - recoveries > 0.01 THEN 1
                 ELSE 0 END AS "loss_occurred"''',
    ]

    con.execute(f"""
        COPY (
            SELECT {', '.join(outer)}
            FROM (SELECT {', '.join(inner)} FROM read_parquet('{RAW_PQ}'))
        ) TO '{MAIN_PQ}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    n = con.execute(f"SELECT COUNT(*) FROM '{MAIN_PQ}'").fetchone()[0]
    ncol = len(con.execute(f"DESCRIBE SELECT * FROM '{MAIN_PQ}'").fetchall())
    log(f'  完成：{n:,} 行 × {ncol} 列')
    _write_stamp(MAIN_PQ)


def stage4_build_features(con):
    """建【防泄漏特征表】loans_features.parquet：只含放款前字段。

    这张表存在的全部意义是"物理隔离"。光靠纪律"记得剔除泄漏字段"是靠不住的——
    项目做两周，某天半夜赶进度写个 SQL，脑子一热 FROM loans 把 tot_cur_bal
    拉进特征，谁也不会发现。所以这里把合法特征单独写成一张表，
    要做特征分析就只许 FROM features，从物理上让错误发生不了。

    字段清单不硬编码：从 FEAT_* 组里取，再过一遍 db.is_leaky() 过滤器。
    这样万一泄漏扫描发现我漏了某个字段，只要往黑名单加一条，
    特征表自动跟着变，不会出现"改了名单但特征表没重建"的错配。
    """
    if _up_to_date(FEATURES_PQ):
        log(f'阶段4 跳过（{os.path.basename(FEATURES_PQ)} 已是最新）')
        return

    log(f'阶段4 建防泄漏特征表 {os.path.basename(FEATURES_PQ)} ...')
    keep, leak, blind = [], [], []
    for c in FEAT_TEXT + FEAT_NUM:
        if db.is_leaky(c):
            leak.append(c)
        elif c in db.COHORT_BLIND:
            blind.append(c)
        else:
            keep.append(c)
    if leak:
        log(f'  ⚠️ 被泄漏黑名单拦下：{leak}')
    if blind:
        log(f'  ⚠️ 被"队列相关缺失"名单拦下：{blind}')
        log('     这几个不是泄漏，是当年压根没采集，早期队列大面积缺失。')
        log('     拿它做跨队列模型，模型会从"有没有值"里反推出"这是哪一年"，')
        log('     最后把队列信息当成了信号——原因不同，后果一样，所以同样不能用。')

    # grade / sub_grade 不在这里单列——它们在 FEAT_TEXT 里，会随 keep 一起进来，
    # 再列一次就重复了（parquet 不允许重名列）。
    sel = ['"loan_key"', '"src_file"', '"outcome"', '"issue_date"', '"issue_year"',
           '"issue_q"', '"issue_q_label"', '"term_m"', '"emp_years"',
           '"earliest_cr_line_date"', '"cr_hist_m"']
    sel += [f'"{c}"' for c in keep]

    con.execute(f"""
        COPY (
            SELECT {', '.join(sel)}
            FROM (SELECT *, date_diff('month', earliest_cr_line_date, issue_date)
                             AS "cr_hist_m"
                  FROM '{MAIN_PQ}')
        ) TO '{FEATURES_PQ}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    n = con.execute(f"SELECT COUNT(*) FROM '{FEATURES_PQ}'").fetchone()[0]
    cols = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM '{FEATURES_PQ}'").fetchall()]
    log(f'  完成：{n:,} 行 × {len(cols)} 列（不含任何放款后字段）')

    bad = [c for c in cols if c in db.UNUSABLE_AS_FEATURE]
    if bad:
        raise SystemExit(f'❌ 特征表里混进了不能用的字段 {bad}，停止建表，先查清楚')
    log(f'  自检：{len(cols)} 列与"不可用字段"名单交集为空 ✅')
    _write_stamp(FEATURES_PQ)


def stage5_summary(con):
    """阶段5 出摘要表，作为后续所有分析的起点。"""
    log('阶段5 摘要')
    con.execute(f"CREATE OR REPLACE VIEW loans AS SELECT * FROM '{MAIN_PQ}'")
    print('\n===== 主表概览：放款年 × 状态 =====')
    print(con.execute("""
        SELECT issue_year AS 放款年,
               COUNT(*) AS 总笔数,
               SUM(CASE WHEN status_group='已结清' THEN 1 ELSE 0 END) AS 已结清,
               SUM(CASE WHEN status_group='已核销' THEN 1 ELSE 0 END) AS 已核销,
               SUM(CASE WHEN status_group='未决'   THEN 1 ELSE 0 END) AS 未决,
               ROUND(100.0*SUM(CASE WHEN status_group='未决' THEN 1 ELSE 0 END)/COUNT(*),1) AS 未决占比,
               ROUND(SUM(CASE WHEN status_group='已核销' THEN loan_amnt ELSE 0 END)/1e6,1) AS 核销本金_百万,
               ROUND(AVG(int_rate),2) AS 平均利率
        FROM loans
        GROUP BY 1 ORDER BY 1
    """).fetchdf().to_string(index=False))
    print()
    print('  读法：未决占比逐年升高 = 右删失存在的第一证据。')
    print('  "核销本金"是期末口径的绝对额，它在近年变小不代表质量变好，只代表没来得及坏。')

    # ── 双口径对照：官方 PD 口径 vs 损失口径 ──
    # 这张表每次都打出来，是为了让"两条尺子对不上"这件事一直在眼前。
    # 只跑官方口径的话，2008 年那个最该冒出来的信号会被抹掉一半，而且不报错。
    print('\n===== 双口径对照：官方核销率 vs 实际发生本金损失的比例 =====')
    print(con.execute("""
        SELECT issue_year AS 放款年,
               COUNT(*) AS 已定标签笔数,
               ROUND(100.0*SUM(CASE WHEN outcome=1 THEN 1 ELSE 0 END)/COUNT(*),2) AS 官方核销率,
               ROUND(100.0*SUM(loss_occurred)/COUNT(*),2) AS 含损失率,
               ROUND(100.0*SUM(CASE WHEN loss_occurred=1 AND outcome=0 THEN 1 ELSE 0 END)
                     /COUNT(*),2) AS 差额pp
        FROM loans WHERE outcome IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """).fetchdf().to_string(index=False))
    print()
    print('  读法：差额集中在早年（2007–2011），且 2008 年最大。')
    print('  这批贷款状态是 Fully Paid、out_prncp 已归零，但本金从未收全，')
    print('  已排除债务和解与 hardship（标记全为 N），成因无法从数据本身判定。')
    print('  ⚠️ 影响：官方口径会把 2007–2011 队列画得比实际安全，且恰好是这个方向，')
    print('     所以 vintage 分析必须【两个口径都跑】，差异本身就是一条结论。')


def main():
    os.makedirs(os.path.dirname(RAW_PQ), exist_ok=True)
    os.makedirs(TABLES, exist_ok=True)
    csvs = stage0_extract()
    stage1_raw_parquet(csvs)
    con = duckdb.connect()
    stage2_diagnose(con)
    stage3_build_main(con)
    stage4_build_features(con)
    stage5_summary(con)
    log('阶段 0-5 完成。')


if __name__ == '__main__':
    main()
