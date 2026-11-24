# Share Radar: low-level design (LLD)

This file is the build contract: CoCo generates code from it, and every name here is final unless a ticket changes it. Replace `SR_DB` with the team database and `<NIQ_...>` placeholders with what SR-003 discovers.

## L1 Conventions, environment and setup

One database, eight schemas, six roles (SR\_UI is added in L12) and two warehouses. Every object name is fully qualified, every threshold lives in `OPS.SETTINGS`, and every procedure tags its queries.

| Kind | Pattern | Example |
| --- | --- | --- |
| Dynamic table | `CORE.DT_<NOUN>` | `CORE.DT_SHARE_COMPARE` |
| View | `<SCHEMA>.V_<NOUN>` | `SEM.V_SEM_SHARE_GRID` |
| Result table | `APP.<NOUN>` | `APP.SHARE_BRIDGE` |
| Procedure | `APP.SP_<VERB>_<NOUN>` | `APP.SP_BUILD_FACT_PACK` |
| Agent tool procedure | `APP.TOOL_<VERB>_<NOUN>` | `APP.TOOL_GET_SHARE_BRIDGE` |
| ML instance | `ML.<KIND>_<NOUN>` | `ML.AD_SHARE_WEEKLY` |
| Stream, task, alert | `OPS.ST_`, `OPS.T_`, `OPS.A_` | `OPS.T_RUN_WEEK` |
| Setting key | `UPPER_SNAKE` | `MIN_SHARE_PTS` |
| Test | `T-<AREA>-NN` | `T-BR-01` |

**Units.** Shares are stored as fractions (0–1); columns ending `_PCT` or `_PTS` are ×100 for display only. Money is local currency, `NUMBER(18,2)`. Weeks are identified by `WEEK_END_DATE DATE`. Timestamps are `TIMESTAMP_LTZ`.

**Query tag** (first statement of every procedure step):

```sql
ALTER SESSION SET QUERY_TAG = 'SR|run=<RUN_ID>|step=<STEP>';
```

**Setup DDL** — `sql/00_setup/001_roles_wh_db.sql`. Skip the role and warehouse part if the organizers provisioned them; then map every `SR_*` role below to the team role.

```sql
USE ROLE SECURITYADMIN;
CREATE ROLE IF NOT EXISTS SR_ADMIN;    -- owns the database
CREATE ROLE IF NOT EXISTS SR_DEV;      -- builds (CoCo sessions run as this role)
CREATE ROLE IF NOT EXISTS SR_APP;      -- owns tasks, alerts, the stream and the admin app; runs the pipeline
CREATE ROLE IF NOT EXISTS SR_ANALYST;  -- CoWork and Streamlit users
CREATE ROLE IF NOT EXISTS SR_JUDGE;    -- read-only demo role
GRANT ROLE SR_DEV TO ROLE SR_ADMIN;
GRANT ROLE SR_APP TO ROLE SR_ADMIN;
GRANT ROLE SR_ANALYST TO ROLE SR_ADMIN;
GRANT ROLE SR_JUDGE TO ROLE SR_ADMIN;

USE ROLE SYSADMIN;
CREATE WAREHOUSE IF NOT EXISTS SR_WH_XS WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE;
CREATE WAREHOUSE IF NOT EXISTS SR_WH_M  WAREHOUSE_SIZE = 'MEDIUM' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE;
CREATE DATABASE IF NOT EXISTS SR_DB;
CREATE SCHEMA IF NOT EXISTS SR_DB.SRC;   -- adapter views (only place NIQ tables are named)
CREATE SCHEMA IF NOT EXISTS SR_DB.CORE;  -- dynamic tables
CREATE SCHEMA IF NOT EXISTS SR_DB.ML;    -- ML instances and ML outputs
CREATE SCHEMA IF NOT EXISTS SR_DB.APP;   -- procedures, result tables, Streamlit
CREATE SCHEMA IF NOT EXISTS SR_DB.SEM;   -- semantic views, search service, agent
CREATE SCHEMA IF NOT EXISTS SR_DB.OPS;   -- settings, logs, streams, tasks, alerts
CREATE SCHEMA IF NOT EXISTS SR_DB.KB;    -- method documents
CREATE SCHEMA IF NOT EXISTS SR_DB.TEST;  -- test fixtures only
GRANT OWNERSHIP ON DATABASE SR_DB TO ROLE SR_ADMIN COPY CURRENT GRANTS;
GRANT OWNERSHIP ON ALL SCHEMAS IN DATABASE SR_DB TO ROLE SR_ADMIN COPY CURRENT GRANTS;
GRANT USAGE ON WAREHOUSE SR_WH_XS TO ROLE SR_DEV;
GRANT USAGE ON WAREHOUSE SR_WH_M  TO ROLE SR_DEV;
```

**Settings** — `sql/00_setup/002_settings.sql`. Set `AS_OF_WEEK_END` four weeks before the latest real week, so the demo can replay four weeks.

```sql
CREATE TABLE IF NOT EXISTS SR_DB.OPS.SETTINGS (
  SETTING_KEY    VARCHAR(64)   NOT NULL PRIMARY KEY,
  SETTING_VALUE  VARIANT       NOT NULL,
  DESCRIPTION    VARCHAR(500),
  UPDATED_AT     TIMESTAMP_LTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

MERGE INTO SR_DB.OPS.SETTINGS t
USING (
  SELECT column1 AS SETTING_KEY, PARSE_JSON(column2) AS SETTING_VALUE, column3 AS DESCRIPTION
  FROM VALUES
    ('AS_OF_WEEK_END',      '"<yyyy-mm-dd>"',      'Replay control: adapter shows weeks up to this date'),
    ('SCOPE_CATEGORY',      '"<category>"',        'Demo category (V_SRC_PRODUCT.CATEGORY)'),
    ('SCOPE_PARENT_MARKET', '"<market_id>"',       'Parent market whose child retailer markets partition it'),
    ('FOCUS_MANUFACTURER',  '"<manufacturer>"',    'Client whose brands lead the brief'),
    ('COMPARES',            '["L4W_VS_YA","L4W_VS_PP","L12W_VS_YA"]', 'Comparisons evaluated each run'),
    ('MIN_SHARE_PTS',       '0.3',   'Gate: absolute share change, points'),
    ('MIN_VALUE_AT_STAKE',  '50000', 'Gate: |share change| x category sales, local currency'),
    ('MIN_Z',               '2.0',   'Gate: z-score of the change against history'),
    ('TOP_N',               '5',     'Shifts per brief'),
    ('SUPPRESS_RUNS',       '3',     'Look-back runs for repeat suppression'),
    ('SUPPRESS_GROWTH',     '0.2',   'A repeat is shown again if it grew by this fraction'),
    ('ART_STORE_CHG',       '0.05',  'R1: store-count change that marks a coverage change'),
    ('ART_CAT_TDP_JUMP',    '0.15',  'R1 proxy: category TDP log-change'),
    ('ART_CAT_SPPD_FLAT',   '0.03',  'R1 proxy: category velocity log-change treated as flat'),
    ('ART_RECODE_TOL',      '0.2',   'R4: exit vs entry item sales tolerance'),
    ('ART_SPIKE_K',         '5',     'R5: std deviations from the trailing 13-week mean'),
    ('EW_DIST_DROP',        '-0.05', 'Early warning: latest-week distribution share vs L4W'),
    ('EW_PRICE_RISE',       '0.03',  'Early warning: latest-week price index vs L4W'),
    ('LLM_MODEL',           '"claude-sonnet-4-5"', 'Confirm availability in the smoke test'),
    ('LLM_FALLBACK_MODEL',  '"mistral-large2"',    'Used after one failure'),
    ('NOTIFY_EMAILS',       '["<analyst>@nielseniq.com"]', 'Verified Snowflake user emails only'),
    ('TEAMS_ENABLED',       'false', 'Stretch: Teams webhook'),
    ('DISPLAY_ALIAS',       'false', 'Mask manufacturer and brand names in UI and briefs'),
    ('MAX_CREDITS_PER_RUN', '5',     'Above this, ML and TOP_INSIGHTS steps are skipped'),
    ('CURRENCY',            '"INR"', 'Display currency code for briefs and the app')
) s
ON t.SETTING_KEY = s.SETTING_KEY
WHEN MATCHED THEN UPDATE SET t.SETTING_VALUE = s.SETTING_VALUE, t.DESCRIPTION = s.DESCRIPTION, t.UPDATED_AT = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (SETTING_KEY, SETTING_VALUE, DESCRIPTION) VALUES (s.SETTING_KEY, s.SETTING_VALUE, s.DESCRIPTION);

-- Read helper for procedures (not used inside dynamic tables)
CREATE OR REPLACE FUNCTION SR_DB.OPS.CFG(K VARCHAR)
RETURNS VARIANT
AS $$ SELECT SETTING_VALUE FROM SR_DB.OPS.SETTINGS WHERE SETTING_KEY = K $$;
```

**Feature smoke test** — `sql/00_setup/009_feature_smoke_test.sql`, run on Wednesday as the team role. Each statement must succeed; a failure maps to assumption A5 or A6.

```sql
SELECT AI_COMPLETE('claude-sonnet-4-5', 'Reply with the word OK');                       -- LLM access and model
SELECT AI_COMPLETE(
  model => 'claude-sonnet-4-5',
  prompt => 'Return ok = true',
  response_format => {'type': 'json', 'schema': {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok']}}
);                                                                                         -- structured output
CREATE SNOWFLAKE.ML.TOP_INSIGHTS IF NOT EXISTS SR_DB.ML.TI_SMOKE();                     -- ML privilege
SHOW SNOWFLAKE.ML.ANOMALY_DETECTION IN SCHEMA SR_DB.ML;                                 -- ML class visible
CREATE OR REPLACE DYNAMIC TABLE SR_DB.TEST.DT_SMOKE TARGET_LAG = '1 day' WAREHOUSE = SR_WH_XS AS SELECT 1 AS X;
SHOW AGENTS IN ACCOUNT;                                                                  -- Cortex Agents
DESCRIBE SNOWFLAKE INTELLIGENCE SNOWFLAKE_INTELLIGENCE_OBJECT_DEFAULT;                   -- CoWork object exists
SHOW NOTIFICATION INTEGRATIONS;                                                          -- what we may send through
DROP DYNAMIC TABLE SR_DB.TEST.DT_SMOKE;
```

## L2 Repository layout

One repository, connected to a Snowsight Workspace or cloned for the CoCo CLI. SQL files deploy in numeric order; each file holds one object and can be rerun.

```text
share-radar/
├── AGENTS.md                         # agent rules (docs/TESTS_AND_COCO.md, T4)
├── CLAUDE.md                         # Claude Code entry point; imports AGENTS.md
├── README.md                         # deploy order, replay how-to, object list
├── .sr_ticket                        # current ticket ID, read by the Stop hook
├── .cortex/
│   ├── settings.json                 # hooks (Stop -> scripts/coco_log.py)
│   ├── agents/sr-reviewer.md         # reviewer subagent
│   └── skills/
│       ├── sr-sql-conventions/SKILL.md
│       ├── share-methodology/SKILL.md   # also uploaded to @SR_DB.SEM.SKILLS for the agent (stretch)
│       ├── sr-cortex-agent/SKILL.md
│       ├── sr-streamlit/SKILL.md
│       └── sr-tests/SKILL.md
├── .claude/                          # same skills, reviewer and Stop hook, for Claude Code
├── sql/
│   ├── 00_setup/   001_roles_wh_db.sql  002_settings.sql  003_ops_tables.sql  009_feature_smoke_test.sql
│   ├── 10_src/     101_adapter_views.sql  102_capability.sql
│   ├── 20_core/    201_dt_period_week.sql  202_dt_brand_week.sql  203_dt_cat_week.sql
│   │               204_dt_brand_period.sql  205_dt_cat_period.sql  206_dt_share_compare.sql
│   │               207_dt_share_week.sql  208_v_grid_views.sql
│   ├── 30_ml/      301_sp_ml_share_anomaly.sql  302_sp_where_insights.sql  303_sp_ml_lever_anomaly.sql
│   ├── 40_app/     401_result_tables.sql  402_sp_snapshot.sql  403_sp_detect_shifts.sql
│   │               404_sp_bridge.sql  405_sp_artefact.sql  406_sp_rank.sql  407_sp_where.sql
│   │               408_sp_flow.sql  409_sp_early_warning.sql  410_sp_what_if.sql
│   │               411_sp_build_fact_pack.sql  412_sp_write_brief.sql  413_sp_run_week.sql
│   │               414_tool_procs.sql  415_ui_objects.sql
│   ├── 50_sem/     501_v_sem_views.sql  502_sv_share.sql  503_kb_and_search.sql  504_agent.sql  505_cowork.sql
│   ├── 60_ops/     601_stream_task.sql  602_replay.sql  603_notifications.sql  604_alert.sql  605_dmf.sql
│   │               606_observability.sql
│   └── 70_sec/     701_grants.sql  702_row_access.sql  703_app_usage.sql
├── python/
│   ├── sr_lib/     __init__.py  bridge.py  validator.py  render.py  fallback.py  factpack.py  run.py
│   └── tests/      test_bridge.py  test_validator.py  test_render.py  test_fallback.py  test_ui.py
├── streamlit/                        # Snowflake CLI project for both apps (L11)
│   ├── snowflake.yml                 # entities share_radar (owner SR_UI), share_radar_admin (owner SR_APP)
│   ├── streamlit_app.py              # entry point: read-only app
│   ├── admin_app.py                  # entry point: admin app
│   ├── pages/      0_Radar.py  1_Shift_detail.py  2_Brief.py  3_Trust.py  4_Settings.py
│   ├── sr_ui/      __init__.py  nav.py  data.py  charts.py  format.py
│   ├── .streamlit/config.toml
│   └── environment.yml
├── kb/             acv_and_tdp.md  share_bridge.md  artefact_rules.md  periods.md  glossary.md
├── eval/           golden_set.csv  run_eval.sql  run_eval.py
├── tests/sql/      T-SRC-01.sql … T-SEC-01.sql  run_all.sql
├── scripts/        coco_log.py  deploy_all.sh  load_kb.py
└── docs/           HLD.md  LLD.md  TESTS_AND_COCO.md  TICKETS.md  img/  coco_log.md  coco_log.jsonl  decisions.md  demo_script.md
```

**Deploy order:** `00_setup` → `10_src` → `20_core` → `40_app/401` (tables) → `30_ml` → rest of `40_app` → `50_sem` → `60_ops` → `70_sec/701`, `702` → the two Streamlit apps → `70_sec/703`. `scripts/deploy_all.sh` runs exactly this. Each SQL file runs with `snow sql -f <file> -c sr`. Then, from `streamlit/`, it runs `snow streamlit deploy share_radar --replace --role SR_UI -c sr` and `snow streamlit deploy share_radar_admin --replace --role SR_APP -c sr`. The role flag makes each app's owner the role it should run as.

**`streamlit/snowflake.yml`** (Snowflake CLI project for the two apps). The CLI runs from `streamlit/`, so artifact paths are relative to it and match `main_file`:

```yaml
definition_version: 2
entities:
  share_radar:
    type: streamlit
    identifier:
      name: SHARE_RADAR
      database: SR_DB
      schema: APP
    query_warehouse: SR_WH_XS
    title: "Share Radar"
    main_file: streamlit_app.py
    artifacts:
      - streamlit_app.py
      - environment.yml
      - .streamlit/config.toml
      - pages/
      - sr_ui/
  share_radar_admin:
    type: streamlit
    identifier:
      name: SHARE_RADAR_ADMIN
      database: SR_DB
      schema: APP
    query_warehouse: SR_WH_XS
    title: "Share Radar admin"
    main_file: admin_app.py
    artifacts:
      - admin_app.py
      - environment.yml
      - .streamlit/config.toml
      - pages/
      - sr_ui/
```

## L3 Source adapter contract and capability check

Four views form the contract between NIQ's tables and everything else; `sql/10_src/101_adapter_views.sql` is the only file allowed to name NIQ objects. Optional columns may be NULL, and the capability check then picks a simpler bridge mode.

**`SRC.V_SRC_FACT_WEEKLY_ALL`** — grain: one row per `WEEK_END_DATE` × `MARKET_ID` × `PRODUCT_ID` (item level).

| Column | Type | Meaning | Required |
| --- | --- | --- | --- |
| `WEEK_END_DATE` | DATE | NIQ week-ending date | Yes |
| `MARKET_ID` | VARCHAR | NIQ market key (total, channel, retailer or region) | Yes |
| `PRODUCT_ID` | VARCHAR | Item key (UPC or NIQ item code) | Yes |
| `VALUE_SALES` | NUMBER(18,2) | Sales value, local currency | Yes |
| `VOLUME_SALES` | NUMBER(18,3) | Equivalised volume (kg, l or standard units) | No |
| `UNIT_SALES` | NUMBER(18,3) | Units sold | No |
| `ACV_DIST_PCT` | NUMBER(9,4) | %ACV weighted distribution of the item, 0–100 | No (mode C or lower without it) |
| `BASE_VALUE_SALES` | NUMBER(18,2) | Baseline (non-promoted) sales value | No (mode A needs it) |
| `BASE_UNIT_SALES` | NUMBER(18,3) | Baseline units | No (mode A needs it) |
| `STORES_SELLING` | NUMBER(9,0) | Stores selling the item | No |
| `DATA_VERSION` | VARCHAR | Load or release identifier, if NIQ provides one | No |

**`SRC.V_SRC_FACT_WEEKLY`** — the same columns, filtered to `WEEK_END_DATE <= AS_OF_WEEK_END` (the replay control). Everything downstream reads this view.

**`SRC.V_SRC_PRODUCT`** — `PRODUCT_ID`, `ITEM_DESC`, `BRAND`, `MANUFACTURER`, `CATEGORY`, `SEGMENT`, `PACK_SIZE`, `IS_PRIVATE_LABEL` (BOOLEAN).

**`SRC.V_SRC_MARKET`** — `MARKET_ID`, `MARKET_NAME`, `MARKET_LEVEL` ('TOTAL', 'CHANNEL', 'RETAILER', 'REGION'), `PARENT_MARKET_ID` (NULL for totals), `RETAILER`, `CHANNEL`, `REGION`.

**`SRC.V_SRC_MARKET_UNIVERSE`** (optional) — `MARKET_ID`, `WEEK_END_DATE`, `STORE_COUNT`. Rule R1 uses it when present.

**Mapping worksheet for SR-003** (CoCo proposes it after exploring the NIQ schema; a person approves it before any SQL is written):

| Contract column | NIQ object.column | Transform | Note |
| --- | --- | --- | --- |
| `WEEK_END_DATE` |  |  |  |
| `MARKET_ID` |  |  |  |
| `PRODUCT_ID` |  |  |  |
| `VALUE_SALES` |  |  |  |
| `UNIT_SALES` |  |  |  |
| `ACV_DIST_PCT` |  |  |  |
| `BASE_VALUE_SALES` |  |  |  |
| `BASE_UNIT_SALES` |  |  |  |
| `STORES_SELLING` |  |  |  |

**DDL template** — `sql/10_src/101_adapter_views.sql`:

```sql
CREATE OR REPLACE VIEW SR_DB.SRC.V_SRC_FACT_WEEKLY_ALL (
  WEEK_END_DATE, MARKET_ID, PRODUCT_ID, VALUE_SALES, VOLUME_SALES, UNIT_SALES,
  ACV_DIST_PCT, BASE_VALUE_SALES, BASE_UNIT_SALES, STORES_SELLING, DATA_VERSION
) AS
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

CREATE OR REPLACE VIEW SR_DB.SRC.V_SRC_FACT_WEEKLY AS
SELECT f.*
FROM SR_DB.SRC.V_SRC_FACT_WEEKLY_ALL f
WHERE f.WEEK_END_DATE <= (
  SELECT SETTING_VALUE::VARCHAR::DATE FROM SR_DB.OPS.SETTINGS WHERE SETTING_KEY = 'AS_OF_WEEK_END'
);

CREATE OR REPLACE VIEW SR_DB.SRC.V_SRC_PRODUCT (
  PRODUCT_ID, ITEM_DESC, BRAND, MANUFACTURER, CATEGORY, SEGMENT, PACK_SIZE, IS_PRIVATE_LABEL
) AS
SELECT p.<PRODUCT_KEY>::VARCHAR, p.<ITEM_DESC>, p.<BRAND>, p.<MANUFACTURER>, p.<CATEGORY>,
       p.<SEGMENT>, p.<PACK_SIZE>::VARCHAR, COALESCE(p.<PRIVATE_LABEL_FLAG>, FALSE)::BOOLEAN
FROM <NIQ_DB>.<NIQ_SCHEMA>.<PRODUCT_TABLE> p;

CREATE OR REPLACE VIEW SR_DB.SRC.V_SRC_MARKET (
  MARKET_ID, MARKET_NAME, MARKET_LEVEL, PARENT_MARKET_ID, RETAILER, CHANNEL, REGION
) AS
SELECT m.<MARKET_KEY>::VARCHAR, m.<MARKET_DESC>, m.<LEVEL_CODE>, m.<PARENT_KEY>::VARCHAR,
       m.<RETAILER>, m.<CHANNEL>, m.<REGION>
FROM <NIQ_DB>.<NIQ_SCHEMA>.<MARKET_TABLE> m;
```

**Capability check** — `sql/10_src/102_capability.sql`. Called at the start of every run; the result caps the bridge mode for that run.

```sql
CREATE TABLE IF NOT EXISTS SR_DB.OPS.CAPABILITY (
  CHECKED_AT       TIMESTAMP_LTZ NOT NULL,
  AS_OF_WEEK       DATE          NOT NULL,
  N_WEEKS          NUMBER        NOT NULL,
  HAS_DIST         BOOLEAN       NOT NULL,
  HAS_UNITS        BOOLEAN       NOT NULL,
  HAS_BASE_VALUE   BOOLEAN       NOT NULL,
  HAS_BASE_UNITS   BOOLEAN       NOT NULL,
  HAS_STORES       BOOLEAN       NOT NULL,
  HAS_UNIVERSE     BOOLEAN       NOT NULL,
  MAX_BRIDGE_MODE  VARCHAR(1)    NOT NULL   -- 'A' | 'B' | 'C' | 'D'
);

CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_CAPABILITY_CHECK()
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
BEGIN
  INSERT INTO SR_DB.OPS.CAPABILITY
  WITH f AS (
    SELECT * FROM SR_DB.SRC.V_SRC_FACT_WEEKLY
    WHERE WEEK_END_DATE > DATEADD(week, -8, (SELECT MAX(WEEK_END_DATE) FROM SR_DB.SRC.V_SRC_FACT_WEEKLY))
  ), c AS (
    SELECT
      COUNT_IF(ACV_DIST_PCT IS NOT NULL)     / NULLIF(COUNT(*), 0) >= 0.95 AS HAS_DIST,
      COUNT_IF(UNIT_SALES IS NOT NULL)       / NULLIF(COUNT(*), 0) >= 0.95 AS HAS_UNITS,
      COUNT_IF(BASE_VALUE_SALES IS NOT NULL) / NULLIF(COUNT(*), 0) >= 0.95 AS HAS_BASE_VALUE,
      COUNT_IF(BASE_UNIT_SALES IS NOT NULL)  / NULLIF(COUNT(*), 0) >= 0.95 AS HAS_BASE_UNITS,
      COUNT_IF(STORES_SELLING IS NOT NULL)   / NULLIF(COUNT(*), 0) >= 0.95 AS HAS_STORES
    FROM f
  )
  SELECT CURRENT_TIMESTAMP(),
         (SELECT MAX(WEEK_END_DATE) FROM SR_DB.SRC.V_SRC_FACT_WEEKLY),
         (SELECT COUNT(DISTINCT WEEK_END_DATE) FROM SR_DB.SRC.V_SRC_FACT_WEEKLY),
         c.HAS_DIST, c.HAS_UNITS, c.HAS_BASE_VALUE, c.HAS_BASE_UNITS, c.HAS_STORES,
         (SELECT COUNT(*) > 0 FROM SR_DB.INFORMATION_SCHEMA.VIEWS
           WHERE TABLE_SCHEMA = 'SRC' AND TABLE_NAME = 'V_SRC_MARKET_UNIVERSE'),
         CASE WHEN c.HAS_DIST AND c.HAS_BASE_VALUE AND c.HAS_BASE_UNITS THEN 'A'
              WHEN c.HAS_DIST AND c.HAS_UNITS THEN 'B'
              WHEN c.HAS_DIST THEN 'C'
              ELSE 'D' END
  FROM c;
  RETURN 'OK';
END;
$$;
```

