# AGENTS.md

LBGB is an LLM benchmark that uses board games to measure reasoning and planning.

This file is a map, not a manual. Read only the document your task actually needs.

## The three documents

| Path | What it is |
|---|---|
| `ARCHITECTURE.md` | **How the system is built — the source of truth.** Versionless and game-agnostic: it stays true regardless of what is implemented today and which games exist. Read it before designing anything. |
| `prd/` | **What a release delivers.** One file per release. Carries scope, functional requirements, acceptance criteria and milestones. `ACCEPTANCE-v1.md` at the root records what v1 actually is, deviations included. |
| `kanban/` | **What to do next.** One board per release, in Markdown Kanban format. Work is cut into horizontal slices: each task cuts through every layer end to end and ends in something runnable. |

`.agents/skills/` holds reusable working procedures. Load the matching skill before starting.

## Tree

```text
.
├── AGENTS.md                     this file
├── ARCHITECTURE.md               how the system is built - versionless, game-agnostic
├── ACCEPTANCE-v1.md              release record - what v1 actually is, deviations included
├── prd/
│   ├── PRD-v1.md                 release v1 scope, requirements, acceptance
│   ├── PRD-v2.md                 release v2 - current
│   └── PRD-v3.md                 release v3 - operator console and replay viewer (next)
├── kanban/
│   ├── KANBAN-v1.kanban.md       release v1 task board - done
│   └── KANBAN-v2.kanban.md       release v2 task board - current
├── .agents/skills/
│   ├── horizontal-slicing/       how to cut and read the board
│   └── test-driven-development/  how to write the code
└── lgbg/, web/, tests/           code - created as the board is worked
```

The authoritative code layout is `ARCHITECTURE.md` section 4.1. Do not restate it elsewhere.

## How to work

1. **Pick a task** from the board of the release you are working on. Its description names the slice, what it integrates,
   its dependencies and the requirements it satisfies.
2. **Read the requirement** it cites in the PRD for its release.
3. **Read the architecture section** the PRD points to, before writing code.
4. Follow the `test-driven-development` skill: a failing test first, then the least code that passes,
   then refactor. Run the tooling gate before calling anything done.

Follow the references rather than reading all three documents end to end.

## Rules that are easy to get wrong

- **Never version `ARCHITECTURE.md`.** It is not updated when a release ships or scope changes. It
  may be amended for a planned, general capability — a new layer, a new plugin declaration — never
  for a release's scope. Versioned and game-specific detail belongs in the PRDs.
- **Keep the core game-agnostic.** Nothing game-specific in `core/`, `host/`, `runner/` or
  `console/`. Game facts reach the platform as declarations from the plugin.
- **Presentation is derived, never authored.** The console reads records and never writes one. A
  view may draw only what the game declares; it may not compute a rule, a score or a hidden fact.
- **Determinism is a hard requirement**, not a tradeoff. No floats, no `hash()`, no ambient time, no
  unordered iteration inside the engine. All randomness goes through an injected source.
- **Do not add prose sections to a kanban board.** It is a list of tasks; slicing and dependency
  notes belong in tags and card descriptions.
- **A task is done when its acceptance criteria are asserted by tests**, not when the code runs.
