# Share Radar tickets and prompts

Every ticket in build order, with what "done" means and the prompt to paste into the coding agent. Each dependency comes before the ticket that needs it. Estimates are hours. Section numbers point to docs/LLD.md (L1–L14) and docs/TESTS_AND_COCO.md (T1–T7).

## The loop for every ticket

1. `echo SR-0xx > .sr_ticket`
2. Switch the agent to plan mode (see README.md), paste the prompt, and approve the plan only if it touches the files the ticket names.
3. Let it build and deploy.
4. It runs the ticket's named tests (T2) and fixes the code until they pass. It never edits a test to make it pass.
5. Ask the `sr-reviewer` subagent to review; fix anything BLOCKING.
6. `python3 scripts/coco_log.py --event flush`, then commit as `SR-0xx: <summary>`.
7. Set the ticket's Status in docs/HLD.md, then start the next one.

Until SR-033 exists, steps are called with run ID `'dev-001'`, and `$RUN_UNDER_TEST` is set to it.

## Build order at a glance

| # | Ticket | Title | Role | Est | Scope |
| --- | --- | --- | --- | --- | --- |
| 1 | SR-001 | Repo, AGENTS.md, CoCo skills, reviewer subagent, Stop hook | PM | 1.5 | MVP |
| 2 | SR-002 | Roles, warehouses, schemas, OPS.SETTINGS, run and step logs | DE | 1 | MVP |
| 3 | SR-003 | Source discovery (CoCo explores NIQ tables), adapter views, capability check | DE | 3 | MVP |
| 4 | SR-004 | Pick demo scope: country, category, focus manufacturer, parent market | PM | 0.5 | MVP |
| 5 | SR-010 | Period calendar dynamic table | DE | 1.5 | MVP |
| 6 | SR-011 | Brand-week and category-week dynamic tables | DE | 1.5 | MVP |
| 7 | SR-012 | Brand-period, category-period and share-compare dynamic tables, grid views | DE | 2.5 | MVP |
| 8 | SR-013 | Reconcile five numbers to an NIQ reference | PM | 1 | MVP |
| 9 | SR-020 | Shift detector: gates and z-score into SHIFT_CANDIDATE | DE | 2 | MVP |
| 10 | SR-021 | ANOMALY_DETECTION on weekly share series | AI | 2 | MVP |
| 11 | SR-022 | Share bridge procedure (LMDI, modes A–D) and Python mirror | DE + AI | 3 | MVP |
| 12 | SR-024 | Artefact gate rules R1–R6 and snapshot hashes | DE | 3 | MVP |
| 13 | SR-026 | Materiality score, ranking and suppression into SHIFT_RANKED | DE | 1.5 | MVP |
| 14 | SR-023 | Where: exact retailer split and TOP_INSIGHTS for ranked shifts | AI | 2.5 | MVP |
| 15 | SR-025 | Share flow (who took it) | AI | 1.5 | MVP |
| 16 | SR-027 | Early warning: mechanical SQL projection | AI | 1.5 | MVP |
| 17 | SR-029 | What-if procedure | AI | 1 | MVP |
| 18 | SR-030 | Fact pack builder | AI | 2 | MVP |
| 19 | SR-031 | Brief writer: prompt and AI_COMPLETE structured output | AI | 2 | MVP |
| 20 | SR-032 | Validator, renderer and template fallback | AI | 3 | MVP |
| 21 | SR-033 | Orchestrator SP_RUN_WEEK, logs, query tags | DE | 2 | MVP |
| 22 | SR-053 | Stream, triggered task and replay procedure | DE | 1.5 | MVP |
| 23 | SR-040 | Semantic view over grid and change views | AI | 2 | MVP |
| 24 | SR-056 | Roles, grants, row access policy, judge role | DE | 1 | MVP |
| 25 | SR-041 | Method docs (KB) and Cortex Search service | PM | 2 | MVP |
| 26 | SR-042 | Tool procedures: bridge, artefact, flow, what-if, latest brief | DE | 2 | MVP |
| 27 | SR-043 | Agent specification and CoWork registration | AI | 1.5 | MVP |
| 28 | SR-044 | Golden set (30 questions) and evaluation run | PM | 2.5 | MVP |
| 29 | SR-050 | Streamlit: Radar home and replay button | APP | 3 | MVP |
| 30 | SR-051 | Streamlit: shift detail (waterfall, where, flow, artefact, what-if) | APP | 3 | MVP |
| 31 | SR-052 | Streamlit: brief page with provenance, Trust page | APP | 2.5 | MVP |
| 32 | SR-054 | Email notification and alert on new brief | APP | 1.5 | MVP |
| 33 | SR-060 | Time the manual share review with 2–3 analysts | PM | 1 | MVP |
| 34 | SR-061 | End-to-end timing and dry run | PM | 1 | MVP |
| 35 | SR-062 | Demo video, 5 minutes max | PM | 4 | MVP |
| 36 | SR-063 | Solution brief, 1–2 pages | PM | 2 | MVP |
| 37 | SR-064 | Code freeze, README, submission | All | 1 | MVP |
| 38 | SR-028 | Early warning: ANOMALY_DETECTION on lever series | AI | 1.5 | Stretch |
| 39 | SR-045 | Methodology skill attached to the agent | AI | 1 | Stretch |
| 40 | SR-055 | Teams webhook notification | APP | 1 | Stretch |
| 41 | SR-057 | Data metric functions on the fact adapter | DE | 1 | Stretch |

