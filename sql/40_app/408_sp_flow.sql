-- SR-025 · L6 who took it: within one market, category and comparison, share changes sum to zero, so the points
-- a losing brand gave up are allocated to the gainers in proportion to their gains. An accounting allocation,
-- labelled as such, not shopper switching. Written for every market that has a selected shift.
USE ROLE SR_DEV;
CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_FLOW(P_RUN_ID VARCHAR)
RETURNS NUMBER
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  n NUMBER DEFAULT 0;
BEGIN
  EXECUTE IMMEDIATE 'ALTER SESSION SET QUERY_TAG = ''SR|run=' || P_RUN_ID || '|step=FLOW''';
  DELETE FROM SR_DB.APP.SHARE_FLOW WHERE RUN_ID = :P_RUN_ID;
  INSERT INTO SR_DB.APP.SHARE_FLOW (RUN_ID, CMP_CODE, MARKET_ID, CATEGORY, FROM_BRAND, TO_BRAND, FLOW_PTS)
  -- d: every brand's share change in the markets and comparisons of the selected shifts
  WITH d AS (
    SELECT c.CMP_CODE, c.MARKET_ID, c.CATEGORY, c.BRAND, SUM(c.D_SHARE) AS D_SHARE
    FROM SR_DB.CORE.DT_SHARE_COMPARE c
    WHERE c.D_SHARE IS NOT NULL
      AND (c.CMP_CODE, c.MARKET_ID, c.CATEGORY) IN (SELECT CMP_CODE, MARKET_ID, CATEGORY FROM SR_DB.APP.SHIFT_RANKED
                                                    WHERE RUN_ID = :P_RUN_ID AND SELECTED)
    GROUP BY c.CMP_CODE, c.MARKET_ID, c.CATEGORY, c.BRAND
  ),
  -- g: total gains per market, category and comparison (equal to total losses)
  g AS (
    SELECT CMP_CODE, MARKET_ID, CATEGORY, SUM(IFF(D_SHARE > 0, D_SHARE, 0)) AS GAIN_TOTAL
    FROM d GROUP BY CMP_CODE, MARKET_ID, CATEGORY
  )
  SELECT :P_RUN_ID, l.CMP_CODE, l.MARKET_ID, l.CATEGORY, l.BRAND, w.BRAND,
         100 * (-l.D_SHARE) * w.D_SHARE / NULLIF(g.GAIN_TOTAL, 0) AS FLOW_PTS
  FROM d l
  JOIN d w ON w.CMP_CODE = l.CMP_CODE AND w.MARKET_ID = l.MARKET_ID AND w.CATEGORY = l.CATEGORY AND w.D_SHARE > 0
  JOIN g   ON g.CMP_CODE = l.CMP_CODE AND g.MARKET_ID = l.MARKET_ID AND g.CATEGORY = l.CATEGORY
  WHERE l.D_SHARE < 0 AND g.GAIN_TOTAL > 0;
  n := SQLROWCOUNT;
  RETURN n;
END;
$$;
