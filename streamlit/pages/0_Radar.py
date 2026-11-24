"""Radar (home): this week's shifts, held back, watchlist; the replay panel in the admin app (L11)."""
from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from sr_ui import data, format as fmt, nav

N_STEPS = 14


def replay_panel() -> None:
    busy = data.active_run() is not None or st.session_state.awaiting is not None
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    c1.metric("Data as of", str(data.cfg("AS_OF_WEEK_END")))
    try:
        if c2.button("Load next week", disabled=busy, type="primary"):
            st.session_state.awaiting = {"kind": "REPLAY", "since": data.start_task("T_REPLAY_NEXT"), "t0": time.monotonic()}
            st.rerun()
        if c3.button("Rerun this week", disabled=busy):
            st.session_state.awaiting = {"kind": "RERUN", "since": data.start_task("T_RUN_WEEK_MANUAL"), "t0": time.monotonic()}
            st.rerun()
    except data.Busy:
        st.warning("A run is in progress; wait for it to finish.")
    with c4.popover("Reset to week…", disabled=busy):
        week = st.date_input("Week ending")
        if st.button("Reset"):
            st.toast(data.reset_replay(week))
            data.clear_cache()
            st.rerun()
    if busy or st.session_state.awaiting:
        progress_panel()


@st.fragment(run_every="5s")
def progress_panel() -> None:
    a = st.session_state.awaiting
    run = data.run_started_since(a["since"]) if a else data.active_run()
    if run is None:
        task = data.task_last_run("T_REPLAY_NEXT" if a and a["kind"] == "REPLAY" else "T_RUN_WEEK_MANUAL")
        if task and task.get("STATE") == "FAILED":
            st.error(task.get("ERROR_MESSAGE") or "The task failed")
            st.session_state.awaiting = None
        elif a and time.monotonic() - a["t0"] > 900:
            st.warning("No run started within 15 minutes; check the task history (Trust page).")
            st.session_state.awaiting = None
        else:
            st.info("Loading the new week; the run starts when the stream sees it…")
        if st.button("Refresh", key="refresh_progress"):
            st.rerun()
        return
    steps = data.step_log(run.run_id)
    done = steps.STEP_NO.nunique() if len(steps) else 0
    st.progress(min(1.0, done / N_STEPS), text=f"{fmt.RUN_CHIP.get(run.status, run.status)} · "
                                               f"{steps.STEP.iloc[-1] if done else 'OPEN'}")
    if len(steps):
        st.dataframe(steps[["STEP", "STATUS", "SECONDS", "ROWS_WRITTEN", "MESSAGE"]], hide_index=True)
    if run.status != "RUNNING":
        if run.status == "SKIPPED":
            st.caption(f"Run skipped: {run.error_msg}")
        st.session_state.awaiting = None
        data.clear_cache()
        st.rerun()                                  # whole app


def banners() -> None:
    attempt = data.latest_attempt()
    if attempt is None:
        return
    if attempt.status == "FAILED":
        msg = attempt.error_msg or ""
        if msg.startswith("CAPABILITY") and "NO_DATA" in msg:
            st.error("This week's data has not arrived. The last good brief stays on screen.")
        else:
            st.error(f"The latest run failed at {msg.split(':')[0] or 'a step'}. The last good brief stays on screen.")
        if nav.is_admin():
            st.caption(msg[:2000])
    elif attempt.status == "SKIPPED" and nav.is_admin():
        st.caption(f"Latest run skipped: {attempt.error_msg}")


def tiles(run: data.Run) -> None:
    k = data.kpis(run.run_id)
    cur = data.cfg("CURRENCY") or ""
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Shifts past the gates", int(k.get("N_PASSED", 0)))
    c2.metric("Shifts in the brief", int(k.get("N_SELECTED", 0)))
    c3.metric("Possible data effects", int(k.get("N_DATA_EFFECT", 0)))
    c4.metric("Value at stake in the brief", fmt.money(k.get("VALUE_SELECTED", 0), cur))


