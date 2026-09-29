-- sql_05_actions.sql —— 前面四节的结论，能变成什么动作
--
-- 【这一节和前四节的区别】
-- 前四节回答的是"发生了什么"。这一节回答的是"所以呢"。
-- 判据很硬：一条结论如果换算不出【要动什么、动多少、影响多大盘子】，
-- 它就还只是一个观察，不是一条建议。
--
-- 所以下面每一条都写成同一个形状：
--     缺口（pp） × 敞口（多少本金） = 年化影响（多少钱）
-- 缺口是前面的分析算出来的，敞口和金额是这一节新查的。
--
-- 【三条行动建议的出处】
--   行动1 · 给 B/C 级补价        —— 来自 sql_03 结果4（B 缺口 −0.74pp）
--   行动2 · 给 60 期加期限价     —— 来自 sql_02 结果7 + sql_03 结果1
--   行动3 · 把借款用途纳入规则   —— 来自 sql_04 结果2（用途是等级的放大器）
--
-- ⚠️ 金额全部是【年化一阶近似】，不是真实利润预测。
--    毛价差本身就是"利率 − 期望损失率"的近似，不含资金成本、运营成本、
--    催收成本，也不含提前还款。它回答的是"缺口有多大"，
--    不是"照做就能多赚这么多"。引用时必须带上这句。
--
-- 写 SQL 的硬约束：不能有行内注释；字符串里不能出现分号。

-- ── 结果1：行动1 的靶子 —— 各等级的定价缺口与敞口 ──
-- 缺口直接引用 sql_03 结果4 的口径（2018 相对 2010-2011），
-- 这里只补上 sql_03 没有的那一半：每个等级到底有多少本金。
-- 缺口 pp × 本金 / 100 = 年化少收的钱。
SELECT l.grade                                                    AS 信用等级,
       COUNT(*)                                                   AS 笔数,
       ROUND(SUM(l.loan_amnt) / 1e6, 1)                           AS 放款本金_百万,
       ROUND(AVG(l.int_rate), 2)                                  AS 平均利率,
       ROUND(100.0 * SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= 24
                              THEN 1 ELSE 0 END) / COUNT(*)
             * AVG(CASE WHEN l.outcome = 1 THEN l.lgd_net END), 3) AS 期望损失率,
       ROUND(AVG(l.int_rate)
             - 100.0 * SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= 24
                                THEN 1 ELSE 0 END) / COUNT(*)
             * AVG(CASE WHEN l.outcome = 1 THEN l.lgd_net END), 3) AS 毛价差pp
FROM loans l
WHERE l.mob_obs >= 24
GROUP BY 1
ORDER BY 1;

-- ── 结果2：行动2 的靶子 —— 60 期该补多少价，盘子多大 ──
-- 应补价差 = 同一等级 60 期的期望损失率 − 36 期的期望损失率。
-- 这个差完全是 LGD 撑起来的（第二节证明：拉平等级构成后，
-- 60 期的 24 期违约率反而略低）。所以补的是"期限风险价"，不是"违约风险价"。
--
-- 只列 D 级以上：A/B/C 两档期限的价差几乎没差（第二节已述）。
WITH g AS (
    SELECT grade,
           term_m,
           COUNT(*)                                                   AS n,
           SUM(loan_amnt)                                             AS amt,
           AVG(int_rate)                                              AS rate,
           100.0 * SUM(CASE WHEN outcome = 1 AND mob_event <= 24
                            THEN 1 ELSE 0 END) / COUNT(*)
             * AVG(CASE WHEN outcome = 1 THEN lgd_net END)            AS exp_loss
    FROM loans
    WHERE mob_obs >= 24
    GROUP BY 1, 2
)
SELECT a.grade                                                    AS 信用等级,
       a.n                                                        AS 三十六期笔数,
       b.n                                                        AS 六十期笔数,
       ROUND(b.amt / 1e6, 1)                                      AS 六十期本金_百万,
       ROUND(a.rate, 2)                                           AS 三十六期利率,
       ROUND(b.rate, 2)                                           AS 六十期利率,
       ROUND(b.rate - a.rate, 2)                                  AS 利率差pp,
       ROUND(a.exp_loss, 2)                                       AS 三十六期期望损失,
       ROUND(b.exp_loss, 2)                                       AS 六十期期望损失,
       ROUND(b.exp_loss - a.exp_loss, 2)                          AS 应补价差pp,
       ROUND(b.amt * (b.exp_loss - a.exp_loss) / 100.0 / 1e6, 2)  AS 年化少收_百万
