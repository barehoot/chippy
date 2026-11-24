"""Shift detail: bridge, trend, where, who took it, data checks and what-if for one shift (L11)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from sr_ui import charts, data, format as fmt, nav

st.title("Shift detail")
run = data.current_run()
if run is None:
    st.info("No run yet.")
    st.stop()

options = data.shifts(run.run_id)
if options.empty:
    st.info("No shifts passed the gates in the current run.")
    st.stop()
markets = data.market_names()
ids = list(options.SHIFT_ID)
default = ids.index(st.session_state.shift_id) if st.session_state.shift_id in ids else 0
by_id = {r.SHIFT_ID: r._asdict() for r in options.itertuples(index=False)}
sid = st.selectbox("Shift", ids, index=default, format_func=lambda i: fmt.headline(by_id[i], markets))
st.session_state.shift_id = sid
s = data.shift(sid)
direction = "LOSS" if float(s["D_SHARE"]) < 0 else "GAIN"
cur = data.cfg("CURRENCY") or ""

st.header(fmt.headline(s, markets))
st.markdown(f'<span class="sr-chip">{fmt.LABEL_CHIP.get(s["ARTEFACT_LABEL"], s["ARTEFACT_LABEL"])}</span>'
            f'<span class="sr-chip">Confidence {fmt.confidence(s["CONFIDENCE"])}</span>'
            f'<span class="sr-chip">Share {fmt.pct(s["SH0"])} → {fmt.pct(s["SH1"])}</span>'
            f'<span class="sr-chip">Value at stake {fmt.money(s["VALUE_AT_STAKE"], cur)}</span>',
            unsafe_allow_html=True)
if s.get("SUPPRESS_REASON"):
    st.caption(s["SUPPRESS_REASON"])


def bridge_section() -> None:
    st.subheader("What moved share")
    b = data.bridge(sid)
    if not b:
        st.info("No bridge for this shift.")
        return
    if b["STATUS"] == "NEW":
        st.markdown('<span class="sr-chip">New listing</span> No sales in the base period, so there is nothing to split.',
                    unsafe_allow_html=True)
    elif b["STATUS"] == "EXIT":
        st.markdown('<span class="sr-chip">Delisted</span> No sales in the current period.', unsafe_allow_html=True)
    elif b["STATUS"] == "NO_DATA":
        st.warning("A category total is missing in one period; the change cannot be split.")
    st.altair_chart(charts.bridge_bars(b), use_container_width=True)
    if b["MODE"] == "D" or b["STATUS"] != "OK":
        st.caption(b.get("NOTE") or "No distribution data: share change only")
    else:
        resid = b.get("RESIDUAL_PTS")
        st.caption(f"Mode {b['MODE']}: the terms add up to {fmt.pts(100 * float(b['D_SHARE']))} "
                   f"(residual {0.0 if resid is None else float(resid):.1e} pts)."
                   + (" No price or promo split in mode C." if b["MODE"] == "C" else "")
                   + (" No promo split in mode B." if b["MODE"] == "B" else ""))


def trend_section() -> None:
    st.subheader("Trend")
    t = data.trend(s["MARKET_ID"], s["CATEGORY"], s["BRAND"])
    if t.empty:
        st.caption("No weekly history.")
        return
    as_of = pd.to_datetime(t.WEEK_END_DATE.max()).date()
    now, base = charts.period_bounds(as_of, s["CMP_CODE"], fmt.CUR_WEEKS.get(s["CMP_CODE"], 4))
    t = t.assign(WEEK_END_DATE=pd.to_datetime(t.WEEK_END_DATE))
    st.altair_chart(charts.trend_lines(t, now, base), use_container_width=True)
    st.caption("Shaded: the compared periods.")


def where_section() -> None:
    st.subheader("Where it happened")
    w = data.where(sid)
    exact = w[w.METHOD == "EXACT_RETAILER"]
    if exact.empty:
        st.caption("The exact retailer split is computed for selected shifts in the parent market.")
    else:
        st.altair_chart(charts.retailer_bars(exact), use_container_width=True)
        st.dataframe(pd.DataFrame({"Retailer": exact.CONTRIBUTOR, "Performance": [fmt.pts(v) for v in exact.PERF_PTS],
                                   "Mix": [fmt.pts(v) for v in exact.MIX_PTS], "Total": [fmt.pts(v) for v in exact.TOTAL_PTS]}),
                     hide_index=True, use_container_width=True)
    ti = w[w.METHOD == "TOP_INSIGHTS"]
    if not ti.empty:
        st.markdown("**Drivers of brand sales change** (TOP_INSIGHTS: explains sales, not share)")
        st.dataframe(pd.DataFrame({"Segment": ti.CONTRIBUTOR, "Contribution": [fmt.money(v, cur) for v in ti.CONTRIBUTION],
                                   "Share of change": [fmt.signed_pct(v) for v in ti.RELATIVE_CONTRIBUTION],
                                   "Growth": [fmt.signed_pct(v) for v in ti.GROWTH_RATE]}),
                     hide_index=True, use_container_width=True)


def flow_section() -> None:
    st.subheader("Who took it" if direction == "LOSS" else "Where it came from")
    f = data.flow(s["RUN_ID"], s["CMP_CODE"], s["MARKET_ID"], s["CATEGORY"], s["BRAND"], direction)
    if f.empty:
        st.caption("No flow for this shift.")
        return
    f = f.assign(COUNTERPART=[fmt.name(b) for b in f.COUNTERPART])
    st.altair_chart(charts.flow_bars(f), use_container_width=True)
    st.caption("Proportional allocation of share points: an accounting split, not shopper switching.")


def checks_section() -> None:
    st.subheader("Data checks")
    a = data.artefacts(s["RUN_ID"], s["CMP_CODE"], s["MARKET_ID"], s["CATEGORY"], s["BRAND"])
    if a.empty:
        st.success("No data rule fired for this market and comparison.")
        return
    for r in a.itertuples(index=False):
        with st.expander(f"{'⚠' if r.SEVERITY == 'HIGH' else '◐'} {fmt.RULE_TEXT.get(r.RULE_ID, r.RULE_ID)} ({r.SEVERITY})"):
            st.json(r.EVIDENCE)


def what_if_section() -> None:
    st.subheader("What if")
    b = data.bridge(sid) or {}
    has_dist = b.get("DS1") is not None and not pd.isna(b.get("DS1")) and b.get("STATUS") == "OK"
    levers = ["DISTRIBUTION"] + (["PROMO"] if b.get("MODE") == "A" else [])
    with st.form("what_if"):
        c1, c2 = st.columns(2)
        lever = c1.selectbox("Lever", levers, disabled=not has_dist)
        how = c2.selectbox("Target", ["Restore the base-period level", "Change by a percentage"], disabled=not has_dist)
        pct = st.number_input("Percentage change", value=10.0, step=5.0, disabled=not has_dist)
        go = st.form_submit_button("Show the mechanical effect", disabled=not has_dist)
    if not has_dist:
        st.caption("Needs a distribution share (bridge mode A to C).")
    if go:
        target = "BASE" if how.startswith("Restore") else f"{pct:+g}%"
        r = data.what_if(sid, lever, target)
        if r.get("error"):
            st.warning(r.get("detail", r["error"]))
        else:
            st.metric("Share if", fmt.pct(r["share_if_pts"] / 100, 2), delta=fmt.pts(r["delta_pts"]))
            st.caption(r["assumption"])


def ask_why() -> None:
    if data.cfg("DISPLAY_ALIAS") is True:
        return
    st.subheader("Ask why in CoWork")
    st.code(f"Why did {s['BRAND']} {'lose' if direction == 'LOSS' else 'gain'} share in "
            f"{markets.get(s['MARKET_ID'], s['MARKET_ID'])}, {fmt.CMP_TEXT.get(s['CMP_CODE'], s['CMP_CODE'])}?",
            language=None)


left, right = st.columns(2)
with left:
    nav.guarded("Bridge", bridge_section)
with right:
    nav.guarded("Trend", trend_section)
left, right = st.columns(2)
with left:
    nav.guarded("Where it happened", where_section)
with right:
    nav.guarded("Who took it", flow_section)
nav.guarded("Data checks", checks_section)
nav.guarded("What if", what_if_section)
nav.guarded("Ask why", ask_why)
