-- SR-033 · L9 orchestrator: opens the run, calls the step procedures in order with a query tag each, logs every
-- step, downgrades optional failures to WARN, skips cost steps over MAX_CREDITS_PER_RUN, and closes the run.
-- Handler python/sr_lib/run.py::run_week. Returns the RUN_ID, or 'SKIPPED' (busy, or the week already ran).
USE ROLE SR_DEV;
CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_RUN_WEEK(P_TRIGGER VARCHAR DEFAULT 'MANUAL', P_FORCE BOOLEAN DEFAULT FALSE)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
IMPORTS = ('@SR_DB.APP.CODE/sr_lib.zip')
HANDLER = 'sr_lib.run.run_week'
EXECUTE AS CALLER;
