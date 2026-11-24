-- T-FP-01 (SR-030): in the latest fact pack every fact has v, u, d and src; every fact ID used under shifts,
-- held_back and watchlist exists; N_FACTS matches; and 10 random facts equal the column their src names,
-- re-read from that table (relative tolerance 1e-9).
SET TEST_ID = 'T-FP-01';
EXECUTE IMMEDIATE $$
DECLARE
  fails     ARRAY DEFAULT ARRAY_CONSTRUCT();
  bid       VARCHAR;
  n_facts   NUMBER;
  n_actual  NUMBER;
  n_bad     NUMBER;
  n_missing NUMBER;
  q         VARCHAR;
  got       FLOAT;
  res       RESULTSET;
  sample    RESULTSET DEFAULT (
    SELECT f.KEY AS FID, f.VALUE:v::FLOAT AS V, f.VALUE:src::VARCHAR AS SRC
    FROM SR_DB.APP.FACT_PACK p, LATERAL FLATTEN(INPUT => p.PACK:facts) f
    WHERE p.BRIEF_ID = (SELECT BRIEF_ID FROM SR_DB.APP.FACT_PACK ORDER BY CREATED_AT DESC LIMIT 1)
    ORDER BY RANDOM() LIMIT 10);
  c1 CURSOR FOR sample;
BEGIN
  SELECT BRIEF_ID, N_FACTS INTO :bid, :n_facts FROM SR_DB.APP.FACT_PACK ORDER BY CREATED_AT DESC LIMIT 1;
  IF (bid IS NULL) THEN
    RETURN 'no fact pack';
  END IF;

  SELECT COUNT(*), COUNT_IF(f.VALUE:v IS NULL OR f.VALUE:u IS NULL OR f.VALUE:d IS NULL OR f.VALUE:src IS NULL)
    INTO :n_actual, :n_bad
    FROM SR_DB.APP.FACT_PACK p, LATERAL FLATTEN(INPUT => p.PACK:facts) f WHERE p.BRIEF_ID = :bid;
  IF (n_bad > 0) THEN fails := ARRAY_APPEND(fails, n_bad || ' facts lack v, u, d or src'); END IF;
  IF (n_actual <> n_facts) THEN fails := ARRAY_APPEND(fails, 'N_FACTS ' || n_facts || ' <> ' || n_actual || ' facts'); END IF;

  SELECT COUNT(*) INTO :n_missing FROM (
    SELECT u.VALUE::VARCHAR AS FID
    FROM SR_DB.APP.FACT_PACK p, LATERAL FLATTEN(INPUT => p.PACK, RECURSIVE => TRUE) u
    WHERE p.BRIEF_ID = :bid
      AND u.KEY IN ('share_now', 'share_before', 'delta', 'value_at_stake', 'fact', 'lever_chg', 'projected')
      AND NOT IS_NULL_VALUE(u.VALUE)
  ) x
  WHERE x.FID NOT IN (SELECT f.KEY FROM SR_DB.APP.FACT_PACK p, LATERAL FLATTEN(INPUT => p.PACK:facts) f WHERE p.BRIEF_ID = :bid);
  IF (n_missing > 0) THEN fails := ARRAY_APPEND(fails, n_missing || ' fact IDs used but not defined'); END IF;

  FOR r IN c1 DO
    LET fid VARCHAR := r.FID;
    LET v FLOAT := r.V;
    LET s VARCHAR := r.SRC;
    IF (NOT REGEXP_LIKE(SPLIT_PART(s, '#', 1), '^[A-Z_]+\\.[A-Z_]+$')) THEN
      fails := ARRAY_APPEND(fails, fid || ': unparseable src ' || s);
      CONTINUE;
    END IF;
    SELECT 'SELECT (' || MAX(IFF(STARTSWITH(t.VALUE, 'col='), SUBSTR(t.VALUE, 5), NULL)) || ')::FLOAT AS GOT FROM SR_DB.'
           || SPLIT_PART(:s, '#', 1) || ' WHERE '
           || LISTAGG(IFF(STARTSWITH(t.VALUE, 'col=') OR t.VALUE = '', NULL,
                          SPLIT_PART(t.VALUE, '=', 1) || ' = '''
                          || REPLACE(SUBSTR(t.VALUE, POSITION('=' IN t.VALUE) + 1), '''', '''''') || ''''), ' AND ')
           || ' LIMIT 1'
      INTO :q
      FROM TABLE(SPLIT_TO_TABLE(SPLIT_PART(:s, '#', 2), ';')) t;
    IF (NOT REGEXP_LIKE(q, '^SELECT \\([A-Z_0-9*]+\\)::FLOAT AS GOT FROM .*')) THEN
      fails := ARRAY_APPEND(fails, fid || ': unsafe or unparseable col in ' || s);
      CONTINUE;
    END IF;
    got := NULL;
    res := (EXECUTE IMMEDIATE :q);
    LET c2 CURSOR FOR res;
    FOR r2 IN c2 DO
      got := r2.GOT;
    END FOR;
    IF (got IS NULL OR ABS(got - v) > 1e-9 * GREATEST(1, ABS(v))) THEN
      fails := ARRAY_APPEND(fails, fid || ': pack ' || v::VARCHAR || ' vs ' || COALESCE(got::VARCHAR, 'no row') || ' at ' || s);
    END IF;
  END FOR;
  RETURN ARRAY_TO_STRING(fails, '; ');
END;
$$;
SET Q = LAST_QUERY_ID();
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
SELECT $TEST_RUN_ID, $TEST_ID, $1 = '', IFF($1 = '', 0, ARRAY_SIZE(SPLIT($1, '; '))), TO_VARIANT($1)
FROM TABLE(RESULT_SCAN($Q));
