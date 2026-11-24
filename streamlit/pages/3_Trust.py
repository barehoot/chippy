"""Trust: golden set, reconciliation, bridge exactness, runs, cost, pipeline health and the build log (L11, L14)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from sr_ui import charts, data, format as fmt, nav

st.title("Trust")
run = data.current_run()


def tiles() -> None:
    ev, rc = data.eval_latest(), data.recon_latest()
    resid = data.bridge_residual_max(run.run_id) if run else None
    cost = data.run_cost(1)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Golden set", f"{int(ev.PASSED.sum())}/{len(ev)}" if len(ev) else "–", help="Bar: 27 of 30")
    c2.metric("Reconciliation checks passed", f"{int(rc.PASSED.fillna(False).sum())}/{len(rc)}" if len(rc) else "–")
    c3.metric("Largest bridge residual", "–" if resid is None else f"{resid:.1e} pts", help="Must stay below 1e-6")
    if len(cost):
        r = cost.iloc[0]
        exact = r.COST_BASIS == "EXACT"
        credits = (r.WAREHOUSE_CREDITS if exact else r.CREDITS_EST)
        c4.metric("Last run's credits", "–" if pd.isna(credits) else f"{float(credits):.3f}",
                  help="Exact from account usage" if exact else "Estimate until the cost snapshot runs")
    else:
        c4.metric("Last run's credits", "–")


def health() -> None:
    st.subheader("Pipeline health")
    h = data.health_latest()
    if nav.is_admin() and st.button("Check health now"):
        data.start_task("T_HEALTH")
        st.toast("Health check started; refresh in a minute.")
    if h.empty:
        st.caption("No health check yet.")
        return
    bad = h[h.STATE != "OK"]
    line = f"{len(h) - len(bad)} of {len(h)} objects healthy · checked {pd.to_datetime(h.CHECKED_AT.max()):%d %b %H:%M}"
    if (h.STATE == "FAILED").any():
        st.error(line)
    elif len(bad):
        st.warning(line)
    else:
        st.success(line)
    st.dataframe(h.assign(STATE=[fmt.STATUS_CHIP.get(s, s) for s in h.STATE]), hide_index=True, use_container_width=True)


def golden() -> None:
    st.subheader("Golden set")
    ev = data.eval_latest()
    failed = ev[~ev.PASSED.astype(bool)] if len(ev) else ev
    if ev.empty:
        st.caption("Not run yet: python3 eval/run_eval.py --connection sr")
    elif failed.empty:
        st.success(f"All {len(ev)} questions passed (run {ev.EVAL_RUN_ID.iloc[0][:8]}).")
    else:
        st.dataframe(failed[["QUESTION_ID", "QUESTION", "EXPECTED_TOOL", "ACTUAL_TOOLS", "NOTE"]], hide_index=True,
                     use_container_width=True)


def recon() -> None:
    st.subheader("Reconciliation to NIQ reference numbers")
    rc = data.recon_latest()
    if len(rc):
        st.dataframe(rc, hide_index=True, use_container_width=True)
    else:
        st.caption("No reference numbers loaded.")


def tests() -> None:
    st.subheader("Latest SQL test run")
    t = data.tests_latest()
    if t.empty:
        st.caption("Not run yet: snow sql -f tests/sql/run_all.sql -c sr")
        return
    st.caption(f"{int(t.PASSED.sum())} of {len(t)} tests passed")
    st.dataframe(t[["TEST_ID", "PASSED", "FAILURES", "RAN_AT"]], hide_index=True, use_container_width=True)


def runs() -> None:
    st.subheader("Last 20 runs")
    r = data.runs(20)
    if r.empty:
        st.caption("No runs yet.")
        return
    st.dataframe(r.assign(STATUS=[fmt.RUN_CHIP.get(s, s) for s in r.STATUS])[
        ["RUN_ID", "TRIGGER_TYPE", "AS_OF_WEEK", "STATUS", "BRIDGE_MODE", "N_CANDIDATES", "N_RANKED", "SECONDS",
         "CREDITS_EST", "ERROR_MSG"]], hide_index=True, use_container_width=True)
    pick = st.selectbox("Step timeline of run", list(r.RUN_ID), format_func=lambda i: i[:8])
    steps = data.step_log(pick)
    if len(steps):
        steps = steps.assign(ENDED_AT=steps.ENDED_AT.fillna(pd.Timestamp.now(tz=steps.STARTED_AT.dt.tz)))
        st.altair_chart(charts.step_timeline(steps), use_container_width=True)


def cost() -> None:
    st.subheader("Cost and tokens per brief")
    c = data.run_cost(10)
    if len(c):
        st.dataframe(c, hide_index=True, use_container_width=True)
    else:
        st.caption("No runs yet.")
    d = data.cost_daily()
    if len(d):
        st.dataframe(d, hide_index=True, use_container_width=True)
    else:
        st.caption("Exact daily costs appear after CALL SR_DB.OPS.SP_COST_SNAPSHOT(14) (needs account usage access).")


def built_with() -> None:
    st.subheader("Built with a coding agent")
    log = data.coco_log()
    if log.empty:
        st.caption("Session log not loaded yet: python3 scripts/coco_log.py --event flush")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Tickets with a session record", log.TICKET.nunique())
    c2.metric("Lines added in sessions", int(log.LINES_ADDED.fillna(0).sum()))
    c3.metric("Sessions that wrote tests", int(log.SESSIONS_WITH_TESTS.sum()))
    st.dataframe(log, hide_index=True, use_container_width=True)


nav.guarded("Tiles", tiles)
nav.guarded("Pipeline health", health)
left, right = st.columns(2)
with left:
    nav.guarded("Golden set", golden)
with right:
    nav.guarded("Reconciliation", recon)
nav.guarded("Tests", tests)
nav.guarded("Runs", runs)
nav.guarded("Cost", cost)
nav.guarded("Build log", built_with)
