"""Every query and action of the two apps (L11). Bind values with params; never format user input into SQL.

Reads are cached per viewer session (st.cache_data, TTL_S); run and step reads are not cached, because they drive
the progress panel; actions are never cached and clear the cache after them. The apps run with their owner's
rights, so the read-only app (SR_UI) can only read, and only the admin app (SR_APP) can execute tasks.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st

TTL_S = 120             # per viewer session on the warehouse runtime
BUSY_MIN = 30           # a RUNNING run younger than this blocks replay and rerun
TASKS = {"T_REPLAY_NEXT", "T_RUN_WEEK_MANUAL", "T_RUN_WEEK", "T_HEALTH"}
STARTABLE = {"T_REPLAY_NEXT", "T_RUN_WEEK_MANUAL", "T_HEALTH"}


@dataclass(frozen=True)
class Run:
    run_id: str
    trigger_type: str           # STREAM | REPLAY | MANUAL
    as_of_week: date | None
    scope_key: str | None
    status: str                 # RUNNING | SUCCEEDED | FAILED | SKIPPED
    bridge_mode: str | None
    n_candidates: int | None
    n_ranked: int | None
    brief_id: str | None
    credits_est: float | None
    started_at: pd.Timestamp
    ended_at: pd.Timestamp | None
    error_msg: str | None


class Busy(Exception):
    """A run is in progress; replay and rerun wait for it."""


def session():
    from snowflake.snowpark.context import get_active_session
    return get_active_session()


def q(sql: str, params: list | None = None) -> pd.DataFrame:
    return session().sql(sql, params=params).to_pandas()


def _one(sql: str, params: list | None = None) -> dict | None:
    df = q(sql, params)
    return None if df.empty else df.iloc[0].to_dict()


def _variant(v):
    """VARIANT columns arrive as JSON text."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


# ---- Context (cached) -----------------------------------------------------------------------------------------

@st.cache_data(ttl=TTL_S, show_spinner=False)
def _settings_map() -> dict[str, object]:
    df = q("SELECT SETTING_KEY, TO_JSON(SETTING_VALUE) AS VALUE_JSON FROM SR_DB.OPS.SETTINGS")
    return {k: json.loads(v) for k, v in zip(df.SETTING_KEY, df.VALUE_JSON)}


def cfg(key: str) -> object:
    return _settings_map().get(key)


def scope_key() -> str:
    return f"{cfg('SCOPE_CATEGORY')}|{cfg('SCOPE_PARENT_MARKET')}|{cfg('FOCUS_MANUFACTURER')}"


@st.cache_data(ttl=TTL_S, show_spinner=False)
def viewer_name() -> str | None:
    try:
        return q("SELECT CURRENT_USER() AS U").U.iloc[0]
    except Exception:                    # needs READ SESSION on the owner role (L11)
        return None


@st.cache_data(ttl=TTL_S, show_spinner=False)
def aliases() -> dict[tuple[str, str], str]:
    df = q("SELECT KIND, REAL_NAME, ALIAS FROM SR_DB.APP.V_ALIAS")
    return {(k, r): a for k, r, a in zip(df.KIND, df.REAL_NAME, df.ALIAS)}


@st.cache_data(ttl=TTL_S, show_spinner=False)
def market_names() -> dict[str, str]:
    df = q("SELECT MARKET_ID, MARKET_NAME FROM SR_DB.SRC.V_SRC_MARKET")
    return dict(zip(df.MARKET_ID, df.MARKET_NAME))


# ---- Runs (not cached: they drive the progress panel) ---------------------------------------------------------

_RUN_COLS = ("RUN_ID, TRIGGER_TYPE, AS_OF_WEEK, SCOPE_KEY, STATUS, BRIDGE_MODE, N_CANDIDATES, N_RANKED, BRIEF_ID, "
             "CREDITS_EST, STARTED_AT, ENDED_AT, ERROR_MSG")


