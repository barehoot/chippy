# Decisions log

Decisions taken while building, on top of D1–D11 in docs/HLD.md. Each entry says what was decided, why, and
what to do if it turns out wrong. Measured numbers (credits, minutes, golden-set score) are recorded here as
they are measured, never estimated.

## Status of the HLD assumptions

| ID | Assumption | Status | Evidence / next step |
| --- | --- | --- | --- |
| A1 | At least 104 weeks of history | Open | `OPS.CAPABILITY.N_WEEKS` after SR-003 |
| A2 | Item-level %ACV exists | Open | `OPS.CAPABILITY.HAS_DIST`; bridge mode falls back automatically |
| A3 | Base (non-promoted) sales exist | Open | `OPS.CAPABILITY.HAS_BASE_VALUE`, `HAS_BASE_UNITS` |
| A4 | Retailer markets roll up to a parent | Open | SR-004 scope query |
| A5 | Cortex Agents, CoWork, AI_COMPLETE, ML functions enabled | Open | `sql/00_setup/009_feature_smoke_test.sql` |
| A6 | Notification integrations can be created | Open | Ask organizers; `sql/60_ops/603_notifications.sql` |
| A7 | Team database and warehouse exist | Open | `sql/00_setup/001_roles_wh_db.sql` creates them if not |
| A8 | One focus manufacturer and category chosen | Open | SR-004 |

## Build decisions

- **B01 Settings rerun safety (SR-002).** `002_settings.sql` overwrites a stored value only while it still holds a
  `<placeholder>`; otherwise a rerun only refreshes the description. The LLD version reset every value on rerun,
  which would put `AS_OF_WEEK_END` back to `"<yyyy-mm-dd>"` and break every dynamic table on the next deploy.
- **B02 Two new threshold keys (SR-024).** `ART_RESTATE_PCT` (R3's "1%") and `ART_RECODE_MIN_SHARE` (R4's "20%")
  are settings rather than literals, per AGENTS.md rule 4. The 13-week window in R5 stays a structural constant.
- **B03 Bridge residual is NULL when nothing was decomposed (SR-022).** In mode D, and for NEW, EXIT and NO_DATA
  rows, `RESIDUAL_PTS` is NULL instead of `100 * D_SHARE`. The LLD formula made the residual equal the whole change
  in mode D, which contradicts T-BR-01 ("every OK row has |residual| < 1e-6") on any account without %ACV. Found by
  the randomised property test in `python/tests/test_bridge.py`.
- **B04 Suppression looks only at earlier weeks (SR-026).** The look-back takes the latest successful run of
  each of the last `SUPPRESS_RUNS` as-of weeks before the current one. Counting every run would make a forced
  rerun of the same week ("Rerun this week" in the admin app) suppress everything it selected the first time,
  so the rerun's brief would come out empty. T-RANK-02 (two consecutive replay weeks) is unaffected.
- **B05 One comparison per brand and market in the brief (SR-026).** If a brand x market passes the gates on
  several comparisons, only its highest-scoring one is eligible for selection; the others keep their rank and
  carry the reason "Another comparison of this brand and market ranks higher". Without it, "L4W vs YA" and
  "L12W vs YA" for the same brand can take two of the five brief slots. Remove the `BEST_CMP` term in
  `406_sp_rank.sql` to undo.
- **B06 Lever-model verdicts are stored (SR-028, stretch).** `SP_ML_LEVER_ANOMALY` keeps each scored latest week
  in the new table `ML.AD_LEVERS_RESULT`, so T-EW-02 can check `ML_CONFIRMED` against what the model said. It runs
  as an optional, cost-capped step `EW_ML` (step 11) after `EARLY_WARNING`.
- **B07 T-E2E-03 simulates the overlap (SR-053).** Snowflake does not run two executions of one task at the same
  time; it skips the second. So "T_RUN_WEEK_MANUAL executed twice" cannot produce two runs. The test inserts a
  RUNNING marker row, checks that `SP_RUN_WEEK` writes a SKIPPED/BUSY row and that `SP_REPLAY_NEXT_WEEK` returns
  BUSY, then removes the marker. Replay-based E2E tests (T-ART-05, T-RANK-02) suspend `T_RUN_WEEK` while they
  move the as-of week, so the triggered task cannot race them, and put the week back at the end.
- **B08 Procedures in 60_ops are created as SR_DEV (SR-053).** L12 gives `SR_APP` no `CREATE PROCEDURE` on `APP`.
  `SP_RUN_FROM_STREAM`, `SP_REPLAY_NEXT_WEEK`, `SP_REPLAY_RESET` and `SP_NOTIFY_NEW_BRIEFS` are created as
  `SR_DEV` (caller's rights, so ownership does not change what they can do); streams, tasks and alerts are
  created as `SR_APP`, so they run as `SR_APP`.
- **B09 `SEM.V_TOOL_BRIDGE.IN_SCOPE` (SR-040).** Tool procedures may read only `SEM.V_TOOL_*` views, and none of the
  L12 views says which markets the artefact gate checks. The added boolean column lets `TOOL_CHECK_ARTEFACT` answer
  `NOT_CHECKED` outside the scope (L10) and lets `TOOL_GET_SHARE_BRIDGE` report the same. Additive; no rename.
- **B10 Grants L12 left implicit (SR-056).** `SR_ANALYST` gets `USAGE` on `APP.SP_RESOLVE` (every tool calls it as
  the caller); `SR_UI` gets `SELECT` on `OPS.NOTIFY_LOG` (the Brief page's "emailed" chip). The email integration's
  allowed recipients are mirrored into the setting `NOTIFY_ALLOWED` by `603_notifications.sql`, because the admin
  app may not run `DESCRIBE INTEGRATION` to validate `NOTIFY_EMAILS` (L11).