If time runs short, use the cut line in docs/HLD.md ("Risks, fallbacks and the cut line"). Never cut the bridge, the artefact gate, the validator, replay, the golden set, or the agent's bridge and artefact tools.

## Phase 1: setup and the share grid

### SR-001 · Repo, AGENTS.md, CoCo skills, reviewer subagent, Stop hook

- **Stream:** Setup · **Role:** PM · **Estimate:** 1.5 h · **Scope:** MVP
- **Depends on:** —
- **Done when:** CoCo lists the 5 skills; a test session writes a coco_log line

```text
Set up the repository. The design docs (docs/HLD.md, docs/LLD.md, docs/TESTS_AND_COCO.md, docs/TICKETS.md), AGENTS.md, CLAUDE.md, the five skills, the sr-reviewer subagent, the Stop hook settings, scripts/coco_log.py and .gitignore are already in place: check them against T4 to T6 and report anything missing. Then create the rest of the L2 tree with empty files. Make one change and show that the Stop hook wrote docs/coco_log.md.
```

### SR-002 · Roles, warehouses, schemas, OPS.SETTINGS, run and step logs

- **Stream:** Setup · **Role:** DE · **Estimate:** 1 h · **Scope:** MVP
- **Depends on:** SR-001
- **Done when:** Setup scripts rerun cleanly; settings seeded

```text
Implement SR-002. Read L1 and L5. Write sql/00_setup/001_roles_wh_db.sql, 002_settings.sql (with the CURRENCY row), 003_ops_tables.sql (the L5 ops tables plus OPS.TEST_RESULT from T1) and 009_feature_smoke_test.sql. Run them in order, and report each smoke-test line as pass or fail against assumptions A5 and A6.
```

### SR-003 · Source discovery (CoCo explores NIQ tables), adapter views, capability check

- **Stream:** Setup · **Role:** DE · **Estimate:** 3 h · **Scope:** MVP
- **Depends on:** SR-002
- **Done when:** T-SRC-01..03 pass; OPS.CAPABILITY written

```text
Implement SR-003. Read L3 and AGENTS.md. Explore <NIQ_DB> with SHOW and DESCRIBE, propose the column mapping as the L3 worksheet table, and wait for my approval. Then write sql/10_src/101_adapter_views.sql and 102_capability.sql, including the L13 E01 check, then write and run T-SRC-01..03.
```

### SR-004 · Pick demo scope: country, category, focus manufacturer, parent market

- **Stream:** Setup · **Role:** PM · **Estimate:** 0.5 h · **Scope:** MVP
- **Depends on:** SR-003
- **Done when:** Settings updated and agreed

```text
Help me choose the demo scope. Using the adapter views, list the 5 categories with the most brands and child retailer markets under one parent market, with weeks of history. For the category I pick, list weeks where a child retailer's category sales drop to zero or its store count changes. Do not write files; give me the tables.
```

### SR-010 · Period calendar dynamic table

- **Stream:** Core · **Role:** DE · **Estimate:** 1.5 h · **Scope:** MVP
- **Depends on:** SR-003
- **Done when:** T-CORE-04 passes

```text
Implement SR-010. Read L4. Write sql/20_core/201_dt_period_week.sql exactly as in L4, deploy it, then write and run T-CORE-04.
```

### SR-011 · Brand-week and category-week dynamic tables

- **Stream:** Core · **Role:** DE · **Estimate:** 1.5 h · **Scope:** MVP
- **Depends on:** SR-003
- **Done when:** T-CORE-02 passes

