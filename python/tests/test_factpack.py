"""Fact pack builder tests (SR-030): structure, IDs, sources and aliasing, without Snowflake."""
from __future__ import annotations

from sr_lib.factpack import alias_pack, build_pack
from sr_lib.fallback import template_brief
from sr_lib.validator import validate_brief

SHIFTS = [
    {"SHIFT_ID": "s1", "RANK_NO": 1, "CMP_CODE": "L4W_VS_YA", "MARKET_ID": "M0", "MARKET_NAME": "All India",
     "MANUFACTURER": "Acme Foods", "BRAND": "Crunchy", "ARTEFACT_LABEL": "MARKET_MOVE", "VALUE_AT_STAKE": -1834220.5,
     "D_SHARE_PTS": -0.84, "SH1": 0.2341, "SH0": 0.2425, "MODE": "B", "STATUS": "OK",
     "DIST_PTS": -0.61, "VELOCITY_PTS": -0.30, "PRICE_PTS": 0.07, "PROMO_PTS": None},
]
WHERE = [{"SHIFT_ID": "s1", "RANK_NO": 2, "CONTRIBUTOR": "QuickShop", "TOTAL_PTS": -0.20},
         {"SHIFT_ID": "s1", "RANK_NO": 1, "CONTRIBUTOR": "MegaMart", "TOTAL_PTS": -0.52}]
FLOWS = [{"SHIFT_ID": "s1", "CMP_CODE": "L4W_VS_YA", "MARKET_ID": "M0", "FROM_BRAND": "Crunchy", "TO_BRAND": "Golden Bake",
          "FLOW_PTS": 0.47, "COUNTERPART": "Golden Bake"}]
HELD = [{"SHIFT_ID": "s3", "CMP_CODE": "L4W_VS_YA", "MARKET_ID": "M2", "MARKET_NAME": "QuickShop", "BRAND": "Tea Time",
         "D_SHARE_PTS": -1.7, "RULES": ["R2_FEED"]}]
WATCH = [{"MARKET_ID": "M0", "MARKET_NAME": "All India", "BRAND": "Crunchy", "SIGNAL": "DIST_DROP",
          "LEVER_CHG": -0.081, "PROJECTED_SHARE_PTS": -0.19},
         {"MARKET_ID": "M0", "MARKET_NAME": "All India", "BRAND": "Golden Bake", "SIGNAL": "PRICE_RISE",
          "LEVER_CHG": 0.04, "PROJECTED_SHARE_PTS": None}]


def _pack():
    return build_pack(run_id="r1", brief_id="b1", as_of_week="2026-11-07",
                      scope={"category": "Biscuits", "parent_market": "All India", "focus_manufacturer": "Acme Foods"},
                      currency="INR", shifts=SHIFTS, where=WHERE, flows=FLOWS, held=HELD, watch=WATCH)


def test_every_fact_is_complete_and_every_id_exists():
    p = _pack()
    assert all(set(f) == {"v", "u", "d", "src"} for f in p["facts"].values())
    used = []
    for s in p["shifts"]:
        used += [s["share_now"], s["share_before"], s["delta"], s["value_at_stake"]]
        used += [x["fact"] for x in s["bridge"] + s["where"] + s["flow"]]
    used += [h["delta"] for h in p["held_back"]] + [w["lever_chg"] for w in p["watchlist"]]
    assert all(u in p["facts"] for u in used)
    assert len(p["facts"]) == 4 + 3 + 2 + 1 + 1 + 3       # shift, three terms (no promo), where, flow, held, watch


def test_values_units_and_sources_are_copied_not_computed():
    p = _pack()
    s = p["shifts"][0]
    assert p["facts"][s["delta"]] == {"v": -0.84, "u": "pts", "d": 2, "src": "APP.SHIFT_RANKED#SHIFT_ID=s1;col=D_SHARE*100"}
    assert p["facts"][s["value_at_stake"]]["u"] == "money"
    assert [w["contributor"] for w in s["where"]] == ["MegaMart", "QuickShop"]           # by RANK_NO
    assert p["facts"][s["where"][0]["fact"]]["src"] == "APP.SHIFT_WHERE#SHIFT_ID=s1;METHOD=EXACT_RETAILER;RANK_NO=1;col=TOTAL_PTS"
    assert s["direction"] == "LOSS" and [b["term"] for b in s["bridge"]] == ["distribution", "velocity", "price"]
    assert p["watchlist"][1]["projected"] is None


def test_template_on_a_built_pack_passes():
    p = _pack()
    assert validate_brief(template_brief(p), p) == []


def test_alias_pack_masks_brands_everywhere_shown():
    p = alias_pack(_pack(), {("BRAND", "Crunchy"): "Brand A", ("BRAND", "Golden Bake"): "Brand B",
                             ("MANUFACTURER", "Acme Foods"): "Maker A"})
    assert p["shifts"][0]["brand"] == "Brand A" and p["scope"]["focus_manufacturer"] == "Maker A"
    assert p["shifts"][0]["flow"][0]["brand"] == "Brand B"
    srcs = " ".join(f["src"] for f in p["facts"].values())
    assert "Crunchy" not in srcs and "Golden Bake" not in srcs
