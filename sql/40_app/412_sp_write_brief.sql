-- SR-031 · L8 brief writer: AI_COMPLETE with structured output, the validator, one retry on the fallback model
-- with the problems listed, then the deterministic template. Handler python/sr_lib/run.py::write_brief.
-- The only place AI_COMPLETE is called (AGENTS.md). sr_lib.zip is PUT by scripts/deploy_all.sh.
USE ROLE SR_DEV;
CREATE STAGE IF NOT EXISTS SR_DB.APP.CODE COMMENT = 'sr_lib.zip for the Python procedures';

CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_WRITE_BRIEF(P_RUN_ID VARCHAR)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'snowflake-ml-python')
IMPORTS = ('@SR_DB.APP.CODE/sr_lib.zip')
HANDLER = 'sr_lib.run.write_brief'
EXECUTE AS CALLER;
