-- SR-040 · L10 semantic view for Cortex Analyst (the agent's share_analyst tool). FACTS before DIMENSIONS.
-- After any change here, rerun sql/70_sec/702_row_access.sql and the golden set (sr-cortex-agent skill).
USE ROLE SR_DEV;
CREATE OR REPLACE SEMANTIC VIEW SR_DB.SEM.SV_SHARE
  TABLES (
    grid AS SR_DB.SEM.V_SEM_SHARE_GRID
      PRIMARY KEY (PERIOD_CODE, MARKET_ID, CATEGORY, BRAND)
      WITH SYNONYMS = ('market share', 'share grid')
      COMMENT = 'Brand value and distribution share by market and reporting period, as of the latest data week',
    chg AS SR_DB.SEM.V_SEM_SHARE_CHANGE
      PRIMARY KEY (CMP_CODE, MARKET_ID, CATEGORY, BRAND)
      WITH SYNONYMS = ('share change', 'share shift', 'share movement')
      COMMENT = 'Share change between two periods with its exact driver bridge and data-artefact label'
  )
  FACTS (
    grid.value_sales      AS VALUE_SALES      COMMENT = 'Brand value sales in the period, local currency',
    grid.cat_value_sales  AS CAT_VALUE_SALES  COMMENT = 'Category value sales in the same market and period',
    grid.tdp              AS TDP_SUM          COMMENT = 'Total distribution points (sum of item %ACV across weeks)',
    grid.cat_tdp          AS CAT_TDP_SUM      COMMENT = 'Category total distribution points in the same market and period',
    chg.share_now_pct     AS SHARE_NOW_PCT    COMMENT = 'Value share in the current period, percent',
    chg.share_before_pct  AS SHARE_BEFORE_PCT COMMENT = 'Value share in the comparison period, percent',
    chg.share_change_pts  AS SHARE_CHANGE_PTS COMMENT = 'Share now minus share before, in share points',
    chg.value_at_stake    AS VALUE_AT_STAKE   COMMENT = 'Share change times current category sales, local currency',
    chg.dist_pts          AS BRIDGE_DIST_PTS      COMMENT = 'Share points explained by distribution',
    chg.velocity_pts      AS BRIDGE_VELOCITY_PTS  COMMENT = 'Share points explained by velocity (sales per distribution point)',
    chg.price_pts         AS BRIDGE_PRICE_PTS     COMMENT = 'Share points explained by price',
    chg.promo_pts         AS BRIDGE_PROMO_PTS     COMMENT = 'Share points explained by promotion'
  )
  DIMENSIONS (
    grid.period_code         AS PERIOD_CODE  WITH SYNONYMS = ('period') COMMENT = 'L4W, P4W, L4W_YA, L12W, L12W_YA, L52W, L52W_YA',
    grid.as_of_week          AS AS_OF_WEEK   COMMENT = 'Latest week in the data',
    grid.market_name         AS MARKET_NAME  WITH SYNONYMS = ('market', 'retailer', 'channel', 'account'),
    grid.market_level        AS MARKET_LEVEL COMMENT = 'TOTAL, CHANNEL, RETAILER or REGION',
    grid.category            AS CATEGORY,
    grid.manufacturer        AS MANUFACTURER WITH SYNONYMS = ('company', 'supplier', 'client'),
    grid.brand               AS BRAND,
    chg.cmp_code             AS CMP_CODE     WITH SYNONYMS = ('comparison', 'versus year ago', 'versus prior period')
                             COMMENT = 'L4W_VS_YA, L4W_VS_PP, L12W_VS_YA, L52W_VS_YA',
    chg.change_market        AS MARKET_NAME,
    chg.change_category      AS CATEGORY,
    chg.change_manufacturer  AS MANUFACTURER,
    chg.change_brand         AS BRAND,
    chg.artefact_label       AS ARTEFACT_LABEL COMMENT = 'MARKET_MOVE, MIXED or POSSIBLE_DATA_EFFECT',
    chg.is_selected          AS IS_SELECTED    COMMENT = 'TRUE if the shift is in the latest brief'
  )
  METRICS (
    grid.value_share_pct        AS 100 * SUM(grid.value_sales) / NULLIF(MAX(grid.cat_value_sales), 0)
                                COMMENT = 'Value share %, valid within one market, category and period',
    grid.distribution_share_pct AS 100 * SUM(grid.tdp) / NULLIF(MAX(grid.cat_tdp), 0)
                                COMMENT = 'Distribution share %, valid within one market, category and period',
    grid.total_value_sales      AS SUM(grid.value_sales),
    chg.total_share_change_pts  AS SUM(chg.share_change_pts) COMMENT = 'Adds up across brands within one market and comparison',
    chg.total_value_at_stake    AS SUM(chg.value_at_stake)
  )
  COMMENT = 'Share Radar governed share metrics'
  AI_SQL_GENERATION 'Always filter grid to one PERIOD_CODE and chg to one CMP_CODE. Share metrics are valid only within one market and category, so group by MARKET_NAME and CATEGORY whenever more than one is requested. Never sum or average shares across markets. Show shares with one decimal and share changes with two.';
