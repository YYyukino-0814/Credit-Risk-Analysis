-- sql_03_pricing.sql —— 定价有没有跟上风险
--
-- 【从上一节接过来的问题】
-- sql_02b 证明了：E/F/G 等级的组内违约率涨得比 A/B 快得多
-- （A 只 +0.46pp，F 涨了 +9.97pp）。等级排序还保得住，但风险梯度被拉开了。
-- 那么问题来了：**收的利率跟上了吗？**
--
-- 如果风险涨了 8 个点、利率只涨了 2 个点，那几个等级这几年就是在亏钱放贷。
--
-- 【两个口径，别混用】
--   一阶近似口径：用 24 期违约率 + LGD 算"期望损失率"，和利率直接比。
--                 好处是对全部队列都可用（可观察性有保证）。
--   实际账务口径：用真实的 total_rec_int 和 loss_net 算净收益。
--                 好处是不需要任何模型假设，但【只能用在已走完全周期的队列上】，
--                 近年队列的损失还没出来，算出来会虚高。
--   两个都报，各自的适用范围写在结果标题里。
--
-- 写 SQL 的硬约束：不能有行内注释；字符串里不能出现分号。

-- ── 结果1：各等级的定价 vs 实际风险（24 期口径，全队列可用）──
-- 期望损失率 ≈ 24期违约率 × 该类贷款的平均净损失率。
-- 拿它和平均利率比，看"收的价差"够不够覆盖"预期的损失"。
-- 注意：这是个一阶近似，没考虑资金成本和运营成本，只回答"够不够覆盖损失"。
SELECT l.grade                                                    AS 信用等级,
       l.term_m                                                   AS 期限,
       COUNT(*)                                                   AS 笔数,
       ROUND(AVG(l.int_rate), 2)                                  AS 平均利率,
       ROUND(100.0 * SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= 24
                              THEN 1 ELSE 0 END) / COUNT(*), 3)   AS 二十四期违约率,
       ROUND(AVG(CASE WHEN l.outcome = 1 THEN l.lgd_net END), 4)  AS 平均净损失率,
       ROUND(100.0 * SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= 24
                              THEN 1 ELSE 0 END) / COUNT(*)
             * AVG(CASE WHEN l.outcome = 1 THEN l.lgd_net END), 3) AS 期望损失率,
       ROUND(AVG(l.int_rate)
             - 100.0 * SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= 24
                                THEN 1 ELSE 0 END) / COUNT(*)
             * AVG(CASE WHEN l.outcome = 1 THEN l.lgd_net END), 3) AS 毛价差pp
FROM loans l
WHERE l.mob_obs >= 24
GROUP BY 1, 2
ORDER BY 1, 2;

-- ── 结果2：各队列的实际盈亏（全周期账务口径）──
-- 不依赖任何模型假设：利息是真实收到的，损失是真实发生的。
--
-- ⚠️ 这个口径【只对已经走完全周期的队列有意义】，必须显式标出来。
--    没走完的队列：利息只收了一半、损失还没爆，两个量都被截断，
--    净收益率既可能虚高也可能虚低，和成熟队列不可比。
--    （第一版这里写了"排除未成熟队列"的注释却没真的过滤，2017–2018
--      的 9.40% / 7.31% 混在成熟队列里，看起来像是"近年也很赚钱"。
--      注释和代码不一致是很危险的错，所以改成用一列显式标出来。）
--
-- 成熟判据：该队列里【所有】贷款都已还完 60 期 → MIN(mob_obs) >= 60。
--    用 MIN 不用 AVG：只要队列里有一笔还没走完，整列就不可比。
SELECT l.issue_year                                               AS 放款年,
       COUNT(*)                                                   AS 放款笔数,
       ROUND(SUM(l.loan_amnt) / 1e6, 1)                           AS 放款本金_百万,
       MIN(l.mob_obs)                                             AS 最短可观察账龄,
       CASE WHEN MIN(l.mob_obs) >= 60 THEN '是' ELSE '否（数据不可比）' END
                                                                  AS 已走完全周期,
       ROUND(100.0 * SUM(l.total_rec_int) / SUM(l.loan_amnt), 2)  AS 利息收入率,
       ROUND(100.0 * SUM(l.loss_net) / SUM(l.loan_amnt), 2)       AS 净损失率,
       ROUND(100.0 * (SUM(l.total_rec_int) - SUM(l.loss_net))
             / SUM(l.loan_amnt), 2)                               AS 净收益率
FROM loans l
GROUP BY 1
ORDER BY 1;

