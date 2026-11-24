# Share Radar starter kit

Everything a coding agent needs to build Share Radar one ticket at a time: the design (HLD, LLD, tests), the agent rules, five skills, a reviewer subagent, a session-log hook and 41 tickets with ready-to-paste prompts. It works with Claude Code, the CoCo CLI and CoCo in Snowsight.

## What is inside

```text
share-radar/
├── README.md                  # this file
├── AGENTS.md                  # project rules every agent session loads (T4)
├── CLAUDE.md                  # Claude Code entry point; imports AGENTS.md
├── .sr_ticket                 # current ticket ID (starts at SR-001)
├── .gitignore                 # keeps .snowflake/, keys and .env out of Git
├── docs/
│   ├── HLD.md                 # what and why, architecture, weekly run, agent, decisions, tickets, risks
│   ├── LLD.md                 # L1–L14: names, DDL, procedures, ML, brief, orchestration, agent, app, security, errors, cost
│   ├── TESTS_AND_COCO.md      # T1–T7: test harness, named tests, golden set, rules, skills, reviewer, hook, prompts
│   ├── TICKETS.md             # every ticket in build order, with "done when" and its prompt
│   ├── img/                   # architecture, weekly run and timeline diagrams (SVG)
│   └── reference/Share_Radar_Design.html   # the same design as one page, for people
├── .cortex/                   # for CoCo: skills, sr-reviewer subagent, Stop hook
├── .claude/                   # for Claude Code: the same skills, subagent and Stop hook
└── scripts/coco_log.py        # session log written by the Stop hook (T6)
```

The agent creates everything else (sql/, python/, streamlit/, tests/, eval/, kb/) ticket by ticket, exactly as laid out in LLD section L2.

## Before you start (about 15 minutes)

1. **Make it a Git repository.** The session log and the reviewer both read `git diff`.

   ```bash
   cd share-radar
   git init && git add . && git commit -m "SR-000: starter kit"
   ```

2. **Install the Snowflake CLI and add the `sr` connection.** Every command in AGENTS.md uses it.

   ```bash
   pip install snowflake-cli
   ```

   Add this to `~/.snowflake/config.toml`. It goes in your home folder, never in the repository, and it holds no password:

   ```toml
   [connections.sr]
   account = "<orgname>-<accountname>"
   user = "<your Snowflake user>"
   authenticator = "externalbrowser"
   role = "<the role you were given, or ACCOUNTADMIN on your own trial account>"
   warehouse = "<any warehouse you can use>"
   ```

   Check it with `snow connection test -c sr`. After SR-002 has created them, change `role` to `SR_DEV` and `warehouse` to `SR_WH_XS`. If the organisers already created roles and warehouses, LLD section L1 says how to map the `SR_*` roles to yours.

3. **Check that the AI features work.** SR-002 runs `sql/00_setup/009_feature_smoke_test.sql`. Fix anything it reports as failing before you start SR-003; assumptions A5 and A6 in the HLD list the fallbacks.

## Open the kit in your agent

| Agent | How to start | What it reads | Plan first |
| --- | --- | --- | --- |
| Claude Code | run `claude` in the folder | CLAUDE.md (which imports AGENTS.md) and `.claude/` | press Shift+Tab until plan mode is on, then paste the prompt |
| CoCo CLI | run `cortex` in the folder | AGENTS.md and `.cortex/` | start the prompt with `/plan` |
| CoCo in Snowsight | Workspaces → upload the folder → CoCo icon | AGENTS.md at the workspace root | end the prompt with "Show me a plan first and wait for my approval." |

**CoCo in Snowsight:** skills only load once uploaded through the CoCo panel. Click **+ → Upload Skill Folder(s)** and add each folder in `.cortex/skills/`. Hooks may not fire there, so record that work later from a laptop with `python3 scripts/coco_log.py --event manual --surface snowsight --note "<ticket and what was built>"`.

**If the sprint rules require CoCo,** run the build tickets in CoCo. The same files work in both agents, and the session log records which one did each ticket.

## First session

Paste this first, so the agent orients itself before it writes anything:

```text
Read AGENTS.md, docs/HLD.md and docs/TICKETS.md. Do not write any files yet. In at most 10 lines, tell me what we are building, the build order, and which of the HLD assumptions A1 to A8 you need me to confirm before SR-003.
```

Then start the ticket loop:

```bash
echo SR-001 > .sr_ticket
```

Paste the SR-001 prompt from `docs/TICKETS.md`, approve the plan, and continue with SR-002, SR-003 and so on in the order that file gives. The loop for each ticket is at the top of `docs/TICKETS.md`.

## What only a person can supply

- **SR-003:** the agent finds the NIQ databases and proposes a column mapping (the `<NIQ_...>` placeholders); you approve it before any view is written.
- **SR-004:** the demo country, category, focus manufacturer and parent market.
- **SR-013:** five reference numbers from an NIQ report, to reconcile the share grid.
- **SR-044, SR-060, SR-062, SR-064:** golden-set answers, analyst timings, the video and the submission.

## Rules that keep the build on track

- One ticket per session. The agent touches only that ticket's files.
- Names in the LLD are final. If one looks wrong, the agent stops and asks.
- A ticket is done when its named tests pass and `sr-reviewer` reports nothing BLOCKING.
- The agent never edits a test to make it pass.
- Credentials stay in `~/.snowflake/config.toml`, never in the repository.

## When the design changes

Re-export the changed doc tab to the same file in `docs/` (HLD.md, LLD.md or TESTS_AND_COCO.md), commit it, and tell the agent which section changed.
