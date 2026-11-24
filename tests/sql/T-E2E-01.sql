-- T-E2E-01 (SR-033): CALL SP_RUN_WEEK('MANUAL', TRUE) for the current week gives RUN_LOG SUCCEEDED, 14 step
-- numbers in STEP_LOG, one PUBLISHED brief, and a SENT row in NOTIFY_LOG within 5 minutes (the alert on new data
-- sends it; the test polls every 15 seconds). Run after every deploy (E12).
SET TEST_ID = 'T-E2E-01';
EXECUTE IMMEDIATE $$
DECLARE
  fails ARRAY DEFAULT ARRAY_CONSTRUCT();
  rid   VARCHAR;
  st    VARCHAR;
  steps NUMBER;
  nb    NUMBER;
  bid   VARCHAR;
  sent  NUMBER DEFAULT 0;
  i     NUMBER DEFAULT 0;
BEGIN
  IF (NOT $RUN_E2E) THEN RETURN 'SKIPPED_NO_E2E'; END IF;
  CALL SR_DB.APP.SP_RUN_WEEK('MANUAL', TRUE) INTO :rid;
  SELECT STATUS, BRIEF_ID INTO :st, :bid FROM SR_DB.OPS.RUN_LOG WHERE RUN_ID = :rid;
  IF (st IS NULL OR st <> 'SUCCEEDED') THEN fails := ARRAY_APPEND(fails, 'run ' || COALESCE(rid, 'none') || ' status ' || COALESCE(st, 'none')); END IF;
  SELECT COUNT(DISTINCT STEP_NO) INTO :steps FROM SR_DB.OPS.STEP_LOG WHERE RUN_ID = :rid;
  IF (steps <> 14) THEN fails := ARRAY_APPEND(fails, steps || ' step numbers logged, expected 14'); END IF;
  SELECT COUNT(*) INTO :nb FROM SR_DB.APP.BRIEF WHERE RUN_ID = :rid AND STATUS = 'PUBLISHED';
  IF (nb <> 1) THEN fails := ARRAY_APPEND(fails, nb || ' published briefs, expected 1'); END IF;
  WHILE (sent = 0 AND i < 20) DO
    SELECT COUNT(*) INTO :sent FROM SR_DB.OPS.NOTIFY_LOG WHERE BRIEF_ID = :bid AND STATUS = 'SENT';
    IF (sent = 0) THEN
      CALL SYSTEM$WAIT(15);
    END IF;
    i := i + 1;
  END WHILE;
  IF (sent = 0) THEN fails := ARRAY_APPEND(fails, 'no SENT notification within 5 minutes'); END IF;
  RETURN ARRAY_TO_STRING(fails, '; ');
END;
$$;
SET Q = LAST_QUERY_ID();
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
SELECT $TEST_RUN_ID, $TEST_ID, $1 = '', IFF($1 = '', 0, ARRAY_SIZE(SPLIT($1, '; '))), TO_VARIANT($1)
FROM TABLE(RESULT_SCAN($Q)) WHERE $1 <> 'SKIPPED_NO_E2E';
