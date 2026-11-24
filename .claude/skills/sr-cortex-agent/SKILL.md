---
name: sr-cortex-agent
description: How Share Radar's semantic view, search service, tool procedures and Cortex Agent are built and changed. Use when editing anything in sql/50_sem, sql/40_app/414_tool_procs.sql, kb/ or eval/golden_set.csv.
---
# Semantic view, tools and agent

## Semantic view (L10)
- Clause order: TABLES, RELATIONSHIPS, FACTS, DIMENSIONS, METRICS, COMMENT, AI_SQL_GENERATION.
  FACTS must come before DIMENSIONS.
- Every new column gets a COMMENT and the synonyms an analyst would use.
- Share metrics are valid within one market, category and period; the AI_SQL_GENERATION rule says so.

## Tools
- Signatures and payloads are fixed in L10; errors follow L13 (NOT_FOUND, AMBIGUOUS, NO_DATA, BAD_INPUT,
  TOOL_FAILED).
- Read only SEM.V_TOOL_* views. Resolve names with APP.SP_RESOLVE. Return TO_JSON(OBJECT_CONSTRUCT(...)).
- A new tool needs the procedure, a tool_spec whose description tells the orchestrator when to use it, a
  tool_resources entry with execution_environment, a grant in 70_sec/701 block 7, a T-TOOL test and golden rows.

## Agent specification
- Keep the orchestration instructions short and rule-like. Write each tool description in the user's words.
- After any change: CREATE OR REPLACE AGENT ... FROM SPECIFICATION, rerun the 505_cowork.sql grants, then
  python3 eval/run_eval.py --tools-only, then the full golden set.

## Knowledge base
- kb/*.md is split at "## " headings into KB.METHOD_DOCS by scripts/load_kb.py.
- One idea per section, under 300 words, using the definitions in share-methodology.

## After editing sql/50_sem
- Rerun sql/70_sec/702_row_access.sql (CREATE OR REPLACE VIEW drops row policies), then T-SEC-03.
