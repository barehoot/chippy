-- SR-027 · L6 early warning: lever moves in the latest week that the reported L4W share has not absorbed yet.
-- If the latest week's distribution share persists, next period's L4W share moves mechanically by
--   PROJECTED_SHARE_PTS = 100 x s(L4W) x (DS latest / DS L4W - 1)     (velocity, price and promo held constant)
-- DIST_DROP: LEVER_CHG <= EW_DIST_DROP. PRICE_RISE: price index change >= EW_PRICE_RISE (no projection:
-- elasticity is unknown). Watched brands: the focus manufacturer's, plus each scope market's top ten by L4W sales.
USE ROLE SR_DEV;
CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_EARLY_WARNING(P_RUN_ID VARCHAR)
RETURNS NUMBER
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  n      NUMBER DEFAULT 0;
  parent VARCHAR;
BEGIN
  EXECUTE IMMEDIATE 'ALTER SESSION SET QUERY_TAG = ''SR|run=' || P_RUN_ID || '|step=EARLY_WARNING''';
  SELECT SR_DB.OPS.CFG('SCOPE_PARENT_MARKET')::VARCHAR INTO :parent;
  DELETE FROM SR_DB.APP.EARLY_WARNING WHERE RUN_ID = :P_RUN_ID;
  INSERT INTO SR_DB.APP.EARLY_WARNING
    (RUN_ID, MARKET_ID, CATEGORY, BRAND, SIGNAL, LATEST_WEEK, LEVER_LATEST, LEVER_L4W, LEVER_CHG, PROJECTED_SHARE_PTS, NOTE)
  -- cfg: thresholds and the focus manufacturer
  WITH cfg AS (
    SELECT SR_DB.OPS.CFG('EW_DIST_DROP')::FLOAT AS DIST_DROP, SR_DB.OPS.CFG('EW_PRICE_RISE')::FLOAT AS PRICE_RISE,
           SR_DB.OPS.CFG('FOCUS_MANUFACTURER')::VARCHAR AS FOCUS
  ),
  -- lat: the latest week
  lat AS (SELECT MAX(WEEK_END_DATE) AS WK FROM SR_DB.CORE.DT_SHARE_WEEK),
  -- l4: L4W share, distribution share and price index per brand in the scope markets, ranked by sales
  l4 AS (
    SELECT g.MARKET_ID, g.CATEGORY, g.MANUFACTURER, g.BRAND, g.VALUE_SHARE, g.DIST_SHARE, g.PRICE_INDEX,
           ROW_NUMBER() OVER (PARTITION BY g.MARKET_ID, g.CATEGORY ORDER BY g.VALUE_SALES DESC, g.BRAND) AS SALES_RANK
    FROM SR_DB.CORE.V_SHARE_GRID g
    WHERE g.PERIOD_CODE = 'L4W'
      AND g.MARKET_ID IN (SELECT MARKET_ID FROM SR_DB.SRC.V_SRC_MARKET WHERE MARKET_ID = :parent OR PARENT_MARKET_ID = :parent)
  ),
  -- watch: the brands we watch
  watch AS (
    SELECT l4.* FROM l4 CROSS JOIN cfg WHERE l4.SALES_RANK <= 10 OR l4.MANUFACTURER = cfg.FOCUS
  ),
  -- wk: the same levers in the latest week
  wk AS (
    SELECT w.MARKET_ID, w.CATEGORY, w.MANUFACTURER, w.BRAND, w.DIST_SHARE, w.PRICE_INDEX, w.WEEK_END_DATE
    FROM SR_DB.CORE.DT_SHARE_WEEK w JOIN lat ON w.WEEK_END_DATE = lat.WK
  ),
  -- sig: both signals per watched brand
  sig AS (
    SELECT 'DIST_DROP' AS SIGNAL, a.MARKET_ID, a.CATEGORY, a.BRAND, b.WEEK_END_DATE,
           b.DIST_SHARE AS LEVER_LATEST, a.DIST_SHARE AS LEVER_L4W,
           b.DIST_SHARE / NULLIF(a.DIST_SHARE, 0) - 1 AS LEVER_CHG,
           100 * a.VALUE_SHARE * (b.DIST_SHARE / NULLIF(a.DIST_SHARE, 0) - 1) AS PROJECTED_SHARE_PTS,
           'Mechanical: if the latest week''s distribution persists, other levers held; not a forecast' AS NOTE
    FROM watch a
    JOIN wk b ON b.MARKET_ID = a.MARKET_ID AND b.CATEGORY = a.CATEGORY AND b.BRAND = a.BRAND
             AND EQUAL_NULL(b.MANUFACTURER, a.MANUFACTURER)
    UNION ALL
    SELECT 'PRICE_RISE', a.MARKET_ID, a.CATEGORY, a.BRAND, b.WEEK_END_DATE,
           b.PRICE_INDEX, a.PRICE_INDEX, b.PRICE_INDEX / NULLIF(a.PRICE_INDEX, 0) - 1, NULL,
           'Price index up against the category; share effect not projected (elasticity unknown)'
    FROM watch a
    JOIN wk b ON b.MARKET_ID = a.MARKET_ID AND b.CATEGORY = a.CATEGORY AND b.BRAND = a.BRAND
             AND EQUAL_NULL(b.MANUFACTURER, a.MANUFACTURER)
  )
  SELECT :P_RUN_ID, s.MARKET_ID, s.CATEGORY, s.BRAND, s.SIGNAL, s.WEEK_END_DATE, s.LEVER_LATEST, s.LEVER_L4W,
         s.LEVER_CHG, s.PROJECTED_SHARE_PTS, s.NOTE
  FROM sig s CROSS JOIN cfg
  WHERE (s.SIGNAL = 'DIST_DROP'  AND s.LEVER_CHG <= cfg.DIST_DROP)
     OR (s.SIGNAL = 'PRICE_RISE' AND s.LEVER_CHG >= cfg.PRICE_RISE);
  n := SQLROWCOUNT;
  RETURN n;
END;
$$;
