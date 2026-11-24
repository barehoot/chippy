-- T-TOOL-02 (SR-042): for the latest run's ranked shifts, TOOL_CHECK_ARTEFACT returns the shift's ARTEFACT_LABEL;
-- a market outside the scope returns NOT_CHECKED (skipped, and noted, if every market is in scope).
SET TEST_ID = 'T-TOOL-02';
EXECUTE IMMEDIATE $$
DECLARE
  fails ARRAY DEFAULT ARRAY_CONSTRUCT();
  note  VARCHAR DEFAULT '';
  res   VARCHAR;
  outm  VARCHAR;
  outc  VARCHAR;
  rs    RESULTSET DEFAULT (SELECT BRAND, MARKET_ID, CMP_CODE, ARTEFACT_LABEL FROM SR_DB.APP.SHIFT_RANKED
                           WHERE RUN_ID = $RUN_UNDER_TEST ORDER BY RANK_NO LIMIT 10);
  c1 CURSOR FOR rs;
BEGIN
  FOR r IN c1 DO
    LET br VARCHAR := r.BRAND;
    LET mk VARCHAR := r.MARKET_ID;
    LET cp VARCHAR := r.CMP_CODE;
    LET lb VARCHAR := r.ARTEFACT_LABEL;
    CALL SR_DB.APP.TOOL_CHECK_ARTEFACT(:mk, :cp, :br) INTO :res;
    IF (COALESCE(PARSE_JSON(res):label::VARCHAR, '') <> lb) THEN
      fails := ARRAY_APPEND(fails, br || '/' || mk || '/' || cp || ' expected ' || lb || ': ' || LEFT(res, 200));
    END IF;
  END FOR;
  SELECT MAX(MARKET_ID), MAX(CMP_CODE) INTO :outm, :outc
    FROM (SELECT MARKET_ID, CMP_CODE FROM SR_DB.SEM.V_TOOL_BRIDGE WHERE NOT IN_SCOPE LIMIT 1);
  IF (outm IS NULL) THEN
    note := '|skipped: every market is in scope';
  ELSE
    CALL SR_DB.APP.TOOL_CHECK_ARTEFACT(:outm, :outc, '') INTO :res;
    IF (COALESCE(PARSE_JSON(res):label::VARCHAR, '') <> 'NOT_CHECKED') THEN
      fails := ARRAY_APPEND(fails, 'outside market ' || outm || ': ' || LEFT(res, 200));
    END IF;
  END IF;
  RETURN ARRAY_TO_STRING(fails, '; ') || note;
END;
$$;
SET Q = LAST_QUERY_ID();
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
SELECT $TEST_RUN_ID, $TEST_ID, SPLIT_PART($1, '|', 1) = '',
       IFF(SPLIT_PART($1, '|', 1) = '', 0, ARRAY_SIZE(SPLIT(SPLIT_PART($1, '|', 1), '; '))), TO_VARIANT($1)
FROM TABLE(RESULT_SCAN($Q));
