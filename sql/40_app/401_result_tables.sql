-- SR-020 · L5 result tables. Every run writes rows keyed by RUN_ID, so a brief traces back to its numbers.
-- SHIFT_ID = MD5(RUN_ID || '|' || CMP_CODE || '|' || MARKET_ID || '|' || CATEGORY || '|' || BRAND)
-- SCOPE_KEY = CATEGORY || '|' || PARENT_MARKET || '|' || FOCUS_MANUFACTURER
USE ROLE SR_DEV;

CREATE TABLE IF NOT EXISTS SR_DB.APP.SHIFT_CANDIDATE (
  RUN_ID            VARCHAR(36)   NOT NULL,
  SHIFT_ID          VARCHAR(32)   NOT NULL,
  CMP_CODE          VARCHAR(16)   NOT NULL,
  MARKET_ID         VARCHAR       NOT NULL,
  CATEGORY          VARCHAR       NOT NULL,
  MANUFACTURER      VARCHAR,
  BRAND             VARCHAR       NOT NULL,
  SH1               FLOAT,
  SH0               FLOAT,
  D_SHARE           FLOAT,
  VALUE_AT_STAKE    NUMBER(18,2),
  Z_SCORE           FLOAT,
  ANOMALY_WEEKS     NUMBER(2,0)   DEFAULT 0,      -- anomalous weeks among the last 4 (ML)
  ANOMALY_CONFIRMED BOOLEAN       DEFAULT FALSE,
  PASSED_GATES      BOOLEAN       NOT NULL,
  GATE_NOTES        VARIANT,
  CREATED_AT        TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
  PRIMARY KEY (RUN_ID, SHIFT_ID)
);

CREATE TABLE IF NOT EXISTS SR_DB.APP.SHARE_BRIDGE (
  RUN_ID         VARCHAR(36) NOT NULL,
  SHIFT_ID       VARCHAR(32) NOT NULL,
  CMP_CODE       VARCHAR(16) NOT NULL,
  MARKET_ID      VARCHAR     NOT NULL,
  CATEGORY       VARCHAR     NOT NULL,
  BRAND          VARCHAR     NOT NULL,
  MODE           VARCHAR(1)  NOT NULL,   -- A | B | C | D
  STATUS         VARCHAR(8)  NOT NULL,   -- OK | NEW | EXIT | NO_DATA
  SH1            FLOAT,
  SH0            FLOAT,
  D_SHARE        FLOAT,
  LMDI_WEIGHT    FLOAT,                  -- logarithmic mean of SH1 and SH0
  DIST_PTS       FLOAT,                  -- distribution share term, points
  VELOCITY_PTS   FLOAT,                  -- base unit velocity (A), unit velocity (B) or value velocity (C)
  PRICE_PTS      FLOAT,                  -- base price index (A) or average price index (B)
  PROMO_PTS      FLOAT,                  -- promo index (A only)
  RESIDUAL_PTS   FLOAT,                  -- D_SHARE*100 minus the sum of terms; |x| < 1e-6 expected
  DS1 FLOAT, DS0 FLOAT, PI1 FLOAT, PI0 FLOAT, PRI1 FLOAT, PRI0 FLOAT,  -- distribution share, price and promo indices
  NOTE           VARCHAR,
  PRIMARY KEY (RUN_ID, SHIFT_ID)
);

