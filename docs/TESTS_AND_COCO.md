# Tests & CoCo

Tests define done for every ticket, and the CoCo files below make CoCo follow this design without being reminded.

## T1 Test strategy and fixtures

A ticket is done when its named tests pass (T2). Tests run in six layers, cheapest first. SQL tests check properties of the real pipeline output, such as exact sums, gates, labels and grants. Hand-computed exact values live in pytest, where inputs can be controlled. Every test has an ID `T-<AREA>-NN` and its own file.

| Layer | What it proves | Where | How to run | When |
| --- | --- | --- | --- | --- |
| SQL assertions | Properties of real outputs: sums, exactness, gates, labels, grants | `tests/sql/T-*.sql` | `snow sql -f tests/sql/run_all.sql -c sr` | After each ticket; before each gate |
| Python unit | Bridge mirror, validator, renderer, fallback, UI frames and formatting, against hand-computed values | `python/tests/` | `pytest -q python/tests` | On every change to `sr_lib` or `sr_ui` |
| Python integration | SQL and Python agree on real rows | `python/tests/`, marker `integration` | `pytest -q -m integration python/tests` | After SR-022 and before freeze |
| End to end | A whole run, its failure modes, overlap, credit cap | `tests/sql/T-E2E-*.sql` | Part of `run_all.sql` when `$RUN_E2E = TRUE` | Before each gate; after every deploy |
| Golden set | The agent picks the right tool and states the right number | `eval/` (T3) | `python3 eval/run_eval.py --connection sr` | After any agent, tool or semantic view change; Saturday gate |
| Manual | Demo path, email arrival, video | `docs/demo_script.md` | Dry run (SR-061) | Saturday |

**SQL test format.** Each file appends one row to `OPS.TEST_RESULT`. The CTE `failures` returns one row per failure, so zero rows means pass. `run_all.sql` sets the session variables, sources every file in ID order, and prints the failures. The Trust page shows the latest test run next to the golden set.

```sql
-- sql/00_setup/003_ops_tables.sql gains:
CREATE TABLE IF NOT EXISTS SR_DB.OPS.TEST_RESULT (
  TEST_RUN_ID VARCHAR(36)   NOT NULL,
  TEST_ID     VARCHAR(16)   NOT NULL,
  PASSED      BOOLEAN       NOT NULL,
  FAILURES    NUMBER(9,0)   NOT NULL,
  DETAIL      VARIANT,                    -- up to 20 failing rows, as objects
  RAN_AT      TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- tests/sql/T-BR-01.sql: every OK bridge row adds up exactly
SET TEST_ID = 'T-BR-01';
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
WITH failures AS (
  SELECT SHIFT_ID, RESIDUAL_PTS
  FROM SR_DB.APP.SHARE_BRIDGE
  WHERE RUN_ID = $RUN_UNDER_TEST AND STATUS = 'OK' AND ABS(RESIDUAL_PTS) >= 1e-6
)
SELECT $TEST_RUN_ID, $TEST_ID, COUNT(*) = 0, COUNT(*),
       (SELECT ARRAY_AGG(OBJECT_CONSTRUCT(*)) FROM (SELECT * FROM failures LIMIT 20))
FROM failures;

-- tests/sql/run_all.sql
USE ROLE SR_DEV;
USE SECONDARY ROLES NONE;
USE WAREHOUSE SR_WH_XS;
SET TEST_RUN_ID = UUID_STRING();
SET RUN_UNDER_TEST = (SELECT RUN_ID FROM SR_DB.OPS.RUN_LOG WHERE STATUS = 'SUCCEEDED' ORDER BY STARTED_AT DESC LIMIT 1);
SET RUN_E2E = FALSE;                                      -- TRUE before gates: E2E files start runs and take minutes
!source tests/sql/000_fixtures.sql
!source tests/sql/T-SRC-01.sql
-- … one !source line per test file, in ID order; E2E files return early unless $RUN_E2E
SELECT TEST_ID, PASSED, FAILURES, DETAIL
FROM SR_DB.OPS.TEST_RESULT WHERE TEST_RUN_ID = $TEST_RUN_ID
ORDER BY PASSED, TEST_ID;
```

**Tests that expect an error.** Security tests switch to the role under test and try each forbidden statement inside its own `BEGIN … EXCEPTION` block. The block returns the statements that wrongly succeeded, as text. The test then switches back and records that text through `RESULT_SCAN`, because the role under test cannot write the result itself.

```sql
-- tests/sql/T-SEC-01.sql (abridged)
SET TEST_ID = 'T-SEC-01';
USE ROLE SR_JUDGE;
USE SECONDARY ROLES NONE;
EXECUTE IMMEDIATE $$
DECLARE
  fails ARRAY DEFAULT ARRAY_CONSTRUCT();
BEGIN
  BEGIN
    INSERT INTO SR_DB.OPS.SETTINGS (SETTING_KEY, SETTING_VALUE) SELECT 'X', TO_VARIANT(1);
    fails := ARRAY_APPEND(fails, 'insert into OPS.SETTINGS succeeded');
  EXCEPTION WHEN OTHER THEN NULL;
  END;
  BEGIN
    EXECUTE TASK SR_DB.OPS.T_RUN_WEEK_MANUAL;
    fails := ARRAY_APPEND(fails, 'EXECUTE TASK succeeded');
  EXCEPTION WHEN OTHER THEN NULL;
  END;
  -- … SELECT on APP.SHIFT_RANKED must fail; SELECT on SEM.V_SEM_SHARE_CHANGE must succeed
  RETURN ARRAY_TO_STRING(fails, '; ');
END;
$$;
SET Q = LAST_QUERY_ID();
USE ROLE SR_DEV;
INSERT INTO SR_DB.OPS.TEST_RESULT (TEST_RUN_ID, TEST_ID, PASSED, FAILURES, DETAIL)
SELECT $TEST_RUN_ID, $TEST_ID, $1 = '', IFF($1 = '', 0, ARRAY_SIZE(SPLIT($1, '; '))), TO_VARIANT($1)
FROM TABLE(RESULT_SCAN($Q));
```

Entitlement tests do not need a second user. As `SR_DEV`, which owns the policy, they add a `USER` entitlement for a made-up user, run the query under `EXECUTE USING POLICY_CONTEXT(CURRENT_USER => 'SR_TEST_USER', CURRENT_ROLE => 'PUBLIC') AS SELECT …`, and delete the entitlement afterwards. If the account lacks policy simulation, a real test user with only `SR_ANALYST` runs the same query.

**Fixtures** (`tests/sql/000_fixtures.sql`, schema `SR_DB.TEST`). There are only two, because the rest is real data:

