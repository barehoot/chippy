"""Fact pack builder (L8, SR-030), handler of APP.SP_BUILD_FACT_PACK.

Every number the brief may state becomes a fact {"v", "u", "d", "src"} with an ID f1, f2, ... The values are read
from the result tables as SQL computed them (AGENTS.md rule 8); this module only assigns IDs and records where
each number came from, as "<SCHEMA.TABLE>#<KEY>=<value>;...;col=<expression>" (T-FP-01 recomputes from it).
build_pack is pure, so it is unit-tested without Snowflake; build_fact_pack does the reads and the insert.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Iterable

DECIMALS = {"share": 1, "pts": 2, "money": 1, "index": 1}
TERMS = (("distribution", "DIST_PTS"), ("velocity", "VELOCITY_PTS"), ("price", "PRICE_PTS"), ("promo", "PROMO_PTS"))
TOP_WHERE, TOP_FLOW, TOP_HELD, TOP_WATCH = 3, 3, 3, 5


def src(table: str, keys: dict[str, Any], col: str) -> str:
    return f"{table}#" + "".join(f"{k}={v};" for k, v in keys.items()) + f"col={col}"


class _Facts:
    def __init__(self) -> None:
        self.facts: dict[str, dict] = {}

    def add(self, v: Any, unit: str, source: str) -> str | None:
        if v is None:
            return None
        fid = f"f{len(self.facts) + 1}"
        self.facts[fid] = {"v": float(v), "u": unit, "d": DECIMALS[unit], "src": source}
        return fid


def build_pack(*, run_id: str, brief_id: str, as_of_week: str, scope: dict, currency: str,
               shifts: Iterable[dict], where: Iterable[dict], flows: Iterable[dict],
               held: Iterable[dict], watch: Iterable[dict]) -> dict:
    """Assemble the L8 pack from result-table rows (upper-case column names, as Snowpark returns them).

    shifts: selected SHIFT_RANKED rows, in rank order, with SH1, SH0, D_SHARE_PTS, VALUE_AT_STAKE, MARKET_NAME,
            and the SHARE_BRIDGE terms; where: EXACT_RETAILER rows; flows: SHARE_FLOW rows with SHIFT_ID;
            held: POSSIBLE_DATA_EFFECT shifts with RULES; watch: EARLY_WARNING rows with MARKET_NAME.
    """
    f = _Facts()
    where_by, flow_by = {}, {}
    for w in where:
        where_by.setdefault(w["SHIFT_ID"], []).append(w)
    for x in flows:
        flow_by.setdefault(x["SHIFT_ID"], []).append(x)

    out_shifts = []
    for rank, s in enumerate(shifts, start=1):
        sid = s["SHIFT_ID"]
        delta = float(s["D_SHARE_PTS"])
        entry = {
            "shift_id": sid, "rank": rank, "brand": s["BRAND"], "manufacturer": s.get("MANUFACTURER"),
            "market": s.get("MARKET_NAME") or s["MARKET_ID"], "cmp_code": s["CMP_CODE"],
            "label": s["ARTEFACT_LABEL"], "direction": "LOSS" if delta < 0 else "GAIN",
            "bridge_mode": s.get("MODE"), "bridge_status": s.get("STATUS"),
            "share_now": f.add(s.get("SH1"), "share", src("APP.SHIFT_CANDIDATE", {"SHIFT_ID": sid}, "SH1")),
            "share_before": f.add(s.get("SH0"), "share", src("APP.SHIFT_CANDIDATE", {"SHIFT_ID": sid}, "SH0")),
            "delta": f.add(delta, "pts", src("APP.SHIFT_RANKED", {"SHIFT_ID": sid}, "D_SHARE*100")),
            "value_at_stake": f.add(s.get("VALUE_AT_STAKE"), "money", src("APP.SHIFT_RANKED", {"SHIFT_ID": sid}, "VALUE_AT_STAKE")),
            "bridge": [], "where": [], "flow": [],
        }
        for term, col in TERMS:
            fid = f.add(s.get(col), "pts", src("APP.SHARE_BRIDGE", {"SHIFT_ID": sid}, col))
            if fid:
                entry["bridge"].append({"term": term, "fact": fid})
        for w in sorted(where_by.get(sid, []), key=lambda r: r["RANK_NO"])[:TOP_WHERE]:
            keys = {"SHIFT_ID": sid, "METHOD": "EXACT_RETAILER", "RANK_NO": int(w["RANK_NO"])}
            entry["where"].append({"contributor": w["CONTRIBUTOR"],
                                   "fact": f.add(w["TOTAL_PTS"], "pts", src("APP.SHIFT_WHERE", keys, "TOTAL_PTS"))})
        for x in sorted(flow_by.get(sid, []), key=lambda r: -float(r["FLOW_PTS"]))[:TOP_FLOW]:
            keys = {"RUN_ID": run_id, "CMP_CODE": x["CMP_CODE"], "MARKET_ID": x["MARKET_ID"],
                    "FROM_BRAND": x["FROM_BRAND"], "TO_BRAND": x["TO_BRAND"]}
            entry["flow"].append({"brand": x["COUNTERPART"],
                                  "fact": f.add(x["FLOW_PTS"], "pts", src("APP.SHARE_FLOW", keys, "FLOW_PTS"))})
        out_shifts.append(entry)

    out_held = []
    for h in list(held)[:TOP_HELD]:
        sid = h["SHIFT_ID"]
        out_held.append({"shift_id": sid, "brand": h["BRAND"], "market": h.get("MARKET_NAME") or h["MARKET_ID"],
                         "cmp_code": h["CMP_CODE"],
                         "delta": f.add(h["D_SHARE_PTS"], "pts", src("APP.SHIFT_RANKED", {"SHIFT_ID": sid}, "D_SHARE*100")),
                         "rules": sorted(h.get("RULES") or [])})

    out_watch = []
    for w in list(watch)[:TOP_WATCH]:
        keys = {"RUN_ID": run_id, "MARKET_ID": w["MARKET_ID"], "BRAND": w["BRAND"], "SIGNAL": w["SIGNAL"]}
        out_watch.append({"brand": w["BRAND"], "market": w.get("MARKET_NAME") or w["MARKET_ID"], "signal": w["SIGNAL"],
                          "lever_chg": f.add(w["LEVER_CHG"], "index", src("APP.EARLY_WARNING", keys, "LEVER_CHG")),
                          "projected": f.add(w.get("PROJECTED_SHARE_PTS"), "pts",
                                             src("APP.EARLY_WARNING", keys, "PROJECTED_SHARE_PTS"))})

    return {"brief_id": brief_id, "run_id": run_id, "as_of_week": as_of_week,
            "as_of_src": src("OPS.RUN_LOG", {"RUN_ID": run_id}, "AS_OF_WEEK"),
            "scope": scope, "currency": currency, "facts": f.facts,
            "shifts": out_shifts, "held_back": out_held, "watchlist": out_watch}


def alias_pack(pack: dict, aliases: dict[tuple[str, str], str]) -> dict:
    """A copy of the pack with brand and manufacturer names replaced by APP.V_ALIAS aliases (DISPLAY_ALIAS)."""
    p = json.loads(json.dumps(pack))
    b = lambda n: aliases.get(("BRAND", n), n)          # noqa: E731
    m = lambda n: aliases.get(("MANUFACTURER", n), n)   # noqa: E731
    p["scope"]["focus_manufacturer"] = m(p["scope"].get("focus_manufacturer"))
    for s in p["shifts"]:
        s["brand"], s["manufacturer"] = b(s["brand"]), m(s.get("manufacturer"))
        for x in s["flow"]:
            x["brand"] = b(x["brand"])
    for h in p["held_back"]:
        h["brand"] = b(h["brand"])
    for w in p["watchlist"]:
        w["brand"] = b(w["brand"])
    for fact in p["facts"].values():                    # sources name brands too; mask them in the shown copy
        parts = fact["src"].split(";")
        for i, part in enumerate(parts):
            key, _, val = part.partition("=")
            if key.endswith("BRAND"):
                parts[i] = f"{key}={b(val)}"
        fact["src"] = ";".join(parts)
    return p


# ---- Snowflake handler -------------------------------------------------------------------------------------

_SHIFTS_SQL = """
SELECT r.SHIFT_ID, r.RANK_NO, r.CMP_CODE, r.MARKET_ID, COALESCE(m.MARKET_NAME, r.MARKET_ID) AS MARKET_NAME,
       r.CATEGORY, r.MANUFACTURER, r.BRAND, r.ARTEFACT_LABEL, r.VALUE_AT_STAKE, 100 * r.D_SHARE AS D_SHARE_PTS,
       c.SH1, c.SH0, b.MODE, b.STATUS, b.DIST_PTS, b.VELOCITY_PTS, b.PRICE_PTS, b.PROMO_PTS
