"""Smoke tests: every page of both apps runs headless (streamlit.testing AppTest) against a fake data module.

They catch errors in page code that only show at run time: a wrong column, a bad chart spec, a missing key.
No section may fall back to "Couldn't load ...", and the admin-only parts appear only in the admin app.
"""
from __future__ import annotations

import json
import sys
import types
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest  # noqa: E402

from sr_lib.render import render_html  # noqa: E402
from cases import GOOD_LLM, PACK  # noqa: E402

APP_DIR = Path(__file__).resolve().parents[2] / "streamlit"
TS = pd.Timestamp("2026-11-09 06:00:00+00:00")

SETTINGS = {"AS_OF_WEEK_END": "2026-11-07", "SCOPE_CATEGORY": "Biscuits", "SCOPE_PARENT_MARKET": "M0",
            "FOCUS_MANUFACTURER": "Acme Foods", "CURRENCY": "INR", "DISPLAY_ALIAS": False, "TOP_N": 5,
            "MIN_SHARE_PTS": 0.3, "NOTIFY_EMAILS": ["a@x.com"], "NOTIFY_ALLOWED": ["a@x.com"]}


def build_fake():
    import sr_ui.data as real
    fake = types.ModuleType("sr_ui.data")
    for k in ("Run", "Busy", "EDITABLE", "validate_setting", "TASKS", "STARTABLE", "TTL_S", "BUSY_MIN"):
        setattr(fake, k, getattr(real, k))
    run = real.Run("r-0001", "REPLAY", date(2026, 11, 7), "Biscuits|M0|Acme Foods", "SUCCEEDED", "A", 12, 2, "b-0001",
                   0.42, TS, TS + pd.Timedelta(minutes=3), None)
    shifts = pd.DataFrame({
        "SHIFT_ID": ["s1", "s2", "s3"], "RANK_NO": [1, 2, 3], "CMP_CODE": ["L4W_VS_YA", "L12W_VS_YA", "L4W_VS_YA"],
        "MARKET_ID": ["M0", "M1", "M2"], "CATEGORY": ["Biscuits"] * 3, "MANUFACTURER": ["Acme Foods", "Rival Co", "Tea Co"],
        "BRAND": ["Crunchy", "Golden Bake", "Tea Time"], "IS_FOCUS": [True, False, False], "SH1": [0.2341, 0.121, 0.08],
        "SH0": [0.2425, 0.1105, 0.097], "D_SHARE_PTS": [-0.84, 1.05, -1.7], "VALUE_AT_STAKE": [-1834220.5, 2290000.0, -900000.0],
        "Z_SCORE": [-3.1, 2.4, None], "ANOMALY_CONFIRMED": [True, False, False], "CONFIDENCE": [1.0, 0.8, 0.5],
        "ARTEFACT_LABEL": ["MARKET_MOVE", "MIXED", "POSSIBLE_DATA_EFFECT"], "SCORE": [2.7e6, 1.1e6, 1.3e5],
        "SUPPRESSED": [False, False, False], "SUPPRESS_REASON": [None, None, "Held back for data checks"],
        "SELECTED": [True, True, False]})
    detail = {**shifts.iloc[0].to_dict(), "RUN_ID": "r-0001", "D_SHARE": -0.0084, "ANOMALY_WEEKS": 3, "MODE": "A",
              "STATUS": "OK", "NOTE": None}
    bridge = {"SHIFT_ID": "s1", "MODE": "A", "STATUS": "OK", "SH1": 0.2341, "SH0": 0.2425, "D_SHARE": -0.0084,
              "LMDI_WEIGHT": 0.238, "DIST_PTS": -0.61, "VELOCITY_PTS": -0.30, "PRICE_PTS": 0.05, "PROMO_PTS": 0.02,
              "RESIDUAL_PTS": 1e-12, "DS1": 0.30, "DS0": 0.32, "PI1": 1.0, "PI0": 1.0, "PRI1": 1.1, "PRI0": 1.09, "NOTE": None}
    where = pd.DataFrame({"METHOD": ["EXACT_RETAILER"] * 3 + ["TOP_INSIGHTS"], "RANK_NO": [1, 2, 3, 1],
                          "CONTRIBUTOR": ["MegaMart", "QuickShop", "Rest of market", "MegaMart and 500g"],
                          "PERF_PTS": [-0.40, -0.25, 0.05, None], "MIX_PTS": [-0.12, -0.05, -0.07, None],
                          "TOTAL_PTS": [-0.52, -0.30, -0.02, None], "METRIC_CONTROL": [None] * 3 + [1e6],
                          "METRIC_TEST": [None] * 3 + [8e5], "CONTRIBUTION": [None] * 3 + [-2e5],
                          "RELATIVE_CONTRIBUTION": [None] * 3 + [0.6], "GROWTH_RATE": [None] * 3 + [-0.2]})
    weeks = pd.date_range(end="2026-11-07", periods=104, freq="7D")
    trend = pd.DataFrame({"WEEK_END_DATE": weeks, "VALUE_SHARE_PCT": 24.0, "DIST_SHARE_PCT": 31.0})
    steps = pd.DataFrame({"STEP_NO": [1, 2, 4], "STEP": ["OPEN", "CAPABILITY", "DETECT"], "STATUS": ["OK", "OK", "WARN"],
                          "STARTED_AT": [TS, TS, TS], "ENDED_AT": [TS + pd.Timedelta(seconds=s) for s in (1, 3, 9)],
                          "ROWS_WRITTEN": [None, None, 40], "MESSAGE": [None, None, "L52W_VS_YA needs 104 weeks"],
                          "SECONDS": [1, 3, 9]})
    brief = {"BRIEF_ID": "b-0001", "RUN_ID": "r-0001", "SCOPE_KEY": "Biscuits|M0|Acme Foods", "AS_OF_WEEK": date(2026, 11, 7),
             "STATUS": "PUBLISHED", "GENERATOR": "LLM_RETRY", "MODEL": "model-b", "HEADLINE": "Acme Foods lost ground",
             "BODY_MD": "# x", "BODY_HTML": render_html(GOOD_LLM, PACK, "INR"), "LLM_JSON": GOOD_LLM,
             "VIOLATIONS": [{"attempt": 1, "model": "model-a",
                             "violations": [{"code": "V03_RAW_NUMBER", "path": "shifts[0].why", "detail": "raw number '0.61'"}]},
                            {"attempt": 2, "model": "model-b", "violations": []}],
             "TOKENS_IN": 1200, "TOKENS_OUT": 300, "PUBLISHED_AT": TS, "NOTIFIED_AT": TS, "NOTIFY_ATTEMPTS": 1}
    facts = pd.DataFrame([{"FACT_ID": k, "V": f["v"], "UNIT": f["u"], "DECIMALS": f["d"], "SOURCE": f["src"]}
                          for k, f in PACK["facts"].items()])
    calls = []
    fns = {
        "cfg": lambda k: SETTINGS.get(k), "scope_key": lambda: "Biscuits|M0|Acme Foods", "viewer_name": lambda: None,
        "aliases": lambda: {("BRAND", "Crunchy"): "Brand A"}, "market_names": lambda: {"M0": "All India", "M1": "Store 24", "M2": "QuickShop"},
        "current_run": lambda: run, "latest_attempt": lambda: run, "active_run": lambda: None,
        "run_started_since": lambda since: run, "step_log": lambda rid: steps,
        "task_last_run": lambda t: {"STATE": "SUCCEEDED", "ERROR_MESSAGE": None},
        "shifts": lambda rid: shifts,
        "held_back": lambda rid: shifts[~shifts.SELECTED][["SHIFT_ID", "CMP_CODE", "MARKET_ID", "BRAND", "D_SHARE_PTS", "SCORE"]].assign(RULES=[["R2_FEED"]]),
        "watchlist": lambda rid: pd.DataFrame({"MARKET_ID": ["M0"], "BRAND": ["Crunchy"], "SIGNAL": ["DIST_DROP"],
                                               "LATEST_WEEK": [date(2026, 11, 7)], "LEVER_LATEST": [0.29], "LEVER_L4W": [0.315],
                                               "LEVER_CHG": [-0.081], "PROJECTED_SHARE_PTS": [-0.19], "ML_CONFIRMED": [True], "NOTE": ["m"]}),
        "kpis": lambda rid: {"N_PASSED": 12, "N_SELECTED": 2, "N_DATA_EFFECT": 1, "VALUE_SELECTED": 4.1e6},
        "shift": lambda sid: detail, "bridge": lambda sid: bridge, "where": lambda sid: where,
        "flow": lambda *a: pd.DataFrame({"COUNTERPART": ["Golden Bake", "Tea Time"], "FLOW_PTS": [0.47, 0.2]}),
        "artefacts": lambda *a: pd.DataFrame({"RULE_ID": ["R5_SPIKE"], "SEVERITY": ["MEDIUM"], "BRAND": [None],
                                              "EVIDENCE": [{"weeks": ["2026-10-31"], "source": "CORE.DT_CAT_WEEK"}]}),
        "trend": lambda *a: trend, "what_if": lambda *a: {"share_now_pts": 23.41, "share_if_pts": 24.9, "delta_pts": 1.49,
                                                          "assumption": "Other levers held constant; mechanical, not a forecast"},
        "briefs": lambda limit=12: pd.DataFrame([{k: brief[k] for k in ("BRIEF_ID", "RUN_ID", "AS_OF_WEEK", "HEADLINE", "GENERATOR",
                                                                        "MODEL", "PUBLISHED_AT", "NOTIFIED_AT", "NOTIFY_ATTEMPTS")}]),
        "brief": lambda bid: brief, "brief_facts": lambda bid: facts,
        "brief_notifications": lambda bid: pd.DataFrame({"CHANNEL": ["EMAIL"], "STATUS": ["SENT"], "SENT_AT": [TS], "MESSAGE": [None]}),
        "eval_latest": lambda: pd.DataFrame({"EVAL_RUN_ID": ["e1"] * 2, "QUESTION_ID": ["G01", "G29"], "QUESTION": ["q1", "q2"],
                                             "EXPECTED_TOOL": ["get_share_bridge", None], "ACTUAL_TOOLS": ['["get_share_bridge"]', "[]"],
                                             "PASSED": [True, False], "NOTE": ["", "stated figures"], "EVALUATED_AT": [TS, TS]}),
        "recon_latest": lambda: pd.DataFrame({"CHECK_ID": ["R01"], "DESCRIPTION": ["Category sales"], "REFERENCE_VALUE": [1e8],
                                              "SR_VALUE": [1.001e8], "ABS_DIFF": [1e5], "PASSED": [True], "CHECKED_AT": [TS]}),
        "bridge_residual_max": lambda rid: 3e-13,
        "runs": lambda limit=20: pd.DataFrame([{**{k.upper(): v for k, v in run.__dict__.items()}, "SECONDS": 180}]),
        "run_cost": lambda limit=10: pd.DataFrame({"RUN_ID": ["r-0001"], "TRIGGER_TYPE": ["REPLAY"], "AS_OF_WEEK": [date(2026, 11, 7)],
                                                   "STATUS": ["SUCCEEDED"], "SECONDS": [180], "CREDITS_EST": [0.42],
                                                   "WAREHOUSE_CREDITS": [None], "AI_CREDITS": [None], "AI_TOKENS": [1500],
                                                   "MODEL": ["model-b"], "GENERATOR": ["LLM_RETRY"], "COST_BASIS": ["ESTIMATE"]}),
        "coco_log": lambda: pd.DataFrame({"TICKET": ["SR-022"], "SURFACE": ["claude-code"], "SESSIONS": [1], "LINES_ADDED": [400],
                                          "SESSIONS_WITH_TESTS": [1], "HUMAN_EDITS": [0], "LAST_LOGGED": [TS]}),
        "tests_latest": lambda: pd.DataFrame({"TEST_ID": ["T-BR-01"], "PASSED": [True], "FAILURES": [0], "DETAIL": [None], "RAN_AT": [TS]}),
        "health_latest": lambda: pd.DataFrame({"CHECKED_AT": [TS], "OBJECT_TYPE": ["TASK"], "OBJECT_NAME": ["T_RUN_WEEK"],
                                               "STATE": ["OK"], "DETAIL": ['{"state": "started"}']}),
        "cost_daily": lambda days=14: pd.DataFrame(),
        "settings": lambda: pd.DataFrame({"SETTING_KEY": list(SETTINGS), "VALUE_JSON": [json.dumps(v) for v in SETTINGS.values()],
                                          "DESCRIPTION": [""] * len(SETTINGS), "UPDATED_AT": [TS] * len(SETTINGS)}),
        "start_task": lambda t: calls.append(("start", t)) or "2026-11-09 06:00:00.000 +0000",
        "reset_replay": lambda w: "AS_OF=2026-10-31", "save_setting": lambda k, v: calls.append(("save", k, v)),
        "clear_cache": lambda: None,
    }
    for k, f in fns.items():
        setattr(fake, k, f)
    fake.calls = calls
    return fake


