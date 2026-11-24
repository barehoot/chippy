"""The repository's SQL, run on DuckDB against synthetic data (tests/local/harness.py). Marker: local_sql.

  pytest -q tests/local            (about 10 seconds)

Covers what can run outside Snowflake: the share grid, detector gates, the exact bridge on every row (T-BR-02 in
full, not a sample), artefact rules, ranking, the retailer split, flow and early warning, through the project's
own T-* SQL test files; then the fact pack built with sr_lib.factpack's own queries, the template brief, the
validator and the HTML render. Scripting, ML classes, tasks, the agent and grants are tested on the account.
"""
from __future__ import annotations

import html
import math
import re

import pytest

import harness as h
import local_brief
from sr_lib.bridge import PeriodInputs, bridge

pytestmark = pytest.mark.local_sql


@pytest.fixture(scope="module")
def loc():
    return h.build()


def test_every_statement_ran(loc):
    assert [r for r in loc.log if r[1] != "OK"] == []
    assert len(loc.log) >= 45


@pytest.mark.parametrize("test_id", h.SQL_TESTS)
def test_project_sql_test_passes(loc, test_id):
    passed, failures, detail = h.run_sql_test(loc, test_id)
    assert passed, f"{test_id}: {failures} failures {detail}"


def test_T_BR_02_sql_bridge_equals_python_mirror_on_every_row(loc):
    cap = loc.con.execute("SELECT MAX_BRIDGE_MODE FROM SR_DB.OPS.CAPABILITY ORDER BY CHECKED_AT DESC LIMIT 1").fetchone()[0]
    rows = loc.con.execute("""
        SELECT c.S1, c.CS1, c.TDP1, c.CTDP1, c.U1, c.CU1, c.B1, c.CB1, c.BU1, c.CBU1,
               c.S0, c.CS0, c.TDP0, c.CTDP0, c.U0, c.CU0, c.B0, c.CB0, c.BU0, c.CBU0,
               b.MODE, b.STATUS, b.DIST_PTS, b.VELOCITY_PTS, b.PRICE_PTS, b.PROMO_PTS, b.RESIDUAL_PTS
        FROM SR_DB.CORE.DT_SHARE_COMPARE c
        JOIN SR_DB.APP.V_BRIDGE_ALL b ON b.CMP_CODE = c.CMP_CODE AND b.MARKET_ID = c.MARKET_ID
         AND b.CATEGORY = c.CATEGORY AND b.BRAND = c.BRAND""").fetchall()
    assert len(rows) == 4 * 5 * 8            # every comparison x market x brand
    f = lambda x: None if x is None else float(x)  # noqa: E731
    statuses = set()
    for r in rows:
        py = bridge(PeriodInputs(*map(f, r[0:10])), PeriodInputs(*map(f, r[10:20])), cap)
        statuses.add(py.status)
        assert (py.mode, py.status) == (r[20], r[21])
        for got, want in zip((py.dist_pts, py.velocity_pts, py.price_pts, py.promo_pts), r[22:26]):
            assert (got is None) == (want is None) and (got is None or math.isclose(got, want, abs_tol=1e-9))
        assert (py.residual_pts is None) == (r[26] is None)
    assert {"OK", "NO_DATA"} <= statuses        # FreshCo's missing weeks exercise the NO_DATA path


def test_planted_events_are_found(loc):
    q = lambda s: loc.con.execute(s).fetchall()  # noqa: E731
    rules = set(q("SELECT RULE_ID, MARKET_ID FROM SR_DB.APP.ARTEFACT_CHECK"))
    assert {("R2_FEED", "M0"), ("R6_GAP", "M4"), ("R5_SPIKE", "M3")} <= rules        # E3, E5
    sel = q("SELECT BRAND, MARKET_ID, D_SHARE FROM SR_DB.APP.SHIFT_RANKED WHERE SELECTED ORDER BY RANK_NO")
    assert sel[0][:2] == ("Crunchy", "M1") and sel[0][2] < 0                          # E1 leads the brief
    assert ("Golden Bake", "M2") in {(b, m) for b, m, _ in sel}                        # E2
    lead = q("""SELECT b.DIST_PTS, b.VELOCITY_PTS, b.PRICE_PTS, b.PROMO_PTS FROM SR_DB.APP.SHARE_BRIDGE b
                JOIN SR_DB.APP.SHIFT_RANKED r ON r.SHIFT_ID = b.SHIFT_ID WHERE r.RANK_NO = 1""")[0]
    assert abs(lead[0]) == max(abs(x) for x in lead)                                    # distribution-led
    held = q("SELECT DISTINCT MARKET_ID FROM SR_DB.APP.SHIFT_RANKED WHERE ARTEFACT_LABEL = 'POSSIBLE_DATA_EFFECT'")
    assert held == [("M0",)]                                    # the parent is held back while FreshCo's feed is out
    assert not q("SELECT 1 FROM SR_DB.APP.SHIFT_RANKED WHERE SELECTED AND ARTEFACT_LABEL = 'POSSIBLE_DATA_EFFECT'")
    ew = q("SELECT BRAND, MARKET_ID FROM SR_DB.APP.EARLY_WARNING WHERE SIGNAL = 'DIST_DROP'")
    assert ("Choco Bites", "M1") in ew                                                  # E6


def test_fact_pack_and_template_brief_end_to_end(loc):
    pack, llm, violations, md, body = local_brief.brief(loc)
    assert violations == []
    assert len(pack["shifts"]) == 5 and pack["held_back"] and pack["watchlist"]
    for fid, fact in pack["facts"].items():                       # T-FP-01: every fact re-reads from its source
        got = local_brief.fact_value(loc, fact["src"])
        assert got is not None and math.isclose(got, fact["v"], rel_tol=1e-9, abs_tol=1e-9), (fid, fact)
    assert "{{" not in md and "Crunchy lost share in MegaMart" in md
    spans = re.findall(r'<span class="fact" title="([^"]*)">', body)
    assert len(spans) >= len({m for m in re.findall(r"\{\{(f\d+)\}\}", str(llm))}) and "&lt;" not in html.unescape(body)
