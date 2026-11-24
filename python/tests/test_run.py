"""Orchestration and brief-writer tests against a fake Snowpark session (L8, L9, L13).

They cover the failure matrix locally: E09 credit cap, E10/E11 LLM failure and retry, E16 busy and duplicate
runs, critical versus optional steps. The real thing is checked by T-E2E-01..04 and T-NAR-04 on the account.
"""
from __future__ import annotations

import json
import re

import pytest

from sr_lib import run
from cases import GOOD_LLM, PACK


class FakeSQLError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class Row(dict):
    def __getitem__(self, k):
        return list(self.values())[k] if isinstance(k, int) else super().__getitem__(k)

    def as_dict(self):
        return dict(self)


class Result:
    def __init__(self, rows):
        self.rows = rows

    def collect(self):
        return [r if isinstance(r, Row) else Row(r) for r in self.rows]


class FakeSession:
    """Answers SQL by the first matching regex; records every statement and its parameters."""

    def __init__(self, handlers):
        self.handlers = handlers
        self.calls: list[tuple[str, list | None]] = []

    def sql(self, sql, params=None):
        self.calls.append((sql, params))
        for pattern, fn in self.handlers:
            if re.search(pattern, sql, re.S):
                out = fn(params) if callable(fn) else fn
                return Result(out)
        return Result([{"X": None}])

    def executed(self, pattern):
        return [(s, p) for s, p in self.calls if re.search(pattern, s, re.S)]


# ---- write_brief -------------------------------------------------------------------------------------------

def brief_session(alias=False):
    return FakeSession([
        (r"FROM SR_DB\.APP\.FACT_PACK", [{"BRIEF_ID": "b-0001", "PACK": json.dumps(PACK), "SCOPE_KEY": "Biscuits|M0|Acme Foods"}]),
        (r"CFG\('LLM_MODEL'\)", [{"LLM_MODEL": '"model-a"', "LLM_FALLBACK_MODEL": '"model-b"',
                                  "DISPLAY_ALIAS": "true" if alias else "false", "CURRENCY": '"INR"'}]),
        (r"COUNT_TOKENS", [{"N": 321}]),
        (r"V_ALIAS", [{"KIND": "BRAND", "REAL_NAME": "Crunchy", "ALIAS": "Brand A"}]),
    ])


def inserted_brief(session):
    sql, params = session.executed(r"INSERT INTO SR_DB\.APP\.BRIEF")[-1]
    keys = ["BRIEF_ID", "RUN_ID", "SCOPE_KEY", "AS_OF_WEEK", "GENERATOR", "MODEL", "HEADLINE", "BODY_MD", "BODY_HTML",
            "LLM_JSON", "VIOLATIONS", "TOKENS_IN", "TOKENS_OUT"]
    return dict(zip(keys, params))


def test_prompt_carries_fact_ids_not_values():
    p = run.build_prompt(PACK)
    assert "{{f12}}" in p and '"f3"' in p
    assert "-0.84" not in p and "1834220" not in p and "APP.SHIFT" not in p


def test_brief_first_attempt_published(monkeypatch):
    monkeypatch.setattr(run, "_complete", lambda s, m, p: json.dumps(GOOD_LLM))
    s = brief_session()
    assert run.write_brief(s, "r-0001") == "b-0001"
    b = inserted_brief(s)
    assert (b["GENERATOR"], b["MODEL"], b["TOKENS_IN"]) == ("LLM", "model-a", 321)
    assert '<span class="fact" title="APP.SHARE_BRIDGE#SHIFT_ID=s1;col=DIST_PTS">-0.61 pts</span>' in b["BODY_HTML"]
    assert "{{" not in b["HEADLINE"] and "-0.84 pts" in b["HEADLINE"]
    assert s.executed(r"DELETE FROM SR_DB\.APP\.BRIEF WHERE RUN_ID")          # idempotent per run


def test_brief_retry_lists_the_problems(monkeypatch):
    bad = json.loads(json.dumps(GOOD_LLM))
    bad["shifts"][0]["why"] = "Distribution fell 0.61 pts."
    prompts = []

    def fake(session, model, prompt):
        prompts.append((model, prompt))
        return json.dumps(bad if len(prompts) == 1 else GOOD_LLM)

    monkeypatch.setattr(run, "_complete", fake)
    s = brief_session()
    run.write_brief(s, "r-0001")
    b = inserted_brief(s)
    assert (b["GENERATOR"], b["MODEL"]) == ("LLM_RETRY", "model-b")
    assert [m for m, _ in prompts] == ["model-a", "model-b"] and "Fix these problems: V03_RAW_NUMBER" in prompts[1][1]
    assert json.loads(b["VIOLATIONS"])[0]["violations"][0]["code"] == "V03_RAW_NUMBER"


