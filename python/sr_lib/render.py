"""Brief renderer (L8, SR-032): fills {{fNN}} placeholders from the fact pack, as Markdown and as HTML.

In HTML every number is <span class="fact" title="<src>">...</span>, so the brief page and the email show each
number's source on hover. All text, from the LLM or from the pack, is escaped before the spans go in.
format_fact matches streamlit/sr_ui/format.py character for character (T-UI-02).
"""
from __future__ import annotations

import html
import re

PLACEHOLDER = re.compile(r"\{\{(f\d+)\}\}")
_UNITS = ((1e9, "B"), (1e6, "M"), (1e3, "K"))

# Comparison and rule wording for the brief, spelled without digits so every digit in BODY_HTML is a fact.
CMP_WORDS = {"L4W_VS_YA": "last four weeks vs year ago", "L4W_VS_PP": "last four weeks vs the previous four",
             "L12W_VS_YA": "last twelve weeks vs year ago", "L52W_VS_YA": "last fifty-two weeks vs year ago"}
LABEL_WORDS = {"MARKET_MOVE": "market move", "MIXED": "mixed signals", "POSSIBLE_DATA_EFFECT": "possible data effect"}
RULE_WORDS = {"R1_COVERAGE": "store coverage change", "R2_FEED": "retailer feed change", "R3_RESTATE": "restated data",
              "R4_RECODE": "item recode", "R5_SPIKE": "one-week spike", "R6_GAP": "missing weeks"}


def money(x: float | None, currency: str, d: int = 1) -> str:
    """-1834220.5 -> '-INR 1.8M'. K, M and B with d decimals; below 1,000 a whole number."""
    if x is None:
        return "–"
    sign, a = ("-" if x < 0 else ""), abs(float(x))
    if f"{a:.0f}" == "1000" and a < 1e3:                       # 999.6 rounds to 1000: show it as 1.0K
        a = 1e3
    for i, (unit, suffix) in enumerate(_UNITS):
        if a >= unit:
            text = f"{a / unit:.{d}f}"
            if float(text) >= 1000 and i > 0:                  # 999.96K would print 1000.0K: step up a unit
                unit, suffix = _UNITS[i - 1]
                text = f"{a / unit:.{d}f}"
            return f"{sign}{currency} {text}{suffix}"
    return f"{sign}{currency} {a:.0f}"


def format_fact(fact: dict, currency: str) -> str:
    """'23.4%' (share), '-0.84 pts' (pts), 'INR 1.8M' (money), '+3.1%' (index)."""
    v, u, d = fact.get("v"), fact.get("u"), int(fact.get("d", 1))
    if v is None:
        return "–"
    v = float(v)
    if u == "share":
        return f"{100 * v:.{d}f}%"
    if u == "pts":
        return f"{v:+.{d}f} pts"
    if u == "money":
        return money(v, currency, d)
    if u == "index":
        return f"{100 * v:+.{d}f}%"
    return f"{v:.{d}f}"


def _fill_text(text: str, pack: dict, currency: str) -> str:
    facts = pack.get("facts", {})
    return PLACEHOLDER.sub(lambda m: format_fact(facts[m.group(1)], currency) if m.group(1) in facts else m.group(0), text)


def _fill_html(text: str, pack: dict, currency: str) -> str:
    """Escape the text first, then put each fact in a span whose title is its source."""
    facts = pack.get("facts", {})

    def span(m: re.Match) -> str:
        f = facts.get(m.group(1))
        if f is None:
            return html.escape(m.group(0))
        return f'<span class="fact" title="{html.escape(f.get("src", ""), quote=True)}">{html.escape(format_fact(f, currency))}</span>'

    return PLACEHOLDER.sub(span, html.escape(text, quote=False))


def _fact_text(fid: str | None, pack: dict, currency: str) -> str:
    return "{{" + fid + "}}" if fid else ""


