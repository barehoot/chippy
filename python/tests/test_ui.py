"""UI tests: T-UI-01 (bridge_frame) and T-UI-02 (format.py matches render.format_fact)."""
from __future__ import annotations

import random
from datetime import date

import pandas as pd
import pytest

from sr_lib.render import format_fact
from sr_ui import charts
from sr_ui import format as fmt


def test_T_UI_01_mode_a_terms_add_up_to_the_total():
    b = {"DIST_PTS": 4.4966028678679155, "VELOCITY_PTS": 2.5985100456466297, "PRICE_PTS": -0.5542488219741867,
         "PROMO_PTS": 3.4591359084596407, "D_SHARE": 0.1}
    df = charts.bridge_frame(b)
    assert list(df.term) == ["Distribution", "Velocity", "Price", "Promo", "Total change"]
    assert abs(df.pts.iloc[:4].sum() - df.pts.iloc[4]) < 1e-9
    assert list(df.kind) == ["gain", "gain", "loss", "gain", "total"]


def test_T_UI_01_mode_d_gives_the_total_only():
    df = charts.bridge_frame({"DIST_PTS": None, "VELOCITY_PTS": float("nan"), "PRICE_PTS": None, "PROMO_PTS": None,
                              "D_SHARE": -0.0084})
    assert list(df.term) == ["Total change"] and df.pts.iloc[0] == pytest.approx(-0.84)


def test_charts_build_valid_specs():
    charts.bridge_bars({"DIST_PTS": -0.61, "VELOCITY_PTS": -0.3, "PRICE_PTS": 0.05, "PROMO_PTS": None, "D_SHARE": -0.0086}).to_dict()
    where = pd.DataFrame({"METHOD": ["EXACT_RETAILER"] * 2, "CONTRIBUTOR": ["A", "B"], "TOTAL_PTS": [-0.5, 0.1],
                          "PERF_PTS": [-0.4, 0.1], "MIX_PTS": [-0.1, 0.0]})
    charts.retailer_bars(where).to_dict()
    charts.flow_bars(pd.DataFrame({"COUNTERPART": ["X", "Y"], "FLOW_PTS": [0.4, 0.1]})).to_dict()
    weeks = pd.date_range("2025-01-04", periods=60, freq="7D")
    trend = pd.DataFrame({"WEEK_END_DATE": weeks, "VALUE_SHARE_PCT": 20.0, "DIST_SHARE_PCT": 30.0})
    now, base = charts.period_bounds(weeks[-1].date(), "L4W_VS_YA", 4)
    charts.trend_lines(trend, now, base).to_dict()
    steps = pd.DataFrame({"STEP": ["OPEN", "DETECT"], "STATUS": ["OK", "WARN"], "STARTED_AT": weeks[:2],
                          "ENDED_AT": weeks[1:3], "ROWS_WRITTEN": [None, 12], "MESSAGE": [None, "x"]})
    charts.step_timeline(steps).to_dict()


def test_period_bounds_match_the_LLD_periods():
    as_of = date(2026, 11, 7)
    now, base = charts.period_bounds(as_of, "L4W_VS_YA", 4)
    assert now == (date(2026, 10, 17), as_of) and base == (date(2025, 10, 18), date(2025, 11, 8))
    _, pp = charts.period_bounds(as_of, "L4W_VS_PP", 4)
    assert pp == (date(2026, 9, 19), date(2026, 10, 10))


def _samples(n=50):
    rng = random.Random(11)
    edge = [0.0, -0.0004, 0.00049, 0.99999, 999.6, 999_950.0, 999_960.0, -1834220.5, 4.2e9, 1e3, -0.005]
    out = []
    for i in range(n):
        unit = ("share", "pts", "money", "index")[i % 4]
        v = edge[i] if i < len(edge) else {"share": rng.uniform(0, 1), "pts": rng.uniform(-5, 5),
                                           "money": rng.uniform(-5e9, 5e9) / 10 ** rng.randint(0, 6),
                                           "index": rng.uniform(-0.5, 0.5)}[unit]
        out.append({"v": v, "u": unit, "d": {"share": 1, "pts": 2, "money": 1, "index": 1}[unit]})
    return out


@pytest.mark.parametrize("fact", _samples(), ids=lambda f: f"{f['u']}:{f['v']}")
def test_T_UI_02_format_matches_render(fact):
    app = {"share": lambda f: fmt.pct(f["v"], f["d"]), "pts": lambda f: fmt.pts(f["v"], f["d"]),
           "money": lambda f: fmt.money(f["v"], "INR", f["d"]), "index": lambda f: fmt.signed_pct(f["v"], f["d"])}
    assert app[fact["u"]](fact) == format_fact(fact, "INR")


def test_format_helpers():
    assert fmt.pct(0.2341) == "23.4%" and fmt.pts(-0.8412) == "-0.84 pts" and fmt.signed_pct(0.031) == "+3.1%"
    assert fmt.money(-1834220.5, "INR") == "-INR 1.8M" and fmt.pct(None) == "–"
    assert fmt.confidence(0.83) == "High (0.83)" and fmt.confidence(0.5) == "Medium (0.50)"


def test_settings_validation():
    from sr_ui import data
    assert data.validate_setting("TOP_N", 5) == 5 and data.validate_setting("MIN_Z", 2) == 2.0
    for key, bad in (("TOP_N", 11), ("TOP_N", 2.5), ("MIN_SHARE_PTS", 0.01), ("DISPLAY_ALIAS", "yes"),
                     ("AS_OF_WEEK_END", "2026-01-03"), ("MIN_Z", True)):
        with pytest.raises(ValueError):
            data.validate_setting(key, bad)
    assert data.validate_setting("NOTIFY_EMAILS", ["A@x.com"], ["a@x.com"]) == ["A@x.com"]
    with pytest.raises(ValueError, match="allowed recipients"):
        data.validate_setting("NOTIFY_EMAILS", ["b@x.com"], ["a@x.com"])
