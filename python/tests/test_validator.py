"""Validator tests: T-NAR-01, T-NAR-02, T-NAR-03, plus the clean reply and schema cases."""
from __future__ import annotations

import copy

from sr_lib.validator import allowed_tokens, validate_brief
from cases import GOOD_LLM, PACK


def codes(v):
    return {(x.code, x.path) for x in v}


def test_good_reply_passes():
    assert validate_brief(GOOD_LLM, PACK) == []


def test_T_NAR_01_bare_number_in_why():
    llm = copy.deepcopy(GOOD_LLM)
    llm["shifts"][0]["why"] = "Distribution fell 0.61 pts ({{f5}}) at MegaMart."
    assert ("V03_RAW_NUMBER", "shifts[0].why") in codes(validate_brief(llm, PACK))


def test_T_NAR_01_percent_and_money_are_caught():
    llm = copy.deepcopy(GOOD_LLM)
    llm["headline"] = "Crunchy is at 23.4% after losing INR 1.8M."
    found = [x for x in validate_brief(llm, PACK) if x.code == "V03_RAW_NUMBER"]
    assert {x.detail for x in found} == {"raw number '23.4%'", "raw number '1.8M.'"}


def test_period_codes_and_digit_names_are_allowed():
    llm = copy.deepcopy(GOOD_LLM)
    llm["shifts"][1]["why"] = "In Store 24, over L12W and on L4W, {{f15}} came from distribution."
    assert validate_brief(llm, PACK) == []
    assert {"24", "L4W", "L12W_VS_YA"} <= allowed_tokens(PACK)


def test_T_NAR_02_unknown_placeholder_and_shift_order():
    llm = copy.deepcopy(GOOD_LLM)
    llm["shifts"][0]["why"] = "Distribution ({{f99}}) drove it."
    llm["shifts"] = list(reversed(llm["shifts"]))
    got = codes(validate_brief(llm, PACK))
    assert ("V02_UNKNOWN_FACT", "shifts[1].why") in got
    assert ("V05_SHIFT_SET", "shifts") in got


def test_T_NAR_03_gain_word_in_loss_title_and_long_title():
    llm = copy.deepcopy(GOOD_LLM)
    llm["shifts"][0]["title"] = "Crunchy gained ground in All India"
    llm["shifts"][1]["title"] = ("Golden Bake gained share in Store 24 " + "x" * 130)[:130]
    assert len(llm["shifts"][1]["title"]) == 130
    got = codes(validate_brief(llm, PACK))
    assert ("V04_DIRECTION", "shifts[0].title") in got
    assert ("V07_LENGTH", "shifts[1].title") in got


def test_loss_word_in_gain_title():
    llm = copy.deepcopy(GOOD_LLM)
    llm["shifts"][1]["title"] = "Golden Bake share fell in Store 24"
    assert ("V04_DIRECTION", "shifts[1].title") in codes(validate_brief(llm, PACK))


def test_empty_text_and_schema():
    llm = copy.deepcopy(GOOD_LLM)
    llm["shifts"][0]["so_what"] = "   "
    assert ("V06_EMPTY", "shifts[0].so_what") in codes(validate_brief(llm, PACK))
    broken = copy.deepcopy(GOOD_LLM)
    del broken["shifts"][0]["why"]
    assert {x.code for x in validate_brief(broken, PACK)} == {"V01_SCHEMA"}
    assert validate_brief("not json", PACK)[0].code == "V01_SCHEMA"