def _scope_line(pack: dict) -> str:
    sc = pack.get("scope", {})
    return f"{sc.get('category', '')} · {sc.get('parent_market', '')} · focus {sc.get('focus_manufacturer', '')}"


def render_markdown(llm: dict, pack: dict, currency: str) -> str:
    f = lambda t: _fill_text(t, pack, currency)  # noqa: E731
    by_id = {s["shift_id"]: s for s in pack.get("shifts", [])}
    out = [f"# {f(llm['headline'])}", "", f"_Week ending {pack.get('as_of_week', '')} · {_scope_line(pack)}_", ""]
    for s in llm.get("shifts", []):
        p = by_id.get(s["shift_id"], {})
        out += [f"## {f(s['title'])}", "",
                f"_{CMP_WORDS.get(p.get('cmp_code'), p.get('cmp_code', ''))} · {LABEL_WORDS.get(p.get('label'), '')}_", "",
                f(s["why"]), "", f"**So what:** {f(s['so_what'])}", "", f"**Ask next:** {f(s['next_question'])}", ""]
    held = pack.get("held_back", [])
    if held:
        out += ["## Held back for data checks", ""]
        for h in held:
            rules = ", ".join(RULE_WORDS.get(r, r) for r in h.get("rules", []))
            out.append(f"- {h['brand']} in {h['market']}, {CMP_WORDS.get(h.get('cmp_code'), '')}: "
                       f"{f(_fact_text(h.get('delta'), pack, currency))} ({rules})")
        out.append("")
    if llm.get("watchlist"):
        out += ["## Watchlist", ""] + [f"- {f(w)}" for w in llm["watchlist"]] + [""]
    return "\n".join(out)


def render_html(llm: dict, pack: dict, currency: str) -> str:
    h = lambda t: _fill_html(t, pack, currency)  # noqa: E731
    e = lambda t: html.escape(str(t or ""), quote=False)  # noqa: E731
    by_id = {s["shift_id"]: s for s in pack.get("shifts", [])}
    as_of = (f'<span class="fact" title="{html.escape(pack.get("as_of_src", ""), quote=True)}">'
             f'{e(pack.get("as_of_week", ""))}</span>')
    out = ['<div class="sr-brief">', f"<h1>{h(llm['headline'])}</h1>",
           f'<p class="meta">Week ending {as_of} · {e(_scope_line(pack))}</p>']
    for s in llm.get("shifts", []):
        p = by_id.get(s["shift_id"], {})
        out += ['<div class="shift">', f"<h2>{h(s['title'])}</h2>",
                f'<p class="meta">{e(CMP_WORDS.get(p.get("cmp_code"), ""))} · {e(LABEL_WORDS.get(p.get("label"), ""))}</p>',
                f"<p>{h(s['why'])}</p>", f"<p><b>So what:</b> {h(s['so_what'])}</p>",
                f"<p><b>Ask next:</b> {h(s['next_question'])}</p>", "</div>"]
    held = pack.get("held_back", [])
    if held:
        out.append("<h2>Held back for data checks</h2><ul>")
        for x in held:
            rules = ", ".join(RULE_WORDS.get(r, r) for r in x.get("rules", []))
            out.append(f"<li>{e(x['brand'])} in {e(x['market'])}, {e(CMP_WORDS.get(x.get('cmp_code'), ''))}: "
                       f"{h(_fact_text(x.get('delta'), pack, currency))} ({e(rules)})</li>")
        out.append("</ul>")
    if llm.get("watchlist"):
        out.append("<h2>Watchlist</h2><ul>" + "".join(f"<li>{h(w)}</li>" for w in llm["watchlist"]) + "</ul>")
    out.append("</div>")
    return "\n".join(out)


def plain(text: str, pack: dict, currency: str) -> str:
    """A placeholder text as plain text (the HEADLINE column and the email subject)."""
    return _fill_text(text, pack, currency)
