-- T-SRC-03 (SR-003): the adapter reaches AS_OF_WEEK_END; the newest capability row has a mode A-D; with the
-- setting one week past all data, SP_CAPABILITY_CHECK raises NO_DATA (E01). The setting is restored, and its
-- UPDATED_AT is left untouched so the stream task does not mistake the test for a replay.
SET TEST_ID = 'T-SRC-03';
EXECUTE IMMEDIATE $$
DECLARE
  fails  ARRAY DEFAULT ARRAY_CONSTRUCT();
  orig   VARIANT;
  as_of  DATE;
  max_wk DATE;
  all_wk DATE;
  mode   VARCHAR;
  raised BOOLEAN DEFAULT FALSE;
BEGIN
  SELECT SETTING_VALUE, SETTING_VALUE::VARCHAR::DATE INTO :orig, :as_of
    FROM SR_DB.OPS.SETTINGS WHERE SETTING_KEY = 'AS_OF_WEEK_END';
  SELECT MAX(WEEK_END_DATE) INTO :max_wk FROM SR_DB.SRC.V_SRC_FACT_WEEKLY;
  IF (max_wk IS NULL OR max_wk <> as_of) THEN
    fails := ARRAY_APPEND(fails, 'adapter latest week ' || COALESCE(max_wk::VARCHAR, 'NULL') || ' <> AS_OF_WEEK_END ' || as_of::VARCHAR);
  END IF;

  CALL SR_DB.APP.SP_CAPABILITY_CHECK();
  SELECT MAX_BRIDGE_MODE INTO :mode FROM SR_DB.OPS.CAPABILITY ORDER BY CHECKED_AT DESC LIMIT 1;
  IF (mode IS NULL OR mode NOT IN ('A', 'B', 'C', 'D')) THEN
    fails := ARRAY_APPEND(fails, 'capability mode ' || COALESCE(mode, 'NULL'));
  END IF;

  SELECT MAX(WEEK_END_DATE) INTO :all_wk FROM SR_DB.SRC.V_SRC_FACT_WEEKLY_ALL;
  UPDATE SR_DB.OPS.SETTINGS SET SETTING_VALUE = TO_VARIANT(TO_CHAR(DATEADD(week, 1, :all_wk), 'YYYY-MM-DD'))
   WHERE SETTING_KEY = 'AS_OF_WEEK_END';
  BEGIN
    CALL SR_DB.APP.SP_CAPABILITY_CHECK();
  EXCEPTION
    WHEN OTHER THEN
      raised := (SQLERRM ILIKE '%NO_DATA%');
  END;
  UPDATE SR_DB.OPS.SETTINGS SET SETTING_VALUE = :orig WHERE SETTING_KEY = 'AS_OF_WEEK_END';
  IF (NOT raised) THEN
    fails := ARRAY_APPEND(fails, 'SP_CAPABILITY_CHECK did not raise NO_DATA past the data');
  END IF;
  RETURN ARRAY_TO_STRING(fails, '; ');
END;
$$;
SET Q = LAST_QUERY_ID();
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
SELECT $TEST_RUN_ID, $TEST_ID, $1 = '', IFF($1 = '', 0, ARRAY_SIZE(SPLIT($1, '; '))), TO_VARIANT($1)
FROM TABLE(RESULT_SCAN($Q));
