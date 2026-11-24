"""Bridge mirror tests: T-BR-02 (integration), T-BR-03, T-BR-04, T-BR-05."""
from __future__ import annotations

import math
import random

import pytest

from sr_lib.bridge import PeriodInputs, bridge, log_mean, pick_mode
from cases import BRIDGE_TOY


def _inputs(d: dict, **over) -> PeriodInputs:
    return PeriodInputs(**{**d, **over})


CUR, BASE = _inputs(BRIDGE_TOY["cur"]), _inputs(BRIDGE_TOY["base"])


@pytest.mark.parametrize("mode", ["A", "B", "C"])
def test_T_BR_05_toy_case(mode):
    exp = BRIDGE_TOY["expected"][mode]
    r = bridge(CUR, BASE, cap_mode=mode)
    assert r.mode == mode and r.status == "OK"
    assert r.d_share_pts == pytest.approx(exp["d_share_pts"], abs=1e-12)
    for key in ("dist_pts", "velocity_pts", "price_pts", "promo_pts"):
        got, want = getattr(r, key), exp[key]
        if want is None:
            assert got is None, key
        else:
            assert got == pytest.approx(want, abs=1e-12), key
    terms = [t for t in (r.dist_pts, r.velocity_pts, r.price_pts, r.promo_pts) if t is not None]
    assert sum(terms) == pytest.approx(r.d_share_pts, abs=1e-12)
    assert abs(r.residual_pts) < 1e-12


def test_T_BR_05_mode_d_has_no_terms():
    r = bridge(CUR, BASE, cap_mode="D")
    assert (r.mode, r.status) == ("D", "OK")
    assert (r.dist_pts, r.velocity_pts, r.price_pts, r.promo_pts) == (None, None, None, None)
    assert r.residual_pts is None          # no decomposition, so no residual (B03)


def test_T_BR_03_log_mean_edges():
    a = 0.2341
    assert log_mean(a, a) == a
    near = log_mean(a, a * (1 + 1e-15))
    assert math.isfinite(near) and abs(near - a) < 1e-12
    assert log_mean(0.3, 0.2) == pytest.approx(0.1 / math.log(1.5), abs=1e-15)
    assert log_mean(0.2, 0.3) == pytest.approx(log_mean(0.3, 0.2), abs=1e-15)     # symmetric


def test_T_BR_03_new_exit_no_data():
    new = bridge(CUR, _inputs(BRIDGE_TOY["base"], s=0.0, tdp=None, u=None, b=None, bu=None))
    assert new.status == "NEW" and new.dist_pts is None and new.d_share_pts == pytest.approx(30.0)
    exit_ = bridge(_inputs(BRIDGE_TOY["cur"], s=0.0, tdp=None, u=None, b=None, bu=None), BASE)
    assert exit_.status == "EXIT" and exit_.velocity_pts is None and exit_.d_share_pts == pytest.approx(-20.0)
    no_cat = bridge(CUR, _inputs(BRIDGE_TOY["base"], cs=None))
    assert no_cat.status == "NO_DATA" and no_cat.dist_pts is None and math.isnan(no_cat.d_share_pts)


def test_T_BR_04_mode_falls_back():
    assert pick_mode(CUR, BASE, "A") == "A"
    no_base_units = _inputs(BRIDGE_TOY["cur"], bu=None)
    assert pick_mode(no_base_units, BASE, "A") == "B"
    no_units = _inputs(BRIDGE_TOY["cur"], bu=None, u=None)
    assert pick_mode(no_units, BASE, "A") == "C"
    no_tdp = _inputs(BRIDGE_TOY["cur"], bu=None, u=None, tdp=None)
    assert pick_mode(no_tdp, BASE, "A") == "D"


def test_T_BR_04_cap_is_respected():
    for cap in "ABCD":
        assert "ABCD".index(pick_mode(CUR, BASE, cap)) >= "ABCD".index(cap)


def test_T_BR_01_random_rows_add_up_exactly():
    """Property behind T-BR-01: on random positive inputs every OK row's residual is below 1e-6 pts."""
    rng = random.Random(7)
    for _ in range(2000):
        def period():
            cs = rng.uniform(1e5, 1e8)
            return dict(s=cs * rng.uniform(0.001, 0.6), cs=cs, tdp=rng.uniform(1, 500), ctdp=rng.uniform(500, 5000),
                        u=rng.uniform(1, 1e5), cu=rng.uniform(1e5, 1e7), b=rng.uniform(1, 1e6), cb=rng.uniform(1e6, 1e8),
                        bu=rng.uniform(1, 1e5), cbu=rng.uniform(1e5, 1e7))
        r = bridge(PeriodInputs(**period()), PeriodInputs(**period()), rng.choice("ABCD"))
        assert r.status == "OK"
        assert r.residual_pts is None if r.mode == "D" else abs(r.residual_pts) < 1e-6


@pytest.mark.integration
def test_T_BR_02_sql_matches_python():
    """200 random DT_SHARE_COMPARE rows: APP.V_BRIDGE_ALL terms equal bridge() within 1e-9."""
    from snowflake.snowpark import Session

    session = Session.builder.config("connection_name", "sr").create()
    try:
        cap = session.sql("SELECT MAX_BRIDGE_MODE FROM SR_DB.OPS.CAPABILITY ORDER BY CHECKED_AT DESC LIMIT 1").collect()[0][0]
        rows = session.sql(
            """SELECT c.S1, c.CS1, c.TDP1, c.CTDP1, c.U1, c.CU1, c.B1, c.CB1, c.BU1, c.CBU1,
                      c.S0, c.CS0, c.TDP0, c.CTDP0, c.U0, c.CU0, c.B0, c.CB0, c.BU0, c.CBU0,
                      b.MODE, b.STATUS, b.D_SHARE, b.DIST_PTS, b.VELOCITY_PTS, b.PRICE_PTS, b.PROMO_PTS
               FROM SR_DB.CORE.DT_SHARE_COMPARE c
               JOIN SR_DB.APP.V_BRIDGE_ALL b
                 ON b.CMP_CODE = c.CMP_CODE AND b.MARKET_ID = c.MARKET_ID AND b.CATEGORY = c.CATEGORY
                AND b.BRAND = c.BRAND AND EQUAL_NULL(b.MANUFACTURER, c.MANUFACTURER)
               SAMPLE (200 ROWS)""").collect()
    finally:
        session.close()
    assert rows, "no rows to compare"
    f = lambda x: None if x is None else float(x)  # noqa: E731
    for r in rows:
        cur = PeriodInputs(*(f(r[k]) for k in ("S1", "CS1", "TDP1", "CTDP1", "U1", "CU1", "B1", "CB1", "BU1", "CBU1")))
        base = PeriodInputs(*(f(r[k]) for k in ("S0", "CS0", "TDP0", "CTDP0", "U0", "CU0", "B0", "CB0", "BU0", "CBU0")))
        py = bridge(cur, base, cap)
        assert (py.mode, py.status) == (r["MODE"], r["STATUS"])
        for col, val in (("DIST_PTS", py.dist_pts), ("VELOCITY_PTS", py.velocity_pts),
                         ("PRICE_PTS", py.price_pts), ("PROMO_PTS", py.promo_pts)):
            if r[col] is None:
                assert val is None, col
            else:
                assert val == pytest.approx(float(r[col]), abs=1e-9), col
