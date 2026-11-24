-- SR-003 · L3 source adapter. THE ONLY FILE THAT NAMES NIQ OBJECTS (AGENTS.md rule 5).
--
-- Status: TEMPLATE. Replace every <NIQ_...> placeholder with the mapping approved in SR-003, using the L3
-- worksheet below. Nothing downstream changes when the mapping changes.
--
-- | Contract column    | NIQ object.column | Transform                 | Note                           |
-- | ------------------ | ----------------- | ------------------------- | ------------------------------ |
-- | WEEK_END_DATE      | <fill>            | ::DATE                    |                                |
-- | MARKET_ID          | <fill>            | ::VARCHAR                 |                                |
-- | PRODUCT_ID         | <fill>            | ::VARCHAR                 | UPC or NIQ item code           |
-- | VALUE_SALES        | <fill>            | ::NUMBER(18,2)            | local currency                 |
-- | UNIT_SALES         | <fill>            | ::NUMBER(18,3)            | NULL if absent                 |
-- | ACV_DIST_PCT       | <fill>            | x100 if stored as 0-1     | NULL if absent -> mode C or D  |
-- | BASE_VALUE_SALES   | <fill>            | ::NUMBER(18,2)            | NULL if absent -> mode B       |
-- | BASE_UNIT_SALES    | <fill>            | ::NUMBER(18,3)            | NULL if absent -> mode B       |
-- | STORES_SELLING     | <fill>            | ::NUMBER(9,0)             | NULL if absent                 |
--
-- Optional columns may be NULL; SP_CAPABILITY_CHECK then caps the bridge mode (L3, E04).
USE ROLE SR_DEV;

CREATE OR REPLACE VIEW SR_DB.SRC.V_SRC_FACT_WEEKLY_ALL (
  WEEK_END_DATE, MARKET_ID, PRODUCT_ID, VALUE_SALES, VOLUME_SALES, UNIT_SALES,
  ACV_DIST_PCT, BASE_VALUE_SALES, BASE_UNIT_SALES, STORES_SELLING, DATA_VERSION
)
COMMENT = 'Item x market x week facts, all weeks (contract L3)'
AS
SELECT
  f.<WEEK_END_COL>::DATE,
  f.<MARKET_KEY>::VARCHAR,
  f.<PRODUCT_KEY>::VARCHAR,
  f.<SALES_VALUE>::NUMBER(18,2),
  f.<SALES_VOLUME>::NUMBER(18,3),        -- NULL::NUMBER(18,3) if absent
  f.<SALES_UNITS>::NUMBER(18,3),
  f.<ACV_WTD_DIST>::NUMBER(9,4),         -- convert 0-1 to 0-100 if needed
  f.<BASE_SALES_VALUE>::NUMBER(18,2),
  f.<BASE_SALES_UNITS>::NUMBER(18,3),
  f.<STORES_SELLING>::NUMBER(9,0),
  f.<LOAD_VERSION>::VARCHAR
FROM <NIQ_DB>.<NIQ_SCHEMA>.<FACT_TABLE> f
WHERE f.<SALES_VALUE> IS NOT NULL;

-- Replay control: everything downstream reads this view, never the _ALL view (except SP_REPLAY_NEXT_WEEK).
CREATE OR REPLACE VIEW SR_DB.SRC.V_SRC_FACT_WEEKLY
COMMENT = 'V_SRC_FACT_WEEKLY_ALL up to OPS.SETTINGS AS_OF_WEEK_END (replay control)'
AS
SELECT f.WEEK_END_DATE, f.MARKET_ID, f.PRODUCT_ID, f.VALUE_SALES, f.VOLUME_SALES, f.UNIT_SALES,
       f.ACV_DIST_PCT, f.BASE_VALUE_SALES, f.BASE_UNIT_SALES, f.STORES_SELLING, f.DATA_VERSION
FROM SR_DB.SRC.V_SRC_FACT_WEEKLY_ALL f
WHERE f.WEEK_END_DATE <= (
  SELECT SETTING_VALUE::VARCHAR::DATE FROM SR_DB.OPS.SETTINGS WHERE SETTING_KEY = 'AS_OF_WEEK_END'
);

CREATE OR REPLACE VIEW SR_DB.SRC.V_SRC_PRODUCT (
  PRODUCT_ID, ITEM_DESC, BRAND, MANUFACTURER, CATEGORY, SEGMENT, PACK_SIZE, IS_PRIVATE_LABEL
)
COMMENT = 'Product hierarchy (contract L3)'
AS
SELECT p.<PRODUCT_KEY>::VARCHAR, p.<ITEM_DESC>, p.<BRAND>, p.<MANUFACTURER>, p.<CATEGORY>,
       p.<SEGMENT>, p.<PACK_SIZE>::VARCHAR, COALESCE(p.<PRIVATE_LABEL_FLAG>, FALSE)::BOOLEAN
FROM <NIQ_DB>.<NIQ_SCHEMA>.<PRODUCT_TABLE> p;

CREATE OR REPLACE VIEW SR_DB.SRC.V_SRC_MARKET (
  MARKET_ID, MARKET_NAME, MARKET_LEVEL, PARENT_MARKET_ID, RETAILER, CHANNEL, REGION
)
COMMENT = 'Market hierarchy: TOTAL, CHANNEL, RETAILER, REGION (contract L3)'
AS
SELECT m.<MARKET_KEY>::VARCHAR, m.<MARKET_DESC>, m.<LEVEL_CODE>, m.<PARENT_KEY>::VARCHAR,
       m.<RETAILER>, m.<CHANNEL>, m.<REGION>
FROM <NIQ_DB>.<NIQ_SCHEMA>.<MARKET_TABLE> m;

-- Optional (rule R1 uses it when present). Uncomment once a store-universe source is mapped.
-- CREATE OR REPLACE VIEW SR_DB.SRC.V_SRC_MARKET_UNIVERSE (MARKET_ID, WEEK_END_DATE, STORE_COUNT) AS
-- SELECT u.<MARKET_KEY>::VARCHAR, u.<WEEK_END_COL>::DATE, u.<STORE_COUNT>::NUMBER(9,0)
-- FROM <NIQ_DB>.<NIQ_SCHEMA>.<UNIVERSE_TABLE> u;
