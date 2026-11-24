"""Brief validator (L8, SR-032). The LLM writes words; every number must be a {{fNN}} placeholder from the fact pack.

validate_brief returns an empty list when the reply passes. Checks, in order: V01 schema and types; V05 shift_ids
equal the pack's order; V06 no empty strings; V07 title <= 120, why <= 400, headline <= 200 characters; V02 every
placeholder exists in pack['facts']; V03 after removing placeholders, no digit token outside allowed_tokens(pack);
V04 a LOSS shift's title has no gain word and a GAIN shift's title has no loss word.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PLACEHOLDER   = re.compile(r"\{\{(f\d+)\}\}")
DIGIT_TOKEN   = re.compile(r"[\w%.,-]*\d[\w%.,-]*")
WORD          = re.compile(r"[a-z]+")
PERIOD_TOKENS = {"L4W", "L12W", "L52W", "P4W", "4W", "12W", "52W"}
CMP_CODES     = {"L4W_VS_YA", "L4W_VS_PP", "L12W_VS_YA", "L52W_VS_YA"}
GAIN_WORDS = {"gain", "gained", "gains", "grew", "grows", "rose", "up", "increased", "won", "added"}
LOSS_WORDS = {"lost", "lose", "loses", "loss", "fell", "down", "declined", "dropped", "slipped", "ceded"}
SHIFT_FIELDS = ("shift_id", "title", "why", "so_what", "next_question")
MAX_LEN = {"title": 120, "why": 400, "headline": 200}


@dataclass(frozen=True)
class Violation:
    code: str    # V01_SCHEMA | V02_UNKNOWN_FACT | V03_RAW_NUMBER | V04_DIRECTION | V05_SHIFT_SET | V06_EMPTY | V07_LENGTH
    path: str    # e.g. "shifts[1].why"
    detail: str


def _clean(token: str) -> str:
    return token.strip(".,-%")


def _names(pack: dict) -> list[str]:
    """Every name the system put in the pack: scope, brands, manufacturers, markets, retailers."""
    names = list((pack.get("scope") or {}).values())
    for s in pack.get("shifts", []):
        names += [s.get("brand"), s.get("manufacturer"), s.get("market")]
        names += [w.get("contributor") for w in s.get("where", [])]
        names += [f.get("brand") for f in s.get("flow", [])]
    for h in pack.get("held_back", []):
        names += [h.get("brand"), h.get("market")]
    for w in pack.get("watchlist", []):
        names += [w.get("brand"), w.get("market")]
    return [n for n in names if isinstance(n, str)]


def allowed_tokens(pack: dict) -> set[str]:
    """Digit-bearing tokens that may appear: period codes plus any token inside brand, market or retailer names."""
    allowed = set(PERIOD_TOKENS) | CMP_CODES
    for name in _names(pack):
        for tok in DIGIT_TOKEN.findall(name):
            allowed.add(tok)
            allowed.add(_clean(tok))
    return allowed


def _texts(llm: dict) -> list[tuple[str, str]]:
    """(path, text) for every free-text field the LLM wrote."""
    out = [("headline", llm["headline"])]
    for i, s in enumerate(llm["shifts"]):
        out += [(f"shifts[{i}].{k}", s[k]) for k in SHIFT_FIELDS if k != "shift_id"]
    out += [(f"watchlist[{i}]", w) for i, w in enumerate(llm["watchlist"])]
    return out


def _schema(llm: object) -> list[Violation]:
    v: list[Violation] = []
    if not isinstance(llm, dict):
        return [Violation("V01_SCHEMA", "", "reply is not a JSON object")]
    if not isinstance(llm.get("headline"), str):
        v.append(Violation("V01_SCHEMA", "headline", "missing or not a string"))
    if not isinstance(llm.get("watchlist"), list) or not all(isinstance(w, str) for w in llm.get("watchlist") or []):
        v.append(Violation("V01_SCHEMA", "watchlist", "missing or not a list of strings"))
    shifts = llm.get("shifts")
    if not isinstance(shifts, list):
        v.append(Violation("V01_SCHEMA", "shifts", "missing or not a list"))
        return v
    for i, s in enumerate(shifts):
        if not isinstance(s, dict):
            v.append(Violation("V01_SCHEMA", f"shifts[{i}]", "not an object"))
            continue
        for k in SHIFT_FIELDS:
            if not isinstance(s.get(k), str):
                v.append(Violation("V01_SCHEMA", f"shifts[{i}].{k}", "missing or not a string"))
    return v


def validate_brief(llm: dict, pack: dict) -> list[Violation]:
    """Empty list = pass. See the module docstring for the checks and their order."""
    v = _schema(llm)
    if v:
        return v

    got = [s["shift_id"] for s in llm["shifts"]]
    want = [s["shift_id"] for s in pack.get("shifts", [])]
    if got != want:
        v.append(Violation("V05_SHIFT_SET", "shifts", f"expected {want}, got {got}"))

    texts = _texts(llm)
    for path, text in texts:
        if not text.strip():
            v.append(Violation("V06_EMPTY", path, "empty text"))

    for path, text in texts:
        field = path.rsplit(".", 1)[-1]
        limit = MAX_LEN.get(field)
        if limit is not None and len(text) > limit:
            v.append(Violation("V07_LENGTH", path, f"{len(text)} characters, limit {limit}"))

    facts = pack.get("facts", {})
    for path, text in texts:
        for fid in PLACEHOLDER.findall(text):
            if fid not in facts:
                v.append(Violation("V02_UNKNOWN_FACT", path, f"{{{{{fid}}}}} is not in the fact pack"))

    allowed = allowed_tokens(pack)
    for path, text in texts:
        for tok in DIGIT_TOKEN.findall(PLACEHOLDER.sub(" ", text)):
            if tok not in allowed and _clean(tok) not in allowed:
                v.append(Violation("V03_RAW_NUMBER", path, f"raw number '{tok}'"))

    direction = {s["shift_id"]: s.get("direction") for s in pack.get("shifts", [])}
    for i, s in enumerate(llm["shifts"]):
        words = set(WORD.findall(s["title"].lower()))
        d = direction.get(s["shift_id"])
        if d == "LOSS" and words & GAIN_WORDS:
            v.append(Violation("V04_DIRECTION", f"shifts[{i}].title", f"gain word in a loss title: {sorted(words & GAIN_WORDS)}"))
        if d == "GAIN" and words & LOSS_WORDS:
            v.append(Violation("V04_DIRECTION", f"shifts[{i}].title", f"loss word in a gain title: {sorted(words & LOSS_WORDS)}"))
    return v