## L4 Core dynamic tables

Seven dynamic tables turn item-week facts into brand share now-versus-before; only the two leaf tables carry a time lag, and everything upstream refreshes on demand (`TARGET_LAG = DOWNSTREAM`). The scope filter on category keeps compute small for the demo; remove it for full coverage.

| Object | Grain | Lag | Feeds |
| --- | --- | --- | --- |
| `CORE.DT_PERIOD_WEEK` | period × week | DOWNSTREAM | all period tables |
| `CORE.DT_BRAND_WEEK` | week × market × brand | DOWNSTREAM | brand period, share week |
| `CORE.DT_CAT_WEEK` | week × market × category | DOWNSTREAM | category period, share week, artefact rules |
| `CORE.DT_BRAND_PERIOD` | period × market × brand | DOWNSTREAM | share compare, grid view |
| `CORE.DT_CAT_PERIOD` | period × market × category | DOWNSTREAM | share compare, grid view |
| `CORE.DT_SHARE_COMPARE` | comparison × market × brand | 15 minutes | stream, detector, bridge, flow |
| `CORE.DT_SHARE_WEEK` | week × market × brand | 15 minutes | z-score, ML, early warning |

```sql
-- sql/20_core/201_dt_period_week.sql
CREATE OR REPLACE DYNAMIC TABLE SR_DB.CORE.DT_PERIOD_WEEK
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = SR_WH_XS
  REFRESH_MODE = FULL
  COMMENT = 'Week membership of each reporting period, anchored on the latest available week'
AS
WITH asof AS (
  SELECT MAX(WEEK_END_DATE) AS AS_OF_WEEK FROM SR_DB.SRC.V_SRC_FACT_WEEKLY
), def AS (
  SELECT column1 AS PERIOD_CODE, column2 AS FROM_WK, column3 AS TO_WK
  FROM VALUES ('L4W', 3, 0), ('P4W', 7, 4), ('L4W_YA', 55, 52),
              ('L12W', 11, 0), ('L12W_YA', 63, 52), ('L52W', 51, 0), ('L52W_YA', 103, 52)
), weeks AS (
  SELECT DISTINCT WEEK_END_DATE FROM SR_DB.SRC.V_SRC_FACT_WEEKLY
)
SELECT d.PERIOD_CODE,
       w.WEEK_END_DATE,
       a.AS_OF_WEEK,
       DATEADD(week, -d.FROM_WK, a.AS_OF_WEEK) AS PERIOD_START,
       DATEADD(week, -d.TO_WK,   a.AS_OF_WEEK) AS PERIOD_END,
       d.FROM_WK - d.TO_WK + 1                 AS EXPECTED_WEEKS
FROM def d
CROSS JOIN asof a
JOIN weeks w
  ON w.WEEK_END_DATE BETWEEN DATEADD(week, -d.FROM_WK, a.AS_OF_WEEK) AND DATEADD(week, -d.TO_WK, a.AS_OF_WEEK);

-- sql/20_core/202_dt_brand_week.sql
CREATE OR REPLACE DYNAMIC TABLE SR_DB.CORE.DT_BRAND_WEEK
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = SR_WH_M
  REFRESH_MODE = AUTO
  COMMENT = 'Brand x market x week; TDP = sum of item %ACV'
AS
SELECT f.WEEK_END_DATE, f.MARKET_ID, p.CATEGORY, p.MANUFACTURER, p.BRAND,
       SUM(f.VALUE_SALES)           AS VALUE_SALES,
       SUM(f.VOLUME_SALES)          AS VOLUME_SALES,
       SUM(f.UNIT_SALES)            AS UNIT_SALES,
       SUM(f.ACV_DIST_PCT)          AS TDP,
       SUM(f.BASE_VALUE_SALES)      AS BASE_VALUE_SALES,
       SUM(f.BASE_UNIT_SALES)       AS BASE_UNIT_SALES,
       COUNT(DISTINCT f.PRODUCT_ID) AS ITEMS_SELLING,
       MAX(f.STORES_SELLING)        AS MAX_STORES_SELLING
FROM SR_DB.SRC.V_SRC_FACT_WEEKLY f
JOIN SR_DB.SRC.V_SRC_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
WHERE p.CATEGORY = (SELECT SETTING_VALUE::VARCHAR FROM SR_DB.OPS.SETTINGS WHERE SETTING_KEY = 'SCOPE_CATEGORY')
GROUP BY f.WEEK_END_DATE, f.MARKET_ID, p.CATEGORY, p.MANUFACTURER, p.BRAND;

-- sql/20_core/203_dt_cat_week.sql
CREATE OR REPLACE DYNAMIC TABLE SR_DB.CORE.DT_CAT_WEEK
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = SR_WH_XS
  REFRESH_MODE = AUTO
AS
SELECT WEEK_END_DATE, MARKET_ID, CATEGORY,
       SUM(VALUE_SALES)      AS VALUE_SALES,
       SUM(VOLUME_SALES)     AS VOLUME_SALES,
       SUM(UNIT_SALES)       AS UNIT_SALES,
       SUM(TDP)              AS TDP,
       SUM(BASE_VALUE_SALES) AS BASE_VALUE_SALES,
       SUM(BASE_UNIT_SALES)  AS BASE_UNIT_SALES,
       COUNT(DISTINCT BRAND) AS BRANDS_SELLING,
       SUM(ITEMS_SELLING)    AS ITEMS_SELLING
FROM SR_DB.CORE.DT_BRAND_WEEK
GROUP BY WEEK_END_DATE, MARKET_ID, CATEGORY;

-- sql/20_core/204_dt_brand_period.sql
CREATE OR REPLACE DYNAMIC TABLE SR_DB.CORE.DT_BRAND_PERIOD
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = SR_WH_M
  REFRESH_MODE = AUTO
AS
SELECT pw.PERIOD_CODE, MAX(pw.AS_OF_WEEK) AS AS_OF_WEEK,
       bw.MARKET_ID, bw.CATEGORY, bw.MANUFACTURER, bw.BRAND,
       COUNT(DISTINCT bw.WEEK_END_DATE) AS N_WEEKS_SELLING,
       SUM(bw.VALUE_SALES)      AS VALUE_SALES,
       SUM(bw.VOLUME_SALES)     AS VOLUME_SALES,
       SUM(bw.UNIT_SALES)       AS UNIT_SALES,
       SUM(bw.TDP)              AS TDP_SUM,
       SUM(bw.BASE_VALUE_SALES) AS BASE_VALUE_SALES,
       SUM(bw.BASE_UNIT_SALES)  AS BASE_UNIT_SALES
FROM SR_DB.CORE.DT_BRAND_WEEK bw
JOIN SR_DB.CORE.DT_PERIOD_WEEK pw ON pw.WEEK_END_DATE = bw.WEEK_END_DATE
GROUP BY pw.PERIOD_CODE, bw.MARKET_ID, bw.CATEGORY, bw.MANUFACTURER, bw.BRAND;

-- sql/20_core/205_dt_cat_period.sql
CREATE OR REPLACE DYNAMIC TABLE SR_DB.CORE.DT_CAT_PERIOD
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = SR_WH_XS
  REFRESH_MODE = AUTO
AS
SELECT pw.PERIOD_CODE, MAX(pw.AS_OF_WEEK) AS AS_OF_WEEK, MAX(pw.EXPECTED_WEEKS) AS EXPECTED_WEEKS,
       cw.MARKET_ID, cw.CATEGORY,
       COUNT(DISTINCT cw.WEEK_END_DATE) AS N_WEEKS,
       SUM(cw.VALUE_SALES)      AS CAT_VALUE_SALES,
       SUM(cw.VOLUME_SALES)     AS CAT_VOLUME_SALES,
       SUM(cw.UNIT_SALES)       AS CAT_UNIT_SALES,
       SUM(cw.TDP)              AS CAT_TDP_SUM,
       SUM(cw.BASE_VALUE_SALES) AS CAT_BASE_VALUE_SALES,
       SUM(cw.BASE_UNIT_SALES)  AS CAT_BASE_UNIT_SALES
FROM SR_DB.CORE.DT_CAT_WEEK cw
JOIN SR_DB.CORE.DT_PERIOD_WEEK pw ON pw.WEEK_END_DATE = cw.WEEK_END_DATE
GROUP BY pw.PERIOD_CODE, cw.MARKET_ID, cw.CATEGORY;

-- sql/20_core/206_dt_share_compare.sql
CREATE OR REPLACE DYNAMIC TABLE SR_DB.CORE.DT_SHARE_COMPARE
  TARGET_LAG = '15 minutes'
  WAREHOUSE = SR_WH_M
  REFRESH_MODE = AUTO
  COMMENT = 'Brand share now vs before; one row per CMP_CODE x MARKET_ID x CATEGORY x BRAND'
AS
WITH cmp AS (
  SELECT column1 AS CMP_CODE, column2 AS CUR_PERIOD, column3 AS BASE_PERIOD
  FROM VALUES ('L4W_VS_YA', 'L4W', 'L4W_YA'), ('L4W_VS_PP', 'L4W', 'P4W'),
              ('L12W_VS_YA', 'L12W', 'L12W_YA'), ('L52W_VS_YA', 'L52W', 'L52W_YA')
), keys AS (
  SELECT DISTINCT c.CMP_CODE, b.MARKET_ID, b.CATEGORY, b.MANUFACTURER, b.BRAND
  FROM cmp c
  JOIN SR_DB.CORE.DT_BRAND_PERIOD b ON b.PERIOD_CODE IN (c.CUR_PERIOD, c.BASE_PERIOD)
)
SELECT k.CMP_CODE, c.CUR_PERIOD, c.BASE_PERIOD, cp1.AS_OF_WEEK,
       k.MARKET_ID, k.CATEGORY, k.MANUFACTURER, k.BRAND,
       COALESCE(bp1.VALUE_SALES, 0) AS S1,    COALESCE(bp0.VALUE_SALES, 0) AS S0,
       cp1.CAT_VALUE_SALES          AS CS1,   cp0.CAT_VALUE_SALES          AS CS0,
       bp1.TDP_SUM                  AS TDP1,  bp0.TDP_SUM                  AS TDP0,
       cp1.CAT_TDP_SUM              AS CTDP1, cp0.CAT_TDP_SUM              AS CTDP0,
       bp1.UNIT_SALES               AS U1,    bp0.UNIT_SALES               AS U0,
       cp1.CAT_UNIT_SALES           AS CU1,   cp0.CAT_UNIT_SALES           AS CU0,
       bp1.BASE_VALUE_SALES         AS B1,    bp0.BASE_VALUE_SALES         AS B0,
       cp1.CAT_BASE_VALUE_SALES     AS CB1,   cp0.CAT_BASE_VALUE_SALES     AS CB0,
       bp1.BASE_UNIT_SALES          AS BU1,   bp0.BASE_UNIT_SALES          AS BU0,
       cp1.CAT_BASE_UNIT_SALES      AS CBU1,  cp0.CAT_BASE_UNIT_SALES      AS CBU0,
       cp1.N_WEEKS AS CAT_WEEKS1, cp0.N_WEEKS AS CAT_WEEKS0, cp1.EXPECTED_WEEKS AS EXP_WEEKS,
       COALESCE(bp1.VALUE_SALES, 0) / NULLIF(cp1.CAT_VALUE_SALES, 0) AS SH1,
       COALESCE(bp0.VALUE_SALES, 0) / NULLIF(cp0.CAT_VALUE_SALES, 0) AS SH0,
       SH1 - SH0                         AS D_SHARE,
       (SH1 - SH0) * cp1.CAT_VALUE_SALES AS VALUE_AT_STAKE
FROM keys k
JOIN cmp c ON c.CMP_CODE = k.CMP_CODE
LEFT JOIN SR_DB.CORE.DT_BRAND_PERIOD bp1
  ON bp1.PERIOD_CODE = c.CUR_PERIOD AND bp1.MARKET_ID = k.MARKET_ID AND bp1.CATEGORY = k.CATEGORY
 AND bp1.MANUFACTURER = k.MANUFACTURER AND bp1.BRAND = k.BRAND
LEFT JOIN SR_DB.CORE.DT_BRAND_PERIOD bp0
  ON bp0.PERIOD_CODE = c.BASE_PERIOD AND bp0.MARKET_ID = k.MARKET_ID AND bp0.CATEGORY = k.CATEGORY
 AND bp0.MANUFACTURER = k.MANUFACTURER AND bp0.BRAND = k.BRAND
LEFT JOIN SR_DB.CORE.DT_CAT_PERIOD cp1
  ON cp1.PERIOD_CODE = c.CUR_PERIOD AND cp1.MARKET_ID = k.MARKET_ID AND cp1.CATEGORY = k.CATEGORY
LEFT JOIN SR_DB.CORE.DT_CAT_PERIOD cp0
  ON cp0.PERIOD_CODE = c.BASE_PERIOD AND cp0.MARKET_ID = k.MARKET_ID AND cp0.CATEGORY = k.CATEGORY;

-- sql/20_core/207_dt_share_week.sql
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

-- sql/20_core/208_v_grid_views.sql
CREATE OR REPLACE VIEW SR_DB.CORE.V_SHARE_GRID AS
SELECT bp.PERIOD_CODE, bp.AS_OF_WEEK, bp.MARKET_ID, bp.CATEGORY, bp.MANUFACTURER, bp.BRAND,
       bp.VALUE_SALES, cp.CAT_VALUE_SALES, bp.TDP_SUM, cp.CAT_TDP_SUM,
       bp.VALUE_SALES  / NULLIF(cp.CAT_VALUE_SALES, 0)  AS VALUE_SHARE,
       bp.VOLUME_SALES / NULLIF(cp.CAT_VOLUME_SALES, 0) AS VOLUME_SHARE,
       bp.TDP_SUM      / NULLIF(cp.CAT_TDP_SUM, 0)      AS DIST_SHARE,
       (bp.VALUE_SALES / NULLIF(bp.UNIT_SALES, 0))
         / NULLIF(cp.CAT_VALUE_SALES / NULLIF(cp.CAT_UNIT_SALES, 0), 0) AS PRICE_INDEX
FROM SR_DB.CORE.DT_BRAND_PERIOD bp
JOIN SR_DB.CORE.DT_CAT_PERIOD cp
  ON cp.PERIOD_CODE = bp.PERIOD_CODE AND cp.MARKET_ID = bp.MARKET_ID AND cp.CATEGORY = bp.CATEGORY;
```

Shares within one market, category and period sum to 1 across all brands, private label included; test T-CORE-01 asserts it.

## L5 Result and ops tables

Every run writes rows keyed by `RUN_ID`, so any brief can be traced back to the exact numbers behind it. `SHIFT_ID` is `MD5(RUN_ID || '|' || CMP_CODE || '|' || MARKET_ID || '|' || CATEGORY || '|' || BRAND)`; `SCOPE_KEY` is `CATEGORY || '|' || PARENT_MARKET || '|' || FOCUS_MANUFACTURER`.

```sql
-- sql/40_app/401_result_tables.sql
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

-- sql/00_setup/003_ops_tables.sql
CREATE TABLE IF NOT EXISTS SR_DB.OPS.RUN_LOG (
  RUN_ID       VARCHAR(36)   NOT NULL PRIMARY KEY,
  TRIGGER_TYPE VARCHAR(8)    NOT NULL,   -- STREAM | REPLAY | MANUAL
  AS_OF_WEEK   DATE,
  SCOPE_KEY    VARCHAR,
  STATUS       VARCHAR(10)   NOT NULL,   -- RUNNING | SUCCEEDED | FAILED | SKIPPED
  BRIDGE_MODE  VARCHAR(1),
  N_CANDIDATES NUMBER(9,0),
  N_RANKED     NUMBER(9,0),
  BRIEF_ID     VARCHAR(36),
  CREDITS_EST  NUMBER(10,4),
  STARTED_AT   TIMESTAMP_LTZ NOT NULL,
  ENDED_AT     TIMESTAMP_LTZ,
  ERROR_MSG    VARCHAR
);

CREATE TABLE IF NOT EXISTS SR_DB.OPS.STEP_LOG (
  RUN_ID       VARCHAR(36)   NOT NULL,
  STEP_NO      NUMBER(2,0)   NOT NULL,
  STEP         VARCHAR(32)   NOT NULL,
  STATUS       VARCHAR(8)    NOT NULL,   -- OK | WARN | FAILED | SKIPPED
  STARTED_AT   TIMESTAMP_LTZ NOT NULL,
  ENDED_AT     TIMESTAMP_LTZ,
  ROWS_WRITTEN NUMBER(12,0),
  MESSAGE      VARCHAR
);

CREATE TABLE IF NOT EXISTS SR_DB.OPS.FACT_SNAPSHOT (
  RUN_ID        VARCHAR(36)   NOT NULL,
  WEEK_END_DATE DATE          NOT NULL,
  MARKET_ID     VARCHAR       NOT NULL,
  ROW_COUNT     NUMBER(12,0)  NOT NULL,
  VALUE_SUM     NUMBER(20,2)  NOT NULL,
  ROW_HASH      NUMBER(20,0)  NOT NULL,   -- HASH_AGG over item rows
  CAPTURED_AT   TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS SR_DB.OPS.NOTIFY_LOG (
  BRIEF_ID VARCHAR(36) NOT NULL, CHANNEL VARCHAR(8) NOT NULL, STATUS VARCHAR(8) NOT NULL,
  SENT_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(), MESSAGE VARCHAR
);

CREATE TABLE IF NOT EXISTS SR_DB.OPS.EVAL_RESULT (
  EVAL_RUN_ID VARCHAR(36) NOT NULL, QUESTION_ID VARCHAR(8) NOT NULL, QUESTION VARCHAR NOT NULL,
  EXPECTED VARIANT, ACTUAL VARIANT, EXPECTED_TOOL VARCHAR(32), ACTUAL_TOOLS VARIANT,
  PASSED BOOLEAN NOT NULL, NOTE VARCHAR, EVALUATED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS SR_DB.OPS.RECON_RESULT (
  CHECK_ID VARCHAR(8) NOT NULL, DESCRIPTION VARCHAR NOT NULL, REFERENCE_VALUE FLOAT,
  SR_VALUE FLOAT, ABS_DIFF FLOAT, PASSED BOOLEAN, CHECKED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS SR_DB.OPS.COCO_LOG (
  LOGGED_AT TIMESTAMP_LTZ NOT NULL, TICKET VARCHAR(8), SURFACE VARCHAR(16), FILES VARIANT,
  LINES_ADDED NUMBER(9,0), TESTS VARIANT, HUMAN_EDITS BOOLEAN, NOTE VARCHAR
);

CREATE TABLE IF NOT EXISTS SR_DB.OPS.STREAM_CONSUMED (
  CONSUMED_AT TIMESTAMP_LTZ NOT NULL, ROWS_SEEN NUMBER(12,0) NOT NULL
);
```

## L6 Intelligence procedures

Each step is one SQL procedure that takes the run ID, deletes its own rows for that run, writes set-based results and returns the row count, so any step can be rerun alone. All procedures are `LANGUAGE SQL EXECUTE AS CALLER`, because owner's-rights procedures cannot run `ALTER SESSION` for the query tag; the tasks run them as `SR_APP`.

| Procedure | Signature | Writes | Ticket |
| --- | --- | --- | --- |
| Snapshot | `APP.SP_SNAPSHOT(P_RUN_ID VARCHAR) RETURNS NUMBER` | `OPS.FACT_SNAPSHOT` | SR-024 |
| Detector | `APP.SP_DETECT_SHIFTS(P_RUN_ID VARCHAR) RETURNS NUMBER` | `APP.SHIFT_CANDIDATE` | SR-020 |
| Share anomaly (ML) | `APP.SP_ML_SHARE_ANOMALY(P_RUN_ID VARCHAR) RETURNS NUMBER` | `SHIFT_CANDIDATE.ANOMALY_*` | SR-021 |
| Bridge | `APP.SP_BRIDGE(P_RUN_ID VARCHAR) RETURNS NUMBER` | `APP.SHARE_BRIDGE` | SR-022 |
| Artefact gate | `APP.SP_ARTEFACT(P_RUN_ID VARCHAR) RETURNS NUMBER` | `APP.ARTEFACT_CHECK` | SR-024 |
| Rank | `APP.SP_RANK(P_RUN_ID VARCHAR) RETURNS NUMBER` | `APP.SHIFT_RANKED` | SR-026 |
| Where | `APP.SP_WHERE(P_RUN_ID VARCHAR) RETURNS NUMBER` | `APP.SHIFT_WHERE` | SR-023 |
| Flow | `APP.SP_FLOW(P_RUN_ID VARCHAR) RETURNS NUMBER` | `APP.SHARE_FLOW` | SR-025 |
| Early warning | `APP.SP_EARLY_WARNING(P_RUN_ID VARCHAR) RETURNS NUMBER` | `APP.EARLY_WARNING` | SR-027 |
| What-if | `APP.SP_WHAT_IF(P_SHIFT_ID VARCHAR, P_LEVER VARCHAR, P_TARGET VARCHAR) RETURNS VARIANT` | — | SR-029 |

**Procedure template** (every step follows it):

```sql
CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_<STEP>(P_RUN_ID VARCHAR)
RETURNS NUMBER
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  n NUMBER DEFAULT 0;
BEGIN
  EXECUTE IMMEDIATE 'ALTER SESSION SET QUERY_TAG = ''SR|run=' || P_RUN_ID || '|step=<STEP>''';
  DELETE FROM SR_DB.APP.<TARGET> WHERE RUN_ID = :P_RUN_ID;
  INSERT INTO SR_DB.APP.<TARGET> (...) SELECT ...;   -- set-based body below
  n := SQLROWCOUNT;
  RETURN n;
END;
$$;
```

The scope markets used below are the parent market and its children: `MARKET_ID IN (SELECT MARKET_ID FROM SR_DB.SRC.V_SRC_MARKET WHERE MARKET_ID = :PARENT OR PARENT_MARKET_ID = :PARENT)`, with `:PARENT = SR_DB.OPS.CFG('SCOPE_PARENT_MARKET')::VARCHAR`.

### Detector (SR-020)

Noise for each comparison is the standard deviation of the same difference measured on rolling shares in the history before the judged weeks; z = change ÷ noise. L52W comparisons get no z and are gated on points and value only.