def test_T_NAR_04_models_fail_template_published(monkeypatch):
    def boom(session, model, prompt):
        raise RuntimeError(f"Unknown model {model}")

    monkeypatch.setattr(run, "_complete", boom)
    s = brief_session()
    run.write_brief(s, "r-0001")
    b = inserted_brief(s)
    assert (b["GENERATOR"], b["MODEL"], b["TOKENS_IN"]) == ("TEMPLATE", None, None)
    llm = json.loads(b["LLM_JSON"])
    from sr_lib.validator import validate_brief
    assert validate_brief(llm, PACK) == []
    attempts = json.loads(b["VIOLATIONS"])
    assert [a["violations"][0]["code"] for a in attempts[:2]] == ["V00_LLM_ERROR", "V00_LLM_ERROR"]
    assert attempts[2] == {"attempt": "template", "model": None, "violations": []}


def test_display_alias_masks_names_in_prompt_and_brief(monkeypatch):
    seen = []
    monkeypatch.setattr(run, "_complete", lambda s, m, p: seen.append(p) or (_ for _ in ()).throw(RuntimeError("x")))
    s = brief_session(alias=True)
    run.write_brief(s, "r-0001")
    b = inserted_brief(s)
    assert "Crunchy" not in seen[0] and "Brand A" in seen[0]
    assert "Crunchy" not in b["BODY_HTML"] and "Brand A" in b["BODY_HTML"]


def test_fenced_json_reply_is_accepted(monkeypatch):
    monkeypatch.setattr(run, "_complete", lambda s, m, p: "```json\n" + json.dumps(GOOD_LLM) + "\n```")
    s = brief_session()
    run.write_brief(s, "r-0001")
    assert inserted_brief(s)["GENERATOR"] == "LLM"


# ---- run_week ----------------------------------------------------------------------------------------------

def run_session(*, busy=0, done=0, cap=5.0, fail=None, credits_hours=0.01):
    """fail: {step procedure name fragment: message} to raise a step error."""
    fail = fail or {}

    def step(params, name):
        def _f(_params):
            if name in fail:
                raise FakeSQLError(fail[name])
            return [{"R": 7}]
        return _f

    handlers = [
        (r"STATUS = 'RUNNING'", [{"N": busy}]),
        (r"STATUS = 'SUCCEEDED' AND AS_OF_WEEK", [{"N": done}]),
        (r"CFG\('AS_OF_WEEK_END'\)::VARCHAR AS AS_OF", [{"AS_OF": "2026-11-07", "SCOPE_KEY": "Biscuits|M0|Acme Foods"}]),
        (r"MAX_CREDITS_PER_RUN", [{"CAP": cap}]),
        (r"QUERY_HISTORY_BY_SESSION", [{"WAREHOUSE_SIZE": "Medium", "HOURS": credits_hours}]),
        (r"FLATTEN\(INPUT => SR_DB\.OPS\.CFG\('COMPARES'\)\)", [{"CMP_CODE": "L4W_VS_YA", "N_BASE": 120, "N_WEEKS": 110}]),
    ]
    for proc in ("SP_CAPABILITY_CHECK", "SP_SNAPSHOT", "SP_DETECT_SHIFTS", "SP_ML_SHARE_ANOMALY", "SP_BRIDGE",
                 "SP_ARTEFACT", "SP_RANK", "SP_WHERE_INSIGHTS", "SP_WHERE", "SP_FLOW", "SP_EARLY_WARNING",
                 "SP_ML_LEVER_ANOMALY", "SP_BUILD_FACT_PACK", "SP_WRITE_BRIEF"):
        handlers.append((rf"CALL SR_DB\.APP\.{proc}\(", step(None, proc)))
    return FakeSession(handlers)


def steps_logged(s):
    return [(p[1], p[2], p[3], p[6]) for _, p in s.executed(r"INSERT INTO SR_DB\.OPS\.STEP_LOG")]


def run_status(s):
    return s.executed(r"UPDATE SR_DB\.OPS\.RUN_LOG")[-1][1][0]


