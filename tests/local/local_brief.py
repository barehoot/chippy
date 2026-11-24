"""Build the run's fact pack from the local pipeline with sr_lib.factpack's own queries, then the template brief."""
from __future__ import annotations

import re

import harness as h
from sr_lib import factpack
from sr_lib.fallback import template_brief
from sr_lib.render import render_html, render_markdown
from sr_lib.validator import validate_brief


def rows(loc: h.Local, sql: str) -> list[dict]:
    df = loc.df(sql.replace("?", f"'{h.RUN_ID}'"))
    out = []
    for rec in df.to_dict("records"):
        out.append({k: (None if v is None or (isinstance(v, float) and v != v) else
                        (list(v) if hasattr(v, "tolist") and not isinstance(v, str) else v)) for k, v in rec.items()})
    return out


def build_pack(loc: h.Local) -> dict:
    markets = dict(loc.con.execute("SELECT MARKET_ID, MARKET_NAME FROM SR_DB.SRC.V_SRC_MARKET").fetchall())
    return factpack.build_pack(
        run_id=h.RUN_ID, brief_id="local-brief", as_of_week=h.SETTINGS["AS_OF_WEEK_END"],
        scope={"category": h.SETTINGS["SCOPE_CATEGORY"], "parent_market": markets[h.SETTINGS["SCOPE_PARENT_MARKET"]],
               "focus_manufacturer": h.SETTINGS["FOCUS_MANUFACTURER"]},
        currency=h.SETTINGS["CURRENCY"],
        shifts=rows(loc, factpack._SHIFTS_SQL), where=rows(loc, factpack._WHERE_SQL), flows=rows(loc, factpack._FLOW_SQL),
        held=rows(loc, factpack._HELD_SQL), watch=rows(loc, factpack._WATCH_SQL))


def brief(loc: h.Local) -> tuple[dict, dict, list, str, str]:
    pack = build_pack(loc)
    llm = template_brief(pack)
    return pack, llm, validate_brief(llm, pack), render_markdown(llm, pack, "INR"), render_html(llm, pack, "INR")


def fact_value(loc: h.Local, src: str) -> float | None:
    """Re-read a fact from the table and column its src names (the T-FP-01 check)."""
    table, rest = src.split("#", 1)
    parts = rest.split(";")
    col = parts[-1].removeprefix("col=")
    where = " AND ".join(f"{k} = '{v}'" for k, v in (p.split("=", 1) for p in parts[:-1]))
    assert re.fullmatch(r"[A-Z_]+\.[A-Z_]+", table) and re.fullmatch(r"[A-Z_0-9*]+", col)
    got = loc.con.execute(f"SELECT CAST({col} AS DOUBLE) FROM SR_DB.{table} WHERE {where} LIMIT 1").fetchone()
    return None if got is None else got[0]