```sql
INSERT INTO SR_DB.APP.SHIFT_CANDIDATE
  (RUN_ID, SHIFT_ID, CMP_CODE, MARKET_ID, CATEGORY, MANUFACTURER, BRAND, SH1, SH0, D_SHARE, VALUE_AT_STAKE, Z_SCORE, PASSED_GATES, GATE_NOTES)
WITH roll AS (
  SELECT MARKET_ID, CATEGORY, BRAND, WEEK_END_DATE,
    SUM(VALUE_SALES)     OVER (PARTITION BY MARKET_ID, CATEGORY, BRAND ORDER BY WEEK_END_DATE ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
    / NULLIF(SUM(CAT_VALUE_SALES) OVER (PARTITION BY MARKET_ID, CATEGORY, BRAND ORDER BY WEEK_END_DATE ROWS BETWEEN 3 PRECEDING AND CURRENT ROW), 0)  AS SH4,
    SUM(VALUE_SALES)     OVER (PARTITION BY MARKET_ID, CATEGORY, BRAND ORDER BY WEEK_END_DATE ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
    / NULLIF(SUM(CAT_VALUE_SALES) OVER (PARTITION BY MARKET_ID, CATEGORY, BRAND ORDER BY WEEK_END_DATE ROWS BETWEEN 11 PRECEDING AND CURRENT ROW), 0) AS SH12
  FROM SR_DB.CORE.DT_SHARE_WEEK
), diffs AS (
  SELECT MARKET_ID, CATEGORY, BRAND, WEEK_END_DATE,
         SH4  - LAG(SH4, 52)  OVER (PARTITION BY MARKET_ID, CATEGORY, BRAND ORDER BY WEEK_END_DATE) AS D4_YA,
         SH4  - LAG(SH4, 4)   OVER (PARTITION BY MARKET_ID, CATEGORY, BRAND ORDER BY WEEK_END_DATE) AS D4_PP,
         SH12 - LAG(SH12, 52) OVER (PARTITION BY MARKET_ID, CATEGORY, BRAND ORDER BY WEEK_END_DATE) AS D12_YA
  FROM roll
), noise AS (
  SELECT d.MARKET_ID, d.CATEGORY, d.BRAND,
         STDDEV_SAMP(d.D4_YA) AS SD_L4W_VS_YA, STDDEV_SAMP(d.D4_PP) AS SD_L4W_VS_PP, STDDEV_SAMP(d.D12_YA) AS SD_L12W_VS_YA
  FROM diffs d
  WHERE d.WEEK_END_DATE <= DATEADD(week, -4, (SELECT MAX(WEEK_END_DATE) FROM SR_DB.CORE.DT_SHARE_WEEK))
  GROUP BY d.MARKET_ID, d.CATEGORY, d.BRAND
), cfg AS (
  SELECT SR_DB.OPS.CFG('MIN_SHARE_PTS')::FLOAT AS MIN_PTS, SR_DB.OPS.CFG('MIN_VALUE_AT_STAKE')::FLOAT AS MIN_VAL,
         SR_DB.OPS.CFG('MIN_Z')::FLOAT AS MIN_Z, SR_DB.OPS.CFG('COMPARES') AS COMPARES
), z AS (
  SELECT c.*, c.D_SHARE / NULLIF(CASE c.CMP_CODE WHEN 'L4W_VS_YA'  THEN n.SD_L4W_VS_YA
                                                 WHEN 'L4W_VS_PP'  THEN n.SD_L4W_VS_PP
                                                 WHEN 'L12W_VS_YA' THEN n.SD_L12W_VS_YA END, 0) AS Z_SCORE
  FROM SR_DB.CORE.DT_SHARE_COMPARE c
  LEFT JOIN noise n ON n.MARKET_ID = c.MARKET_ID AND n.CATEGORY = c.CATEGORY AND n.BRAND = c.BRAND
  WHERE c.D_SHARE IS NOT NULL AND c.MARKET_ID IN (<scope markets>)
)
SELECT :P_RUN_ID,
       MD5(:P_RUN_ID || '|' || z.CMP_CODE || '|' || z.MARKET_ID || '|' || z.CATEGORY || '|' || z.BRAND),
       z.CMP_CODE, z.MARKET_ID, z.CATEGORY, z.MANUFACTURER, z.BRAND, z.SH1, z.SH0, z.D_SHARE, z.VALUE_AT_STAKE, z.Z_SCORE,
       ABS(z.D_SHARE) * 100 >= cfg.MIN_PTS AND ABS(z.VALUE_AT_STAKE) >= cfg.MIN_VAL
         AND (z.Z_SCORE IS NULL OR ABS(z.Z_SCORE) >= cfg.MIN_Z)                              AS PASSED_GATES,
       OBJECT_CONSTRUCT('pts', ABS(z.D_SHARE) * 100, 'value', ABS(z.VALUE_AT_STAKE), 'z', z.Z_SCORE)  AS GATE_NOTES
FROM z CROSS JOIN cfg
WHERE ARRAY_CONTAINS(z.CMP_CODE::VARIANT, cfg.COMPARES);
```

### Bridge (SR-022)

Share is a product of indices relative to the category, so its log-change splits exactly; each term is weighted by the logarithmic mean of the two shares (LMDI), which makes the terms add up to the change in points with no residual.

```latex
s = \frac{S_b}{S_c} = \underbrace{\frac{TDP_b}{TDP_c}}_{\text{distribution share}} \times \underbrace{\frac{BU_b/TDP_b}{BU_c/TDP_c}}_{\text{base velocity index}} \times \underbrace{\frac{B_b/BU_b}{B_c/BU_c}}_{\text{base price index}} \times \underbrace{\frac{S_b/B_b}{S_c/B_c}}_{\text{promo index}}
```

```latex
\Delta s_i = L(s_1, s_0) \cdot \ln\frac{F_{i,1}}{F_{i,0}}, \qquad L(a,b) = \frac{a-b}{\ln a - \ln b}, \quad L(a,a) = a, \qquad \sum_i \Delta s_i = s_1 - s_0
```

| Mode | Needs (both periods, brand and category, all > 0) | Terms |
| --- | --- | --- |
| A | TDP, base units, base value, value | distribution, base unit velocity, base price, promo |
| B | TDP, units, value | distribution, unit velocity, average price |
| C | TDP, value | distribution, value velocity |
| D | value only | none: share change only; where and flow still run |

The row mode is the best mode the row's data supports, capped by `OPS.CAPABILITY.MAX_BRIDGE_MODE`. Status: `NEW` (S0 = 0), `EXIT` (S1 = 0), `NO_DATA` (a category total missing), else `OK`; only `OK` rows get terms.

```sql
INSERT INTO SR_DB.APP.SHARE_BRIDGE
  (RUN_ID, SHIFT_ID, CMP_CODE, MARKET_ID, CATEGORY, BRAND, MODE, STATUS, SH1, SH0, D_SHARE, LMDI_WEIGHT,
   DIST_PTS, VELOCITY_PTS, PRICE_PTS, PROMO_PTS, RESIDUAL_PTS, DS1, DS0, PI1, PI0, PRI1, PRI0, NOTE)
WITH cap AS (
  SELECT MAX_BRIDGE_MODE AS M FROM SR_DB.OPS.CAPABILITY ORDER BY CHECKED_AT DESC LIMIT 1
), x AS (
  SELECT sc.SHIFT_ID, c.*,
    CASE WHEN c.CS1 IS NULL OR c.CS0 IS NULL THEN 'NO_DATA'
         WHEN c.S0 = 0 AND c.S1 > 0 THEN 'NEW'
         WHEN c.S1 = 0 AND c.S0 > 0 THEN 'EXIT' ELSE 'OK' END AS STATUS,
    CASE WHEN cap.M = 'A' AND LEAST(c.TDP1, c.TDP0, c.CTDP1, c.CTDP0, c.BU1, c.BU0, c.CBU1, c.CBU0, c.B1, c.B0, c.CB1, c.CB0) > 0 THEN 'A'
         WHEN cap.M IN ('A', 'B') AND LEAST(c.TDP1, c.TDP0, c.CTDP1, c.CTDP0, c.U1, c.U0, c.CU1, c.CU0) > 0 THEN 'B'
         WHEN cap.M IN ('A', 'B', 'C') AND LEAST(c.TDP1, c.TDP0, c.CTDP1, c.CTDP0) > 0 THEN 'C'
         ELSE 'D' END AS MODE
  FROM SR_DB.APP.SHIFT_CANDIDATE sc
  JOIN SR_DB.CORE.DT_SHARE_COMPARE c
    ON c.CMP_CODE = sc.CMP_CODE AND c.MARKET_ID = sc.MARKET_ID AND c.CATEGORY = sc.CATEGORY AND c.BRAND = sc.BRAND
  CROSS JOIN cap
  WHERE sc.RUN_ID = :P_RUN_ID AND sc.PASSED_GATES
), f AS (
  SELECT x.*,
    IFF(MODE <> 'D', (TDP1 / CTDP1), NULL) AS DS1,
    IFF(MODE <> 'D', (TDP0 / CTDP0), NULL) AS DS0,
    CASE MODE WHEN 'A' THEN (BU1 / TDP1) / (CBU1 / CTDP1) WHEN 'B' THEN (U1 / TDP1) / (CU1 / CTDP1) WHEN 'C' THEN (S1 / TDP1) / (CS1 / CTDP1) END AS V1,
    CASE MODE WHEN 'A' THEN (BU0 / TDP0) / (CBU0 / CTDP0) WHEN 'B' THEN (U0 / TDP0) / (CU0 / CTDP0) WHEN 'C' THEN (S0 / TDP0) / (CS0 / CTDP0) END AS V0,
    CASE MODE WHEN 'A' THEN (B1 / BU1) / (CB1 / CBU1) WHEN 'B' THEN (S1 / U1) / (CS1 / CU1) END AS PI1,
    CASE MODE WHEN 'A' THEN (B0 / BU0) / (CB0 / CBU0) WHEN 'B' THEN (S0 / U0) / (CS0 / CU0) END AS PI0,
    IFF(MODE = 'A', (S1 / B1) / (CS1 / CB1), NULL) AS PRI1,
    IFF(MODE = 'A', (S0 / B0) / (CS0 / CB0), NULL) AS PRI0,
    IFF(STATUS = 'OK', IFF(ABS(SH1 - SH0) < 1e-12, SH1, (SH1 - SH0) / (LN(SH1) - LN(SH0))), NULL) AS L
  FROM x
)
SELECT :P_RUN_ID, SHIFT_ID, CMP_CODE, MARKET_ID, CATEGORY, BRAND, MODE, STATUS, SH1, SH0, D_SHARE, L,
       100 * L * LN(DS1 / DS0)   AS DIST_PTS,
       100 * L * LN(V1 / V0)     AS VELOCITY_PTS,
       100 * L * LN(PI1 / PI0)   AS PRICE_PTS,
       100 * L * LN(PRI1 / PRI0) AS PROMO_PTS,
       100 * D_SHARE - COALESCE(DIST_PTS, 0) - COALESCE(VELOCITY_PTS, 0) - COALESCE(PRICE_PTS, 0) - COALESCE(PROMO_PTS, 0) AS RESIDUAL_PTS,
       DS1, DS0, PI1, PI0, PRI1, PRI0,
       IFF(MODE = 'D', 'No distribution data: share change only', NULL)
FROM f;
```

`LN` of NULL returns NULL, so rows outside a mode simply carry NULL terms. `python/sr_lib/bridge.py` mirrors this logic for unit tests:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class PeriodInputs:
    s: float; cs: float
    tdp: float | None; ctdp: float | None
    u: float | None; cu: float | None
    b: float | None; cb: float | None
    bu: float | None; cbu: float | None

@dataclass(frozen=True)
class BridgeResult:
    mode: str; status: str; d_share_pts: float
    dist_pts: float | None; velocity_pts: float | None
    price_pts: float | None; promo_pts: float | None
    residual_pts: float

def log_mean(a: float, b: float) -> float: ...
def pick_mode(cur: PeriodInputs, base: PeriodInputs, cap_mode: str) -> str: ...
def bridge(cur: PeriodInputs, base: PeriodInputs, cap_mode: str = "A") -> BridgeResult: ...
```

### Artefact gate (SR-024)

| Rule | Level | Fires when | Severity |
| --- | --- | --- | --- |
| `R1_COVERAGE` | market | Store count (universe view) changes by ≥ `ART_STORE_CHG` between periods. Proxy without it: \|Δln category TDP per week\| ≥ `ART_CAT_TDP_JUMP` while \|Δln category value per TDP point\| ≤ `ART_CAT_SPPD_FLAT` | HIGH (universe) or MEDIUM (proxy) |
| `R2_FEED` | parent and child market | A child retailer market has category sales in one period and none in the other | HIGH |
| `R3_RESTATE` | market | A week inside either period has a different `ROW_HASH` than the previous successful run's snapshot; HIGH if category value moved ≥ 1% | HIGH or MEDIUM |
| `R4_RECODE` | brand | Exiting items' base-period sales and entering items' current sales are within `ART_RECODE_TOL` of each other, each ≥ 20% of the brand's base sales | MEDIUM |
| `R5_SPIKE` | market | A current-period week's category sales sit more than `ART_SPIKE_K` standard deviations from the trailing 13-week mean | MEDIUM |
| `R6_GAP` | market | Category weeks in either period fall short of the expected count | HIGH |

Label per shift: any HIGH rule on its market (or its brand) gives `POSSIBLE_DATA_EFFECT`; otherwise any MEDIUM gives `MIXED`; otherwise `MARKET_MOVE`. Evidence is an object such as `{"child_market": "<name>", "sales_cur": 0, "sales_base": 1834220.5, "source": "CORE.DT_CAT_PERIOD"}`.

```sql
-- R2_FEED: a child retailer present in one period and absent in the other
INSERT INTO SR_DB.APP.ARTEFACT_CHECK (RUN_ID, CMP_CODE, MARKET_ID, CATEGORY, BRAND, RULE_ID, SEVERITY, EVIDENCE)
SELECT :P_RUN_ID, cmp.CMP_CODE, m.PARENT_MARKET_ID, c1.CATEGORY, NULL, 'R2_FEED', 'HIGH',
       OBJECT_CONSTRUCT('child_market', m.MARKET_NAME, 'sales_cur', COALESCE(c1.CAT_VALUE_SALES, 0),
                        'sales_base', COALESCE(c0.CAT_VALUE_SALES, 0), 'source', 'CORE.DT_CAT_PERIOD')
FROM SR_DB.SRC.V_SRC_MARKET m
CROSS JOIN (SELECT column1 AS CMP_CODE, column2 AS CUR_P, column3 AS BASE_P
            FROM VALUES ('L4W_VS_YA','L4W','L4W_YA'), ('L4W_VS_PP','L4W','P4W'), ('L12W_VS_YA','L12W','L12W_YA')) cmp
LEFT JOIN SR_DB.CORE.DT_CAT_PERIOD c1 ON c1.MARKET_ID = m.MARKET_ID AND c1.PERIOD_CODE = cmp.CUR_P
LEFT JOIN SR_DB.CORE.DT_CAT_PERIOD c0 ON c0.MARKET_ID = m.MARKET_ID AND c0.PERIOD_CODE = cmp.BASE_P
WHERE m.PARENT_MARKET_ID = :PARENT
  AND (COALESCE(c1.CAT_VALUE_SALES, 0) = 0) <> (COALESCE(c0.CAT_VALUE_SALES, 0) = 0);

-- R6_GAP
INSERT INTO SR_DB.APP.ARTEFACT_CHECK (RUN_ID, CMP_CODE, MARKET_ID, CATEGORY, BRAND, RULE_ID, SEVERITY, EVIDENCE)
SELECT DISTINCT :P_RUN_ID, c.CMP_CODE, c.MARKET_ID, c.CATEGORY, NULL, 'R6_GAP', 'HIGH',
       OBJECT_CONSTRUCT('weeks_cur', c.CAT_WEEKS1, 'weeks_base', c.CAT_WEEKS0, 'expected', c.EXP_WEEKS, 'source', 'CORE.DT_SHARE_COMPARE')
FROM SR_DB.CORE.DT_SHARE_COMPARE c
WHERE c.MARKET_ID IN (<scope markets>) AND (c.CAT_WEEKS1 < c.EXP_WEEKS OR c.CAT_WEEKS0 < c.EXP_WEEKS);

-- SP_SNAPSHOT body (feeds R3_RESTATE)
INSERT INTO SR_DB.OPS.FACT_SNAPSHOT (RUN_ID, WEEK_END_DATE, MARKET_ID, ROW_COUNT, VALUE_SUM, ROW_HASH)
SELECT :P_RUN_ID, f.WEEK_END_DATE, f.MARKET_ID, COUNT(*), SUM(f.VALUE_SALES),
       HASH_AGG(f.PRODUCT_ID, f.VALUE_SALES, f.UNIT_SALES, f.ACV_DIST_PCT)
FROM SR_DB.SRC.V_SRC_FACT_WEEKLY f
WHERE f.WEEK_END_DATE IN (SELECT WEEK_END_DATE FROM SR_DB.CORE.DT_PERIOD_WEEK)
  AND f.MARKET_ID IN (<scope markets>)
GROUP BY f.WEEK_END_DATE, f.MARKET_ID;
```

R1, R3, R4 and R5 follow the same pattern: one `INSERT … SELECT` per rule, evidence as an object with a `source` key. For the demo, pick replay weeks around a real feed or coverage change that the Input Validation team recorded, so the catch happens on real data.

### Rank and suppress (SR-026)

```text
CONFIDENCE  = LEAST(1, ABS(Z_SCORE) / 3); 0.5 when Z_SCORE is NULL; at least 0.8 when ANOMALY_CONFIRMED
ART_FACTOR  = 1.0 MARKET_MOVE | 0.6 MIXED | 0.3 POSSIBLE_DATA_EFFECT
SCORE       = ABS(VALUE_AT_STAKE) x CONFIDENCE x ART_FACTOR x (1.5 if MANUFACTURER = FOCUS_MANUFACTURER else 1.0)
SUPPRESSED  = same MARKET_ID, BRAND, CMP_CODE and sign SELECTED in any of the last SUPPRESS_RUNS successful runs,
              and ABS(D_SHARE) < previous ABS(D_SHARE) x (1 + SUPPRESS_GROWTH)
SELECTED    = NOT SUPPRESSED AND ARTEFACT_LABEL <> 'POSSIBLE_DATA_EFFECT' AND rank among those <= TOP_N
HELD BACK   = ARTEFACT_LABEL = 'POSSIBLE_DATA_EFFECT', top 3 by SCORE (listed separately in the brief)
```

### Where it happened (SR-023, exact part)

For a shift in the parent market, each child retailer r (plus a "rest of market" remainder when children don't cover the parent) contributes a performance term and a mix term. With weight w = category sales of r ÷ parent category sales and s = brand share within r, the two-factor split is exact:

```latex
\Delta s_{parent} = \sum_r \Big[ \underbrace{\tfrac{w_{r,1}+w_{r,0}}{2}\,(s_{r,1}-s_{r,0})}_{\text{performance in } r} + \underbrace{\tfrac{s_{r,1}+s_{r,0}}{2}\,(w_{r,1}-w_{r,0})}_{\text{retailer mix}} \Big]
```

Rows go to `APP.SHIFT_WHERE` with `METHOD = 'EXACT_RETAILER'`, ranked by `ABS(TOTAL_PTS)`. TOP\_INSIGHTS rows (L7) are added with `METHOD = 'TOP_INSIGHTS'`.

### Who took it (SR-025)

Within one market, category and comparison, share changes sum to zero, so the points a losing brand gave up are allocated to gainers in proportion to their gains. It is an accounting allocation, labelled as such, not shopper switching.

```sql
INSERT INTO SR_DB.APP.SHARE_FLOW (RUN_ID, CMP_CODE, MARKET_ID, CATEGORY, FROM_BRAND, TO_BRAND, FLOW_PTS)
WITH d AS (
  SELECT c.CMP_CODE, c.MARKET_ID, c.CATEGORY, c.BRAND, c.D_SHARE
  FROM SR_DB.CORE.DT_SHARE_COMPARE c
  WHERE c.D_SHARE IS NOT NULL
    AND (c.CMP_CODE, c.MARKET_ID) IN (SELECT CMP_CODE, MARKET_ID FROM SR_DB.APP.SHIFT_RANKED WHERE RUN_ID = :P_RUN_ID AND SELECTED)
), g AS (
  SELECT CMP_CODE, MARKET_ID, CATEGORY, SUM(IFF(D_SHARE > 0, D_SHARE, 0)) AS GAIN_TOTAL
  FROM d GROUP BY CMP_CODE, MARKET_ID, CATEGORY
)
SELECT :P_RUN_ID, l.CMP_CODE, l.MARKET_ID, l.CATEGORY, l.BRAND, w.BRAND,
       100 * (-l.D_SHARE) * w.D_SHARE / NULLIF(g.GAIN_TOTAL, 0) AS FLOW_PTS
FROM d l
JOIN d w ON w.CMP_CODE = l.CMP_CODE AND w.MARKET_ID = l.MARKET_ID AND w.CATEGORY = l.CATEGORY AND w.D_SHARE > 0
JOIN g   ON g.CMP_CODE = l.CMP_CODE AND g.MARKET_ID = l.MARKET_ID AND g.CATEGORY = l.CATEGORY
WHERE l.D_SHARE < 0;
```

### Early warning (SR-027)

Reported L4W share averages four weeks, so a distribution loss in the latest week shows only a quarter of its effect. If the latest week's distribution share persists, next period's L4W share moves mechanically by:

```latex
\Delta s_{next} \approx s_{L4W} \times \left(\frac{DS_{latest}}{DS_{L4W}} - 1\right) \quad \text{(velocity, price and promo held constant)}
```

Rows with `LEVER_CHG <= EW_DIST_DROP` become `DIST_DROP`; rows with a price index change `>= EW_PRICE_RISE` become `PRICE_RISE` (no projection, because elasticity is unknown). Scope: focus manufacturer's brands plus the category's top ten brands by L4W sales.

### What-if (SR-029)

`P_LEVER` is `DISTRIBUTION` or `PROMO` (mode A only); `P_TARGET` is `BASE` (restore the base-period level) or a signed percentage such as `+10%`. The result is mechanical: new share = SH1 × ratio, with ratio = DS0 ÷ DS1 (or PRI0 ÷ PRI1, or 1 + pct). It returns `{"brand", "market", "cmp_code", "lever", "target", "share_now_pts", "share_if_pts", "delta_pts", "assumption": "Other levers held constant; mechanical, not a forecast"}`.

## L7 ML objects

Two Snowflake ML classes do real work: [ANOMALY\_DETECTION](https://docs.snowflake.com/en/user-guide/snowflake-cortex/ml-functions/anomaly-detection) says whether the latest weeks' share is outside its seasonal expectation, and [TOP\_INSIGHTS](https://docs.snowflake.com/en/sql-reference/classes/top-insights/methods/get_drivers) finds which segments drove a ranked shift. Both run only on gated or ranked shifts, which keeps cost and time small.

| Object | Class | Input | Output used | Ticket |
| --- | --- | --- | --- | --- |
| `ML.AD_SHARE_WEEKLY` | `SNOWFLAKE.ML.ANOMALY_DETECTION` | Weekly `VALUE_SHARE` per (market, brand), trained on weeks up to as-of minus 4 | `IS_ANOMALY` in the last 4 weeks → `ANOMALY_WEEKS`, `ANOMALY_CONFIRMED` (≥ 2 weeks) | SR-021 |
| `ML.TI_SHARE` | `SNOWFLAKE.ML.TOP_INSIGHTS` | Brand item-week sales in the two periods, dimensions retailer, region, segment, pack size; label TRUE = current period | `CONTRIBUTOR`, `CONTRIBUTION`, `RELATIVE_CONTRIBUTION`, `GROWTH_RATE` (top 5) | SR-023 |
| `ML.AD_LEVERS` (stretch) | `SNOWFLAKE.ML.ANOMALY_DETECTION` | Weekly `DIST_SHARE` and `PRICE_INDEX` per (market, brand) | Latest week below the lower bound (distribution) or above the upper bound (price) → `EARLY_WARNING.ML_CONFIRMED` | SR-028 |

Documented limits that shape this design: anomaly detection needs at least 12 rows per series, and the model is immutable once trained, so it is recreated each run. TOP\_INSIGHTS treats every non-label, non-metric column as a dimension, needs a FLOAT metric, and keeps only the 25 most influential values of a high-cardinality dimension.

```sql
-- sql/30_ml/301_sp_ml_share_anomaly.sql
CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_ML_SHARE_ANOMALY(P_RUN_ID VARCHAR)
RETURNS NUMBER
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  n NUMBER DEFAULT 0;
BEGIN
  EXECUTE IMMEDIATE 'ALTER SESSION SET QUERY_TAG = ''SR|run=' || P_RUN_ID || '|step=ML_ANOMALY''';

  CREATE OR REPLACE TEMPORARY TABLE SR_DB.ML.TMP_AD_SERIES AS
  SELECT ARRAY_CONSTRUCT(s.MARKET_ID, s.BRAND)::VARIANT AS SERIES,
         s.WEEK_END_DATE::TIMESTAMP_NTZ               AS TS,
         s.VALUE_SHARE::FLOAT                         AS Y
  FROM SR_DB.CORE.DT_SHARE_WEEK s
  WHERE (s.MARKET_ID, s.BRAND) IN (SELECT MARKET_ID, BRAND FROM SR_DB.APP.SHIFT_CANDIDATE
                                   WHERE RUN_ID = :P_RUN_ID AND PASSED_GATES);

  CREATE OR REPLACE TEMPORARY TABLE SR_DB.ML.TMP_AD_TRAIN AS
  SELECT * FROM SR_DB.ML.TMP_AD_SERIES
  WHERE TS <= DATEADD(week, -4, (SELECT MAX(TS) FROM SR_DB.ML.TMP_AD_SERIES));

  CREATE OR REPLACE TEMPORARY TABLE SR_DB.ML.TMP_AD_TEST AS
  SELECT * FROM SR_DB.ML.TMP_AD_SERIES
  WHERE TS > DATEADD(week, -4, (SELECT MAX(TS) FROM SR_DB.ML.TMP_AD_SERIES));

  CREATE OR REPLACE SNOWFLAKE.ML.ANOMALY_DETECTION SR_DB.ML.AD_SHARE_WEEKLY(
    INPUT_DATA        => TABLE(SR_DB.ML.TMP_AD_TRAIN),
    SERIES_COLNAME    => 'SERIES',
    TIMESTAMP_COLNAME => 'TS',
    TARGET_COLNAME    => 'Y',
    LABEL_COLNAME     => '');

  CALL SR_DB.ML.AD_SHARE_WEEKLY!DETECT_ANOMALIES(
    INPUT_DATA        => TABLE(SR_DB.ML.TMP_AD_TEST),
    SERIES_COLNAME    => 'SERIES',
    TIMESTAMP_COLNAME => 'TS',
    TARGET_COLNAME    => 'Y',
    CONFIG_OBJECT     => {'prediction_interval': 0.95, 'on_error': 'skip'});

  CREATE OR REPLACE TEMPORARY TABLE SR_DB.ML.TMP_AD_OUT AS
  SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));

  UPDATE SR_DB.APP.SHIFT_CANDIDATE sc
     SET ANOMALY_WEEKS = a.N_ANOM, ANOMALY_CONFIRMED = (a.N_ANOM >= 2)
    FROM (SELECT SERIES[0]::VARCHAR AS MARKET_ID, SERIES[1]::VARCHAR AS BRAND, COUNT_IF(IS_ANOMALY) AS N_ANOM
          FROM SR_DB.ML.TMP_AD_OUT GROUP BY 1, 2) a
   WHERE sc.RUN_ID = :P_RUN_ID AND sc.MARKET_ID = a.MARKET_ID AND sc.BRAND = a.BRAND
     AND sc.CMP_CODE LIKE 'L4W%';
  n := SQLROWCOUNT;
  RETURN n;
