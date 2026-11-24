-- T-ART-03 (SR-024): where a week inside the compared periods has a different ROW_HASH between the run under
-- test and the previous successful run with snapshots, an R3_RESTATE row exists for that comparison and market.
-- Passes trivially when there is no previous run with snapshots.
SET TEST_ID = 'T-ART-03';
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
-- prev: the previous successful run that took a snapshot
WITH prev AS (
  SELECT r.RUN_ID FROM SR_DB.OPS.RUN_LOG r
  WHERE r.STATUS = 'SUCCEEDED' AND r.RUN_ID <> $RUN_UNDER_TEST
    AND r.STARTED_AT < (SELECT COALESCE(MAX(STARTED_AT), CURRENT_TIMESTAMP()) FROM SR_DB.OPS.RUN_LOG WHERE RUN_ID = $RUN_UNDER_TEST)
    AND EXISTS (SELECT 1 FROM SR_DB.OPS.FACT_SNAPSHOT s WHERE s.RUN_ID = r.RUN_ID)
  ORDER BY r.STARTED_AT DESC LIMIT 1
),
cmp AS (
  SELECT column1 AS CMP_CODE, column2 AS CUR_P, column3 AS BASE_P
  FROM VALUES ('L4W_VS_YA','L4W','L4W_YA'), ('L4W_VS_PP','L4W','P4W'), ('L12W_VS_YA','L12W','L12W_YA'), ('L52W_VS_YA','L52W','L52W_YA')
),
-- changed: restated weeks mapped to the comparisons whose periods contain them
changed AS (
  SELECT DISTINCT cmp.CMP_CODE, cur.MARKET_ID
  FROM SR_DB.OPS.FACT_SNAPSHOT cur
  JOIN SR_DB.OPS.FACT_SNAPSHOT prv ON prv.RUN_ID = (SELECT RUN_ID FROM prev)
   AND prv.WEEK_END_DATE = cur.WEEK_END_DATE AND prv.MARKET_ID = cur.MARKET_ID
  JOIN SR_DB.CORE.DT_PERIOD_WEEK pw ON pw.WEEK_END_DATE = cur.WEEK_END_DATE
  JOIN cmp ON pw.PERIOD_CODE IN (cmp.CUR_P, cmp.BASE_P)
  WHERE cur.RUN_ID = $RUN_UNDER_TEST AND cur.ROW_HASH <> prv.ROW_HASH
),
failures AS (
  SELECT c.CMP_CODE, c.MARKET_ID FROM changed c
  WHERE NOT EXISTS (SELECT 1 FROM SR_DB.APP.ARTEFACT_CHECK a
                    WHERE a.RUN_ID = $RUN_UNDER_TEST AND a.RULE_ID = 'R3_RESTATE'
                      AND a.CMP_CODE = c.CMP_CODE AND a.MARKET_ID = c.MARKET_ID)
)
SELECT $TEST_RUN_ID, $TEST_ID, COUNT(*) = 0, COUNT(*),
       (SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*)) FROM (SELECT * FROM failures LIMIT 20))
FROM failures;
