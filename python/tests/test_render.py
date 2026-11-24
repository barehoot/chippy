"""Renderer tests: T-NAR-05 and format_fact."""
from __future__ import annotations

import copy
import html
import re

import pytest

from sr_lib.fallback import template_brief
from sr_lib.render import format_fact, money, render_html, render_markdown
from sr_lib.validator import DIGIT_TOKEN, allowed_tokens
from cases import GOOD_LLM, PACK

SPAN = re.compile(r'<span class="fact" title="([^"]*)">([^<]*)</span>')


def _digits_outside_spans(body: str) -> list[str]:
    text = SPAN.sub(" ", body)
    text = re.sub(r"<[^>]+>", " ", text)          # tags and their attributes
    return DIGIT_TOKEN.findall(html.unescape(text))


@pytest.mark.parametrize("llm", [GOOD_LLM, template_brief(PACK)], ids=["llm", "template"])
def test_T_NAR_05_every_number_is_a_sourced_span(llm):
    body = render_html(llm, PACK, "INR")
    srcs = {html.unescape(m.group(1)) for m in SPAN.finditer(body)}
    known = {f["src"] for f in PACK["facts"].values()} | {PACK["as_of_src"]}
    assert srcs and srcs <= known
    allowed = allowed_tokens(PACK)
    assert [t for t in _digits_outside_spans(body) if t.strip(".,-%") not in allowed and t not in allowed] == []


def test_T_NAR_05_script_tag_is_escaped():
    llm = copy.deepcopy(GOOD_LLM)
    llm["shifts"][0]["why"] = "<script>alert('x')</script> Distribution ({{f5}})."
    body = render_html(llm, PACK, "INR")
    assert "<script>" not in body and "&lt;script&gt;" in body


def test_span_shows_formatted_value_and_source():
    body = render_html(GOOD_LLM, PACK, "INR")
    assert '<span class="fact" title="APP.SHARE_BRIDGE#SHIFT_ID=s1;col=DIST_PTS">-0.61 pts</span>' in body


def test_markdown_fills_every_placeholder():
    md = render_markdown(GOOD_LLM, PACK, "INR")
    assert "{{" not in md and "-0.84 pts" in md and "Held back for data checks" in md and "retailer feed change" in md


@pytest.mark.parametrize("fact,want", [
    ({"v": 0.2341, "u": "share", "d": 1}, "23.4%"),
    ({"v": -0.8412, "u": "pts", "d": 2}, "-0.84 pts"),
    ({"v": 0.5, "u": "pts", "d": 2}, "+0.50 pts"),
    ({"v": -1834220.5, "u": "money", "d": 1}, "-INR 1.8M"),
    ({"v": 2290000.0, "u": "money", "d": 1}, "INR 2.3M"),
    ({"v": 999960.0, "u": "money", "d": 1}, "INR 1.0M"),
    ({"v": 512.4, "u": "money", "d": 1}, "INR 512"),
    ({"v": 4.2e9, "u": "money", "d": 1}, "INR 4.2B"),
    ({"v": 0.031, "u": "index", "d": 1}, "+3.1%"),
    ({"v": -0.081, "u": "index", "d": 1}, "-8.1%"),
    ({"v": None, "u": "pts", "d": 2}, "–"),
])
def test_format_fact(fact, want):
    assert format_fact(fact, "INR") == want


def test_money_never_prints_a_thousand_of_a_unit():
    for x in (999.6, 999_960.0, 999_960_000.0):
        assert "1000" not in money(x, "INR")