```sql
CREATE TABLE IF NOT EXISTS SR_DB.TEST.FX_RECON_REFERENCE (     -- the five numbers SR-013 reconciles against
  CHECK_ID        VARCHAR(8) PRIMARY KEY,
  DESCRIPTION     VARCHAR NOT NULL,
  PERIOD_CODE     VARCHAR(8) NOT NULL,
  MARKET_ID       VARCHAR NOT NULL,
  CATEGORY        VARCHAR NOT NULL,
  BRAND           VARCHAR,                      -- NULL for a category total
  METRIC          VARCHAR(16) NOT NULL,         -- VALUE_SALES | VALUE_SHARE | DIST_SHARE
  REFERENCE_VALUE FLOAT NOT NULL,
  SOURCE_NOTE     VARCHAR NOT NULL              -- which NIQ report and page the number came from
);
CREATE TABLE IF NOT EXISTS SR_DB.TEST.FX_DEMO_EVENTS (         -- real data events the demo replays into
  EVENT_ID         VARCHAR(8) PRIMARY KEY,
  AS_OF_WEEK       DATE NOT NULL,
  CMP_CODE         VARCHAR(16) NOT NULL,
  MARKET_ID        VARCHAR NOT NULL,
  EXPECTED_RULE_ID VARCHAR(16) NOT NULL,       -- for example R2_FEED
  NOTE             VARCHAR NOT NULL              -- what Input Validation recorded about it
);
```

Pytest cases with hand-computed values live in `python/tests/cases.py`, one `dict` per case, with the inputs and the expected outputs written out by hand.

**What must pass at each gate**

| Gate | Time | Must pass |
| --- | --- | --- |
| Grid reconciles | Wed 18 Nov, 11 PM | T-SRC-01..03, T-CORE-01..04 |
| First verified brief | Thu 19 Nov, 11 PM | The above, plus T-DET, T-BR, T-ART-01..04, T-RANK-01, T-FP-01, T-NAR-01..05, T-E2E-01 |
| Feature freeze | Fri 20 Nov, 8 PM | Every MVP test, including T-E2E-01..04, T-TOOL-01..05, T-UI-01..02 and T-SEC-01..03 |
| Golden set and dry run | Sat 21 Nov, 8 PM | Golden set at least 27/30, T-ART-05, T-RANK-02, and the manual dry run |

At feature freeze, take a zero-copy rollback point with `CREATE DATABASE SR_DB_FREEZE CLONE SR_DB;`. If a late change breaks the demo, the team can point the apps back at the frozen state rather than debug under time pressure.

## T2 Named test cases

One row per test. **Kind** says where it lives: `SQL` is `tests/sql/<ID>.sql`, `py` is `python/tests/`, `py-int` is pytest with the `integration` marker, and `E2E` is `tests/sql/<ID>.sql` with `$RUN_E2E`. Tolerances are absolute unless marked. "A finished run" means `$RUN_UNDER_TEST`.