END;
$$;

-- sql/30_ml/302_sp_where_insights.sql
CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_WHERE_INSIGHTS(P_RUN_ID VARCHAR)
RETURNS NUMBER
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  n  NUMBER DEFAULT 0;
  rs RESULTSET DEFAULT (
    SELECT r.SHIFT_ID, r.MARKET_ID, r.BRAND, c.CUR_PERIOD, c.BASE_PERIOD
    FROM SR_DB.APP.SHIFT_RANKED r
    JOIN SR_DB.CORE.DT_SHARE_COMPARE c
      ON c.CMP_CODE = r.CMP_CODE AND c.MARKET_ID = r.MARKET_ID AND c.CATEGORY = r.CATEGORY AND c.BRAND = r.BRAND
    WHERE r.RUN_ID = :P_RUN_ID AND r.SELECTED);
  cur CURSOR FOR rs;
BEGIN
  EXECUTE IMMEDIATE 'ALTER SESSION SET QUERY_TAG = ''SR|run=' || P_RUN_ID || '|step=TOP_INSIGHTS''';
  CREATE SNOWFLAKE.ML.TOP_INSIGHTS IF NOT EXISTS SR_DB.ML.TI_SHARE();
  DELETE FROM SR_DB.APP.SHIFT_WHERE WHERE RUN_ID = :P_RUN_ID AND METHOD = 'TOP_INSIGHTS';
  FOR rec IN cur DO
    LET sid VARCHAR := rec.SHIFT_ID;
    LET mkt VARCHAR := rec.MARKET_ID;
    LET br  VARCHAR := rec.BRAND;
    LET cp  VARCHAR := rec.CUR_PERIOD;
    LET bp  VARCHAR := rec.BASE_PERIOD;
    CREATE OR REPLACE TEMPORARY TABLE SR_DB.ML.TMP_TI_INPUT AS
    SELECT COALESCE(m.RETAILER, m.MARKET_NAME)::VARCHAR AS RETAILER,
           m.REGION::VARCHAR     AS REGION,
           p.SEGMENT::VARCHAR    AS SEGMENT,
           p.PACK_SIZE::VARCHAR  AS PACK_SIZE,
           (pw.PERIOD_CODE = :cp) AS LABEL,
           f.VALUE_SALES::FLOAT  AS METRIC
    FROM SR_DB.SRC.V_SRC_FACT_WEEKLY f
    JOIN SR_DB.SRC.V_SRC_PRODUCT p   ON p.PRODUCT_ID = f.PRODUCT_ID
    JOIN SR_DB.SRC.V_SRC_MARKET m    ON m.MARKET_ID = f.MARKET_ID
    JOIN SR_DB.CORE.DT_PERIOD_WEEK pw ON pw.WEEK_END_DATE = f.WEEK_END_DATE AND pw.PERIOD_CODE IN (:cp, :bp)
    WHERE p.BRAND = :br
      AND (m.PARENT_MARKET_ID = :mkt
           OR (m.MARKET_ID = :mkt AND NOT EXISTS (SELECT 1 FROM SR_DB.SRC.V_SRC_MARKET x WHERE x.PARENT_MARKET_ID = :mkt)));
    CALL SR_DB.ML.TI_SHARE!GET_DRIVERS(
      INPUT_DATA     => TABLE(SR_DB.ML.TMP_TI_INPUT),
      LABEL_COLNAME  => 'LABEL',
      METRIC_COLNAME => 'METRIC');
    INSERT INTO SR_DB.APP.SHIFT_WHERE
      (RUN_ID, SHIFT_ID, METHOD, RANK_NO, CONTRIBUTOR, METRIC_CONTROL, METRIC_TEST, CONTRIBUTION, RELATIVE_CONTRIBUTION, GROWTH_RATE)
    SELECT :P_RUN_ID, :sid, 'TOP_INSIGHTS',
           ROW_NUMBER() OVER (ORDER BY ABS(CONTRIBUTION) DESC),
           ARRAY_TO_STRING(CONTRIBUTOR, ' and '),
           METRIC_CONTROL, METRIC_TEST, CONTRIBUTION, RELATIVE_CONTRIBUTION, GROWTH_RATE
    FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
    QUALIFY ROW_NUMBER() OVER (ORDER BY ABS(CONTRIBUTION) DESC) <= 5;
    n := n + SQLROWCOUNT;
  END FOR;
  RETURN n;
END;
$$;
```

TOP\_INSIGHTS explains the brand's **sales** change by segment, not its share; the UI labels it "drivers of brand sales change". `ML.AD_LEVERS` copies `SP_ML_SHARE_ANOMALY` with `Y = DIST_SHARE` (and a second model with `Y = PRICE_INDEX`) and flags only the latest week. Forecasting with lagged levers was considered and cut for time.

## L8 Narrative: fact pack, prompt, schema, validator, fallback

The LLM never sees a bare number it could copy wrongly: it gets fact IDs, writes `{{fNN}}` placeholders, and Python fills and checks them. Two failed attempts produce a deterministic template brief, so a brief is always published.

**Fact pack contract** (`APP.FACT_PACK.PACK`, built by `APP.SP_BUILD_FACT_PACK(P_RUN_ID VARCHAR) RETURNS VARCHAR`, which returns the new `BRIEF_ID`):

```json
{
  "brief_id": "7c0e…", "run_id": "a91f…", "as_of_week": "2026-11-07",
  "scope": {"category": "<category>", "parent_market": "<market>", "focus_manufacturer": "<manufacturer>"},
  "facts": {
    "f1": {"v": 0.2341,  "u": "share", "d": 1, "src": "APP.SHIFT_CANDIDATE#SHIFT_ID=…;col=SH1"},
    "f3": {"v": -0.84,   "u": "pts",   "d": 2, "src": "APP.SHARE_BRIDGE#SHIFT_ID=…;col=D_SHARE*100"},
    "f4": {"v": -1834220.5, "u": "money", "d": 1, "src": "APP.SHIFT_RANKED#SHIFT_ID=…;col=VALUE_AT_STAKE"}
  },
  "shifts": [{
    "shift_id": "…", "rank": 1, "brand": "<brand>", "manufacturer": "<manufacturer>", "market": "<market name>",
    "cmp_code": "L4W_VS_YA", "label": "MARKET_MOVE", "direction": "LOSS",
    "share_now": "f1", "share_before": "f2", "delta": "f3", "value_at_stake": "f4",
    "bridge": [{"term": "distribution", "fact": "f5"}, {"term": "velocity", "fact": "f6"}, {"term": "price", "fact": "f7"}, {"term": "promo", "fact": "f8"}],
    "where": [{"contributor": "<retailer>", "fact": "f9"}],
    "flow":  [{"brand": "<gaining brand>", "fact": "f10"}]
  }],
  "held_back": [{"shift_id": "…", "brand": "…", "market": "…", "delta": "f20", "rules": ["R2_FEED"]}],
  "watchlist": [{"brand": "…", "market": "…", "signal": "DIST_DROP", "lever_chg": "f30", "projected": "f31"}]
}
```

Units: `share` is shown as a percentage, `pts` as signed share points, `money` in compact local currency (K, M, B), `index` as a signed percentage change. Every fact carries `src`, which the brief page shows on hover.

**Prompt** (`python/sr_lib/run.py::build_prompt(pack: dict) -> str`):

```text
You write a competitive share brief for an NIQ client-service analyst.
Rules:
1. Use only the facts in the FACT PACK. Refer to any number only by its placeholder, for example {{f12}}. Never write digits.
2. Return one entry per item in "shifts", in the same order, with the same shift_id.
3. title: one line naming the brand, the market and whether it gained or lost share.
4. why: one or two sentences naming the largest bridge terms and the top retailer, using placeholders.
5. so_what: one sentence on what the client should check or do next.
6. next_question: one question the analyst could ask the Share Radar agent next.
7. headline: one sentence on the week for the focus manufacturer.
8. watchlist: one short line per watchlist item, using placeholders.
9. Do not describe held_back items; the system lists them.
10. Plain business English. No hype.
FACT PACK:
<pack JSON>
```

**Structured output schema** (passed as `response_format`; see [AI\_COMPLETE structured outputs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/complete-structured-outputs)):

```json
{
  "type": "json",
  "schema": {
    "type": "object",
    "properties": {
      "headline": {"type": "string"},
      "shifts": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "shift_id": {"type": "string"},
            "title": {"type": "string"},
            "why": {"type": "string"},
            "so_what": {"type": "string"},
            "next_question": {"type": "string"}
          },
          "required": ["shift_id", "title", "why", "so_what", "next_question"]
        }
      },
      "watchlist": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["headline", "shifts", "watchlist"]
  }
}
```

**Validator** (`python/sr_lib/validator.py`):

```python
import re
from dataclasses import dataclass

PLACEHOLDER   = re.compile(r"\{\{(f\d+)\}\}")
DIGIT_TOKEN   = re.compile(r"[\w%.,-]*\d[\w%.,-]*")
PERIOD_TOKENS = {"L4W", "L12W", "L52W", "P4W", "4W", "12W", "52W"}
GAIN_WORDS = {"gain", "gained", "gains", "grew", "grows", "rose", "up", "increased", "won", "added"}
LOSS_WORDS = {"lost", "lose", "loses", "loss", "fell", "down", "declined", "dropped", "slipped", "ceded"}

@dataclass(frozen=True)
class Violation:
    code: str    # V01_SCHEMA | V02_UNKNOWN_FACT | V03_RAW_NUMBER | V04_DIRECTION | V05_SHIFT_SET | V06_EMPTY | V07_LENGTH
    path: str    # e.g. "shifts[1].why"
    detail: str

def allowed_tokens(pack: dict) -> set[str]:
    """Digit-bearing tokens that may appear: period codes plus any token inside brand, market or retailer names."""

def validate_brief(llm: dict, pack: dict) -> list[Violation]:
    """Empty list = pass. Checks, in order: V01 schema and types; V05 shift_ids equal pack order;
    V06 no empty strings; V07 title <= 120, why <= 400, headline <= 200 characters;
    V02 every placeholder exists in pack['facts']; V03 after removing placeholders, no digit token outside
    allowed_tokens(pack); V04 a LOSS shift's title has no gain word and a GAIN shift's title has no loss word."""
```

**Renderer and fallback** (`python/sr_lib/render.py`, `fallback.py`):

```python
def format_fact(fact: dict, currency: str) -> str: ...                 # "23.4%", "-0.84 pts", "INR 1.8M", "+3.1%"
def render_markdown(llm: dict, pack: dict, currency: str) -> str: ...
def render_html(llm: dict, pack: dict, currency: str) -> str: ...      # each number: <span class="fact" title="<src>">…</span>
def template_brief(pack: dict) -> dict: ...                           # same shape as the schema, built deterministically
```

The template writes, per shift: title "\<brand> \<gained|lost> share in \<market>"; why "Largest driver: \<term> ({{fX}}). Most of it came from \<retailer> ({{fY}})."; so\_what "Check \<term> at \<retailer>."; next\_question "Who took the share?".

**Brief writer** — `APP.SP_WRITE_BRIEF(P_RUN_ID VARCHAR) RETURNS VARCHAR` (Python 3.11):

```sql
CREATE STAGE IF NOT EXISTS SR_DB.APP.CODE;
-- scripts/deploy_all.sh: zip python/sr_lib and PUT it to @SR_DB.APP.CODE (AUTO_COMPRESS = FALSE, OVERWRITE = TRUE)
CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_WRITE_BRIEF(P_RUN_ID VARCHAR)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'snowflake-ml-python')
IMPORTS = ('@SR_DB.APP.CODE/sr_lib.zip')
HANDLER = 'sr_lib.run.write_brief'
EXECUTE AS CALLER;
```

Sequence inside `write_brief(session: Session, run_id: str) -> str`:

1. Read `BRIEF_ID` and `PACK` from `APP.FACT_PACK` for the run; read `LLM_MODEL`, `LLM_FALLBACK_MODEL`, `DISPLAY_ALIAS`.
2. If `DISPLAY_ALIAS` is true, replace brand and manufacturer names with the aliases in APP.V\_ALIAS (L11) before prompting.
3. Attempt 1: `snowflake.cortex.complete(model, prompt, options=CompleteOptions(temperature=0, max_tokens=1500, response_format=SCHEMA), session=session)`, then `json.loads` and `validate_brief`.
4. Attempt 2 (if attempt 1 raised or returned violations): the fallback model, with the violations appended to the prompt as "Fix these problems: …".
5. If both fail, use `template_brief(pack)`; `GENERATOR = 'TEMPLATE'`.
6. Render markdown and HTML; count tokens with `SNOWFLAKE.CORTEX.COUNT_TOKENS`; insert into `APP.BRIEF` with `STATUS = 'PUBLISHED'` and `PUBLISHED_AT`, storing `LLM_JSON` and `VIOLATIONS` for the Trust page.
7. Return `BRIEF_ID`.

## L9 Orchestration: run, trigger, replay, delivery

A stream on the share table wakes a triggered task; one Python procedure runs the steps in order, logs each one and decides whether a failure stops the run or only downgrades it. Delivery is decoupled: an alert on new data in `APP.BRIEF` sends the email.

**`APP.SP_RUN_WEEK`** — steps, in order:

| No | Step | Call | Critical | On failure |
| --- | --- | --- | --- | --- |
| 1 | OPEN | Insert `OPS.RUN_LOG` (RUNNING); skip if a SUCCEEDED run exists for the same as-of week and scope, unless `P_FORCE` | Yes | Run FAILED |
| 2 | CAPABILITY | `CALL APP.SP_CAPABILITY_CHECK()` | Yes | Run FAILED |
| 3 | SNAPSHOT | `CALL APP.SP_SNAPSHOT(:run)` | No | WARN; rule R3 skipped |
| 4 | DETECT | `CALL APP.SP_DETECT_SHIFTS(:run)` | Yes | Run FAILED |
| 5 | ML\_ANOMALY | `CALL APP.SP_ML_SHARE_ANOMALY(:run)` | No | WARN; confidence from z only |
| 6 | BRIDGE | `CALL APP.SP_BRIDGE(:run)` | Yes | Run FAILED |
| 7 | ARTEFACT | `CALL APP.SP_ARTEFACT(:run)` | Yes | Run FAILED |
| 8 | RANK | `CALL APP.SP_RANK(:run)` | Yes | Run FAILED |
| 9 | WHERE | `CALL APP.SP_WHERE(:run)`, then `CALL APP.SP_WHERE_INSIGHTS(:run)` | Exact part only | WARN if TOP\_INSIGHTS fails |
| 10 | FLOW | `CALL APP.SP_FLOW(:run)` | No | WARN; brief omits "who took it" |
| 11 | EARLY\_WARNING | `CALL APP.SP_EARLY_WARNING(:run)` | No | WARN; empty watchlist |
| 12 | FACT\_PACK | `CALL APP.SP_BUILD_FACT_PACK(:run)` | Yes | Run FAILED |
| 13 | BRIEF | `CALL APP.SP_WRITE_BRIEF(:run)` | Yes | Cannot fail silently: template fallback |
| 14 | CLOSE | Update `RUN_LOG` (SUCCEEDED, counts, `CREDITS_EST`, `BRIEF_ID`) | — | — |

Steps 5 and 9 (TOP\_INSIGHTS part) are skipped when the run's estimated credits pass `MAX_CREDITS_PER_RUN`.

```python
# python/sr_lib/run.py
from snowflake.snowpark import Session

Step = tuple[int, str, str, bool]          # (step_no, name, sql_template, critical)

STEPS: list[Step] = [
    (2,  "CAPABILITY",    "CALL SR_DB.APP.SP_CAPABILITY_CHECK()", True),
    (3,  "SNAPSHOT",      "CALL SR_DB.APP.SP_SNAPSHOT('{run}')", False),
    (4,  "DETECT",        "CALL SR_DB.APP.SP_DETECT_SHIFTS('{run}')", True),
    (5,  "ML_ANOMALY",    "CALL SR_DB.APP.SP_ML_SHARE_ANOMALY('{run}')", False),
    (6,  "BRIDGE",        "CALL SR_DB.APP.SP_BRIDGE('{run}')", True),
    (7,  "ARTEFACT",      "CALL SR_DB.APP.SP_ARTEFACT('{run}')", True),
    (8,  "RANK",          "CALL SR_DB.APP.SP_RANK('{run}')", True),
    (9,  "WHERE",         "CALL SR_DB.APP.SP_WHERE('{run}')", True),
    (9,  "TOP_INSIGHTS",  "CALL SR_DB.APP.SP_WHERE_INSIGHTS('{run}')", False),
    (10, "FLOW",          "CALL SR_DB.APP.SP_FLOW('{run}')", False),
    (11, "EARLY_WARNING", "CALL SR_DB.APP.SP_EARLY_WARNING('{run}')", False),
    (12, "FACT_PACK",     "CALL SR_DB.APP.SP_BUILD_FACT_PACK('{run}')", True),
    (13, "BRIEF",         "CALL SR_DB.APP.SP_WRITE_BRIEF('{run}')", True),
]

def open_run(session: Session, trigger_type: str, force: bool) -> str | None: ...   # RUN_ID, or None if skipped
def log_step(session: Session, run_id: str, step_no: int, step: str, status: str,
             rows: int | None, message: str | None) -> None: ...
def estimate_credits(session: Session, run_id: str) -> float: ...                  # from QUERY_TAG, see L14
def close_run(session: Session, run_id: str, status: str, error: str | None) -> None: ...
def run_week(session: Session, trigger_type: str = "MANUAL", force: bool = False) -> str: ...
```

```sql
-- sql/40_app/413_sp_run_week.sql
CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_RUN_WEEK(P_TRIGGER VARCHAR DEFAULT 'MANUAL', P_FORCE BOOLEAN DEFAULT FALSE)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
IMPORTS = ('@SR_DB.APP.CODE/sr_lib.zip')
HANDLER = 'sr_lib.run.run_week'
EXECUTE AS CALLER;

-- sql/60_ops/601_stream_task.sql
CREATE OR REPLACE STREAM SR_DB.OPS.ST_SHARE_COMPARE ON DYNAMIC TABLE SR_DB.CORE.DT_SHARE_COMPARE;

CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_RUN_FROM_STREAM()
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  rid VARCHAR;
BEGIN
  -- reading the stream inside DML advances its offset when the statement commits
  INSERT INTO SR_DB.OPS.STREAM_CONSUMED SELECT CURRENT_TIMESTAMP(), COUNT(*) FROM SR_DB.OPS.ST_SHARE_COMPARE;
  LET is_replay BOOLEAN := FALSE;
  SELECT UPDATED_AT > DATEADD(minute, -15, CURRENT_TIMESTAMP()) INTO :is_replay
    FROM SR_DB.OPS.SETTINGS WHERE SETTING_KEY = 'AS_OF_WEEK_END';
  IF (is_replay) THEN
    CALL SR_DB.APP.SP_RUN_WEEK('REPLAY', TRUE) INTO :rid;    -- a replayed week always runs, even if it ran before
  ELSE
    CALL SR_DB.APP.SP_RUN_WEEK('STREAM', FALSE) INTO :rid;
  END IF;
  RETURN rid;
END;
$$;

CREATE OR REPLACE TASK SR_DB.OPS.T_RUN_WEEK
  WAREHOUSE = SR_WH_M
  WHEN SYSTEM$STREAM_HAS_DATA('SR_DB.OPS.ST_SHARE_COMPARE')
AS
  CALL SR_DB.APP.SP_RUN_FROM_STREAM();
ALTER TASK SR_DB.OPS.T_RUN_WEEK RESUME;

-- sql/60_ops/602_replay.sql
CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_REPLAY_NEXT_WEEK()
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  cur_wk  DATE;
  next_wk DATE;
BEGIN
  LET n_running NUMBER := 0;
  SELECT COUNT(*) INTO :n_running FROM SR_DB.OPS.RUN_LOG
   WHERE STATUS = 'RUNNING' AND STARTED_AT > DATEADD(minute, -30, CURRENT_TIMESTAMP());
  IF (n_running > 0) THEN
    RETURN 'BUSY';                                   -- never move the week under a running run
  END IF;
  SELECT SETTING_VALUE::VARCHAR::DATE INTO :cur_wk FROM SR_DB.OPS.SETTINGS WHERE SETTING_KEY = 'AS_OF_WEEK_END';
  SELECT MIN(WEEK_END_DATE) INTO :next_wk FROM SR_DB.SRC.V_SRC_FACT_WEEKLY_ALL WHERE WEEK_END_DATE > :cur_wk;
  IF (next_wk IS NULL) THEN
    RETURN 'NO_MORE_WEEKS';
  END IF;
  UPDATE SR_DB.OPS.SETTINGS
     SET SETTING_VALUE = TO_VARIANT(TO_CHAR(:next_wk, 'YYYY-MM-DD')), UPDATED_AT = CURRENT_TIMESTAMP()
   WHERE SETTING_KEY = 'AS_OF_WEEK_END';
  ALTER DYNAMIC TABLE SR_DB.CORE.DT_SHARE_COMPARE REFRESH;   -- refreshes upstream dynamic tables as needed
  ALTER DYNAMIC TABLE SR_DB.CORE.DT_SHARE_WEEK REFRESH;
  RETURN 'AS_OF=' || TO_CHAR(:next_wk, 'YYYY-MM-DD');
END;
$$;
-- APP.SP_REPLAY_RESET(P_WEEK VARCHAR) sets AS_OF_WEEK_END back to P_WEEK for rehearsals, same pattern.
```

**Delivery** — the integrations need `CREATE INTEGRATION`, so the organizers may have to run them. Per the [webhook notification docs](https://docs.snowflake.com/en/user-guide/notifications/webhook-notifications), the Teams workflow URL's secret part goes into a secret object.

```sql
-- sql/60_ops/603_notifications.sql
CREATE NOTIFICATION INTEGRATION IF NOT EXISTS SR_EMAIL_INT
  TYPE = EMAIL
  ENABLED = TRUE
  ALLOWED_RECIPIENTS = ('<analyst>@nielseniq.com');
GRANT USAGE ON INTEGRATION SR_EMAIL_INT TO ROLE SR_APP;

-- stretch (SR-055)
CREATE SECRET IF NOT EXISTS SR_DB.OPS.SR_TEAMS_SECRET
  TYPE = GENERIC_STRING
  SECRET_STRING = '<secret part of the Teams workflow URL>';
CREATE NOTIFICATION INTEGRATION IF NOT EXISTS SR_TEAMS_INT
  TYPE = WEBHOOK
  ENABLED = TRUE
  WEBHOOK_URL = '<workflow URL with its secret replaced by SNOWFLAKE_WEBHOOK_SECRET>'
  WEBHOOK_SECRET = SR_DB.OPS.SR_TEAMS_SECRET
  WEBHOOK_BODY_TEMPLATE = '{"text": "SNOWFLAKE_WEBHOOK_MESSAGE"}'
  WEBHOOK_HEADERS = ('Content-Type' = 'application/json');

