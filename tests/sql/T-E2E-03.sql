-- T-E2E-03 (SR-053): while a run is in progress, a second run is SKIPPED with reason BUSY and
-- SP_REPLAY_NEXT_WEEK returns BUSY (E16). Snowflake itself skips a second EXECUTE TASK while the first is
-- running, so the overlap is simulated with a RUNNING marker row, which makes the check deterministic.
SET TEST_ID = 'T-E2E-03';
EXECUTE IMMEDIATE $$
DECLARE
  fails  ARRAY DEFAULT ARRAY_CONSTRUCT();
  marker VARCHAR DEFAULT 'test-busy-' || UUID_STRING();
  res    VARCHAR;
  reason VARCHAR;
BEGIN
  IF (NOT $RUN_E2E) THEN RETURN 'SKIPPED_NO_E2E'; END IF;
  INSERT INTO SR_DB.OPS.RUN_LOG (RUN_ID, TRIGGER_TYPE, STATUS, STARTED_AT, ERROR_MSG)
  VALUES (:marker, 'MANUAL', 'RUNNING', CURRENT_TIMESTAMP(), 'T-E2E-03 marker');
  BEGIN
    CALL SR_DB.APP.SP_RUN_WEEK('MANUAL', TRUE) INTO :res;
    IF (res <> 'SKIPPED') THEN fails := ARRAY_APPEND(fails, 'second run returned ' || res); END IF;
    SELECT ERROR_MSG INTO :reason FROM SR_DB.OPS.RUN_LOG
     WHERE STATUS = 'SKIPPED' AND STARTED_AT > DATEADD(minute, -5, CURRENT_TIMESTAMP())
     ORDER BY STARTED_AT DESC LIMIT 1;
    IF (reason IS NULL OR NOT STARTSWITH(reason, 'BUSY')) THEN fails := ARRAY_APPEND(fails, 'skip reason ' || COALESCE(reason, 'none')); END IF;
    CALL SR_DB.APP.SP_REPLAY_NEXT_WEEK() INTO :res;
    IF (res <> 'BUSY') THEN fails := ARRAY_APPEND(fails, 'replay returned ' || res); END IF;
  EXCEPTION
    WHEN OTHER THEN
      fails := ARRAY_APPEND(fails, 'raised: ' || LEFT(SQLERRM, 200));
  END;
  DELETE FROM SR_DB.OPS.RUN_LOG WHERE RUN_ID = :marker;
  RETURN ARRAY_TO_STRING(fails, '; ');
END;
$$;
SET Q = LAST_QUERY_ID();
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
SELECT $TEST_RUN_ID, $TEST_ID, $1 = '', IFF($1 = '', 0, ARRAY_SIZE(SPLIT($1, '; '))), TO_VARIANT($1)
FROM TABLE(RESULT_SCAN($Q)) WHERE $1 <> 'SKIPPED_NO_E2E';
