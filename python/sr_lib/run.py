"""Weekly run orchestration (L9, L13, L14; SR-033) and the brief writer (L8; SR-031, SR-032).

Handlers:
  APP.SP_RUN_WEEK(P_TRIGGER, P_FORCE)  -> run_week(session, trigger_type, force)
  APP.SP_WRITE_BRIEF(P_RUN_ID)         -> write_brief(session, run_id)

Step procedures do not catch their own errors; run_week does. A critical step that fails closes the run FAILED
(the last good brief stays on screen); an optional one logs WARN and the run carries on with less. An outer
handler makes sure no run is ever left RUNNING. Snowpark is imported lazily so the module unit-tests without it.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from .factpack import alias_pack
from .fallback import template_brief
from .render import plain, render_html, render_markdown
from .validator import Violation, validate_brief

# ---- brief writer (L8) --------------------------------------------------------------------------------------

SCHEMA = {
    "type": "json",
    "schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string"},
            "shifts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "shift_id": {"type": "string"},
                        "title": {"type": "string"},
                        "why": {"type": "string"},
                        "so_what": {"type": "string"},
                        "next_question": {"type": "string"},
                    },
                    "required": ["shift_id", "title", "why", "so_what", "next_question"],
                },
            },
            "watchlist": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["headline", "shifts", "watchlist"],
    },
}

PROMPT = """You write a competitive share brief for an NIQ client-service analyst.
Rules:
1. Use only the facts in the FACT PACK. Refer to any number only by its placeholder, for example {{f12}}. Never write digits.
2. Return one entry per item in "shifts", in the same order, with the same shift_id.
3. title: one line naming the brand, the market and whether it gained or lost share.
4. why: one or two sentences naming the largest bridge terms and the top retailer, using placeholders.
5. so_what: one sentence on what the client should check or do next.
6. next_question: one question the analyst could ask the Share Radar agent next.
7. headline: one sentence on the week for the focus manufacturer.
8. watchlist: one short line per watchlist item, using placeholders.
9. Do not describe held_back items; the system lists them.
10. Plain business English. No hype.
FACT PACK:
"""

LLM_OPTIONS = {"temperature": 0, "max_tokens": 1500}


def build_prompt(pack: dict) -> str:
    """The L8 prompt. The pack goes in without values, so the model sees fact IDs and units, never numbers."""
    shown = json.loads(json.dumps(pack))
    shown["facts"] = {fid: {"u": f["u"]} for fid, f in pack.get("facts", {}).items()}
    for k in ("as_of_src", "run_id", "brief_id"):
        shown.pop(k, None)
    return PROMPT + json.dumps(shown, indent=1, ensure_ascii=False)


def _complete(session, model: str, prompt: str) -> str:
    """One structured-output call. snowflake.cortex.complete per L8; SQL AI_COMPLETE if the package is missing."""
    try:
        from snowflake.cortex import CompleteOptions, complete
    except ImportError:
        row = session.sql(
            "SELECT AI_COMPLETE(model => ?, prompt => ?, model_parameters => PARSE_JSON(?), response_format => PARSE_JSON(?))",
            params=[model, prompt, json.dumps(LLM_OPTIONS), json.dumps(SCHEMA)]).collect()
        return row[0][0]
    return complete(model, prompt, options=CompleteOptions(response_format=SCHEMA, **LLM_OPTIONS), session=session)


def _parse(reply) -> object:
    if isinstance(reply, (dict, list)):
        return reply
    text = str(reply).strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return json.loads(text)


def _count_tokens(session, model: str | None, text: str) -> int | None:
    if not model:
        return None
    try:
        return int(session.sql("SELECT SNOWFLAKE.CORTEX.COUNT_TOKENS(?, ?)", params=[model, text]).collect()[0][0])
    except Exception:                       # token counts are reported, never required
        return None


def _cfg(session, *keys: str) -> dict:
    sel = ", ".join(f"SR_DB.OPS.CFG('{k}') AS {k}" for k in keys)
    row = session.sql(f"SELECT {sel}").collect()[0].as_dict()
    return {k: (json.loads(v) if isinstance(v, str) else v) for k, v in row.items()}


def _aliases(session) -> dict[tuple[str, str], str]:
    return {(r["KIND"], r["REAL_NAME"]): r["ALIAS"]
            for r in session.sql("SELECT KIND, REAL_NAME, ALIAS FROM SR_DB.APP.V_ALIAS").collect()}


def write_brief(session, run_id: str) -> str:
    """APP.SP_WRITE_BRIEF: LLM attempt, retry on the fallback model with the problems listed, else the template.
    Publishes exactly one brief for the run and returns its BRIEF_ID."""
    _tag(session, run_id, "BRIEF")
    rows = session.sql("SELECT BRIEF_ID, PACK, SCOPE_KEY FROM SR_DB.APP.FACT_PACK WHERE RUN_ID = ? "
                       "ORDER BY CREATED_AT DESC LIMIT 1", params=[run_id]).collect()
    if not rows:
        raise RuntimeError(f"No fact pack for run {run_id}")
    brief_id, pack, scope_key = rows[0]["BRIEF_ID"], _parse(rows[0]["PACK"]), rows[0]["SCOPE_KEY"]
    cfg = _cfg(session, "LLM_MODEL", "LLM_FALLBACK_MODEL", "DISPLAY_ALIAS", "CURRENCY")
    currency = cfg.get("CURRENCY") or pack.get("currency") or ""
    shown = alias_pack(pack, _aliases(session)) if cfg.get("DISPLAY_ALIAS") is True else pack

    prompt = build_prompt(shown)
    attempts: list[dict] = []
    llm, generator, model_used, prompt_used, problems = None, "TEMPLATE", None, prompt, []
    for attempt, model in enumerate([cfg.get("LLM_MODEL"), cfg.get("LLM_FALLBACK_MODEL")], start=1):
        if not model:
            continue
        p = prompt if attempt == 1 else prompt + "\nFix these problems: " + "; ".join(
            f"{x.code} at {x.path}: {x.detail}" for x in problems)
        candidate = None
        try:
            candidate = _parse(_complete(session, model, p))
            problems = validate_brief(candidate, shown)
        except Exception as e:                                     # E10: the call failed or returned no JSON
            problems = [Violation("V00_LLM_ERROR", "", str(e)[:300])]
        attempts.append({"attempt": attempt, "model": model, "violations": [asdict(x) for x in problems]})
        if candidate is not None and not problems:
            llm, generator, model_used, prompt_used = candidate, ("LLM" if attempt == 1 else "LLM_RETRY"), model, p
            break
    if llm is None:                                                # E10, E11: both attempts failed
        llm = template_brief(shown)
        attempts.append({"attempt": "template", "model": None,
                         "violations": [asdict(x) for x in validate_brief(llm, shown)]})

    body_md = render_markdown(llm, shown, currency)
    body_html = render_html(llm, shown, currency)
    tokens_in = _count_tokens(session, model_used, prompt_used)
    tokens_out = _count_tokens(session, model_used, json.dumps(llm))
    session.sql("DELETE FROM SR_DB.APP.BRIEF WHERE RUN_ID = ?", params=[run_id]).collect()
    session.sql(
        "INSERT INTO SR_DB.APP.BRIEF (BRIEF_ID, RUN_ID, SCOPE_KEY, AS_OF_WEEK, STATUS, GENERATOR, MODEL, HEADLINE, "
        "BODY_MD, BODY_HTML, LLM_JSON, VIOLATIONS, TOKENS_IN, TOKENS_OUT, PUBLISHED_AT) "
        "SELECT ?, ?, ?, TO_DATE(?), 'PUBLISHED', ?, ?, ?, ?, ?, PARSE_JSON(?), PARSE_JSON(?), ?, ?, CURRENT_TIMESTAMP()",
        params=[brief_id, run_id, scope_key, pack.get("as_of_week"), generator, model_used,
                plain(llm["headline"], shown, currency)[:400], body_md, body_html, json.dumps(llm),
                json.dumps(attempts), tokens_in, tokens_out]).collect()
    return brief_id


# ---- orchestration (L9, L13, L14) ---------------------------------------------------------------------------

Step = tuple[int, str, str, bool]          # (step_no, name, sql_template, critical)

STEPS: list[Step] = [
    (2,  "CAPABILITY",    "CALL SR_DB.APP.SP_CAPABILITY_CHECK()", True),
    (3,  "SNAPSHOT",      "CALL SR_DB.APP.SP_SNAPSHOT('{run}')", False),
    (4,  "DETECT",        "CALL SR_DB.APP.SP_DETECT_SHIFTS('{run}')", True),
    (5,  "ML_ANOMALY",    "CALL SR_DB.APP.SP_ML_SHARE_ANOMALY('{run}')", False),
    (6,  "BRIDGE",        "CALL SR_DB.APP.SP_BRIDGE('{run}')", True),
    (7,  "ARTEFACT",      "CALL SR_DB.APP.SP_ARTEFACT('{run}')", True),
    (8,  "RANK",          "CALL SR_DB.APP.SP_RANK('{run}')", True),
    (9,  "WHERE",         "CALL SR_DB.APP.SP_WHERE('{run}')", True),
    (9,  "TOP_INSIGHTS",  "CALL SR_DB.APP.SP_WHERE_INSIGHTS('{run}')", False),
    (10, "FLOW",          "CALL SR_DB.APP.SP_FLOW('{run}')", False),
    (11, "EARLY_WARNING", "CALL SR_DB.APP.SP_EARLY_WARNING('{run}')", False),
    (11, "EW_ML",         "CALL SR_DB.APP.SP_ML_LEVER_ANOMALY('{run}')", False),    # stretch SR-028 (B06)
    (12, "FACT_PACK",     "CALL SR_DB.APP.SP_BUILD_FACT_PACK('{run}')", True),
    (13, "BRIEF",         "CALL SR_DB.APP.SP_WRITE_BRIEF('{run}')", True),
]
OPTIONAL_COST_STEPS = {"ML_ANOMALY", "TOP_INSIGHTS", "EW_ML"}
CREDITS_PER_HOUR = {"X-Small": 1, "Small": 2, "Medium": 4, "Large": 8}
BUSY_MINUTES = 30
WEEKS_NEEDED = {"L4W_VS_PP": 8, "L4W_VS_YA": 56, "L12W_VS_YA": 64, "L52W_VS_YA": 104}
SCOPE_KEY_SQL = ("SR_DB.OPS.CFG('SCOPE_CATEGORY')::VARCHAR || '|' || SR_DB.OPS.CFG('SCOPE_PARENT_MARKET')::VARCHAR"
                 " || '|' || SR_DB.OPS.CFG('FOCUS_MANUFACTURER')::VARCHAR")


def _step_error_type() -> type[BaseException]:
    try:
        from snowflake.snowpark.exceptions import SnowparkSQLException
        return SnowparkSQLException
    except ImportError:                    # unit tests without Snowpark
        return RuntimeError


STEP_ERRORS: type[BaseException] = _step_error_type()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tag(session, run_id: str, step: str) -> None:
    session.sql(f"ALTER SESSION SET QUERY_TAG = 'SR|run={run_id}|step={step}'").collect()


def log_step(session, run_id: str, step_no: int, step: str, status: str, rows: int | None, message: str | None,
             *, started_at: datetime | None = None) -> None:
    session.sql(
        "INSERT INTO SR_DB.OPS.STEP_LOG (RUN_ID, STEP_NO, STEP, STATUS, STARTED_AT, ENDED_AT, ROWS_WRITTEN, MESSAGE) "
        "SELECT ?, ?, ?, ?, TO_TIMESTAMP_LTZ(?), CURRENT_TIMESTAMP(), ?, ?",
        params=[run_id, step_no, step, status, (started_at or _now()).isoformat(), rows, message]).collect()


def open_run(session, trigger_type: str, force: bool) -> str | None:
    """RUN_ID of a new RUNNING run, or None when a SKIPPED row was written instead (E16): another run is in
    progress (BUSY), or this week already succeeded for the scope and the run is not forced (ALREADY_RAN)."""
    started = _now()
    run_id = str(uuid.uuid4())
    _tag(session, run_id, "OPEN")
    ctx = session.sql(f"SELECT SR_DB.OPS.CFG('AS_OF_WEEK_END')::VARCHAR AS AS_OF, {SCOPE_KEY_SQL} AS SCOPE_KEY").collect()[0]
    as_of, scope_key = ctx["AS_OF"], ctx["SCOPE_KEY"]
    busy = session.sql("SELECT COUNT(*) FROM SR_DB.OPS.RUN_LOG WHERE STATUS = 'RUNNING' "
                       f"AND STARTED_AT > DATEADD(minute, -{BUSY_MINUTES}, CURRENT_TIMESTAMP())").collect()[0][0]
    reason = None
    if busy:
        reason = "BUSY: a run is in progress"
    elif not force:
        done = session.sql("SELECT COUNT(*) FROM SR_DB.OPS.RUN_LOG WHERE STATUS = 'SUCCEEDED' "
                           "AND AS_OF_WEEK = TO_DATE(?) AND SCOPE_KEY = ?", params=[as_of, scope_key]).collect()[0][0]
        if done:
            reason = "ALREADY_RAN: this week already has a brief for this scope"
    session.sql(
        "INSERT INTO SR_DB.OPS.RUN_LOG (RUN_ID, TRIGGER_TYPE, AS_OF_WEEK, SCOPE_KEY, STATUS, STARTED_AT, ENDED_AT, ERROR_MSG) "
        "SELECT ?, ?, TO_DATE(?), ?, ?, CURRENT_TIMESTAMP(), IFF(? IS NULL, NULL, CURRENT_TIMESTAMP()), ?",
        params=[run_id, trigger_type, as_of, scope_key, "SKIPPED" if reason else "RUNNING", reason, reason]).collect()
    if reason:
        return None
    log_step(session, run_id, 1, "OPEN", "OK", None, f"{trigger_type}{' (forced)' if force else ''}", started_at=started)
    return run_id


def estimate_credits(session, run_id: str) -> float:
    """Execution time of the run's own tagged queries at standard warehouse rates (L14). Overstates slightly,
    which is the safe side for a cap. AI tokens are billed separately and reported, not estimated."""
    rows = session.sql(
        """SELECT WAREHOUSE_SIZE, SUM(EXECUTION_TIME) / 1000 / 3600 AS HOURS
           FROM TABLE(SR_DB.INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION(RESULT_LIMIT => 10000))
           WHERE QUERY_TAG LIKE ? AND WAREHOUSE_SIZE IS NOT NULL
           GROUP BY WAREHOUSE_SIZE""", params=[f"SR|run={run_id}|%"]).collect()
    return round(sum(CREDITS_PER_HOUR.get(r["WAREHOUSE_SIZE"], 4) * float(r["HOURS"]) for r in rows), 4)


def close_run(session, run_id: str, status: str, error: str | None) -> None:
    started = _now()
    try:
        credits = estimate_credits(session, run_id)
    except Exception:
        credits = None
    session.sql(
        """UPDATE SR_DB.OPS.RUN_LOG SET STATUS = ?, ENDED_AT = CURRENT_TIMESTAMP(), ERROR_MSG = ?, CREDITS_EST = ?,
             BRIDGE_MODE  = (SELECT MAX_BRIDGE_MODE FROM SR_DB.OPS.CAPABILITY ORDER BY CHECKED_AT DESC LIMIT 1),
             N_CANDIDATES = (SELECT COUNT_IF(PASSED_GATES) FROM SR_DB.APP.SHIFT_CANDIDATE WHERE RUN_ID = ?),
             N_RANKED     = (SELECT COUNT_IF(SELECTED) FROM SR_DB.APP.SHIFT_RANKED WHERE RUN_ID = ?),
             BRIEF_ID     = (SELECT MAX(BRIEF_ID) FROM SR_DB.APP.BRIEF WHERE RUN_ID = ? AND STATUS = 'PUBLISHED')
           WHERE RUN_ID = ?""",
        params=[status, error, credits, run_id, run_id, run_id, run_id]).collect()
    log_step(session, run_id, 14, "CLOSE", "OK" if status == "SUCCEEDED" else "FAILED", None, status, started_at=started)


def detect_warning(session) -> str | None:
    """E02: comparisons in COMPARES that have no base-period data, with the weeks they need and have."""
    rows = session.sql(
        """SELECT f.VALUE::VARCHAR AS CMP_CODE, COUNT_IF(d.CS0 IS NOT NULL) AS N_BASE,
                  (SELECT MAX(N_WEEKS) FROM (SELECT N_WEEKS FROM SR_DB.OPS.CAPABILITY ORDER BY CHECKED_AT DESC LIMIT 1)) AS N_WEEKS
           FROM TABLE(FLATTEN(INPUT => SR_DB.OPS.CFG('COMPARES'))) f
           LEFT JOIN SR_DB.CORE.DT_SHARE_COMPARE d ON d.CMP_CODE = f.VALUE::VARCHAR
           GROUP BY f.VALUE::VARCHAR""").collect()
    gaps = [f"{r['CMP_CODE']} needs {WEEKS_NEEDED.get(r['CMP_CODE'], '?')} weeks; {r['N_WEEKS']} available"
            for r in rows if not r["N_BASE"]]
    return "; ".join(gaps) or None


def _as_rows(result) -> int | None:
    try:
        return int(result)
    except (TypeError, ValueError):         # SP_CAPABILITY_CHECK returns 'OK', SP_BUILD_FACT_PACK a BRIEF_ID
        return None


def run_week(session, trigger_type: str = "MANUAL", force: bool = False) -> str:
    """APP.SP_RUN_WEEK: the whole weekly run. Returns the RUN_ID, or 'SKIPPED'."""
    run_id = open_run(session, trigger_type, bool(force))
    if run_id is None:
        return "SKIPPED"
    try:
        cap = float(session.sql("SELECT SR_DB.OPS.CFG('MAX_CREDITS_PER_RUN')::FLOAT").collect()[0][0])
        failed = None
        for step_no, name, sql, critical in STEPS:
            started = _now()
            if name in OPTIONAL_COST_STEPS and estimate_credits(session, run_id) > cap:          # E09
                log_step(session, run_id, step_no, name, "SKIPPED", None, "credit cap", started_at=started)
                continue
            try:
                _tag(session, run_id, name)
                result = session.sql(sql.format(run=run_id)).collect()[0][0]
                status, message = "OK", None
                if name == "DETECT":
                    message = detect_warning(session)
                    status = "WARN" if message else "OK"
                log_step(session, run_id, step_no, name, status, _as_rows(result), message, started_at=started)
            except STEP_ERRORS as e:
                msg = f"{name}: {getattr(e, 'message', None) or e}"[:2000]
                log_step(session, run_id, step_no, name, "FAILED" if critical else "WARN", None, msg, started_at=started)
                if critical:
                    failed = msg
                    break
        close_run(session, run_id, "FAILED" if failed else "SUCCEEDED", failed)
    except Exception as e:                                         # a bug in this file, not in a step
        close_run(session, run_id, "FAILED", f"INTERNAL: {e}"[:2000])
    try:
        session.sql("CALL SR_DB.OPS.SP_HEALTH_CHECK()").collect()  # keep the Trust page fresh after each run
    except Exception:
        pass
    return run_id