def _run(row: dict | None) -> Run | None:
    if not row:
        return None
    clean = {k.lower(): (None if (v is None or (isinstance(v, float) and pd.isna(v))) else v) for k, v in row.items()}
    return Run(**clean)


def current_run() -> Run | None:
    """The newest SUCCEEDED run, preferring the current as-of week and scope."""
    return _run(_one(f"SELECT {_RUN_COLS} FROM SR_DB.OPS.RUN_LOG WHERE STATUS = 'SUCCEEDED' "
                     "ORDER BY IFF(AS_OF_WEEK = TRY_TO_DATE(?) AND SCOPE_KEY = ?, 0, 1), STARTED_AT DESC LIMIT 1",
                     [str(cfg("AS_OF_WEEK_END")), scope_key()]))


def latest_attempt() -> Run | None:
    """The newest run of any status for the current as-of week (drives the 'data has not arrived' banner)."""
    return _run(_one(f"SELECT {_RUN_COLS} FROM SR_DB.OPS.RUN_LOG WHERE AS_OF_WEEK = TRY_TO_DATE(?) "
                     "ORDER BY STARTED_AT DESC LIMIT 1", [str(cfg("AS_OF_WEEK_END"))]))


def active_run() -> Run | None:
    return _run(_one(f"SELECT {_RUN_COLS} FROM SR_DB.OPS.RUN_LOG WHERE STATUS = 'RUNNING' "
                     f"AND STARTED_AT > DATEADD(minute, -{BUSY_MIN}, CURRENT_TIMESTAMP()) ORDER BY STARTED_AT DESC LIMIT 1"))


def run_started_since(since: str) -> Run | None:
    return _run(_one(f"SELECT {_RUN_COLS} FROM SR_DB.OPS.RUN_LOG WHERE STARTED_AT >= TO_TIMESTAMP_LTZ(?) "
                     "ORDER BY STARTED_AT DESC LIMIT 1", [since]))


def step_log(run_id: str) -> pd.DataFrame:
    return q("SELECT STEP_NO, STEP, STATUS, STARTED_AT, ENDED_AT, ROWS_WRITTEN, MESSAGE, "
             "DATEDIFF(second, STARTED_AT, COALESCE(ENDED_AT, CURRENT_TIMESTAMP())) AS SECONDS "
             "FROM SR_DB.OPS.STEP_LOG WHERE RUN_ID = ? ORDER BY STARTED_AT, STEP_NO", [run_id])


def task_last_run(task: str) -> dict | None:
    if task not in TASKS:
        raise ValueError(f"Unknown task {task}")
    return _one("SELECT STATE, ERROR_MESSAGE, SCHEDULED_TIME, COMPLETED_TIME "
                f"FROM TABLE(SR_DB.INFORMATION_SCHEMA.TASK_HISTORY(TASK_NAME => '{task}', RESULT_LIMIT => 1))")


# ---- Radar (cached) -------------------------------------------------------------------------------------------

@st.cache_data(ttl=TTL_S, show_spinner=False)
def shifts(run_id: str) -> pd.DataFrame:
    return q("""SELECT r.SHIFT_ID, r.RANK_NO, r.CMP_CODE, r.MARKET_ID, r.CATEGORY, r.MANUFACTURER, r.BRAND, r.IS_FOCUS,
                       c.SH1, c.SH0, 100 * r.D_SHARE AS D_SHARE_PTS, r.VALUE_AT_STAKE, c.Z_SCORE, c.ANOMALY_CONFIRMED,
                       r.CONFIDENCE, r.ARTEFACT_LABEL, r.SCORE, r.SUPPRESSED, r.SUPPRESS_REASON, r.SELECTED
                FROM SR_DB.APP.SHIFT_RANKED r
                JOIN SR_DB.APP.SHIFT_CANDIDATE c ON c.RUN_ID = r.RUN_ID AND c.SHIFT_ID = r.SHIFT_ID
                WHERE r.RUN_ID = ? ORDER BY r.SELECTED DESC, r.SCORE DESC""", [run_id])


