-- T1 SQL test harness: snow sql -f tests/sql/run_all.sql -c sr
-- Sets the session variables, sources every test file in ID order, and prints the failures (failed tests first).
-- E2E files (T-E2E-*, T-NAR-04, T-ART-05, T-RANK-02) start runs and take minutes; they skip unless RUN_E2E = TRUE.
-- Before a gate: change the RUN_E2E line below to TRUE. Until SR-033, set RUN_UNDER_TEST to 'dev-001' by hand.
USE ROLE SR_DEV;
USE SECONDARY ROLES NONE;
USE WAREHOUSE SR_WH_XS;
SET TEST_RUN_ID = UUID_STRING();
SET RUN_UNDER_TEST = (SELECT COALESCE(MAX(RUN_ID), 'dev-001') FROM (
  SELECT RUN_ID FROM SR_DB.OPS.RUN_LOG WHERE STATUS = 'SUCCEEDED' ORDER BY STARTED_AT DESC LIMIT 1));
SET RUN_E2E = FALSE;
!source tests/sql/000_fixtures.sql
!source tests/sql/T-ART-01.sql
!source tests/sql/T-ART-02.sql
!source tests/sql/T-ART-03.sql
!source tests/sql/T-ART-04.sql
!source tests/sql/T-ART-05.sql
!source tests/sql/T-BR-01.sql
!source tests/sql/T-BR-03.sql
!source tests/sql/T-BR-04.sql
!source tests/sql/T-CORE-01.sql
!source tests/sql/T-CORE-02.sql
!source tests/sql/T-CORE-03.sql
!source tests/sql/T-CORE-04.sql
!source tests/sql/T-DET-01.sql
!source tests/sql/T-DET-02.sql
!source tests/sql/T-E2E-01.sql
!source tests/sql/T-E2E-02.sql
!source tests/sql/T-E2E-03.sql
!source tests/sql/T-E2E-04.sql
!source tests/sql/T-EW-01.sql
!source tests/sql/T-EW-02.sql
!source tests/sql/T-FLOW-01.sql
!source tests/sql/T-FLOW-02.sql
!source tests/sql/T-FP-01.sql
!source tests/sql/T-ML-01.sql
!source tests/sql/T-NAR-04.sql
!source tests/sql/T-RANK-01.sql
!source tests/sql/T-RANK-02.sql
!source tests/sql/T-SEC-01.sql
!source tests/sql/T-SEC-02.sql
!source tests/sql/T-SEC-03.sql
!source tests/sql/T-SRC-01.sql
!source tests/sql/T-SRC-02.sql
!source tests/sql/T-SRC-03.sql
!source tests/sql/T-TOOL-01.sql
!source tests/sql/T-TOOL-02.sql
!source tests/sql/T-TOOL-03.sql
!source tests/sql/T-TOOL-04.sql
!source tests/sql/T-TOOL-05.sql
!source tests/sql/T-WH-01.sql
!source tests/sql/T-WH-02.sql
!source tests/sql/T-WI-01.sql
SELECT TEST_ID, PASSED, FAILURES, DETAIL
FROM SR_DB.OPS.TEST_RESULT WHERE TEST_RUN_ID = $TEST_RUN_ID
ORDER BY PASSED, TEST_ID;