FROM SR_DB.APP.SHIFT_RANKED r
JOIN SR_DB.APP.SHIFT_CANDIDATE c ON c.RUN_ID = r.RUN_ID AND c.SHIFT_ID = r.SHIFT_ID
LEFT JOIN SR_DB.APP.SHARE_BRIDGE b ON b.RUN_ID = r.RUN_ID AND b.SHIFT_ID = r.SHIFT_ID
LEFT JOIN SR_DB.SRC.V_SRC_MARKET m ON m.MARKET_ID = r.MARKET_ID
WHERE r.RUN_ID = ? AND r.SELECTED
ORDER BY r.RANK_NO"""

_WHERE_SQL = """
SELECT SHIFT_ID, RANK_NO, CONTRIBUTOR, TOTAL_PTS FROM SR_DB.APP.SHIFT_WHERE
WHERE RUN_ID = ? AND METHOD = 'EXACT_RETAILER' ORDER BY SHIFT_ID, RANK_NO"""

_FLOW_SQL = """
SELECT r.SHIFT_ID, f.CMP_CODE, f.MARKET_ID, f.FROM_BRAND, f.TO_BRAND, f.FLOW_PTS,
       IFF(r.D_SHARE < 0, f.TO_BRAND, f.FROM_BRAND) AS COUNTERPART
