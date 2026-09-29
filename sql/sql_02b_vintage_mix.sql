-- sql_02b_vintage_mix.sql —— 拆开看：恶化是"客群下沉"还是"风控失灵"
--
-- 【为什么这一步最值钱】
-- sql_02 发现了一个反直觉的事实：用固定账龄控制住删失之后，
-- 2015–2016 的队列是 2010 年以来最差的。但"变差"有两种完全不同的成因：
--
--   成因A 结构效应（mix）：平台主动下沉客群，多放了 D/E/F/G 级。
--        → 这是【业务决策】。风险敞口变大是预期内的，只要定价补得回来就没问题。
--
--   成因B 组内效应（rate）：同一个信用等级内部，违约率也变高了。
--        → 这是【风控模型失效】。等级失去区分度，定价的地基就塌了。
--
-- 两者的处置方式完全相反，所以必须拆开。
--
-- 【分解方法：shift-share】
-- 把整体违约率写成各等级的加权平均：
--     Total_t = Σ_g  w_gt × r_gt        （w = 占比，r = 组内违约率）
-- 相对基准期 b 的变化拆成三块：
--     结构效应 = Σ_g (w_gt − w_gb) × r_gb      ← 只是权重变了，组内风险按老的算
--     组内效应 = Σ_g  w_gb × (r_gt − r_gb)     ← 只是组内风险变了，权重按老的算
--     交互项   = Σ_g (w_gt − w_gb) × (r_gt − r_gb)   ← 两者同时变的那部分
-- 三者相加 = 总变化。交互项通常很小，但要报出来，不能偷偷并进前两项。
--
-- 基准期选 2010–2011（合并）：那是 sql_02 里表现最好的一段，
-- 也是"数据干净、样本量够"的起点。
--
-- 写 SQL 的硬约束：不能有行内注释；字符串里不能出现分号。

-- ── 结果1：各年 × 各等级的【组内】24 期累计违约率 ──
-- 看的是"同一个等级内部，风险有没有变化"。
-- 如果每一行（等级）从左往右都在升高，那就是组内恶化，风控失灵。
SELECT l.issue_year                                              AS 放款年,
       l.grade                                                   AS 等级,
       COUNT(*)                                                  AS 放款笔数,
       ROUND(AVG(l.int_rate), 2)                                 AS 平均利率,
       ROUND(100.0 * SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= 24
                              THEN 1 ELSE 0 END) / COUNT(*), 3)  AS 二十四期违约率
FROM loans l
WHERE l.mob_obs >= 24
GROUP BY 1, 2
ORDER BY 1, 2;

-- ── 结果2：各年 × 各等级的【放款占比】──
-- 看的是"客群结构有没有下沉"。
-- 如果 D/E/F/G 的占比逐年上升，那就是结构效应在起作用。
SELECT l.issue_year                                              AS 放款年,
       l.grade                                                   AS 等级,
       COUNT(*)                                                  AS 放款笔数,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY l.issue_year), 2)
                                                                 AS 占比,
       ROUND(100.0 * AVG(l.int_rate), 2)                         AS 平均利率
FROM loans l
WHERE l.mob_obs >= 24
GROUP BY 1, 2
ORDER BY 1, 2;

-- ── 结果3：shift-share 分解（核心）──
-- 基准期 2010–2011 合并。三块效应相加 = 总变化。
-- 读法：看【组内效应】那一列的绝对值是不是远大于【结构效应】——
-- 前者大 = 风控失灵，后者大 = 主动下沉。这是本节要回答的唯一问题。
WITH g AS (
    SELECT l.issue_year AS y, l.grade AS g,
           COUNT(*) AS n,
           SUM(CASE WHEN l.outcome = 1 AND l.mob_event <= 24 THEN 1 ELSE 0 END) AS bad
    FROM loans l
    WHERE l.mob_obs >= 24
    GROUP BY 1, 2
), yr AS (
    SELECT y, g,
           n * 1.0 / SUM(n) OVER (PARTITION BY y)  AS w,
           bad * 1.0 / n                            AS r
    FROM g
), base AS (
    SELECT g AS gb,
           SUM(n) * 1.0 / SUM(SUM(n)) OVER ()               AS wb,
           SUM(bad) * 1.0 / SUM(n)                          AS rb
    FROM g
    WHERE y IN (2010, 2011)
    GROUP BY 1
)
SELECT yr.y                                                       AS 放款年,
       ROUND(SUM(yr.w * yr.r) * 100, 3)                           AS 实际违约率,
       ROUND(SUM(base.wb * base.rb) * 100, 3)                     AS 基准期违约率,
       ROUND((SUM(yr.w * yr.r) - SUM(base.wb * base.rb)) * 100, 3) AS 总变化pp,
       ROUND(SUM((yr.w - base.wb) * base.rb) * 100, 3)            AS 结构效应pp,
       ROUND(SUM(base.wb * (yr.r - base.rb)) * 100, 3)            AS 组内效应pp,
       ROUND(SUM((yr.w - base.wb) * (yr.r - base.rb)) * 100, 3)   AS 交互项pp
FROM yr JOIN base ON yr.g = base.gb
GROUP BY 1
ORDER BY 1;

-- ── 结果4：等级下移的量化 —— 加权平均等级分 ──
-- 把 A~G 映射成 1~7 分，按放款笔数加权求平均。
-- 这个数字逐年上升 = 客群在下沉，是结果2 的一句话版本，
-- 适合直接引用（"加权平均等级从 3.1 降到 3.9"比一张占比表更好记）。
SELECT issue_year                                                 AS 放款年,
       COUNT(*)                                                   AS 放款笔数,
       ROUND(SUM(CASE grade
                     WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'C' THEN 3
                     WHEN 'D' THEN 4 WHEN 'E' THEN 5 WHEN 'F' THEN 6
                     WHEN 'G' THEN 7 END) * 1.0 / COUNT(*), 3)    AS 加权平均等级分,
       ROUND(100.0 * SUM(CASE WHEN grade IN ('F', 'G') THEN 1 ELSE 0 END)
             / COUNT(*), 2)                                       AS 高危等级占比,
       ROUND(100.0 * SUM(CASE WHEN grade IN ('A', 'B') THEN 1 ELSE 0 END)
             / COUNT(*), 2)                                       AS 优质等级占比
FROM loans l
WHERE l.mob_obs >= 24
GROUP BY 1
ORDER BY 1;