@st.cache_data(ttl=TTL_S, show_spinner=False)
def held_back(run_id: str) -> pd.DataFrame:
    """POSSIBLE_DATA_EFFECT shifts, top 3 by SCORE, with the HIGH rules that matched them (the SP_RANK match)."""
    df = q("""SELECT r.SHIFT_ID, r.CMP_CODE, r.MARKET_ID, r.BRAND, 100 * ANY_VALUE(r.D_SHARE) AS D_SHARE_PTS,
                     ANY_VALUE(r.SCORE) AS SCORE, ARRAY_AGG(DISTINCT a.RULE_ID) AS RULES
              FROM SR_DB.APP.SHIFT_RANKED r
              LEFT JOIN SR_DB.APP.ARTEFACT_CHECK a
                ON a.RUN_ID = r.RUN_ID AND a.CMP_CODE = r.CMP_CODE AND a.MARKET_ID = r.MARKET_ID
               AND a.CATEGORY = r.CATEGORY AND (a.BRAND IS NULL OR a.BRAND = r.BRAND) AND a.SEVERITY = 'HIGH'
              WHERE r.RUN_ID = ? AND r.ARTEFACT_LABEL = 'POSSIBLE_DATA_EFFECT'
              GROUP BY r.SHIFT_ID, r.CMP_CODE, r.MARKET_ID, r.BRAND
              ORDER BY SCORE DESC LIMIT 3""", [run_id])
    df["RULES"] = [_variant(v) or [] for v in df.RULES]
    return df


@st.cache_data(ttl=TTL_S, show_spinner=False)
def watchlist(run_id: str) -> pd.DataFrame:
    return q("""SELECT MARKET_ID, BRAND, SIGNAL, LATEST_WEEK, LEVER_LATEST, LEVER_L4W, LEVER_CHG, PROJECTED_SHARE_PTS,
                       ML_CONFIRMED, NOTE
                FROM SR_DB.APP.EARLY_WARNING WHERE RUN_ID = ?
                ORDER BY ABS(COALESCE(PROJECTED_SHARE_PTS, 0)) DESC, ABS(LEVER_CHG) DESC""", [run_id])


@st.cache_data(ttl=TTL_S, show_spinner=False)
def kpis(run_id: str) -> dict[str, float]:
    row = _one("""SELECT (SELECT COUNT_IF(PASSED_GATES) FROM SR_DB.APP.SHIFT_CANDIDATE WHERE RUN_ID = ?) AS N_PASSED,
                         COUNT_IF(SELECTED) AS N_SELECTED, COUNT_IF(ARTEFACT_LABEL = 'POSSIBLE_DATA_EFFECT') AS N_DATA_EFFECT,
                         SUM(IFF(SELECTED, ABS(VALUE_AT_STAKE), 0)) AS VALUE_SELECTED
                  FROM SR_DB.APP.SHIFT_RANKED WHERE RUN_ID = ?""", [run_id, run_id]) or {}
    return {k: (0 if v is None or pd.isna(v) else float(v)) for k, v in row.items()}


# ---- Shift detail (cached, except what_if) --------------------------------------------------------------------

