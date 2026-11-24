-- T-ART-01 (SR-024): every child market with category sales in one period and none in the other, or with fewer
-- weeks than its parent in either period (B12), has an R2_FEED row on its parent, and there are no other R2_FEED
-- rows. Recomputed from the weekly table, not the period table the procedure reads.
SET TEST_ID = 'T-ART-01';
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
-- cmp: comparisons and periods
WITH cmp AS (
  SELECT column1 AS CMP_CODE, column2 AS CUR_P, column3 AS BASE_P
  FROM VALUES ('L4W_VS_YA','L4W','L4W_YA'), ('L4W_VS_PP','L4W','P4W'), ('L12W_VS_YA','L12W','L12W_YA'), ('L52W_VS_YA','L52W','L52W_YA')
),
-- kids: child markets of the scope parent
kids AS (
  SELECT MARKET_ID, PARENT_MARKET_ID FROM SR_DB.SRC.V_SRC_MARKET
  WHERE PARENT_MARKET_ID = (SELECT SETTING_VALUE::VARCHAR FROM SR_DB.OPS.SETTINGS WHERE SETTING_KEY = 'SCOPE_PARENT_MARKET')
),
-- side: each market's category sales and weeks per comparison side, from DT_CAT_WEEK
side AS (
  SELECT cmp.CMP_CODE, cw.MARKET_ID,
         SUM(IFF(pw.PERIOD_CODE = cmp.CUR_P,  cw.VALUE_SALES, 0)) AS V1,
         SUM(IFF(pw.PERIOD_CODE = cmp.BASE_P, cw.VALUE_SALES, 0)) AS V0,
         COUNT(DISTINCT IFF(pw.PERIOD_CODE = cmp.CUR_P,  cw.WEEK_END_DATE, NULL)) AS W1,
         COUNT(DISTINCT IFF(pw.PERIOD_CODE = cmp.BASE_P, cw.WEEK_END_DATE, NULL)) AS W0
  FROM SR_DB.CORE.DT_CAT_WEEK cw
  JOIN SR_DB.CORE.DT_PERIOD_WEEK pw ON pw.WEEK_END_DATE = cw.WEEK_END_DATE
  JOIN cmp ON pw.PERIOD_CODE IN (cmp.CUR_P, cmp.BASE_P)
  GROUP BY cmp.CMP_CODE, cw.MARKET_ID
),
-- sales: each child against its parent
sales AS (
  SELECT cmp.CMP_CODE, k.MARKET_ID, k.PARENT_MARKET_ID,
         COALESCE(c.V1, 0) AS V1, COALESCE(c.V0, 0) AS V0, COALESCE(c.W1, 0) AS W1, COALESCE(c.W0, 0) AS W0,
         p.W1 AS PW1, p.W0 AS PW0
  FROM kids k CROSS JOIN cmp
  LEFT JOIN side c ON c.CMP_CODE = cmp.CMP_CODE AND c.MARKET_ID = k.MARKET_ID
  LEFT JOIN side p ON p.CMP_CODE = cmp.CMP_CODE AND p.MARKET_ID = k.PARENT_MARKET_ID
),
expected AS (
  SELECT CMP_CODE, PARENT_MARKET_ID AS MARKET_ID, MARKET_ID AS CHILD_ID FROM sales
  WHERE (V1 = 0) <> (V0 = 0) OR (V1 <> 0 AND V0 <> 0 AND (W1 < PW1 OR W0 < PW0))
),
actual AS (
  SELECT CMP_CODE, MARKET_ID, EVIDENCE:child_market_id::VARCHAR AS CHILD_ID
  FROM SR_DB.APP.ARTEFACT_CHECK WHERE RUN_ID = $RUN_UNDER_TEST AND RULE_ID = 'R2_FEED'
),
failures AS (
  SELECT 'MISSING' AS PROBLEM, e.CMP_CODE, e.MARKET_ID, e.CHILD_ID FROM expected e
  WHERE NOT EXISTS (SELECT 1 FROM actual a WHERE a.CMP_CODE = e.CMP_CODE AND a.MARKET_ID = e.MARKET_ID AND a.CHILD_ID = e.CHILD_ID)
  UNION ALL
  SELECT 'UNEXPECTED', a.CMP_CODE, a.MARKET_ID, a.CHILD_ID FROM actual a
  WHERE NOT EXISTS (SELECT 1 FROM expected e WHERE e.CMP_CODE = a.CMP_CODE AND e.MARKET_ID = a.MARKET_ID AND e.CHILD_ID = a.CHILD_ID)
)
SELECT $TEST_RUN_ID, $TEST_ID, COUNT(*) = 0, COUNT(*),
       (SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*)) FROM (SELECT * FROM failures LIMIT 20))
FROM failures;
