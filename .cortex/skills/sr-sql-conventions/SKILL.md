---
name: sr-sql-conventions
description: How every Share Radar SQL file is written - names, qualification, settings, query tags, idempotent step procedures and tests. Use whenever you create or change a file under sql/ or tests/sql/.
---
# Share Radar SQL conventions

## Names (L1)
- Dynamic table CORE.DT_<NOUN>; view <SCHEMA>.V_<NOUN>; result table APP.<NOUN>; procedure APP.SP_<VERB>_<NOUN>;
  tool APP.TOOL_<VERB>_<NOUN>; ML instance ML.<KIND>_<NOUN>; stream, task and alert OPS.ST_, OPS.T_, OPS.A_.
- Always SR_DB.<SCHEMA>.<OBJECT>. Columns are UPPER_SNAKE.

## Types and units
- Money NUMBER(18,2), local currency. Shares FLOAT fractions; _PTS and _PCT columns are x100.
- Weeks are WEEK_END_DATE DATE. Timestamps are TIMESTAMP_LTZ.

## Settings
- In procedures: SR_DB.OPS.CFG('KEY')::FLOAT (or ::VARCHAR, ::NUMBER).
- In dynamic tables: (SELECT SETTING_VALUE::<type> FROM SR_DB.OPS.SETTINGS WHERE SETTING_KEY = 'KEY').
- Never a literal for a threshold.

## Step procedures (L6 template)
- LANGUAGE SQL, EXECUTE AS CALLER, one argument P_RUN_ID VARCHAR, RETURNS NUMBER.
- First statement sets the query tag with EXECUTE IMMEDIATE (L1 format).
- Then DELETE the run's rows, INSERT ... SELECT set-based, RETURN SQLROWCOUNT.
- No row loops unless the LLD shows one (the ML procedures). No EXCEPTION blocks; run_week handles errors.
  Tool procedures are the exception and follow the L13 pattern.

## Files
- One object per file, rerunnable: CREATE OR REPLACE for views, procedures and dynamic tables;
  CREATE TABLE IF NOT EXISTS for tables.
- A one-line comment above each CTE saying what it computes.
- Dynamic tables use TARGET_LAG = DOWNSTREAM, except DT_SHARE_COMPARE and DT_SHARE_WEEK ('15 minutes').

## Before you finish
- Search the diff for literals that should be settings, unqualified names, SELECT * in procedures, and NIQ
  object names outside sql/10_src/101_adapter_views.sql.
- Write the ticket's T2 tests in the T1 format (see sr-tests).