```text
Implement SR-011. Read L4. Write 202_dt_brand_week.sql and 203_dt_cat_week.sql exactly as in L4, deploy them, then write and run T-CORE-02.
```

### SR-012 · Brand-period, category-period and share-compare dynamic tables, grid views

- **Stream:** Core · **Role:** DE · **Estimate:** 2.5 h · **Scope:** MVP
- **Depends on:** SR-010, SR-011
- **Done when:** T-CORE-01 passes

```text
Implement SR-012. Read L4. Write 204 to 208 as in L4: the period tables, DT_SHARE_COMPARE, DT_SHARE_WEEK and V_SHARE_GRID. Deploy them, then write and run T-CORE-01.
```

### SR-013 · Reconcile five numbers to an NIQ reference

- **Stream:** Core · **Role:** PM · **Estimate:** 1 h · **Scope:** MVP
- **Depends on:** SR-012
- **Done when:** T-CORE-03 passes; any gap explained

```text
Help with SR-013. I will give you five reference numbers from an NIQ report. Insert them into TEST.FX_RECON_REFERENCE (T1), write the query that compares each with V_SHARE_GRID and fills OPS.RECON_RESULT, and run it. Then write and run T-CORE-03. Explain any mismatch before you change code.
```

## Phase 2: intelligence

### SR-020 · Shift detector: gates and z-score into SHIFT_CANDIDATE

- **Stream:** Intelligence · **Role:** DE · **Estimate:** 2 h · **Scope:** MVP
- **Depends on:** SR-012
- **Done when:** T-DET-01..02 pass

```text
Implement SR-020. Read L5 and L6 (template, Detector). Write sql/40_app/401_result_tables.sql with every L5 result table, and 403_sp_detect_shifts.sql. Call it for 'dev-001', then write and run T-DET-01..02.
```

### SR-021 · ANOMALY_DETECTION on weekly share series

- **Stream:** Intelligence · **Role:** AI · **Estimate:** 2 h · **Scope:** MVP
- **Depends on:** SR-011
- **Done when:** T-ML-01 passes; training under 10 min

```text
Implement SR-021. Read L7. Write sql/30_ml/301_sp_ml_share_anomaly.sql as in L7. Run it for 'dev-001' after the detector, then write and run T-ML-01.
```

### SR-022 · Share bridge procedure (LMDI, modes A–D) and Python mirror

- **Stream:** Intelligence · **Role:** DE + AI · **Estimate:** 3 h · **Scope:** MVP
- **Depends on:** SR-012
- **Done when:** T-BR-01..05 pass

```text
Implement SR-022. Read L6 (Bridge) and L10 (V_BRIDGE_ALL). Write python/sr_lib/bridge.py with the L6 signatures, and python/tests/cases.py with a toy case; show me the hand computation before you code it. Then write 404_sp_bridge.sql and APP.V_BRIDGE_ALL, and write and run T-BR-01..05.
```

### SR-024 · Artefact gate rules R1–R6 and snapshot hashes

- **Stream:** Intelligence · **Role:** DE · **Estimate:** 3 h · **Scope:** MVP
- **Depends on:** SR-011
- **Done when:** T-ART-01..05 pass

```text
Implement SR-024. Read L6 (Artefact gate). Write 402_sp_snapshot.sql, and 405_sp_artefact.sql with all six rules and their evidence objects. Run them, then write and run T-ART-01..04. T-ART-05 follows SR-053.
```

### SR-026 · Materiality score, ranking and suppression into SHIFT_RANKED

- **Stream:** Intelligence · **Role:** DE · **Estimate:** 1.5 h · **Scope:** MVP
- **Depends on:** SR-020, SR-022, SR-024
- **Done when:** T-RANK-01..02 pass

```text
Implement SR-026. Read L6 (Rank and suppress). Write 406_sp_rank.sql, run it, then write and run T-RANK-01. T-RANK-02 follows SR-053.
```

### SR-023 · Where: exact retailer split and TOP_INSIGHTS for ranked shifts

- **Stream:** Intelligence · **Role:** AI · **Estimate:** 2.5 h · **Scope:** MVP
- **Depends on:** SR-012, SR-026
- **Done when:** T-WH-01..02 pass

```text
Implement SR-023. Read L6 (Where) and L7 (TOP_INSIGHTS). Write 407_sp_where.sql for the exact retailer split, and sql/30_ml/302_sp_where_insights.sql. Run both for 'dev-001', then write and run T-WH-01..02.
```

### SR-025 · Share flow (who took it)

