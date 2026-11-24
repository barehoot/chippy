"""SHARE_RADAR: the read-only app that analysts and judges open (owner SR_UI)."""
import streamlit as st

from sr_ui import nav

st.set_page_config(page_title="Share Radar", page_icon="📡", layout="wide")
nav.run(admin=False)