| ID | Kind | Given | Then (pass) | Ticket |
| --- | --- | --- | --- | --- |
| T-SRC-01 | SQL | The adapter views exist | Every contract column in L3 exists in `V_SRC_FACT_WEEKLY_ALL`, `V_SRC_PRODUCT` and `V_SRC_MARKET`, with the contract type family (`INFORMATION_SCHEMA.COLUMNS`) | SR-003 |
| T-SRC-02 | SQL | The last 8 weeks of facts | No duplicate (`WEEK_END_DATE`, `MARKET_ID`, `PRODUCT_ID`); `ACV_DIST_PCT` between 0 and 100; every product and market ID resolves in its view | SR-003 |
| T-SRC-03 | SQL | `AS_OF_WEEK_END` set to a real week | The adapter's latest week equals it; the newest `OPS.CAPABILITY` row has a mode from A to D; with the setting one week past the data, `SP_CAPABILITY_CHECK` raises `NO_DATA` (setting restored afterwards) | SR-003 |
| T-CORE-01 | SQL | Period tables refreshed | For every period, market and category, shares over all brands, private label included, sum to 1 within 1e-9 | SR-012 |
| T-CORE-02 | SQL | `DT_BRAND_WEEK` refreshed | Per week and market, brand value sales sum to the adapter's scope-category sales within 0.01 | SR-011 |
| T-CORE-03 | SQL | The five rows of `TEST.FX_RECON_REFERENCE` | Each Share Radar value is within 0.05 pts (shares) or 0.5% relative (sales); every `OPS.RECON_RESULT` row is `PASSED` | SR-013 |
| T-CORE-04 | SQL | `DT_PERIOD_WEEK` refreshed | Each period has `EXPECTED_WEEKS` weeks where history allows; L4W ends at the as-of week; L4W\_YA sits exactly 52 weeks earlier; a comparison without base data has NULL `CS0` | SR-010 |
| T-DET-01 | SQL | A finished run | Each candidate with `PASSED_GATES` meets all three gates, recomputed from `DT_SHARE_COMPARE` and the settings, and no other candidate does | SR-020 |
| T-DET-02 | SQL | A finished run | `Z_SCORE` is NULL for every `L52W_VS_YA` candidate, and not NULL for other comparisons where the brand has at least 70 weeks of history | SR-020 |
| T-ML-01 | SQL | A finished run | `ANOMALY_WEEKS` between 0 and 4; `ANOMALY_CONFIRMED` equals `ANOMALY_WEEKS >= 2`; if `ML_ANOMALY` logged `WARN`, the run is still `SUCCEEDED` | SR-021 |
| T-BR-01 | SQL | A finished run | Every `SHARE_BRIDGE` row with `STATUS = 'OK'` has `ABS(RESIDUAL_PTS) < 1e-6` | SR-022 |
| T-BR-02 | py-int | 200 random rows of `DT_SHARE_COMPARE` and the run's capability mode | `APP.V_BRIDGE_ALL` terms equal `sr_lib.bridge.bridge()` within 1e-9 on every row | SR-022 |
| T-BR-03 | SQL, py | Rows with S0 = 0, S1 = 0, or a missing category total; and `log_mean` edge inputs | Status `NEW`, `EXIT` or `NO_DATA`, with NULL terms; `log_mean(a, a) == a`; `log_mean(a, a * (1 + 1e-15))` is finite and within 1e-12 of `a` | SR-022 |
| T-BR-04 | py, SQL | Inputs missing base units, then units, then TDP | `pick_mode` returns B, then C, then D; no SQL row's `MODE` is better than the capability cap | SR-022 |
| T-BR-05 | py | The hand-computed toy case in `cases.py` | `bridge()` returns each hand-computed term within 1e-12, and the terms sum to the share change | SR-022 |
| T-WH-01 | SQL | Ranked shifts in the parent market | Over all retailers plus the remainder, `PERF_PTS + MIX_PTS` sums to `100 * D_SHARE` within 1e-6 | SR-023 |
| T-WH-02 | SQL | A finished run | At most 5 `TOP_INSIGHTS` rows per shift; when that step logged `WARN`, the `EXACT_RETAILER` rows still exist | SR-023 |
| T-ART-01 | SQL | A finished run | Every child market with category sales in one period and none in the other has an `R2_FEED` row on its parent, recomputed independently, and there are no other `R2_FEED` rows | SR-024 |
| T-ART-02 | SQL | A finished run | `R6_GAP` rows exist exactly where `CAT_WEEKS1` or `CAT_WEEKS0` is below `EXP_WEEKS` | SR-024 |
| T-ART-03 | SQL | Two successful runs with snapshots | Where a week inside the compared periods has a different `ROW_HASH` between them, an `R3_RESTATE` row exists | SR-024 |
| T-ART-04 | SQL | A finished run | The label is `POSSIBLE_DATA_EFFECT` exactly when a HIGH rule matches the shift's market or brand, `MIXED` when only MEDIUM rules match, and `MARKET_MOVE` otherwise | SR-024 |
| T-ART-05 | E2E | Each row of `TEST.FX_DEMO_EVENTS` | After replaying to its week, the expected rule fires on that market, and the shift is held back from the brief | SR-024 |
| T-FLOW-01 | SQL | A finished run | Each losing brand's outflows sum to `100 * ABS(D_SHARE)` within 1e-6 | SR-025 |
| T-FLOW-02 | SQL | A finished run | Each gaining brand's inflows sum to `100 * D_SHARE` within 1e-6 | SR-025 |
| T-RANK-01 | SQL | A finished run | At most `TOP_N` rows `SELECTED`, none labelled `POSSIBLE_DATA_EFFECT`; `SCORE` recomputed from its parts within 1e-9; `RANK_NO` contiguous from 1 | SR-026 |
| T-RANK-02 | E2E | Two consecutive replay weeks | A shift selected in week 1, with the same sign and growth below `SUPPRESS_GROWTH`, is `SUPPRESSED` in week 2 | SR-026 |
| T-EW-01 | SQL | A finished run | `PROJECTED_SHARE_PTS` equals 100 × s(L4W) × (DS latest ÷ DS L4W − 1) within 1e-9; only rows with `LEVER_CHG <= EW_DIST_DROP` are `DIST_DROP` | SR-027 |
| T-EW-02 | SQL | A run with the stretch lever model | `ML_CONFIRMED` is true only where the lever model flagged the latest week | SR-028 |
| T-WI-01 | SQL | A ranked mode-A shift, and a mode-B shift | `DISTRIBUTION` with `BASE` gives `share_if_pts = 100 * SH1 * DS0 / DS1` within 1e-9; `PROMO` on the mode-B shift returns an error object | SR-029 |
| T-FP-01 | SQL | The latest fact pack | Every fact has `v`, `u`, `d` and `src`; every fact ID used under `shifts` exists; `N_FACTS` matches; 10 random facts equal the column their `src` names | SR-030 |
| T-NAR-01 | py | An LLM reply with a bare number in `why` | `validate_brief` returns `V03` at that path | SR-032 |
| T-NAR-02 | py | An unknown placeholder, and shifts out of order | `V02` and `V05` | SR-032 |
| T-NAR-03 | py | A gain word in a LOSS title, and a 130-character title | `V04` and `V07` | SR-032 |
| T-NAR-04 | E2E | `LLM_MODEL` and `LLM_FALLBACK_MODEL` set to a name that does not exist | `SP_WRITE_BRIEF` publishes `GENERATOR = 'TEMPLATE'` with no violations; settings restored | SR-032 |
| T-NAR-05 | py | A template brief, and LLM text containing a script tag | Every number in `BODY_HTML` sits in a span whose `title` is its fact's `src`; the script tag is escaped | SR-032 |
| T-E2E-01 | E2E | The current week | `CALL SP_RUN_WEEK('MANUAL', TRUE)` gives `RUN_LOG` `SUCCEEDED`, 14 step rows, one `PUBLISHED` brief, and a `SENT` row in `NOTIFY_LOG` within 5 minutes | SR-033 |
| T-E2E-02 | E2E | The T-NAR-04 settings, through a whole run | The run is `SUCCEEDED` and the brief's generator is `TEMPLATE` | SR-033 |
| T-E2E-03 | E2E | `T_RUN_WEEK_MANUAL` executed twice within a minute | The second run row is `SKIPPED` with reason `BUSY`, and `SP_REPLAY_NEXT_WEEK` returns `BUSY` meanwhile | SR-053 |
| T-E2E-04 | E2E | `MAX_CREDITS_PER_RUN = 0` | `ML_ANOMALY` and `TOP_INSIGHTS` are `SKIPPED` with "credit cap"; the run is `SUCCEEDED`; setting restored | SR-033 |
| T-TOOL-01 | SQL | 5 brand and market pairs from the latest run | `TOOL_GET_SHARE_BRIDGE` returns `change_pts` equal to `100 * D_SHARE` in `SEM.V_TOOL_BRIDGE` within 1e-9 | SR-042 |
| T-TOOL-02 | SQL | The ranked shifts, and one market outside the scope | `TOOL_CHECK_ARTEFACT` returns the shift's `ARTEFACT_LABEL`; the outside market returns `NOT_CHECKED` | SR-042 |
| T-TOOL-03 | SQL | 5 losing brands | `TOOL_SHARE_FLOW` flows sum to the brand's change within 1e-6 | SR-042 |
| T-TOOL-04 | SQL | A ranked shift | `TOOL_WHAT_IF` equals `SP_WHAT_IF`; `TOOL_LATEST_BRIEF` returns the newest `PUBLISHED` brief ID | SR-042 |
| T-TOOL-05 | SQL | A brand with one typo, an unknown brand, a 3-letter prefix shared by two brands, and comparison `XYZ` | `OK`, `NOT_FOUND` with at most 3 candidates, `AMBIGUOUS`, `BAD_INPUT` | SR-042 |
| T-UI-01 | py | A mode-A bridge row, and a mode-D row | `bridge_frame` gives 4 terms plus the total, adding up within 1e-9; mode D gives the total only | SR-051 |
| T-UI-02 | py | 50 sample values across all units | `format.py` and `render.format_fact` give identical strings | SR-052 |
| T-SEC-01 | SQL | Role `SR_JUDGE`, no secondary roles | Writes, `APP` table reads and `EXECUTE TASK` all fail; reading the `SEM` views succeeds | SR-056 |
| T-SEC-02 | SQL | A `USER` entitlement for one retailer, simulated with `POLICY_CONTEXT` (T1) | The `SEM` views return only that retailer's rows; `SP_RESOLVE` for a brand sold only elsewhere returns `NOT_FOUND` | SR-056 |
| T-SEC-03 | SQL | After deploy | `INFORMATION_SCHEMA.POLICY_REFERENCES` shows `RAP_ENTITLED` on all seven `SEM` views | SR-056 |

Run one test with `snow sql -f tests/sql/T-BR-01.sql -c sr`, after setting the three session variables as `run_all.sql` does. Run one pytest with `pytest -q python/tests/test_bridge.py -k T_BR_05`; pytest functions carry the test ID in their name, such as `test_T_BR_05_toy_case`.

## T3 Golden set and scoring

Thirty questions that an NIQ client-service analyst would really ask, written with real brand and market names in SR-044. The bar is **27 of 30**. Expected answers are not typed in. Each row carries a SQL query that computes the expected value from the governed views when the eval runs, so the golden set stays right as the replay moves the as-of week.

| Type | Count | Example question | Expected tool | Check |
| --- | --- | --- | --- | --- |
| `WHY` | 8 | Why did \<brand> lose share in \<market> in the last 4 weeks vs year ago? | `get_share_bridge` | `VALUE_PTS`: the share change |
| `WHO` | 5 | Who took the share \<brand> lost in \<market>? | `share_flow` | `NAME`: the largest gainer |
| `REAL` | 4 | Is the \<brand> drop in \<market> real or a data effect? | `check_artefact` | `LABEL` |
| `WHATIF` | 3 | What if \<brand> restored distribution to last year's level in \<market>? | `what_if` | `VALUE_PTS`: the share if |
| `NUMBER` | 6 | What is \<brand>'s value share in \<market> over the last 12 weeks? | `share_analyst` | `VALUE_PCT` or `VALUE_MONEY` |
| `METHOD` | 2 | How is TDP calculated? | `method_search` | `PHRASE` from the knowledge base |
| `REFUSE` | 2 | What is \<brand>'s average share across all markets? What will it be next quarter? | None required | `REFUSE`: no figure stated |