- **Stream:** Intelligence · **Role:** AI · **Estimate:** 1.5 h · **Scope:** MVP
- **Depends on:** SR-012
- **Done when:** T-FLOW-01..02 pass

```text
Implement SR-025. Read L6 (Who took it). Write 408_sp_flow.sql, run it, then write and run T-FLOW-01..02.
```

### SR-027 · Early warning: mechanical SQL projection

- **Stream:** Intelligence · **Role:** AI · **Estimate:** 1.5 h · **Scope:** MVP
- **Depends on:** SR-011
- **Done when:** T-EW-01 passes

```text
Implement SR-027. Read L6 (Early warning). Write 409_sp_early_warning.sql, run it, then write and run T-EW-01.
```

### SR-029 · What-if procedure

- **Stream:** Intelligence · **Role:** AI · **Estimate:** 1 h · **Scope:** MVP
- **Depends on:** SR-022
- **Done when:** T-WI-01 passes

```text
Implement SR-029. Read L6 (What-if). Write 410_sp_what_if.sql returning the L6 object, then write and run T-WI-01.
```

## Phase 3: brief and orchestration

### SR-030 · Fact pack builder

- **Stream:** Narrative · **Role:** AI · **Estimate:** 2 h · **Scope:** MVP
- **Depends on:** SR-023, SR-025, SR-026, SR-027
- **Done when:** T-FP-01 passes

```text
Implement SR-030. Read L8 (Fact pack contract). Write 411_sp_build_fact_pack.sql and python/sr_lib/factpack.py as L8 specifies. Every number gets a fact with its src. Then write and run T-FP-01.
```

### SR-031 · Brief writer: prompt and AI_COMPLETE structured output

- **Stream:** Narrative · **Role:** AI · **Estimate:** 2 h · **Scope:** MVP
- **Depends on:** SR-030
- **Done when:** Valid JSON on three runs in a row

```text
Implement SR-031. Read L8 (Prompt, Structured output schema, Brief writer). Write build_prompt and the first attempt of write_brief in python/sr_lib/run.py, 412_sp_write_brief.sql, and the zip-and-PUT step of scripts/deploy_all.sh. Run it three times on 'dev-001', and show that each reply parses against the schema.
```

### SR-032 · Validator, renderer and template fallback

- **Stream:** Narrative · **Role:** AI · **Estimate:** 3 h · **Scope:** MVP
- **Depends on:** SR-031
- **Done when:** T-NAR-01..05 pass

```text
Implement SR-032. Read L8 (Validator, Renderer and fallback) and L13 (E10, E11). Write python/sr_lib/validator.py, render.py and fallback.py, and finish write_brief: retry, fallback model, template. Then write and run T-NAR-01..05.
```

### SR-033 · Orchestrator SP_RUN_WEEK, logs, query tags

- **Stream:** Narrative · **Role:** DE · **Estimate:** 2 h · **Scope:** MVP
- **Depends on:** SR-020 to SR-032
- **Done when:** T-E2E-01, T-E2E-02 and T-E2E-04 pass

```text
Implement SR-033. Read L9, L13 (run_week) and L14 (estimate_credits). Write python/sr_lib/run.py (STEPS, open_run, log_step with started_at, estimate_credits, close_run, run_week) and 413_sp_run_week.sql. Run CALL SR_DB.APP.SP_RUN_WEEK('MANUAL', TRUE), then write and run T-E2E-01, T-E2E-02 and T-E2E-04.
```

### SR-053 · Stream, triggered task and replay procedure

- **Stream:** Delivery · **Role:** DE · **Estimate:** 1.5 h · **Scope:** MVP
- **Depends on:** SR-033
- **Done when:** Replay starts a run within 2 minutes

```text
Implement SR-053. Read L9 (stream, task, replay) and L11 (the two tasks). Write 601_stream_task.sql and 602_replay.sql, each starting with USE ROLE SR_APP. Replay one week from the admin app and watch the run finish. Then write and run T-E2E-03, T-ART-05 and T-RANK-02.
```

## Phase 4: agent and security

### SR-040 · Semantic view over grid and change views

- **Stream:** Agent · **Role:** AI · **Estimate:** 2 h · **Scope:** MVP
- **Depends on:** SR-012, SR-022, SR-024
- **Done when:** 10 golden questions right through Analyst

