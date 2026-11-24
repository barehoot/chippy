# Share Radar

Share Radar turns every new NIQ retail-measurement week into a ranked, explained and verified competitive share brief
within minutes, entirely inside Snowflake. It detects material share shifts, splits each one exactly into
distribution, velocity, price and promo, checks whether it could be a data artefact, publishes a numbers-locked brief
by email, and answers follow-up questions through a Cortex Agent in CoWork.

Design: [docs/HLD.md](docs/HLD.md) (what and why) · [docs/LLD.md](docs/LLD.md) (the build contract, L1–L14) ·
[docs/TESTS_AND_COCO.md](docs/TESTS_AND_COCO.md) (tests T1–T7) · [docs/TICKETS.md](docs/TICKETS.md) ·
[docs/decisions.md](docs/decisions.md) (decisions taken while building, B01–B13) ·
[docs/demo_script.md](docs/demo_script.md) · [docs/solution_brief.md](docs/solution_brief.md) (draft).

## Status

Every MVP and stretch ticket that a coding agent can do is written, with its tests; the ticket table in
docs/HLD.md has the status of each. What still needs the NIQ Snowflake account or a person:

| Needs | Ticket | What to do |
| --- | --- | --- |
| The NIQ column mapping | SR-003 | Explore the NIQ schema, fill the L3 worksheet in `sql/10_src/101_adapter_views.sql`, approve it |
| The demo scope | SR-004 | Run the queries in docs/demo_script.md §1; fill the placeholders in `002_settings.sql` |
| Five NIQ reference numbers | SR-013 | Insert them with the template in `eval/reconcile.sql`, run it, then T-CORE-03 |
| Organizer privileges | SR-002, 043, 054, 056 | Account-level blocks are marked `ORGANIZERS`; `deploy_all.sh` lists any that failed |
| Real names in the golden set | SR-044 | `python3 eval/run_eval.py --propose`, review the 30 questions, commit |
| Timings, video, submission | SR-060, 062, 064 | People |

Verified here without the account: `pytest -q` runs 152 tests: unit tests for the bridge, validator, renderer,
fallback, fact pack, orchestration failure matrix, golden-set scoring and app formatting; every page of both
Streamlit apps run headless; and the repository's own SQL run on DuckDB against synthetic data (16 of the project's
SQL tests pass as written, and the SQL bridge equals its Python mirror on every row).

## Quick start (no Snowflake needed)

```bash
pip install pytest pandas altair streamlit duckdb sqlglot snowflake-snowpark-python
pytest -q                                   # unit, page and local SQL tests (about 30 seconds)
python3 tests/local/run_local.py            # pipeline on synthetic data; writes tests/local/out/synthetic_brief.html
```

An example of that brief is in [docs/examples/synthetic_brief.html](docs/examples/synthetic_brief.html) (invented names).

## Deploy to Snowflake

1. Install the Snowflake CLI (`pip install snowflake-cli`) and add an `sr` connection to `~/.snowflake/config.toml`
   (never to this repository). After the first deploy, use role `SR_DEV` and warehouse `SR_WH_XS`.
2. Run the feature smoke test: `snow sql -f sql/00_setup/009_feature_smoke_test.sql -c sr`. Each failing line names
   the HLD assumption (A5, A6) and its fallback.
3. Fill the NIQ mapping (SR-003) and the scope settings (SR-004), as in the table above.
4. Deploy everything in order: `scripts/deploy_all.sh` (`SKIP_APPS=1` for SQL only, `WITH_DMF=1` for SR-057). It
   zips `python/sr_lib` to `@SR_DB.APP.CODE`, loads the knowledge base, deploys both Streamlit apps and flushes the
   session log. Order: 00_setup → 10_src → 20_core → 40_app/401 → 30_ml → 40_app → 50_sem → 70_sec/701 → 60_ops →
   70_sec/702 → apps → 70_sec/703 (701 moved before 60_ops: decision B11).
5. First run: `snow sql -q "CALL SR_DB.APP.SP_RUN_WEEK('MANUAL', TRUE)" -c sr`, then
   `snow sql -f tests/sql/run_all.sql -c sr` (set `RUN_E2E = TRUE` in that file before a gate) and
   `python3 eval/run_eval.py --connection sr --load` (add `--tools-only` for a run without AI credits).

If the organizers provisioned their own roles, map each `SR_*` role to the team role: grant the team role to the
`SR_*` roles, or replace the role names in `001_roles_wh_db.sql` and `701_grants.sql` before running them.

## Replaying a week

The setting `AS_OF_WEEK_END` hides weeks after it (D8): real NIQ weeks replayed in order.

- **Load next week** in the admin app (`SR_DB.APP.SHARE_RADAR_ADMIN`), or `EXECUTE TASK SR_DB.OPS.T_REPLAY_NEXT`.
  The week moves, the dynamic tables refresh, the stream wakes `OPS.T_RUN_WEEK`, the run publishes a brief, and the
  alert emails it. The admin app shows progress step by step.
- **Rerun this week**: `EXECUTE TASK SR_DB.OPS.T_RUN_WEEK_MANUAL`.
- **Reset**: `CALL SR_DB.APP.SP_REPLAY_RESET('2026-10-10')`. Replay and reset return `BUSY` while a run is in progress.