**File format** (`eval/golden_set.csv`, loaded into `OPS.GOLDEN_SET` by `run_eval.py --load`). `TOOL_ARGS` is filled for the four custom-tool types, so a tool-only run can check them without the LLM. `EXPECTED_SQL` returns one value and runs as `SR_DEV`.

```text
QUESTION_ID,QTYPE,QUESTION,EXPECTED_TOOL,TOOL_ARGS,EXPECTED_SQL,CHECK_TYPE,TOLERANCE
G01,WHY,"Why did <brand> lose share in <market> in the last 4 weeks vs year ago?",get_share_bridge,"{""p_brand"":""<brand>"",""p_market"":""<market>"",""p_cmp_code"":""L4W_VS_YA""}","SELECT 100 * D_SHARE FROM SR_DB.SEM.V_TOOL_BRIDGE WHERE BRAND = '<brand>' AND MARKET_NAME = '<market>' AND CMP_CODE = 'L4W_VS_YA'",VALUE_PTS,0.05
G09,WHO,"Who took the share <brand> lost in <market>?",share_flow,"{""p_brand"":""<brand>"",""p_market"":""<market>"",""p_cmp_code"":""L4W_VS_YA""}","SELECT f.TO_BRAND FROM SR_DB.SEM.V_TOOL_FLOW f JOIN SR_DB.SRC.V_SRC_MARKET m ON m.MARKET_ID = f.MARKET_ID WHERE f.FROM_BRAND = '<brand>' AND m.MARKET_NAME = '<market>' AND f.CMP_CODE = 'L4W_VS_YA' ORDER BY f.FLOW_PTS DESC LIMIT 1",NAME,0
G14,REAL,"Is the <brand> drop in <market> real or a data effect?",check_artefact,"{""p_market"":""<market>"",""p_cmp_code"":""L4W_VS_YA"",""p_brand"":""<brand>""}","SELECT ARTEFACT_LABEL FROM SR_DB.APP.SHIFT_RANKED WHERE RUN_ID = (SELECT RUN_ID FROM SR_DB.OPS.RUN_LOG WHERE STATUS = 'SUCCEEDED' ORDER BY STARTED_AT DESC LIMIT 1) AND BRAND = '<brand>' AND MARKET_ID = '<market_id>' AND CMP_CODE = 'L4W_VS_YA'",LABEL,0
G18,WHATIF,"What if <brand> restored distribution to last year's level in <market>?",what_if,"{""p_brand"":""<brand>"",""p_market"":""<market>"",""p_lever"":""DISTRIBUTION"",""p_target"":""BASE""}","SELECT 100 * SH1 * DS0 / DS1 FROM SR_DB.SEM.V_TOOL_BRIDGE WHERE BRAND = '<brand>' AND MARKET_NAME = '<market>' AND CMP_CODE = 'L4W_VS_YA'",VALUE_PTS,0.05
G21,NUMBER,"What is <brand>'s value share in <market> over the last 12 weeks?",share_analyst,,"SELECT 100 * g.VALUE_SHARE FROM SR_DB.CORE.V_SHARE_GRID g JOIN SR_DB.SRC.V_SRC_MARKET m ON m.MARKET_ID = g.MARKET_ID WHERE g.PERIOD_CODE = 'L12W' AND g.BRAND = '<brand>' AND m.MARKET_NAME = '<market>'",VALUE_PCT,0.05
G27,METHOD,"How is TDP calculated?",method_search,,"SELECT 'sum of'",PHRASE,0
G29,REFUSE,"What is <brand>'s average share across all markets?",,,"SELECT NULL",REFUSE,0
```

```sql
-- eval/run_eval.sql: table DDL and the report queries
CREATE TABLE IF NOT EXISTS SR_DB.OPS.GOLDEN_SET (
  QUESTION_ID   VARCHAR(8)  NOT NULL PRIMARY KEY,
  QTYPE         VARCHAR(8)  NOT NULL,
  QUESTION      VARCHAR     NOT NULL,
  EXPECTED_TOOL VARCHAR(32),
  TOOL_ARGS     VARIANT,
  EXPECTED_SQL  VARCHAR     NOT NULL,
  CHECK_TYPE    VARCHAR(12) NOT NULL,   -- VALUE_PTS | VALUE_PCT | VALUE_MONEY | NAME | LABEL | PHRASE | REFUSE
  TOLERANCE     FLOAT       NOT NULL DEFAULT 0
);

SELECT COUNT_IF(PASSED) || '/' || COUNT(*) AS SCORE, MAX(EVALUATED_AT) AS AT
FROM SR_DB.OPS.EVAL_RESULT
WHERE EVAL_RUN_ID = (SELECT EVAL_RUN_ID FROM SR_DB.OPS.EVAL_RESULT ORDER BY EVALUATED_AT DESC LIMIT 1);
```

**Scoring.** A question passes when its route and its check both pass.

| Check | Passes when |
| --- | --- |
| Route | `EXPECTED_TOOL` is among the tools the agent called. `REFUSE` rows have no route rule. |
| `VALUE_PTS`, `VALUE_PCT` | Some number in the answer is within `TOLERANCE` of the expected value: 0.05 share points, or 0.05 percentage points of share |
| `VALUE_MONEY` | Some money figure in the answer, with K, M or B expanded, is within 0.5% of the expected value |
| `NAME` | The expected brand or market name appears in the answer, ignoring case |
| `LABEL` | The answer uses the label's words: `MARKET_MOVE` is "market move" or "real"; `MIXED` is "mixed"; `POSSIBLE_DATA_EFFECT` is "data effect" |
| `PHRASE` | The phrase appears in the answer, ignoring case |
| `REFUSE` | The answer states no figure: no numbers other than period codes and digits inside names |

**Runner** (`eval/run_eval.py`). It runs from a builder's machine with the `sr` connection and needs no token. It calls the agent through [`SNOWFLAKE.CORTEX.DATA_AGENT_RUN`](https://docs.snowflake.com/en/sql-reference/functions/data_agent_run-snowflake-cortex), which takes the agent's full name and a JSON request body and returns JSON.