-- ── 结果3：各等级的实际盈亏（只取已走完全周期的队列）──
-- 回答一个业务上最直接的问题：哪个等级在赚钱，哪个在亏。
-- 只保留 MIN(mob_obs) >= 60 的队列，理由同结果2——
-- 不然近年未成熟队列的虚高数字会把成熟队列的真实成绩冲淡。
WITH mature AS (
    SELECT issue_year
    FROM loans
    GROUP BY 1
    HAVING MIN(mob_obs) >= 60
)
SELECT l.grade                                                    AS 信用等级,
       COUNT(*)                                                   AS 放款笔数,
       ROUND(AVG(l.int_rate), 2)                                  AS 平均利率,
       ROUND(100.0 * SUM(l.total_rec_int) / SUM(l.loan_amnt), 2)  AS 利息收入率,
       ROUND(100.0 * SUM(l.loss_net) / SUM(l.loan_amnt), 2)       AS 净损失率,
       ROUND(100.0 * (SUM(l.total_rec_int) - SUM(l.loss_net))
             / SUM(l.loan_amnt), 2)                               AS 净收益率,
       ROUND(100.0 * SUM(CASE WHEN l.outcome = 1 THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN l.outcome IS NOT NULL THEN 1 ELSE 0 END), 0), 2)
                                                                  AS 最终核销率
FROM loans l
WHERE l.issue_year IN (SELECT issue_year FROM mature)
GROUP BY 1
ORDER BY 1;

-- ── 结果4：定价缺口 —— 风险涨了多少，利率涨了多少 ──
-- 这是本节的核心表。基准期 2010-2011，看每个等级到 2018 年的变化。
--
-- ⚠️ 【必须经过 LGD 折算，不能把两个 pp 直接相减】
--    第一版写成 "利率涨幅 − 违约率涨幅"，那等于假设违约时本金全损（LGD = 1）。
--    实测净损失率 lgd_net 平均只有 0.55 —— 违约的贷款还能收回四成多。
--    所以违约率涨 1pp，只需要利率涨 0.55pp 就覆盖得住。
--    直接相减会把定价缺口【高估近一倍】，结论就会从"基本跟上了"
--    错判成"严重跟不上"。这是很容易犯、而且不会报错的错。
--
-- 口径说明：
--   期望损失率 = 24期违约率 × 平均净损失率（LGD），是"两年期的累计预期损失"。
--   利率是年化 APR。两者时间口径不同，所以这里【只比较变化量】——
--   基准期和 2018 用同一个 24 期窗口，口径一致，变化量可比。
--   绝不能用这张表的绝对水平去判断赚不赚钱（那是结果2、结果3 的活）。
WITH base AS (
    SELECT grade AS g,
           AVG(int_rate) AS r0,
           100.0 * SUM(CASE WHEN outcome = 1 AND mob_event <= 24 THEN 1 ELSE 0 END)
                 / COUNT(*) AS d0,
           AVG(CASE WHEN outcome = 1 THEN lgd_net END) AS l0
    FROM loans
    WHERE issue_year IN (2010, 2011) AND mob_obs >= 24
    GROUP BY 1
), now AS (
    SELECT grade AS g,
           AVG(int_rate) AS r1,
           100.0 * SUM(CASE WHEN outcome = 1 AND mob_event <= 24 THEN 1 ELSE 0 END)
                 / COUNT(*) AS d1,
           AVG(CASE WHEN outcome = 1 THEN lgd_net END) AS l1
    FROM loans
    WHERE issue_year = 2018 AND mob_obs >= 24
    GROUP BY 1
)
SELECT base.g                                                     AS 信用等级,
       ROUND(base.d0, 2)                                          AS 基准期违约率,
       ROUND(now.d1, 2)                                           AS 二零一八年违约率,
       ROUND(now.d1 - base.d0, 2)                                 AS 违约率涨幅pp,
       ROUND(base.l0, 3)                                          AS 基准期净损失率,
       ROUND(now.l1, 3)                                           AS 二零一八年净损失率,
       ROUND(now.d1 * now.l1 - base.d0 * base.l0, 2)              AS 期望损失涨幅pp,
       ROUND(base.r0, 2)                                          AS 基准期利率,
       ROUND(now.r1, 2)                                           AS 二零一八年利率,
       ROUND(now.r1 - base.r0, 2)                                 AS 利率涨幅pp,
       ROUND(now.r1 - base.r0 - (now.d1 * now.l1 - base.d0 * base.l0), 2)
                                                                  AS 定价缺口pp
FROM base JOIN now ON base.g = now.g
ORDER BY base.g;

-- ── 结果5：各队列的风险与定价走势（看两条线是不是同步）──
-- 把"风险"和"定价"逐年并排放，看它们是不是同涨同跌。
-- 两条线如果长期背离，说明定价机制对风险不敏感。
WITH m AS (
    SELECT 24 AS k
)
SELECT l.issue_year                                               AS 放款年,
       ROUND(AVG(l.int_rate), 3)                                  AS 平均利率,
       ROUND(100.0 * SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= m.k
                              THEN 1 ELSE 0 END) / COUNT(*), 3)   AS 二十四期违约率,
       ROUND(AVG(l.int_rate)
             - 100.0 * SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= m.k
                                THEN 1 ELSE 0 END) / COUNT(*)
             * AVG(CASE WHEN l.outcome = 1 THEN l.lgd_net END), 3) AS 毛价差pp,
       ROUND(AVG(CASE WHEN l.outcome = 1 THEN l.lgd_net END), 4)  AS 平均净损失率
FROM loans l
CROSS JOIN m
WHERE l.mob_obs >= m.k
GROUP BY 1
ORDER BY 1;
