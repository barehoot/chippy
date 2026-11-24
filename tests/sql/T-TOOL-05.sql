-- T-TOOL-05 (SR-042): name resolution and input errors through a tool. A brand with one typo -> OK (the right
-- brand); an unknown brand -> NOT_FOUND with at most 3 candidates; a 3-letter prefix shared by two brands ->
-- AMBIGUOUS; comparison XYZ -> BAD_INPUT. Inputs are picked from the data so each case is unambiguous.
SET TEST_ID = 'T-TOOL-05';
EXECUTE IMMEDIATE $$
DECLARE
  fails  ARRAY DEFAULT ARRAY_CONSTRUCT();
  note   VARCHAR DEFAULT '';
  mk     VARCHAR;
  br     VARCHAR;
  typo   VARCHAR;
  prefix VARCHAR;
  res    VARCHAR;
  j      VARIANT;
BEGIN
  SELECT MARKET_ID INTO :mk FROM SR_DB.SEM.V_TOOL_BRIDGE WHERE CMP_CODE = 'L4W_VS_YA' AND IN_SCOPE AND D_SHARE IS NOT NULL
   GROUP BY MARKET_ID ORDER BY COUNT(*) DESC LIMIT 1;

  -- typo: change the last letter of a brand whose typo is within distance 2 of no other brand and inside no other name
  WITH b AS (SELECT DISTINCT BRAND FROM SR_DB.SEM.V_TOOL_BRIDGE WHERE CMP_CODE = 'L4W_VS_YA'),
  t AS (SELECT BRAND, LEFT(BRAND, LENGTH(BRAND) - 1) || IFF(RIGHT(UPPER(BRAND), 1) = 'Q', 'X', 'Q') AS TYPO
        FROM b WHERE LENGTH(BRAND) >= 6)
  SELECT MIN(t.BRAND), MIN(t.TYPO) INTO :br, :typo FROM t
   WHERE NOT EXISTS (SELECT 1 FROM b o WHERE o.BRAND <> t.BRAND
                       AND (EDITDISTANCE(UPPER(o.BRAND), UPPER(t.TYPO)) <= 2 OR CONTAINS(UPPER(o.BRAND), UPPER(t.TYPO))));
  IF (typo IS NULL) THEN
    note := note || '|skipped typo case: no suitable brand';
  ELSE
    CALL SR_DB.APP.TOOL_SHARE_FLOW(:typo, :mk, 'L4W_VS_YA') INTO :res;
    j := PARSE_JSON(res);
    IF (GET(j, 'error') IS NOT NULL AND GET(j, 'error')::VARCHAR <> 'NO_DATA') THEN
      fails := ARRAY_APPEND(fails, 'typo ' || typo || ' did not resolve: ' || LEFT(res, 150));
    END IF;
    IF (GET(j, 'error') IS NULL AND GET(j, 'brand')::VARCHAR <> br) THEN
      fails := ARRAY_APPEND(fails, 'typo ' || typo || ' resolved to ' || GET(j, 'brand')::VARCHAR || ', expected ' || br);
    END IF;
  END IF;

  CALL SR_DB.APP.TOOL_SHARE_FLOW('Zqxv Nonexistent Brand', :mk, 'L4W_VS_YA') INTO :res;
  j := PARSE_JSON(res);
  IF (COALESCE(GET(j, 'error')::VARCHAR, '') <> 'NOT_FOUND' OR ARRAY_SIZE(GET(j, 'candidates')) > 3) THEN
    fails := ARRAY_APPEND(fails, 'unknown brand: ' || LEFT(res, 150));
  END IF;

  -- prefix: three letters that start two or more brands and are not themselves a brand
  SELECT MIN(P) INTO :prefix FROM (
    SELECT LEFT(UPPER(BRAND), 3) AS P FROM (SELECT DISTINCT BRAND FROM SR_DB.SEM.V_TOOL_BRIDGE WHERE CMP_CODE = 'L4W_VS_YA')
    WHERE LENGTH(BRAND) > 3 GROUP BY P HAVING COUNT(*) >= 2)
   WHERE P NOT IN (SELECT UPPER(BRAND) FROM SR_DB.SEM.V_TOOL_BRIDGE);
  IF (prefix IS NULL) THEN
    note := note || '|skipped prefix case: no shared prefix';
  ELSE
    CALL SR_DB.APP.TOOL_SHARE_FLOW(:prefix, :mk, 'L4W_VS_YA') INTO :res;
    IF (COALESCE(PARSE_JSON(res):error::VARCHAR, '') <> 'AMBIGUOUS') THEN
      fails := ARRAY_APPEND(fails, 'prefix ' || prefix || ': ' || LEFT(res, 150));
    END IF;
  END IF;

  CALL SR_DB.APP.TOOL_GET_SHARE_BRIDGE('any', :mk, 'XYZ') INTO :res;
  IF (COALESCE(PARSE_JSON(res):error::VARCHAR, '') <> 'BAD_INPUT') THEN
    fails := ARRAY_APPEND(fails, 'comparison XYZ: ' || LEFT(res, 150));
  END IF;
  RETURN ARRAY_TO_STRING(fails, '; ') || note;
END;
$$;
SET Q = LAST_QUERY_ID();
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
SELECT $TEST_RUN_ID, $TEST_ID, SPLIT_PART($1, '|', 1) = '',
       IFF(SPLIT_PART($1, '|', 1) = '', 0, ARRAY_SIZE(SPLIT(SPLIT_PART($1, '|', 1), '; '))), TO_VARIANT($1)
FROM TABLE(RESULT_SCAN($Q));