FROM g a
JOIN g b ON a.grade = b.grade AND a.term_m = 36 AND b.term_m = 60
WHERE a.grade >= 'D'
ORDER BY a.grade;

-- ── 结果3：行动3 的靶子 —— 小微经营贷的敞口和超额损失 ──
-- sql_04 结果2 已经证明：同一个等级组里，small_business 的违约率
-- 始终比组内最好的用途高一截，而且在三组里排序一致。
-- 这里补上敞口：这个用途占了多少钱。
--
-- 超额违约 pp = 该用途违约率 − 同等级组的加权平均违约率。
-- 乘 LGD 换成期望损失，再乘本金 = 年化超额损失。
WITH b AS (
    SELECT purpose,
           CASE WHEN grade IN ('A', 'B') THEN '1 优质 A-B'
                WHEN grade IN ('C', 'D') THEN '2 中间 C-D'
                ELSE '3 高危 E-G' END                                  AS grp,
           COUNT(*)                                                   AS n,
           SUM(loan_amnt)                                             AS amt,
           100.0 * SUM(CASE WHEN outcome = 1 AND mob_event <= 24
                            THEN 1 ELSE 0 END) / COUNT(*)             AS pd24,
           AVG(CASE WHEN outcome = 1 THEN lgd_net END)                AS lgd
    FROM loans
    WHERE mob_obs >= 24
    GROUP BY 1, 2
    HAVING COUNT(*) >= 300
),
grp_avg AS (
    SELECT grp,
           SUM(pd24 * n) / SUM(n)                                     AS grp_pd
    FROM b
    GROUP BY 1
)
SELECT b.purpose                                                  AS 借款用途,
       b.grp                                                      AS 等级组,
       b.n                                                        AS 笔数,
       ROUND(b.amt / 1e6, 1)                                      AS 本金_百万,
       ROUND(b.pd24, 2)                                           AS 违约率,
       ROUND(g.grp_pd, 2)                                         AS 组内平均违约率,
       ROUND(b.pd24 - g.grp_pd, 2)                                AS 超额违约pp,
       ROUND(b.amt * (b.pd24 - g.grp_pd) / 100.0 * b.lgd / 1e6, 2) AS 年化超额损失_百万
FROM b
JOIN grp_avg g ON b.grp = g.grp
WHERE b.purpose = 'small_business'
ORDER BY b.grp;

-- ── 结果4：三条建议的监控基期值 ──
-- 建议一旦落地，得有个东西能盯着它有没有生效。
-- 这张表就是基期数：把三条建议各自对应的指标，在"全部队列"上算一个基准值。
-- 以后按季重跑这一段，数值朝预期方向动 = 建议生效。
--
-- 注意这是【基期快照】，不是时间序列。时间序列在 Tableau 那边用放款年做维度。
SELECT '1 B/C 级定价缺口' AS 建议,
       'B/C 级平均利率' AS 监控指标,
       ROUND(AVG(CASE WHEN grade IN ('B', 'C') THEN int_rate END), 3) AS 基期值,
       'pp' AS 单位
FROM loans WHERE mob_obs >= 24
UNION ALL
SELECT '1 B/C 级定价缺口',
       'B 级毛价差',
       (SELECT ROUND(AVG(int_rate)
                     - 100.0 * SUM(CASE WHEN outcome = 1 AND mob_event <= 24
                                        THEN 1 ELSE 0 END) / COUNT(*)
                     * AVG(CASE WHEN outcome = 1 THEN lgd_net END), 3)
        FROM loans WHERE mob_obs >= 24 AND grade = 'B'),
       'pp'
