-- T-TOOL-04 (SR-042): for a ranked L4W_VS_YA shift with a distribution share, TOOL_WHAT_IF equals SP_WHAT_IF
-- (share_if_pts within 1e-9); TOOL_LATEST_BRIEF returns the newest PUBLISHED brief ID.
SET TEST_ID = 'T-TOOL-04';
EXECUTE IMMEDIATE $$
DECLARE
  fails ARRAY DEFAULT ARRAY_CONSTRUCT();
  note  VARCHAR DEFAULT '';
  sid   VARCHAR;
  br    VARCHAR;
  mk    VARCHAR;
  tool  VARCHAR;
  proc  VARIANT;
  res   VARCHAR;
  bid   VARCHAR;
BEGIN
  SELECT MAX(SHIFT_ID), MAX(BRAND), MAX(MARKET_ID) INTO :sid, :br, :mk FROM (
    SELECT r.SHIFT_ID, r.BRAND, r.MARKET_ID FROM SR_DB.APP.SHIFT_RANKED r
    JOIN SR_DB.APP.SHARE_BRIDGE b ON b.RUN_ID = r.RUN_ID AND b.SHIFT_ID = r.SHIFT_ID
    WHERE r.RUN_ID = $RUN_UNDER_TEST AND r.CMP_CODE = 'L4W_VS_YA' AND b.STATUS = 'OK' AND b.DS1 > 0
    ORDER BY r.RANK_NO LIMIT 1);
  IF (sid IS NULL) THEN
    note := '|skipped what-if: no ranked L4W_VS_YA shift with distribution share';
  ELSE
    CALL SR_DB.APP.TOOL_WHAT_IF(:br, :mk, 'DISTRIBUTION', 'BASE') INTO :tool;
    CALL SR_DB.APP.SP_WHAT_IF(:sid, 'DISTRIBUTION', 'BASE') INTO :proc;
    IF (PARSE_JSON(tool):share_if_pts IS NULL
        OR ABS(PARSE_JSON(tool):share_if_pts::FLOAT - GET(proc, 'share_if_pts')::FLOAT) > 1e-9) THEN
      fails := ARRAY_APPEND(fails, 'what-if differs: tool ' || LEFT(tool, 150) || ' proc ' || LEFT(TO_JSON(proc), 150));
    END IF;
  END IF;
  CALL SR_DB.APP.TOOL_LATEST_BRIEF('') INTO :res;
  SELECT BRIEF_ID INTO :bid FROM SR_DB.APP.BRIEF WHERE STATUS = 'PUBLISHED' ORDER BY PUBLISHED_AT DESC LIMIT 1;
  IF (COALESCE(PARSE_JSON(res):brief_id::VARCHAR, '') <> COALESCE(bid, '-')) THEN
    fails := ARRAY_APPEND(fails, 'latest brief ' || LEFT(res, 120) || ' expected ' || COALESCE(bid, 'none'));
  END IF;
  RETURN ARRAY_TO_STRING(fails, '; ') || note;
END;
$$;
SET Q = LAST_QUERY_ID();
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
SELECT $TEST_RUN_ID, $TEST_ID, SPLIT_PART($1, '|', 1) = '',
       IFF(SPLIT_PART($1, '|', 1) = '', 0, ARRAY_SIZE(SPLIT(SPLIT_PART($1, '|', 1), '; '))), TO_VARIANT($1)
FROM TABLE(RESULT_SCAN($Q));
