-- T-CORE-04 (SR-010): each period has EXPECTED_WEEKS weeks where history allows; L4W ends at the as-of week;
-- L4W_YA sits exactly 52 weeks earlier; a comparison without base data has NULL CS0.
SET TEST_ID = 'T-CORE-04';
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
-- hist: the first and last week of data, recomputed from the adapter
WITH hist AS (
  SELECT MIN(WEEK_END_DATE) AS FIRST_WK, MAX(WEEK_END_DATE) AS LAST_WK FROM SR_DB.SRC.V_SRC_FACT_WEEKLY
),
-- per_period: weeks found per period, with its bounds
per_period AS (
  SELECT PERIOD_CODE, COUNT(*) AS N, MAX(EXPECTED_WEEKS) AS EXP_N,
         MIN(PERIOD_START) AS P_START, MAX(PERIOD_END) AS P_END, MAX(WEEK_END_DATE) AS LAST_IN
  FROM SR_DB.CORE.DT_PERIOD_WEEK GROUP BY PERIOD_CODE
),
failures AS (
  -- a fully covered period with the wrong number of weeks
  SELECT 'WEEK_COUNT' AS PROBLEM, p.PERIOD_CODE, p.N::VARCHAR AS ACTUAL, p.EXP_N::VARCHAR AS EXPECTED
  FROM per_period p CROSS JOIN hist h
  WHERE p.P_START >= h.FIRST_WK AND p.N <> p.EXP_N
  UNION ALL
  -- L4W must end at the latest week
  SELECT 'L4W_END', p.PERIOD_CODE, p.LAST_IN::VARCHAR, h.LAST_WK::VARCHAR
  FROM per_period p CROSS JOIN hist h
  WHERE p.PERIOD_CODE = 'L4W' AND p.LAST_IN <> h.LAST_WK
  UNION ALL
  -- L4W_YA must sit exactly 52 weeks before L4W
  SELECT 'L4W_YA_OFFSET', ya.PERIOD_CODE, ya.P_END::VARCHAR, DATEADD(week, -52, cur.P_END)::VARCHAR
  FROM per_period ya JOIN per_period cur ON cur.PERIOD_CODE = 'L4W'
  WHERE ya.PERIOD_CODE = 'L4W_YA' AND ya.P_END <> DATEADD(week, -52, cur.P_END)
  UNION ALL
  -- no base-period category row, yet CS0 is filled
  SELECT 'CS0_NOT_NULL', c.CMP_CODE || '|' || c.MARKET_ID, c.CS0::VARCHAR, 'NULL'
  FROM SR_DB.CORE.DT_SHARE_COMPARE c
  WHERE c.CS0 IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM SR_DB.CORE.DT_CAT_PERIOD cp
                    WHERE cp.PERIOD_CODE = c.BASE_PERIOD AND cp.MARKET_ID = c.MARKET_ID AND cp.CATEGORY = c.CATEGORY)
)
SELECT $TEST_RUN_ID, $TEST_ID, COUNT(*) = 0, COUNT(*),
       (SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*)) FROM (SELECT * FROM failures LIMIT 20))
FROM failures;
