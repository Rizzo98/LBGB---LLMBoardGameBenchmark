# LBGB — LLM Board Game Benchmark

A benchmark that uses board games to measure reasoning and planning in LLMs.
Version 1 is accepted: the game engine core, the verifiable-replay machinery and the first game
plugin (Settlers of Catan, base game, 4 players). Version 2 is in acceptance: the agent layer, the
runner and the run artefacts. Version 3, the operator console and replay viewer, is specified in
`prd/PRD-v3.md`.

## Documentation map

| Path | What it is |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | How the system is built. Versionless, game-agnostic, the source of truth. |
| [`prd/PRD-v1.md`](prd/PRD-v1.md) | What release v1 delivers: scope, requirements, acceptance criteria. |
| [`prd/PRD-v2.md`](prd/PRD-v2.md) | What release v2 delivers: the agent layer, the runner and the run artefacts. |
| [`prd/PRD-v3.md`](prd/PRD-v3.md) | What release v3 delivers: the operator console and the replay viewer. |
| [`kanban/KANBAN-v2.kanban.md`](kanban/KANBAN-v2.kanban.md) | What to do next: the current release board, cut into horizontal slices. |
| [`AGENTS.md`](AGENTS.md) | Contributor and agent orientation. |

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

## Running a game

The command line is the operator's view of a run:

```bash
# show the opening decisions of a new game
uv run python -m lgbg.adapters.cli new --game catan --seed 123 --board fixed:standard_a

# play a scripted action file into a run directory
uv run python -m lgbg.adapters.cli play --script game.json --out runs/demo

# replay the standalone record `play` wrote, verifying every hash
uv run python -m lgbg.adapters.cli replay runs/demo/games/g-0001.god.jsonl --print-states

# verify one record, or every record in a run directory; exits non-zero on failure
uv run python -m lgbg.adapters.cli verify runs/demo
```

A game defined outside the engine is loaded with `--plugin MODULE`, which imports a module
that registers its games. `tests/cli/test_cli.py` drives the suite's fixture game that way.

An experiment directory written by `run` holds a root manifest (`run.json`), the aggregates
(`results.json`), and one directory per game (`ARCHITECTURE.md` section 8.2). A game directory holds
its manifest (`game.json`) and, under `games/`, two records: the `<game_id>.god.jsonl` deterministic
record, and a `<game_id>.meta.jsonl` sidecar holding everything that is real and not reproducible —
wall-clock time, host, process id. `play` writes a standalone record under `<out>/games/`; the
console can open either.

A scripted action file declares the game, the configuration and an ordered list of actions.
The example below is the shape, using the suite's fixture game:

```json
{
  "game": "fixture",
  "config": { "seed": 90210, "players": 2, "interaction_protocol": "decline_only" },
  "actions": [
    { "player": 0, "type": "take" },
    { "request_id": "d1", "player": 1, "type": "gamble" }
  ]
}
```

`request_id` is optional where the player has exactly one open decision; where the choice is
ambiguous, naming it is required.

## Development

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
lgbg/console/  read-only operator console and replay read model (v3)
lgbg/eval/     scoring, statistics, reporting (v4)
web/           browser client served by the console; build-time toolchain only (v3)
tests/         core, games, console, and tooling suites
```
