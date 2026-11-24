-- SR-002 · L1 feature smoke test. Run as the team role before SR-003; every statement must succeed.
-- Report each line as pass or fail. A failure maps to an HLD assumption and its fallback:
--   lines 1-2 fail -> A5 (LLM / model): change LLM_MODEL in OPS.SETTINGS to a model the account has, rerun.
--   line 3-4 fail  -> A5 (ML functions): ML steps log WARN; confidence comes from z only (E07, E08).
--   line 5 fails   -> dynamic tables unavailable: stop and raise with the organizers (no fallback).
--   line 6-7 fail  -> A5 (Agents / CoWork): Streamlit is the only surface; agent tickets move to the cut line.
--   line 8 shows no integration we may use -> A6: in-app brief only, plus a hand-sent email for the video.
USE ROLE SR_DEV;
USE WAREHOUSE SR_WH_XS;

-- 1 LLM access and model
SELECT AI_COMPLETE('claude-sonnet-4-5', 'Reply with the word OK') AS SMOKE_1_LLM;

-- 2 structured output
SELECT AI_COMPLETE(
  model => 'claude-sonnet-4-5',
  prompt => 'Return ok = true',
  response_format => {'type': 'json', 'schema': {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok']}}
) AS SMOKE_2_STRUCTURED;

-- 3 ML privilege
CREATE SNOWFLAKE.ML.TOP_INSIGHTS IF NOT EXISTS SR_DB.ML.TI_SMOKE();

-- 4 ML class visible
SHOW SNOWFLAKE.ML.ANOMALY_DETECTION IN SCHEMA SR_DB.ML;

-- 5 dynamic tables
CREATE OR REPLACE DYNAMIC TABLE SR_DB.TEST.DT_SMOKE TARGET_LAG = '1 day' WAREHOUSE = SR_WH_XS AS SELECT 1 AS X;

-- 6 Cortex Agents
SHOW AGENTS IN ACCOUNT;

-- 7 CoWork object exists
DESCRIBE SNOWFLAKE INTELLIGENCE SNOWFLAKE_INTELLIGENCE_OBJECT_DEFAULT;

-- 8 what we may send through
SHOW NOTIFICATION INTEGRATIONS;

-- clean up
DROP DYNAMIC TABLE IF EXISTS SR_DB.TEST.DT_SMOKE;
DROP SNOWFLAKE.ML.TOP_INSIGHTS IF EXISTS SR_DB.ML.TI_SMOKE;