@st.cache_data(ttl=TTL_S, show_spinner=False)
def shift(shift_id: str) -> dict:
    return _one("""SELECT r.RUN_ID, r.SHIFT_ID, r.RANK_NO, r.CMP_CODE, r.MARKET_ID, r.CATEGORY, r.MANUFACTURER, r.BRAND,
                          r.IS_FOCUS, r.D_SHARE, 100 * r.D_SHARE AS D_SHARE_PTS, r.VALUE_AT_STAKE, r.CONFIDENCE,
                          r.ARTEFACT_LABEL, r.SCORE, r.SUPPRESSED, r.SUPPRESS_REASON, r.SELECTED,
                          c.SH1, c.SH0, c.Z_SCORE, c.ANOMALY_WEEKS, c.ANOMALY_CONFIRMED, b.MODE, b.STATUS, b.NOTE
                   FROM SR_DB.APP.SHIFT_RANKED r
                   JOIN SR_DB.APP.SHIFT_CANDIDATE c ON c.RUN_ID = r.RUN_ID AND c.SHIFT_ID = r.SHIFT_ID
                   LEFT JOIN SR_DB.APP.SHARE_BRIDGE b ON b.RUN_ID = r.RUN_ID AND b.SHIFT_ID = r.SHIFT_ID
                   WHERE r.SHIFT_ID = ?""", [shift_id]) or {}


@st.cache_data(ttl=TTL_S, show_spinner=False)
def bridge(shift_id: str) -> dict | None:
    return _one("""SELECT SHIFT_ID, MODE, STATUS, SH1, SH0, D_SHARE, LMDI_WEIGHT, DIST_PTS, VELOCITY_PTS, PRICE_PTS,
                          PROMO_PTS, RESIDUAL_PTS, DS1, DS0, PI1, PI0, PRI1, PRI0, NOTE
                   FROM SR_DB.APP.SHARE_BRIDGE WHERE SHIFT_ID = ?""", [shift_id])


@st.cache_data(ttl=TTL_S, show_spinner=False)
def where(shift_id: str) -> pd.DataFrame:
    return q("""SELECT METHOD, RANK_NO, CONTRIBUTOR, PERF_PTS, MIX_PTS, TOTAL_PTS, METRIC_CONTROL, METRIC_TEST,
                       CONTRIBUTION, RELATIVE_CONTRIBUTION, GROWTH_RATE
                FROM SR_DB.APP.SHIFT_WHERE WHERE SHIFT_ID = ? ORDER BY METHOD, RANK_NO""", [shift_id])


@st.cache_data(ttl=TTL_S, show_spinner=False)
def flow(run_id: str, cmp_code: str, market_id: str, category: str, brand: str, direction: str) -> pd.DataFrame:
    """LOSS: TO_BRAND AS COUNTERPART where FROM_BRAND = brand; GAIN: FROM_BRAND AS COUNTERPART where TO_BRAND = brand."""
    mine, other = ("FROM_BRAND", "TO_BRAND") if direction == "LOSS" else ("TO_BRAND", "FROM_BRAND")
    return q(f"""SELECT {other} AS COUNTERPART, FLOW_PTS FROM SR_DB.APP.SHARE_FLOW
                 WHERE RUN_ID = ? AND CMP_CODE = ? AND MARKET_ID = ? AND CATEGORY = ? AND {mine} = ?
                 ORDER BY FLOW_PTS DESC LIMIT 8""", [run_id, cmp_code, market_id, category, brand])


@st.cache_data(ttl=TTL_S, show_spinner=False)
def artefacts(run_id: str, cmp_code: str, market_id: str, category: str, brand: str) -> pd.DataFrame:
    df = q("""SELECT RULE_ID, SEVERITY, BRAND, EVIDENCE FROM SR_DB.APP.ARTEFACT_CHECK
              WHERE RUN_ID = ? AND CMP_CODE = ? AND MARKET_ID = ? AND CATEGORY = ? AND (BRAND IS NULL OR BRAND = ?)
              ORDER BY SEVERITY, RULE_ID""", [run_id, cmp_code, market_id, category, brand])
    df["EVIDENCE"] = [_variant(v) for v in df.EVIDENCE]
    return df