```python
from __future__ import annotations
import csv, json, re, uuid
from dataclasses import dataclass
from snowflake.snowpark import Session

AGENT = "SR_DB.SEM.SHARE_RADAR_AGENT"
PASS_BAR = 27
TOOL_FIELD = {"get_share_bridge": "change_pts", "share_flow": "flows[0].brand",
              "check_artefact": "label", "what_if": "share_if_pts"}      # used by --tools-only
LABEL_WORDS = {"MARKET_MOVE": ("market move", "real"), "MIXED": ("mixed",), "POSSIBLE_DATA_EFFECT": ("data effect",)}

@dataclass(frozen=True)
class GoldenRow:
    question_id: str
    qtype: str
    question: str
    expected_tool: str | None
    tool_args: dict | None
    expected_sql: str
    check_type: str
    tolerance: float

@dataclass(frozen=True)
class AgentAnswer:
    text: str
    tools: list[str]
    raw: dict

def load_golden(path: str = "eval/golden_set.csv") -> list[GoldenRow]: ...
def upload_golden(session: Session, rows: list[GoldenRow]) -> None: ...      # --load: replaces OPS.GOLDEN_SET
def expected_value(session: Session, row: GoldenRow) -> object: ...          # first column of the first row
def ask_agent(session: Session, question: str, timeout_s: int = 120) -> AgentAnswer:
    """SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(?, ?) with [AGENT, json.dumps({"messages": [{"role": "user",
    "content": [{"type": "text", "text": question}]}]})]. From the reply's content list: items of type tool_use give
    the tool name, items of type text give the answer. If the reply has status in_progress, poll
    SNOWFLAKE.CORTEX.THREAD_MESSAGES with its thread ID until done or timeout_s."""
def call_tool(session: Session, row: GoldenRow) -> object: ...               # --tools-only: CALL the TOOL_* procedure, read TOOL_FIELD
def numbers_in(text: str, ignore: set[str]) -> list[float]: ...             # "-0.84 pts", "23.4%", "INR 1.8M" -> -0.84, 23.4, 1800000.0
def score(row: GoldenRow, expected: object, ans: AgentAnswer) -> tuple[bool, str]: ...
def main(argv: list[str] | None = None) -> int:
    """--connection sr [--load] [--tools-only] [--only G01,G02]. Writes one OPS.EVAL_RESULT row per question
    under a new EVAL_RUN_ID, prints 'passed/total' and each failure with its reason, and returns 0 when
    passed >= PASS_BAR."""
```

**When it runs.** After SR-043, then after any change to the agent specification, a tool, the semantic view or the knowledge base. Before Saturday's gate, record the `EVAL_RUN_ID` in `docs/decisions.md`. `--tools-only` costs no AI credits, so run it after every SQL change to a tool or `SEM` view.

**Reading a failure.** If the route is wrong, sharpen the tool descriptions or the orchestration instructions (L10). If the route is right but the value is wrong, the bug is in the tool or the view, and `--tools-only` will show it. If the value is right but it is stated wrongly or not at all, fix the response instructions. If an Analyst number is wrong, tighten the semantic view's synonyms, metric comments or `AI_SQL_GENERATION` rule.

## T4 AGENTS.md

CoCo reads `AGENTS.md` at the start of every session, so the rules that must never be forgotten live there. The design lives in `docs/HLD.md`, `docs/LLD.md` and `docs/TESTS_AND_COCO.md`; re-export them from the team doc after any design change. Paste the file below as it is.

```markdown
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
```

## T5 CoCo skills

Each skill is a folder under `.cortex/skills/` holding one `SKILL.md`. CoCo loads a skill when its `description` matches the task, so each description names the files and situations it covers. The skills hold the how; `AGENTS.md` holds the rules. `share-methodology` is also the file uploaded to `@SR_DB.SEM.SKILLS` for the agent in the stretch ticket SR-045.

`.cortex/skills/sr-sql-conventions/SKILL.md`

```markdown
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
```

`.cortex/skills/share-methodology/SKILL.md`

```markdown
---
name: share-methodology
description: The retail measurement method behind Share Radar - ACV, TDP, velocity, value share, the exact LMDI share bridge and its modes, the retailer split, share flow, early warning and the data artefact rules. Use when writing or checking any calculation, a brief, knowledge-base text or an answer about why share moved.
---
# Share methodology

## Definitions
- %ACV distribution of an item: the share of all-commodity volume in stores selling it, 0 to 100.
- TDP (total distribution points) = sum of item %ACV; over a period, also summed across weeks.
- Value share = brand value sales / category value sales, within one market, category and period.
  Shares never add up or average across markets.
- Velocity = sales per TDP point. Price = value per unit. Promo index = actual value / base value.

## The bridge (L6)
- share = distribution share x velocity index x price index x promo index (mode A), each relative to the category.
- Points per term = 100 x L(s1, s0) x ln(F1 / F0), where L(a, b) = (a - b) / (ln a - ln b) and L(a, a) = a.
  The terms add up exactly to the change, so the residual is zero.
- Mode A: TDP, base units, base value, value -> four terms. Mode B: TDP, units, value -> distribution, unit
  velocity, price. Mode C: TDP, value -> distribution, value velocity. Mode D: no terms.
- NEW, EXIT and NO_DATA rows get no terms.

## Where and who
- Retailer split, exact: performance = average weight x change in within-retailer share;
  mix = average share x change in weight.
- Flow: a losing brand's points go to gainers in proportion to their gains. It is an accounting allocation;
  never call it switching.

## Early warning
- If the latest week's distribution share persists, next period's L4W share moves by about
  s(L4W) x (DS latest / DS L4W - 1), other levers held. It is mechanical, not a forecast.

## Data artefact rules (L6)
- R1 coverage, R2 feed, R3 restatement, R4 recode, R5 spike, R6 gap.
- Any HIGH rule -> POSSIBLE_DATA_EFFECT, held back from the brief. MEDIUM only -> MIXED.

## Writing about it
- Name the comparison every time, for example "last 4 weeks vs year ago". Put the largest term first.
- Say "share points" for changes, never "percent". Never state a number that no tool or fact returned.
```

`.cortex/skills/sr-cortex-agent/SKILL.md`

```markdown
---
name: sr-cortex-agent
description: How Share Radar's semantic view, search service, tool procedures and Cortex Agent are built and changed. Use when editing anything in sql/50_sem, sql/40_app/414_tool_procs.sql, kb/ or eval/golden_set.csv.
---
# Semantic view, tools and agent

## Semantic view (L10)
- Clause order: TABLES, RELATIONSHIPS, FACTS, DIMENSIONS, METRICS, COMMENT, AI_SQL_GENERATION.
  FACTS must come before DIMENSIONS.
- Every new column gets a COMMENT and the synonyms an analyst would use.
- Share metrics are valid within one market, category and period; the AI_SQL_GENERATION rule says so.

## Tools
- Signatures and payloads are fixed in L10; errors follow L13 (NOT_FOUND, AMBIGUOUS, NO_DATA, BAD_INPUT,
  TOOL_FAILED).
- Read only SEM.V_TOOL_* views. Resolve names with APP.SP_RESOLVE. Return TO_JSON(OBJECT_CONSTRUCT(...)).
- A new tool needs the procedure, a tool_spec whose description tells the orchestrator when to use it, a
  tool_resources entry with execution_environment, a grant in 70_sec/701 block 7, a T-TOOL test and golden rows.

## Agent specification
- Keep the orchestration instructions short and rule-like. Write each tool description in the user's words.
- After any change: CREATE OR REPLACE AGENT ... FROM SPECIFICATION, rerun the 505_cowork.sql grants, then
  python3 eval/run_eval.py --tools-only, then the full golden set.

## Knowledge base
- kb/*.md is split at "## " headings into KB.METHOD_DOCS by scripts/load_kb.py.
- One idea per section, under 300 words, using the definitions in share-methodology.

## After editing sql/50_sem
- Rerun sql/70_sec/702_row_access.sql (CREATE OR REPLACE VIEW drops row policies), then T-SEC-03.
```

