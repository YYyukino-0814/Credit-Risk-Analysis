-- sql_01_overview.sql —— 第一步：认识这份数据
--
-- 目的不是"画个图"，而是把后面所有分析要用的【分母】先钉死：
--   这份数据有多少笔、多少钱、什么期限结构、利率什么水平、
--   以及最关键的——【每一年的贷款，我们现在能看到第几个月】。
--
-- 读法提示：
--   结果1 是规模，结果2 是逐年结构，结果3 是【双口径】，
--   结果4 是删失程度（vintage 分析可行性的前提），
--   结果5 是风险分级的规模分布。
--
-- 写 SQL 的两条硬约束（切分器决定，违反会安静地少跑结果集）：
--   不能有行内注释，-- 必须独占一行；字符串里不能出现分号。

-- ── 结果1：全样本一句话概览 ──
-- 这是后面所有比率的统一分母。放款本金合计用 loan_amnt 不用 funded_amnt：
-- loan_amnt 是借款人申请的金额，funded_amnt 是实际放款额，两者在本数据集里
-- 逐笔基本相等，但口径上"放款本金"应该用 funded_amnt。
-- 这里两个都报出来，差异本身就是一条要交代的事。
SELECT COUNT(*)                                        AS 总笔数,
       ROUND(SUM(loan_amnt) / 1e9, 2)                  AS 申请本金_十亿,
       ROUND(SUM(funded_amnt) / 1e9, 2)                AS 实际放款_十亿,
       ROUND(AVG(loan_amnt), 0)                        AS 平均单笔,
       ROUND(MIN(int_rate), 2)                         AS 最低利率,
       ROUND(AVG(int_rate), 2)                         AS 平均利率,
       ROUND(MAX(int_rate), 2)                         AS 最高利率,
       MIN(issue_date)                                 AS 最早放款,
       MAX(issue_date)                                 AS 最晚放款,
       ROUND(100.0 * SUM(CASE WHEN term_m = 60 THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                       AS 六十期占比
FROM loans;

-- ── 结果2：放款年 × 状态结构 ──
-- 未决占比逐年升高 = 右删失存在的第一证据（越近的队列越没来得及走完）。
-- 核销本金是期末口径的绝对额，它在近年变小不代表质量变好，只代表没来得及坏。
SELECT issue_year                                                     AS 放款年,
       COUNT(*)                                                       AS 放款笔数,
       ROUND(SUM(loan_amnt) / 1e6, 1)                                 AS 放款本金_百万,
       SUM(CASE WHEN status_group = '已结清' THEN 1 ELSE 0 END)       AS 已结清,
       SUM(CASE WHEN status_group = '已核销' THEN 1 ELSE 0 END)       AS 已核销,
       SUM(CASE WHEN status_group = '未决'   THEN 1 ELSE 0 END)       AS 未决,
       ROUND(100.0 * SUM(CASE WHEN status_group = '未决' THEN 1 ELSE 0 END)
             / COUNT(*), 1)                                           AS 未决占比,
       ROUND(AVG(int_rate), 2)                                        AS 平均利率,
       ROUND(AVG(loan_amnt), 0)                                       AS 平均单笔,
       ROUND(100.0 * SUM(CASE WHEN term_m = 60 THEN 1 ELSE 0 END)
             / COUNT(*), 1)                                           AS 六十期占比,
       ROUND(SUM(CASE WHEN grade IN ('A', 'B') THEN 1 ELSE 0 END) * 100.0
             / COUNT(*), 1)                                           AS AB级占比
FROM loans
GROUP BY 1
ORDER BY 1;

-- ── 结果3：双口径对照（本项目的核心数据质量限制）──
-- outcome      = 官方状态口径（Fully Paid 算好客户）
-- loss_occurred= 损失口径（本金有没有真的亏掉）
-- 差额集中在 2007-2011，2008 年最大。详见 00_口径与数据说明.md 第四之二节。
-- 两个口径都跑、差异并报，是这一节存在的全部意义。
SELECT issue_year                                                    AS 放款年,
       COUNT(*)                                                      AS 已定标签笔数,
       SUM(CASE WHEN outcome = 1 THEN 1 ELSE 0 END)                  AS 官方核销笔数,
       SUM(loss_occurred)                                            AS 实际损失笔数,
       ROUND(100.0 * SUM(CASE WHEN outcome = 1 THEN 1 ELSE 0 END)
             / COUNT(*), 2)                                          AS 官方核销率,
       ROUND(100.0 * SUM(loss_occurred) / COUNT(*), 2)               AS 含损失率,
       ROUND(100.0 * SUM(loss_occurred) / COUNT(*)
             - 100.0 * SUM(CASE WHEN outcome = 1 THEN 1 ELSE 0 END)
             / COUNT(*), 2)                                          AS 差额pp
FROM loans
WHERE outcome IS NOT NULL
GROUP BY 1
ORDER BY 1;

-- ── 结果4：删失程度（vintage 分析可行性的前提）──
-- mob_obs = 该笔贷款从放款到快照日能观察到第几个月。
-- 这一列决定 vintage 网格里哪一格能发、哪一格必须空着。
-- 只要【最年轻队列】的 mob_obs 还够得着目标账龄，这个账龄就对全部队列都可用。
-- 实测最年轻队列（2018Q4）的 mob_obs = 44，所以 24 期和 36 期的
-- 固定账龄对比对全样本都成立，这就是后面 vintage 网格的地基。
SELECT issue_year                                            AS 放款年,
       COUNT(*)                                              AS 笔数,
       MIN(mob_obs)                                          AS 最短可观察账龄,
       ROUND(AVG(mob_obs), 1)                                AS 平均可观察账龄,
       MAX(mob_obs)                                          AS 最长可观察账龄,
       SUM(CASE WHEN mob_obs >= 24 THEN 1 ELSE 0 END)        AS 够得着24期,
       SUM(CASE WHEN mob_obs >= 36 THEN 1 ELSE 0 END)        AS 够得着36期,
       SUM(CASE WHEN mob_obs >= 60 THEN 1 ELSE 0 END)        AS 够得着60期
FROM loans
GROUP BY 1
ORDER BY 1;

-- ── 结果5：风险分级 × 期限的规模与定价 ──
-- grade 是 LC 放款时定的风险等级，替代 FICO 做本项目的主风险轴
-- （该数据集【没有 FICO 列】，已实测确认，见阶段3 的字段存在性校验）。
-- 严格单调的利率是"这个字段可信"的最朴素检验（自检第 8 项）。
SELECT grade                                                   AS 信用等级,
       term_m                                                  AS 期限,
       COUNT(*)                                                AS 笔数,
       ROUND(AVG(int_rate), 2)                                 AS 平均利率,
       ROUND(AVG(loan_amnt), 0)                                AS 平均单笔,
       ROUND(100.0 * SUM(CASE WHEN outcome = 1 THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN outcome IS NOT NULL THEN 1 ELSE 0 END), 0), 2)
                                                               AS 官方核销率,
       ROUND(100.0 * SUM(loss_occurred)
             / NULLIF(SUM(CASE WHEN outcome IS NOT NULL THEN 1 ELSE 0 END), 0), 2)
                                                               AS 含损失率
FROM loans
GROUP BY 1, 2
ORDER BY 1, 2;