@st.cache_data(ttl=TTL_S, show_spinner=False)
def trend(market_id: str, category: str, brand: str, weeks: int = 104) -> pd.DataFrame:
    return q("""SELECT WEEK_END_DATE, 100 * VALUE_SHARE AS VALUE_SHARE_PCT, 100 * DIST_SHARE AS DIST_SHARE_PCT
                FROM SR_DB.APP.V_UI_SHARE_WEEK WHERE MARKET_ID = ? AND CATEGORY = ? AND BRAND = ?
                QUALIFY ROW_NUMBER() OVER (ORDER BY WEEK_END_DATE DESC) <= ? ORDER BY WEEK_END_DATE""",
             [market_id, category, brand, weeks])


def what_if(shift_id: str, lever: str, target: str) -> dict:
    r = session().call("SR_DB.APP.SP_WHAT_IF", shift_id, lever, target)
    return r if isinstance(r, dict) else json.loads(r)


# ---- Brief (cached) -------------------------------------------------------------------------------------------

@st.cache_data(ttl=TTL_S, show_spinner=False)
def briefs(limit: int = 12) -> pd.DataFrame:
    return q("""SELECT BRIEF_ID, RUN_ID, AS_OF_WEEK, HEADLINE, GENERATOR, MODEL, PUBLISHED_AT, NOTIFIED_AT, NOTIFY_ATTEMPTS
                FROM SR_DB.APP.BRIEF WHERE STATUS = 'PUBLISHED'
                ORDER BY AS_OF_WEEK DESC, PUBLISHED_AT DESC LIMIT ?""", [limit])


@st.cache_data(ttl=TTL_S, show_spinner=False)
def brief(brief_id: str) -> dict:
    row = _one("""SELECT BRIEF_ID, RUN_ID, SCOPE_KEY, AS_OF_WEEK, STATUS, GENERATOR, MODEL, HEADLINE, BODY_MD, BODY_HTML,
                         LLM_JSON, VIOLATIONS, TOKENS_IN, TOKENS_OUT, PUBLISHED_AT, NOTIFIED_AT, NOTIFY_ATTEMPTS
                  FROM SR_DB.APP.BRIEF WHERE BRIEF_ID = ?""", [brief_id]) or {}
    for k in ("LLM_JSON", "VIOLATIONS"):
        row[k] = _variant(row.get(k))
    return row


@st.cache_data(ttl=TTL_S, show_spinner=False)
def brief_facts(brief_id: str) -> pd.DataFrame:
    return q("""SELECT f.KEY AS FACT_ID, f.VALUE:v::FLOAT AS V, f.VALUE:u::VARCHAR AS UNIT, f.VALUE:d::INT AS DECIMALS,
                       f.VALUE:src::VARCHAR AS SOURCE
                FROM SR_DB.APP.FACT_PACK p, LATERAL FLATTEN(INPUT => p.PACK:facts) f
                WHERE p.BRIEF_ID = ? ORDER BY TRY_TO_NUMBER(SUBSTR(f.KEY, 2))""", [brief_id])


@st.cache_data(ttl=TTL_S, show_spinner=False)
def brief_notifications(brief_id: str) -> pd.DataFrame:
    return q("SELECT CHANNEL, STATUS, SENT_AT, MESSAGE FROM SR_DB.OPS.NOTIFY_LOG WHERE BRIEF_ID = ? ORDER BY SENT_AT DESC",
             [brief_id])


# ---- Trust (cached) -------------------------------------------------------------------------------------------

@st.cache_data(ttl=TTL_S, show_spinner=False)
def eval_latest() -> pd.DataFrame:
    return q("""SELECT EVAL_RUN_ID, QUESTION_ID, QUESTION, EXPECTED_TOOL, ACTUAL_TOOLS, PASSED, NOTE, EVALUATED_AT
                FROM SR_DB.OPS.EVAL_RESULT
                WHERE EVAL_RUN_ID = (SELECT EVAL_RUN_ID FROM SR_DB.OPS.EVAL_RESULT ORDER BY EVALUATED_AT DESC LIMIT 1)
                ORDER BY QUESTION_ID""")


