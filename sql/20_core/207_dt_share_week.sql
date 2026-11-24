-- SR-012 · L4 weekly share and lever indices per brand, for z-scores, ML and early warning. Leaf table.
USE ROLE SR_DEV;
CREATE OR REPLACE DYNAMIC TABLE SR_DB.CORE.DT_SHARE_WEEK
  TARGET_LAG = '15 minutes'
  WAREHOUSE = SR_WH_M
  REFRESH_MODE = AUTO
  COMMENT = 'Weekly share and lever indices per brand, for z-scores, ML and early warning'
AS
SELECT bw.WEEK_END_DATE, bw.MARKET_ID, bw.CATEGORY, bw.MANUFACTURER, bw.BRAND,
       bw.VALUE_SALES, cw.VALUE_SALES AS CAT_VALUE_SALES,
       bw.VALUE_SALES / NULLIF(cw.VALUE_SALES, 0) AS VALUE_SHARE,
       bw.TDP / NULLIF(cw.TDP, 0)                 AS DIST_SHARE,
       (bw.VALUE_SALES / NULLIF(bw.UNIT_SALES, 0))
         / NULLIF(cw.VALUE_SALES / NULLIF(cw.UNIT_SALES, 0), 0)       AS PRICE_INDEX,
       (bw.VALUE_SALES / NULLIF(bw.BASE_VALUE_SALES, 0))
         / NULLIF(cw.VALUE_SALES / NULLIF(cw.BASE_VALUE_SALES, 0), 0) AS PROMO_INDEX
FROM SR_DB.CORE.DT_BRAND_WEEK bw
JOIN SR_DB.CORE.DT_CAT_WEEK cw
  ON cw.WEEK_END_DATE = bw.WEEK_END_DATE AND cw.MARKET_ID = bw.MARKET_ID AND cw.CATEGORY = bw.CATEGORY;