def _view(df: pd.DataFrame) -> pd.DataFrame:
    markets, cur = data.market_names(), data.cfg("CURRENCY") or ""
    return pd.DataFrame({
        "SHIFT_ID": df.SHIFT_ID,
        "Rank": df.RANK_NO,
        "Brand": [fmt.name(b) for b in df.BRAND],
        "Market": [markets.get(m, m) for m in df.MARKET_ID],
        "Comparison": [fmt.CMP_TEXT.get(c, c) for c in df.CMP_CODE],
        "Change": [fmt.pts(v) for v in df.D_SHARE_PTS],
        "Value at stake": [fmt.money(v, cur) for v in df.VALUE_AT_STAKE],
        "Confidence": [fmt.confidence(c) for c in df.CONFIDENCE],
        "Data status": [fmt.LABEL_CHIP.get(lbl, lbl) for lbl in df.ARTEFACT_LABEL],
    })


def this_weeks_shifts(run: data.Run) -> None:
    st.subheader("This week's shifts")
    df = data.shifts(run.run_id)
    sel = df[df.SELECTED]
    if sel.empty:
        st.info("No material shift passed the gates and the data checks this week.")
        return
    view = _view(sel)
    event = st.dataframe(view, on_select="rerun", selection_mode="single-row", column_config={"SHIFT_ID": None},
                         hide_index=True, key="radar_shifts", use_container_width=True)
    st.caption("Select a row to open the shift.")
    rows = event.selection.rows if event is not None and hasattr(event, "selection") else []
    if rows:
        st.session_state.shift_id = view.iloc[rows[0]].SHIFT_ID
        st.switch_page("pages/1_Shift_detail.py")


def held_back(run: data.Run) -> None:
    st.subheader("Held back for data checks")
    df = data.held_back(run.run_id)
    if df.empty:
        st.caption("Nothing held back this week.")
        return
    markets = data.market_names()
    st.dataframe(pd.DataFrame({
        "Brand": [fmt.name(b) for b in df.BRAND], "Market": [markets.get(m, m) for m in df.MARKET_ID],
        "Comparison": [fmt.CMP_TEXT.get(c, c) for c in df.CMP_CODE], "Change": [fmt.pts(v) for v in df.D_SHARE_PTS],
        "Rules": [", ".join(fmt.RULE_TEXT.get(r, r) for r in rules) for rules in df.RULES]}),
        hide_index=True, use_container_width=True)


def watchlist(run: data.Run) -> None:
    st.subheader("Watchlist")
    df = data.watchlist(run.run_id)
    if df.empty:
        st.caption("No early warnings this week.")
        return
    markets = data.market_names()
    st.dataframe(pd.DataFrame({
        "Brand": [fmt.name(b) for b in df.BRAND], "Market": [markets.get(m, m) for m in df.MARKET_ID],
        "Signal": ["Distribution drop" if s == "DIST_DROP" else "Price rise" for s in df.SIGNAL],
        "Latest week vs L4W": [fmt.signed_pct(v) for v in df.LEVER_CHG],
        "Projected next L4W share": [fmt.pts(v) for v in df.PROJECTED_SHARE_PTS],
        "Model confirmed": ["yes" if v else "" for v in df.ML_CONFIRMED]}), hide_index=True, use_container_width=True)
    st.caption("Mechanical projection with other levers held; not a forecast.")


def all_candidates(run: data.Run) -> None:
    with st.expander("All candidates"):
        df = data.shifts(run.run_id)
        view = _view(df).drop(columns=["SHIFT_ID"])
        view["In brief"] = ["yes" if s else "" for s in df.SELECTED]
        view["Why not"] = df.SUPPRESS_REASON.fillna("").values
        st.dataframe(view, hide_index=True, use_container_width=True)


st.title("Radar")
if nav.is_admin():
    nav.guarded("Replay panel", replay_panel)
nav.guarded("Status", banners)
current = data.current_run()
if current is None:
    st.info("No brief yet. The first run starts when a data week lands" +
            (" — or press Load next week." if nav.is_admin() else "."))
else:
    st.caption(f"Week ending {current.as_of_week} · run {fmt.RUN_CHIP.get(current.status, current.status)} "
               f"· bridge mode {current.bridge_mode or '–'}")
    nav.guarded("Tiles", lambda: tiles(current))
    nav.guarded("This week's shifts", lambda: this_weeks_shifts(current))
    left, right = st.columns(2)
    with left:
        nav.guarded("Held back", lambda: held_back(current))
    with right:
        nav.guarded("Watchlist", lambda: watchlist(current))
    nav.guarded("All candidates", lambda: all_candidates(current))
