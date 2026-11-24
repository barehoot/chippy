-- SR-023 · L6 where it happened, exact part: for each selected shift in the parent market, each child retailer r
-- (plus a "rest of market" remainder where children do not cover the parent) contributes
--   performance = 100 x (w1 + w0) / 2 x (s1 - s0)      w = category sales of r / parent category sales
--   mix         = 100 x (s1 + s0) / 2 x (w1 - w0)      s = brand share within r (0 where r has no category sales)
-- and the parts add up exactly to 100 x D_SHARE of the parent (T-WH-01). Ranked by ABS(TOTAL_PTS).
-- TOP_INSIGHTS rows are added by SP_WHERE_INSIGHTS (sql/30_ml/302) with METHOD = 'TOP_INSIGHTS'.
USE ROLE SR_DEV;
CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_WHERE(P_RUN_ID VARCHAR)
RETURNS NUMBER
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  n NUMBER DEFAULT 0;
BEGIN
  EXECUTE IMMEDIATE 'ALTER SESSION SET QUERY_TAG = ''SR|run=' || P_RUN_ID || '|step=WHERE''';
  DELETE FROM SR_DB.APP.SHIFT_WHERE WHERE RUN_ID = :P_RUN_ID AND METHOD = 'EXACT_RETAILER';
  INSERT INTO SR_DB.APP.SHIFT_WHERE (RUN_ID, SHIFT_ID, METHOD, RANK_NO, CONTRIBUTOR, PERF_PTS, MIX_PTS, TOTAL_PTS)
  -- sel: selected shifts with the parent's brand and category sales in both periods
  WITH sel AS (
    SELECT r.SHIFT_ID, r.CMP_CODE, r.MARKET_ID, r.CATEGORY, r.BRAND, c.CUR_PERIOD, c.BASE_PERIOD,
           c.S1, c.S0, c.CS1, c.CS0
    FROM SR_DB.APP.SHIFT_RANKED r
    JOIN SR_DB.CORE.DT_SHARE_COMPARE c
      ON c.CMP_CODE = r.CMP_CODE AND c.MARKET_ID = r.MARKET_ID AND c.CATEGORY = r.CATEGORY AND c.BRAND = r.BRAND
     AND EQUAL_NULL(c.MANUFACTURER, r.MANUFACTURER)
    WHERE r.RUN_ID = :P_RUN_ID AND r.SELECTED AND c.CS1 > 0 AND c.CS0 > 0
  ),
  -- bp: brand sales per market and period (summed over manufacturers, in case a brand spans two)
  bp AS (
    SELECT PERIOD_CODE, MARKET_ID, CATEGORY, BRAND, SUM(VALUE_SALES) AS V
    FROM SR_DB.CORE.DT_BRAND_PERIOD GROUP BY PERIOD_CODE, MARKET_ID, CATEGORY, BRAND
  ),
  -- kids: every child market of each selected shift's market, with its category and brand sales
  kids AS (
    SELECT s.SHIFT_ID, COALESCE(m.RETAILER, m.MARKET_NAME) AS CONTRIBUTOR,
           COALESCE(k1.CAT_VALUE_SALES, 0) AS KCS1, COALESCE(k0.CAT_VALUE_SALES, 0) AS KCS0,
           COALESCE(b1.V, 0) AS KS1, COALESCE(b0.V, 0) AS KS0
    FROM sel s
    JOIN SR_DB.SRC.V_SRC_MARKET m ON m.PARENT_MARKET_ID = s.MARKET_ID
    LEFT JOIN SR_DB.CORE.DT_CAT_PERIOD k1 ON k1.PERIOD_CODE = s.CUR_PERIOD  AND k1.MARKET_ID = m.MARKET_ID AND k1.CATEGORY = s.CATEGORY
    LEFT JOIN SR_DB.CORE.DT_CAT_PERIOD k0 ON k0.PERIOD_CODE = s.BASE_PERIOD AND k0.MARKET_ID = m.MARKET_ID AND k0.CATEGORY = s.CATEGORY
    LEFT JOIN bp b1 ON b1.PERIOD_CODE = s.CUR_PERIOD  AND b1.MARKET_ID = m.MARKET_ID AND b1.CATEGORY = s.CATEGORY AND b1.BRAND = s.BRAND
    LEFT JOIN bp b0 ON b0.PERIOD_CODE = s.BASE_PERIOD AND b0.MARKET_ID = m.MARKET_ID AND b0.CATEGORY = s.CATEGORY AND b0.BRAND = s.BRAND
  ),
  -- rest: the part of the parent that its children do not cover
  rest AS (
    SELECT s.SHIFT_ID, 'Rest of market' AS CONTRIBUTOR,
           s.CS1 - SUM(k.KCS1) AS KCS1, s.CS0 - SUM(k.KCS0) AS KCS0,
           s.S1 - SUM(k.KS1)   AS KS1,  s.S0 - SUM(k.KS0)   AS KS0
    FROM sel s JOIN kids k ON k.SHIFT_ID = s.SHIFT_ID
    GROUP BY s.SHIFT_ID, s.CS1, s.CS0, s.S1, s.S0
    HAVING ABS(s.CS1 - SUM(k.KCS1)) > 0.005 OR ABS(s.CS0 - SUM(k.KCS0)) > 0.005
  ),
  parts AS (
    SELECT SHIFT_ID, CONTRIBUTOR, KCS1, KCS0, KS1, KS0 FROM kids
    UNION ALL
    SELECT SHIFT_ID, CONTRIBUTOR, KCS1, KCS0, KS1, KS0 FROM rest
  ),
  -- terms: weight and within-retailer share per period, then the two-factor split
  terms AS (
    SELECT p.SHIFT_ID, p.CONTRIBUTOR,
           p.KCS1 / s.CS1 AS W1, p.KCS0 / s.CS0 AS W0,
           COALESCE(p.KS1 / NULLIF(p.KCS1, 0), 0) AS SH1, COALESCE(p.KS0 / NULLIF(p.KCS0, 0), 0) AS SH0
    FROM parts p JOIN sel s ON s.SHIFT_ID = p.SHIFT_ID
  )
  SELECT :P_RUN_ID, SHIFT_ID, 'EXACT_RETAILER',
         ROW_NUMBER() OVER (PARTITION BY SHIFT_ID ORDER BY ABS(PERF + MIX) DESC, CONTRIBUTOR),
         CONTRIBUTOR, PERF, MIX, PERF + MIX
  FROM (SELECT SHIFT_ID, CONTRIBUTOR,
               100 * (W1 + W0) / 2 * (SH1 - SH0) AS PERF,
               100 * (SH1 + SH0) / 2 * (W1 - W0) AS MIX
        FROM terms);
  n := SQLROWCOUNT;
  RETURN n;
END;
$$;
