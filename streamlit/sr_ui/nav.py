"""Page list, sidebar and session-state defaults (L11), plus the section guard every page uses."""
from __future__ import annotations

from collections.abc import Callable

import streamlit as st

DEFAULTS = {"sr_admin": False, "shift_id": None, "brief_id": None, "awaiting": None}
# awaiting = {"kind": "REPLAY" | "RERUN", "since": <Snowflake timestamp text>, "t0": <time.monotonic()>}

CSS = """<style>
.fact { border-bottom: 1px dotted #898781; cursor: help }
.sr-chip { display: inline-block; padding: 1px 8px; margin-right: 6px; border-radius: 10px; background: #f0efec;
           color: #52514e; font-size: 0.85em }
</style>"""


def run(admin: bool) -> None:
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value)
    st.session_state["sr_admin"] = admin
    pages = [st.Page("pages/0_Radar.py", title="Radar", icon="📡", default=True),
             st.Page("pages/1_Shift_detail.py", title="Shift detail", icon="🔍"),
             st.Page("pages/2_Brief.py", title="Brief", icon="📰"),
             st.Page("pages/3_Trust.py", title="Trust", icon="✅")]
    if admin:
        pages.append(st.Page("pages/4_Settings.py", title="Settings", icon="⚙️"))
    page = st.navigation(pages)        # with st.navigation, Streamlit ignores automatic pages/ discovery
    st.html(CSS)
    guarded("Sidebar", sidebar, container=st.sidebar)
    page.run()


def is_admin() -> bool:
    return bool(st.session_state.get("sr_admin"))


def guarded(title: str, render: Callable[[], None], container=None) -> None:
    """Run one section; on failure show a short message and a retry button, never a stack trace (L13).
    The admin app adds the first 300 characters of the Snowflake message."""
    try:
        render()
    except Exception as e:                                    # noqa: BLE001 - every section fails soft
        box = container or st
        box.warning(f"Couldn't load {title.lower()}.")
        if is_admin():
            box.caption(str(e)[:300])
        if box.button("Retry", key=f"retry_{title}"):
            from sr_ui import data
            data.clear_cache()
            st.rerun()


def sidebar() -> None:
    """Scope, as-of week, current run status and bridge mode, 'Names masked', the viewer, and the CoWork agent."""
    from sr_ui import data, format as fmt
    sb = st.sidebar
    sb.markdown("### Share Radar")
    markets = data.market_names()
    sb.markdown(f"**Category** {data.cfg('SCOPE_CATEGORY')}  \n"
                f"**Market** {markets.get(str(data.cfg('SCOPE_PARENT_MARKET')), data.cfg('SCOPE_PARENT_MARKET'))}  \n"
                f"**Focus** {fmt.name(data.cfg('FOCUS_MANUFACTURER'), 'MANUFACTURER')}  \n"
                f"**Data as of** {data.cfg('AS_OF_WEEK_END')}")
    run = data.current_run()
    if run:
        sb.markdown(f"**Run** {fmt.RUN_CHIP.get(run.status, run.status)} · bridge mode {run.bridge_mode or '–'}")
    if data.active_run():
        sb.info("Updating…")
    if data.cfg("DISPLAY_ALIAS") is True:
        sb.markdown('<span class="sr-chip">Names masked</span>', unsafe_allow_html=True)
    sb.caption(f"Viewer: {data.viewer_name() or 'viewer unknown'}")
    sb.caption("Ask follow-up questions in CoWork: AI & ML › Agents › Share Radar.")
