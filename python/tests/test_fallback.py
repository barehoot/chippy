"""Template brief tests: the fallback always passes the validator (T-NAR-04, Python side)."""
from __future__ import annotations

import copy

from sr_lib.fallback import template_brief
from sr_lib.validator import validate_brief
from cases import PACK


def test_T_NAR_04_template_passes_validator():
    assert validate_brief(template_brief(PACK), PACK) == []


def test_template_follows_the_L8_wording():
    t = template_brief(PACK)
    s0, s1 = t["shifts"]
    assert s0["title"] == "Crunchy lost share in All India"
    assert s0["why"] == "Largest driver: distribution ({{f5}}). Most of it came from MegaMart ({{f9}})."
    assert s0["so_what"] == "Check distribution at MegaMart."
    assert s0["next_question"] == "Who took the share?"
    assert s1["title"] == "Golden Bake gained share in Store 24"
    assert s1["so_what"] == "Check distribution for Golden Bake in Store 24."


def test_template_without_bridge_or_where_or_shifts():
    pack = copy.deepcopy(PACK)
    pack["shifts"][0]["bridge"], pack["shifts"][0]["where"] = [], []
    t = template_brief(pack)
    assert "no driver split" in t["shifts"][0]["why"] and validate_brief(t, pack) == []
    pack["shifts"], pack["watchlist"] = [], []
    empty = template_brief(pack)
    assert empty["shifts"] == [] and validate_brief(empty, pack) == []


def test_template_with_digit_names_and_long_names():
    pack = copy.deepcopy(PACK)
    pack["shifts"][0]["brand"] = "Bake 7"
    pack["shifts"][0]["market"] = "Hypermarket Chain Number 42 " * 5
    t = template_brief(pack)
    assert len(t["shifts"][0]["title"]) <= 120 and validate_brief(t, pack) == []
