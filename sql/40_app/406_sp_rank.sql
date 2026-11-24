-- SR-026 · L6 materiality score, ranking and suppression into APP.SHIFT_RANKED.
--
-- CONFIDENCE  = LEAST(1, ABS(Z_SCORE) / 3); 0.5 when Z_SCORE is NULL; at least 0.8 when ANOMALY_CONFIRMED
-- ART_FACTOR  = 1.0 MARKET_MOVE | 0.6 MIXED | 0.3 POSSIBLE_DATA_EFFECT
-- SCORE       = ABS(VALUE_AT_STAKE) x CONFIDENCE x ART_FACTOR x (1.5 if the focus manufacturer, else 1.0)
-- SUPPRESSED  = same MARKET_ID, BRAND, CMP_CODE and sign SELECTED in one of the last SUPPRESS_RUNS earlier weeks
--               (latest successful run per week, same scope), and ABS(D_SHARE) < that ABS(D_SHARE) x (1 + SUPPRESS_GROWTH)
-- SELECTED    = not suppressed, not POSSIBLE_DATA_EFFECT, the best comparison of its market x brand, and
--               RANK_NO <= TOP_N. RANK_NO runs 1..n with the eligible shifts first, by SCORE.
-- Decisions B04 (earlier weeks only) and B05 (one comparison per market x brand) are in docs/decisions.md.
USE ROLE SR_DEV;
CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_RANK(P_RUN_ID VARCHAR)
RETURNS NUMBER
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  n NUMBER DEFAULT 0;
BEGIN
  EXECUTE IMMEDIATE 'ALTER SESSION SET QUERY_TAG = ''SR|run=' || P_RUN_ID || '|step=RANK''';
  DELETE FROM SR_DB.APP.SHIFT_RANKED WHERE RUN_ID = :P_RUN_ID;
  INSERT INTO SR_DB.APP.SHIFT_RANKED
    (RUN_ID, SHIFT_ID, SCOPE_KEY, RANK_NO, CMP_CODE, MARKET_ID, CATEGORY, MANUFACTURER, BRAND, IS_FOCUS, D_SHARE,
     VALUE_AT_STAKE, CONFIDENCE, ARTEFACT_LABEL, ART_FACTOR, SCORE, SUPPRESSED, SUPPRESS_REASON, SELECTED)
  -- cfg: ranking settings, the scope key and this run's as-of week
  WITH cfg AS (
    SELECT SR_DB.OPS.CFG('TOP_N')::NUMBER                AS TOP_N,
           SR_DB.OPS.CFG('SUPPRESS_RUNS')::NUMBER        AS SUPPRESS_RUNS,
           SR_DB.OPS.CFG('SUPPRESS_GROWTH')::FLOAT       AS SUPPRESS_GROWTH,
           SR_DB.OPS.CFG('FOCUS_MANUFACTURER')::VARCHAR  AS FOCUS,
           SR_DB.OPS.CFG('SCOPE_CATEGORY')::VARCHAR || '|' || SR_DB.OPS.CFG('SCOPE_PARENT_MARKET')::VARCHAR
             || '|' || SR_DB.OPS.CFG('FOCUS_MANUFACTURER')::VARCHAR AS SCOPE_KEY,
           SR_DB.OPS.CFG('AS_OF_WEEK_END')::VARCHAR::DATE AS AS_OF_WEEK
  ),
  -- cand: the run's gated shifts
  cand AS (
    SELECT SHIFT_ID, CMP_CODE, MARKET_ID, CATEGORY, MANUFACTURER, BRAND, D_SHARE, VALUE_AT_STAKE, Z_SCORE,
           COALESCE(ANOMALY_CONFIRMED, FALSE) AS ANOMALY_CONFIRMED
    FROM SR_DB.APP.SHIFT_CANDIDATE
    WHERE RUN_ID = :P_RUN_ID AND PASSED_GATES
  ),
  -- art: worst matching artefact severity per shift (2 = HIGH, 1 = MEDIUM)
  art AS (
    SELECT c.SHIFT_ID, MAX(IFF(a.SEVERITY = 'HIGH', 2, 1)) AS SEV
    FROM cand c
    JOIN SR_DB.APP.ARTEFACT_CHECK a
      ON a.RUN_ID = :P_RUN_ID AND a.CMP_CODE = c.CMP_CODE AND a.MARKET_ID = c.MARKET_ID AND a.CATEGORY = c.CATEGORY
     AND (a.BRAND IS NULL OR a.BRAND = c.BRAND)
    GROUP BY c.SHIFT_ID
  ),
  -- week_runs: the latest successful run of each earlier week, same scope
  week_runs AS (
    SELECT r.RUN_ID, r.AS_OF_WEEK
    FROM SR_DB.OPS.RUN_LOG r CROSS JOIN cfg
    WHERE r.STATUS = 'SUCCEEDED' AND r.RUN_ID <> :P_RUN_ID AND r.SCOPE_KEY = cfg.SCOPE_KEY AND r.AS_OF_WEEK < cfg.AS_OF_WEEK
    QUALIFY ROW_NUMBER() OVER (PARTITION BY r.AS_OF_WEEK ORDER BY r.STARTED_AT DESC) = 1
  ),
  -- prev_runs: the last SUPPRESS_RUNS of those weeks
  prev_runs AS (
    SELECT w.RUN_ID, w.AS_OF_WEEK FROM week_runs w CROSS JOIN cfg
    QUALIFY ROW_NUMBER() OVER (ORDER BY w.AS_OF_WEEK DESC) <= cfg.SUPPRESS_RUNS
  ),
  -- prev: the most recent earlier selection of each market x brand x comparison x sign
  prev AS (
    SELECT r.MARKET_ID, r.BRAND, r.CMP_CODE, SIGN(r.D_SHARE) AS SGN, r.D_SHARE AS PREV_D_SHARE, p.AS_OF_WEEK AS PREV_WEEK
    FROM SR_DB.APP.SHIFT_RANKED r JOIN prev_runs p ON p.RUN_ID = r.RUN_ID
    WHERE r.SELECTED
    QUALIFY ROW_NUMBER() OVER (PARTITION BY r.MARKET_ID, r.BRAND, r.CMP_CODE, SIGN(r.D_SHARE) ORDER BY p.AS_OF_WEEK DESC) = 1
  ),
  -- s1: label, factor, confidence and suppression per shift
  s1 AS (
    SELECT c.*, cfg.SCOPE_KEY, cfg.TOP_N,
           CASE art.SEV WHEN 2 THEN 'POSSIBLE_DATA_EFFECT' WHEN 1 THEN 'MIXED' ELSE 'MARKET_MOVE' END AS ARTEFACT_LABEL,
           CASE art.SEV WHEN 2 THEN 0.3 WHEN 1 THEN 0.6 ELSE 1.0 END                                   AS ART_FACTOR,
           IFF(c.Z_SCORE IS NULL, 0.5, LEAST(1, ABS(c.Z_SCORE) / 3))                                  AS BASE_CONF,
           IFF(c.ANOMALY_CONFIRMED, GREATEST(BASE_CONF, 0.8), BASE_CONF)                               AS CONFIDENCE,
           COALESCE(c.MANUFACTURER = cfg.FOCUS, FALSE)                                                  AS IS_FOCUS,
           COALESCE(pv.PREV_D_SHARE IS NOT NULL
                    AND ABS(c.D_SHARE) < ABS(pv.PREV_D_SHARE) * (1 + cfg.SUPPRESS_GROWTH), FALSE)       AS SUPPRESSED,
           pv.PREV_D_SHARE, pv.PREV_WEEK
    FROM cand c
    CROSS JOIN cfg
    LEFT JOIN art ON art.SHIFT_ID = c.SHIFT_ID
    LEFT JOIN prev pv ON pv.MARKET_ID = c.MARKET_ID AND pv.BRAND = c.BRAND AND pv.CMP_CODE = c.CMP_CODE
                     AND pv.SGN = SIGN(c.D_SHARE)
  ),
  -- s2: score, eligibility and the best comparison per market x brand
  s2 AS (
    SELECT s1.*,
           ABS(VALUE_AT_STAKE) * CONFIDENCE * ART_FACTOR * IFF(IS_FOCUS, 1.5, 1.0) AS SCORE,
           (NOT SUPPRESSED AND ARTEFACT_LABEL <> 'POSSIBLE_DATA_EFFECT')          AS ELIGIBLE
    FROM s1
  ),
  s3 AS (
    SELECT s2.*,
           ELIGIBLE AND ROW_NUMBER() OVER (PARTITION BY ELIGIBLE, MARKET_ID, BRAND ORDER BY SCORE DESC, SHIFT_ID) = 1 AS BEST_CMP
    FROM s2
  ),
  -- s4: one ranking, eligible best comparisons first
  s4 AS (
    SELECT s3.*,
           ROW_NUMBER() OVER (ORDER BY IFF(BEST_CMP, 0, 1), SCORE DESC, SHIFT_ID) AS RANK_NO
    FROM s3
  )
  SELECT :P_RUN_ID, SHIFT_ID, SCOPE_KEY, RANK_NO, CMP_CODE, MARKET_ID, CATEGORY, MANUFACTURER, BRAND, IS_FOCUS, D_SHARE,
         VALUE_AT_STAKE, CONFIDENCE, ARTEFACT_LABEL, ART_FACTOR, SCORE, SUPPRESSED,
         CASE WHEN SUPPRESSED THEN 'Repeat of the shift selected for week ending ' || PREV_WEEK::VARCHAR
                                   || '; it has not grown enough to show again'
              WHEN ARTEFACT_LABEL = 'POSSIBLE_DATA_EFFECT' THEN 'Held back for data checks'
              WHEN NOT BEST_CMP THEN 'Another comparison of this brand and market ranks higher' END AS SUPPRESS_REASON,
         BEST_CMP AND RANK_NO <= TOP_N AS SELECTED
  FROM s4;
  n := SQLROWCOUNT;
  RETURN n;
END;
$$;