@pytest.fixture(autouse=True)
def fake_errors(monkeypatch):
    monkeypatch.setattr(run, "STEP_ERRORS", FakeSQLError)


def test_T_E2E_01_shape_all_steps_logged():
    s = run_session()
    rid = run.run_week(s, "MANUAL", True)
    assert re.fullmatch(r"[0-9a-f-]{36}", rid) and run_status(s) == "SUCCEEDED"
    logged = steps_logged(s)
    assert {n for n, *_ in logged} == set(range(1, 15))                   # 14 step numbers, 1 OPEN .. 14 CLOSE
    assert all(st == "OK" for _, _, st, _ in logged)
    tags = [sql for sql, _ in s.executed(r"ALTER SESSION SET QUERY_TAG")]
    assert f"ALTER SESSION SET QUERY_TAG = 'SR|run={rid}|step=BRIDGE'" in tags
    assert s.executed(r"CALL SR_DB\.OPS\.SP_HEALTH_CHECK")


def test_optional_step_failure_downgrades_to_warn():
    s = run_session(fail={"SP_WHERE_INSIGHTS": "TOP_INSIGHTS quota"})
    run.run_week(s, "MANUAL", True)
    assert ("TOP_INSIGHTS", "WARN") in {(n, st) for _, n, st, _ in steps_logged(s)}
    assert run_status(s) == "SUCCEEDED"


def test_critical_step_failure_stops_the_run():
    s = run_session(fail={"SP_BRIDGE": "division by zero"})
    run.run_week(s, "MANUAL", True)
    logged = {(n, st) for _, n, st, _ in steps_logged(s)}
    assert ("BRIDGE", "FAILED") in logged and not s.executed(r"CALL SR_DB\.APP\.SP_ARTEFACT")
    assert run_status(s) == "FAILED"
    assert s.executed(r"UPDATE SR_DB\.OPS\.RUN_LOG")[-1][1][1] == "BRIDGE: division by zero"
    assert s.executed(r"CALL SR_DB\.OPS\.SP_HEALTH_CHECK")                # health check runs on every path


def test_T_E2E_04_credit_cap_skips_cost_steps():
    s = run_session(cap=0.0)
    run.run_week(s, "MANUAL", True)
    skipped = {n for _, n, st, msg in steps_logged(s) if st == "SKIPPED" and msg == "credit cap"}
    assert skipped == run.OPTIONAL_COST_STEPS and run_status(s) == "SUCCEEDED"


def test_T_E2E_03_busy_run_is_skipped():
    s = run_session(busy=1)
    assert run.run_week(s, "MANUAL", True) == "SKIPPED"
    _, params = s.executed(r"INSERT INTO SR_DB\.OPS\.RUN_LOG")[0]
    assert params[4] == "SKIPPED" and params[6].startswith("BUSY")
    assert not s.executed(r"CALL SR_DB\.APP\.")


def test_week_already_ran_is_skipped_unless_forced():
    s = run_session(done=1)
    assert run.run_week(s, "STREAM", False) == "SKIPPED"
    assert s.executed(r"INSERT INTO SR_DB\.OPS\.RUN_LOG")[0][1][6].startswith("ALREADY_RAN")
    forced = run_session(done=1)
    assert run.run_week(forced, "REPLAY", True) != "SKIPPED"


def test_E02_short_history_warns_on_detect():
    s = run_session()
    s.handlers.insert(0, (r"FLATTEN\(INPUT => SR_DB\.OPS\.CFG\('COMPARES'\)\)",
                          [{"CMP_CODE": "L4W_VS_YA", "N_BASE": 0, "N_WEEKS": 40}]))
    run.run_week(s, "MANUAL", True)
    detect = [(st, msg) for _, n, st, msg in steps_logged(s) if n == "DETECT"][0]
    assert detect == ("WARN", "L4W_VS_YA needs 56 weeks; 40 available")


def test_internal_error_never_leaves_a_run_running():
    s = run_session()
    s.handlers.insert(0, (r"MAX_CREDITS_PER_RUN", lambda p: (_ for _ in ()).throw(ValueError("bad setting"))))
    run.run_week(s, "MANUAL", True)
    assert run_status(s) == "FAILED"
    assert s.executed(r"UPDATE SR_DB\.OPS\.RUN_LOG")[-1][1][1].startswith("INTERNAL: bad setting")
