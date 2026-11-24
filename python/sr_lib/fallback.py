"""Template brief (L8, SR-032): the same shape as the LLM schema, built deterministically from the fact pack.

Used when both LLM attempts fail (E10, E11), so a brief is always published. It only uses placeholders for
numbers and must pass validate_brief (tested). Per shift:
  title         "<brand> <gained|lost> share in <market>"
  why           "Largest driver: <term> ({{fX}}). Most of it came from <retailer> ({{fY}})."
                (with no retailer split: "<brand> took the most ({{fZ}})." from the share flow)
  so_what       "Check <term> at <retailer>."
  next_question "Who took the share?" (a loss) or "Who lost the share <brand> gained?" (a gain)
"""
from __future__ import annotations

from .render import CMP_WORDS


def _largest_term(shift: dict, facts: dict) -> dict | None:
    terms = [t for t in shift.get("bridge", []) if t.get("fact") in facts and facts[t["fact"]].get("v") is not None]
    return max(terms, key=lambda t: abs(float(facts[t["fact"]]["v"])), default=None)


def _title(brand: str, verb: str, market: str) -> str:
    title = f"{brand} {verb} share in {market}"
    return title if len(title) <= 120 else f"{brand} {verb} share"[:120]


def _shift(shift: dict, facts: dict) -> dict:
    loss = shift.get("direction") == "LOSS"
    brand, market = shift["brand"], shift["market"]
    term = _largest_term(shift, facts)
    where = (shift.get("where") or [None])[0]
    if term:
        why = f"Largest driver: {term['term']} ({{{{{term['fact']}}}}})."
    else:
        why = f"Share moved {{{{{shift['delta']}}}}}; no driver split is available for this shift."
    flow = (shift.get("flow") or [None])[0]
    if where:
        why += f" Most of it came from {where['contributor']} ({{{{{where['fact']}}}}})."
    elif flow:
        why += (f" {flow['brand']} took the most ({{{{{flow['fact']}}}}})." if loss
                else f" It came mostly from {flow['brand']} ({{{{{flow['fact']}}}}}).")
    if term and where:
        so_what = f"Check {term['term']} at {where['contributor']}."
    elif term:
        so_what = f"Check {term['term']} for {brand} in {market}."
    else:
        so_what = f"Check listings and data status for {brand} in {market}."
    question = "Who took the share?" if loss else f"Who lost the share {brand} gained?"
    return {"shift_id": shift["shift_id"], "title": _title(brand, "lost" if loss else "gained", market),
            "why": why[:400], "so_what": so_what, "next_question": question}


def _watch(item: dict) -> str:
    who = f"{item['brand']} in {item['market']}"
    if item.get("signal") == "DIST_DROP":
        line = f"{who}: latest-week distribution share {{{{{item['lever_chg']}}}}} against L4W"
        if item.get("projected"):
            line += f"; about {{{{{item['projected']}}}}} on next L4W share if it persists"
        return line + "."
    return f"{who}: latest-week price index {{{{{item['lever_chg']}}}}} against L4W."


def template_brief(pack: dict) -> dict:
    """Same shape as the structured output schema, built deterministically."""
    facts = pack.get("facts", {})
    shifts = pack.get("shifts", [])
    scope = pack.get("scope", {})
    focus, parent = scope.get("focus_manufacturer", ""), scope.get("parent_market", "")
    if shifts:
        top = shifts[0]
        cmp = CMP_WORDS.get(top.get("cmp_code"), "")
        headline = f"Top shift for {focus}: {top['brand']} in {top['market']}, {{{{{top['delta']}}}}} ({cmp})."
        if len(headline) > 200:
            headline = f"Top shift: {top['brand']}, {{{{{top['delta']}}}}}."
    else:
        headline = f"No material share shifts for {focus} in {parent} this week."[:200]
    return {"headline": headline,
            "shifts": [_shift(s, facts) for s in shifts],
            "watchlist": [_watch(w) for w in pack.get("watchlist", [])]}
