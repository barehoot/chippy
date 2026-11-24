-- SR-030 · L8 fact pack builder: every number the brief may state becomes a fact with an ID, unit, decimals and
-- its source. Handler python/sr_lib/factpack.py (reads the result tables, computes nothing). Returns the BRIEF_ID.
-- sr_lib.zip is uploaded to @SR_DB.APP.CODE by scripts/deploy_all.sh before this file runs.
USE ROLE SR_DEV;
CREATE STAGE IF NOT EXISTS SR_DB.APP.CODE COMMENT = 'sr_lib.zip for the Python procedures';

CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_BUILD_FACT_PACK(P_RUN_ID VARCHAR)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
IMPORTS = ('@SR_DB.APP.CODE/sr_lib.zip')
HANDLER = 'sr_lib.factpack.build_fact_pack'
EXECUTE AS CALLER;
