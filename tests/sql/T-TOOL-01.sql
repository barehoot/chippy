-- T-TOOL-01 (SR-042): for 5 ranked brand x market pairs of the latest run, TOOL_GET_SHARE_BRIDGE returns change_pts
-- equal to 100 x D_SHARE in SEM.V_TOOL_BRIDGE within 1e-9.
SET TEST_ID = 'T-TOOL-01';
EXECUTE IMMEDIATE $$
DECLARE
  fails ARRAY DEFAULT ARRAY_CONSTRUCT();
  res   VARCHAR;
  want  FLOAT;
  rs    RESULTSET DEFAULT (SELECT BRAND, MARKET_ID, CMP_CODE FROM SR_DB.APP.SHIFT_RANKED
                           WHERE RUN_ID = $RUN_UNDER_TEST ORDER BY RANK_NO LIMIT 5);
  c1 CURSOR FOR rs;
BEGIN
  FOR r IN c1 DO
    LET br VARCHAR := r.BRAND;
    LET mk VARCHAR := r.MARKET_ID;
    LET cp VARCHAR := r.CMP_CODE;
    CALL SR_DB.APP.TOOL_GET_SHARE_BRIDGE(:br, :mk, :cp) INTO :res;
    SELECT 100 * SUM(D_SHARE) INTO :want FROM SR_DB.SEM.V_TOOL_BRIDGE WHERE BRAND = :br AND MARKET_ID = :mk AND CMP_CODE = :cp;
    IF (PARSE_JSON(res):change_pts IS NULL OR ABS(PARSE_JSON(res):change_pts::FLOAT - want) > 1e-9) THEN
      fails := ARRAY_APPEND(fails, br || '/' || mk || '/' || cp || ': ' || LEFT(res, 200));
    END IF;
  END FOR;
  RETURN ARRAY_TO_STRING(fails, '; ');
END;
$$;
SET Q = LAST_QUERY_ID();
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
SELECT $TEST_RUN_ID, $TEST_ID, $1 = '', IFF($1 = '', 0, ARRAY_SIZE(SPLIT($1, '; '))), TO_VARIANT($1)
FROM TABLE(RESULT_SCAN($Q));
