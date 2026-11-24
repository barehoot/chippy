#!/usr/bin/env bash
# Share Radar: deploy everything in the L2 order.
#   00_setup -> 10_src -> 20_core -> 40_app/401 (tables) -> sr_lib.zip PUT -> 30_ml -> rest of 40_app -> 50_sem
#   -> load KB -> 60_ops -> 70_sec/701, 702 -> the two Streamlit apps -> 70_sec/703 -> CoCo log flush
#
# Usage: scripts/deploy_all.sh            (connection "sr", or set SR_CONNECTION)
#        SKIP_APPS=1 scripts/deploy_all.sh  (SQL only)
# Files marked "organizer" need privileges the team may not have (CREATE INTEGRATION, ALTER on the CoWork
# object, ACCOUNTADMIN grants). Their failure is reported and the deploy carries on; hand them to the organizers.
set -euo pipefail
cd "$(dirname "$0")/.."
CONN="${SR_CONNECTION:-sr}"
FAILED_OPTIONAL=()

run_sql() {   # run_sql <file> [organizer]
  local f="$1" kind="${2:-}"
  echo "== $f"
  if ! snow sql -f "$f" -c "$CONN" >/tmp/sr_deploy_last.log 2>&1; then
    if [[ "$kind" == "organizer" ]]; then
      echo "   !! failed (needs organizer privileges?): see message below; continuing"
      tail -5 /tmp/sr_deploy_last.log | sed 's/^/   /'
      FAILED_OPTIONAL+=("$f")
    else
      cat /tmp/sr_deploy_last.log
      echo "Deploy stopped at $f"
      exit 1
    fi
  fi
}

build_and_put_sr_lib() {
  echo "== python/sr_lib -> @SR_DB.APP.CODE/sr_lib.zip"
  mkdir -p python/build
  python3 - <<'PY'
import pathlib, zipfile
root = pathlib.Path("python")
with zipfile.ZipFile(root / "build" / "sr_lib.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted((root / "sr_lib").rglob("*.py")):
        z.write(p, p.relative_to(root))
print("   sr_lib.zip:", sorted(n for n in zipfile.ZipFile(root / "build" / "sr_lib.zip").namelist()))
PY
  snow sql -c "$CONN" -q "CREATE STAGE IF NOT EXISTS SR_DB.APP.CODE" >/dev/null
  snow sql -c "$CONN" -q "PUT file://$(pwd)/python/build/sr_lib.zip @SR_DB.APP.CODE AUTO_COMPRESS = FALSE OVERWRITE = TRUE" >/dev/null
}

# 00_setup (the smoke test 009 is run by hand, SR-002)
run_sql sql/00_setup/001_roles_wh_db.sql organizer
run_sql sql/00_setup/002_settings.sql
run_sql sql/00_setup/003_ops_tables.sql
run_sql tests/sql/000_fixtures.sql

# 10_src, 20_core
for f in sql/10_src/*.sql sql/20_core/*.sql; do run_sql "$f"; done

# 40_app tables, then the Python package the procedures import
run_sql sql/40_app/401_result_tables.sql
build_and_put_sr_lib

# 30_ml, then the rest of 40_app
for f in sql/30_ml/*.sql; do run_sql "$f"; done
for f in sql/40_app/*.sql; do [[ "$f" == */401_* ]] || run_sql "$f"; done

# 50_sem, with the knowledge base loaded before the agent
run_sql sql/50_sem/501_v_sem_views.sql
run_sql sql/50_sem/502_sv_share.sql
run_sql sql/50_sem/503_kb_and_search.sql
python3 scripts/load_kb.py --connection "$CONN"
run_sql sql/50_sem/504_agent.sql
run_sql sql/50_sem/505_cowork.sql organizer

# 60_ops (each file starts with USE ROLE SR_APP)
run_sql sql/60_ops/601_stream_task.sql
run_sql sql/60_ops/602_replay.sql
run_sql sql/60_ops/603_notifications.sql organizer
run_sql sql/60_ops/604_alert.sql
run_sql sql/60_ops/606_observability.sql
[[ -n "${WITH_DMF:-}" ]] && run_sql sql/60_ops/605_dmf.sql organizer

# 70_sec grants and row access (702 always runs after 50_sem: CREATE OR REPLACE VIEW drops row policies)
run_sql sql/70_sec/701_grants.sql organizer
run_sql sql/70_sec/702_row_access.sql

# Streamlit apps, then app usage grants
if [[ -z "${SKIP_APPS:-}" ]]; then
  (cd streamlit && snow streamlit deploy share_radar --replace --role SR_UI -c "$CONN")
  (cd streamlit && snow streamlit deploy share_radar_admin --replace --role SR_APP -c "$CONN")
  run_sql sql/70_sec/703_app_usage.sql
fi

python3 scripts/coco_log.py --event flush || true

echo
echo "Deploy finished."
if (( ${#FAILED_OPTIONAL[@]} )); then
  echo "Needs organizer action:"; printf '  - %s\n' "${FAILED_OPTIONAL[@]}"
fi
echo "Next: snow sql -f tests/sql/run_all.sql -c $CONN   (T-E2E-01 after every deploy: E12)"