-- sql/60_ops/604_alert.sql
CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_NOTIFY_NEW_BRIEFS()
RETURNS NUMBER
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  n     NUMBER DEFAULT 0;
  rcpts ARRAY;
  rs    RESULTSET DEFAULT (SELECT BRIEF_ID, HEADLINE, BODY_HTML FROM SR_DB.APP.BRIEF
                           WHERE STATUS = 'PUBLISHED' AND NOTIFIED_AT IS NULL AND NOTIFY_ATTEMPTS < 3);
  c     CURSOR FOR rs;
BEGIN
  SELECT ARRAY_AGG(VALUE::VARCHAR) INTO :rcpts FROM TABLE(FLATTEN(INPUT => SR_DB.OPS.CFG('NOTIFY_EMAILS')));
  FOR r IN c DO
    LET bid  VARCHAR := r.BRIEF_ID;
    LET subj VARCHAR := 'Share Radar: ' || r.HEADLINE;
    LET html VARCHAR := r.BODY_HTML;
    BEGIN
      CALL SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(
        SNOWFLAKE.NOTIFICATION.TEXT_HTML(:html),
        SNOWFLAKE.NOTIFICATION.EMAIL_INTEGRATION_CONFIG('SR_EMAIL_INT', :subj, :rcpts));
      UPDATE SR_DB.APP.BRIEF SET NOTIFIED_AT = CURRENT_TIMESTAMP(), NOTIFY_ATTEMPTS = NOTIFY_ATTEMPTS + 1 WHERE BRIEF_ID = :bid;
      INSERT INTO SR_DB.OPS.NOTIFY_LOG (BRIEF_ID, CHANNEL, STATUS) VALUES (:bid, 'EMAIL', 'SENT');
      n := n + 1;
    EXCEPTION
      WHEN OTHER THEN
        UPDATE SR_DB.APP.BRIEF SET NOTIFY_ATTEMPTS = NOTIFY_ATTEMPTS + 1 WHERE BRIEF_ID = :bid;
        INSERT INTO SR_DB.OPS.NOTIFY_LOG (BRIEF_ID, CHANNEL, STATUS, MESSAGE) VALUES (:bid, 'EMAIL', 'FAILED', :SQLERRM);
    END;
  END FOR;
  RETURN n;
END;
$$;

-- Alert on new data: no SCHEDULE, so only newly inserted BRIEF rows are evaluated
CREATE OR REPLACE ALERT SR_DB.OPS.A_NEW_BRIEF
  WAREHOUSE = SR_WH_XS
  IF (EXISTS (SELECT 1 FROM SR_DB.APP.BRIEF WHERE STATUS = 'PUBLISHED'))
  THEN CALL SR_DB.APP.SP_NOTIFY_NEW_BRIEFS();
ALTER ALERT SR_DB.OPS.A_NEW_BRIEF RESUME;
```

With Teams enabled, the same procedure also calls `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(SNOWFLAKE.NOTIFICATION.TEXT_PLAIN(SNOWFLAKE.NOTIFICATION.SANITIZE_WEBHOOK_CONTENT(:msg)), SNOWFLAKE.NOTIFICATION.INTEGRATION('SR_TEAMS_INT'))`. An [alert on new data](https://docs.snowflake.com/en/user-guide/alerts) cannot be run by hand with `EXECUTE ALERT`; for rehearsals, call `SP_NOTIFY_NEW_BRIEFS()` directly.

## L10 Semantic view, search, agent and CoWork

The agent reads the same precomputed tables as the brief: a semantic view for open questions, a search service for method questions, and five procedures for the why-questions. One refactor makes this work for any brand, not just gated shifts: the bridge `SELECT` from L6 is also saved as view `APP.V_BRIDGE_ALL` over every `DT_SHARE_COMPARE` row, and `SP_BRIDGE` inserts from that view joined to the run's candidates.

**Semantic-layer views** (`sql/50_sem/501_v_sem_views.sql`): `SEM.V_SEM_SHARE_GRID` is `CORE.V_SHARE_GRID` joined to `SRC.V_SRC_MARKET` for `MARKET_NAME` and `MARKET_LEVEL`. `SEM.V_SEM_SHARE_CHANGE` is `CORE.DT_SHARE_COMPARE` left-joined to `APP.V_BRIDGE_ALL` and to the latest successful run's `APP.SHIFT_RANKED`. Its columns are `CMP_CODE`, `MARKET_ID`, `MARKET_NAME`, `CATEGORY`, `MANUFACTURER`, `BRAND`, `SHARE_NOW_PCT`, `SHARE_BEFORE_PCT`, `SHARE_CHANGE_PTS`, `VALUE_AT_STAKE`, `BRIDGE_DIST_PTS`, `BRIDGE_VELOCITY_PTS`, `BRIDGE_PRICE_PTS`, `BRIDGE_PROMO_PTS`, `ARTEFACT_LABEL` (default `MARKET_MOVE`) and `IS_SELECTED`.

**Semantic view** — syntax per [CREATE SEMANTIC VIEW](https://docs.snowflake.com/en/sql-reference/sql/create-semantic-view); FACTS must come before DIMENSIONS.

```sql
-- sql/50_sem/502_sv_share.sql
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
    grid.cat_tdp          AS CAT_TDP_SUM,
    chg.share_now_pct     AS SHARE_NOW_PCT,
    chg.share_before_pct  AS SHARE_BEFORE_PCT,
    chg.share_change_pts  AS SHARE_CHANGE_PTS COMMENT = 'Share now minus share before, in share points',
    chg.value_at_stake    AS VALUE_AT_STAKE   COMMENT = 'Share change times current category sales, local currency',
    chg.dist_pts          AS BRIDGE_DIST_PTS,
    chg.velocity_pts      AS BRIDGE_VELOCITY_PTS,
    chg.price_pts         AS BRIDGE_PRICE_PTS,
    chg.promo_pts         AS BRIDGE_PROMO_PTS
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
    grid.distribution_share_pct AS 100 * SUM(grid.tdp) / NULLIF(MAX(grid.cat_tdp), 0),
    grid.total_value_sales      AS SUM(grid.value_sales),
    chg.total_share_change_pts  AS SUM(chg.share_change_pts) COMMENT = 'Adds up across brands within one market and comparison',
    chg.total_value_at_stake    AS SUM(chg.value_at_stake)
  )
  COMMENT = 'Share Radar governed share metrics'
  AI_SQL_GENERATION 'Always filter grid to one PERIOD_CODE and chg to one CMP_CODE. Share metrics are valid only within one market and category, so group by MARKET_NAME and CATEGORY whenever more than one is requested. Never sum or average shares across markets. Show shares with one decimal and share changes with two.';