FROM SR_DB.APP.SHIFT_RANKED r
JOIN SR_DB.APP.SHARE_FLOW f
  ON f.RUN_ID = r.RUN_ID AND f.CMP_CODE = r.CMP_CODE AND f.MARKET_ID = r.MARKET_ID AND f.CATEGORY = r.CATEGORY
 AND IFF(r.D_SHARE < 0, f.FROM_BRAND, f.TO_BRAND) = r.BRAND
WHERE r.RUN_ID = ? AND r.SELECTED"""

_HELD_SQL = """
SELECT r.SHIFT_ID, r.CMP_CODE, r.MARKET_ID, ANY_VALUE(COALESCE(m.MARKET_NAME, r.MARKET_ID)) AS MARKET_NAME, r.BRAND,
       ANY_VALUE(100 * r.D_SHARE) AS D_SHARE_PTS, ANY_VALUE(r.SCORE) AS SCORE,
       ARRAY_AGG(DISTINCT a.RULE_ID) AS RULES
FROM SR_DB.APP.SHIFT_RANKED r
LEFT JOIN SR_DB.SRC.V_SRC_MARKET m ON m.MARKET_ID = r.MARKET_ID
LEFT JOIN SR_DB.APP.ARTEFACT_CHECK a
  ON a.RUN_ID = r.RUN_ID AND a.CMP_CODE = r.CMP_CODE AND a.MARKET_ID = r.MARKET_ID AND a.CATEGORY = r.CATEGORY
 AND (a.BRAND IS NULL OR a.BRAND = r.BRAND) AND a.SEVERITY = 'HIGH'
