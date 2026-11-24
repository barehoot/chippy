-- T-RANK-02 (SR-026, E2E): over two consecutive replay weeks, a shift selected in week 1 that recurs in week 2 with
-- the same sign and has grown by less than SUPPRESS_GROWTH is SUPPRESSED in week 2. The test replays the week
-- before the current as-of week and the current week, with the triggered task suspended, and restores the setting.
SET TEST_ID = 'T-RANK-02';
EXECUTE IMMEDIATE $$
DECLARE
  fails ARRAY DEFAULT ARRAY_CONSTRUCT();
  orig  VARCHAR;
  prev  VARCHAR;
  r1    VARCHAR;
  r2    VARCHAR;
  n_bad NUMBER;
  n_chk NUMBER;
BEGIN
  IF (NOT $RUN_E2E) THEN RETURN 'SKIPPED_NO_E2E'; END IF;
  SELECT SETTING_VALUE::VARCHAR INTO :orig FROM SR_DB.OPS.SETTINGS WHERE SETTING_KEY = 'AS_OF_WEEK_END';
  SELECT MAX(WEEK_END_DATE)::VARCHAR INTO :prev FROM SR_DB.SRC.V_SRC_FACT_WEEKLY_ALL WHERE WEEK_END_DATE < TO_DATE(:orig);
  ALTER TASK SR_DB.OPS.T_RUN_WEEK SUSPEND;
  CALL SR_DB.APP.SP_REPLAY_RESET(:prev);
  CALL SR_DB.APP.SP_RUN_WEEK('REPLAY', TRUE) INTO :r1;
  CALL SR_DB.APP.SP_REPLAY_NEXT_WEEK();
  CALL SR_DB.APP.SP_RUN_WEEK('REPLAY', TRUE) INTO :r2;
  -- every week-1 selection that recurs with the same sign and little growth must be suppressed in week 2
  SELECT COUNT(*), COUNT_IF(NOT b.SUPPRESSED) INTO :n_chk, :n_bad
    FROM SR_DB.APP.SHIFT_RANKED a
    JOIN SR_DB.APP.SHIFT_RANKED b
      ON b.RUN_ID = :r2 AND b.MARKET_ID = a.MARKET_ID AND b.BRAND = a.BRAND AND b.CMP_CODE = a.CMP_CODE
     AND SIGN(b.D_SHARE) = SIGN(a.D_SHARE)
   WHERE a.RUN_ID = :r1 AND a.SELECTED
     AND ABS(b.D_SHARE) < ABS(a.D_SHARE) * (1 + (SELECT SETTING_VALUE::FLOAT FROM SR_DB.OPS.SETTINGS WHERE SETTING_KEY = 'SUPPRESS_GROWTH'));
  IF (n_bad > 0) THEN fails := ARRAY_APPEND(fails, n_bad || ' of ' || n_chk || ' repeats were not suppressed'); END IF;
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
