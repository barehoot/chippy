---
name: sr-tests
description: How Share Radar tests are written and run - SQL assertion files, the expect-error pattern, pytest cases and markers, end-to-end files and the golden set. Use when a ticket needs its tests written or when a test fails.
---
# Tests

## SQL tests (T1)
- One file per test: tests/sql/<TEST_ID>.sql, starting with SET TEST_ID.
- A failures CTE returns one row per failure. Insert one row into OPS.TEST_RESULT with
  PASSED = (COUNT(*) = 0) and up to 20 failing rows in DETAIL.
- Use $RUN_UNDER_TEST for the run being checked and $TEST_RUN_ID for the result row.
- Add a !source line to tests/sql/run_all.sql, in ID order.
- Recompute independently. Never reuse the procedure's own SQL in its test.
- Expect-error tests: switch role, USE SECONDARY ROLES NONE, try each forbidden statement in its own
  BEGIN ... EXCEPTION block, return the failures as text, switch back, record through RESULT_SCAN.
- End-to-end files return early unless $RUN_E2E is TRUE, and restore every setting they change.

## Python tests
- python/tests/test_<module>.py. Function names carry the ID, for example test_T_BR_05_toy_case.
- Hand-computed cases go in python/tests/cases.py, with inputs and expected outputs written out.
- Integration tests use @pytest.mark.integration and
  Session.builder.config("connection_name", "sr").create().

## When a test fails
- Read the DETAIL rows first. If the test is right, fix the code.
- If you believe the test is wrong, stop and explain why. Never edit a test just to make it pass.
