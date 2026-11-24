#!/usr/bin/env python3
"""Load kb/*.md into SR_DB.KB.METHOD_DOCS, one row per "## " section, then refresh the search service (SR-041).

  python3 scripts/load_kb.py [--connection sr] [--dry-run]

Each row's BODY starts with the document and section titles, so a search for "TDP" finds the TDP section even
when the body says "total distribution points". Rows of sections that no longer exist are deleted.
Uses the Snowflake CLI (snow sql), like scripts/coco_log.py, so it needs no Python packages.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB_DIR = ROOT / "kb"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def split_markdown(text: str, source_file: str) -> list[dict]:
    """One row per '## ' section; the '# ' line is the document title."""
    title, rows, section, body = Path(source_file).stem, [], None, []

    def flush() -> None:
        if section and "".join(body).strip():
            content = " ".join(line.strip() for line in body if line.strip())
            rows.append({"DOC_ID": f"{Path(source_file).stem}#{slug(section)}", "TITLE": title, "SECTION": section,
                         "BODY": f"{title}: {section}. {content}", "SOURCE_FILE": source_file})

    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            flush()
            section, body = line[3:].strip(), []
        elif section is not None:
            body.append(line)
    flush()
    return rows


def load_rows() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(KB_DIR.glob("*.md")):
        rows += split_markdown(path.read_text(encoding="utf-8"), f"kb/{path.name}")
    return rows


def sql_for(rows: list[dict]) -> str:
    payload = base64.b64encode(json.dumps(rows).encode("utf-8")).decode("ascii")
    src = (f"SELECT f.value:DOC_ID::VARCHAR AS DOC_ID, f.value:TITLE::VARCHAR AS TITLE, f.value:SECTION::VARCHAR AS SECTION, "
           f"f.value:BODY::VARCHAR AS BODY, f.value:SOURCE_FILE::VARCHAR AS SOURCE_FILE "
           f"FROM TABLE(FLATTEN(INPUT => PARSE_JSON(BASE64_DECODE_STRING('{payload}')))) f")
    return (
        f"MERGE INTO SR_DB.KB.METHOD_DOCS t USING ({src}) s ON t.DOC_ID = s.DOC_ID "
        "WHEN MATCHED THEN UPDATE SET t.TITLE = s.TITLE, t.SECTION = s.SECTION, t.BODY = s.BODY, "
        "t.SOURCE_FILE = s.SOURCE_FILE, t.UPDATED_AT = CURRENT_TIMESTAMP() "
        "WHEN NOT MATCHED THEN INSERT (DOC_ID, TITLE, SECTION, BODY, SOURCE_FILE) "
        "VALUES (s.DOC_ID, s.TITLE, s.SECTION, s.BODY, s.SOURCE_FILE);\n"
        f"DELETE FROM SR_DB.KB.METHOD_DOCS WHERE DOC_ID NOT IN (SELECT DOC_ID FROM ({src}));\n"
        "ALTER CORTEX SEARCH SERVICE SR_DB.SEM.CSS_METHOD REFRESH;\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--connection", default="sr")
    ap.add_argument("--dry-run", action="store_true", help="print the sections instead of loading them")
    args = ap.parse_args(argv)
    rows = load_rows()
    if args.dry_run:
        for r in rows:
            print(f"{r['DOC_ID']:<45} {len(r['BODY'].split()):>4} words")
        print(f"{len(rows)} sections")
        return 0
    res = subprocess.run(["snow", "sql", "-q", sql_for(rows), "-c", args.connection], capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stderr or res.stdout, file=sys.stderr)
        return res.returncode
    print(f"Loaded {len(rows)} sections into SR_DB.KB.METHOD_DOCS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