```text
Implement SR-040. Read L10 (Semantic view), L12 (Tool views) and the sr-cortex-agent skill. Write sql/50_sem/501_v_sem_views.sql, with the V_SEM_* and V_TOOL_* views, and 502_sv_share.sql. Ask Cortex Analyst 10 questions taken from the golden set's NUMBER and REFUSE rows, compare each with its EXPECTED_SQL, and report.
```

### SR-056 · Roles, grants, row access policy, judge role

- **Stream:** Delivery · **Role:** DE · **Estimate:** 1 h · **Scope:** MVP
- **Depends on:** SR-012
- **Done when:** T-SEC-01..03 pass

```text
Implement SR-056. Read L12. Write sql/70_sec/701_grants.sql, 702_row_access.sql and 703_app_usage.sql, and mark the blocks that need ACCOUNTADMIN for the organizers. Run them, then write and run T-SEC-01..03.
```

### SR-041 · Method docs (KB) and Cortex Search service

- **Stream:** Agent · **Role:** PM · **Estimate:** 2 h · **Scope:** MVP
- **Depends on:** SR-002
- **Done when:** Right passage for 5 definition queries

```text
Help with SR-041. Read L10 (Method knowledge base) and the share-methodology skill. Draft the five kb/*.md files, one idea per ## section, for my review. Then write scripts/load_kb.py and 503_kb_and_search.sql, load the documents, and show the top three search results for 'what is TDP'.
```

### SR-042 · Tool procedures: bridge, artefact, flow, what-if, latest brief

- **Stream:** Agent · **Role:** DE · **Estimate:** 2 h · **Scope:** MVP
- **Depends on:** SR-022, SR-024, SR-025, SR-029, SR-032
- **Done when:** T-TOOL-01..05 pass

```text
Implement SR-042. Read L10 (Tool procedures) and L13 (Tool error contract). Write APP.SP_RESOLVE and the five TOOL_* procedures in 414_tool_procs.sql, reading only SEM.V_TOOL_* views. Then write and run T-TOOL-01..05.
```

### SR-043 · Agent specification and CoWork registration

- **Stream:** Agent · **Role:** AI · **Estimate:** 1.5 h · **Scope:** MVP
- **Depends on:** SR-040, SR-041, SR-042
- **Done when:** Three sample questions answered in CoWork

```text
Implement SR-043. Read L10 (Agent, CoWork registration). Write 504_agent.sql and 505_cowork.sql, and create the agent. Ask it the four sample questions through SNOWFLAKE.CORTEX.DATA_AGENT_RUN, and show which tools each answer called. If the CoWork ADD AGENT statement fails, write it up for the organizers.
```

### SR-044 · Golden set (30 questions) and evaluation run

- **Stream:** Agent · **Role:** PM · **Estimate:** 2.5 h · **Scope:** MVP
- **Depends on:** SR-043
- **Done when:** At least 27 of 30 correct; OPS.EVAL_RESULT filled

```text
Help with SR-044. Read T3. From the latest run, propose 30 golden questions with real brand and market names in the T3 mix, each with EXPECTED_SQL, TOOL_ARGS and CHECK_TYPE, as eval/golden_set.csv. Then write eval/run_eval.py and eval/run_eval.sql, run --tools-only, then the full set, and sort the failures with the T3 triage.
```

## Phase 5: app and delivery

### SR-050 · Streamlit: Radar home and replay button

- **Stream:** Delivery · **Role:** APP · **Estimate:** 3 h · **Scope:** MVP
- **Depends on:** SR-026, SR-033
- **Done when:** Replay shows a new brief without errors

```text
Implement SR-050. Read L11 and the sr-streamlit skill. Write streamlit/snowflake.yml, environment.yml, .streamlit/config.toml, streamlit_app.py, admin_app.py, sr_ui/nav.py, sr_ui/data.py, sr_ui/format.py and pages/0_Radar.py with the replay panel, plus sql/40_app/415_ui_objects.sql. Deploy both apps and show the Radar for the current run.
```

### SR-051 · Streamlit: shift detail (waterfall, where, flow, artefact, what-if)

- **Stream:** Delivery · **Role:** APP · **Estimate:** 3 h · **Scope:** MVP
- **Depends on:** SR-022 to SR-029
- **Done when:** T-UI-01 passes

```text
Implement SR-051. Read L11 (Pages, Charts). Write sr_ui/charts.py and pages/1_Shift_detail.py. Write and run T-UI-01, redeploy, and check one shift end to end.
```

### SR-052 · Streamlit: brief page with provenance, Trust page

- **Stream:** Delivery · **Role:** APP · **Estimate:** 2.5 h · **Scope:** MVP
- **Depends on:** SR-032, SR-044
- **Done when:** Every number shows its source

