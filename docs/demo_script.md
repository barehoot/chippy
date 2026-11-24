# Demo script, scope choice and dry-run checklist

The video follows one shift from "a week lands" to "the analyst knows what to do", in five minutes, on real data.
Words in angle brackets are filled from measured results, never estimated.

## 1. Choosing the demo scope (SR-004)

Run once the adapter views are mapped (SR-003). A person picks; the agent only lists.

```sql
-- 1a. The five categories with the most brands, per parent market with child retailers, with weeks of history
WITH parents AS (
  SELECT PARENT_MARKET_ID AS PARENT, COUNT(*) AS N_RETAILERS
  FROM SR_DB.SRC.V_SRC_MARKET WHERE PARENT_MARKET_ID IS NOT NULL AND MARKET_LEVEL = 'RETAILER'
  GROUP BY PARENT_MARKET_ID
)
SELECT p.CATEGORY, f.MARKET_ID AS PARENT_MARKET_ID, m.MARKET_NAME, pr.N_RETAILERS,
       COUNT(DISTINCT p.BRAND) AS BRANDS, COUNT(DISTINCT f.WEEK_END_DATE) AS WEEKS,
       MIN(f.WEEK_END_DATE) AS FIRST_WEEK, MAX(f.WEEK_END_DATE) AS LAST_WEEK
FROM SR_DB.SRC.V_SRC_FACT_WEEKLY_ALL f
JOIN SR_DB.SRC.V_SRC_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID
JOIN parents pr ON pr.PARENT = f.MARKET_ID
JOIN SR_DB.SRC.V_SRC_MARKET m ON m.MARKET_ID = f.MARKET_ID
GROUP BY p.CATEGORY, f.MARKET_ID, m.MARKET_NAME, pr.N_RETAILERS
ORDER BY BRANDS DESC, N_RETAILERS DESC
LIMIT 5;

-- 1b. For the chosen category and parent: weeks where a child retailer's category sales drop to zero, or its
--     stores selling move by more than 5% week on week (candidate replay weeks for the artefact catch)
SET CAT = '<category>';
SET PARENT = '<parent market_id>';
WITH wk AS (
  SELECT f.MARKET_ID, f.WEEK_END_DATE, SUM(f.VALUE_SALES) AS SALES, MAX(f.STORES_SELLING) AS STORES
  FROM SR_DB.SRC.V_SRC_FACT_WEEKLY_ALL f
  JOIN SR_DB.SRC.V_SRC_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID AND p.CATEGORY = $CAT
  JOIN SR_DB.SRC.V_SRC_MARKET m ON m.MARKET_ID = f.MARKET_ID AND m.PARENT_MARKET_ID = $PARENT
  GROUP BY f.MARKET_ID, f.WEEK_END_DATE
), grid AS (
  SELECT m.MARKET_ID, m.MARKET_NAME, w.WEEK_END_DATE
  FROM SR_DB.SRC.V_SRC_MARKET m
  CROSS JOIN (SELECT DISTINCT WEEK_END_DATE FROM wk) w
  WHERE m.PARENT_MARKET_ID = $PARENT
)
SELECT g.MARKET_NAME, g.WEEK_END_DATE, COALESCE(k.SALES, 0) AS SALES, k.STORES,
       LAG(k.STORES) OVER (PARTITION BY g.MARKET_ID ORDER BY g.WEEK_END_DATE) AS STORES_PREV
FROM grid g LEFT JOIN wk k ON k.MARKET_ID = g.MARKET_ID AND k.WEEK_END_DATE = g.WEEK_END_DATE
QUALIFY COALESCE(k.SALES, 0) = 0
     OR ABS(k.STORES / NULLIF(LAG(k.STORES) OVER (PARTITION BY g.MARKET_ID ORDER BY g.WEEK_END_DATE), 0) - 1) > 0.05
ORDER BY g.WEEK_END_DATE DESC, g.MARKET_NAME;

-- 1c. The focus manufacturer: the largest manufacturers of the chosen category in the parent, last 52 weeks
SELECT p.MANUFACTURER, SUM(f.VALUE_SALES) AS SALES_52W, COUNT(DISTINCT p.BRAND) AS BRANDS
FROM SR_DB.SRC.V_SRC_FACT_WEEKLY_ALL f
JOIN SR_DB.SRC.V_SRC_PRODUCT p ON p.PRODUCT_ID = f.PRODUCT_ID AND p.CATEGORY = $CAT
WHERE f.MARKET_ID = $PARENT
  AND f.WEEK_END_DATE > DATEADD(week, -52, (SELECT MAX(WEEK_END_DATE) FROM SR_DB.SRC.V_SRC_FACT_WEEKLY_ALL))
GROUP BY p.MANUFACTURER ORDER BY SALES_52W DESC LIMIT 10;
```

