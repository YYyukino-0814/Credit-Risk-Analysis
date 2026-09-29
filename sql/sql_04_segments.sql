-- sql_04_segments.sql —— 哪些风险差异，在放款之前就能看出来
--
-- 【从第三节接过来的问题】
-- 第三、四节证明了几件事：定价在 B/C 级没跟上、60 期的 LGD 被漏掉了、
-- 2015-2016 明显变差。但那些结论全是【事后】才知道的
-- （违约、损失、回收都要等贷款跑完）。
--
-- 这一节换成【放款前】的视角：把每笔贷款按申请时就能拿到的信息切开，
-- 看哪些差异是统计上真的、哪些只是噪声。
-- 这件事直接决定风控模型能用到什么变量。
--
-- 【为什么 SQL 只输出"长表"，不在这里算 IV】
-- IV（信息值）的公式要在十几个特征上各算一遍。如果写在这个文件里，
-- 就是同一个公式抄十几遍——抄错一个不会被发现，改口径要改十几处。
-- 所以这里只把【分箱后的原子计数】吐出来（特征、分箱、笔数、坏账数），
-- IV / 置信区间 / 卡方检验全部交给 code/04_segment_stats.py 算一次。
-- 这也是数据库该干的活：它负责把数据整理成规整的形状，不负责统计推断。
--
-- 【标签口径】
-- 本节统一用 bad24 = 24 期内违约，理由和第二节一样：
-- 它是唯一对全部 12 个队列都成立的账龄，而这一节要跨年份比较。
-- 未决贷款照例进分母不进分子——它们在第 24 个月时确实还活着。
--
-- 写 SQL 的硬约束：不能有行内注释；字符串里不能出现分号。

