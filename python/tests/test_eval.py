"""Golden-set runner tests (SR-044): file shape, number parsing, scoring and slot filling, without Snowflake."""
from __future__ import annotations

import csv
import importlib.util
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("run_eval", ROOT / "eval" / "run_eval.py")
ev = importlib.util.module_from_spec(spec)
sys.modules["run_eval"] = ev                  # dataclasses resolve annotations through sys.modules
spec.loader.exec_module(ev)


def row(check, tool="get_share_bridge", tol=0.05, args=None):
    return ev.GoldenRow("G01", "WHY", "q", tool, args or {"p_brand": "Bake 7", "p_market": "Store 24"}, "SELECT 1", check, tol)


def test_golden_set_has_the_T3_mix():
    rows = ev.load_golden()
    assert len(rows) == 30 and len({r.question_id for r in rows}) == 30
    assert Counter(r.qtype for r in rows) == {"WHY": 8, "WHO": 5, "REAL": 4, "WHATIF": 3, "NUMBER": 6, "METHOD": 2, "REFUSE": 2}
    for r in rows:
        if r.qtype in ("WHY", "WHO", "REAL", "WHATIF"):
            assert r.expected_tool in ev.TOOL_PROC and r.tool_args, r.question_id
        assert r.expected_sql.upper().startswith("SELECT")


def test_numbers_in_parses_units_and_ignores_names_and_periods():
    text = "Bake 7 lost -0.84 pts in Store 24 (L4W_VS_YA); share 23.4%, value at stake INR 1.8M, 2,500 stores."
    assert ev.numbers_in(text, {"Bake 7", "Store 24"}) == [-0.84, 23.4, 1_800_000.0, 2500.0]


def test_score_route_value_and_refuse():
    ok = ev.AgentAnswer("Share fell -0.84 pts, last 4 weeks vs year ago.", ["get_share_bridge", "check_artefact"], {})
    assert ev.score(row("VALUE_PTS"), -0.8412, ok) == (True, "")
    assert not ev.score(row("VALUE_PTS"), -0.95, ok)[0]
    wrong_route = ev.AgentAnswer("-0.84 pts", ["share_analyst"], {})
    assert ev.score(row("VALUE_PTS"), -0.84, wrong_route)[1].startswith("route")
    refuse = ev.GoldenRow("G29", "REFUSE", "q", None, None, "SELECT NULL", "REFUSE", 0)
    assert ev.score(refuse, None, ev.AgentAnswer("I can't average shares across markets (L4W).", [], {}))[0]
    assert not ev.score(refuse, None, ev.AgentAnswer("About 12.5% on average.", [], {}))[0]


def test_score_money_label_name_phrase():
    money = ev.AgentAnswer("Sales were INR 1.83M over L52W.", ["share_analyst"], {})
    assert ev.score(row("VALUE_MONEY", "share_analyst", 0.005), 1_834_220.5, money)[0]
    label = ev.AgentAnswer("This looks like a possible data effect: a retailer feed changed.", ["check_artefact"], {})
    assert ev.score(row("LABEL", "check_artefact", 0), "POSSIBLE_DATA_EFFECT", label)[0]
    assert ev.score(row("NAME", "share_flow", 0), "Golden Bake", ev.AgentAnswer("Mostly golden bake.", ["share_flow"], {}))[0]


def test_tools_only_answer_and_agent_reply_parsing():
    r = ev.GoldenRow("G09", "WHO", "q", "share_flow", {}, "SELECT 1", "NAME", 0)
    ans = ev.tool_answer(r, {"flows": [{"brand": "Golden Bake", "pts": 0.47}]})
    assert ans.text == "Golden Bake" and ans.tools == ["share_flow"]
    reply = {"role": "assistant", "content": [{"type": "tool_use", "tool_use": {"name": "get_share_bridge", "input": {}}},
                                              {"type": "text", "text": "It fell -0.84 pts."}]}
    parsed = ev.parse_agent_reply(reply)
    assert parsed.tools == ["get_share_bridge"] and parsed.text == "It fell -0.84 pts."


def test_propose_fills_slots_and_escapes_sql(tmp_path):
    out = tmp_path / "g.csv"
    slots = {f"<brand{i}>": f"Brand {i}" for i in range(1, 11)} | {f"<market{i}>": "O'Mart" for i in range(1, 11)}
    missing = ev.write_proposal(ev.GOLDEN, out, slots)
    rows = list(csv.DictReader(open(out)))
    assert "O''Mart" in rows[0]["EXPECTED_SQL"] and "O'Mart" in rows[0]["QUESTION"]
    assert "<lbrand1>" in missing and "<brand1>" not in missing