UNION ALL
SELECT '2 六十期期限价',
       '六十期与三十六期的利率差（G 级）',
       (SELECT ROUND(AVG(CASE WHEN term_m = 60 THEN int_rate END)
                     - AVG(CASE WHEN term_m = 36 THEN int_rate END), 3)
        FROM loans WHERE mob_obs >= 24 AND grade = 'G'),
       'pp'
UNION ALL
SELECT '2 六十期期限价',
       '六十期与三十六期的期望损失差（G 级）',
       (SELECT ROUND(
                  100.0 * SUM(CASE WHEN term_m = 60 AND outcome = 1
                                    AND mob_event <= 24 THEN 1 ELSE 0 END)
                        / NULLIF(SUM(CASE WHEN term_m = 60 THEN 1 ELSE 0 END), 0)
                  * AVG(CASE WHEN term_m = 60 AND outcome = 1 THEN lgd_net END)
                - 100.0 * SUM(CASE WHEN term_m = 36 AND outcome = 1
                                    AND mob_event <= 24 THEN 1 ELSE 0 END)
                        / NULLIF(SUM(CASE WHEN term_m = 36 THEN 1 ELSE 0 END), 0)
                  * AVG(CASE WHEN term_m = 36 AND outcome = 1 THEN lgd_net END), 3)
        FROM loans WHERE mob_obs >= 24 AND grade = 'G'),
       'pp'
UNION ALL
SELECT '3 用途纳入规则',
       '小微经营贷的违约率（A-B 组内）',
       (SELECT ROUND(100.0 * SUM(CASE WHEN outcome = 1 AND mob_event <= 24
                                      THEN 1 ELSE 0 END) / COUNT(*), 3)
        FROM loans
        WHERE mob_obs >= 24 AND purpose = 'small_business'
          AND grade IN ('A', 'B')),
       'pp'
UNION ALL
SELECT '3 用途纳入规则',
       '同组其他用途的中位违约率（A-B 组内）',
       (SELECT ROUND(MEDIAN(r), 3) FROM (
            SELECT 100.0 * SUM(CASE WHEN outcome = 1 AND mob_event <= 24
                                    THEN 1 ELSE 0 END) / COUNT(*) AS r
            FROM loans
            WHERE mob_obs >= 24 AND grade IN ('A', 'B')
              AND purpose <> 'small_business'
            GROUP BY purpose
            HAVING COUNT(*) >= 300)),
       'pp'
ORDER BY 1, 2;

-- ── 结果5：放款年 × 等级的价差时间序列 ──
-- 前三张表都是"把年份压掉"的存量照片。这一张补上时间维，两个用途：
--   1. 行动1 的缺口是"2018 相对 2010-2011"的变化量，只有这张表能算出
--      2018 那一年的 B/C 级到底有多少本金可以叠这个缺口；
--   2. 它是 Tableau 那一屏的时间轴数据源——价差的走势要靠它画。
SELECT issue_year                                                 AS 放款年,
       grade                                                      AS 信用等级,
       COUNT(*)                                                   AS 笔数,
       ROUND(SUM(loan_amnt) / 1e6, 1)                             AS 放款本金_百万,
       ROUND(AVG(int_rate), 2)                                    AS 平均利率,
       ROUND(100.0 * SUM(CASE WHEN outcome = 1 AND mob_event <= 24
                              THEN 1 ELSE 0 END) / COUNT(*), 2)   AS 二十四期违约率,
       ROUND(100.0 * SUM(CASE WHEN outcome = 1 AND mob_event <= 24
                              THEN 1 ELSE 0 END) / COUNT(*)
             * AVG(CASE WHEN outcome = 1 THEN lgd_net END), 3)    AS 期望损失率,
       ROUND(AVG(int_rate)
             - 100.0 * SUM(CASE WHEN outcome = 1 AND mob_event <= 24
                                THEN 1 ELSE 0 END) / COUNT(*)
             * AVG(CASE WHEN outcome = 1 THEN lgd_net END), 3)    AS 毛价差pp
FROM loans
WHERE mob_obs >= 24
GROUP BY 1, 2
ORDER BY 1, 2;
