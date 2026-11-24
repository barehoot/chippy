"""Settings (admin app only): thresholds and recipients (L11). Scope and replay keys are read-only here."""
from __future__ import annotations

import json

import streamlit as st

from sr_ui import data, nav

st.title("Settings")
if not nav.is_admin():
    st.error("Settings are available in the admin app only.")
    st.stop()

st.info("Saving any setting makes the dynamic tables refresh once, because they read OPS.SETTINGS. "
        "Scope and the as-of week are changed by SR-004 and the replay controls, not here.")


def table() -> None:
    s = data.settings()
    s = s.assign(EDITABLE=[k in data.EDITABLE for k in s.SETTING_KEY])
    st.dataframe(s, hide_index=True, use_container_width=True)


def form() -> None:
    st.subheader("Change a setting")
    key = st.selectbox("Setting", sorted(data.EDITABLE))
    kind, lo, hi = data.EDITABLE[key]
    current = data.cfg(key)
    with st.form("edit_setting"):
        if kind is bool:
            value = st.toggle(key, value=bool(current))
        elif kind is list:
            text = st.text_area("Email addresses, one per line", value="\n".join(current or []))
            value = [line.strip() for line in text.splitlines() if line.strip()]
        elif kind is int:
            value = int(st.number_input(key, value=int(current or 0), min_value=int(lo) if lo is not None else None,
                                        max_value=int(hi) if hi is not None else None, step=1))
        else:
            value = float(st.number_input(key, value=float(current or 0), min_value=float(lo) if lo is not None else None,
                                          max_value=float(hi) if hi is not None else None, format="%.4f"))
        if st.form_submit_button("Save"):
            try:
                data.save_setting(key, value)
                st.success(f"{key} = {json.dumps(value)}")
            except ValueError as e:
                st.error(str(e))


nav.guarded("Settings table", table)
nav.guarded("Settings form", form)