-- ── 结果1：所有特征的分箱统计（长表）──
-- 分箱标签用 00 / 01 / 02 前缀，为的是让字符串排序等于数值顺序。
-- 中文标签直接排序会乱（按 Unicode 码点），加数字前缀最省事。
--
-- 分类型特征里，取值太多的（addr_state 有 50 个州、purpose 有 14 种）
-- 只保留头部的几个，剩下的并成"其他"——
-- 分箱太细会让每个箱的样本量太小，算出来的违约率全是噪声。
WITH b AS (
    SELECT CASE WHEN outcome = 1 AND mob_event <= 24 THEN 1 ELSE 0 END AS bad24,
           grade,
           term_m,
           purpose,
           home_ownership,
           verification_status,
           application_type,
           initial_list_status,
           CASE WHEN addr_state IN ('CA', 'NY', 'TX', 'FL', 'IL',
                                    'NJ', 'PA', 'OH', 'GA', 'VA')
                THEN addr_state ELSE '其他' END                       AS state_grp,
           CASE WHEN dti IS NULL THEN '99 缺失'
                WHEN dti < 10 THEN '00 低于10' WHEN dti < 15 THEN '01 10-15'
                WHEN dti < 20 THEN '02 15-20'  WHEN dti < 25 THEN '03 20-25'
                WHEN dti < 30 THEN '04 25-30'  ELSE '05 30以上' END    AS dti_band,
           CASE WHEN annual_inc < 30000  THEN '00 3万以下'
                WHEN annual_inc < 50000  THEN '01 3-5万'
                WHEN annual_inc < 75000  THEN '02 5-7.5万'
                WHEN annual_inc < 100000 THEN '03 7.5-10万'
                WHEN annual_inc < 150000 THEN '04 10-15万'
                ELSE '05 15万以上' END                                  AS inc_band,
           CASE WHEN revol_util IS NULL THEN '99 缺失'
                WHEN revol_util < 20 THEN '00 低于20%'
                WHEN revol_util < 40 THEN '01 20-40%'
                WHEN revol_util < 60 THEN '02 40-60%'
                WHEN revol_util < 80 THEN '03 60-80%'
                ELSE '04 80%以上' END                                   AS util_band,
           CASE WHEN loan_amnt < 5000  THEN '00 5千以下'
                WHEN loan_amnt < 10000 THEN '01 5千-1万'
                WHEN loan_amnt < 15000 THEN '02 1-1.5万'
                WHEN loan_amnt < 20000 THEN '03 1.5-2万'
                WHEN loan_amnt < 25000 THEN '04 2-2.5万'
                ELSE '05 2.5万以上' END                                 AS amnt_band,
           CASE WHEN inq_last_6mths = 0 THEN '00 0次'
                WHEN inq_last_6mths = 1 THEN '01 1次'
                WHEN inq_last_6mths = 2 THEN '02 2次'
                WHEN inq_last_6mths = 3 THEN '03 3次'
                ELSE '04 4次以上' END                                   AS inq_band,
           CASE WHEN open_acc < 5  THEN '00 少于5个'
                WHEN open_acc < 8  THEN '01 5-8个'
                WHEN open_acc < 12 THEN '02 8-12个'
                WHEN open_acc < 18 THEN '03 12-18个'
                ELSE '04 18个以上' END                                  AS openacc_band,
           CASE WHEN delinq_2yrs = 0 THEN '00 无'
                WHEN delinq_2yrs = 1 THEN '01 1次'
                ELSE '02 2次以上' END                                   AS delinq_band,
           CASE WHEN pub_rec = 0 THEN '00 无' ELSE '01 有' END         AS pubrec_band,
           CASE WHEN date_diff('month', earliest_cr_line_date, issue_date) < 60
                     THEN '00 5年以下'
                WHEN date_diff('month', earliest_cr_line_date, issue_date) < 120
                     THEN '01 5-10年'
                WHEN date_diff('month', earliest_cr_line_date, issue_date) < 180
                     THEN '02 10-15年'
                WHEN date_diff('month', earliest_cr_line_date, issue_date) < 240
                     THEN '03 15-20年'
                ELSE '04 20年以上' END                                  AS crhist_band,
           CASE WHEN emp_years IS NULL THEN '99 缺失'
                WHEN emp_years < 1 THEN '00 1年以下'
                WHEN emp_years < 3 THEN '01 1-3年'
                WHEN emp_years < 5 THEN '02 3-5年'
                WHEN emp_years < 10 THEN '03 5-10年'
                ELSE '04 10年以上' END                                  AS empyr_band
    FROM loans
    WHERE mob_obs >= 24
)
SELECT '01 信用等级' AS 特征, grade AS 分箱, COUNT(*) AS 笔数, SUM(bad24) AS 坏账数 FROM b GROUP BY 2
UNION ALL SELECT '02 期限', term_m, COUNT(*), SUM(bad24) FROM b GROUP BY 2
UNION ALL SELECT '03 借款用途', purpose, COUNT(*), SUM(bad24) FROM b GROUP BY 2
UNION ALL SELECT '04 住房情况', home_ownership, COUNT(*), SUM(bad24) FROM b GROUP BY 2
UNION ALL SELECT '05 收入核实', verification_status, COUNT(*), SUM(bad24) FROM b GROUP BY 2
UNION ALL SELECT '06 申请类型', application_type, COUNT(*), SUM(bad24) FROM b GROUP BY 2
UNION ALL SELECT '07 挂牌状态', initial_list_status, COUNT(*), SUM(bad24) FROM b GROUP BY 2
UNION ALL SELECT '08 所在州', state_grp, COUNT(*), SUM(bad24) FROM b GROUP BY 2
UNION ALL SELECT '09 负债收入比', dti_band, COUNT(*), SUM(bad24) FROM b GROUP BY 2
UNION ALL SELECT '10 年收入', inc_band, COUNT(*), SUM(bad24) FROM b GROUP BY 2
UNION ALL SELECT '11 额度使用率', util_band, COUNT(*), SUM(bad24) FROM b GROUP BY 2
UNION ALL SELECT '12 借款金额', amnt_band, COUNT(*), SUM(bad24) FROM b GROUP BY 2
UNION ALL SELECT '13 半年查询次数', inq_band, COUNT(*), SUM(bad24) FROM b GROUP BY 2
UNION ALL SELECT '14 在用账户数', openacc_band, COUNT(*), SUM(bad24) FROM b GROUP BY 2
UNION ALL SELECT '15 两年逾期次数', delinq_band, COUNT(*), SUM(bad24) FROM b GROUP BY 2
UNION ALL SELECT '16 公共不良记录', pubrec_band, COUNT(*), SUM(bad24) FROM b GROUP BY 2
UNION ALL SELECT '17 信用史长度', crhist_band, COUNT(*), SUM(bad24) FROM b GROUP BY 2
UNION ALL SELECT '18 工作年限', empyr_band, COUNT(*), SUM(bad24) FROM b GROUP BY 2
ORDER BY 1, 2;

