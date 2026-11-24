-- T-WI-01 (SR-029): for the top ranked shift with a distribution share, DISTRIBUTION with BASE gives
-- share_if_pts = 100 x SH1 x DS0 / DS1 within 1e-9; PROMO on a shift below mode A returns an error object.
-- A part with no qualifying shift in the run passes (it is reported in DETAIL as skipped).
SET TEST_ID = 'T-WI-01';
EXECUTE IMMEDIATE $$
DECLARE
  fails  ARRAY DEFAULT ARRAY_CONSTRUCT();
  notes  ARRAY DEFAULT ARRAY_CONSTRUCT();
  sid    VARCHAR;
  res    VARIANT;
  want   FLOAT;
BEGIN
  SELECT MAX(SHIFT_ID) INTO :sid FROM (
    SELECT b.SHIFT_ID FROM SR_DB.APP.SHARE_BRIDGE b
    JOIN SR_DB.APP.SHIFT_RANKED r ON r.RUN_ID = b.RUN_ID AND r.SHIFT_ID = b.SHIFT_ID
    WHERE b.RUN_ID = $RUN_UNDER_TEST AND b.STATUS = 'OK' AND b.DS1 > 0 AND b.DS0 > 0
    ORDER BY r.RANK_NO LIMIT 1);
  IF (sid IS NULL) THEN
    notes := ARRAY_APPEND(notes, 'skipped: no shift with distribution share');
  ELSE
    CALL SR_DB.APP.SP_WHAT_IF(:sid, 'DISTRIBUTION', 'BASE') INTO :res;
    SELECT 100 * SH1 * DS0 / DS1 INTO :want FROM SR_DB.APP.SHARE_BRIDGE WHERE SHIFT_ID = :sid;
    IF (GET(res, 'share_if_pts') IS NULL OR ABS(GET(res, 'share_if_pts')::FLOAT - want) > 1e-9) THEN
      fails := ARRAY_APPEND(fails, 'DISTRIBUTION/BASE on ' || sid || ' returned ' || TO_JSON(res));
    END IF;
  END IF;

  sid := NULL;
  SELECT MAX(SHIFT_ID) INTO :sid FROM (
    SELECT SHIFT_ID FROM SR_DB.APP.SHARE_BRIDGE
    WHERE RUN_ID = $RUN_UNDER_TEST AND STATUS = 'OK' AND MODE IN ('B', 'C') LIMIT 1);
  IF (sid IS NULL) THEN
    notes := ARRAY_APPEND(notes, 'skipped: no mode B or C shift');
  ELSE
    CALL SR_DB.APP.SP_WHAT_IF(:sid, 'PROMO', 'BASE') INTO :res;
    IF (GET(res, 'error') IS NULL) THEN
      fails := ARRAY_APPEND(fails, 'PROMO on mode-' || 'B/C shift ' || sid || ' did not return an error');
    END IF;
  END IF;
  RETURN ARRAY_TO_STRING(fails, '; ') || IFF(ARRAY_SIZE(notes) > 0, '|' || ARRAY_TO_STRING(notes, '; '), '');
END;
$$;
SET Q = LAST_QUERY_ID();
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
SELECT $TEST_RUN_ID, $TEST_ID, SPLIT_PART($1, '|', 1) = '',
       IFF(SPLIT_PART($1, '|', 1) = '', 0, ARRAY_SIZE(SPLIT(SPLIT_PART($1, '|', 1), '; '))), TO_VARIANT($1)
FROM TABLE(RESULT_SCAN($Q));
