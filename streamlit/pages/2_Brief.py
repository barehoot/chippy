"""Brief: the published brief, with each number's source on hover, and how it was written (L11)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from sr_ui import data, format as fmt, nav

st.title("Brief")
lst = data.briefs()
if lst.empty:
    st.info("No brief has been published yet.")
    st.stop()
ids = list(lst.BRIEF_ID)
default = ids.index(st.session_state.brief_id) if st.session_state.brief_id in ids else 0
labels = {r.BRIEF_ID: f"Week ending {r.AS_OF_WEEK} · {r.HEADLINE}" for r in lst.itertuples(index=False)}
bid = st.selectbox("Brief", ids, index=default, format_func=lambda i: labels[i][:140])
st.session_state.brief_id = bid
b = data.brief(bid)


def chips() -> None:
    notes = data.brief_notifications(bid)
    emailed = (notes[(notes.CHANNEL == "EMAIL") & (notes.STATUS == "SENT")].SENT_AT.max() if len(notes) else None)
    attempts = int(b.get("NOTIFY_ATTEMPTS") or 0)
    if emailed is not None and not pd.isna(emailed):
        mail = f"Emailed {pd.to_datetime(emailed):%d %b %H:%M}"
    elif attempts >= 3:
        mail = "Email not sent (3 attempts)"
    else:
        mail = "Not emailed yet"
    gen = fmt.GENERATOR_CHIP.get(b.get("GENERATOR"), b.get("GENERATOR") or "")
    st.markdown("".join(f'<span class="sr-chip">{c}</span>' for c in
                        (gen, f"Model {b.get('MODEL') or '–'}", f"Published {pd.to_datetime(b['PUBLISHED_AT']):%d %b %H:%M}", mail)),
                unsafe_allow_html=True)


def body() -> None:
    st.html(nav.CSS + (b.get("BODY_HTML") or ""))
    st.caption("Hover over any number to see the table and column it came from.")


def sources() -> None:
    with st.expander("Show sources"):
        f = data.brief_facts(bid)
        cur = data.cfg("CURRENCY") or ""
        shown = [{"share": fmt.pct, "pts": fmt.pts, "index": fmt.signed_pct}.get(u, lambda v, d: fmt.money(v, cur, d))(v, d)
                 for v, u, d in zip(f.V, f.UNIT, f.DECIMALS)]
        st.dataframe(pd.DataFrame({"Fact": f.FACT_ID, "Shown as": shown, "Source": f.SOURCE}),
                     hide_index=True, use_container_width=True)


def checks() -> None:
    attempts = b.get("VIOLATIONS") or []
    if not attempts:
        return
    with st.expander("Checks: how the brief was written"):
        for a in attempts:
            who = "Template" if a.get("attempt") == "template" else f"Attempt {a.get('attempt')} ({a.get('model')})"
            v = a.get("violations") or []
            if not v:
                st.markdown(f"**{who}**: passed every check")
            else:
                st.markdown(f"**{who}**: rejected")
                st.dataframe(pd.DataFrame(v), hide_index=True, use_container_width=True)


nav.guarded("Brief header", lambda: st.subheader(b.get("HEADLINE") or ""))
nav.guarded("Chips", chips)
nav.guarded("Brief", body)
nav.guarded("Sources", sources)
nav.guarded("Checks", checks)
