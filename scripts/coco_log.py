#!/usr/bin/env python3
"""Share Radar CoCo session log.

stop    Stop hook: record the ticket, changed files, lines added and tests touched, if the tree changed.
human   A person edited CoCo's output by hand: always record, with HUMAN_EDITS = true.
manual  Work done where hooks do not fire (for example CoCo in Snowsight): always record.
flush   Load records not yet loaded into SR_DB.OPS.COCO_LOG.

Never blocks CoCo: every failure goes to stderr and the exit code is 0.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_MD = ROOT / "docs" / "coco_log.md"
LOG_JSONL = ROOT / "docs" / "coco_log.jsonl"
STATE = ROOT / ".git" / "sr_coco_state.json"          # last diff hash and number of lines loaded
TICKET_FILE = ROOT / ".sr_ticket"
CONNECTION = os.environ.get("SR_CONNECTION", "sr")
MD_HEADER = ("| Logged (UTC) | Ticket | Surface | Event | Files | Lines added | Tests touched | Human edits | Note |\n"
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")

def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout

def current_ticket() -> str:
    return TICKET_FILE.read_text(encoding="utf-8").strip() if TICKET_FILE.exists() else "SR-???"

def changed_files() -> tuple[list[str], int, str]:
    """Files changed against HEAD, lines added, and a hash of the numstat used to skip unchanged trees."""
    numstat = git("diff", "--numstat", "HEAD")
    files, added = [], 0
    for line in numstat.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            files.append(parts[2])
            added += int(parts[0]) if parts[0].isdigit() else 0
    return files, added, hashlib.sha1(numstat.encode()).hexdigest()

def tests_touched(files: list[str]) -> list[str]:
    return sorted(Path(f).stem for f in files if f.startswith(("tests/sql/T-", "python/tests/test_")))

def read_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"diff_hash": "", "loaded": 0}

def write_state(state: dict) -> None:
    STATE.write_text(json.dumps(state))

def hook_input() -> dict:
    """The hook passes a JSON object on stdin; manual calls have none."""
    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}

def record(row: dict) -> None:
    LOG_MD.parent.mkdir(parents=True, exist_ok=True)
    if not LOG_MD.exists():
        LOG_MD.write_text("# CoCo session log\n\n" + MD_HEADER, encoding="utf-8")
    with LOG_MD.open("a", encoding="utf-8") as md:
        md.write(f"| {row['logged_at']} | {row['ticket']} | {row['surface']} | {row['event']} | {len(row['files'])} | "
                 f"{row['lines_added']} | {', '.join(row['tests']) or '-'} | {'yes' if row['human_edits'] else 'no'} | "
                 f"{row['note'].replace('|', '/')} |\n")
    with LOG_JSONL.open("a", encoding="utf-8") as js:
        js.write(json.dumps(row) + "\n")

def flush(state: dict) -> None:
    lines = LOG_JSONL.read_text(encoding="utf-8").splitlines() if LOG_JSONL.exists() else []
    new = [json.loads(x) for x in lines[state["loaded"]:]]
    if not new:
        return
    payload = base64.b64encode(json.dumps(new).encode("utf-8")).decode("ascii")
    sql = ("INSERT INTO SR_DB.OPS.COCO_LOG (LOGGED_AT, TICKET, SURFACE, FILES, LINES_ADDED, TESTS, HUMAN_EDITS, NOTE) "
           "SELECT f.value:logged_at::TIMESTAMP_LTZ, f.value:ticket::VARCHAR, f.value:surface::VARCHAR, f.value:files, "
           "f.value:lines_added::NUMBER, f.value:tests, f.value:human_edits::BOOLEAN, f.value:note::VARCHAR "
           f"FROM TABLE(FLATTEN(INPUT => PARSE_JSON(BASE64_DECODE_STRING('{payload}')))) f")
    res = subprocess.run(["snow", "sql", "-q", sql, "-c", CONNECTION], capture_output=True, text=True, check=False)
    if res.returncode == 0:
        state["loaded"] = len(lines)
    else:
        print(f"coco_log: load failed, will retry next flush: {res.stderr.strip()[:300]}", file=sys.stderr)

def main(event: str, surface: str = "cli", note: str = "") -> int:
    try:
        state = read_state()
        if event == "flush":
            flush(state)
        else:
            files, added, diff_hash = changed_files()
            if event == "stop" and diff_hash == state["diff_hash"]:
                return 0                                   # nothing changed since the last record
            hook = hook_input() if event == "stop" else {}
            record({
                "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "ticket": current_ticket(), "surface": surface, "event": event,
                "files": files, "lines_added": added, "tests": tests_touched(files),
                "human_edits": event == "human",
                "note": (note or str(hook.get("session_id", "")))[:500],
            })
            state["diff_hash"] = diff_hash
        write_state(state)
    except Exception as exc:                               # the hook must never stop CoCo
        print(f"coco_log: {exc}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", choices=["stop", "human", "manual", "flush"], required=True)
    parser.add_argument("--surface", choices=["cli", "desktop", "snowsight", "claude-code"], default="cli")
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    sys.exit(main(args.event, args.surface, args.note))
