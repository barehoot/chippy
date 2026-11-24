#!/usr/bin/env python3
"""Golden-set evaluation of the Share Radar agent (T3, SR-044).

  python3 eval/run_eval.py --connection sr [--load] [--tools-only] [--only G01,G02]
  python3 eval/run_eval.py --connection sr --propose [--out eval/golden_set.csv]

A question passes when its route and its check both pass. Expected values are not typed in: each row's
EXPECTED_SQL computes them from the governed views when the eval runs, so the set stays right as the replay
moves the as-of week. --tools-only calls the TOOL_* procedures directly (no LLM, no AI credits) for the four
custom-tool types. --propose fills the <brandN>/<marketN> slots of the template from the latest run, for a
person to review before the set is committed. Writes one OPS.EVAL_RESULT row per question under a new
EVAL_RUN_ID and returns 0 when at least PASS_BAR questions pass.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

AGENT = "SR_DB.SEM.SHARE_RADAR_AGENT"
PASS_BAR = 27
GOLDEN = Path(__file__).resolve().parent / "golden_set.csv"
TOOL_FIELD = {"get_share_bridge": "change_pts", "share_flow": "flows[0].brand",
              "check_artefact": "label", "what_if": "share_if_pts"}      # used by --tools-only
TOOL_PROC = {"get_share_bridge": ("SR_DB.APP.TOOL_GET_SHARE_BRIDGE", ("p_brand", "p_market", "p_cmp_code")),
             "check_artefact": ("SR_DB.APP.TOOL_CHECK_ARTEFACT", ("p_market", "p_cmp_code", "p_brand")),
             "share_flow": ("SR_DB.APP.TOOL_SHARE_FLOW", ("p_brand", "p_market", "p_cmp_code")),
             "what_if": ("SR_DB.APP.TOOL_WHAT_IF", ("p_brand", "p_market", "p_lever", "p_target"))}
LABEL_WORDS = {"MARKET_MOVE": ("market move", "real"), "MIXED": ("mixed",), "POSSIBLE_DATA_EFFECT": ("data effect",)}
PERIOD_TOKENS = {"L4W", "L12W", "L52W", "P4W", "4W", "12W", "52W", "L4W_VS_YA", "L4W_VS_PP", "L12W_VS_YA", "L52W_VS_YA"}
NUMBER = re.compile(r"(?<![\w.])([-+−]?)\s*(?:[A-Z]{3}\s*)?(\d[\d,]*(?:\.\d+)?)\s*([KMB](?![a-z])|%|\s?pts\b)?", re.I)
SCALE = {"K": 1e3, "M": 1e6, "B": 1e9}


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


def load_golden(path: str | Path = GOLDEN) -> list[GoldenRow]:
    with open(path, newline="", encoding="utf-8") as f:
        return [GoldenRow(r["QUESTION_ID"], r["QTYPE"], r["QUESTION"], r["EXPECTED_TOOL"] or None,
                          json.loads(r["TOOL_ARGS"]) if r["TOOL_ARGS"] else None, r["EXPECTED_SQL"],
                          r["CHECK_TYPE"], float(r["TOLERANCE"] or 0)) for r in csv.DictReader(f)]


# ---- scoring (pure) ----------------------------------------------------------------------------------------

def numbers_in(text: str, ignore: set[str] = frozenset()) -> list[float]:
    """'-0.84 pts', '23.4%', 'INR 1.8M' -> -0.84, 23.4, 1800000.0. Digits inside ignored tokens (period codes,
    names) do not count."""
    for tok in sorted(set(ignore) | PERIOD_TOKENS, key=len, reverse=True):
        if any(ch.isdigit() for ch in tok):
            text = re.sub(re.escape(tok), " ", text, flags=re.I)
    out = []
    for sign, num, suffix in NUMBER.findall(text):
        v = float(num.replace(",", ""))
        v *= SCALE.get((suffix or "").strip().upper(), 1)
        out.append(-v if sign in ("-", "−") else v)
    return out


def _names(row: GoldenRow) -> set[str]:
    vals = set((row.tool_args or {}).values())
    return {v for v in vals if isinstance(v, str)}


def score(row: GoldenRow, expected: object, ans: AgentAnswer) -> tuple[bool, str]:
    """(passed, reason). Route first, then the check (T3 table)."""
    if row.check_type != "REFUSE" and row.expected_tool and row.expected_tool not in ans.tools:
        return False, f"route: expected {row.expected_tool}, called {ans.tools or 'nothing'}"
    text = ans.text or ""
    nums = numbers_in(text, _names(row))
    if row.check_type in ("VALUE_PTS", "VALUE_PCT"):
        if expected is None:
            return False, "no expected value (EXPECTED_SQL returned nothing)"
        ok = any(abs(n - float(expected)) <= row.tolerance for n in nums)
        return ok, "" if ok else f"no number within {row.tolerance} of {float(expected):.4f} in {nums[:6]}"
    if row.check_type == "VALUE_MONEY":
        if expected is None:
            return False, "no expected value"
        e = float(expected)
        ok = any(abs(n - e) <= max(row.tolerance, 0.005) * abs(e) for n in nums)
        return ok, "" if ok else f"no money figure within 0.5% of {e:,.0f} in {nums[:6]}"
    if row.check_type == "NAME":
        ok = expected is not None and str(expected).lower() in text.lower()
        return ok, "" if ok else f"'{expected}' not named"
    if row.check_type == "LABEL":
        words = LABEL_WORDS.get(str(expected), ())
        ok = any(w in text.lower() for w in words)
        return ok, "" if ok else f"label {expected} not stated (looked for {words})"
    if row.check_type == "PHRASE":
        ok = expected is not None and str(expected).lower() in text.lower()
        return ok, "" if ok else f"phrase '{expected}' missing"
    if row.check_type == "REFUSE":
        ok = not nums
        return ok, "" if ok else f"stated figures {nums[:6]}"
    return False, f"unknown check {row.check_type}"


def _path(obj: object, path: str) -> object:
    for part in re.findall(r"[^.\[\]]+", path):
        if obj is None:
            return None
        obj = obj[int(part)] if part.isdigit() and isinstance(obj, list) and int(part) < len(obj) else (
            obj.get(part) if isinstance(obj, dict) else None)
    return obj


def tool_answer(row: GoldenRow, payload: dict) -> AgentAnswer:
    """A tool payload dressed as an answer, so --tools-only scores with the same rules."""
    value = _path(payload, TOOL_FIELD[row.expected_tool])
    if row.check_type == "LABEL":
        text = {"MARKET_MOVE": "market move", "MIXED": "mixed", "POSSIBLE_DATA_EFFECT": "data effect"}.get(str(value), str(value))
    else:
        text = "" if value is None else str(value)
    return AgentAnswer(text=text, tools=[row.expected_tool], raw=payload)


def parse_agent_reply(reply: object) -> AgentAnswer:
    """Text and tool names from a DATA_AGENT_RUN reply, whatever its nesting."""
    data = json.loads(reply) if isinstance(reply, str) else reply
    texts, tools = [], []

    def walk(o):
        if isinstance(o, dict):
            t = o.get("type")
            if t == "text" and isinstance(o.get("text"), str):
                texts.append(o["text"])
            if t in ("tool_use", "tool_call"):
                inner = o.get("tool_use") or o.get("tool_call") or o
                name = inner.get("name") if isinstance(inner, dict) else None
                if name:
                    tools.append(name)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return AgentAnswer(text="\n".join(texts), tools=list(dict.fromkeys(tools)), raw=data if isinstance(data, dict) else {"reply": data})


# ---- Snowflake ---------------------------------------------------------------------------------------------

def session_for(connection: str):
    from snowflake.snowpark import Session
    return Session.builder.config("connection_name", connection).create()


def upload_golden(session, rows: list[GoldenRow]) -> None:
    session.sql(Path(__file__).with_name("run_eval.sql").read_text().split("-- REPORT")[0]).collect()
    session.sql("TRUNCATE TABLE SR_DB.OPS.GOLDEN_SET").collect()
    for r in rows:
        session.sql("INSERT INTO SR_DB.OPS.GOLDEN_SET (QUESTION_ID, QTYPE, QUESTION, EXPECTED_TOOL, TOOL_ARGS, EXPECTED_SQL, "
                    "CHECK_TYPE, TOLERANCE) SELECT ?, ?, ?, ?, PARSE_JSON(?), ?, ?, ?",
                    params=[r.question_id, r.qtype, r.question, r.expected_tool,
                            json.dumps(r.tool_args) if r.tool_args else None, r.expected_sql, r.check_type,
                            r.tolerance]).collect()


def expected_value(session, row: GoldenRow) -> object:
    rows = session.sql(row.expected_sql).collect()
    return rows[0][0] if rows else None


def ask_agent(session, question: str, timeout_s: int = 120) -> AgentAnswer:
    body = json.dumps({"messages": [{"role": "user", "content": [{"type": "text", "text": question}]}]})
    reply = session.sql("SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(?, ?)", params=[AGENT, body]).collect()[0][0]
    data = json.loads(reply) if isinstance(reply, str) else reply
    t0 = time.monotonic()
    while isinstance(data, dict) and data.get("status") == "in_progress" and time.monotonic() - t0 < timeout_s:
        time.sleep(3)
        thread = data.get("thread_id")
        reply = session.sql("SELECT SNOWFLAKE.CORTEX.THREAD_MESSAGES(?)", params=[thread]).collect()[0][0]
        data = json.loads(reply) if isinstance(reply, str) else reply
    return parse_agent_reply(data)


def call_tool(session, row: GoldenRow) -> AgentAnswer:
    proc, keys = TOOL_PROC[row.expected_tool]
    args = [row.tool_args.get(k, "") for k in keys]
    out = session.sql(f"CALL {proc}({', '.join('?' for _ in keys)})", params=args).collect()[0][0]
    return tool_answer(row, json.loads(out))


def propose(session, template: list[GoldenRow]) -> dict[str, str]:
    """Slot values from the latest successful run: <brandN>/<marketN>/<market_idN> from its ranked L4W_VS_YA shifts,
    <lbrandN>/<lmarketN> from losing brands, <pbrandN>/<pmarketN>/<pmarket_idN> with possible data effects first."""
    run = "(SELECT RUN_ID FROM SR_DB.OPS.RUN_LOG WHERE STATUS = 'SUCCEEDED' ORDER BY STARTED_AT DESC LIMIT 1)"
    base = ("SELECT r.BRAND, m.MARKET_NAME, r.MARKET_ID FROM SR_DB.APP.SHIFT_RANKED r "
            f"JOIN SR_DB.SRC.V_SRC_MARKET m ON m.MARKET_ID = r.MARKET_ID WHERE r.RUN_ID = {run} AND r.CMP_CODE = 'L4W_VS_YA' ")
    lists = {"": base + "ORDER BY r.SELECTED DESC, r.RANK_NO",
             "l": base + "AND r.D_SHARE < 0 ORDER BY r.SELECTED DESC, r.RANK_NO",
             "p": base + "ORDER BY (r.ARTEFACT_LABEL = 'POSSIBLE_DATA_EFFECT') DESC, (r.ARTEFACT_LABEL = 'MIXED') DESC, r.RANK_NO"}
    slots: dict[str, str] = {}
    for prefix, sql in lists.items():
        for i, r in enumerate(session.sql(sql).collect()[:10], start=1):
            slots[f"<{prefix}brand{i}>"], slots[f"<{prefix}market{i}>"], slots[f"<{prefix}market_id{i}>"] = r[0], r[1], r[2]
    return slots


def fill(text: str, slots: dict[str, str], sql: bool = False) -> str:
    for k, v in slots.items():
        text = text.replace(k, v.replace("'", "''") if sql else v)
    return text


def write_proposal(template_path: Path, out_path: Path, slots: dict[str, str]) -> list[str]:
    with open(template_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["QUESTION"] = fill(r["QUESTION"], slots)
        r["EXPECTED_SQL"] = fill(r["EXPECTED_SQL"], slots, sql=True)
        if r["TOOL_ARGS"]:
            r["TOOL_ARGS"] = json.dumps({k: fill(v, slots) for k, v in json.loads(r["TOOL_ARGS"]).items()})
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return sorted({m for r in rows for m in re.findall(r"<[a-z_]+\d+>", r["QUESTION"] + r["EXPECTED_SQL"])})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--connection", default="sr")
    ap.add_argument("--load", action="store_true", help="replace OPS.GOLDEN_SET with eval/golden_set.csv")
    ap.add_argument("--tools-only", action="store_true", help="call the TOOL_* procedures, no LLM")
    ap.add_argument("--only", default="", help="comma-separated question IDs")
    ap.add_argument("--propose", action="store_true", help="fill the template's slots from the latest run")
    ap.add_argument("--out", default=str(GOLDEN))
    args = ap.parse_args(argv)

    session = session_for(args.connection)
    try:
        if args.propose:
            missing = write_proposal(GOLDEN, Path(args.out), propose(session, load_golden()))
            print(f"Wrote {args.out}. Review every question before committing." +
                  (f" Unfilled slots (too few shifts): {missing}" if missing else ""))
            return 0
        rows = load_golden()
        if args.load:
            upload_golden(session, rows)
        only = {q.strip() for q in args.only.split(",") if q.strip()}
        rows = [r for r in rows if not only or r.question_id in only]
        if args.tools_only:
            rows = [r for r in rows if r.expected_tool in TOOL_PROC]
        eval_id, passed = str(uuid.uuid4()), 0
        for r in rows:
            expected = expected_value(session, r)
            try:
                ans = call_tool(session, r) if args.tools_only else ask_agent(session, r.question)
                ok, why = score(r, expected, ans)
            except Exception as e:                                  # a failed call is a failed question
                ans, ok, why = AgentAnswer("", [], {}), False, f"call failed: {e}"[:300]
            passed += ok
            session.sql("INSERT INTO SR_DB.OPS.EVAL_RESULT (EVAL_RUN_ID, QUESTION_ID, QUESTION, EXPECTED, ACTUAL, "
                        "EXPECTED_TOOL, ACTUAL_TOOLS, PASSED, NOTE) "
                        "SELECT ?, ?, ?, TO_VARIANT(?), TO_VARIANT(?), ?, PARSE_JSON(?), ?, ?",
                        params=[eval_id, r.question_id, r.question, None if expected is None else str(expected),
                                ans.text[:4000], r.expected_tool, json.dumps(ans.tools), ok,
                                ("tools-only; " if args.tools_only else "") + why]).collect()
            if not ok:
                print(f"FAIL {r.question_id} {r.qtype}: {why}")
        print(f"{passed}/{len(rows)} passed (EVAL_RUN_ID {eval_id})")
        bar = PASS_BAR if len(rows) == 30 else len(rows)
        return 0 if passed >= bar else 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