WHERE r.RUN_ID = ? AND r.ARTEFACT_LABEL = 'POSSIBLE_DATA_EFFECT'
GROUP BY r.SHIFT_ID, r.CMP_CODE, r.MARKET_ID, r.BRAND
QUALIFY ROW_NUMBER() OVER (PARTITION BY r.MARKET_ID, r.BRAND ORDER BY ANY_VALUE(r.SCORE) DESC) = 1
ORDER BY SCORE DESC LIMIT 3"""

_WATCH_SQL = """
SELECT e.MARKET_ID, COALESCE(m.MARKET_NAME, e.MARKET_ID) AS MARKET_NAME, e.BRAND, e.SIGNAL, e.LEVER_CHG,
       e.PROJECTED_SHARE_PTS
FROM SR_DB.APP.EARLY_WARNING e
LEFT JOIN SR_DB.SRC.V_SRC_MARKET m ON m.MARKET_ID = e.MARKET_ID
WHERE e.RUN_ID = ?
ORDER BY ABS(COALESCE(e.PROJECTED_SHARE_PTS, 0)) DESC, ABS(e.LEVER_CHG) DESC"""

_CONTEXT_SQL = """
SELECT SR_DB.OPS.CFG('AS_OF_WEEK_END')::VARCHAR AS AS_OF, SR_DB.OPS.CFG('SCOPE_CATEGORY')::VARCHAR AS CATEGORY,
       SR_DB.OPS.CFG('SCOPE_PARENT_MARKET')::VARCHAR AS PARENT_ID, SR_DB.OPS.CFG('FOCUS_MANUFACTURER')::VARCHAR AS FOCUS,
       SR_DB.OPS.CFG('CURRENCY')::VARCHAR AS CURRENCY,
       (SELECT MAX(MARKET_NAME) FROM SR_DB.SRC.V_SRC_MARKET WHERE MARKET_ID = SR_DB.OPS.CFG('SCOPE_PARENT_MARKET')::VARCHAR) AS PARENT_NAME"""


def _rows(session, sql: str, params: list) -> list[dict]:
    out = []
    for r in session.sql(sql, params=params).collect():
        d = r.as_dict()
        for k, v in d.items():
            if isinstance(v, str) and k == "RULES":
                d[k] = json.loads(v)
        out.append(d)
    return out


def build_fact_pack(session, run_id: str) -> str:
    """APP.SP_BUILD_FACT_PACK(P_RUN_ID): writes APP.FACT_PACK for the run and returns the new BRIEF_ID."""
    session.sql(f"ALTER SESSION SET QUERY_TAG = 'SR|run={run_id}|step=FACT_PACK'").collect()
    ctx = session.sql(_CONTEXT_SQL).collect()[0].as_dict()
    brief_id = str(uuid.uuid4())
    scope = {"category": ctx["CATEGORY"], "parent_market": ctx["PARENT_NAME"] or ctx["PARENT_ID"],
             "focus_manufacturer": ctx["FOCUS"]}
    pack = build_pack(run_id=run_id, brief_id=brief_id, as_of_week=ctx["AS_OF"], scope=scope,
                      currency=ctx["CURRENCY"] or "", shifts=_rows(session, _SHIFTS_SQL, [run_id]),
                      where=_rows(session, _WHERE_SQL, [run_id]), flows=_rows(session, _FLOW_SQL, [run_id]),
                      held=_rows(session, _HELD_SQL, [run_id]), watch=_rows(session, _WATCH_SQL, [run_id]))
    scope_key = f"{ctx['CATEGORY']}|{ctx['PARENT_ID']}|{ctx['FOCUS']}"
    session.sql("DELETE FROM SR_DB.APP.FACT_PACK WHERE RUN_ID = ?", params=[run_id]).collect()
    session.sql("INSERT INTO SR_DB.APP.FACT_PACK (RUN_ID, BRIEF_ID, SCOPE_KEY, PACK, N_FACTS) "
                "SELECT ?, ?, ?, PARSE_JSON(?), ?",
                params=[run_id, brief_id, scope_key, json.dumps(pack), len(pack["facts"])]).collect()
    return brief_id
