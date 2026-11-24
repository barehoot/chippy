-- T-ART-05 (SR-024, E2E): for each row of TEST.FX_DEMO_EVENTS, after replaying to its week the expected rule fires
-- on that market and comparison, and no shift there is in the brief (held back). The triggered task is suspended
-- while the test replays, and the as-of week is put back at the end.
SET TEST_ID = 'T-ART-05';
EXECUTE IMMEDIATE $$
DECLARE
  fails  ARRAY DEFAULT ARRAY_CONSTRUCT();
  orig   VARCHAR;
  rid    VARCHAR;
  n_rule NUMBER;
  n_sel  NUMBER;
  ev     RESULTSET DEFAULT (SELECT EVENT_ID, AS_OF_WEEK, CMP_CODE, MARKET_ID, EXPECTED_RULE_ID
                            FROM SR_DB.TEST.FX_DEMO_EVENTS ORDER BY AS_OF_WEEK);
  c1 CURSOR FOR ev;
BEGIN
  IF (NOT $RUN_E2E) THEN RETURN 'SKIPPED_NO_E2E'; END IF;
  SELECT SETTING_VALUE::VARCHAR INTO :orig FROM SR_DB.OPS.SETTINGS WHERE SETTING_KEY = 'AS_OF_WEEK_END';
  ALTER TASK SR_DB.OPS.T_RUN_WEEK SUSPEND;
  FOR e IN c1 DO
    LET eid VARCHAR := e.EVENT_ID;
    LET wk  VARCHAR := e.AS_OF_WEEK::VARCHAR;
    LET cmp VARCHAR := e.CMP_CODE;
    LET mkt VARCHAR := e.MARKET_ID;
    LET rul VARCHAR := e.EXPECTED_RULE_ID;
    CALL SR_DB.APP.SP_REPLAY_RESET(:wk);
    CALL SR_DB.APP.SP_RUN_WEEK('REPLAY', TRUE) INTO :rid;
    SELECT COUNT(*) INTO :n_rule FROM SR_DB.APP.ARTEFACT_CHECK
     WHERE RUN_ID = :rid AND CMP_CODE = :cmp AND MARKET_ID = :mkt AND RULE_ID = :rul;
    SELECT COUNT(*) INTO :n_sel FROM SR_DB.APP.SHIFT_RANKED
     WHERE RUN_ID = :rid AND CMP_CODE = :cmp AND MARKET_ID = :mkt AND SELECTED;
    IF (n_rule = 0) THEN fails := ARRAY_APPEND(fails, eid || ': ' || rul || ' did not fire'); END IF;
    IF (n_sel > 0) THEN fails := ARRAY_APPEND(fails, eid || ': ' || n_sel || ' shifts in that market were not held back'); END IF;
  END FOR;
  CALL SR_DB.APP.SP_REPLAY_RESET(:orig);
  ALTER TASK SR_DB.OPS.T_RUN_WEEK RESUME;
  RETURN ARRAY_TO_STRING(fails, '; ');
EXCEPTION
  WHEN OTHER THEN
    CALL SR_DB.APP.SP_REPLAY_RESET(:orig);
    ALTER TASK SR_DB.OPS.T_RUN_WEEK RESUME;
    RETURN 'raised: ' || LEFT(SQLERRM, 200);
END;
$$;
SET Q = LAST_QUERY_ID();
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
SELECT $TEST_RUN_ID, $TEST_ID, $1 = '', IFF($1 = '', 0, ARRAY_SIZE(SPLIT($1, '; '))), TO_VARIANT($1)
FROM TABLE(RESULT_SCAN($Q)) WHERE $1 <> 'SKIPPED_NO_E2E';