```text
Implement SR-052. Read L11 (Pages), L14 and T1. Write pages/2_Brief.py, 3_Trust.py and 4_Settings.py. Write and run T-UI-02, redeploy, and check that every Trust tile has data.
```

### SR-054 · Email notification and alert on new brief

- **Stream:** Delivery · **Role:** APP · **Estimate:** 1.5 h · **Scope:** MVP
- **Depends on:** SR-032
- **Done when:** Email received for a published brief

```text
Implement SR-054. Read L9 (Delivery). Write 603_notifications.sql and 604_alert.sql. Publish a brief, and confirm that NOTIFY_LOG shows SENT and the email arrived.
```

## Phase 6: ship

### SR-060 · Time the manual share review with 2–3 analysts

- **Stream:** Ship · **Role:** PM · **Estimate:** 1 h · **Scope:** MVP
- **Depends on:** —
- **Done when:** Minutes per review recorded

*Human work, no prompt (T7).*

### SR-061 · End-to-end timing and dry run

- **Stream:** Ship · **Role:** PM · **Estimate:** 1 h · **Scope:** MVP
- **Depends on:** All MVP tickets
- **Done when:** Replay to email within target

```text
Run the dry-run checklist in docs/demo_script.md: reset the replay to the demo start week, run run_all.sql with RUN_E2E set to TRUE, run the golden set, and summarise anything that failed.
```

### SR-062 · Demo video, 5 minutes max

- **Stream:** Ship · **Role:** PM · **Estimate:** 4 h · **Scope:** MVP
- **Depends on:** SR-061
- **Done when:** Video under 5:00 uploaded

*Human work, no prompt (T7).*

### SR-063 · Solution brief, 1–2 pages

- **Stream:** Ship · **Role:** PM · **Estimate:** 2 h · **Scope:** MVP
- **Depends on:** SR-061
- **Done when:** Reviewed by the team

```text
Draft docs/solution_brief.md, two pages, from docs/HLD.md and docs/LLD.md, the Trust page numbers (OPS.EVAL_RESULT, OPS.V_RUN_COST, OPS.COCO_LOG) and docs/decisions.md, for me to edit.
```

### SR-064 · Code freeze, README, submission

- **Stream:** Ship · **Role:** All · **Estimate:** 1 h · **Scope:** MVP
- **Depends on:** SR-062, SR-063
- **Done when:** Submitted before 23 Nov, 11:59 PM IST

*Human work, no prompt (T7).*

## Stretch (only when every MVP ticket is done)

### SR-028 · Early warning: ANOMALY_DETECTION on lever series

- **Stream:** Intelligence · **Role:** AI · **Estimate:** 1.5 h · **Scope:** Stretch
- **Depends on:** SR-021, SR-027
- **Done when:** T-EW-02 passes

```text
Stretch. /plan Implement SR-028 only once SR-027 passes. Read L7 (ML.AD_LEVERS). Write sql/30_ml/303_sp_ml_lever_anomaly.sql so that it sets EARLY_WARNING.ML_CONFIRMED, then write and run T-EW-02.
```

### SR-045 · Methodology skill attached to the agent

- **Stream:** Agent · **Role:** AI · **Estimate:** 1 h · **Scope:** Stretch
- **Depends on:** SR-043
- **Done when:** Agent explains the method when asked "how"

```text
Stretch. /plan Implement SR-045 only once the golden set passes. Read L10 (Stretch). Upload .cortex/skills/share-methodology to @SR_DB.SEM.SKILLS and attach it to the agent's live version. Rerun the golden set and compare the score.
```

### SR-055 · Teams webhook notification

- **Stream:** Delivery · **Role:** APP · **Estimate:** 1 h · **Scope:** Stretch
- **Depends on:** SR-054
- **Done when:** Teams message received

```text
Stretch. /plan Implement SR-055 only once SR-054 works. Read L9 (Teams). Create the secret and the webhook integration, and extend SP_NOTIFY_NEW_BRIEFS for TEAMS_ENABLED. Send one test message.
```

### SR-057 · Data metric functions on the fact adapter

- **Stream:** Delivery · **Role:** DE · **Estimate:** 1 h · **Scope:** Stretch
- **Depends on:** SR-003
- **Done when:** DMF results visible

```text
Stretch. /plan Implement SR-057. Write sql/60_ops/605_dmf.sql, which attaches data metric functions for row count and nulls in VALUE_SALES to the scope's fact source, and show their first results.
```