`.cortex/skills/sr-streamlit/SKILL.md`

```markdown
---
name: sr-streamlit
description: Rules for the two Share Radar Streamlit in Snowflake apps (read-only and admin) on the warehouse runtime. Use when editing anything under streamlit/.
---
# Streamlit apps

## The model (L11)
- One codebase, two apps: SHARE_RADAR (owner SR_UI, read-only) and SHARE_RADAR_ADMIN (owner SR_APP).
  Both run with their owner's rights.
- Pages are pages/0_Radar.py to pages/4_Settings.py, listed by sr_ui/nav.py with st.navigation.
  Settings and the replay panel appear only when st.session_state.sr_admin is true.

## Rules
- All SQL lives in sr_ui/data.py, with bound parameters: session.sql(sql, params=[...]).
- Never run pipeline steps from the app. Start work with data.start_task(...), which runs EXECUTE TASK,
  and watch OPS.RUN_LOG and OPS.STEP_LOG.
- No SHOW, DESCRIBE or ALTER SESSION in app code.
- Cache reads with st.cache_data(ttl=120). Never cache actions; call data.clear_cache() after one.
- Format numbers only through sr_ui/format.py, so they read the same as in the brief.
- Draw charts only through sr_ui/charts.py: zero baselines, signed labels, tooltips, the palette constants.
- On error, show a short message and a retry button. Never show a stack trace in the read-only app.

## Deploy
- From streamlit/: snow streamlit deploy share_radar --replace --role SR_UI -c sr, then share_radar_admin
  with --role SR_APP.
- Pin streamlit in environment.yml with "=" (1.37 or later).

## Tests
- T-UI-01 and T-UI-02 live in python/tests/test_ui.py and import sr_ui.charts and sr_ui.format only;
  format imports data lazily, inside name().
```

`.cortex/skills/sr-tests/SKILL.md`

```markdown
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
```

## T6 Reviewer subagent, Stop hook and session log

Three pieces make the CoCo story provable rather than claimed. A reviewer subagent checks each ticket against this design. A Stop hook records what each CoCo session changed. The log flows into `OPS.COCO_LOG`, where the Trust page shows it next to CoCo's credit usage (L14).

