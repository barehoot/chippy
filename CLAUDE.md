# Share Radar: Claude Code entry point

@AGENTS.md

## How this repository maps to Claude Code

- AGENTS.md, imported above, holds the project rules. They were written for Snowflake Cortex Code (CoCo). Wherever
  the rules or the docs say CoCo, they mean the coding agent, which here is you.
- The design is in docs/: HLD.md (what and why, architecture, decisions, ticket list), LLD.md (L1 to L14: every
  object, DDL, procedure, payload and error), TESTS_AND_COCO.md (T1 to T7: test harness, named tests, golden set,
  skills, prompts) and TICKETS.md (each ticket with its prompt, in build order). LLD.md is long: read only the
  sections the current ticket cites.
- Skills are in .claude/skills/ (identical to .cortex/skills/). The reviewer subagent is .claude/agents/sr-reviewer.md.
  The Stop hook in .claude/settings.json runs scripts/coco_log.py with --surface claude-code.
- You reach Snowflake only through the Snowflake CLI: snow sql -f <file> -c sr, or snow sql -q "<sql>" -c sr.
  Never write credentials into any file.
- The current ticket is in .sr_ticket. Plan first: show the plan for the ticket and wait for approval before
  writing files.
- If both .cortex/ and .claude/ copies of a skill exist and you change one, change the other the same way.
- docs/reference/ holds a human-readable HTML copy of the design. Use the Markdown files instead.