```

**Method knowledge base and search** (`sql/50_sem/503_kb_and_search.sql`; `scripts/load_kb.py` splits `kb/*.md` at ` ##  ` headings into rows):

```sql
CREATE TABLE IF NOT EXISTS SR_DB.KB.METHOD_DOCS (
  DOC_ID VARCHAR(64) NOT NULL PRIMARY KEY, TITLE VARCHAR NOT NULL, SECTION VARCHAR NOT NULL,
  BODY VARCHAR NOT NULL, SOURCE_FILE VARCHAR NOT NULL, UPDATED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE CORTEX SEARCH SERVICE SR_DB.SEM.CSS_METHOD
  ON BODY
  PRIMARY KEY (DOC_ID)
  ATTRIBUTES TITLE, SECTION
  WAREHOUSE = SR_WH_XS
  TARGET_LAG = '1 day'
  EMBEDDING_MODEL = 'snowflake-arctic-embed-l-v2.0'
  AS (SELECT DOC_ID, TITLE, SECTION, BODY, SOURCE_FILE FROM SR_DB.KB.METHOD_DOCS);
```

KB files: `acv_and_tdp.md` (%ACV, TDP, velocity), `share_bridge.md` (method, modes, reading the terms), `artefact_rules.md` (R1–R6 and what to do about each), `periods.md` (period and comparison codes), `glossary.md` (share points, value at stake, confidence, suppression).

**Tool procedures** (`sql/40_app/414_tool_procs.sql`). Each takes names as people type them, resolves them case-insensitively against the latest data (exact match first, then `EDITDISTANCE <= 2`), and returns a JSON string built with `TO_JSON(OBJECT_CONSTRUCT(...))`. No match returns `{"error": "NOT_FOUND", "candidates": [...]}`.

| Procedure | Signature | Returns (keys) |
| --- | --- | --- |
| Bridge | `APP.TOOL_GET_SHARE_BRIDGE(P_BRAND VARCHAR, P_MARKET VARCHAR, P_CMP_CODE VARCHAR) RETURNS VARCHAR` | `brand, market, cmp_code, as_of_week, share_now_pct, share_before_pct, change_pts, mode, terms_pts{distribution, velocity, price, promo}, top_retailers[{retailer, total_pts, performance_pts, mix_pts}], artefact_label, source` |
| Artefact | `APP.TOOL_CHECK_ARTEFACT(P_MARKET VARCHAR, P_CMP_CODE VARCHAR, P_BRAND VARCHAR) RETURNS VARCHAR` | `label, rules[{rule_id, severity, evidence}], source` |
| Flow | `APP.TOOL_SHARE_FLOW(P_BRAND VARCHAR, P_MARKET VARCHAR, P_CMP_CODE VARCHAR) RETURNS VARCHAR` | `direction, flows[{brand, pts}], method_note` |
| What-if | `APP.TOOL_WHAT_IF(P_BRAND VARCHAR, P_MARKET VARCHAR, P_LEVER VARCHAR, P_TARGET VARCHAR) RETURNS VARCHAR` | As `SP_WHAT_IF` (L6), comparison `L4W_VS_YA` |
| Latest brief | `APP.TOOL_LATEST_BRIEF(P_SCOPE VARCHAR) RETURNS VARCHAR` | `brief_id, as_of_week, headline, shifts[{brand, market, title, change_pts}], held_back[...]` |

Tool procedures read only the `SEM.V_TOOL_*` views (L12), so callers need no table grants and the row policy always applies. The artefact tool returns the latest run's checks, which cover every scope market and comparison; outside the scope it returns `{"label": "NOT_CHECKED"}`. Retailer contributions exist for ranked shifts only, so for any other brand `top_retailers` is empty, and the tool says so in a `note` key.

**Agent** (`sql/50_sem/504_agent.sql`) — structure per [CREATE AGENT](https://docs.snowflake.com/sql-reference/sql/create-agent). Analyst and custom tools need a nested `execution_environment`, per Snowflake's [custom tools tutorial](https://skills.sh/snowflake-labs/sfguides/cortex-agents-with-custom-tools-tutorial). Some examples use `name` instead of `search_service` for the search resource; keep whichever key the account accepts.

```sql
CREATE OR REPLACE AGENT SR_DB.SEM.SHARE_RADAR_AGENT
  COMMENT = 'Ask-Why agent for competitive share shifts'
  PROFILE = '{"display_name": "Share Radar", "color": "blue"}'
  FROM SPECIFICATION
  $$
  models:
    orchestration: auto
  orchestration:
    budget:
      seconds: 60
      tokens: 16000
  instructions:
    orchestration: >
      You explain competitive market share changes for NIQ client-service analysts.
      For any question about why share changed, call get_share_bridge first, then check_artefact.
      For who gained or lost the share, call share_flow. For lever scenarios, call what_if and repeat its assumption.
      For any other number use share_analyst. For definitions or method use method_search.
      Never calculate, round or estimate numbers yourself; quote them exactly as tools return them.
      If a tool returns an error or nothing, say so. Never fill the gap. If it returns AMBIGUOUS, ask which of the candidates the user means.
    response: >
      Lead with the answer in one sentence and name the period comparison.
      If check_artefact returns POSSIBLE_DATA_EFFECT, say so in the first sentence.
      Then at most four bullets: drivers in share points, where it happened, who gained, data status.
    sample_questions:
      - question: "Why did <brand> lose share in <market> in the last 4 weeks vs year ago?"
      - question: "Who took the share <brand> lost in <market>?"
      - question: "Is the <brand> drop real or a data effect?"
      - question: "What if <brand> restored distribution to last year's level?"
  tools:
    - tool_spec:
        type: "cortex_analyst_text_to_sql"
        name: "share_analyst"
        description: "Governed share, sales, distribution and share-change numbers by brand, market and period"
    - tool_spec:
        type: "cortex_search"
        name: "method_search"
        description: "Definitions and method: ACV, TDP, velocity, the share bridge, artefact rules, period codes"
    - tool_spec:
        type: "generic"
        name: "get_share_bridge"
        description: "Exact share-change bridge (distribution, velocity, price, promo, in share points) and top retailer contributions for one brand, market and comparison"
        input_schema:
          type: "object"
          properties:
            p_brand: {type: "string", description: "Brand name as the user wrote it"}
            p_market: {type: "string", description: "Market or retailer name"}
            p_cmp_code: {type: "string", description: "L4W_VS_YA, L4W_VS_PP, L12W_VS_YA or L52W_VS_YA; default L4W_VS_YA"}
          required: ["p_brand", "p_market", "p_cmp_code"]
    - tool_spec:
        type: "generic"
        name: "check_artefact"
        description: "Whether a share change could be a data effect (coverage, feed, restatement, recode, spike, gap), with evidence"
        input_schema:
          type: "object"
          properties:
            p_market: {type: "string", description: "Market or retailer name"}
            p_cmp_code: {type: "string", description: "Comparison code"}
            p_brand: {type: "string", description: "Brand name, or empty for market-level rules only"}
          required: ["p_market", "p_cmp_code", "p_brand"]
    - tool_spec:
        type: "generic"
        name: "share_flow"
        description: "Which brands gained the share a brand lost, or lost the share it gained, in share points (proportional allocation)"
        input_schema:
          type: "object"
          properties:
            p_brand: {type: "string", description: "Brand name"}
            p_market: {type: "string", description: "Market or retailer name"}
            p_cmp_code: {type: "string", description: "Comparison code"}
          required: ["p_brand", "p_market", "p_cmp_code"]
    - tool_spec:
        type: "generic"
        name: "what_if"
        description: "Mechanical share impact of restoring or changing distribution or promo for a brand"
        input_schema:
          type: "object"
          properties:
            p_brand: {type: "string", description: "Brand name"}
            p_market: {type: "string", description: "Market or retailer name"}
            p_lever: {type: "string", description: "DISTRIBUTION or PROMO"}
            p_target: {type: "string", description: "BASE to restore the year-ago level, or a signed percentage such as +10%"}
          required: ["p_brand", "p_market", "p_lever", "p_target"]
    - tool_spec:
        type: "generic"
        name: "latest_brief"
        description: "Headline and top shifts of the latest published brief"
        input_schema:
          type: "object"
          properties:
            p_scope: {type: "string", description: "Scope key, or empty for the default scope"}
          required: ["p_scope"]
  tool_resources:
    share_analyst:
      semantic_view: "SR_DB.SEM.SV_SHARE"
      execution_environment: {type: "warehouse", warehouse: "SR_WH_XS"}
    method_search:
      search_service: "SR_DB.SEM.CSS_METHOD"
      max_results: 4
    get_share_bridge:
      type: "procedure"
      identifier: "SR_DB.APP.TOOL_GET_SHARE_BRIDGE"
      execution_environment: {type: "warehouse", warehouse: "SR_WH_XS"}
    check_artefact:
      type: "procedure"
      identifier: "SR_DB.APP.TOOL_CHECK_ARTEFACT"
      execution_environment: {type: "warehouse", warehouse: "SR_WH_XS"}
    share_flow:
      type: "procedure"
      identifier: "SR_DB.APP.TOOL_SHARE_FLOW"
      execution_environment: {type: "warehouse", warehouse: "SR_WH_XS"}
    what_if:
      type: "procedure"
      identifier: "SR_DB.APP.TOOL_WHAT_IF"
      execution_environment: {type: "warehouse", warehouse: "SR_WH_XS"}
    latest_brief:
      type: "procedure"
      identifier: "SR_DB.APP.TOOL_LATEST_BRIEF"
      execution_environment: {type: "warehouse", warehouse: "SR_WH_XS"}
  $$;
```

**CoWork registration** (`sql/50_sem/505_cowork.sql`). Adding an agent to the [CoWork object](https://docs.snowflake.com/en/user-guide/snowflake-cortex/snowflake-cowork/deploy-agents) needs ALTER on that object, so the organizers may run it. Confirm the exact statement on the account; the Snowsight route is AI & ML » Agents » the CoWork tab.

```sql
ALTER SNOWFLAKE INTELLIGENCE SNOWFLAKE_INTELLIGENCE_OBJECT_DEFAULT ADD AGENT SR_DB.SEM.SHARE_RADAR_AGENT;  -- verify syntax
GRANT USAGE ON AGENT SR_DB.SEM.SHARE_RADAR_AGENT TO ROLE SR_ANALYST;
GRANT USAGE ON AGENT SR_DB.SEM.SHARE_RADAR_AGENT TO ROLE SR_JUDGE;
```

**Stretch: one skill, two agents (SR-045).** [Agent skills](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-skills) are attached by updating the live specification (JSON) with a `skills` entry whose source is a stage path:

```sql
CREATE STAGE IF NOT EXISTS SR_DB.SEM.SKILLS;
-- PUT .cortex/skills/share-methodology/SKILL.md to @SR_DB.SEM.SKILLS/share-methodology/ (AUTO_COMPRESS = FALSE)
ALTER AGENT SR_DB.SEM.SHARE_RADAR_AGENT MODIFY LIVE VERSION SET SPECIFICATION =
  '<the specification above as JSON, plus "skills": [{"name": "share-methodology", "source": {"type": "STAGE", "path": "@SR_DB.SEM.SKILLS/share-methodology"}}]>';
```

## L11 Streamlit app

One codebase deploys as two Streamlit in Snowflake apps on the warehouse runtime. `SR_DB.APP.SHARE_RADAR` is the read-only app that analysts and judges open; it is owned by the read-only role `SR_UI` (added in L12). `SR_DB.APP.SHARE_RADAR_ADMIN` adds the replay controls and the Settings page; it is owned by `SR_APP`, and only the team can open it. Apps run with their [owner's rights](https://docs.snowflake.com/en/developer-guide/streamlit/object-management/owners-rights): the owner role, not the viewer's role, decides what an app can read or change. That is why the admin controls live in a separate app guarded by a grant, not behind an `if` in the code.

Four rules follow from the owner's-rights model:

- **The app never runs pipeline steps itself.** A warehouse-runtime app runs as an owner's-rights stored procedure, and the steps set the query tag with `ALTER SESSION`, which owner's-rights code cannot do. The admin app starts work with [`EXECUTE TASK`](https://docs.snowflake.com/en/sql-reference/sql/execute-task) and watches `OPS.RUN_LOG` and `OPS.STEP_LOG`. A task with no schedule runs only when someone executes it, and a suspended task can be executed without resuming it.
- **No `SHOW` or `DESCRIBE` in app code.** Read our own tables, or `INFORMATION_SCHEMA` table functions.
- **`CURRENT_USER()` needs `READ SESSION` on the owner role** ([row access in Streamlit](https://docs.snowflake.com/en/developer-guide/streamlit/features/row-access)). Until it is granted, `viewer_name()` returns `None` and the sidebar says "viewer unknown".
- **Caching is per viewer session** on the warehouse runtime ([limitations](https://docs.snowflake.com/developer-guide/streamlit/limitations)), so `st.cache_data` saves repeat queries within one visit, not across viewers.

**Files**

| File | Responsibility |
| --- | --- |
| `streamlit/streamlit_app.py` | Entry point of SHARE\_RADAR: `st.set_page_config(layout="wide")`, then `nav.run(admin=False)` |
| `streamlit/admin_app.py` | Entry point of SHARE\_RADAR\_ADMIN: the same with `admin=True` |
| `streamlit/sr_ui/nav.py` | Page list (`st.navigation`), sidebar, session-state defaults |
| `streamlit/pages/0_Radar.py` | Home: this week's shifts, held back, watchlist; replay panel in the admin app |
| `streamlit/pages/1_Shift_detail.py` | One shift: bridge, trend, where, who took it, data checks, what-if |
| `streamlit/pages/2_Brief.py` | Published brief, with each number's source on hover |
| `streamlit/pages/3_Trust.py` | Golden set, reconciliation, bridge exactness, runs, cost, CoCo log |
| `streamlit/pages/4_Settings.py` | Admin app only: thresholds and recipients |
| `streamlit/sr_ui/data.py` | Every query and action; pages never write SQL |
| `streamlit/sr_ui/charts.py` | Altair chart builders |
| `streamlit/sr_ui/format.py` | Number, label and alias formatting |
| `streamlit/environment.yml`, `.streamlit/config.toml`, `snowflake.yml` | Packages, theme, CLI project (L2) |

```yaml
# streamlit/environment.yml: warehouse runtime takes the Snowflake Anaconda channel only; pin with "="
name: sf_env
channels:
  - snowflake
dependencies:
  - streamlit=1.51.0          # needs 1.37 or later: st.navigation, st.fragment(run_every), dataframe row selection
  - snowflake-snowpark-python
  - pandas
  - altair
```

```toml
# streamlit/.streamlit/config.toml
[theme]
base = "light"
```

If the deploy rejects 1.51.0, pin the newest version that the Snowsight package picker lists, as long as it is 1.37 or later ([dependency management](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/dependency-management)).

**SQL objects the app needs.** `sql/40_app/415_ui_objects.sql` is a new file, deployed after 414; the two tasks go into `601_stream_task.sql` and `602_replay.sql`.

```sql
-- Trend source for the app; the row access policy attaches here (L12), so SR_UI never reads the dynamic table
CREATE OR REPLACE VIEW SR_DB.APP.V_UI_SHARE_WEEK AS
SELECT WEEK_END_DATE, MARKET_ID, CATEGORY, MANUFACTURER, BRAND, VALUE_SHARE, DIST_SHARE, PRICE_INDEX, PROMO_INDEX
FROM SR_DB.CORE.DT_SHARE_WEEK;

-- Stable display aliases, used when DISPLAY_ALIAS = true. SP_WRITE_BRIEF reads the same view, so app and brief agree.
CREATE OR REPLACE VIEW SR_DB.APP.V_ALIAS AS
WITH base AS (
  SELECT MANUFACTURER, BRAND, SUM(VALUE_SALES) AS V
  FROM SR_DB.CORE.DT_BRAND_PERIOD
  WHERE PERIOD_CODE = 'L52W' AND MARKET_ID = SR_DB.OPS.CFG('SCOPE_PARENT_MARKET')::VARCHAR
  GROUP BY MANUFACTURER, BRAND
), b AS (
  SELECT BRAND AS REAL_NAME, ROW_NUMBER() OVER (ORDER BY SUM(V) DESC, BRAND) AS N FROM base GROUP BY BRAND
), m AS (
  SELECT MANUFACTURER AS REAL_NAME, ROW_NUMBER() OVER (ORDER BY SUM(V) DESC, MANUFACTURER) AS N FROM base GROUP BY MANUFACTURER
)
SELECT 'BRAND' AS KIND, REAL_NAME, 'Brand ' || IFF(N <= 26, CHR(64 + N), N::VARCHAR) AS ALIAS FROM b
UNION ALL
SELECT 'MANUFACTURER', REAL_NAME, 'Maker ' || IFF(N <= 26, CHR(64 + N), N::VARCHAR) FROM m;

-- No schedule: these run only when the admin app executes them
CREATE OR REPLACE TASK SR_DB.OPS.T_RUN_WEEK_MANUAL
  WAREHOUSE = SR_WH_M
AS
  CALL SR_DB.APP.SP_RUN_WEEK('MANUAL', TRUE);

CREATE OR REPLACE TASK SR_DB.OPS.T_REPLAY_NEXT
  WAREHOUSE = SR_WH_M
AS
  CALL SR_DB.APP.SP_REPLAY_NEXT_WEEK();
```

Two changes to L9 go with this, and L9 already shows them. `SP_REPLAY_NEXT_WEEK` returns `BUSY` while a run is in progress. `SP_RUN_FROM_STREAM` forces the run and marks it `REPLAY` when `AS_OF_WEEK_END` changed in the last 15 minutes, so a rehearsal can rerun a week that already has a brief.

**Pages**

| Page | What it shows, top to bottom | `data.py` calls |
| --- | --- | --- |
| Radar | Header: scope, week and run status. Four tiles: shifts past the gates, shifts in the brief, possible data effects, value at stake in the brief. "This week's shifts" table; selecting a row opens Shift detail. "Held back for data checks" (brand, market, change, rules). "Watchlist" (early warnings). "All candidates" expander with suppression reasons | `current_run`, `kpis`, `shifts`, `held_back`, `watchlist` |
| Shift detail | Shift picker, defaulting to the selected shift. Headline such as "Brand lost 0.84 pts in Market, last 4 weeks vs year ago", with the data-status chip and confidence. Bridge bars, with "terms add up to … (residual …)". Trend of value and distribution share over 104 weeks, with the compared periods shaded. Where: retailer bars and a performance/mix table, with TOP\_INSIGHTS rows below. Who took it. Data checks: each fired rule with its evidence. What-if form. "Ask why" question to paste into CoWork, hidden when names are masked | `shift`, `bridge`, `trend`, `where`, `flow`, `artefacts`, `what_if` |
| Brief | Brief picker, latest first. Headline. Chips: generator, model, published, emailed. Body HTML, with sources on hover. "Show sources" table. Validator violations from the attempts, if any | `briefs`, `brief`, `brief_facts` |
| Trust | Tiles: golden set (for example 28/30), reconciliation checks passed, largest bridge residual, last run's credits. Tables: failed golden questions, reconciliation, last 20 runs. Step timeline of a chosen run. LLM tokens per brief. CoCo log summary | `eval_latest`, `recon_latest`, `bridge_residual_max`, `runs`, `step_log`, `run_cost`, `coco_log` |
| Settings (admin app) | Settings table. An edit form for allowed keys only. Scope and as-of keys shown read-only, with a note that saving any setting makes the dynamic tables refresh once, because they read `OPS.SETTINGS` | `settings`, `save_setting` |

The admin app's Radar adds a replay panel: the data's as-of week, **Load next week**, **Rerun this week**, **Reset to week…** and a live progress panel. Both buttons are disabled while a run is in progress.

```python
# streamlit/sr_ui/nav.py
import streamlit as st

DEFAULTS = {"sr_admin": False, "shift_id": None, "brief_id": None, "awaiting": None}
# awaiting = {"kind": "REPLAY" | "RERUN", "since": <Snowflake timestamp text>, "t0": <time.monotonic()>}

def run(admin: bool) -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)
    st.session_state["sr_admin"] = admin
    pages = [st.Page("pages/0_Radar.py", title="Radar", default=True),
             st.Page("pages/1_Shift_detail.py", title="Shift detail"),
             st.Page("pages/2_Brief.py", title="Brief"),
             st.Page("pages/3_Trust.py", title="Trust")]
    if admin:
        pages.append(st.Page("pages/4_Settings.py", title="Settings"))
    page = st.navigation(pages)        # with st.navigation, Streamlit ignores automatic pages/ discovery
    sidebar()
    page.run()

def sidebar() -> None:
    """Scope (category, parent market name, focus manufacturer), as-of week, current run status and bridge mode,
    'Names masked' when DISPLAY_ALIAS is true, the viewer name or 'viewer unknown', and how to open the CoWork agent."""
```

```python
# streamlit/sr_ui/data.py: every query and action. Bind values with params; never format user input into SQL.
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st
from snowflake.snowpark import Session
from snowflake.snowpark.context import get_active_session

TTL_S = 120             # per viewer session on the warehouse runtime
BUSY_MIN = 30           # a RUNNING run younger than this blocks replay and rerun
TASKS = {"T_REPLAY_NEXT", "T_RUN_WEEK_MANUAL", "T_RUN_WEEK", "T_HEALTH"}

@dataclass(frozen=True)
class Run:
    run_id: str
    trigger_type: str           # STREAM | REPLAY | MANUAL
    as_of_week: date | None
    scope_key: str | None
    status: str                 # RUNNING | SUCCEEDED | FAILED | SKIPPED
    bridge_mode: str | None
    n_candidates: int | None
    n_ranked: int | None
    brief_id: str | None
    credits_est: float | None
    started_at: pd.Timestamp
    ended_at: pd.Timestamp | None
    error_msg: str | None

class Busy(Exception): ...

def session() -> Session: return get_active_session()
def q(sql: str, params: list | None = None) -> pd.DataFrame: return session().sql(sql, params=params).to_pandas()

# Context (cached)
def cfg(key: str) -> object: ...                    # json.loads(TO_JSON(SETTING_VALUE)) from OPS.SETTINGS
def scope_key() -> str: ...                         # SCOPE_CATEGORY|SCOPE_PARENT_MARKET|FOCUS_MANUFACTURER
def viewer_name() -> str | None: ...                # SELECT CURRENT_USER(); None on error
def aliases() -> dict[tuple[str, str], str]: ...    # APP.V_ALIAS: (KIND, REAL_NAME) -> ALIAS
def market_names() -> dict[str, str]: ...           # SRC.V_SRC_MARKET: MARKET_ID -> MARKET_NAME

# Runs (not cached: they drive the progress panel)
def current_run() -> Run | None:
    """SELECT * FROM SR_DB.OPS.RUN_LOG WHERE STATUS = 'SUCCEEDED'
       ORDER BY IFF(AS_OF_WEEK = ? AND SCOPE_KEY = ?, 0, 1), STARTED_AT DESC LIMIT 1
       params [cfg('AS_OF_WEEK_END'), scope_key()]"""
def active_run() -> Run | None: ...                 # STATUS = 'RUNNING' AND STARTED_AT > DATEADD(minute, -BUSY_MIN, CURRENT_TIMESTAMP())
def run_started_since(since: str) -> Run | None: ... # STARTED_AT >= TO_TIMESTAMP_LTZ(?) ORDER BY STARTED_AT DESC LIMIT 1
def step_log(run_id: str) -> pd.DataFrame: ...      # OPS.STEP_LOG + SECONDS = DATEDIFF(second, STARTED_AT, COALESCE(ENDED_AT, CURRENT_TIMESTAMP()))
def task_last_run(task: str) -> dict | None:
    """task must be in TASKS. SELECT STATE, ERROR_MESSAGE, SCHEDULED_TIME, COMPLETED_TIME
       FROM TABLE(SR_DB.INFORMATION_SCHEMA.TASK_HISTORY(TASK_NAME => '<task>', RESULT_LIMIT => 1))"""

# Radar (cached)
def shifts(run_id: str) -> pd.DataFrame:
    """SELECT r.SHIFT_ID, r.RANK_NO, r.CMP_CODE, r.MARKET_ID, r.CATEGORY, r.MANUFACTURER, r.BRAND, r.IS_FOCUS,
              c.SH1, c.SH0, 100 * r.D_SHARE AS D_SHARE_PTS, r.VALUE_AT_STAKE, c.Z_SCORE, c.ANOMALY_CONFIRMED,
              r.CONFIDENCE, r.ARTEFACT_LABEL, r.SCORE, r.SUPPRESSED, r.SUPPRESS_REASON, r.SELECTED
       FROM SR_DB.APP.SHIFT_RANKED r
       JOIN SR_DB.APP.SHIFT_CANDIDATE c ON c.RUN_ID = r.RUN_ID AND c.SHIFT_ID = r.SHIFT_ID
       WHERE r.RUN_ID = ? ORDER BY r.SELECTED DESC, r.SCORE DESC"""
def held_back(run_id: str) -> pd.DataFrame:
    """POSSIBLE_DATA_EFFECT shifts, top 3 by SCORE, with ARRAY_AGG(DISTINCT RULE_ID) of the HIGH rules on their
       RUN_ID, CMP_CODE, MARKET_ID, CATEGORY and (BRAND IS NULL OR BRAND = shift brand), the same match as SP_RANK."""
def watchlist(run_id: str) -> pd.DataFrame: ...     # APP.EARLY_WARNING, ORDER BY ABS(COALESCE(PROJECTED_SHARE_PTS, 0)) DESC
def kpis(run_id: str) -> dict[str, float]:
    """SELECT (SELECT COUNT_IF(PASSED_GATES) FROM SR_DB.APP.SHIFT_CANDIDATE WHERE RUN_ID = ?) AS N_PASSED,
              COUNT_IF(SELECTED) AS N_SELECTED, COUNT_IF(ARTEFACT_LABEL = 'POSSIBLE_DATA_EFFECT') AS N_DATA_EFFECT,
              SUM(IFF(SELECTED, ABS(VALUE_AT_STAKE), 0)) AS VALUE_SELECTED
       FROM SR_DB.APP.SHIFT_RANKED WHERE RUN_ID = ?          -- params [run_id, run_id]"""

# Shift detail (cached, except what_if)
def shift(shift_id: str) -> dict: ...               # SHIFT_RANKED + SHIFT_CANDIDATE (SH1, SH0, Z_SCORE, ANOMALY_*) + SHARE_BRIDGE (MODE, STATUS)
def bridge(shift_id: str) -> dict | None: ...       # SELECT * FROM SR_DB.APP.SHARE_BRIDGE WHERE SHIFT_ID = ?
def where(shift_id: str) -> pd.DataFrame: ...       # APP.SHIFT_WHERE ORDER BY METHOD, RANK_NO
def flow(run_id: str, cmp_code: str, market_id: str, category: str, brand: str, direction: str) -> pd.DataFrame:
    """LOSS: TO_BRAND AS COUNTERPART where FROM_BRAND = brand; GAIN: FROM_BRAND AS COUNTERPART where TO_BRAND = brand.
       ORDER BY FLOW_PTS DESC LIMIT 8"""
def artefacts(run_id: str, cmp_code: str, market_id: str, category: str, brand: str) -> pd.DataFrame: ...
    # APP.ARTEFACT_CHECK, (BRAND IS NULL OR BRAND = ?), ORDER BY SEVERITY, RULE_ID
def trend(market_id: str, category: str, brand: str, weeks: int = 104) -> pd.DataFrame:
    """SELECT WEEK_END_DATE, 100 * VALUE_SHARE AS VALUE_SHARE_PCT, 100 * DIST_SHARE AS DIST_SHARE_PCT
       FROM SR_DB.APP.V_UI_SHARE_WEEK WHERE MARKET_ID = ? AND CATEGORY = ? AND BRAND = ?
       QUALIFY ROW_NUMBER() OVER (ORDER BY WEEK_END_DATE DESC) <= ? ORDER BY WEEK_END_DATE"""
def what_if(shift_id: str, lever: str, target: str) -> dict:
    r = session().call("SR_DB.APP.SP_WHAT_IF", shift_id, lever, target)
    return r if isinstance(r, dict) else json.loads(r)

# Brief (cached)
def briefs(limit: int = 12) -> pd.DataFrame: ...    # PUBLISHED, ORDER BY AS_OF_WEEK DESC, PUBLISHED_AT DESC
def brief(brief_id: str) -> dict: ...               # APP.BRIEF row
def brief_facts(brief_id: str) -> pd.DataFrame:
    """SELECT f.KEY AS FACT_ID, f.VALUE:v::FLOAT AS V, f.VALUE:u::VARCHAR AS UNIT, f.VALUE:d::INT AS DECIMALS,
              f.VALUE:src::VARCHAR AS SOURCE
       FROM SR_DB.APP.FACT_PACK p, LATERAL FLATTEN(INPUT => p.PACK:facts) f
       WHERE p.BRIEF_ID = ? ORDER BY TRY_TO_NUMBER(SUBSTR(f.KEY, 2))"""

# Trust (cached)
def eval_latest() -> pd.DataFrame: ...              # OPS.EVAL_RESULT rows of the newest EVAL_RUN_ID
def recon_latest() -> pd.DataFrame: ...             # OPS.RECON_RESULT QUALIFY ROW_NUMBER() OVER (PARTITION BY CHECK_ID ORDER BY CHECKED_AT DESC) = 1
def bridge_residual_max(run_id: str) -> float | None: ...  # MAX(ABS(RESIDUAL_PTS)) WHERE RUN_ID = ? AND STATUS = 'OK'
def runs(limit: int = 20) -> pd.DataFrame: ...      # OPS.RUN_LOG + SECONDS, newest first
def run_cost(limit: int = 10) -> pd.DataFrame: ...  # OPS.V_RUN_COST (L14)
def coco_log() -> pd.DataFrame: ...                 # OPS.COCO_LOG grouped by TICKET, SURFACE
def tests_latest() -> pd.DataFrame: ...             # OPS.TEST_RESULT rows of the newest TEST_RUN_ID (T1)

# Admin actions (admin app only; never cached)
def start_task(task: str) -> str:
    """Raises Busy if active_run() is not None. Reads SELECT CURRENT_TIMESTAMP() as the anchor, runs
       EXECUTE TASK SR_DB.OPS.<task> (task in {'T_REPLAY_NEXT', 'T_RUN_WEEK_MANUAL', 'T_HEALTH'}), clears the cache, returns the anchor."""
def reset_replay(week: date) -> str: ...            # session().call("SR_DB.APP.SP_REPLAY_RESET", week.isoformat())
def settings() -> pd.DataFrame: ...                 # SETTING_KEY, TO_JSON(SETTING_VALUE) AS VALUE_JSON, DESCRIPTION, UPDATED_AT
EDITABLE: dict[str, tuple[type, float | None, float | None]] = {
    "MIN_SHARE_PTS": (float, 0.05, 5), "MIN_VALUE_AT_STAKE": (float, 0, None), "MIN_Z": (float, 0, 10),
    "TOP_N": (int, 1, 10), "SUPPRESS_RUNS": (int, 0, 12), "SUPPRESS_GROWTH": (float, 0, 5),
    "ART_STORE_CHG": (float, 0, 1), "ART_CAT_TDP_JUMP": (float, 0, 2), "ART_CAT_SPPD_FLAT": (float, 0, 1),
    "ART_RECODE_TOL": (float, 0, 1), "ART_SPIKE_K": (float, 1, 20), "EW_DIST_DROP": (float, -1, 0),
    "EW_PRICE_RISE": (float, 0, 1), "MAX_CREDITS_PER_RUN": (float, 0, 50),
    "DISPLAY_ALIAS": (bool, None, None), "TEAMS_ENABLED": (bool, None, None), "NOTIFY_EMAILS": (list, None, None)}
def save_setting(key: str, value: object) -> None:
    """ValueError unless key is in EDITABLE and value has the right type and bounds (NOTIFY_EMAILS: strings that
       contain '@' and appear in the email integration's ALLOWED_RECIPIENTS). Then
       UPDATE SR_DB.OPS.SETTINGS SET SETTING_VALUE = PARSE_JSON(?), UPDATED_AT = CURRENT_TIMESTAMP() WHERE SETTING_KEY = ?
       with [json.dumps(value), key], and clear the cache."""
def clear_cache() -> None: st.cache_data.clear()
```

**Replay panel and live progress** (`pages/0_Radar.py`, admin app only). The panel polls every 5 seconds through a fragment, so only the panel reruns. When the run ends, it reruns the whole app, and the Radar redraws on the new run. If `run_every` is not honoured on the account, a **Refresh** button calls the same function.

```python
import time
import streamlit as st
from sr_ui import data, format as fmt

N_STEPS = 14

def replay_panel() -> None:
    busy = data.active_run() is not None or st.session_state.awaiting is not None
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    c1.metric("Data as of", str(data.cfg("AS_OF_WEEK_END")))
    if c2.button("Load next week", disabled=busy):
        st.session_state.awaiting = {"kind": "REPLAY", "since": data.start_task("T_REPLAY_NEXT"), "t0": time.monotonic()}
    if c3.button("Rerun this week", disabled=busy):
        st.session_state.awaiting = {"kind": "RERUN", "since": data.start_task("T_RUN_WEEK_MANUAL"), "t0": time.monotonic()}
    with c4.popover("Reset to week…", disabled=busy):
        week = st.date_input("Week ending")
        if st.button("Reset"):
            st.toast(data.reset_replay(week)); data.clear_cache(); st.rerun()
    if busy or st.session_state.awaiting:
        progress_panel()

@st.fragment(run_every="5s")
def progress_panel() -> None:
    a = st.session_state.awaiting
    run = data.run_started_since(a["since"]) if a else data.active_run()
    if run is None:
        task = data.task_last_run("T_REPLAY_NEXT" if a and a["kind"] == "REPLAY" else "T_RUN_WEEK_MANUAL")
        if task and task["STATE"] == "FAILED":
            st.error(task["ERROR_MESSAGE"]); st.session_state.awaiting = None
        elif a and time.monotonic() - a["t0"] > 900:
            st.warning("No run started within 15 minutes; check task history (L14)."); st.session_state.awaiting = None
        else:
            st.info("Loading the new week; the run starts when the stream sees it…")
        return
    steps = data.step_log(run.run_id)
    done = steps.STEP_NO.nunique() if len(steps) else 0
    st.progress(min(1.0, done / N_STEPS), text=f"{fmt.RUN_CHIP[run.status]} · {steps.STEP.iloc[-1] if done else 'OPEN'}")
    st.dataframe(steps[["STEP", "STATUS", "SECONDS", "ROWS_WRITTEN", "MESSAGE"]], hide_index=True)
    if run.status != "RUNNING":
        st.session_state.awaiting = None
        data.clear_cache()
        st.rerun()                                  # whole app
```

Selecting a shift on the Radar uses `st.dataframe(view, on_select="rerun", selection_mode="single-row", column_config={"SHIFT_ID": None}, hide_index=True)`. The selected row's ID goes to `st.session_state.shift_id`, then `st.switch_page("pages/1_Shift_detail.py")`. The Brief page renders `BODY_HTML` with `st.html`, after a small style rule: `.fact { border-bottom: 1px dotted #898781; cursor: help }`. Each number's `title` attribute is its source. `render_html` (L8) escapes all LLM text with `html.escape` before it inserts the fact spans, and `st.html` sanitises the markup again.

**Charts** (`sr_ui/charts.py`). These use the reference palette's light values. Polarity is shown blue for a gain and red for a loss, with a neutral grey total. Two-series charts use categorical slots 1 and 2. Status colours are used only for run states, and always next to their text label. Every bar sits on a zero baseline. Signed value labels mean polarity never depends on colour alone. Every mark has a tooltip.

```python
from __future__ import annotations
from datetime import date
import altair as alt
import pandas as pd

GAIN, LOSS, TOTAL = "#2a78d6", "#e34948", "#898781"
SERIES = ["#2a78d6", "#eb6834"]                                   # value share, distribution share
STATUS = {"OK": "#0ca30c", "WARN": "#fab219", "FAILED": "#d03b3b", "SKIPPED": "#898781"}
INK_2, AXIS, SHADE = "#52514e", "#c3c2b7", "#f0efec"
TERMS = [("DIST_PTS", "Distribution"), ("VELOCITY_PTS", "Velocity"), ("PRICE_PTS", "Price"), ("PROMO_PTS", "Promo")]

def bridge_frame(b: dict) -> pd.DataFrame:
    """One SHARE_BRIDGE row -> (term, pts, kind): the terms its mode has, then 'Total change'. Points throughout."""
    rows = [(label, float(b[col])) for col, label in TERMS if b.get(col) is not None and not pd.isna(b[col])]
    rows.append(("Total change", 100.0 * float(b["D_SHARE"])))
    df = pd.DataFrame(rows, columns=["term", "pts"])
    df["kind"] = ["total" if t == "Total change" else ("gain" if p >= 0 else "loss") for t, p in zip(df.term, df.pts)]
    return df

def bridge_bars(b: dict) -> alt.LayerChart:
    df = bridge_frame(b)
    y = alt.Y("term:N", sort=list(df.term), title=None)
    bars = alt.Chart(df).mark_bar(cornerRadiusEnd=4, size=16).encode(
        y=y, x=alt.X("pts:Q", title="Share points"),
        color=alt.Color("kind:N", scale=alt.Scale(domain=["gain", "loss", "total"], range=[GAIN, LOSS, TOTAL]), legend=None),
        tooltip=[alt.Tooltip("term:N", title="Driver"), alt.Tooltip("pts:Q", title="Share points", format="+.2f")])
    pos = alt.Chart(df).transform_filter("datum.pts >= 0").mark_text(align="left", dx=4, color=INK_2).encode(
        y=y, x="pts:Q", text=alt.Text("pts:Q", format="+.2f"))
    neg = alt.Chart(df).transform_filter("datum.pts < 0").mark_text(align="right", dx=-4, color=INK_2).encode(
        y=y, x="pts:Q", text=alt.Text("pts:Q", format="+.2f"))
    zero = alt.Chart(pd.DataFrame({"x": [0.0]})).mark_rule(color=AXIS).encode(x="x:Q")
    return (bars + pos + neg + zero).properties(height=34 * len(df), width="container")

def retailer_bars(where_df: pd.DataFrame) -> alt.LayerChart:
    """EXACT_RETAILER rows: TOTAL_PTS by CONTRIBUTOR, sorted by ABS(TOTAL_PTS), gain/loss colours, signed labels,
    zero rule; the tooltip adds PERF_PTS and MIX_PTS."""
def flow_bars(flow_df: pd.DataFrame) -> alt.LayerChart:
    """COUNTERPART by FLOW_PTS in SERIES[0], value labels, no legend; the section title says which way share moved."""
def trend_lines(trend_df: pd.DataFrame, now: tuple[date, date], base: tuple[date, date] | None) -> alt.LayerChart:
    """Long format (WEEK_END_DATE, series, pct) on one % axis: value share SERIES[0], distribution share SERIES[1],
    2px lines, legend plus direct labels at the last week, SHADE rectangles for the compared periods,
    crosshair rule with tooltip."""
def step_timeline(steps_df: pd.DataFrame) -> alt.Chart:
    """Bars from STARTED_AT to ENDED_AT per STEP, coloured by STATUS with a legend; tooltip: rows written, message."""
```

In a Mode D shift, `bridge_frame` returns only "Total change", and the page adds "No distribution data: share change only". The what-if form is disabled when the bridge has no distribution share, and the PROMO lever appears only in Mode A. Shaded periods come from `format.CUR_WEEKS`: the current period is the last N weeks to the as-of week; the base period is the same weeks 52 weeks earlier, or the previous N weeks for `L4W_VS_PP`.

**Formatting** (`sr_ui/format.py`). It matches `render.format_fact` (L8) character for character, so the numbers in the app and in the brief read the same.

```python
CMP_TEXT = {"L4W_VS_YA": "last 4 weeks vs year ago", "L4W_VS_PP": "last 4 weeks vs previous 4 weeks",
            "L12W_VS_YA": "last 12 weeks vs year ago", "L52W_VS_YA": "last 52 weeks vs year ago"}
CUR_WEEKS = {"L4W_VS_YA": 4, "L4W_VS_PP": 4, "L12W_VS_YA": 12, "L52W_VS_YA": 52}
LABEL_CHIP = {"MARKET_MOVE": "✓ Market move", "MIXED": "◐ Mixed signals", "POSSIBLE_DATA_EFFECT": "⚠ Possible data effect"}
RUN_CHIP = {"SUCCEEDED": "✓ Succeeded", "RUNNING": "… Running", "FAILED": "✕ Failed", "SKIPPED": "– Skipped"}

def pct(share: float | None, d: int = 1) -> str: ...          # 0.2341 -> "23.4%"; None -> "–"
def pts(points: float | None, d: int = 2) -> str: ...         # -0.8412 -> "-0.84 pts" (input already in points)
def money(x: float | None, currency: str) -> str: ...         # -1834220.5 -> "-INR 1.8M"; K, M, B with one decimal
def signed_pct(ratio: float | None, d: int = 1) -> str: ...   # 0.031 -> "+3.1%"
def confidence(c: float | None) -> str: ...                   # >= 0.8 "High", >= 0.5 "Medium", else "Low", with the value
def name(real: str, kind: str) -> str: ...                    # alias from data.aliases() when DISPLAY_ALIAS is true
def headline(shift: dict, markets: dict[str, str]) -> str: ...  # "<Brand> lost 0.84 pts in <Market>, last 4 weeks vs year ago"
```

The display currency comes from the `CURRENCY` setting (L1). Tests: T-UI-01 checks `bridge_frame` (the terms add up to the total; Mode D gives one row). T-UI-02 checks that `format.py` and `render.format_fact` give identical strings for 50 sample values.

## L12 Security: roles, grants, row access, judge role

The model in one sentence: analysts and judges never touch a table. They reach data only through three governed surfaces: the read-only app, which shows only the configured scope; the semantic view; and the five tool procedures. The last two read `SEM` views that carry a row access policy. Builders and the pipeline use separate roles that viewers cannot assume.

| Role | Used by | Can | Cannot |
| --- | --- | --- | --- |
| `SR_ADMIN` | Team admin | Own the database and schemas, grant, everything below | — |
| `SR_DEV` | Builders and CoCo sessions | Create objects in every schema, use ML and Cortex, deploy as `SR_APP` or `SR_UI`, see all rows | Grant (that stays with `SR_ADMIN`) |
| `SR_APP` | Tasks, alert, stream, admin app | Read `SRC` and `CORE`, write `APP`, `ML` and `OPS`, refresh dynamic tables, run tasks and alerts, send email | Read `SEM` views as an analyst |
| `SR_UI` | Owner of the read-only app | `SELECT` on `APP` and on the `OPS` logs, call `SP_WHAT_IF` | Write anything, run tasks, change settings |
| `SR_ANALYST` | Analysts in CoWork and the read-only app | Use the agent, semantic view, search service, tool procedures and read-only app, within their entitlement | Read any table directly, write anything |
| `SR_JUDGE` | Judges | Inherits `SR_ANALYST`, nothing more | Same as `SR_ANALYST` |

**Grants** — `sql/70_sec/701_grants.sql`. The account-level block needs ACCOUNTADMIN, so the organizers may run it. Each `ON ALL … IN SCHEMA` line is repeated with `ON FUTURE … IN SCHEMA`, so objects created later inherit the grant. Snowflake grants one object per statement, so the per-table lines are written out in the file.

```sql
-- Block 1: roles
USE ROLE SECURITYADMIN;
CREATE ROLE IF NOT EXISTS SR_UI;                 -- owns the read-only app
GRANT ROLE SR_APP     TO ROLE SR_DEV;            -- builders can act as the runtime role
GRANT ROLE SR_UI      TO ROLE SR_DEV;            -- builders deploy the read-only app as SR_UI
GRANT ROLE SR_UI      TO ROLE SR_ADMIN;
GRANT ROLE SR_ANALYST TO ROLE SR_JUDGE;          -- judges are analysts, read-only

-- Block 2: account level
USE ROLE ACCOUNTADMIN;
GRANT EXECUTE TASK  ON ACCOUNT TO ROLE SR_APP;
GRANT EXECUTE ALERT ON ACCOUNT TO ROLE SR_APP;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE SR_DEV;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE SR_APP;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE SR_ANALYST;
-- optional: GRANT READ SESSION ON ACCOUNT TO ROLE SR_UI;   -- only to show the viewer's name in the app

-- Block 3: warehouses (SYSADMIN owns them)
USE ROLE SYSADMIN;
GRANT USAGE ON WAREHOUSE SR_WH_XS TO ROLE SR_APP;
GRANT USAGE ON WAREHOUSE SR_WH_M  TO ROLE SR_APP;
GRANT USAGE ON WAREHOUSE SR_WH_XS TO ROLE SR_UI;
GRANT USAGE ON WAREHOUSE SR_WH_XS TO ROLE SR_ANALYST;   -- the agent's tools run on SR_WH_XS as the caller

-- Block 4: builders
USE ROLE SR_ADMIN;
GRANT USAGE ON DATABASE SR_DB TO ROLE SR_DEV;
GRANT ALL ON ALL SCHEMAS IN DATABASE SR_DB TO ROLE SR_DEV;   -- every CREATE privilege, but not ML class instances
GRANT CREATE SNOWFLAKE.ML.ANOMALY_DETECTION ON SCHEMA SR_DB.ML TO ROLE SR_DEV;
GRANT CREATE SNOWFLAKE.ML.TOP_INSIGHTS      ON SCHEMA SR_DB.ML TO ROLE SR_DEV;

-- Block 5: runtime (SR_APP)
GRANT USAGE ON DATABASE SR_DB TO ROLE SR_APP;
GRANT USAGE ON SCHEMA SR_DB.SRC TO ROLE SR_APP;   -- likewise CORE, ML, APP, OPS
GRANT SELECT ON ALL VIEWS IN SCHEMA SR_DB.SRC TO ROLE SR_APP;
GRANT SELECT, OPERATE ON ALL DYNAMIC TABLES IN SCHEMA SR_DB.CORE TO ROLE SR_APP;   -- OPERATE: replay refresh
GRANT SELECT ON ALL VIEWS IN SCHEMA SR_DB.CORE TO ROLE SR_APP;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA SR_DB.APP TO ROLE SR_APP;  -- likewise ML, OPS
GRANT SELECT ON ALL VIEWS IN SCHEMA SR_DB.APP TO ROLE SR_APP;
GRANT USAGE ON ALL PROCEDURES IN SCHEMA SR_DB.APP TO ROLE SR_APP;
GRANT USAGE ON ALL FUNCTIONS  IN SCHEMA SR_DB.OPS TO ROLE SR_APP;
GRANT READ ON STAGE SR_DB.APP.CODE TO ROLE SR_APP;
GRANT CREATE TABLE ON SCHEMA SR_DB.ML TO ROLE SR_APP;                      -- temporary tables in the ML procedures
GRANT CREATE SNOWFLAKE.ML.ANOMALY_DETECTION ON SCHEMA SR_DB.ML TO ROLE SR_APP;
GRANT CREATE SNOWFLAKE.ML.TOP_INSIGHTS      ON SCHEMA SR_DB.ML TO ROLE SR_APP;
GRANT CREATE STREAM, CREATE TASK, CREATE ALERT ON SCHEMA SR_DB.OPS TO ROLE SR_APP;
GRANT CREATE STREAMLIT, CREATE STAGE ON SCHEMA SR_DB.APP TO ROLE SR_APP;   -- owns the admin app
GRANT USAGE ON INTEGRATION SR_EMAIL_INT TO ROLE SR_APP;                    -- as in 603

-- Block 6: read-only app owner (SR_UI)
GRANT USAGE ON DATABASE SR_DB TO ROLE SR_UI;
GRANT USAGE ON SCHEMA SR_DB.APP TO ROLE SR_UI;    -- likewise OPS, SRC
GRANT SELECT ON ALL TABLES IN SCHEMA SR_DB.APP TO ROLE SR_UI;
GRANT SELECT ON ALL VIEWS  IN SCHEMA SR_DB.APP TO ROLE SR_UI;              -- V_UI_SHARE_WEEK, V_ALIAS
GRANT SELECT ON VIEW SR_DB.SRC.V_SRC_MARKET TO ROLE SR_UI;
GRANT SELECT ON TABLE SR_DB.OPS.RUN_LOG TO ROLE SR_UI;  -- likewise STEP_LOG, EVAL_RESULT, RECON_RESULT, COCO_LOG, SETTINGS, TEST_RESULT
GRANT SELECT ON VIEW SR_DB.OPS.V_RUN_COST TO ROLE SR_UI;
GRANT USAGE ON PROCEDURE SR_DB.APP.SP_WHAT_IF(VARCHAR, VARCHAR, VARCHAR) TO ROLE SR_UI;
GRANT CREATE STREAMLIT, CREATE STAGE ON SCHEMA SR_DB.APP TO ROLE SR_UI;

-- Block 7: analysts (judges inherit)
GRANT USAGE ON DATABASE SR_DB TO ROLE SR_ANALYST;
GRANT USAGE ON SCHEMA SR_DB.SEM TO ROLE SR_ANALYST;
GRANT USAGE ON SCHEMA SR_DB.APP TO ROLE SR_ANALYST;                        -- tool procedures and the app live here
GRANT SELECT ON SEMANTIC VIEW SR_DB.SEM.SV_SHARE TO ROLE SR_ANALYST;
GRANT SELECT ON ALL VIEWS IN SCHEMA SR_DB.SEM TO ROLE SR_ANALYST;          -- V_SEM_* and V_TOOL_*, all row-filtered
GRANT USAGE ON CORTEX SEARCH SERVICE SR_DB.SEM.CSS_METHOD TO ROLE SR_ANALYST;
GRANT USAGE ON PROCEDURE SR_DB.APP.TOOL_GET_SHARE_BRIDGE(VARCHAR, VARCHAR, VARCHAR) TO ROLE SR_ANALYST;
GRANT USAGE ON PROCEDURE SR_DB.APP.TOOL_CHECK_ARTEFACT(VARCHAR, VARCHAR, VARCHAR) TO ROLE SR_ANALYST;
GRANT USAGE ON PROCEDURE SR_DB.APP.TOOL_SHARE_FLOW(VARCHAR, VARCHAR, VARCHAR) TO ROLE SR_ANALYST;
GRANT USAGE ON PROCEDURE SR_DB.APP.TOOL_WHAT_IF(VARCHAR, VARCHAR, VARCHAR, VARCHAR) TO ROLE SR_ANALYST;
GRANT USAGE ON PROCEDURE SR_DB.APP.TOOL_LATEST_BRIEF(VARCHAR) TO ROLE SR_ANALYST;
-- agent usage is granted in 505_cowork.sql
```

The `60_ops` files start with `USE ROLE SR_APP;`, so `SR_APP` owns the stream, the tasks and the alert, and tasks run as their owner. Procedures may stay owned by `SR_DEV`; they run with caller's rights, so ownership does not change what they can do.

**Tool views** — added to `sql/50_sem/501_v_sem_views.sql`. The tool procedures (L10) read only these, so callers need no table grants and the row policy always applies. Views read their sources with the view owner's privileges.

```sql
CREATE OR REPLACE VIEW SR_DB.SEM.V_TOOL_BRIDGE AS          -- every brand, not only ranked shifts
SELECT c.AS_OF_WEEK, c.CMP_CODE, c.MARKET_ID, m.MARKET_NAME, c.CATEGORY, c.MANUFACTURER, c.BRAND,
       b.MODE, b.STATUS, b.SH1, b.SH0, b.D_SHARE, b.DIST_PTS, b.VELOCITY_PTS, b.PRICE_PTS, b.PROMO_PTS,
       b.DS1, b.DS0, b.PRI1, b.PRI0
FROM SR_DB.CORE.DT_SHARE_COMPARE c
JOIN SR_DB.APP.V_BRIDGE_ALL b
  ON b.CMP_CODE = c.CMP_CODE AND b.MARKET_ID = c.MARKET_ID AND b.CATEGORY = c.CATEGORY AND b.BRAND = c.BRAND
JOIN SR_DB.SRC.V_SRC_MARKET m ON m.MARKET_ID = c.MARKET_ID;

CREATE OR REPLACE VIEW SR_DB.SEM.V_TOOL_WHERE AS           -- retailer split exists for ranked shifts only
SELECT r.CMP_CODE, r.MARKET_ID, r.CATEGORY, r.BRAND, w.METHOD, w.RANK_NO, w.CONTRIBUTOR, w.PERF_PTS, w.MIX_PTS, w.TOTAL_PTS
FROM SR_DB.APP.SHIFT_WHERE w
JOIN SR_DB.APP.SHIFT_RANKED r ON r.RUN_ID = w.RUN_ID AND r.SHIFT_ID = w.SHIFT_ID
WHERE w.RUN_ID = (SELECT RUN_ID FROM SR_DB.OPS.RUN_LOG WHERE STATUS = 'SUCCEEDED' ORDER BY STARTED_AT DESC LIMIT 1);

CREATE OR REPLACE VIEW SR_DB.SEM.V_TOOL_ARTEFACT AS
SELECT a.CMP_CODE, a.MARKET_ID, m.MARKET_NAME, a.CATEGORY, a.BRAND, a.RULE_ID, a.SEVERITY, a.EVIDENCE
FROM SR_DB.APP.ARTEFACT_CHECK a
JOIN SR_DB.SRC.V_SRC_MARKET m ON m.MARKET_ID = a.MARKET_ID
WHERE a.RUN_ID = (SELECT RUN_ID FROM SR_DB.OPS.RUN_LOG WHERE STATUS = 'SUCCEEDED' ORDER BY STARTED_AT DESC LIMIT 1);

CREATE OR REPLACE VIEW SR_DB.SEM.V_TOOL_FLOW AS            -- same allocation as SP_FLOW, for every market
WITH d AS (
  SELECT CMP_CODE, MARKET_ID, CATEGORY, BRAND, D_SHARE FROM SR_DB.CORE.DT_SHARE_COMPARE WHERE D_SHARE IS NOT NULL
), g AS (
  SELECT CMP_CODE, MARKET_ID, CATEGORY, SUM(IFF(D_SHARE > 0, D_SHARE, 0)) AS GAIN_TOTAL FROM d GROUP BY CMP_CODE, MARKET_ID, CATEGORY
)
SELECT l.CMP_CODE, l.MARKET_ID, l.CATEGORY, l.BRAND AS FROM_BRAND, w.BRAND AS TO_BRAND,
       100 * (-l.D_SHARE) * w.D_SHARE / NULLIF(g.GAIN_TOTAL, 0) AS FLOW_PTS
FROM d l
JOIN d w ON w.CMP_CODE = l.CMP_CODE AND w.MARKET_ID = l.MARKET_ID AND w.CATEGORY = l.CATEGORY AND w.D_SHARE > 0
JOIN g   ON g.CMP_CODE = l.CMP_CODE AND g.MARKET_ID = l.MARKET_ID AND g.CATEGORY = l.CATEGORY
WHERE l.D_SHARE < 0;

CREATE OR REPLACE VIEW SR_DB.SEM.V_TOOL_BRIEF AS
SELECT b.BRIEF_ID, SPLIT_PART(b.SCOPE_KEY, '|', 1) AS CATEGORY, SPLIT_PART(b.SCOPE_KEY, '|', 2) AS MARKET_ID,
       b.AS_OF_WEEK, b.HEADLINE, b.BODY_MD, p.PACK, b.PUBLISHED_AT
FROM SR_DB.APP.BRIEF b
JOIN SR_DB.APP.FACT_PACK p ON p.BRIEF_ID = b.BRIEF_ID
WHERE b.STATUS = 'PUBLISHED';
```

**Row access** — `sql/70_sec/702_row_access.sql`. Entitlements name a user or a role, plus a category and a market; `'*'` means all. Granting a parent market also grants its child retailers. Row access policies need Enterprise Edition or higher. Without it, the agent path rests on the object grants alone, and only the configured scope is ever computed.

```sql
CREATE TABLE IF NOT EXISTS SR_DB.OPS.ENTITLEMENT (
  PRINCIPAL_TYPE VARCHAR(4) NOT NULL,      -- USER | ROLE
  PRINCIPAL      VARCHAR    NOT NULL,      -- upper-case user or role name
  CATEGORY       VARCHAR    NOT NULL,      -- category or '*'
  MARKET_ID      VARCHAR    NOT NULL,      -- market or '*'; child markets are stored as their own rows
  GRANTED_AT     TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
  NOTE           VARCHAR,
  PRIMARY KEY (PRINCIPAL_TYPE, PRINCIPAL, CATEGORY, MARKET_ID)
);

CREATE OR REPLACE PROCEDURE SR_DB.OPS.SP_ENTITLE(P_TYPE VARCHAR, P_PRINCIPAL VARCHAR, P_CATEGORY VARCHAR, P_MARKET_ID VARCHAR)
RETURNS NUMBER
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
BEGIN
  MERGE INTO SR_DB.OPS.ENTITLEMENT t
  USING (
    SELECT UPPER(:P_TYPE) AS PRINCIPAL_TYPE, UPPER(:P_PRINCIPAL) AS PRINCIPAL, :P_CATEGORY AS CATEGORY, :P_MARKET_ID AS MARKET_ID
    UNION
    SELECT UPPER(:P_TYPE), UPPER(:P_PRINCIPAL), :P_CATEGORY, m.MARKET_ID
    FROM SR_DB.SRC.V_SRC_MARKET m WHERE m.PARENT_MARKET_ID = :P_MARKET_ID      -- a parent brings its children
  ) s
  ON t.PRINCIPAL_TYPE = s.PRINCIPAL_TYPE AND t.PRINCIPAL = s.PRINCIPAL AND t.CATEGORY = s.CATEGORY AND t.MARKET_ID = s.MARKET_ID
  WHEN NOT MATCHED THEN INSERT (PRINCIPAL_TYPE, PRINCIPAL, CATEGORY, MARKET_ID)
                        VALUES (s.PRINCIPAL_TYPE, s.PRINCIPAL, s.CATEGORY, s.MARKET_ID);
  RETURN SQLROWCOUNT;
END;
$$;

CREATE ROW ACCESS POLICY IF NOT EXISTS SR_DB.OPS.RAP_ENTITLED
  AS (P_MARKET_ID VARCHAR, P_CATEGORY VARCHAR) RETURNS BOOLEAN ->
    IS_ROLE_IN_SESSION('SR_DEV')                                    -- builders and admins see everything
    OR EXISTS (
      SELECT 1 FROM SR_DB.OPS.ENTITLEMENT e
      WHERE ((e.PRINCIPAL_TYPE = 'USER' AND e.PRINCIPAL = CURRENT_USER())
          OR (e.PRINCIPAL_TYPE = 'ROLE' AND IS_ROLE_IN_SESSION(e.PRINCIPAL)))
        AND e.CATEGORY  IN (P_CATEGORY, '*')
        AND e.MARKET_ID IN (P_MARKET_ID, '*'));
-- To change the body later: ALTER ROW ACCESS POLICY SR_DB.OPS.RAP_ENTITLED SET BODY -> ...

-- Attach to every governed surface. CREATE OR REPLACE VIEW drops a policy, so this file reruns after any 50_sem change.
ALTER VIEW SR_DB.SEM.V_SEM_SHARE_GRID DROP ALL ROW ACCESS POLICIES;
ALTER VIEW SR_DB.SEM.V_SEM_SHARE_GRID ADD ROW ACCESS POLICY SR_DB.OPS.RAP_ENTITLED ON (MARKET_ID, CATEGORY);
-- the same two lines for V_SEM_SHARE_CHANGE, V_TOOL_BRIDGE, V_TOOL_WHERE, V_TOOL_ARTEFACT, V_TOOL_FLOW and V_TOOL_BRIEF
-- (V_TOOL_BRIEF's MARKET_ID is the parent market)

-- Demo entitlement: analysts, and so judges, see the demo category in the parent market and its retailers
CALL SR_DB.OPS.SP_ENTITLE('ROLE', 'SR_ANALYST', '<category>', '<parent market_id>');
```

Analysts and judges are not limited per user inside the read-only app. It runs as `SR_UI`, and only the configured scope is ever computed. Per-viewer filtering there would need `READ SESSION` on `SR_UI` (L11) and is not in scope for the sprint.

**App usage** — `sql/70_sec/703_app_usage.sql`, run after both apps are deployed:

```sql
USE ROLE SR_ADMIN;
GRANT USAGE ON STREAMLIT SR_DB.APP.SHARE_RADAR       TO ROLE SR_ANALYST;   -- judges inherit it
GRANT USAGE ON STREAMLIT SR_DB.APP.SHARE_RADAR_ADMIN TO ROLE SR_DEV;
```

**Judge accounts.** The organizers create the users; then, as SECURITYADMIN:

```sql
GRANT ROLE SR_JUDGE TO USER <judge_user>;
ALTER USER <judge_user> SET DEFAULT_ROLE = SR_JUDGE, DEFAULT_SECONDARY_ROLES = ();
```

No secondary roles means a judge's session holds only `SR_JUDGE`, so what a judge sees matches what the tests check. Tests that switch roles start with `USE SECONDARY ROLES NONE;` for the same reason.

**Threats and controls**

| Threat | Control | Check |
| --- | --- | --- |
| An analyst sees markets outside their entitlement | Row policy on every `SEM` surface; no table grants to analysts | T-SEC-02 |
| A judge or analyst changes data, settings or runs | No write privilege on any analyst-side role; the admin app is granted only to `SR_DEV` | T-SEC-01 |
| Rerunning a view script drops its policy without anyone noticing | `702` reattaches the policy (`DROP ALL` then `ADD`); `deploy_all.sh` always runs it after `50_sem` | T-SEC-03 |
| LLM text injects markup or invented numbers | `render_html` escapes LLM text; `st.html` sanitises; validator V03 rejects bare digits | T-NAR-01..05 |
| The agent states a number no tool returned | Numbers come only from tools; response instructions; the golden set checks values and tool routes | Golden set |
| Client or brand names show in a recording | `DISPLAY_ALIAS = true` for the demo video (L11 aliases) | Dry run |
| A brief is emailed to the wrong people | The integration's `ALLOWED_RECIPIENTS`; `save_setting` validates `NOTIFY_EMAILS` against it | Manual |
| Credentials end up in the repo | The `sr` connection lives in each person's `~/.snowflake/config.toml`; `.gitignore` covers `.snowflake/`, `*.p8`, `*.pem`, `.env` | Review subagent |
| Data leaves Snowflake | Cortex functions run inside Snowflake; cross-region inference, if the chosen model needs it, is an account decision recorded in `docs/decisions.md` | Smoke test |
| Cost runs away | `MAX_CREDITS_PER_RUN`, XS warehouse by default, 60-second auto-suspend (L14) | Trust page |

## L13 Error matrix

Every failure has one detector, one response, one visible symptom and one test. When a critical step fails, the run stops and the last good brief stays on screen. When an optional step fails, the run carries on with less, and the brief and app say what is missing. Nothing fails silently, and no partial number is ever shown as a whole one.

| ID | Failure | Detected by | System response | What people see | Test |
| --- | --- | --- | --- | --- | --- |
| E01 | No facts for the as-of week (feed late, wrong `AS_OF_WEEK_END`) | `SP_CAPABILITY_CHECK` raises `NO_DATA` when the latest adapter week is earlier than `AS_OF_WEEK_END` | Run `FAILED`, `ERROR_MSG = 'NO_DATA: no facts for <week>'` | Radar keeps the last good run, with a red banner: "This week's data has not arrived" | T-SRC-03 |
| E02 | History too short for a comparison (fewer than 56 weeks for year-ago, 104 for L52W) | `DT_SHARE_COMPARE` rows with NULL base category totals | The comparison yields no candidates; `DETECT` logs `WARN` naming it and the weeks available | Radar note: "Year-ago comparisons need 56 weeks; N available" | T-CORE-04 |
| E03 | A dynamic table refresh fails (source renamed, adapter broken, quota) | Refresh history state `FAILED` (L14 health view) | No stream data, so no run starts | Trust page "Data refreshed" tile turns red with the error; fix the adapter (SR-003) | T-SRC-01 |
| E04 | Optional columns missing (no %ACV, no base sales) | `OPS.CAPABILITY.MAX_BRIDGE_MODE` below A | Bridge runs in mode B, C or D; `RUN_LOG.BRIDGE_MODE` records it | Shift detail: "Mode C: no price or promo split" or "Mode D: share change only"; the brief omits missing terms | T-BR-04 |
| E05 | A row's factor is zero or missing (new listing, delisting, zero TDP) | Bridge `STATUS` `NEW`, `EXIT` or `NO_DATA`, or a row mode below the run mode | NULL terms for that row; `NOTE` explains; still ranked on share change | "New listing" or "Delisted" chip instead of the bridge | T-BR-03 |
| E06 | Gap, feed drop, restatement, recode, spike or coverage change | Artefact rules R1–R6 | Label `POSSIBLE_DATA_EFFECT` or `MIXED`; `ART_FACTOR` lowers the score; HIGH means held back | "Held back for data checks", with the rule and its evidence | T-ART-01..05 |
| E07 | Anomaly detection fails, or a series has fewer than 12 weeks | Exception in `SP_ML_SHARE_ANOMALY`; `on_error: skip` for short series | Step `WARN`; confidence from z only | Nothing missing; the run log shows `WARN` | T-ML-01 |
| E08 | TOP\_INSIGHTS fails | Exception in `SP_WHERE_INSIGHTS` | Step `WARN`; the exact retailer split still stands | Shift detail shows the retailer split only | T-WH-02 |
| E09 | Credit estimate passes `MAX_CREDITS_PER_RUN` | `estimate_credits` before the ML and TOP\_INSIGHTS steps | Those steps `SKIPPED` with message "credit cap" | The run log shows the skip | T-E2E-04 |
| E10 | LLM call fails (model not enabled, timeout, quota) | Exception from `complete()` | Attempt 2 with `LLM_FALLBACK_MODEL`, then the template; `GENERATOR` records which | Brief chip "Template brief"; the numbers are identical | T-NAR-04, T-E2E-02 |
| E11 | LLM output fails validation | `validate_brief` returns violations | Retry with "Fix these problems", then the template; `VIOLATIONS` stored | Brief page lists the violations under "Checks" | T-NAR-01..03 |
| E12 | Brief writer cannot start (`sr_lib.zip` missing, package resolution) | `CALL SP_WRITE_BRIEF` raises before Python runs | Run `FAILED` (step 13 is critical) | Red banner "Brief not written"; the last good brief stays | T-E2E-01 after every deploy |
| E13 | Email send fails | Exception inside `SP_NOTIFY_NEW_BRIEFS` | `NOTIFY_ATTEMPTS + 1`, `NOTIFY_LOG` row `FAILED`; retried at the next alert evaluation, at most 3 attempts | Brief page: "Email not sent (3 attempts)"; the admin calls `SP_NOTIFY_NEW_BRIEFS()` after fixing it | Manual |
| E14 | A tool cannot resolve a name, the caller is not entitled, or the tool errors | `SP_RESOLVE` status; the row policy hides rows the caller may not see; `EXCEPTION` handler | JSON error: `NOT_FOUND`, `AMBIGUOUS`, `NO_DATA`, `BAD_INPUT` or `TOOL_FAILED`; never a partial number | The agent says it cannot find it and offers candidates, or asks which one; it never reveals whether hidden data exists | T-TOOL-05, T-SEC-02 |
| E15 | Cortex Analyst cannot answer, or its SQL fails | Analyst returns no SQL, or an error | The agent says so and suggests a supported question | A plain "can't answer that", no estimate | Golden set, unsupported questions |
| E16 | Duplicate or overlapping run | `OPEN` finds a `SUCCEEDED` run for the same week and scope (not forced), or a `RUNNING` run younger than 30 minutes | `RUN_LOG` row `SKIPPED` with the reason; replay returns `BUSY`; admin buttons disabled | Grey note: "Already ran" or "Run in progress" | T-E2E-03 |
| E17 | Task, stream or alert stops (task suspended after repeated failures, stale stream, alert suspended) | L14 health view: task state and last run, stream staleness, alert state | Nothing runs until fixed: `ALTER TASK … RESUME`, or recreate the stream and rerun the week | Trust page "Pipeline health" turns red | Dry run |
| E18 | An admin action fails (`EXECUTE TASK` error, task run `FAILED`) | `start_task` exception; `task_last_run` state `FAILED` | The panel stops polling and shows the error text | Error box in the admin app | Manual |

**How a run handles failure** (`python/sr_lib/run.py`). Step procedures do not catch their own errors. `run_week` catches each step's error. A critical step closes the run as `FAILED`; an optional one logs `WARN` and carries on. An outer handler makes sure no run is left `RUNNING`, and the 30-minute busy window stops a crashed run from blocking replay for ever. `log_step` gains a `started_at` keyword argument.

```python
import json
from datetime import datetime, timezone
from snowflake.snowpark import Session
from snowflake.snowpark.exceptions import SnowparkSQLException

OPTIONAL_COST_STEPS = {"ML_ANOMALY", "TOP_INSIGHTS"}

def run_week(session: Session, trigger_type: str = "MANUAL", force: bool = False) -> str:
    run_id = open_run(session, trigger_type, force)           # None: a SKIPPED row is already written (E16)
    if run_id is None:
        return "SKIPPED"
    try:
        cap = float(session.sql("SELECT SR_DB.OPS.CFG('MAX_CREDITS_PER_RUN')::FLOAT").collect()[0][0])
        for step_no, name, sql, critical in STEPS:
            started = datetime.now(timezone.utc)
            if name in OPTIONAL_COST_STEPS and estimate_credits(session, run_id) > cap:      # E09
                log_step(session, run_id, step_no, name, "SKIPPED", None, "credit cap", started_at=started)
                continue
            try:
                result = session.sql(sql.format(run=run_id)).collect()[0][0]
                rows = result if isinstance(result, int) else None   # SP_CAPABILITY_CHECK returns 'OK'
                log_step(session, run_id, step_no, name, "OK", rows, None, started_at=started)
            except SnowparkSQLException as e:
                msg = f"{name}: {e.message}"[:2000]
                log_step(session, run_id, step_no, name, "FAILED" if critical else "WARN", None, msg, started_at=started)
                if critical:
                    close_run(session, run_id, "FAILED", msg)
                    return run_id
        close_run(session, run_id, "SUCCEEDED", None)
    except Exception as e:                                       # a bug in this file, not in a step
        close_run(session, run_id, "FAILED", f"INTERNAL: {e}"[:2000])
    return run_id
```

**Tool error contract.** Every `TOOL_*` procedure returns either its L10 payload or one of these objects, so the agent never has to parse an exception:

| `error` | When | The agent should |
| --- | --- | --- |
| `NOT_FOUND` | No entitled brand or market within the matching rules | Say it cannot find it, and offer the `candidates` |
| `AMBIGUOUS` | Two or more names tie for the best match | Ask which of the `candidates` the user means |
| `NO_DATA` | Names resolve, but there is no row for that comparison (for example, short history) | Say the comparison isn't available, and suggest another |
| `BAD_INPUT` | Unknown comparison code or lever | Restate the allowed values |
| `TOOL_FAILED` | Any other exception (`SQLCODE` and the first 300 characters of `SQLERRM`) | Say the tool failed, and give no numbers |

`APP.SP_RESOLVE(P_KIND VARCHAR, P_TEXT VARCHAR, P_CMP_CODE VARCHAR) RETURNS VARIANT` resolves names for all tools. Its candidates are the distinct brands (or market names and IDs) in `SEM.V_TOOL_BRIDGE` for that comparison, so the row policy already applies. The score is 0 for an exact case-insensitive match on name or ID; 1 when the name contains the input and the input has at least 3 characters; otherwise `EDITDISTANCE(UPPER(name), UPPER(input))`. If the best score is 2 or less and unique, it returns `{"status": "OK", "value": …, "name": …}`. If the best score is 2 or less but tied, it returns `{"status": "AMBIGUOUS", "what": …, "candidates": […]}`. Otherwise it returns `{"status": "NOT_FOUND", "what": …, "input": …, "candidates": [the three closest names]}`.

```sql
-- The pattern every TOOL_* procedure follows (sql/40_app/414_tool_procs.sql)
CREATE OR REPLACE PROCEDURE SR_DB.APP.TOOL_SHARE_FLOW(P_BRAND VARCHAR, P_MARKET VARCHAR, P_CMP_CODE VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  cmp VARCHAR DEFAULT COALESCE(NULLIF(UPPER(TRIM(P_CMP_CODE)), ''), 'L4W_VS_YA');
  b   VARIANT;
  m   VARIANT;
  out VARIANT;
BEGIN
  IF (cmp NOT IN ('L4W_VS_YA', 'L4W_VS_PP', 'L12W_VS_YA', 'L52W_VS_YA')) THEN
    RETURN TO_JSON(OBJECT_CONSTRUCT('error', 'BAD_INPUT', 'detail', 'Unknown comparison ' || cmp));
  END IF;
  CALL SR_DB.APP.SP_RESOLVE('BRAND', :P_BRAND, :cmp) INTO :b;
  IF (GET(b, 'status')::VARCHAR <> 'OK') THEN
    RETURN TO_JSON(OBJECT_INSERT(b, 'error', GET(b, 'status')));
  END IF;
  CALL SR_DB.APP.SP_RESOLVE('MARKET', :P_MARKET, :cmp) INTO :m;
  IF (GET(m, 'status')::VARCHAR <> 'OK') THEN
    RETURN TO_JSON(OBJECT_INSERT(m, 'error', GET(m, 'status')));
  END IF;
  -- main query: the L10 payload, built with OBJECT_CONSTRUCT from SR_DB.SEM.V_TOOL_FLOW only, INTO :out
  IF (out IS NULL) THEN
    RETURN TO_JSON(OBJECT_CONSTRUCT('error', 'NO_DATA', 'detail', 'No share change for this brand, market and comparison'));
  END IF;
  RETURN TO_JSON(out);
EXCEPTION
  WHEN OTHER THEN
    RETURN TO_JSON(OBJECT_CONSTRUCT('error', 'TOOL_FAILED', 'sqlcode', SQLCODE, 'detail', LEFT(SQLERRM, 300)));
END;
$$;
```

`SP_CAPABILITY_CHECK` (L3) gains the E01 check as its last statement. It declares `no_data EXCEPTION (-20001, 'NO_DATA: no facts for the as-of week')` and raises it when `MAX(WEEK_END_DATE)` in `SRC.V_SRC_FACT_WEEKLY` is earlier than `AS_OF_WEEK_END`.

**What the apps show**

| Situation | Read-only app | Admin app adds |
| --- | --- | --- |
| The latest run for the current week `FAILED` | Red banner with the failed step and a short reason; the last good run stays on screen | The full `ERROR_MSG` and **Rerun this week** |
| The latest run was `SKIPPED` | Nothing, because this is normal | Grey note with the skip reason |
| A section's query fails | "Couldn't load this section" with a retry button; never a stack trace | The Snowflake message, first 300 characters |
| A run is in progress | "Updating…" next to the week | Progress panel; buttons disabled |

## L14 Observability and cost

The Trust page answers three questions at any moment: did the last run work, what did it cost, and is the pipeline healthy. Run-time facts go into our own `OPS` tables as they happen. Snowflake's account usage views supply exact costs later, and a snapshot procedure copies them in. Everything here is in `sql/60_ops/606_observability.sql` unless noted.

| Signal | Stored in | Written by | Delay | Shown on |
| --- | --- | --- | --- | --- |
| Run status, counts, bridge mode, credit estimate | `OPS.RUN_LOG` | `run_week` | Live | Radar header, Trust |
| Step status, timing, rows, message | `OPS.STEP_LOG` | `run_week` | Live | Admin progress panel, Trust step timeline |
| Query tag on every pipeline query (format in L1) | Query history | `run_week` sets it before each `CALL`; SQL steps repeat it | Live | Cost queries below |
| LLM tokens per brief | `APP.BRIEF.TOKENS_IN`, `TOKENS_OUT` | `SP_WRITE_BRIEF` with `COUNT_TOKENS` | Live | Trust |
| Email delivery | `OPS.NOTIFY_LOG` | `SP_NOTIFY_NEW_BRIEFS` | Live | Brief page |
| Golden set, reconciliation | `OPS.EVAL_RESULT`, `OPS.RECON_RESULT` | Eval runner (T3), SR-013 | Per check | Trust |
| Pipeline health | `OPS.HEALTH_LOG` | `SP_HEALTH_CHECK`: hourly task, and after each run | Up to 1 hour | Trust "Pipeline health" |
| Exact costs by day and by run | `OPS.COST_DAILY`, `OPS.COST_RUN` | `SP_COST_SNAPSHOT`, run by hand | 1 to 8 hours | Trust "Cost" |
| CoCo usage | `OPS.COCO_LOG`, plus `COST_DAILY` source `COCO` | Stop hook, then flush (T6); snapshot | At each flush; up to 1 hour | Trust "Built with CoCo" |

**Credit estimate during a run.** The estimate guards `MAX_CREDITS_PER_RUN` (E09) and fills `RUN_LOG.CREDITS_EST`. It reads the run's own session history, so it needs no extra privilege, and it counts execution time at the standard warehouse rates. It overstates a little, because it ignores concurrency, which is the safe side for a cap. If the account uses Gen2 warehouses, set the rates from that account's price sheet. AI tokens are billed separately and are reported, not estimated.

```python
# python/sr_lib/run.py
CREDITS_PER_HOUR = {"X-Small": 1, "Small": 2, "Medium": 4, "Large": 8}

def estimate_credits(session: Session, run_id: str) -> float:
    rows = session.sql(
        """SELECT WAREHOUSE_SIZE, SUM(EXECUTION_TIME) / 1000 / 3600 AS HOURS
           FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION(RESULT_LIMIT => 10000))
           WHERE QUERY_TAG LIKE ? AND WAREHOUSE_SIZE IS NOT NULL
           GROUP BY WAREHOUSE_SIZE""", params=[f"SR|run={run_id}|%"]).collect()
    return round(sum(CREDITS_PER_HOUR.get(r["WAREHOUSE_SIZE"], 4) * float(r["HOURS"]) for r in rows), 4)
```

**Pipeline health** (E03, E17). Health checks need `SHOW`, which runs in the task's own session, not inside the app. So a task writes the results to a table, and the Trust page reads the newest row for each object.

```sql
CREATE TABLE IF NOT EXISTS SR_DB.OPS.HEALTH_LOG (
  CHECKED_AT  TIMESTAMP_LTZ NOT NULL,
  OBJECT_TYPE VARCHAR(16)   NOT NULL,   -- DYNAMIC_TABLE | TASK | TASK_RUN | STREAM | ALERT | RUN
  OBJECT_NAME VARCHAR       NOT NULL,
  STATE       VARCHAR(8)    NOT NULL,   -- OK | WARN | FAILED
  DETAIL      VARIANT
);

CREATE OR REPLACE PROCEDURE SR_DB.OPS.SP_HEALTH_CHECK()
RETURNS NUMBER
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  t TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP();
BEGIN
  DELETE FROM SR_DB.OPS.HEALTH_LOG WHERE CHECKED_AT < DATEADD(day, -14, CURRENT_TIMESTAMP());

  INSERT INTO SR_DB.OPS.HEALTH_LOG                                   -- latest refresh of each dynamic table
  SELECT :t, 'DYNAMIC_TABLE', NAME, IFF(STATE IN ('FAILED', 'UPSTREAM_FAILED'), 'FAILED', 'OK'), OBJECT_CONSTRUCT(*)
  FROM TABLE(SR_DB.INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(NAME_PREFIX => 'SR_DB.CORE.', RESULT_LIMIT => 1000))
  WHERE STATE NOT IN ('SCHEDULED', 'EXECUTING')
  QUALIFY ROW_NUMBER() OVER (PARTITION BY NAME ORDER BY REFRESH_START_TIME DESC) = 1;

  SHOW TASKS IN SCHEMA SR_DB.OPS;                                    -- the triggered and hourly tasks must be started
  INSERT INTO SR_DB.OPS.HEALTH_LOG
  SELECT :t, 'TASK', "name", IFF("name" IN ('T_RUN_WEEK', 'T_HEALTH') AND "state" <> 'started', 'FAILED', 'OK'),
         OBJECT_CONSTRUCT('state', "state", 'schedule', "schedule")
  FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));

  INSERT INTO SR_DB.OPS.HEALTH_LOG                                   -- last finished run of each task
  SELECT :t, 'TASK_RUN', NAME, IFF(STATE = 'FAILED', 'WARN', 'OK'),
         OBJECT_CONSTRUCT('state', STATE, 'error', ERROR_MESSAGE, 'completed', COMPLETED_TIME)
  FROM TABLE(SR_DB.INFORMATION_SCHEMA.TASK_HISTORY(RESULT_LIMIT => 1000))
  WHERE SCHEMA_NAME = 'OPS' AND STATE IN ('SUCCEEDED', 'FAILED', 'CANCELLED', 'SKIPPED')
  QUALIFY ROW_NUMBER() OVER (PARTITION BY NAME ORDER BY COMPLETED_TIME DESC) = 1;

  SHOW STREAMS IN SCHEMA SR_DB.OPS;
  INSERT INTO SR_DB.OPS.HEALTH_LOG
  SELECT :t, 'STREAM', "name",
         CASE WHEN "stale"::VARCHAR = 'true' THEN 'FAILED'
              WHEN "stale_after" < DATEADD(day, 2, CURRENT_TIMESTAMP()) THEN 'WARN' ELSE 'OK' END,
         OBJECT_CONSTRUCT('stale', "stale", 'stale_after', "stale_after")
  FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));

  SHOW ALERTS IN SCHEMA SR_DB.OPS;
  INSERT INTO SR_DB.OPS.HEALTH_LOG
  SELECT :t, 'ALERT', "name", IFF("state" <> 'started', 'FAILED', 'OK'), OBJECT_CONSTRUCT('state', "state")
  FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));

  INSERT INTO SR_DB.OPS.HEALTH_LOG                                   -- a weekly product should not go 8 days silent
  SELECT :t, 'RUN', 'LAST_SUCCEEDED',
         IFF(MAX(ENDED_AT) IS NULL OR MAX(ENDED_AT) < DATEADD(day, -8, CURRENT_TIMESTAMP()), 'WARN', 'OK'),
         OBJECT_CONSTRUCT('last_succeeded', MAX(ENDED_AT))
  FROM SR_DB.OPS.RUN_LOG WHERE STATUS = 'SUCCEEDED';
  RETURN 0;
END;
$$;

CREATE OR REPLACE VIEW SR_DB.OPS.V_HEALTH_LATEST AS
SELECT * FROM SR_DB.OPS.HEALTH_LOG
QUALIFY ROW_NUMBER() OVER (PARTITION BY OBJECT_TYPE, OBJECT_NAME ORDER BY CHECKED_AT DESC) = 1;

USE ROLE SR_APP;
CREATE OR REPLACE TASK SR_DB.OPS.T_HEALTH
  WAREHOUSE = SR_WH_XS
  SCHEDULE = 'USING CRON 7 * * * * UTC'
AS
  CALL SR_DB.OPS.SP_HEALTH_CHECK();
ALTER TASK SR_DB.OPS.T_HEALTH RESUME;          -- suspend it after the event
```

The hourly task resumes an XS warehouse 24 times a day, and each resume bills at least one minute, so it costs about 0.4 credits a day. `run_week` also calls `SP_HEALTH_CHECK` after `close_run`, inside a try block, so the Trust page is fresh after every replay. The admin app's Trust page has a **Check health now** button, which runs `EXECUTE TASK SR_DB.OPS.T_HEALTH`; `T_HEALTH` is added to `data.TASKS`.

**Exact costs.** The account usage views give real credits, with a delay. Reading them needs `GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE SR_DEV`, which ACCOUNTADMIN runs. Without that grant, the Trust page shows estimates only, marked as such. A builder runs `CALL SR_DB.OPS.SP_COST_SNAPSHOT(14);` once a day and before the dry run. `606` also adds the `TEAM_USERS` setting: a JSON array of the team's user names, used to separate our CoCo usage from other teams' on a shared account.

| Source | Account usage view | Filter | Sum | Delay |
| --- | --- | --- | --- | --- |
| `WAREHOUSES` | `WAREHOUSE_METERING_HISTORY` | `WAREHOUSE_NAME IN ('SR_WH_XS', 'SR_WH_M')` | `CREDITS_USED` | Up to 3 hours |
| `AI_FUNCTIONS` | [`CORTEX_AISQL_USAGE_HISTORY`](https://docs.snowflake.com/en/sql-reference/account-usage/cortex_aisql_usage_history) | `STARTSWITH(QUERY_TAG, 'SR' \|\| CHR(124))`, where `CHR(124)` is the tag's separator | `TOKEN_CREDITS`, `TOKENS` by `USAGE_TIME` | After the query completes |
| `AGENT_COWORK` | [`SNOWFLAKE_COWORK_USAGE_HISTORY`](https://docs.snowflake.com/sql-reference/account-usage/snowflake_intelligence_usage_history_view) | `AGENT_NAME = 'SHARE_RADAR_AGENT'` | `TOKEN_CREDITS`, `TOKENS` by `START_TIME` | Up to 1 hour |
| `AGENT_API` | `CORTEX_AGENT_USAGE_HISTORY` (calls outside CoWork, for example the eval runner) | `AGENT_NAME = 'SHARE_RADAR_AGENT'` | `TOKEN_CREDITS`, `TOKENS` by `START_TIME` | Up to 1 hour |
| `COCO` | [`SNOWFLAKE_COCO_USAGE_HISTORY`](https://docs.snowflake.com/sql-reference/account-usage/snowflake_coco_usage_history) (CLI, Desktop and Snowsight) | Users in `TEAM_USERS`, via `ACCOUNT_USAGE.USERS` | `TOKEN_CREDITS`, `TOKENS` by `USAGE_TIME`, split by `INTERFACE` | Up to 1 hour |
| Per run | `QUERY_ATTRIBUTION_HISTORY` and `CORTEX_AISQL_USAGE_HISTORY` | Run ID taken from `QUERY_TAG` | `CREDITS_ATTRIBUTED_COMPUTE`; `TOKEN_CREDITS` | Up to 8 hours |

```sql
CREATE TABLE IF NOT EXISTS SR_DB.OPS.COST_DAILY (
  USAGE_DATE DATE NOT NULL, SOURCE VARCHAR(16) NOT NULL, INTERFACE VARCHAR(16) NOT NULL DEFAULT '-',
  CREDITS NUMBER(18,6), TOKENS NUMBER(18,0), SNAPSHOT_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
  PRIMARY KEY (USAGE_DATE, SOURCE, INTERFACE)
);
CREATE TABLE IF NOT EXISTS SR_DB.OPS.COST_RUN (
  RUN_ID VARCHAR(36) NOT NULL PRIMARY KEY, WAREHOUSE_CREDITS NUMBER(18,6), AI_CREDITS NUMBER(18,6),
  AI_TOKENS NUMBER(18,0), SNAPSHOT_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- SP_COST_SNAPSHOT(P_DAYS NUMBER DEFAULT 14) RETURNS NUMBER, EXECUTE AS CALLER:
-- 1. MERGE into COST_DAILY one UNION ALL query with a branch per source in the table above, keyed on (USAGE_DATE, SOURCE, INTERFACE).
-- 2. MERGE into COST_RUN the per-run sums; the run ID is the tag's middle part:
SELECT SPLIT_PART(SPLIT_PART(QUERY_TAG, 'run=', 2), '|', 1) AS RUN_ID, SUM(CREDITS_ATTRIBUTED_COMPUTE) AS WAREHOUSE_CREDITS
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY
WHERE QUERY_TAG LIKE 'SR|run=%' AND START_TIME >= DATEADD(day, -14, CURRENT_TIMESTAMP())
GROUP BY 1;

CREATE OR REPLACE VIEW SR_DB.OPS.V_RUN_COST AS          -- estimate now, exact once the snapshot has it
SELECT r.RUN_ID, r.TRIGGER_TYPE, r.AS_OF_WEEK, r.STATUS, DATEDIFF(second, r.STARTED_AT, r.ENDED_AT) AS SECONDS,
       r.CREDITS_EST, c.WAREHOUSE_CREDITS, c.AI_CREDITS,
       COALESCE(c.AI_TOKENS, b.TOKENS_IN + b.TOKENS_OUT) AS AI_TOKENS, b.MODEL, b.GENERATOR,
       IFF(c.RUN_ID IS NULL, 'ESTIMATE', 'EXACT') AS COST_BASIS
FROM SR_DB.OPS.RUN_LOG r
LEFT JOIN SR_DB.OPS.COST_RUN c ON c.RUN_ID = r.RUN_ID
LEFT JOIN SR_DB.APP.BRIEF b ON b.BRIEF_ID = r.BRIEF_ID;

GRANT SELECT ON VIEW  SR_DB.OPS.V_HEALTH_LATEST TO ROLE SR_UI;
GRANT SELECT ON TABLE SR_DB.OPS.COST_DAILY      TO ROLE SR_UI;
```

**Cost guards and targets.** The targets are to be confirmed on Wednesday's first full run, and the measured numbers replace them in `docs/decisions.md`.

| Item | What drives it | Guard | Target |
| --- | --- | --- | --- |
| Weekly run | Dynamic-table refresh and steps on `SR_WH_M`; ML and TOP\_INSIGHTS only on gated shifts | `MAX_CREDITS_PER_RUN = 5`; one category in scope | Under 1 credit |
| Replay during the demo | Each replay is one refresh plus one run | Buttons disabled while busy | Same as a run |
| App browsing | Small queries on `SR_WH_XS` | 60-second auto-suspend; per-session cache | Small |
| Health task | 24 XS resumes a day | Suspend after the event | About 0.4 credits a day |
| Brief | One prompt with up to 1,500 output tokens; a retry only on failure | `max_tokens`; template fallback | Tokens shown per brief |
| Agent | CoWork chats | Judges and the team only | From `AGENT_COWORK` |
| Building with CoCo | AI credits per request | None needed | From `COCO`, shown as a proof point |
