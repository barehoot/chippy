-- SR-024 · L6 artefact gate: rules R1-R6, each one INSERT ... SELECT with an evidence object that names its source.
-- Label per shift (applied in SP_RANK): any HIGH rule on its market or brand -> POSSIBLE_DATA_EFFECT,
-- otherwise any MEDIUM -> MIXED, otherwise MARKET_MOVE. Rules cover all four comparisons in the scope markets,
-- so the agent's check_artefact tool can answer for any of them.
--
-- | Rule        | Level  | Fires when                                                                 | Severity |
-- | R1_COVERAGE | market | store count moves >= ART_STORE_CHG (universe view), or proxy: category TDP | HIGH /   |
-- |             |        | per week log-change >= ART_CAT_TDP_JUMP while value per TDP <= _SPPD_FLAT  | MEDIUM   |
-- | R2_FEED     | parent | a child market has category sales in one period and none in the other, or  | HIGH     |
-- |             |        | fewer weeks than its parent in either period (partial feed gap, B12)       |          |
-- | R3_RESTATE  | market | a week's ROW_HASH differs from the previous successful run's snapshot      | HIGH if  |
-- |             |        |                                                                            | >= ART_RESTATE_PCT |
-- | R4_RECODE   | brand  | exiting and entering items' sales match within ART_RECODE_TOL, each        | MEDIUM   |
-- |             |        | >= ART_RECODE_MIN_SHARE of brand base sales                                |          |
-- | R5_SPIKE    | market | a current week sits > ART_SPIKE_K std devs from the trailing 13-week mean  | MEDIUM   |
-- | R6_GAP      | market | category weeks in either period fall short of the expected count           | HIGH     |
USE ROLE SR_DEV;
CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_ARTEFACT(P_RUN_ID VARCHAR)
RETURNS NUMBER
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  n            NUMBER DEFAULT 0;
  parent       VARCHAR;
  category     VARCHAR;
  has_universe BOOLEAN DEFAULT FALSE;
  prev_run     VARCHAR;
