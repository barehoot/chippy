-- SR-010 · L4 period calendar: week membership of each reporting period, anchored on the latest available week.
USE ROLE SR_DEV;
CREATE OR REPLACE DYNAMIC TABLE SR_DB.CORE.DT_PERIOD_WEEK
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = SR_WH_XS
  REFRESH_MODE = FULL
  COMMENT = 'Week membership of each reporting period, anchored on the latest available week'
AS
-- asof: the latest week the adapter shows (moves with the replay setting)
WITH asof AS (
  SELECT MAX(WEEK_END_DATE) AS AS_OF_WEEK FROM SR_DB.SRC.V_SRC_FACT_WEEKLY
),
-- def: each period as a range of weeks back from the as-of week
def AS (
  SELECT column1 AS PERIOD_CODE, column2 AS FROM_WK, column3 AS TO_WK
  FROM VALUES ('L4W', 3, 0), ('P4W', 7, 4), ('L4W_YA', 55, 52),
              ('L12W', 11, 0), ('L12W_YA', 63, 52), ('L52W', 51, 0), ('L52W_YA', 103, 52)
),
-- weeks: every week that has data
weeks AS (
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