## Objects

| Schema | Objects |
| --- | --- |
| `SRC` | `V_SRC_FACT_WEEKLY_ALL`, `V_SRC_FACT_WEEKLY` (replay filter), `V_SRC_PRODUCT`, `V_SRC_MARKET` (only file naming NIQ: 101) |
| `CORE` | `DT_PERIOD_WEEK`, `DT_BRAND_WEEK`, `DT_CAT_WEEK`, `DT_BRAND_PERIOD`, `DT_CAT_PERIOD`, `DT_SHARE_COMPARE`, `DT_SHARE_WEEK`, `V_SHARE_GRID` |
| `APP` | Result tables `SHIFT_CANDIDATE`, `SHARE_BRIDGE`, `ARTEFACT_CHECK`, `SHIFT_RANKED`, `SHIFT_WHERE`, `SHARE_FLOW`, `EARLY_WARNING`, `FACT_PACK`, `BRIEF`; view `V_BRIDGE_ALL`; steps `SP_CAPABILITY_CHECK`, `SP_SNAPSHOT`, `SP_DETECT_SHIFTS`, `SP_ML_SHARE_ANOMALY`, `SP_BRIDGE`, `SP_ARTEFACT`, `SP_RANK`, `SP_WHERE`, `SP_WHERE_INSIGHTS`, `SP_FLOW`, `SP_EARLY_WARNING`, `SP_ML_LEVER_ANOMALY`, `SP_BUILD_FACT_PACK`, `SP_WRITE_BRIEF`, `SP_RUN_WEEK`; `SP_WHAT_IF`, `SP_RESOLVE`, five `TOOL_*` procedures; replay and notification procedures; UI views `V_UI_SHARE_WEEK`, `V_ALIAS`; Streamlit `SHARE_RADAR`, `SHARE_RADAR_ADMIN`; stage `CODE` |
| `ML` | `AD_SHARE_WEEKLY`, `TI_SHARE`, `AD_LEVERS`, `AD_LEVERS_PRICE`, `AD_LEVERS_RESULT` |
| `SEM` | `V_SEM_SHARE_GRID`, `V_SEM_SHARE_CHANGE`, `V_TOOL_BRIDGE`, `V_TOOL_WHERE`, `V_TOOL_ARTEFACT`, `V_TOOL_FLOW`, `V_TOOL_BRIEF` (all row-filtered), semantic view `SV_SHARE`, search `CSS_METHOD`, agent `SHARE_RADAR_AGENT`, stage `SKILLS` |
| `OPS` | `SETTINGS` + `CFG()`, `CAPABILITY`, `RUN_LOG`, `STEP_LOG`, `FACT_SNAPSHOT`, `NOTIFY_LOG`, `EVAL_RESULT`, `RECON_RESULT`, `TEST_RESULT`, `GOLDEN_SET`, `COCO_LOG`, `STREAM_CONSUMED`, `HEALTH_LOG`, `COST_DAILY`, `COST_RUN`, `ENTITLEMENT`, policy `RAP_ENTITLED`; stream `ST_SHARE_COMPARE`; tasks `T_RUN_WEEK`, `T_RUN_WEEK_MANUAL`, `T_REPLAY_NEXT`, `T_HEALTH`; alert `A_NEW_BRIEF`; `SP_HEALTH_CHECK`, `SP_COST_SNAPSHOT`, `SP_ENTITLE`; views `V_HEALTH_LATEST`, `V_RUN_COST` |
| `KB`, `TEST` | `KB.METHOD_DOCS`; fixtures `FX_RECON_REFERENCE`, `FX_DEMO_EVENTS` |

## Repository layout

```text
sql/            00_setup 10_src 20_core 30_ml 40_app 50_sem 60_ops 70_sec   (deploy order: see above)
python/sr_lib/  run (orchestration, brief writer), bridge (test mirror), factpack, validator, render, fallback
python/tests/   unit tests and Streamlit page smoke tests (cases.py holds hand-computed values)
streamlit/      two apps from one codebase: streamlit_app.py (read-only), admin_app.py; pages/, sr_ui/
tests/sql/      T-* SQL tests and run_all.sql (T1 format)
tests/local/    the repository's SQL on DuckDB with synthetic data (harness.py, run_local.py)
eval/           golden_set.csv, run_eval.py, run_eval.sql, reconcile.sql
kb/             method documents for Cortex Search
scripts/        deploy_all.sh, load_kb.py, coco_log.py
docs/           design, decisions, demo script, solution brief, session log
```

## Building with a coding agent

`AGENTS.md` holds the rules every session loads (CLAUDE.md imports it for Claude Code); the five skills, the
`sr-reviewer` subagent and the Stop hook are in `.claude/` and `.cortex/`. One ticket per session: set
`.sr_ticket`, paste the ticket's prompt from docs/TICKETS.md, approve the plan, let the agent build and test, ask
`sr-reviewer` to review, then `python3 scripts/coco_log.py --event flush` and commit as `SR-0xx: <summary>`.
