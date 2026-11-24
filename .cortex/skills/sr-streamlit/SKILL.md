---
name: sr-streamlit
description: Rules for the two Share Radar Streamlit in Snowflake apps (read-only and admin) on the warehouse runtime. Use when editing anything under streamlit/.
---
# Streamlit apps

## The model (L11)
- One codebase, two apps: SHARE_RADAR (owner SR_UI, read-only) and SHARE_RADAR_ADMIN (owner SR_APP).
  Both run with their owner's rights.
- Pages are pages/0_Radar.py to pages/4_Settings.py, listed by sr_ui/nav.py with st.navigation.
  Settings and the replay panel appear only when st.session_state.sr_admin is true.

## Rules
- All SQL lives in sr_ui/data.py, with bound parameters: session.sql(sql, params=[...]).
- Never run pipeline steps from the app. Start work with data.start_task(...), which runs EXECUTE TASK,
  and watch OPS.RUN_LOG and OPS.STEP_LOG.
- No SHOW, DESCRIBE or ALTER SESSION in app code.
- Cache reads with st.cache_data(ttl=120). Never cache actions; call data.clear_cache() after one.
- Format numbers only through sr_ui/format.py, so they read the same as in the brief.
- Draw charts only through sr_ui/charts.py: zero baselines, signed labels, tooltips, the palette constants.
- On error, show a short message and a retry button. Never show a stack trace in the read-only app.

## Deploy
- From streamlit/: snow streamlit deploy share_radar --replace --role SR_UI -c sr, then share_radar_admin
  with --role SR_APP.
- Pin streamlit in environment.yml with "=" (1.37 or later).

## Tests
- T-UI-01 and T-UI-02 live in python/tests/test_ui.py and import sr_ui.charts and sr_ui.format only;
  format imports data lazily, inside name().
