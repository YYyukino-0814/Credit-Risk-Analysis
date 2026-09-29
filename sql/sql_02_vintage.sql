-- sql_02_vintage.sql —— 核心分析：放款质量到底在变好还是变坏
--
-- 这是整个项目的主战场。要回答的问题只有一句：
--   把账龄控制住之后，晚放的款是不是比早放的款更安全？
--
-- 【为什么要控制账龄】
-- 直接比"各年的核销率"是错的。2015 年的贷款已经走完 36/60 期，该坏的都坏了；
-- 2018 年的只走了 44 个月，还没轮到它们坏。直接比等于把
-- "没来得及坏"当成"不会坏"，会凭空造出"质量在改善"的假象。
--
-- 【固定账龄法】
-- 不比起始年份，比【同一账龄】。所有队列都看它在第 24 个月时的累计违约率，
-- 大家站在同一个时间点上比，才公平。这叫 vintage 分析。
--
-- 【可观察性纪律】
-- 只发看得见的格子：WHERE mob_obs >= k。
-- 2018Q4 的队列 mob_obs = 44，所以它在 k=60 那一格必须是空白，不能是 0。
-- 填 0 等于宣称"这批贷款第 60 期一笔都没坏"——而我们根本没看到第 60 期。
--
-- 【双口径】
-- 每个结果都同时给 outcome（官方状态口径）和 loss_occurred（损失口径）。
-- 两者在 2007–2011 有明显差异，详见 00_口径与数据说明.md 第四之二节。
--
-- 写 SQL 的两条硬约束：不能有行内注释；字符串里不能出现分号。

-- ── 结果1：核心答案表 —— 年度队列 × 固定账龄的累计违约率 ──
-- 这张表是全项目最重要的一张。看两件事：
--   (a) 同一列（同一账龄）从上往下走，违约率怎么变 → 质量趋势
--   (b) 同一行从左往右走，违约率怎么升 → 成熟速度
-- 分子判据 mob_event <= k：用"最后一笔还款"代理违约时点（见口径文档第五节）。
-- 未决贷款自动进分母不进分子——它们到第 k 期时确实还活着，这正是累计违约率的定义。
WITH mobs AS (
    SELECT unnest([6, 12, 18, 24, 36]) AS k
)
SELECT l.issue_year                                              AS 放款年,
       m.k                                                       AS 账龄月,
       COUNT(*)                                                  AS 可观察笔数,
       SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= m.k
                THEN 1 ELSE 0 END)                               AS 官方违约笔数,
       SUM(CASE WHEN l.loss_occurred = 1 AND l.mob_event <= m.k
                THEN 1 ELSE 0 END)                               AS 损失口径笔数,
       ROUND(100.0 * SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= m.k
                              THEN 1 ELSE 0 END) / COUNT(*), 3)  AS 官方累计违约率,
       ROUND(100.0 * SUM(CASE WHEN l.loss_occurred = 1 AND l.mob_event <= m.k
                              THEN 1 ELSE 0 END) / COUNT(*), 3)  AS 损失口径累计率
FROM loans l
CROSS JOIN mobs m
WHERE l.mob_obs >= m.k
GROUP BY 1, 2
ORDER BY 1, 2;

-- ── 结果2：季度队列在固定 24 期账龄上的表现（更细的拐点）──
-- 年度粒度会把"某一年之内质量转向"这件事抹平。按季度看拐点在哪。
-- 只留 24 期这一列，是为了让趋势读起来是一条线而不是一个面。
WITH mobs AS (
    SELECT 24 AS k
)
SELECT l.issue_q_label                                          AS 队列,
       l.issue_year                                             AS 放款年,
       l.issue_q                                                AS 季度起点,
       COUNT(*)                                                 AS 可观察笔数,
       ROUND(AVG(l.int_rate), 2)                                AS 平均利率,
       ROUND(100.0 * SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= m.k
                              THEN 1 ELSE 0 END) / COUNT(*), 3)  AS 二十四期官方违约率,
       ROUND(100.0 * SUM(CASE WHEN l.loss_occurred = 1 AND l.mob_event <= m.k
                              THEN 1 ELSE 0 END) / COUNT(*), 3)  AS 二十四期损失口径率
FROM loans l
CROSS JOIN mobs m
WHERE l.mob_obs >= m.k
GROUP BY 1, 2, 3
ORDER BY 3;

-- ── 结果3：代表队列的完整成熟曲线 ──
-- 结果1 是离散的几个时点，这里给几条完整的曲线，看形状。
-- 选 2012–2017 这六个年度队列：它们规模够大、账龄够长，
-- 且横跨了"数据最干净的时期"，形状最能说明问题。
WITH mobs AS (
    SELECT unnest([3, 6, 9, 12, 15, 18, 21, 24, 30, 36, 42, 48]) AS k
)
SELECT l.issue_year                                              AS 放款年,
       m.k                                                       AS 账龄月,
       COUNT(*)                                                  AS 可观察笔数,
       ROUND(100.0 * SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= m.k
                              THEN 1 ELSE 0 END) / COUNT(*), 3)  AS 官方累计违约率,
       ROUND(100.0 * SUM(CASE WHEN l.loss_occurred = 1 AND l.mob_event <= m.k
                              THEN 1 ELSE 0 END) / COUNT(*), 3)  AS 损失口径累计率
FROM loans l
CROSS JOIN mobs m
WHERE l.mob_obs >= m.k
  AND l.issue_year BETWEEN 2012 AND 2017
GROUP BY 1, 2
ORDER BY 1, 2;

