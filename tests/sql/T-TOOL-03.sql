-- T-TOOL-03 (SR-042): for the 5 largest losing brands in the scope markets, TOOL_SHARE_FLOW's flows sum to the
-- brand's share change in points within 1e-6.
SET TEST_ID = 'T-TOOL-03';
EXECUTE IMMEDIATE $$
DECLARE
  fails ARRAY DEFAULT ARRAY_CONSTRUCT();
  res   VARCHAR;
  got   FLOAT;
  rs    RESULTSET DEFAULT (SELECT BRAND, MARKET_ID, CMP_CODE, 100 * SUM(D_SHARE) AS PTS FROM SR_DB.SEM.V_TOOL_BRIDGE
                           WHERE IN_SCOPE AND CMP_CODE = 'L4W_VS_YA' AND D_SHARE IS NOT NULL
                           GROUP BY BRAND, MARKET_ID, CMP_CODE HAVING SUM(D_SHARE) < 0 ORDER BY PTS LIMIT 5);
  c1 CURSOR FOR rs;
BEGIN
  FOR r IN c1 DO
    LET br  VARCHAR := r.BRAND;
    LET mk  VARCHAR := r.MARKET_ID;
    LET cp  VARCHAR := r.CMP_CODE;
    LET pts FLOAT   := r.PTS;
    CALL SR_DB.APP.TOOL_SHARE_FLOW(:br, :mk, :cp) INTO :res;
    SELECT SUM(f.value:pts::FLOAT) INTO :got FROM TABLE(FLATTEN(INPUT => PARSE_JSON(:res):flows)) f;
    IF (got IS NULL OR ABS(got - ABS(pts)) > 1e-6) THEN
      fails := ARRAY_APPEND(fails, br || '/' || mk || ' change ' || pts::VARCHAR || ' flows ' || COALESCE(got::VARCHAR, 'none'));
    END IF;
  END FOR;
  RETURN ARRAY_TO_STRING(fails, '; ');
END;
$$;
SET Q = LAST_QUERY_ID();
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
SELECT $TEST_RUN_ID, $TEST_ID, $1 = '', IFF($1 = '', 0, ARRAY_SIZE(SPLIT($1, '; '))), TO_VARIANT($1)
FROM TABLE(RESULT_SCAN($Q));