`.cortex/agents/sr-reviewer.md` (the `tools` line is optional; leave it out to inherit the session's tools):

```markdown
---
name: sr-reviewer
description: Reviews the current Share Radar ticket's changes against the design and AGENTS.md before the ticket is marked done. Use after the ticket's tests pass, or when asked to review.
tools: Read, Grep, Glob, Bash
---
You review one Share Radar ticket. You do not write or change code.

1. Read .sr_ticket, then that ticket's T7 prompt and the LLD sections it cites in docs/LLD.md.
2. Run git diff --stat HEAD and git diff HEAD.
3. Check every changed file against this list:
   - Names, columns, settings and test IDs exactly as in the design.
   - Every object fully qualified; no threshold literals; NIQ objects named only in 101_adapter_views.sql.
   - Step procedures: EXECUTE AS CALLER, query tag first, delete then insert per RUN_ID, no EXCEPTION block.
   - Tool procedures: read only SEM.V_TOOL_* views, resolve names with SP_RESOLVE, return L13 error objects.
   - App code: SQL only in sr_ui/data.py, with bound parameters; no SHOW, DESCRIBE or ALTER SESSION;
     no pipeline calls.
   - No SELECT * in procedures, no secrets, no client or brand names in comments or logs.
   - The ticket's T2 tests exist, follow the T1 format and recompute independently.
   - If sql/50_sem changed: 702_row_access.sql was rerun and T-SEC-03 passes.
4. Run the ticket's tests if they have not run in this session.

Reply in exactly this form:
BLOCKING: one line per issue as file:line - problem - fix, or "none".
SHOULD FIX: same format.
NIT: same format.
```

`.cortex/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [ { "type": "command", "command": "python3 scripts/coco_log.py --event stop" } ] }
    ]
  }
}
```

The Stop event fires each time CoCo finishes a reply, not once per session. So the script records only when the working tree has changed since its last record, and it writes locally first. `--event flush` loads the new records into Snowflake in one statement; `scripts/deploy_all.sh` runs it at the end, and so does the last step of every ticket. Check once whether hooks fire in CoCo in Snowsight. If they do not, log that work with `--event manual --surface snowsight`.

`scripts/coco_log.py`:

```python
#!/usr/bin/env python3
"""Share Radar CoCo session log.

stop    Stop hook: record the ticket, changed files, lines added and tests touched, if the tree changed.
human   A person edited CoCo's output by hand: always record, with HUMAN_EDITS = true.
manual  Work done where hooks do not fire (for example CoCo in Snowsight): always record.
flush   Load records not yet loaded into SR_DB.OPS.COCO_LOG.

Never blocks CoCo: every failure goes to stderr and the exit code is 0.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_MD = ROOT / "docs" / "coco_log.md"
LOG_JSONL = ROOT / "docs" / "coco_log.jsonl"
STATE = ROOT / ".git" / "sr_coco_state.json"          # last diff hash and number of lines loaded
TICKET_FILE = ROOT / ".sr_ticket"
CONNECTION = os.environ.get("SR_CONNECTION", "sr")
MD_HEADER = ("| Logged (UTC) | Ticket | Surface | Event | Files | Lines added | Tests touched | Human edits | Note |\n"
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")

def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout

def current_ticket() -> str:
    return TICKET_FILE.read_text(encoding="utf-8").strip() if TICKET_FILE.exists() else "SR-???"

def changed_files() -> tuple[list[str], int, str]:
    """Files changed against HEAD, lines added, and a hash of the numstat used to skip unchanged trees."""
    numstat = git("diff", "--numstat", "HEAD")
    files, added = [], 0
    for line in numstat.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            files.append(parts[2])
            added += int(parts[0]) if parts[0].isdigit() else 0
    return files, added, hashlib.sha1(numstat.encode()).hexdigest()

def tests_touched(files: list[str]) -> list[str]:
    return sorted(Path(f).stem for f in files if f.startswith(("tests/sql/T-", "python/tests/test_")))

def read_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"diff_hash": "", "loaded": 0}

def write_state(state: dict) -> None:
    STATE.write_text(json.dumps(state))

def hook_input() -> dict:
    """The hook passes a JSON object on stdin; manual calls have none."""
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}

def record(row: dict) -> None:
    LOG_MD.parent.mkdir(parents=True, exist_ok=True)
    if not LOG_MD.exists():
        LOG_MD.write_text("# CoCo session log\n\n" + MD_HEADER, encoding="utf-8")
    with LOG_MD.open("a", encoding="utf-8") as md:
        md.write(f"| {row['logged_at']} | {row['ticket']} | {row['surface']} | {row['event']} | {len(row['files'])} | "
                 f"{row['lines_added']} | {', '.join(row['tests']) or '-'} | {'yes' if row['human_edits'] else 'no'} | "
                 f"{row['note'].replace('|', '/')} |\n")
    with LOG_JSONL.open("a", encoding="utf-8") as js:
        js.write(json.dumps(row) + "\n")

def flush(state: dict) -> None:
    lines = LOG_JSONL.read_text(encoding="utf-8").splitlines() if LOG_JSONL.exists() else []
    new = [json.loads(x) for x in lines[state["loaded"]:]]
    if not new:
        return
    payload = base64.b64encode(json.dumps(new).encode("utf-8")).decode("ascii")
    sql = ("INSERT INTO SR_DB.OPS.COCO_LOG (LOGGED_AT, TICKET, SURFACE, FILES, LINES_ADDED, TESTS, HUMAN_EDITS, NOTE) "
           "SELECT f.value:logged_at::TIMESTAMP_LTZ, f.value:ticket::VARCHAR, f.value:surface::VARCHAR, f.value:files, "
           "f.value:lines_added::NUMBER, f.value:tests, f.value:human_edits::BOOLEAN, f.value:note::VARCHAR "
           f"FROM TABLE(FLATTEN(INPUT => PARSE_JSON(BASE64_DECODE_STRING('{payload}')))) f")
    res = subprocess.run(["snow", "sql", "-q", sql, "-c", CONNECTION], capture_output=True, text=True, check=False)
    if res.returncode == 0:
        state["loaded"] = len(lines)
    else:
        print(f"coco_log: load failed, will retry next flush: {res.stderr.strip()[:300]}", file=sys.stderr)

def main(event: str, surface: str = "cli", note: str = "") -> int:
    try:
        state = read_state()
        if event == "flush":
            flush(state)
        else:
            files, added, diff_hash = changed_files()
            if event == "stop" and diff_hash == state["diff_hash"]:
                return 0                                   # nothing changed since the last record
            hook = hook_input() if event == "stop" else {}
            record({
                "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "ticket": current_ticket(), "surface": surface, "event": event,
                "files": files, "lines_added": added, "tests": tests_touched(files),
                "human_edits": event == "human",
                "note": (note or str(hook.get("session_id", "")))[:500],
            })
            state["diff_hash"] = diff_hash
        write_state(state)
    except Exception as exc:                               # the hook must never stop CoCo
        print(f"coco_log: {exc}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", choices=["stop", "human", "manual", "flush"], required=True)
    parser.add_argument("--surface", choices=["cli", "desktop", "snowsight", "claude-code"], default="cli")
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    sys.exit(main(args.event, args.surface, args.note))
```

**Proof metrics from the log.** These are the numbers for the video and the solution brief, all from `OPS.COCO_LOG` and the `COCO` cost source in L14:

- Tickets with at least one CoCo record, out of all build tickets.
- Lines added in CoCo sessions, against records flagged as hand edits.
- Tests written in CoCo sessions (`TESTS` not empty).
- CoCo credits, by interface, for the sprint.

## T7 Ticket prompts for CoCo

The loop for every ticket is the same:

1. Run `echo SR-0xx > .sr_ticket`.
2. Paste the prompt into CoCo, in the CLI or a Snowsight Workspace.
3. Approve the plan.
4. Let CoCo build.
5. **Finish as usual**: run the named tests and fix until they pass, ask `sr-reviewer` to review, then run `python3 scripts/coco_log.py --event flush`.

Until SR-033 exists, steps are called with run ID `'dev-001'`, and `$RUN_UNDER_TEST` is set to it. Section numbers refer to `docs/LLD.md` (L1–L14) and `docs/TESTS_AND_COCO.md` (T1–T7).

| Ticket | Prompt |
| --- | --- |
| SR-001 | /plan Set up the repository. The docs, AGENTS.md, CLAUDE.md, the five skills (T5), the sr-reviewer subagent, the Stop hook settings, scripts/coco\_log.py (T6) and .gitignore are already in the starter kit: check them and report anything missing. Then create the rest of the L2 tree with empty files. Make one change and show that the Stop hook wrote docs/coco\_log.md. |
| SR-002 | /plan Implement SR-002. Read L1 and L5. Write sql/00\_setup/001\_roles\_wh\_db.sql, 002\_settings.sql (with the CURRENCY row), 003\_ops\_tables.sql (the L5 ops tables plus OPS.TEST\_RESULT from T1) and 009\_feature\_smoke\_test.sql. Run them in order, and report each smoke-test line as pass or fail against assumptions A5 and A6. |
| SR-003 | /plan Implement SR-003. Read L3 and AGENTS.md. Explore \<NIQ\_DB> with SHOW and DESCRIBE, propose the column mapping as the L3 worksheet table, and wait for my approval. Then write sql/10\_src/101\_adapter\_views.sql and 102\_capability.sql, including the L13 E01 check, then write and run T-SRC-01..03. |
| SR-004 | /plan Help me choose the demo scope. Using the adapter views, list the 5 categories with the most brands and child retailer markets under one parent market, with weeks of history. For the category I pick, list weeks where a child retailer's category sales drop to zero or its store count changes. Do not write files; give me the tables. |
| SR-010 | /plan Implement SR-010. Read L4. Write sql/20\_core/201\_dt\_period\_week.sql exactly as in L4, deploy it, then write and run T-CORE-04. |
| SR-011 | /plan Implement SR-011. Read L4. Write 202\_dt\_brand\_week.sql and 203\_dt\_cat\_week.sql exactly as in L4, deploy them, then write and run T-CORE-02. |
| SR-012 | /plan Implement SR-012. Read L4. Write 204 to 208 as in L4: the period tables, DT\_SHARE\_COMPARE, DT\_SHARE\_WEEK and V\_SHARE\_GRID. Deploy them, then write and run T-CORE-01. |
| SR-013 | /plan Help with SR-013. I will give you five reference numbers from an NIQ report. Insert them into TEST.FX\_RECON\_REFERENCE (T1), write the query that compares each with V\_SHARE\_GRID and fills OPS.RECON\_RESULT, and run it. Then write and run T-CORE-03. Explain any mismatch before you change code. |
| SR-020 | /plan Implement SR-020. Read L5 and L6 (template, Detector). Write sql/40\_app/401\_result\_tables.sql with every L5 result table, and 403\_sp\_detect\_shifts.sql. Call it for 'dev-001', then write and run T-DET-01..02. |
| SR-021 | /plan Implement SR-021. Read L7. Write sql/30\_ml/301\_sp\_ml\_share\_anomaly.sql as in L7. Run it for 'dev-001' after the detector, then write and run T-ML-01. |
| SR-022 | /plan Implement SR-022. Read L6 (Bridge) and L10 (V\_BRIDGE\_ALL). Write python/sr\_lib/bridge.py with the L6 signatures, and python/tests/cases.py with a toy case; show me the hand computation before you code it. Then write 404\_sp\_bridge.sql and APP.V\_BRIDGE\_ALL, and write and run T-BR-01..05. |
| SR-023 | /plan Implement SR-023. Read L6 (Where) and L7 (TOP\_INSIGHTS). Write 407\_sp\_where.sql for the exact retailer split, and sql/30\_ml/302\_sp\_where\_insights.sql. Run both for 'dev-001', then write and run T-WH-01..02. |
| SR-024 | /plan Implement SR-024. Read L6 (Artefact gate). Write 402\_sp\_snapshot.sql, and 405\_sp\_artefact.sql with all six rules and their evidence objects. Run them, then write and run T-ART-01..04. T-ART-05 follows SR-053. |
| SR-025 | /plan Implement SR-025. Read L6 (Who took it). Write 408\_sp\_flow.sql, run it, then write and run T-FLOW-01..02. |
| SR-026 | /plan Implement SR-026. Read L6 (Rank and suppress). Write 406\_sp\_rank.sql, run it, then write and run T-RANK-01. T-RANK-02 follows SR-053. |
| SR-027 | /plan Implement SR-027. Read L6 (Early warning). Write 409\_sp\_early\_warning.sql, run it, then write and run T-EW-01. |
| SR-028 | Stretch. /plan Implement SR-028 only once SR-027 passes. Read L7 (ML.AD\_LEVERS). Write sql/30\_ml/303\_sp\_ml\_lever\_anomaly.sql so that it sets EARLY\_WARNING.ML\_CONFIRMED, then write and run T-EW-02. |
| SR-029 | /plan Implement SR-029. Read L6 (What-if). Write 410\_sp\_what\_if.sql returning the L6 object, then write and run T-WI-01. |
| SR-030 | /plan Implement SR-030. Read L8 (Fact pack contract). Write 411\_sp\_build\_fact\_pack.sql and python/sr\_lib/factpack.py as L8 specifies. Every number gets a fact with its src. Then write and run T-FP-01. |
| SR-031 | /plan Implement SR-031. Read L8 (Prompt, Structured output schema, Brief writer). Write build\_prompt and the first attempt of write\_brief in python/sr\_lib/run.py, 412\_sp\_write\_brief.sql, and the zip-and-PUT step of scripts/deploy\_all.sh. Run it three times on 'dev-001', and show that each reply parses against the schema. |
| SR-032 | /plan Implement SR-032. Read L8 (Validator, Renderer and fallback) and L13 (E10, E11). Write python/sr\_lib/validator.py, render.py and fallback.py, and finish write\_brief: retry, fallback model, template. Then write and run T-NAR-01..05. |
| SR-033 | /plan Implement SR-033. Read L9, L13 (run\_week) and L14 (estimate\_credits). Write python/sr\_lib/run.py (STEPS, open\_run, log\_step with started\_at, estimate\_credits, close\_run, run\_week) and 413\_sp\_run\_week.sql. Run CALL SR\_DB.APP.SP\_RUN\_WEEK('MANUAL', TRUE), then write and run T-E2E-01, T-E2E-02 and T-E2E-04. |
| SR-040 | /plan Implement SR-040. Read L10 (Semantic view), L12 (Tool views) and the sr-cortex-agent skill. Write sql/50\_sem/501\_v\_sem\_views.sql, with the V\_SEM\_\* and V\_TOOL\_\* views, and 502\_sv\_share.sql. Ask Cortex Analyst 10 questions taken from the golden set's NUMBER and REFUSE rows, compare each with its EXPECTED\_SQL, and report. |
| SR-041 | /plan Help with SR-041. Read L10 (Method knowledge base) and the share-methodology skill. Draft the five kb/\*.md files, one idea per ## section, for my review. Then write scripts/load\_kb.py and 503\_kb\_and\_search.sql, load the documents, and show the top three search results for 'what is TDP'. |
| SR-042 | /plan Implement SR-042. Read L10 (Tool procedures) and L13 (Tool error contract). Write APP.SP\_RESOLVE and the five TOOL\_\* procedures in 414\_tool\_procs.sql, reading only SEM.V\_TOOL\_\* views. Then write and run T-TOOL-01..05. |
| SR-043 | /plan Implement SR-043. Read L10 (Agent, CoWork registration). Write 504\_agent.sql and 505\_cowork.sql, and create the agent. Ask it the four sample questions through SNOWFLAKE.CORTEX.DATA\_AGENT\_RUN, and show which tools each answer called. If the CoWork ADD AGENT statement fails, write it up for the organizers. |
| SR-044 | /plan Help with SR-044. Read T3. From the latest run, propose 30 golden questions with real brand and market names in the T3 mix, each with EXPECTED\_SQL, TOOL\_ARGS and CHECK\_TYPE, as eval/golden\_set.csv. Then write eval/run\_eval.py and eval/run\_eval.sql, run --tools-only, then the full set, and sort the failures with the T3 triage. |
| SR-045 | Stretch. /plan Implement SR-045 only once the golden set passes. Read L10 (Stretch). Upload .cortex/skills/share-methodology to @SR\_DB.SEM.SKILLS and attach it to the agent's live version. Rerun the golden set and compare the score. |
| SR-050 | /plan Implement SR-050. Read L11 and the sr-streamlit skill. Write streamlit/snowflake.yml, environment.yml, .streamlit/config.toml, streamlit\_app.py, admin\_app.py, sr\_ui/nav.py, sr\_ui/data.py, sr\_ui/format.py and pages/0\_Radar.py with the replay panel, plus sql/40\_app/415\_ui\_objects.sql. Deploy both apps and show the Radar for the current run. |
| SR-051 | /plan Implement SR-051. Read L11 (Pages, Charts). Write sr\_ui/charts.py and pages/1\_Shift\_detail.py. Write and run T-UI-01, redeploy, and check one shift end to end. |
| SR-052 | /plan Implement SR-052. Read L11 (Pages), L14 and T1. Write pages/2\_Brief.py, 3\_Trust.py and 4\_Settings.py. Write and run T-UI-02, redeploy, and check that every Trust tile has data. |
| SR-053 | /plan Implement SR-053. Read L9 (stream, task, replay) and L11 (the two tasks). Write 601\_stream\_task.sql and 602\_replay.sql, each starting with USE ROLE SR\_APP. Replay one week from the admin app and watch the run finish. Then write and run T-E2E-03, T-ART-05 and T-RANK-02. |
| SR-054 | /plan Implement SR-054. Read L9 (Delivery). Write 603\_notifications.sql and 604\_alert.sql. Publish a brief, and confirm that NOTIFY\_LOG shows SENT and the email arrived. |
| SR-055 | Stretch. /plan Implement SR-055 only once SR-054 works. Read L9 (Teams). Create the secret and the webhook integration, and extend SP\_NOTIFY\_NEW\_BRIEFS for TEAMS\_ENABLED. Send one test message. |
| SR-056 | /plan Implement SR-056. Read L12. Write sql/70\_sec/701\_grants.sql, 702\_row\_access.sql and 703\_app\_usage.sql, and mark the blocks that need ACCOUNTADMIN for the organizers. Run them, then write and run T-SEC-01..03. |
| SR-057 | Stretch. /plan Implement SR-057. Write sql/60\_ops/605\_dmf.sql, which attaches data metric functions for row count and nulls in VALUE\_SALES to the scope's fact source, and show their first results. |
| SR-061 | /plan Run the dry-run checklist in docs/demo\_script.md: reset the replay to the demo start week, run run\_all.sql with RUN\_E2E set to TRUE, run the golden set, and summarise anything that failed. |
| SR-063 | /plan Draft docs/solution\_brief.md, two pages, from docs/HLD.md and docs/LLD.md, the Trust page numbers (OPS.EVAL\_RESULT, OPS.V\_RUN\_COST, OPS.COCO\_LOG) and docs/decisions.md, for me to edit. |

SR-060 (timing the manual review), SR-062 (the video) and SR-064 (submission) are human work and have no prompt.