@st.cache_data(ttl=TTL_S, show_spinner=False)
def recon_latest() -> pd.DataFrame:
    return q("""SELECT CHECK_ID, DESCRIPTION, REFERENCE_VALUE, SR_VALUE, ABS_DIFF, PASSED, CHECKED_AT
                FROM SR_DB.OPS.RECON_RESULT
                QUALIFY ROW_NUMBER() OVER (PARTITION BY CHECK_ID ORDER BY CHECKED_AT DESC) = 1 ORDER BY CHECK_ID""")


@st.cache_data(ttl=TTL_S, show_spinner=False)
def bridge_residual_max(run_id: str) -> float | None:
    row = _one("SELECT MAX(ABS(RESIDUAL_PTS)) AS R FROM SR_DB.APP.SHARE_BRIDGE WHERE RUN_ID = ? AND STATUS = 'OK'", [run_id])
    return None if not row or row["R"] is None or pd.isna(row["R"]) else float(row["R"])


@st.cache_data(ttl=TTL_S, show_spinner=False)
def runs(limit: int = 20) -> pd.DataFrame:
    return q(f"""SELECT {_RUN_COLS}, DATEDIFF(second, STARTED_AT, ENDED_AT) AS SECONDS
                 FROM SR_DB.OPS.RUN_LOG ORDER BY STARTED_AT DESC LIMIT ?""", [limit])


@st.cache_data(ttl=TTL_S, show_spinner=False)
def run_cost(limit: int = 10) -> pd.DataFrame:
    return q("""SELECT RUN_ID, TRIGGER_TYPE, AS_OF_WEEK, STATUS, SECONDS, CREDITS_EST, WAREHOUSE_CREDITS, AI_CREDITS,
                       AI_TOKENS, MODEL, GENERATOR, COST_BASIS
                FROM SR_DB.OPS.V_RUN_COST ORDER BY STARTED_AT DESC LIMIT ?""", [limit])


@st.cache_data(ttl=TTL_S, show_spinner=False)
def coco_log() -> pd.DataFrame:
    return q("""SELECT TICKET, SURFACE, COUNT(*) AS SESSIONS, SUM(LINES_ADDED) AS LINES_ADDED,
                       COUNT_IF(ARRAY_SIZE(TESTS) > 0) AS SESSIONS_WITH_TESTS, COUNT_IF(HUMAN_EDITS) AS HUMAN_EDITS,
                       MAX(LOGGED_AT) AS LAST_LOGGED
                FROM SR_DB.OPS.COCO_LOG GROUP BY TICKET, SURFACE ORDER BY TICKET""")


@st.cache_data(ttl=TTL_S, show_spinner=False)
def tests_latest() -> pd.DataFrame:
    return q("""SELECT TEST_ID, PASSED, FAILURES, DETAIL, RAN_AT FROM SR_DB.OPS.TEST_RESULT
                WHERE TEST_RUN_ID = (SELECT TEST_RUN_ID FROM SR_DB.OPS.TEST_RESULT ORDER BY RAN_AT DESC LIMIT 1)
                ORDER BY PASSED, TEST_ID""")


@st.cache_data(ttl=TTL_S, show_spinner=False)
def health_latest() -> pd.DataFrame:
    return q("SELECT CHECKED_AT, OBJECT_TYPE, OBJECT_NAME, STATE, DETAIL FROM SR_DB.OPS.V_HEALTH_LATEST "
             "ORDER BY IFF(STATE = 'OK', 1, 0), OBJECT_TYPE, OBJECT_NAME")


@st.cache_data(ttl=TTL_S, show_spinner=False)
def cost_daily(days: int = 14) -> pd.DataFrame:
    return q("SELECT USAGE_DATE, SOURCE, INTERFACE, CREDITS, TOKENS FROM SR_DB.OPS.COST_DAILY "
             "WHERE USAGE_DATE >= DATEADD(day, -?, CURRENT_DATE()) ORDER BY USAGE_DATE, SOURCE", [days])


