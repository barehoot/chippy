-- SR-013 · Reconcile the share grid to five numbers from an NIQ reference report.
-- 1) A person fills TEST.FX_RECON_REFERENCE from the report (template below; shares in percent, 0-100).
-- 2) Run this file: it appends one OPS.RECON_RESULT row per check. 3) Run tests/sql/T-CORE-03.sql.
-- Tolerances (T2): 0.05 share points for shares, 0.5% relative for sales.
USE ROLE SR_DEV;
USE WAREHOUSE SR_WH_XS;

-- Template (uncomment, fill from the report, run once):
-- INSERT INTO SR_DB.TEST.FX_RECON_REFERENCE
--   (CHECK_ID, DESCRIPTION, PERIOD_CODE, MARKET_ID, CATEGORY, BRAND, METRIC, REFERENCE_VALUE, SOURCE_NOTE)
-- VALUES
--   ('R01', 'Category value sales, L52W, parent market', 'L52W', '<market_id>', '<category>', NULL, 'VALUE_SALES', 0, '<report, page>'),
--   ('R02', 'Focus brand value share, L52W, parent',      'L52W', '<market_id>', '<category>', '<brand>', 'VALUE_SHARE', 0, '<report, page>'),
--   ('R03', 'Focus brand value share, L12W, parent',      'L12W', '<market_id>', '<category>', '<brand>', 'VALUE_SHARE', 0, '<report, page>'),
--   ('R04', 'Competitor value share, L4W, one retailer',  'L4W',  '<market_id>', '<category>', '<brand>', 'VALUE_SHARE', 0, '<report, page>'),
--   ('R05', 'Focus brand distribution share, L12W',       'L12W', '<market_id>', '<category>', '<brand>', 'DIST_SHARE', 0, '<report, page>');

INSERT INTO SR_DB.OPS.RECON_RESULT (CHECK_ID, DESCRIPTION, REFERENCE_VALUE, SR_VALUE, ABS_DIFF, PASSED)
-- sr: the Share Radar value for each reference row, in the reference's unit
WITH sr AS (
  SELECT r.CHECK_ID, r.DESCRIPTION, r.METRIC, r.REFERENCE_VALUE,
         CASE r.METRIC
           WHEN 'VALUE_SALES' THEN IFF(r.BRAND IS NULL, MAX(g.CAT_VALUE_SALES), SUM(g.VALUE_SALES))
           WHEN 'VALUE_SHARE' THEN 100 * SUM(g.VALUE_SALES) / NULLIF(MAX(g.CAT_VALUE_SALES), 0)
           WHEN 'DIST_SHARE'  THEN 100 * SUM(g.TDP_SUM)     / NULLIF(MAX(g.CAT_TDP_SUM), 0)
         END AS SR_VALUE
  FROM SR_DB.TEST.FX_RECON_REFERENCE r
  LEFT JOIN SR_DB.CORE.V_SHARE_GRID g
    ON g.PERIOD_CODE = r.PERIOD_CODE AND g.MARKET_ID = r.MARKET_ID AND g.CATEGORY = r.CATEGORY
   AND (r.BRAND IS NULL OR g.BRAND = r.BRAND)
  GROUP BY r.CHECK_ID, r.DESCRIPTION, r.METRIC, r.REFERENCE_VALUE, r.BRAND
)
SELECT CHECK_ID, DESCRIPTION, REFERENCE_VALUE, SR_VALUE, ABS(SR_VALUE - REFERENCE_VALUE),
       CASE WHEN SR_VALUE IS NULL THEN FALSE
            WHEN METRIC = 'VALUE_SALES' THEN ABS(SR_VALUE - REFERENCE_VALUE) <= 0.005 * ABS(REFERENCE_VALUE)
            ELSE ABS(SR_VALUE - REFERENCE_VALUE) <= 0.05 END
FROM sr;

SELECT CHECK_ID, DESCRIPTION, REFERENCE_VALUE, SR_VALUE, ABS_DIFF, PASSED
FROM SR_DB.OPS.RECON_RESULT
QUALIFY ROW_NUMBER() OVER (PARTITION BY CHECK_ID ORDER BY CHECKED_AT DESC) = 1
ORDER BY CHECK_ID;