CREATE TABLE IF NOT EXISTS SR_DB.APP.ARTEFACT_CHECK (
  RUN_ID     VARCHAR(36)   NOT NULL,
  CMP_CODE   VARCHAR(16)   NOT NULL,
  MARKET_ID  VARCHAR       NOT NULL,
  CATEGORY   VARCHAR       NOT NULL,
  BRAND      VARCHAR,                   -- NULL = market-level rule
  RULE_ID    VARCHAR(16)   NOT NULL,    -- R1_COVERAGE | R2_FEED | R3_RESTATE | R4_RECODE | R5_SPIKE | R6_GAP
  SEVERITY   VARCHAR(8)    NOT NULL,    -- HIGH | MEDIUM
  EVIDENCE   VARIANT       NOT NULL,    -- numbers that fired the rule, each with its source
  CREATED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS SR_DB.APP.SHIFT_RANKED (
  RUN_ID          VARCHAR(36) NOT NULL,
  SHIFT_ID        VARCHAR(32) NOT NULL,
  SCOPE_KEY       VARCHAR     NOT NULL,
  RANK_NO         NUMBER(4,0),
  CMP_CODE        VARCHAR(16) NOT NULL,
  MARKET_ID       VARCHAR     NOT NULL,
  CATEGORY        VARCHAR     NOT NULL,
  MANUFACTURER    VARCHAR,
  BRAND           VARCHAR     NOT NULL,
  IS_FOCUS        BOOLEAN     NOT NULL,
  D_SHARE         FLOAT,
  VALUE_AT_STAKE  NUMBER(18,2),
  CONFIDENCE      FLOAT,                 -- 0..1
  ARTEFACT_LABEL  VARCHAR(24) NOT NULL,  -- MARKET_MOVE | MIXED | POSSIBLE_DATA_EFFECT
  ART_FACTOR      FLOAT       NOT NULL,
  SCORE           FLOAT       NOT NULL,
  SUPPRESSED      BOOLEAN     NOT NULL,
  SUPPRESS_REASON VARCHAR,
  SELECTED        BOOLEAN     NOT NULL,  -- in the brief's top N
  PRIMARY KEY (RUN_ID, SHIFT_ID)
);

CREATE TABLE IF NOT EXISTS SR_DB.APP.SHIFT_WHERE (
  RUN_ID                VARCHAR(36) NOT NULL,
  SHIFT_ID              VARCHAR(32) NOT NULL,
  METHOD                VARCHAR(16) NOT NULL,   -- EXACT_RETAILER | TOP_INSIGHTS
  RANK_NO               NUMBER(4,0) NOT NULL,
  CONTRIBUTOR           VARCHAR     NOT NULL,   -- retailer name, or the TOP_INSIGHTS segment as text
  PERF_PTS              FLOAT,                  -- exact: within-retailer share change x average weight
  MIX_PTS               FLOAT,                  -- exact: weight change x average share
  TOTAL_PTS             FLOAT,
  METRIC_CONTROL        FLOAT,                  -- TOP_INSIGHTS columns
  METRIC_TEST           FLOAT,
  CONTRIBUTION          FLOAT,
  RELATIVE_CONTRIBUTION FLOAT,
  GROWTH_RATE           FLOAT
);

CREATE TABLE IF NOT EXISTS SR_DB.APP.SHARE_FLOW (
  RUN_ID     VARCHAR(36) NOT NULL,
  CMP_CODE   VARCHAR(16) NOT NULL,
  MARKET_ID  VARCHAR     NOT NULL,
  CATEGORY   VARCHAR     NOT NULL,
  FROM_BRAND VARCHAR     NOT NULL,
  TO_BRAND   VARCHAR     NOT NULL,
  FLOW_PTS   FLOAT       NOT NULL,      -- share points moved, proportional allocation
  METHOD     VARCHAR(16) NOT NULL DEFAULT 'PROPORTIONAL'
);

CREATE TABLE IF NOT EXISTS SR_DB.APP.EARLY_WARNING (
  RUN_ID              VARCHAR(36) NOT NULL,
  MARKET_ID           VARCHAR     NOT NULL,
  CATEGORY            VARCHAR     NOT NULL,
  BRAND               VARCHAR     NOT NULL,
  SIGNAL              VARCHAR(16) NOT NULL,   -- DIST_DROP | PRICE_RISE
  LATEST_WEEK         DATE        NOT NULL,
  LEVER_LATEST        FLOAT,
  LEVER_L4W           FLOAT,
  LEVER_CHG           FLOAT,                  -- latest / L4W - 1
  PROJECTED_SHARE_PTS FLOAT,                  -- DIST_DROP only: mechanical, other levers held
  ML_CONFIRMED        BOOLEAN DEFAULT FALSE,
  NOTE                VARCHAR
);

CREATE TABLE IF NOT EXISTS SR_DB.APP.FACT_PACK (
  RUN_ID     VARCHAR(36)   NOT NULL,
  BRIEF_ID   VARCHAR(36)   NOT NULL,
  SCOPE_KEY  VARCHAR       NOT NULL,
  PACK       VARIANT       NOT NULL,
  N_FACTS    NUMBER(5,0)   NOT NULL,
  CREATED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
  PRIMARY KEY (BRIEF_ID)
);

CREATE TABLE IF NOT EXISTS SR_DB.APP.BRIEF (
  BRIEF_ID        VARCHAR(36)   NOT NULL PRIMARY KEY,
  RUN_ID          VARCHAR(36)   NOT NULL,
  SCOPE_KEY       VARCHAR       NOT NULL,
  AS_OF_WEEK      DATE          NOT NULL,
  STATUS          VARCHAR(12)   NOT NULL,   -- DRAFT | PUBLISHED | FAILED
  GENERATOR       VARCHAR(12),              -- LLM | LLM_RETRY | TEMPLATE
  MODEL           VARCHAR(64),
  HEADLINE        VARCHAR(400),
  BODY_MD         VARCHAR,
  BODY_HTML       VARCHAR,
  LLM_JSON        VARIANT,
  VIOLATIONS      VARIANT,
  TOKENS_IN       NUMBER(9,0),
  TOKENS_OUT      NUMBER(9,0),
  CREATED_AT      TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
  PUBLISHED_AT    TIMESTAMP_LTZ,
  NOTIFIED_AT     TIMESTAMP_LTZ,
  NOTIFY_ATTEMPTS NUMBER(2,0)   DEFAULT 0
);
ALTER TABLE SR_DB.APP.BRIEF SET CHANGE_TRACKING = TRUE;   -- needed by the alert on new data