# ---- Admin actions (admin app only; never cached) -------------------------------------------------------------

def clear_cache() -> None:
    st.cache_data.clear()


def start_task(task: str) -> str:
    """Raises Busy while a run is in progress. Returns the anchor time the progress panel watches from."""
    if task not in STARTABLE:
        raise ValueError(f"Task {task} cannot be started from the app")
    if task != "T_HEALTH" and active_run() is not None:
        raise Busy("A run is in progress")
    anchor = q("SELECT TO_VARCHAR(CURRENT_TIMESTAMP(), 'YYYY-MM-DD HH24:MI:SS.FF3 TZHTZM') AS T").T.iloc[0]
    session().sql(f"EXECUTE TASK SR_DB.OPS.{task}").collect()          # task name from the fixed set above
    clear_cache()
    return anchor


def reset_replay(week: date) -> str:
    return str(session().call("SR_DB.APP.SP_REPLAY_RESET", week.isoformat()))


def settings() -> pd.DataFrame:
    return q("SELECT SETTING_KEY, TO_JSON(SETTING_VALUE) AS VALUE_JSON, DESCRIPTION, UPDATED_AT "
             "FROM SR_DB.OPS.SETTINGS ORDER BY SETTING_KEY")


EDITABLE: dict[str, tuple[type, float | None, float | None]] = {
    "MIN_SHARE_PTS": (float, 0.05, 5), "MIN_VALUE_AT_STAKE": (float, 0, None), "MIN_Z": (float, 0, 10),
    "TOP_N": (int, 1, 10), "SUPPRESS_RUNS": (int, 0, 12), "SUPPRESS_GROWTH": (float, 0, 5),
    "ART_STORE_CHG": (float, 0, 1), "ART_CAT_TDP_JUMP": (float, 0, 2), "ART_CAT_SPPD_FLAT": (float, 0, 1),
    "ART_RECODE_TOL": (float, 0, 1), "ART_SPIKE_K": (float, 1, 20), "EW_DIST_DROP": (float, -1, 0),
    "EW_PRICE_RISE": (float, 0, 1), "MAX_CREDITS_PER_RUN": (float, 0, 50),
    "DISPLAY_ALIAS": (bool, None, None), "TEAMS_ENABLED": (bool, None, None), "NOTIFY_EMAILS": (list, None, None)}


def validate_setting(key: str, value: object, allowed_emails: list[str] | None = None) -> object:
    """The value to store, or ValueError. Pure, so it is unit-tested."""
    if key not in EDITABLE:
        raise ValueError(f"{key} cannot be edited here")
    kind, lo, hi = EDITABLE[key]
    if kind is bool:
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be true or false")
        return value
    if kind is list:
        if not isinstance(value, list) or not value or not all(isinstance(e, str) and "@" in e for e in value):
            raise ValueError("NOTIFY_EMAILS must be a non-empty list of email addresses")
        allowed = {e.lower() for e in (allowed_emails or [])}
        outside = [e for e in value if e.lower() not in allowed]
        if outside:
            raise ValueError(f"Not in the email integration's allowed recipients: {', '.join(outside)}")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    if kind is int and float(value) != int(value):
        raise ValueError(f"{key} must be a whole number")
    v = kind(value)
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise ValueError(f"{key} must be between {lo} and {hi if hi is not None else 'any'}")
    return v


def save_setting(key: str, value: object) -> None:
    v = validate_setting(key, value, cfg("NOTIFY_ALLOWED") or [])
    session().sql("UPDATE SR_DB.OPS.SETTINGS SET SETTING_VALUE = PARSE_JSON(?), UPDATED_AT = CURRENT_TIMESTAMP() "
                  "WHERE SETTING_KEY = ?", params=[json.dumps(v), key]).collect()
    clear_cache()
