-- T-BR-04 (SR-022, SQL part): no bridge row's MODE is better than the capability cap of its run.
SET TEST_ID = 'T-BR-04';
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
-- cap: the run's recorded bridge mode, or the newest capability row for development runs
WITH cap AS (
  SELECT COALESCE((SELECT BRIDGE_MODE FROM SR_DB.OPS.RUN_LOG WHERE RUN_ID = $RUN_UNDER_TEST),
                  (SELECT MAX_BRIDGE_MODE FROM SR_DB.OPS.CAPABILITY ORDER BY CHECKED_AT DESC LIMIT 1)) AS M
),
failures AS (
  SELECT b.SHIFT_ID, b.MODE, cap.M AS CAP_MODE
  FROM SR_DB.APP.SHARE_BRIDGE b CROSS JOIN cap
  WHERE b.RUN_ID = $RUN_UNDER_TEST AND b.MODE < cap.M          -- 'A' < 'B' < 'C' < 'D'
)
SELECT $TEST_RUN_ID, $TEST_ID, COUNT(*) = 0, COUNT(*),
       (SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*)) FROM (SELECT * FROM failures LIMIT 20))
FROM failures;