-- ── 结果2：用途 × 等级 —— 用途的效应是不是被等级解释掉了 ──
-- 单看"哪个用途风险高"很容易得出误导性结论：
-- 某个用途违约率高，可能只是因为借钱的人等级本来就低。
-- 把两个维度交叉，看同一个等级内部不同用途还差不差。
-- 如果组内差距消失，说明用途这个字段是多余的——等级已经把它包含进去了。
SELECT purpose                                                    AS 借款用途,
       CASE WHEN grade IN ('A', 'B') THEN '1 优质 A-B'
            WHEN grade IN ('C', 'D') THEN '2 中间 C-D'
            ELSE '3 高危 E-G' END                                  AS 等级组,
       COUNT(*)                                                   AS 笔数,
       ROUND(100.0 * SUM(CASE WHEN outcome = 1 AND mob_event <= 24
                              THEN 1 ELSE 0 END) / COUNT(*), 3)   AS 二十四期违约率
FROM loans
WHERE mob_obs >= 24
GROUP BY 1, 2
HAVING COUNT(*) >= 300
ORDER BY 2, 4 DESC;

-- ── 结果3：时间分半的稳定性检验 ──
-- 这一步是给整节结论上保险：一个特征"有用"的标准不只是显著，
-- 而且要在【时间上】稳定——前五年有效的规则，后五年还得有效。
--
-- ⚠️ 分半必须按【时间】切，不能随机切。
--    随机切是把同一时期的贷款分到两边，两边的样本几乎一样，
--    当然会得到"高度一致"的结论——那不是验证，那是自我抄袭。
--    时间分半才是真的样本外测试：用前五年发现的规律去检验后五年。
--
-- 只用 2010-2018，2007-2009 样本太小。
SELECT '01 借款用途' AS 特征, CAST(purpose AS VARCHAR) AS 分箱,
       CASE WHEN issue_year <= 2014 THEN '前段 2010-2014' ELSE '后段 2015-2018' END AS 时段,
       COUNT(*) AS 笔数,
       ROUND(100.0 * SUM(CASE WHEN outcome = 1 AND mob_event <= 24
                              THEN 1 ELSE 0 END) / COUNT(*), 3) AS 二十四期违约率
FROM loans WHERE mob_obs >= 24 AND issue_year BETWEEN 2010 AND 2018
GROUP BY 2, 3
UNION ALL
SELECT '02 信用等级', CAST(grade AS VARCHAR),
       CASE WHEN issue_year <= 2014 THEN '前段 2010-2014' ELSE '后段 2015-2018' END,
       COUNT(*),
       ROUND(100.0 * SUM(CASE WHEN outcome = 1 AND mob_event <= 24
                              THEN 1 ELSE 0 END) / COUNT(*), 3)
FROM loans WHERE mob_obs >= 24 AND issue_year BETWEEN 2010 AND 2018
GROUP BY 2, 3
UNION ALL
SELECT '03 负债收入比', CASE WHEN dti < 15 THEN '00 低于15' WHEN dti < 25 THEN '01 15-25'
                             WHEN dti < 35 THEN '02 25-35' ELSE '03 35以上' END,
       CASE WHEN issue_year <= 2014 THEN '前段 2010-2014' ELSE '后段 2015-2018' END,
       COUNT(*),
       ROUND(100.0 * SUM(CASE WHEN outcome = 1 AND mob_event <= 24
                              THEN 1 ELSE 0 END) / COUNT(*), 3)
FROM loans WHERE mob_obs >= 24 AND issue_year BETWEEN 2010 AND 2018
GROUP BY 2, 3
ORDER BY 1, 2, 3;
