# LBGB — LLM Board Game Benchmark

A benchmark that uses board games to measure reasoning and planning in LLMs.
Version 1 delivers the game engine core, the verifiable-replay machinery, and the
first game plugin: Settlers of Catan, base game, 4 players.

## Documentation map

| Path | What it is |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | How the system is built. Versionless, game-agnostic, the source of truth. |
| [`prd/PRD-v1.md`](prd/PRD-v1.md) | What release v1 delivers: scope, requirements, acceptance criteria. |
| [`kanban/KANBAN-v1.kanban.md`](kanban/KANBAN-v1.kanban.md) | What to do next. One board per release, work cut into horizontal slices. |
| [`AGENTS.md`](AGENTS.md) | Contributor and agent orientation. |

## Development

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 or newer is installed and used
automatically; no system Python is required.

One command runs the entire gate — format check, lint, types, tests:

```bash
uv run python scripts/gate.py
```

Individual steps, in the order the gate runs them:

```bash
uv run ruff check --fix .   # autofixes first, so the formatter has the final say
uv run ruff format .        # formatting
uv run ruff check .         # lint: what could not be fixed automatically
uv run mypy .               # static types
uv run pytest               # tests
```

A fresh clone needs nothing beyond `uv`: `uv run` resolves and installs the pinned
environment from `uv.lock` on first use.

### Determinism is a hard requirement

`ARCHITECTURE.md` section 6 is normative. The lint gate enforces its first clause:
importing `random` anywhere other than `lgbg/core/rng.py` fails the build, because
ambient randomness makes results unreproducible. `tests/tooling/test_no_ambient_randomness.py`
demonstrates the rule firing on a deliberate violation and pins the list of exempt paths.

## Layout

The authoritative code layout is `ARCHITECTURE.md` section 4.1.

```text
lgbg/core/     game-agnostic runtime — canonical JSON, hashing, RNG, log, replay, config
lgbg/games/    one package per game plugin; the first is catan
lgbg/host/     HTTP/JSON API over the engine (v2)
lgbg/adapters/ MCP, CLI, python client
lgbg/agents/   LLM providers and the provider-agnostic tool loop (v2)
lgbg/runner/   seats, matchmaking, run orchestration (v2)
lgbg/eval/     scoring, statistics, reporting (v3)
tests/         core, games, and tooling suites
```