BEGIN
  EXECUTE IMMEDIATE 'ALTER SESSION SET QUERY_TAG = ''SR|run=' || P_RUN_ID || '|step=ARTEFACT''';
  SELECT SR_DB.OPS.CFG('SCOPE_PARENT_MARKET')::VARCHAR, SR_DB.OPS.CFG('SCOPE_CATEGORY')::VARCHAR INTO :parent, :category;
  SELECT COALESCE(BOOLOR_AGG(HAS_UNIVERSE), FALSE) INTO :has_universe
    FROM (SELECT HAS_UNIVERSE FROM SR_DB.OPS.CAPABILITY ORDER BY CHECKED_AT DESC LIMIT 1);
  DELETE FROM SR_DB.APP.ARTEFACT_CHECK WHERE RUN_ID = :P_RUN_ID;

  -- R1_COVERAGE, universe version (HIGH). Dynamic SQL, so the procedure compiles without the optional view.
  IF (has_universe) THEN
    EXECUTE IMMEDIATE '
      INSERT INTO SR_DB.APP.ARTEFACT_CHECK (RUN_ID, CMP_CODE, MARKET_ID, CATEGORY, BRAND, RULE_ID, SEVERITY, EVIDENCE)
      WITH cmp AS (
        SELECT column1 AS CMP_CODE, column2 AS CUR_P, column3 AS BASE_P
        FROM VALUES (''L4W_VS_YA'',''L4W'',''L4W_YA''), (''L4W_VS_PP'',''L4W'',''P4W''),
                    (''L12W_VS_YA'',''L12W'',''L12W_YA''), (''L52W_VS_YA'',''L52W'',''L52W_YA''))
      , st AS (
        SELECT cmp.CMP_CODE, u.MARKET_ID,
               AVG(IFF(pw.PERIOD_CODE = cmp.CUR_P,  u.STORE_COUNT, NULL)) AS STORES_CUR,
               AVG(IFF(pw.PERIOD_CODE = cmp.BASE_P, u.STORE_COUNT, NULL)) AS STORES_BASE
        FROM SR_DB.SRC.V_SRC_MARKET_UNIVERSE u
        JOIN SR_DB.CORE.DT_PERIOD_WEEK pw ON pw.WEEK_END_DATE = u.WEEK_END_DATE
        JOIN cmp ON pw.PERIOD_CODE IN (cmp.CUR_P, cmp.BASE_P)
        WHERE u.MARKET_ID IN (SELECT MARKET_ID FROM SR_DB.SRC.V_SRC_MARKET WHERE MARKET_ID = ? OR PARENT_MARKET_ID = ?)
        GROUP BY cmp.CMP_CODE, u.MARKET_ID)
      SELECT ?, st.CMP_CODE, st.MARKET_ID, ?, NULL, ''R1_COVERAGE'', ''HIGH'',
             OBJECT_CONSTRUCT(''stores_cur'', st.STORES_CUR, ''stores_base'', st.STORES_BASE,
                              ''change'', st.STORES_CUR / st.STORES_BASE - 1, ''threshold'', SR_DB.OPS.CFG(''ART_STORE_CHG'')::FLOAT,
                              ''source'', ''SRC.V_SRC_MARKET_UNIVERSE'')
      FROM st
      WHERE st.STORES_BASE > 0 AND ABS(st.STORES_CUR / st.STORES_BASE - 1) >= SR_DB.OPS.CFG(''ART_STORE_CHG'')::FLOAT'
    USING (parent, parent, P_RUN_ID, category);
    n := n + SQLROWCOUNT;
  ELSE
    -- R1_COVERAGE, proxy version (MEDIUM): distribution jumps while sales per point stay flat
    INSERT INTO SR_DB.APP.ARTEFACT_CHECK (RUN_ID, CMP_CODE, MARKET_ID, CATEGORY, BRAND, RULE_ID, SEVERITY, EVIDENCE)
    -- cmp: the comparisons and their periods
    WITH cmp AS (
      SELECT column1 AS CMP_CODE, column2 AS CUR_P, column3 AS BASE_P
      FROM VALUES ('L4W_VS_YA','L4W','L4W_YA'), ('L4W_VS_PP','L4W','P4W'), ('L12W_VS_YA','L12W','L12W_YA'), ('L52W_VS_YA','L52W','L52W_YA')
    ),
    -- p: category TDP per week and value per TDP point, both periods
    p AS (
      SELECT cmp.CMP_CODE, c1.MARKET_ID, c1.CATEGORY,
             c1.CAT_TDP_SUM / NULLIF(c1.N_WEEKS, 0) AS TDPW1, c0.CAT_TDP_SUM / NULLIF(c0.N_WEEKS, 0) AS TDPW0,
             c1.CAT_VALUE_SALES / NULLIF(c1.CAT_TDP_SUM, 0) AS SPPD1, c0.CAT_VALUE_SALES / NULLIF(c0.CAT_TDP_SUM, 0) AS SPPD0
      FROM cmp
      JOIN SR_DB.CORE.DT_CAT_PERIOD c1 ON c1.PERIOD_CODE = cmp.CUR_P
      JOIN SR_DB.CORE.DT_CAT_PERIOD c0 ON c0.PERIOD_CODE = cmp.BASE_P AND c0.MARKET_ID = c1.MARKET_ID AND c0.CATEGORY = c1.CATEGORY
      WHERE c1.MARKET_ID IN (SELECT MARKET_ID FROM SR_DB.SRC.V_SRC_MARKET WHERE MARKET_ID = :parent OR PARENT_MARKET_ID = :parent)
    )
    SELECT :P_RUN_ID, p.CMP_CODE, p.MARKET_ID, p.CATEGORY, NULL, 'R1_COVERAGE', 'MEDIUM',
           OBJECT_CONSTRUCT('tdp_per_week_cur', p.TDPW1, 'tdp_per_week_base', p.TDPW0, 'tdp_log_change', LN(p.TDPW1 / p.TDPW0),
                            'sales_per_point_log_change', LN(p.SPPD1 / p.SPPD0), 'source', 'CORE.DT_CAT_PERIOD (proxy: no store universe)')
    FROM p
    WHERE p.TDPW1 > 0 AND p.TDPW0 > 0 AND p.SPPD1 > 0 AND p.SPPD0 > 0
      AND ABS(LN(p.TDPW1 / p.TDPW0)) >= SR_DB.OPS.CFG('ART_CAT_TDP_JUMP')::FLOAT
      AND ABS(LN(p.SPPD1 / p.SPPD0)) <= SR_DB.OPS.CFG('ART_CAT_SPPD_FLAT')::FLOAT;
    n := n + SQLROWCOUNT;
  END IF;

  -- R2_FEED: a child retailer present in one period and absent in the other, or present with fewer weeks than its
  -- parent in either period (a partial feed gap still moves the parent total), flagged on the parent (B12)
  INSERT INTO SR_DB.APP.ARTEFACT_CHECK (RUN_ID, CMP_CODE, MARKET_ID, CATEGORY, BRAND, RULE_ID, SEVERITY, EVIDENCE)
  SELECT :P_RUN_ID, cmp.CMP_CODE, m.PARENT_MARKET_ID, :category, NULL, 'R2_FEED', 'HIGH',
         OBJECT_CONSTRUCT('child_market', m.MARKET_NAME, 'child_market_id', m.MARKET_ID,
                          'sales_cur', COALESCE(c1.CAT_VALUE_SALES, 0), 'sales_base', COALESCE(c0.CAT_VALUE_SALES, 0),
                          'weeks_cur', COALESCE(c1.N_WEEKS, 0), 'weeks_base', COALESCE(c0.N_WEEKS, 0),
                          'parent_weeks_cur', p1.N_WEEKS, 'parent_weeks_base', p0.N_WEEKS,
                          'source', 'CORE.DT_CAT_PERIOD')
  FROM SR_DB.SRC.V_SRC_MARKET m
  CROSS JOIN (SELECT column1 AS CMP_CODE, column2 AS CUR_P, column3 AS BASE_P
              FROM VALUES ('L4W_VS_YA','L4W','L4W_YA'), ('L4W_VS_PP','L4W','P4W'),
                          ('L12W_VS_YA','L12W','L12W_YA'), ('L52W_VS_YA','L52W','L52W_YA')) cmp
  LEFT JOIN SR_DB.CORE.DT_CAT_PERIOD c1 ON c1.MARKET_ID = m.MARKET_ID AND c1.PERIOD_CODE = cmp.CUR_P  AND c1.CATEGORY = :category
  LEFT JOIN SR_DB.CORE.DT_CAT_PERIOD c0 ON c0.MARKET_ID = m.MARKET_ID AND c0.PERIOD_CODE = cmp.BASE_P AND c0.CATEGORY = :category
  LEFT JOIN SR_DB.CORE.DT_CAT_PERIOD p1 ON p1.MARKET_ID = m.PARENT_MARKET_ID AND p1.PERIOD_CODE = cmp.CUR_P  AND p1.CATEGORY = :category
  LEFT JOIN SR_DB.CORE.DT_CAT_PERIOD p0 ON p0.MARKET_ID = m.PARENT_MARKET_ID AND p0.PERIOD_CODE = cmp.BASE_P AND p0.CATEGORY = :category
  WHERE m.PARENT_MARKET_ID = :parent
    AND ((COALESCE(c1.CAT_VALUE_SALES, 0) = 0) <> (COALESCE(c0.CAT_VALUE_SALES, 0) = 0)
         OR (COALESCE(c1.CAT_VALUE_SALES, 0) <> 0 AND COALESCE(c0.CAT_VALUE_SALES, 0) <> 0
             AND (c1.N_WEEKS < p1.N_WEEKS OR c0.N_WEEKS < p0.N_WEEKS)));
  n := n + SQLROWCOUNT;

  -- R3_RESTATE: weeks whose snapshot hash changed since the previous successful run (needs step 3)
  SELECT MAX(RUN_ID) INTO :prev_run FROM (
    SELECT r.RUN_ID FROM SR_DB.OPS.RUN_LOG r
    WHERE r.STATUS = 'SUCCEEDED' AND r.RUN_ID <> :P_RUN_ID
      AND EXISTS (SELECT 1 FROM SR_DB.OPS.FACT_SNAPSHOT s WHERE s.RUN_ID = r.RUN_ID)
    ORDER BY r.STARTED_AT DESC LIMIT 1);
  IF (prev_run IS NOT NULL) THEN
    INSERT INTO SR_DB.APP.ARTEFACT_CHECK (RUN_ID, CMP_CODE, MARKET_ID, CATEGORY, BRAND, RULE_ID, SEVERITY, EVIDENCE)
    -- d: restated weeks, with value before and after
    WITH d AS (
      SELECT cur.WEEK_END_DATE, cur.MARKET_ID, prv.VALUE_SUM AS V_PREV, cur.VALUE_SUM AS V_NOW,
             ABS(cur.VALUE_SUM - prv.VALUE_SUM) >= SR_DB.OPS.CFG('ART_RESTATE_PCT')::FLOAT * ABS(prv.VALUE_SUM) AS IS_BIG
      FROM SR_DB.OPS.FACT_SNAPSHOT cur
      JOIN SR_DB.OPS.FACT_SNAPSHOT prv
        ON prv.RUN_ID = :prev_run AND prv.WEEK_END_DATE = cur.WEEK_END_DATE AND prv.MARKET_ID = cur.MARKET_ID
      WHERE cur.RUN_ID = :P_RUN_ID AND cur.ROW_HASH <> prv.ROW_HASH
    ),
    -- cmp: the comparisons and their periods
    cmp AS (
      SELECT column1 AS CMP_CODE, column2 AS CUR_P, column3 AS BASE_P
      FROM VALUES ('L4W_VS_YA','L4W','L4W_YA'), ('L4W_VS_PP','L4W','P4W'), ('L12W_VS_YA','L12W','L12W_YA'), ('L52W_VS_YA','L52W','L52W_YA')
    )
    SELECT :P_RUN_ID, cmp.CMP_CODE, d.MARKET_ID, :category, NULL, 'R3_RESTATE',
           IFF(BOOLOR_AGG(d.IS_BIG), 'HIGH', 'MEDIUM'),
           OBJECT_CONSTRUCT('weeks', ARRAY_AGG(DISTINCT d.WEEK_END_DATE::VARCHAR),
                            'value_prev', SUM(d.V_PREV), 'value_now', SUM(d.V_NOW),
                            'previous_run_id', :prev_run, 'source', 'OPS.FACT_SNAPSHOT')
    FROM d
    JOIN SR_DB.CORE.DT_PERIOD_WEEK pw ON pw.WEEK_END_DATE = d.WEEK_END_DATE
    JOIN cmp ON pw.PERIOD_CODE IN (cmp.CUR_P, cmp.BASE_P)
    GROUP BY cmp.CMP_CODE, d.MARKET_ID;
    n := n + SQLROWCOUNT;
  END IF;

  -- R4_RECODE: a brand's exiting items are replaced by entering items of about the same size (gated shifts only)
  INSERT INTO SR_DB.APP.ARTEFACT_CHECK (RUN_ID, CMP_CODE, MARKET_ID, CATEGORY, BRAND, RULE_ID, SEVERITY, EVIDENCE)
  -- cmp: the comparisons and their periods
  WITH cmp AS (
    SELECT column1 AS CMP_CODE, column2 AS CUR_P, column3 AS BASE_P
    FROM VALUES ('L4W_VS_YA','L4W','L4W_YA'), ('L4W_VS_PP','L4W','P4W'), ('L12W_VS_YA','L12W','L12W_YA'), ('L52W_VS_YA','L52W','L52W_YA')
  ),
  -- cand: the run's gated brand x market x comparison
  cand AS (
    SELECT DISTINCT CMP_CODE, MARKET_ID, CATEGORY, BRAND FROM SR_DB.APP.SHIFT_CANDIDATE
    WHERE RUN_ID = :P_RUN_ID AND PASSED_GATES
  ),
  -- it: item sales in the current and base period
  it AS (
    SELECT c.CMP_CODE, c.MARKET_ID, c.CATEGORY, c.BRAND, f.PRODUCT_ID,
           SUM(IFF(pw.PERIOD_CODE = cmp.CUR_P,  f.VALUE_SALES, 0)) AS V1,
           SUM(IFF(pw.PERIOD_CODE = cmp.BASE_P, f.VALUE_SALES, 0)) AS V0
    FROM cand c
    JOIN cmp ON cmp.CMP_CODE = c.CMP_CODE
    JOIN SR_DB.SRC.V_SRC_PRODUCT p ON p.BRAND = c.BRAND AND p.CATEGORY = c.CATEGORY
    JOIN SR_DB.SRC.V_SRC_FACT_WEEKLY f ON f.PRODUCT_ID = p.PRODUCT_ID AND f.MARKET_ID = c.MARKET_ID
    JOIN SR_DB.CORE.DT_PERIOD_WEEK pw ON pw.WEEK_END_DATE = f.WEEK_END_DATE AND pw.PERIOD_CODE IN (cmp.CUR_P, cmp.BASE_P)
    GROUP BY c.CMP_CODE, c.MARKET_ID, c.CATEGORY, c.BRAND, f.PRODUCT_ID
  ),
  -- b: exits (sold before, not now) and entries (sold now, not before) per brand
  b AS (
    SELECT CMP_CODE, MARKET_ID, CATEGORY, BRAND, SUM(V0) AS BRAND_BASE,
           SUM(IFF(V1 <= 0 AND V0 > 0, V0, 0)) AS EXIT_BASE,  COUNT_IF(V1 <= 0 AND V0 > 0) AS N_EXIT,
           SUM(IFF(V0 <= 0 AND V1 > 0, V1, 0)) AS ENTRY_CUR,  COUNT_IF(V0 <= 0 AND V1 > 0) AS N_ENTRY
    FROM it GROUP BY CMP_CODE, MARKET_ID, CATEGORY, BRAND
  )
  SELECT :P_RUN_ID, b.CMP_CODE, b.MARKET_ID, b.CATEGORY, b.BRAND, 'R4_RECODE', 'MEDIUM',
         OBJECT_CONSTRUCT('exit_items', b.N_EXIT, 'exit_base_sales', b.EXIT_BASE, 'entry_items', b.N_ENTRY,
                          'entry_cur_sales', b.ENTRY_CUR, 'brand_base_sales', b.BRAND_BASE, 'source', 'SRC.V_SRC_FACT_WEEKLY')
  FROM b
  WHERE b.BRAND_BASE > 0
    AND b.EXIT_BASE >= SR_DB.OPS.CFG('ART_RECODE_MIN_SHARE')::FLOAT * b.BRAND_BASE
    AND b.ENTRY_CUR >= SR_DB.OPS.CFG('ART_RECODE_MIN_SHARE')::FLOAT * b.BRAND_BASE
    AND ABS(b.ENTRY_CUR - b.EXIT_BASE) <= SR_DB.OPS.CFG('ART_RECODE_TOL')::FLOAT * GREATEST(b.ENTRY_CUR, b.EXIT_BASE);
  n := n + SQLROWCOUNT;

  -- R5_SPIKE: a current-period week far from its trailing 13-week mean (13 is the rule's window, not a threshold)
  INSERT INTO SR_DB.APP.ARTEFACT_CHECK (RUN_ID, CMP_CODE, MARKET_ID, CATEGORY, BRAND, RULE_ID, SEVERITY, EVIDENCE)
  -- cmp: the comparisons and their current periods
  WITH cmp AS (
    SELECT column1 AS CMP_CODE, column2 AS CUR_P
    FROM VALUES ('L4W_VS_YA','L4W'), ('L4W_VS_PP','L4W'), ('L12W_VS_YA','L12W'), ('L52W_VS_YA','L52W')
  ),
  -- w: weekly category sales with the trailing 13 weeks' mean and spread
  w AS (
    SELECT WEEK_END_DATE, MARKET_ID, CATEGORY, VALUE_SALES,
           AVG(VALUE_SALES)         OVER (PARTITION BY MARKET_ID, CATEGORY ORDER BY WEEK_END_DATE ROWS BETWEEN 13 PRECEDING AND 1 PRECEDING) AS M13,
           STDDEV_SAMP(VALUE_SALES) OVER (PARTITION BY MARKET_ID, CATEGORY ORDER BY WEEK_END_DATE ROWS BETWEEN 13 PRECEDING AND 1 PRECEDING) AS SD13,
           COUNT(VALUE_SALES)       OVER (PARTITION BY MARKET_ID, CATEGORY ORDER BY WEEK_END_DATE ROWS BETWEEN 13 PRECEDING AND 1 PRECEDING) AS N13
    FROM SR_DB.CORE.DT_CAT_WEEK
    WHERE MARKET_ID IN (SELECT MARKET_ID FROM SR_DB.SRC.V_SRC_MARKET WHERE MARKET_ID = :parent OR PARENT_MARKET_ID = :parent)
  )
  SELECT :P_RUN_ID, cmp.CMP_CODE, w.MARKET_ID, w.CATEGORY, NULL, 'R5_SPIKE', 'MEDIUM',
         OBJECT_CONSTRUCT('weeks', ARRAY_AGG(w.WEEK_END_DATE::VARCHAR), 'max_z', MAX(ABS(w.VALUE_SALES - w.M13) / w.SD13),
                          'k', SR_DB.OPS.CFG('ART_SPIKE_K')::FLOAT, 'source', 'CORE.DT_CAT_WEEK')
  FROM w
  JOIN SR_DB.CORE.DT_PERIOD_WEEK pw ON pw.WEEK_END_DATE = w.WEEK_END_DATE
  JOIN cmp ON cmp.CUR_P = pw.PERIOD_CODE
  WHERE w.N13 = 13 AND w.SD13 > 0
    AND ABS(w.VALUE_SALES - w.M13) > SR_DB.OPS.CFG('ART_SPIKE_K')::FLOAT * w.SD13
  GROUP BY cmp.CMP_CODE, w.MARKET_ID, w.CATEGORY;
  n := n + SQLROWCOUNT;

  -- R6_GAP: category weeks missing in either period
  INSERT INTO SR_DB.APP.ARTEFACT_CHECK (RUN_ID, CMP_CODE, MARKET_ID, CATEGORY, BRAND, RULE_ID, SEVERITY, EVIDENCE)
  SELECT DISTINCT :P_RUN_ID, c.CMP_CODE, c.MARKET_ID, c.CATEGORY, NULL, 'R6_GAP', 'HIGH',
         OBJECT_CONSTRUCT('weeks_cur', c.CAT_WEEKS1, 'weeks_base', c.CAT_WEEKS0, 'expected', c.EXP_WEEKS,
                          'source', 'CORE.DT_SHARE_COMPARE')
  FROM SR_DB.CORE.DT_SHARE_COMPARE c
  WHERE c.MARKET_ID IN (SELECT MARKET_ID FROM SR_DB.SRC.V_SRC_MARKET WHERE MARKET_ID = :parent OR PARENT_MARKET_ID = :parent)
    AND (c.CAT_WEEKS1 < c.EXP_WEEKS OR c.CAT_WEEKS0 < c.EXP_WEEKS);
  n := n + SQLROWCOUNT;

  RETURN n;
END;
$$;