Then fill the placeholders in `sql/00_setup/002_settings.sql` (`SCOPE_CATEGORY`, `SCOPE_PARENT_MARKET`,
`FOCUS_MANUFACTURER`, and `AS_OF_WEEK_END` four weeks before the latest real week, or the week before a known
feed or coverage change from 1b) and rerun it; it only replaces placeholders (decision B01). Record each replay
event that should be caught in `TEST.FX_DEMO_EVENTS` so T-ART-05 checks it.

## 2. Before recording

- [ ] `DISPLAY_ALIAS = true` in the admin app's Settings, if the organizers require masked names.
- [ ] `CALL SR_DB.APP.SP_REPLAY_RESET('<demo start week>');` then one run, so the Radar shows a brief before the replay.
- [ ] `snow sql -f tests/sql/run_all.sql -c sr` with `RUN_E2E = TRUE`: no failures (Trust page "Latest SQL test run").
- [ ] `python3 eval/run_eval.py --connection sr`: at least 27/30 (Trust page tile).
- [ ] `CALL SR_DB.OPS.SP_HEALTH_CHECK();` all green; `CALL SR_DB.OPS.SP_COST_SNAPSHOT(14);` for exact costs.
- [ ] Your mailbox is in `NOTIFY_EMAILS` and open on screen for the email moment.
- [ ] CoWork open with the Share Radar agent selected; the three questions below typed into a note.
- [ ] Stopwatch overlay ready (the "days to minutes" claim uses the measured time, section 4).

## 3. The five minutes

| Time | On screen | Operator action | Say (one line) | Proves |
| --- | --- | --- | --- | --- |
| 0:00–0:30 | Title, then the manual process | – | "A competitive share review takes <measured hours> today, timed with <n> analysts." | Business relevance, measured baseline |
| 0:30–1:00 | Radar (admin app); run log ticks; brief appears | Press **Load next week**; start the stopwatch | "A new week landed. <minutes> later, the brief is ready." | Days to minutes; dynamic tables, stream, triggered task |
| 1:00–1:50 | Top shift, then Shift detail | Click the top row | "Distribution explains most of it, mostly in one retailer, and two brands took the points." | Exact bridge, retailer split, share flow |
| 1:50–2:30 | "Held back for data checks"; open its evidence | Click the held-back shift's market in Shift detail, open the rule | "This 'loss' is a retailer feed change, so we didn't alert the client." | Real-or-artefact gate |
| 2:30–3:10 | Brief page; hover a number; open "Checks" | Hover; expand Checks (a rejected attempt with V03) | "Every number links to its query, and the LLM can't write its own." | Numbers-locked narrative |
| 3:10–3:50 | CoWork | Ask: "Why did <brand> lose share in <market>?", "Who took it?", "What if distribution came back?" | "Follow-ups use the same numbers as the brief." | Cortex Agent with Analyst, Search and tools |
| 3:50–4:20 | Email arrives; Radar watchlist | Switch to the mailbox | "It also flags what will hit share next month." | Push delivery, anticipation |
| 4:20–4:45 | Trust page; 10-second clip of the agent building a ticket | Scroll the Trust page | "<x> of <y> tickets were built by the coding agent, and every one has tests." | Technical execution |
| 4:45–5:00 | Close | – | "Client service gets the brief on Monday morning; next comes more categories and a feed into Optiq." | Path to production |

For the "unbreakable numbers" moment, the validator log on the Brief page shows a rejected attempt when one
exists. To force one for the recording, run `CALL SR_DB.APP.SP_WRITE_BRIEF('<run_id>')` with `LLM_MODEL` set to
a model that tends to write digits, then restore the setting; the Checks section shows the V03 rejection.

## 4. Dry run (SR-061)

| Step | Command or action | Record |
| --- | --- | --- |
| Local checks | `pytest -q` (unit, page and local SQL tests) | pass count |
| Reset | `CALL SR_DB.APP.SP_REPLAY_RESET('<demo start week>');` | – |
| Replay to brief | **Load next week** in the admin app | minutes from click to RUN_LOG SUCCEEDED |
| Replay to email | Mailbox | minutes from click to email |
| SQL tests | `run_all.sql` with `RUN_E2E = TRUE` | passed / total |
| Golden set | `python3 eval/run_eval.py --connection sr` | score, EVAL_RUN_ID |
| Cost | Trust page, after `SP_COST_SNAPSHOT(14)` | credits per run, tokens per brief |

Write the measured numbers in `docs/decisions.md` (they replace the targets in LLD L14) and in the solution brief.

A dry run without the account: `python3 tests/local/run_local.py` runs the repository's SQL on DuckDB with
synthetic data and writes `tests/local/out/synthetic_brief.html` (see README).

## 5. After the event

- `ALTER TASK SR_DB.OPS.T_HEALTH SUSPEND;` (about 0.4 credits a day otherwise).
- `ALTER TASK SR_DB.OPS.T_RUN_WEEK SUSPEND;` and `ALTER ALERT SR_DB.OPS.A_NEW_BRIEF SUSPEND;` if the account stays up.
