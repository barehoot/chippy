-- T1 fixtures (schema SR_DB.TEST). Only two, because everything else is real data.
CREATE TABLE IF NOT EXISTS SR_DB.TEST.FX_RECON_REFERENCE (     -- the five numbers SR-013 reconciles against
  CHECK_ID        VARCHAR(8) PRIMARY KEY,
  DESCRIPTION     VARCHAR NOT NULL,
  PERIOD_CODE     VARCHAR(8) NOT NULL,
  MARKET_ID       VARCHAR NOT NULL,
  CATEGORY        VARCHAR NOT NULL,
  BRAND           VARCHAR,                      -- NULL for a category total
  METRIC          VARCHAR(16) NOT NULL,         -- VALUE_SALES | VALUE_SHARE | DIST_SHARE
  REFERENCE_VALUE FLOAT NOT NULL,
  SOURCE_NOTE     VARCHAR NOT NULL              -- which NIQ report and page the number came from
);
CREATE TABLE IF NOT EXISTS SR_DB.TEST.FX_DEMO_EVENTS (         -- real data events the demo replays into
  EVENT_ID         VARCHAR(8) PRIMARY KEY,
  AS_OF_WEEK       DATE NOT NULL,
  CMP_CODE         VARCHAR(16) NOT NULL,
  MARKET_ID        VARCHAR NOT NULL,
  EXPECTED_RULE_ID VARCHAR(16) NOT NULL,       -- for example R2_FEED
  NOTE             VARCHAR NOT NULL              -- what Input Validation recorded about it
);