@pytest.fixture()
def fake_data(monkeypatch):
    import sr_ui
    fake = build_fake()
    monkeypatch.setitem(sys.modules, "sr_ui.data", fake)
    monkeypatch.setattr(sr_ui, "data", fake, raising=False)
    return fake


def _run(main: str, page: str | None = None) -> AppTest:
    at = AppTest.from_file(str(APP_DIR / main), default_timeout=30)
    at.run()
    if page:
        at.switch_page(page)
        at.run()
    return at


def _texts(at: AppTest) -> str:
    parts = [e.value for e in at.markdown] + [e.value for e in at.title] + [e.value for e in at.header] + \
            [e.value for e in at.subheader] + [e.value for e in at.caption] + [e.value for e in at.info] + \
            [e.value for e in at.warning] + [e.value for e in at.error] + [e.value for e in at.success]
    return "\n".join(str(p) for p in parts)


@pytest.mark.parametrize("main", ["streamlit_app.py", "admin_app.py"])
@pytest.mark.parametrize("page,expect", [(None, "This week's shifts"), ("pages/1_Shift_detail.py", "What moved share"),
                                         ("pages/2_Brief.py", "Brief"), ("pages/3_Trust.py", "Pipeline health")])
def test_every_page_renders(fake_data, main, page, expect):
    at = _run(main, page)
    assert not at.exception, [e.value for e in at.exception]
    text = _texts(at)
    assert expect in text
    assert "Couldn't load" not in text, text


def test_replay_panel_only_in_admin(fake_data):
    ro, admin = _run("streamlit_app.py"), _run("admin_app.py")
    labels = lambda at: {b.label for b in at.button}  # noqa: E731
    assert "Load next week" not in labels(ro) and "Load next week" in labels(admin)


def test_settings_page_only_in_admin(fake_data):
    at = _run("admin_app.py", "pages/4_Settings.py")
    assert not at.exception and "Change a setting" in _texts(at)


def test_load_next_week_starts_the_replay_task(fake_data):
    at = _run("admin_app.py")
    next(b for b in at.button if b.label == "Load next week").click()
    at.run()
    assert ("start", "T_REPLAY_NEXT") in fake_data.calls