-- ── 结果4：坏账的成熟滞后分布 ──
-- 支撑 mob_event 这个代理的合理性，也告诉读者"要等多久才看得见坏账"。
-- 实测中位数会落在十几个月的量级，说明 24 期观察窗口足够看到大部分坏账，
-- 但 60 期贷款的故事在 24 期时还没讲完——这正是删失的工作机理。
SELECT ROUND(AVG(mob_event), 1)                                  AS 平均滞后月,
       MIN(mob_event)                                            AS 最短,
       MAX(mob_event)                                            AS 最长,
       ROUND(quantile_cont(mob_event, 0.25), 0)                  AS 四分之一分位,
       ROUND(quantile_cont(mob_event, 0.50), 0)                  AS 中位数,
       ROUND(quantile_cont(mob_event, 0.75), 0)                  AS 四分之三分位,
       ROUND(quantile_cont(mob_event, 0.90), 0)                  AS 十分之九分位,
       COUNT(*)                                                  AS 已核销笔数
FROM loans
WHERE outcome = 1;

-- ── 结果5：36 期与 60 期的同队列对比【⚠️ 未控制等级，不要单独引用】──
-- 这张表【只按 放款年 × 期限】汇总，不控制信用等级。
--
-- ⚠️⚠️ 它给出的"60 期更危险"是【辛普森悖论】，不是期限的真实效应。
--    原因：两个期限的客群构成完全不同——
--        36 期里 A 级占 25.4%，60 期里只占 3.7%；
--        36 期里 E/F/G 合计 3.8%，60 期里高达 19.7%。
--    也就是"选 60 期的人本来信用分就更低"，不是"60 期这个期限让人变坏"。
--    实测：把 60 期的等级构成强行换成 36 期的，24 期违约率从 15.75% 掉到 10.09%，
--    反而比 36 期实际的 10.91% 还低。等级构成解释了 117% 的差距。
--
-- 保留这张表是因为【它本身就是结论的一部分】——错误示范要留在代码里，
-- 才能证明后面那张控制等级的对照表不是凭空来的。
-- 真正可用的是结果7。核对过程见 code/_probes/_probe_term_confound.py。
--
-- 另外：60 期在 2017 之后的队列上被删失，所以这张表的近年格子会缺，
-- 缺就是缺，不能补 0。
WITH mobs AS (
    SELECT unnest([12, 24, 36]) AS k
)
SELECT l.issue_year                                              AS 放款年,
       l.term_m                                                  AS 期限,
       m.k                                                       AS 账龄月,
       COUNT(*)                                                  AS 可观察笔数,
       ROUND(100.0 * SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= m.k
                              THEN 1 ELSE 0 END) / COUNT(*), 3)  AS 官方累计违约率
FROM loans l
CROSS JOIN mobs m
WHERE l.mob_obs >= m.k
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- ── 结果6：Vintage 衰变比 —— 相邻队列的违约率倍数 ──
-- 把"变好还是变坏"变成一个可以直接引用的数：
-- 后一年队列的 24 期违约率 ÷ 前一年队列的 24 期违约率。
-- 小于 1 = 变好，大于 1 = 变坏。相邻年比，不跨年比，避免被长期趋势掩盖。
WITH v AS (
    SELECT l.issue_year AS y,
           ROUND(100.0 * SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= 24
                                  THEN 1 ELSE 0 END) / COUNT(*), 3) AS d
    FROM loans l
    WHERE l.mob_obs >= 24
    GROUP BY 1
)
SELECT y                                                          AS 放款年,
       d                                                          AS 二十四期违约率,
       LAG(d) OVER (ORDER BY y)                                   AS 上年违约率,
       ROUND(d / NULLIF(LAG(d) OVER (ORDER BY y), 0), 3)          AS 衰变比,
       ROUND(d - LAG(d) OVER (ORDER BY y), 3)                     AS 绝对变化pp
FROM v
ORDER BY y;

-- ── 结果7：控制等级后的期限效应 —— 这才是能引用的那张表 ──
-- 结果5 把"60 期更危险"做成了辛普森悖论：两个期限的等级构成差了十万八千里。
-- 这里在同一等级内部比，并且把两个维度【分开看】：
--   违约概率（PD）：同一个 24 期时点上，还不还得上钱的比例
--   违约损失率（LGD）：一旦违约，本金要折掉多少
--
-- 分开看是必须的：它们可以有完全不同的答案，而业务含义恰恰相反——
--   PD 高 → 这批客户更可能出事，是【获客/审批】问题；
--   LGD 高 → 出事时剩的窟窿更大，是【产品设计/期限结构】问题。
-- 实测结果：PD 上 60 期并不更高（标准化后甚至更低），
--           但 LGD 上 60 期稳定高出 9 个百分点左右，且七个等级无一例外。
-- 原因不难理解：同样在第 24 个月违约，60 期贷款才还掉四成本金，
--               36 期已经还掉三分之二，剩下的窟窿自然差一大截。
SELECT l.grade                                                    AS 信用等级,
       l.term_m                                                   AS 期限,
       COUNT(*)                                                   AS 笔数,
       ROUND(100.0 * SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= 24
                              THEN 1 ELSE 0 END) / COUNT(*), 2)   AS 二十四期违约率,
       ROUND(AVG(CASE WHEN l.outcome = 1 THEN l.lgd_net END), 4)  AS 违约损失率LGD,
       ROUND(100.0 * SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= 24
                              THEN 1 ELSE 0 END) / COUNT(*)
             * AVG(CASE WHEN l.outcome = 1 THEN l.lgd_net END), 3) AS 期望损失率
FROM loans l
WHERE l.mob_obs >= 24
GROUP BY 1, 2
ORDER BY 1, 2;
