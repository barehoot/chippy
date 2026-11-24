-- SR-053 · L9 trigger: a stream on the share table wakes a triggered task, which runs the week.
-- Procedures are created as SR_DEV (they run with caller's rights, so ownership does not change what they do,
-- L12); the stream and the tasks are owned by SR_APP, so tasks run as SR_APP.
USE ROLE SR_DEV;
CREATE OR REPLACE PROCEDURE SR_DB.APP.SP_RUN_FROM_STREAM()
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  rid       VARCHAR;
  is_replay BOOLEAN DEFAULT FALSE;
BEGIN
  -- reading the stream inside DML advances its offset when the statement commits
  INSERT INTO SR_DB.OPS.STREAM_CONSUMED (CONSUMED_AT, ROWS_SEEN)
  SELECT CURRENT_TIMESTAMP(), COUNT(*) FROM SR_DB.OPS.ST_SHARE_COMPARE;
  SELECT UPDATED_AT > DATEADD(minute, -15, CURRENT_TIMESTAMP()) INTO :is_replay
    FROM SR_DB.OPS.SETTINGS WHERE SETTING_KEY = 'AS_OF_WEEK_END';
  IF (is_replay) THEN
    CALL SR_DB.APP.SP_RUN_WEEK('REPLAY', TRUE) INTO :rid;    -- a replayed week always runs, even if it ran before
  ELSE
    CALL SR_DB.APP.SP_RUN_WEEK('STREAM', FALSE) INTO :rid;   -- a real new week runs once
  END IF;
  RETURN rid;
END;
$$;

USE ROLE SR_APP;
CREATE OR REPLACE STREAM SR_DB.OPS.ST_SHARE_COMPARE ON DYNAMIC TABLE SR_DB.CORE.DT_SHARE_COMPARE
  COMMENT = 'New share rows mean a new data week landed (or was replayed)';

CREATE OR REPLACE TASK SR_DB.OPS.T_RUN_WEEK
  WAREHOUSE = SR_WH_M
  COMMENT = 'Triggered: runs the week when the share table changes'
  WHEN SYSTEM$STREAM_HAS_DATA('SR_DB.OPS.ST_SHARE_COMPARE')
AS
  CALL SR_DB.APP.SP_RUN_FROM_STREAM();
ALTER TASK SR_DB.OPS.T_RUN_WEEK RESUME;

-- No schedule: runs only when the admin app executes it ("Rerun this week")
CREATE OR REPLACE TASK SR_DB.OPS.T_RUN_WEEK_MANUAL
  WAREHOUSE = SR_WH_M
  COMMENT = 'Admin app: rerun the current week'
AS
  CALL SR_DB.APP.SP_RUN_WEEK('MANUAL', TRUE);
