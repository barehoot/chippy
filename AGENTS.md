# Share Radar: rules for CoCo

## What this repository builds
Share Radar watches NIQ retail measurement data each week. It finds material competitive share shifts,
explains each one with an exact driver bridge, checks whether it could be a data artefact, publishes a
numbers-locked brief, and answers follow-up questions through a Cortex Agent in CoWork. The full design is
in docs/: HLD.md (plan, architecture, tickets), LLD.md (sections L1 to L14) and TESTS_AND_COCO.md
(sections T1 to T7). docs/TICKETS.md lists every ticket with its prompt.

## Golden rules
1. One ticket at a time. The current ticket ID is in .sr_ticket. Touch only that ticket's files and tests (T7).
2. Names in the design are final: objects, columns, settings, files and test IDs. If one looks wrong, stop and
   ask. Never rename on your own.
3. Fully qualify every object as SR_DB.<SCHEMA>.<OBJECT>.
4. Thresholds come from OPS.SETTINGS through SR_DB.OPS.CFG('<KEY>'), never as literals. Inside dynamic tables,
   read OPS.SETTINGS with a scalar subquery instead.
5. Only sql/10_src/101_adapter_views.sql names NIQ objects.
6. Shares are stored as fractions from 0 to 1. Columns ending _PTS or _PCT hold values multiplied by 100.
7. Pipeline steps are EXECUTE AS CALLER, idempotent per RUN_ID (delete the run's rows, then insert), return
   their row count, and set the query tag first (L6 template). They do not catch their own errors; run_week
   does (L13).
8. Never compute in Python or in the LLM a number that SQL can compute. The brief's numbers come only from the
   fact pack (L8).
9. The Streamlit apps never run pipeline steps. They start tasks and read logs, and every query lives in
   streamlit/sr_ui/data.py (L11).
10. Tool procedures read only SEM.V_TOOL_* views and return their L10 payload or an L13 error object.
11. A ticket is done only when its T2 tests pass and sr-reviewer reports no blocking finding.
12. No secrets in files. The sr connection lives in ~/.snowflake/config.toml.

## Where code goes
| Layer              | Folder        | Notes                                                              |
| ------------------ | ------------- | ------------------------------------------------------------------ |
| Setup              | sql/00_setup  | roles, warehouses, schemas, settings, ops tables                   |
| Source adapter     | sql/10_src    | the only place NIQ tables are named                                |
| Core               | sql/20_core   | dynamic tables; only the two leaf tables have a time lag           |
| ML                 | sql/30_ml     | ANOMALY_DETECTION and TOP_INSIGHTS procedures                      |
| Intelligence       | sql/40_app    | result tables, step procedures, tools, UI objects                  |
| Semantic and agent | sql/50_sem    | views, semantic view, search, agent, CoWork                        |
| Operations         | sql/60_ops    | stream, tasks, replay, email, alert, health, cost (USE ROLE SR_APP) |
| Security           | sql/70_sec    | grants, row access, app usage                                      |
| Python             | python/sr_lib | run, bridge mirror, fact pack, validator, renderer, fallback       |
| Apps               | streamlit     | two Streamlit apps from one codebase                               |
| Tests              | tests/sql, python/tests, eval | harness T1, catalogue T2, golden set T3            |

## Commands
- Run one SQL file: snow sql -f sql/<folder>/<file>.sql -c sr
- Deploy everything in order: scripts/deploy_all.sh
- SQL tests: snow sql -f tests/sql/run_all.sql -c sr
- Python tests: pytest -q python/tests   (integration: pytest -q -m integration python/tests)
- Deploy the apps, from streamlit/: snow streamlit deploy share_radar --replace --role SR_UI -c sr,
  then the same for share_radar_admin with --role SR_APP
- Golden set: python3 eval/run_eval.py --connection sr   (no LLM: add --tools-only)
- Log a hand edit: python3 scripts/coco_log.py --event human --note "<what changed>"

## Definition of done
- The files named in the ticket's T7 prompt exist and match the design.
- The ticket's T2 tests pass, and run_all.sql shows no new failures.
- sr-reviewer reports no blocking finding.
- After any change in sql/50_sem, sql/70_sec/702_row_access.sql has been rerun and T-SEC-03 passes.
- The Stop hook has written the session line to docs/coco_log.md.

## Do not
- Use SELECT * in procedures.
- Create objects outside SR_DB, or warehouses, roles or integrations outside 00_setup, 60_ops/603 and 70_sec.
- Call AI_COMPLETE anywhere except SP_WRITE_BRIEF.
- Use SHOW or DESCRIBE in app code or tool procedures.
- Edit a test to make it pass. Fix the code, or stop and say why the test is wrong.
- Put client or brand names in logs, commit messages or the CoCo log.
