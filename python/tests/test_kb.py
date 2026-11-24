"""Knowledge-base loader tests (SR-041): sections, IDs and the share-methodology wording."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("load_kb", ROOT / "scripts" / "load_kb.py")
load_kb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(load_kb)


def test_split_markdown_one_row_per_section():
    rows = load_kb.split_markdown("# Doc\n\nintro ignored\n## One\nalpha\n\n## Two\nbeta\n## Empty\n", "kb/doc.md")
    assert [r["DOC_ID"] for r in rows] == ["doc#one", "doc#two"]
    assert rows[0]["BODY"] == "Doc: One. alpha" and rows[0]["TITLE"] == "Doc"


def test_kb_files_load_with_unique_ids_and_short_sections():
    rows = load_kb.load_rows()
    assert len({r["DOC_ID"] for r in rows}) == len(rows) >= 25
    assert all(len(r["DOC_ID"]) <= 64 for r in rows)
    assert all(len(r["BODY"].split()) < 300 for r in rows)        # one idea per section (sr-cortex-agent skill)
    assert {r["SOURCE_FILE"] for r in rows} == {f"kb/{n}" for n in (
        "acv_and_tdp.md", "share_bridge.md", "artefact_rules.md", "periods.md", "glossary.md")}


def test_golden_method_phrase_is_in_the_tdp_section():
    tdp = [r for r in load_kb.load_rows() if r["DOC_ID"] == "acv_and_tdp#how-tdp-is-calculated"][0]
    assert "sum of" in tdp["BODY"].lower()
