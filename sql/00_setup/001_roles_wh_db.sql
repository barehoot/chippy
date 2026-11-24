-- SR-002 · L1 setup: roles, warehouses, database and schemas.
-- If the organizers already provisioned roles and warehouses, skip blocks 1 and 2 and map every SR_* role
-- to the team role (see README "Mapping SR_* roles"). Rerunnable: every statement is IF NOT EXISTS.

-- Block 1: roles (SECURITYADMIN). SR_UI is added in sql/70_sec/701_grants.sql (L12).
USE ROLE SECURITYADMIN;
CREATE ROLE IF NOT EXISTS SR_ADMIN;    -- owns the database
CREATE ROLE IF NOT EXISTS SR_DEV;      -- builds (coding-agent sessions run as this role)
CREATE ROLE IF NOT EXISTS SR_APP;      -- owns tasks, alerts, the stream and the admin app; runs the pipeline
CREATE ROLE IF NOT EXISTS SR_ANALYST;  -- CoWork and Streamlit users
CREATE ROLE IF NOT EXISTS SR_JUDGE;    -- read-only demo role
GRANT ROLE SR_DEV     TO ROLE SR_ADMIN;
GRANT ROLE SR_APP     TO ROLE SR_ADMIN;
GRANT ROLE SR_ANALYST TO ROLE SR_ADMIN;
GRANT ROLE SR_JUDGE   TO ROLE SR_ADMIN;
GRANT ROLE SR_ADMIN   TO ROLE SYSADMIN;   -- keeps the hierarchy reachable by the account admins

-- Block 2: warehouses, database, schemas (SYSADMIN)
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

-- Block 3: builders can create in every schema (the full grant set is in sql/70_sec/701_grants.sql)
USE ROLE SR_ADMIN;
GRANT USAGE ON DATABASE SR_DB TO ROLE SR_DEV;
GRANT ALL ON ALL SCHEMAS IN DATABASE SR_DB TO ROLE SR_DEV;
