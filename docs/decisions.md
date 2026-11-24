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
