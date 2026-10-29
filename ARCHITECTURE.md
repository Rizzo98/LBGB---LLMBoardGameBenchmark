# LBGB — LLM Board Game Benchmark: Architecture

**Status:** source of truth — architecture is versionless and game-agnostic
**Scope:** the complete target architecture of the system, independent of what is currently
implemented and independent of which games are implemented.

---

## 0. About this document

This document describes **what the system is**, not what is being built right now, and not which
games exist. It is deliberately versionless and **game-agnostic**: it is not updated when a release
ships, when scope changes, or when a game plugin is added, removed, or modified.

Specific games appear only as clearly-labelled illustrations of a general contract. Any statement in
this document that applies only to one game is a defect in this document.

Everything that is *versioned* or *game-specific* lives elsewhere:

| Document | Answers |
|---|---|
| `ARCHITECTURE.md` (this document) | What the system is, and why it is shaped this way. Independent of release and of game. |
| `prd/PRD-v*.md` | What a specific release delivers: scope, requirements, acceptance criteria. A PRD for a game plugin necessarily discusses that game in concrete detail. |
| `games/*/RULES.md` | The pinned interpretation of each rule of one game, with citations. |

Presence in this document — in a diagram, a directory layout, or an interface — indicates that a
component is **architecturally planned** or **architecturally required of any game plugin**, not that
it exists for any particular game. Implementation status is a matter for the PRDs.

---

## 1. Purpose and framing

LBGB is a **measurement instrument** that happens to contain game engines. The engine is the
well-understood part; the hard parts are (a) making results bit-for-bit reproducible and (b) ensuring
that what we measure is *reasoning and planning*, not *plumbing or prompt formatting*.

Every design decision below follows from those two goals. Where a decision looks like
over-engineering for a rules engine, it is usually load-bearing for benchmark validity.

### 1.1 The central artefact

The system's single most important output is:

> A game record which can be replayed to reconstruct **every intermediate game state**, with a
> cryptographic hash asserted at **every step**, and any divergence detected and localised.

Everything else — MCP surfaces, LLM agents, scoring, dashboards — is built on top of that artefact.
If the record is not trustworthy, no result computed from it is falsifiable.

Every presentation surface — the CLI, the operator console, the replay viewer — is a **derived view**
of that artefact. None of them may produce it, alter it, or stand in for it as evidence.

---

## 2. Design principles

| # | Principle | Consequence |
|---|---|---|
| P1 | **The engine is a pure function.** | `(state, action, random_draws) -> (state', events)` or `Rejection`. No I/O, no globals, no clock. |
| P2 | **Randomness is injected and recorded, never ambient.** | The RNG records *every draw*, not just the seed. Replay validates draws semantically. |
| P3 | **Determinism is a hard requirement, not a nice-to-have.** | No floats, no `hash()`, no set iteration, no wall-clock inside the engine. |
| P4 | **An action attempt is an event even when rejected.** | Illegal moves are first-class, logged, counted, and measurable. |
| P5 | **The log is the god view; observations are derived projections.** | Hidden information is a *projection* concern, not an engine-state concern. |
| P6 | **Games declare their schemas as data.** | Tool definitions and prompts are *generated* from `action_schema()` / `observation_schema()`. |
| P7 | **The engine never enumerates moves for the player — that is an assist-level decision.** | Legal-action enumeration is a *rendering* concern, gated by a tunable knob. |
| P8 | **One canonical serialisation function.** | The same function produces hashes and replay inputs. Two implementations would drift. |
| P9 | **Timestamps and agent payloads live outside the deterministic core.** | They go in a sidecar file so the hashed record stays stable. |
| P10 | **Rules fidelity is verified against the rulebook, not against memory.** | Each game pins its rule interpretations in a cited document before implementation (§7.9). |
| P11 | **Nothing game-specific may reach the core, the host, the runner, or the console.** | Game facts reach the platform as *declarations* from the plugin (§7.10, §7.11, §7.12), never as branches in shared code. |
| P12 | **Presentation is derived, never authored.** | A view is a pure function of a record plus the game's declarations (its projection, geometry and standings). It cannot produce, alter, or become evidence for a record, and it holds no game facts of its own. |

---

## 3. Scope boundaries

These boundaries are **architectural**, not release-scoped. They are consequences of the design
principles above and do not move as the project progresses.

| Boundary | Rationale |
|---|---|
| **No free-text negotiation.** Any interaction between players is expressed as structured actions. | Unstructured text requires a parser, admits collusion and kingmaking, and destroys reproducibility. A natural-language mode, if ever added, would be a separately specified experimental variant with an auditable parsing layer. |
| **No game-specific transport code.** Tool and resource definitions are generated from the game's declared schemas. | If adding a game requires hand-written tools, the plugin system has failed (P6). |
| **No hand-authored adjacency or incidence tables.** Structural relations are derived from coordinates. | Hand-authored tables of even modest size are unverifiable and are a recurring source of silent rule errors (§7.5). |
| **No agent-framework behaviour that is not logged and constant across models.** | Any unlogged convenience silently becomes the thing being measured (§13). |
| **No engine instrumentation for metrics.** Metrics are folds over the event log. | Keeps the engine pure (P1) and lets any metric be recomputed retroactively from existing records. |
| **No expansions as flags on an existing plugin.** An expansion that changes the decision structure or the information model is a new plugin. | Feature flags would distort the plugin interface away from the base game's shape and make both configurations harder to verify. |
| **No game-specific branches in the core, host, runner, or console.** | A game fact that shared code must act on becomes a declared capability, not an `if` (§7.10, §7.11, §7.12). |
| **No presentation surface may act.** | The console reads records, proposes a configuration, and launches the runner. It never owns a live session, and no graphical game surface exists during play (§12.4). |
| **No game facts in the client.** | A presentation surface shows the projection or observation it is given. It never re-derives a rule, a score, a legal move, or hidden state from public data (§12.4). |

---

## 4. Layered architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  console/ + web/  read-only operator console and replay viewer       │
│                   (reads records and declarations; never writes)     │
├──────────────────────────────────────────────────────────────────────┤
│  eval/       scoring, Elo / Bradley-Terry, dashboards                │
├──────────────────────────────────────────────────────────────────────┤
│  runner/     seats, matchmaking, mirror seats, run orchestration     │
├──────────────────────────────────────────────────────────────────────┤
│  agents/     LLM providers, provider-agnostic tool loop              │
├──────────────────────────────────────────────────────────────────────┤
│  adapters/   mcp/ (stdio bridge + HTTP), cli/, python client         │
├──────────────────────────────────────────────────────────────────────┤
│  host/       HTTP/JSON API over the engine, session registry         │
╞══════════════════════════════════════════════════════════════════════╡
│  core/       Game protocol, Action/Event/DecisionRequest,            │
│              seeded+replay RNG, canonical JSON, event log,           │
│              replay engine, projection replay, run config            │
├──────────────────────────────────────────────────────────────────────┤
│  games/      one package per game: state, structure, rules, phase    │
│              machine, projection, notation, schemas, prompts, view   │
└──────────────────────────────────────────────────────────────────────┘
```

**The core never imports a game. Games never import a transport.**
The dependency arrow points strictly downward.

**Nothing below the console imports it, except the CLI's `console` command, which is only a
launcher.** It is a consumer of records and declarations, not a layer anything depends on. No core,
host, runner, agent or game package imports it. It never imports `host/`, and a played game never
passes through it.

### 4.1 Repository layout

The tree below shows the game-agnostic packages, and — as a labelled example — the first game plugin
in full, which serves as the reference shape for any game plugin.

```
lgbg/
  core/                     engine-agnostic runtime
    types.py                Action, Event, DecisionRequest, ActionDomain, Observation, Outcome
    rng.py                  RandomSource, SeededRandomSource, ReplayRandomSource, NullRandomSource
    errors.py               Rejection, core rejection codes
    game.py                 Game protocol, plugin registry
    canonical.py            canonical_json(), hash_state()   <- single source of truth
    log.py                  GameLogWriter, GameLogReader, record dataclasses
    replay.py               replay(), verify(), projection_replay()
    config.py               RunConfig, GameConfig, AssistLevel, RejectionDetail
    run.py                  RunRecord, GameRecord, outcome records
  games/
    catan/                  EXAMPLE: the first game plugin, in full
      __init__.py           registers the game
      state.py              the game's state and its sub-structures (frozen dataclasses)
      board/
        topology.py         coordinates, derived adjacency, structural invariant checks
        layout.py           the canonical arrangement
        generation.py       fixed and seeded-random arrangement construction
        boards/             curated fixed arrangement data files
      rules/
        setup.py            opening placement and starting endowment
        production.py       resource generation and supply limits
        building.py         piece placement, costs, piece and adjacency constraints
        longest_road.py     the longest-path award (see the plugin's RULES.md)
        trading.py          exchange with the supply, and structured player-to-player trade
        devcards.py         deck, purchase, timing rules, card effects
        robber.py           forced-discard phase, blocking, and seizure
        victory.py          scoring, awards, win detection
      phases.py             the phase machine and decision-request construction
      projection.py         observe(state, player) -> Observation
      notation.py           human-readable and token-efficient renderings
      action_schema.py      JSON Schemas for actions and observations, as data
      prompts/game.md       the shared rules/notation prompt (versioned, hashed)
      RULES.md              pinned rule interpretations, with citations (§7.9)
      game.py               the Game implementation
      view.py               presentation geometry: static scene keyed by canonical ids
  host/                     HTTP/JSON API and session registry
  console/                  read-only operator console and replay read model
    app.py                  ASGI routes, response envelope, static assets
    runs.py                 the one run-directory reader: layout, discovery, compatibility
    replay.py               verify + replay, cached timelines, projections
    operator.py             one run-config schema, validation, preflight, launch
  adapters/
    mcp/                    MCP server: generated tools + resources
    cli/                    new, play, replay, verify, fuzz, inspect, console
  agents/                   LLM providers, tool loop, prompt assembly
  runner/                   seat orchestration, run records, benchmark profiles
  eval/                     scoring, statistics, reporting
web/                        browser client served by the console; build-time toolchain only
  src/shell/                run browser, config editor, timeline, panels
  src/games/catan/          EXAMPLE: the Catan board renderer (SVG)
tests/
  core/                     determinism, canonicalisation, log round-trip, replay
  games/                    per-game conformance: rules, structure, projection leaks, goldens
  console/                  read model, API, seat-mode leaks, compatibility, operator config
  agents/  runner/  eval/   added with those layers
scripts/                    ad-hoc analysis
ARCHITECTURE.md             this document
prd/                        per-release product requirements
```

---

## 5. Core data model

### 5.1 Identity and time

```python
GameId   = str      # e.g. "g-0001"
PlayerId = int      # seat index; seat order is additionally used as a tie-break ordering
Seq      = int      # monotonically increasing, starts at 0 for the initial state
```

**Decision IDs and action IDs are counter-derived, never `uuid4()`.**
The engine holds a monotonic counter; IDs are `d{seq}` / `a{seq}`. This keeps replay exact.

### 5.2 Action

Actions arrive from the outside world (CLI, script, HTTP client, agent) and are therefore untrusted.

```python
@dataclass(frozen=True, slots=True)
class Action:
    player: PlayerId
    type: str                       # a type declared by the game's action schema
    params: Mapping[str, JsonValue] # validated against that type's schema
```

The engine never trusts `type` or `params`. Every action is validated against:

1. the game's declared action schema (§7.3),
2. the open decision requests (§5.6),
3. the game's rules.

### 5.3 Event

Events are what the engine emits on success. They are the *narrative* of the game and the replay
input.

```python
@dataclass(frozen=True, slots=True)
class Event:
    type: str                       # a type declared by the game
    payload: Mapping[str, JsonValue]
```

Events are, by contract, **sufficient to describe every change to state**. A useful test: two states
that produce the same event list from the same starting state must be equal. This is asserted in the
fuzzer (§15.4).

### 5.4 Random draws

```python
@dataclass(frozen=True, slots=True)
class RngDraw:
    purpose: str        # semantic label, e.g. "dice_roll", "deck_deal", "random_selection"
    kind: str           # "randint" | "choice" | "shuffle"
    args: Mapping[str, JsonValue]
    value: JsonValue
```

```python
class RandomSource(Protocol):
    def randint(self, lo: int, hi: int, *, purpose: str) -> int: ...
    def choice(self, items: Sequence[T], *, purpose: str) -> T: ...
    def shuffle(self, items: Sequence[T], *, purpose: str) -> list[T]: ...
    def draws(self) -> list[RngDraw]: ...
```

Implementations:

- **`SeededRandomSource`** — drives a real game. Wraps a local `random.Random(seed)`
  instance (a *local* instance; the module-global `random` functions are banned). Records every
  draw it performs.
- **`ReplayRandomSource`** — drives a replay. Holds the recorded draw list from the log and
  returns them **in order**, asserting:
  - the `purpose` label matches the recorded one,
  - the `kind` matches,
  - the `args` match,
  - the draw list is exhausted exactly at the end of the action.
- **`NullRandomSource`** — raises on any draw. Used in tests to prove a code path is
  deterministic (e.g. a pure query helper that must not touch the RNG).

**Why label purposes rather than replaying a stream positionally.** A positional stream silently
desynchronises the moment anyone reorders two calls or inserts a new random call. The result is a
replay that produces a *different but plausible* game — the worst possible failure mode. Semantic
labels turn that into an immediate, localised error: *"action #47 draw #2: expected purpose
`random_selection`, got `deck_deal`."*

### 5.5 State

State is a game-specific, immutable dataclass. Core requirements:

- Frozen, `slots=True`, hashable-friendly.
- Contains **no floats**, no sets with nondeterministic iteration, no `datetime`, no UUIDs.
- Serialisable by `core.canonical.to_canonical_json` with a game-provided encoder.
- Contains the **god view**: every player's private state, any hidden ordering, everything. Hidden
  information is enforced at the projection boundary, not by hiding state from the engine.

### 5.6 Decision requests — the central abstraction

**A turn counter is not a sufficient primitive.** In a general multi-player game, decisions are
addressed to specific players, some are open simultaneously, and some belong to players who are out of
turn: a forced reaction to another player's move, a response to an offer, a mandatory choice triggered
by a global event. An engine modelled as "whose turn is it" cannot express these without special
cases, and those special cases are where rule bugs live.

The core models it directly:

```python
@dataclass(frozen=True, slots=True)
class DecisionRequest:
    request_id: str                  # "d17", counter-derived
    player: PlayerId
    kind: str                        # a kind declared by the game
    schema_ref: str                  # which action schema governs the response
    context: Mapping[str, JsonValue] # non-secret hints for renderers (never hidden information)
    phase: str                       # the phase this request belongs to
```

The core exposes `pending_decisions(state) -> list[DecisionRequest]`. There may be zero
(transitional), one, or several open at a time.

**Resolution order is declared by the game, not determined by arrival.** The game publishes a
deterministic priority over simultaneously-open requests so that a record produced by a multi-agent
runner is byte-identical to one produced sequentially. Seat order is the usual tie-break, but the
choice belongs to the game.

A phase ends when its request set is empty; the phase machine then advances (emitting a
`phase_started` event).

---

## 6. Determinism contract

This section is normative. Any violation is a bug, not a tradeoff.

1. **Randomness.** All randomness flows through an injected `RandomSource`. Importing
   `random` inside `lgbg/games/**` or `lgbg/core/**` (except `core/rng.py`) is a
   lint error.
2. **No floats in state.** All arithmetic is integer. If a computation is naturally fractional (e.g.
   discarding half of a holding), define the rounding explicitly as documented integer arithmetic.
3. **Canonical serialisation.** `to_canonical_json` uses
   `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)` over a
   game-provided normaliser that converts dataclasses/tuples/enums to plain JSON types. Every dict is
   emitted with sorted keys; every list has a defined, meaningful order.
4. **No `hash()`.** Python string hashing is salted per process (`PYTHONHASHSEED`). Use
   explicit `hashlib.sha256` on canonical bytes.
5. **No ambient time.** No `time`, `datetime`, or `uuid` inside the engine.
   Timestamps are attached by the *log writer*, outside the hashed record (§8.2).
6. **No set/dict iteration for ordered output.** Iterate sorted, or over an explicit list. A dict used
   as a lookup table is fine; a dict used as an ordered collection is not — use a list or
   `sorted()`.
7. **Frozen state.** Every state transition returns a new object. No in-place mutation, so a
   partially-applied action can never leak into the record.
8. **Atomicity.** `apply` either returns a complete new state or a `Rejection`. There is no
   "half-applied" outcome.

### 6.1 State hashing

```python
def hash_state(state: State, game: Game) -> str:
    blob = to_canonical_json(game.encode_state(state)).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:TRUNCATED_HASH_HEX_CHARS]
```

Hashes are recorded **after every action**, both for the pre-state and post-state, forming a hash
chain. The truncation width is a tunable constant; it must be wide enough to make collision-driven
false verification implausible and short enough to keep records readable.

---

## 7. The game plugin interface

A game plugin is a self-contained package implementing one game. The core knows nothing about any
game; everything game-specific — rules, structure, projection, notation, prompts, and the game's own
experimental-design characteristics — lives in the plugin.

### 7.1 Protocol

```python
class Game(Protocol):
    name: str                       # registry key
    rules_version: str              # bumped on any rule change
    schema_version: str             # bumped on any action/observation schema change

    # --- lifecycle ---
    def initial_state(self, cfg: GameConfig, rng: RandomSource) -> State: ...

    # --- decision surface ---
    def pending_decisions(self, state: State) -> list[DecisionRequest]: ...
    def legal_actions(self, state: State, player: PlayerId) -> list[Action]: ...
    def action_domains(self, state: State, player: PlayerId) -> list[ActionDomain]: ...

    # --- transitions ---
    def apply(self, state: State, action: Action, rng: RandomSource) -> ApplyResult: ...

    # --- observation ---
    def observe(self, state: State, player: PlayerId) -> Observation: ...
    def observe_spectator(self, state: State) -> Observation: ...

    # --- terminality and standing ---
    def is_terminal(self, state: State) -> bool: ...
    def outcome(self, state: State) -> Outcome: ...
    def standings(self, state: State) -> Mapping[PlayerId, int]: ...

    # --- serialisation and declared schemas ---
    def encode_state(self, state: State) -> JsonValue: ...
    def decode_state(self, blob: JsonValue) -> State: ...
    def action_schema(self) -> JsonSchema: ...
    def observation_schema(self) -> JsonSchema: ...
    def config_schema(self) -> JsonSchema: ...
    def rejection_codes(self) -> list[RejectionCode]: ...

    # --- declarations the platform needs and must not guess ---
    def benchmark_profile(self) -> BenchmarkProfile: ...
    def check_invariants(self, state: State) -> list[InvariantViolation]: ...
    def view(self) -> GameView | None: ...
```

`standings` is the current score of every seat in the god view. It exists so a replay can display a
scoreboard without re-deriving a scoring rule in a renderer, and it is pure like every other query.
It is not part of a player's projection: a player's view of the score remains `points`, which is
observer-relative and gated by the projection allow-list.

`config_schema` declares the game's own configuration options as JSON Schema, so an operator surface
can render and validate them without knowing the game. `view` is optional and is described in §7.12.

```python
class GameView(Protocol):
    schema_version: str

    def view_schema(self) -> JsonSchema: ...
    def scene(self, state: State) -> JsonValue: ...
```

```python
ApplyResult = Applied | Rejected

@dataclass(frozen=True, slots=True)
class Applied:
    state: State
    events: list[Event]

@dataclass(frozen=True, slots=True)
class Rejected:
    rejection: Rejection
```

A plugin implementation MUST be stateless: no instance state may survive across `apply` calls,
so that one plugin instance can drive many concurrent games.

### 7.2 Action domains — the L1 primitive

```python
@dataclass(frozen=True, slots=True)
class ActionDomain:
    type: str                                      # an action type declared by the game
    cost: Mapping[Component, int] | None           # declared cost, where the game has costs
    params: Mapping[str, ParamDomain]              # per-parameter permitted values

@dataclass(frozen=True, slots=True)
class ParamDomain:
    kind: str                                      # "enum" | "int_range" | "id_set"
    values: list[JsonValue] | None                 # for enum / id_set
    lo: int | None                                 # for int_range
    hi: int | None
```

`ActionDomain` is deliberately the **cross-product-free** description: "this action is available,
and here is the set of permitted values for each of its parameters" rather than an enumeration of
every resulting action. This is what L1 renders (§9).

### 7.3 Schemas as data

`action_schema()` returns a JSON Schema keyed by action type, describing parameters. This is the
contract that makes plug-and-play real:

- The engine uses it to validate incoming actions.
- The MCP adapter uses it to **generate** tool definitions — no hand-written tools per game.
- The prompt generator uses it to describe the action surface to a model.

If adding a game requires hand-writing tool definitions, the plugin system has failed.

### 7.4 Registration

**Decorator registry for in-repo games, entry points for external ones.**

```python
@register_game
class SomeGame(Game):
    name = "..."
    ...
```

Discovery order: (1) explicit import, (2)
`importlib.metadata.entry_points(group="lgbg.games")`. The registry is the only place the core
learns about games; `lgbg.core` must never `import lgbg.games`.

### 7.5 Spatial structure

Some games have a board; some do not. Where a game has spatial elements, the plugin MUST model them as
a derived structure rather than an authored one.

- Elements are defined in a **coordinate system meaningful to the game** — positions, cells, nodes,
  links, or whatever the game's geometry is.
- Adjacency and incidence are **derived** from those coordinates, never hand-authored. Hand-authored
  relational tables of even modest size are unverifiable and are a recurring source of silent rule
  errors.
- Public identifiers are integers assigned by a **canonical ordering** of the derived coordinates, so
  that identifiers are reproducible across implementations and stable across runs. Identifiers appear
  in recorded actions; changing the derivation invalidates every existing record.
- The plugin MUST expose a **structural self-check** asserting the game's geometric invariants —
  element counts, adjacency symmetry, classification of boundary versus interior elements, and any
  containment relations. It MUST run as a test.

This subsection exists because verifiability is a platform requirement, not because any particular
game has a board.

### 7.6 Initial configuration

A game's starting position may be fixed, generated, or a mixture of both.

- The plugin MUST accept a configuration selector that distinguishes curated fixed configurations
  from generated ones.
- Curated configurations MUST be stored as **data**, versioned alongside the plugin.
- Generated configurations MUST consume recorded RNG draws like any other randomness (§5.4).
- Fixed configurations are the default, because comparability across runs is the point of a
  benchmark; generated ones are opt-in for generalization testing.

### 7.7 Phase and decision structure

- A game MUST express its turn or round structure as a **phase machine whose phases produce decision
  requests**, not as ad-hoc control flow.
- Each phase MUST declare which players have open decisions and what closes the phase.
- Simultaneous decisions are the norm, not an exception: the decision queue (§5.6) is the primitive,
  not a turn index.
- The plugin MUST declare a deterministic **resolution order** over simultaneously open requests,
  and that order MUST be independent of arrival order.
- Every phase transition MUST emit an event.
- A phase in which several players decide concurrently **MUST NOT** be simulated as a sequence of
  private turns. Doing so changes what the players can observe about each other and therefore changes
  the game.

### 7.8 Hidden information and projection

The engine holds a god view of state (§5.5). Hidden information is enforced **only** at the
projection boundary.

- The projection MUST be built from an explicit **allow-list**. A field added to state MUST NOT appear
  in any projection unless it is explicitly added to that projection's allow-list. Deny-lists are
  forbidden: they fail open when state grows.
- Every hidden field MUST have a dedicated **leak test** asserting non-exposure to each player who
  should not see it.
- Information may be **asymmetric** rather than merely private: a fact may be known to one player and
  not to others. The projection API therefore takes the observer as a parameter rather than offering
  only "public" and "private" views.
- A game with no hidden information MUST still implement the projection interface, so the platform
  deals with one shape.
- `observe` MUST be pure and RNG-free.
- A **spectator projection** MUST exist and MUST be separately tested. It is a distinct artefact:
  in a game with hidden information, "who is currently ahead" is not fully determinable from any
  player's view, and the spectator view is what analysis and replays use.
- A presentation surface that shows a player's view MUST derive it from that player's projection.
  The god view MUST NOT be sent to a client and filtered there: a client-side filter is not a
  projection boundary, and the data has already left the server.

### 7.9 Rule authority, pinning, and versioning

- Every game MUST have a rules document identifying, for each rule that admits more than one reading,
  the interpretation implemented, **with a citation to the authoritative source**.
- Where the source is ambiguous, the document MUST record the chosen interpretation and the
  alternative considered.
- The document is written **before** rule implementation. An ambiguity resolved during implementation
  is resolved there once, not silently in code.
- Any change to a pinned rule bumps the game's `rules_version` and invalidates the golden record
  corpus by design (§15.3).

### 7.10 Benchmark profile

The platform cannot choose a valid experimental design without facts that differ per game and cannot
be inferred from code. The plugin MUST declare them:

| Fact | Why the platform needs it |
|---|---|
| **Positional asymmetry** | Where an earlier seat or position confers an advantage, seat assignment must be controlled or the result flatters whoever moves first. This axis exists in every game with more than one seat, including games whose starting position is otherwise fixed. |
| **Configuration variability** | Whether the starting position admits more than one arrangement. A game with a single starting position has nothing to vary, and a runner that assumed otherwise would demand a random draw the game cannot make. Seat assignment and starting configuration are independent axes, and a game may have either, both, or neither. |
| **Outcome shape** | Winner-take-all, ranked, or scored outcomes require different statistics. |
| **Stochasticity and variance class** | A high-variance game needs far more games per pairing for a usable signal than a deterministic one; run sizing depends on it. |
| **Interaction character** | Whether players are adversarial, cooperative, or mixed determines whether a shared score even means one thing. |
| **Decision-length distribution** | Typical and worst-case decision counts set context budgets and cost expectations. |

Hardcoding these in the runner would make the runner game-specific, violating the layering (§4). They
are declarations from the plugin, consumed by the runner.

### 7.11 Game-declared invariants

Rules engines are governed by conservation laws — components, supply, resources, or scores that must
balance across every transition. These laws are game-specific, but *checking* them is not.

The plugin MUST declare its invariants via `check_invariants(state)`, returning a list of
violations. This is what lets one generic fuzzing harness (§15.4) validate every game, including games
that do not yet exist, without the harness knowing anything about them.

### 7.12 Declarations the operator console needs

A console that sets up a run and draws a replay must not learn a game's options or geometry by being
written for that game. Three declarations keep it game-agnostic.

**Configuration.** `config_schema()` returns a JSON Schema for the options the game reads from
`GameConfig`. The core carries those options opaquely (P11); the console uses the schema only to
render a form and to validate an operator's declaration. One validator serves the console and the
CLI.

**Standings.** `standings(state)` returns the current score of every seat in the god view. It is
pure, and it exists so a replay's scoreboard is the game's own arithmetic rather than a second
implementation in a renderer. A player's own view of the score remains the observer-relative
`points` field (§7.8).

**View.** `view()` returns an optional `GameView`. A game without one is still fully replayable
textually; a game with one declares the static geometry a graphical replay needs:

- `scene(state)` is a pure function of the initial state. It is keyed by the **same canonical
  identifiers** that appear in recorded actions and observations, so a drawn vertex, edge or cell is
  the one an action names.
- The geometry is **derived** from the game's coordinate system, never an authored table (§7.5).
- Coordinates are integers in a fixed view box. The scene is serialised with the same canonical
  rules as everything else (§6.3); a float in a scene is a defect.
- A scene contains only public structure. Hidden facts belong to a projection, never to geometry.
- `view_schema()` declares the scene's shape and `schema_version` versions the presentation
  contract, independently of the action schema.

A frame is **not** a second state model: the console serves the spectator projection for a god view
and the player projection for a seat view. The view supplies static geometry and `standings()`
supplies the scoreboard; neither supplies a rendered board on the engine's behalf, and neither
decides a rule.

The console MUST validate a scene against `view_schema()`, MUST test that every identifier an
observation can reference is present in the scene, and MUST refuse to draw a record whose
`rules_version` or `schema_version` the installed plugin does not match. A game with no view is
listed and readable as text; absence of a renderer is not an error.

---

## 8. Logging and event sourcing

### 8.1 Why event sourcing rather than logs

A log is a transcript; an event-sourced record is a *program*. The difference buys:

- **Verifiable replay** — the hash chain proves the reconstruction is correct, not merely plausible.
- **Resumption** — start a new game from any historical state.
- **Counterfactual analysis** — "same game, same seed, same initial configuration, different model in
  seat 2."
- **Regression corpus** — recorded games become fixtures; a refactor that changes a hash is caught.
- **Derived metrics** — every metric is a fold over events, computed post hoc, never instrumented
  into the engine.

### 8.2 File layout

```
runs/<run_id>/
  run.json                    experiment manifest: declaration and plan, written before play
  results.json                outcome aggregates, written when the run ends
  <game_id>/                  one directory per game: the portable unit
    game.json                 the game's own manifest: design point, seat map, versions
    games/
      <game_id>.god.jsonl     deterministic core record — the thing hashed and replayed
      <game_id>.meta.jsonl    sidecar: timestamps, wall-clock, agent payloads, costs
```

Splitting the deterministic record from the sidecar is what keeps P9 honest: nothing
non-deterministic can enter the hash chain by accident, because it is physically in another file.

The root manifest is written before the first action, so a run that crashes half-way still records
what it intended to play. `results.json` is written only when the run ends; its absence is a fact
about the run, not an error. The per-game directory is the portable unit: it carries everything
needed to replay one game without the rest of the run. No derived presentation state is stored
anywhere.

### 8.3 Record schemas

Field values below are illustrative; the shapes are normative.

**Header (line 0 of the god log):**

```json
{"t":"header","schema":"lgbg.game.v1","engine_version":"<version>",
 "game":"<name>","rules_version":"<name>-rules-1","schema_version":"<name>-actions-1",
 "game_id":"g-0001","players":4,
 "config":{"board":"fixed:default_a","seed":123456789,"assist":"L1","rejection_detail":"standard",
           "interaction_protocol":"decline_only"},
 "prompt_hashes":{},
 "initial_state_hash":"0000000000000000"}
```

**Action record (one line per attempt, successful or not):**

```json
{"t":"action","seq":47,"request_id":"d91","player":2,
 "action":{"type":"place_piece","params":{"site":17}},
 "result":{"ok":true},
 "state_hash_prev":"a1b2c3d4e5f60718",
 "state_hash":"9f8e7d6c5b4a3210",
 "rng":[{"purpose":"random_selection","kind":"choice","args":{"n":2},"value":1}],
 "events":[{"type":"piece_placed","payload":{"player":2,"site":17}},
           {"type":"components_spent","payload":{"player":2,"component":"a","count":1}}]}
```

```json
{"t":"action","seq":48,"request_id":"d92","player":3,
 "action":{"type":"place_piece","params":{"site":5}},
 "result":{"ok":false,"error":"INSUFFICIENT_COMPONENTS",
           "details":{"requires":{"a":3,"b":2},"you_have":{"a":1,"b":2}}},
 "state_hash_prev":"9f8e7d6c5b4a3210","state_hash":"9f8e7d6c5b4a3210",
 "rng":[],"events":[]}
```

Note that a rejected action **does not change the state hash** — a cheap and powerful invariant,
asserted on every logged rejection.

**Terminal record:**

```json
{"t":"terminal","seq":412,"winner":1,
 "final_scores":{"0":7,"1":10,"2":6,"3":8},
 "rounds":37,"total_actions":412,"rejections":9,
 "state_hash":"..."}
```

### 8.4 Record types

| `t` | Meaning |
|---|---|
| `header` | Once, first line. |
| `action` | Every attempt, accepted or rejected. |
| `phase` | Phase transitions (redundant with events, but useful for tooling). |
| `terminal` | Once, last line. |

Phase transitions are technically derivable from events, but logging them makes records greppable and
replay debugging far easier. Redundancy that is *verified* during replay is fine.

The runtime owns these record types. A game MUST NOT add record types; game-specific narrative belongs
in events.

---

## 9. Assist levels

This is the single most important benchmark-validity knob in the system.

### 9.1 The problem

If the engine enumerates every legal move every turn, the model's task collapses from *planning* to
*classification* — "pick one of these twelve." That may be a legitimate benchmark, but it is a
**different** benchmark. If we do not decide deliberately, we get it by accident and never know which
one we measured.

### 9.2 The levels

| Level | Enumeration | Rendering | Rejection detail |
|---|---|---|---|
| **L0** | None. The model must construct the action from rules plus observation. | Raw observation only. | Minimal: `{"ok":false,"error":"INSUFFICIENT_COMPONENTS"}`. No repair hints. |
| **L1** *(default)* | Action **types** plus parameter domains (`ActionDomain`). | Types, costs, and permitted parameter sets. | Standard: error plus what was required versus what was held. No full alternative list. |
| **L2** | Full enumerated legal action list. | Every legal `Action`, optionally annotated. | Full: includes `legal_alternatives`. |

### 9.3 The invariant that keeps this honest

> **Assist level affects only what is *rendered and returned*. It never affects what is *legal*, and
> it never affects the engine's validation path.**

`apply()` is byte-identical at all three levels: it has no notion of assist level. Every level
produces the same state, the same events, and the same hash for the same action sequence. Assist level
lives in the *renderer* and in the *rejection formatter*, both of which sit outside the hashed core.

This makes assist level a clean experimental variable: one recorded game can be re-rendered at a
different level, and the underlying game is provably the same.

### 9.4 Coherence across channels

At L0, a rejection must **not** include `legal_alternatives` — otherwise a model can recover full
enumeration by brute-forcing illegal actions and reading the error messages, quietly promoting itself
from L0 to L2. The rejection-detail tier is therefore tied to the assist level by default, with an
explicit `rejection_detail` override in `RunConfig` for experiments that want to decouple
them (e.g. "L1 enumeration, minimal errors" — a genuinely interesting condition).

---

## 10. Error model

```python
@dataclass(frozen=True, slots=True)
class Rejection:
    code: RejectionCode
    message: str
    details: Mapping[str, JsonValue]   # filtered by rejection_detail tier before rendering
```

Codes are split into two sets.

### 10.1 Core codes — owned by the runtime

These describe lifecycle and protocol conditions that exist independently of any game:

```
NOT_YOUR_DECISION        the action names a player with no open decision
NO_SUCH_REQUEST          the referenced decision request is not open
WRONG_PHASE              the action is not valid in the current phase
GAME_OVER                the game has already terminated
UNKNOWN_ACTION           the action type is not declared by the game's schema
BAD_PARAMS               the action's parameters do not validate against the schema
SCHEMA_VERSION_MISMATCH  the game schema and the record disagree
```

### 10.2 Game codes — declared by the plugin

Every other condition is game-specific and MUST be declared by the plugin via
`rejection_codes()`. The categories a game typically declares:

- insufficient components or resources to perform the action
- an unavailable or occupied target
- an unmet structural or adjacency constraint
- an exhausted supply of a limited component
- a component that exists but is not playable in the current phase
- an invalid exchange ratio or an unavailable exchange route

Declaring them matters architecturally: the runtime and the metrics layer can **enumerate** rejection
codes without knowing the game, which makes rejection-code distribution a game-agnostic metric.

### 10.3 Rules of the model

- **Every rejection is an event.** Logged with the same envelope as a success, with an unchanged state
  hash.
- **`details` is structured, never prose-only.** Field names such as `requires`,
  `you_have`, and `legal_alternatives` are machine-readable so metrics can be computed
  without parsing text.
- **`details` is filtered by the rejection-detail tier** before it reaches a player (§9.4). The
  full details are always in the record; the *renderer* decides what the player sees.
- **Rejections are not exceptions.** `apply` returns `Rejected`; exceptions are reserved for
  engine bugs. A fuzzer that hits an exception has found a defect.

---

## 11. Prompt layer

Prompts live with the game, because rules and notation are game-specific.

```
games/<game>/prompts/
  game.md      rules, notation, action semantics, worked examples
```

Provider-policy prompts (`system.md`, `policy.md`) live in `agents/` — they are
provider policy, not game-specific. Rules:

1. **The game prompt contains no strategy advice.** Only rules, notation, and action semantics.
   Otherwise the benchmark measures prompt engineering rather than the model.
2. **The game prompt is versioned and hashed.** The hash is stored in the game header record. A result
   without a prompt hash is unreproducible.
3. **Notation is defined once and shared.** The game's `notation.py` is the single renderer;
   prompt generation, the CLI, and the MCP resources all use it. Divergent renderings across surfaces
   would confound results.
4. **Renderings have a detail level.** Full, compact, and delta-only renderings are all required,
   because how the state is rendered measurably changes model performance. Holding rendering constant
   across models is a benchmark requirement, not a nicety.

---

## 12. Execution surfaces

### 12.1 Why MCP is a frontend, not the architecture

If the MCP server held game state, we would get: state hidden behind tool calls, one process per
agent, schema mangling, and no path to running many games in parallel. Instead:

```
core engine → canonical HTTP/JSON API → { MCP stdio bridge, MCP HTTP, CLI, python client, replay tool }

records (runs/) → console read model → browser client
```

The MCP layer is a thin, stateless translator in front of the same authority every other client uses.

The console is a **second kind of frontend**: it reads completed records and the game's declarations,
not live sessions. It never binds to the live host, and the live host never depends on it.

### 12.2 Resources for reading, tools for acting

**Use MCP *resources* for observation and *tools* for actions.** A resource URI such as
`<game>://games/{id}/state?player=2` is a read of the world; an action tool such as
`place_piece` is an intent. Modelling reads as tools burns tokens and muddies the model's notion
of side effects.

Tool and resource definitions are **generated** from `action_schema()` and
`observation_schema()` (§7.3). No per-game adapter code exists.

### 12.3 Server profiles

| Profile | Surface | Use |
|---|---|---|
| *Benchmark* | Curated read/act tools only. The runner owns game creation. | Scored runs. A model must not be able to spawn games. |
| *Sandbox* | Adds lifecycle tools (`create_game`, `join`, `list_games`). | Exploration and manual play. |

### 12.4 The operator console and the replay viewer

A human needs two things the CLI does not give: a way to declare an experiment without hand-editing
JSON, and a way to **see** a game that has already been played. They are one post-hoc surface — the
console — with two halves.

```
config declaration ──validate──> cli run ──> run directory ──read+replay──> browser
        ^                                      (run.json, results.json,
     operator form                            <game_id>/{game.json, games/*.god.jsonl})
```

Rules:

- **The console is read-only over records.** It reads `run.json`, `results.json`, `game.json`, the
  god log and the sidecar. It never writes a record, never edits a prompt, and never synthesises a
  terminal state. The only thing it produces is a configuration file it hands to the runner and the
  run directory the runner writes.
- **Execution is not reimplemented.** The console launches the existing `run` entry point as a
  separate process with a configuration file. It does not import the runner into its own request
  path, and killing the console does not kill a run. There is one execution path for the CLI, the
  tests and the console.
- **No live graphical game surface exists.** During a run the console may show counts and status
  derived from the files; it may not show the board, a decision, or a projection of a game still in
  flight. A live board invites live hints, live intervention, and a second assist surface — and then
  the GUI is part of what is being measured.
- **A seat view is a projection, not a filter.** The console asks the engine for the observer's
  observation and the game's own `render`. It never sends the god view to the browser and hides
  fields there (§7.8). The god view is a separate, explicitly labelled spectator mode; raw records
  and other seats' decision transcripts are not available through a seat's view.
- **One shell, one renderer per game.** Navigation, configuration, replay controls, verification
  and decision inspection are game-agnostic. A game declares its geometry (§7.12) and provides a
  drawing component; adding a game does not touch the shell.
- **Compatibility is checked before drawing.** A record is drawn only when the installed plugin's
  `rules_version` and `schema_version` match the header. A mismatch is reported, not rendered; a
  successful replay is the proof that the reconstruction is exact.
- **Local by default, scoped to declared roots.** The console binds to loopback, reads only under
  roots the operator named, and refuses a path outside them. Model and prompt text is untrusted
  content and is rendered as text, never as markup.
- **The record remains the evidence.** A screenshot, a permalink, or a rendered frame is a view of a
  record; it is never a substitute for the record. The console persists no derived state, so every
  frame can be recomputed from the artefacts alone.

The CLI, the runner and the tests MUST work with the console absent. The console is a reader and an
operator convenience, not a runtime dependency of the benchmark.

---

## 13. Agent layer constraints

The agent layer's job is to be **boring and invisible**: it should contribute nothing to the measured
outcome beyond relaying the model's decisions.

> **The agent framework must not do anything helpful that is not logged and constant across models.**

Auto-retry on tool error, context summarisation, system-prompt injection, "let me re-read the state for
you" — each is a confound that varies per framework and silently becomes the thing being measured. Any
such behaviour must be an explicit policy in `RunConfig`, recorded in the run manifest, and
applied identically to every model in a comparison.

The provider abstraction is deliberately narrow:

```python
LLMProvider.complete(messages, tools, config) -> { text, tool_calls, usage }
```

plus one provider-agnostic tool loop. Real-world variation to accommodate without leaking into
measurement: models without native tool calling, reasoning models that hide chain of thought, context
limits on long games, and providers that ignore a requested seed.

---

## 14. Measurement layer

Metrics are computed from the game record, never instrumented into the engine (§3).

| Category | Metrics |
|---|---|
| Outcome | win rate, place distribution, Elo / Bradley-Terry over multi-player games |
| Legality | illegal-move rate, attempts per decision, rejection-code distribution |
| Cost | tokens and monetary cost per decision and per game, decision latency |
| Quality | blunder rate against a heuristic oracle, long-horizon coherence (does the agent execute a plan across turns or oscillate) |

Experimental design is driven by the game's declared benchmark profile (§7.10), because the governing
facts differ per game:

- **Positional asymmetry.** Where an earlier seat or position confers an advantage, pairings must be
  mirrored — same seed and initial configuration, models swapped across seats. Unmirrored pairings
  silently flatter whoever moves first.
- **Variance and outcome shape.** A high-variance, winner-take-all game requires far more games per
  pairing than a deterministic or finely-scored one before the signal is usable. The runner sizes a
  run from the declared profile rather than from a hardcoded constant.

Cheap, non-scored drivers are what make this calibration affordable before API budget is committed.

---

## 15. Testing strategy

### 15.1 Unit and structural tests

- **Structural invariants.** The plugin's self-check (§7.5) runs as a test: element counts, adjacency
  symmetry, boundary classification, containment. Run at import under test.
- **Rule tests.** One test per pinned rule (§7.9), concentrating on the rules the rules document
  identified as ambiguous. Every ambiguity resolved in that document gets an explicit test asserting
  the chosen interpretation.
- **Projection tests.** Golden assertions that each player's view contains what it should and,
  critically, **does not contain** hidden data. One leak test per hidden field, per observer. A
  projection built from an allow-list (§7.8) is what makes this testable at all.

### 15.2 Determinism tests

- Same seed plus same action sequence ⇒ identical hash chain, across separate processes (guards
  against `PYTHONHASHSEED` leakage).
- `NullRandomSource` on all pure query paths.

### 15.3 Replay tests

- Every game in the fixture corpus replays and hash-verifies.
- **Golden games.** Recorded games committed as fixtures. Any change to a hash is a deliberate,
  reviewed event that requires bumping `rules_version`.
- **Tamper detection.** Tests that mutate a record, a draw, or a hash, and assert replay fails with a
  *localised* error naming the offending sequence number.

### 15.4 Fuzzing — the generic conformance harness

A random-legal driver exercises long action sequences from many seeds. Because a game declares its own
invariants (§7.11), one harness validates every game. Asserted after **every** action:

- No exception (exceptions are defects, not outcomes).
- **Game-declared invariants** hold — via `check_invariants`. For a game with components and
  supplies this means conservation: nothing is created or destroyed outside a rule that says so.
- **Event sufficiency:** applying the returned events to the pre-state reproduces the post-state.
- **Rejection invariance:** a rejected action leaves the hash unchanged.
- **Projection purity:** `observe` does not consume RNG and does not mutate state.
- **Schema conformance:** every action produced during a game validates against `action_schema()`,
  so schema and implementation cannot drift.
- **Termination:** every game reaches a terminal state within a bounded number of actions, or is
  reported as a livelock bug.

The driver is a test harness, not a competitor: it is never scored and never appears in a result.

### 15.5 Presentation tests

The console is derived, so its tests are about fidelity to the record, not about pixels:

- **Every golden game opens.** For each record in the corpus, the replay read model produces the
  same states as `replay()`, and the timeline is aligned one-to-one with the action records,
  rejections included.
- **Scene contract.** Every declared view validates against `view_schema()`, every identifier an
  observation can reference exists in the scene, and no coordinate is a float.
- **Seat-mode leaks.** For every hidden field and every seat, the seat-mode payload contains no
  hidden data, no other seat's decision transcript, and no god-view event. The existing leak matrix
  is reused where it already states the rule.
- **Version and integrity.** A record whose `rules_version` or `schema_version` does not match is
  refused with a stated reason; a tampered record fails at a localised seq rather than drawing a
  plausible game.
- **Run artefacts.** Discovery reads exactly the declared layout; the root manifest exists before
  the first game; a run without `results.json` is reported as unfinished, and an abandoned game is
  never given a terminal state.
- **One operator validator.** The console's validation and the CLI's validation accept and reject
  the same declarations, with the same messages, and a saved declaration round-trips.
- **Generic shell.** A test-only second game view proves the shell, the reader and the API contain no
  Catan branch; a scan refuses a game name in the generic console modules.
- **Local safety.** Path traversal, a symlink escape, and a root outside the declared roots are
  refused; model and prompt text is escaped rather than rendered as markup.
- **Frontend.** Pure layout and frame-selection functions are unit-tested. A browser smoke test is
  optional and never part of the offline Python gate.

---

## 16. Architectural decisions

| Decision | Choice | Rationale |
|---|---|---|
| Engine shape | Pure function over immutable state | P1; makes replay and fuzzing tractable |
| Concurrency model | Decision-request queue, not a turn counter | Out-of-turn and simultaneous decisions are general, not exceptional (§5.6) |
| Randomness | Seeded, every draw recorded with a semantic label | Detects divergence that a positional stream hides (§5.4) |
| Log integrity | SHA-256 state hash on every action, pre and post | Turns "replay works" into a verifiable claim (§6.1) |
| Rejected actions | Logged as first-class records, hash unchanged | Makes illegal-move rate measurable (P4) |
| Hidden information | Enforced at the projection boundary only, by allow-list | Keeps engine state simple, replay exact, and leaks fail closed (§7.8) |
| Assist levels | L0 / L1 / L2; default L1; tunable per run | Controls whether we measure planning or classification (§9) |
| Player interaction | Structured actions only, protocol declared per game | Reproducibility; free text is unparseable and collusion-prone (§3) |
| Schemas | Declared as data by the plugin | Enables generated tools and prompts (§7.3) |
| Spatial structure | Derived from coordinates, never authored | Eliminates an unverifiable class of bugs (§7.5) |
| Benchmark facts | Declared by the plugin, not assumed by the runner | P11; keeps the runner game-agnostic (§7.10) |
| Invariants | Declared by the plugin, checked by a generic harness | One harness validates every game, present and future (§7.11) |
| Rejection codes | Core set owned by the runtime; the rest declared by the plugin | Makes rejection metrics game-agnostic (§10) |
| MCP | Frontend over a canonical HTTP API | Avoids per-agent state and enables parallel runs (§12.1) |
| Presentation | Read-only console over records; setup declares, never executes | Keeps the GUI off the measurement path; replay is the only reconstruction (P12, §12.4) |
| Game view | Optional static geometry declared by the plugin, keyed by canonical ids | The client cannot invent a board or compute a game fact (§7.12) |
| Replay scoreboard | `standings()` declared by the plugin | The score is the game's arithmetic, not a renderer's second implementation (§7.12) |
| Operator configuration | One declared schema and one validator for CLI and console | A form with its own rules would be a second truth (§7.12) |
| Run artefacts | Root experiment manifest plus nested per-game directory | The plan is recorded before play; one game directory is portable (§8.2) |
| Metrics | Folds over the event log | Keeps the engine pure; metrics recomputable retroactively (§14) |

---

## 17. Open architectural questions

1. **Spatial identifier scheme.** The canonical coordinate-to-identifier derivation must be frozen
   before records exist. Identifiers appear in every recorded action, so changing the derivation
   invalidates every existing record.
2. **Curated initial configurations.** How many fixed configurations per game, and chosen for what
   property — balance, positional fairness, or strategic variety? The answer may differ per game and
   is likely a per-game decision recorded in that game's rules document.
3. **Hash width.** A truncated digest is assumed. Revisit if collision risk ever becomes material.
4. **Interaction protocol depth.** A plugin may offer more than one interaction protocol of differing
   expressiveness. Whether a richer protocol materially changes what is measured is an empirical
   question, and protocols are declared per game (§7.7).
5. **Game-interface stability.** The plugin interface is expected to change when a second game is
   implemented. That change is a planned, versioned architectural revision, not a defect. The
   operator-facing declarations of §7.12 are the first such extension.
6. **Benchmark profile form.** Whether the profile should be declarative data or computed by plugin
   code. Declarative is more inspectable; computed allows per-configuration variation.
7. **Third-party renderers.** A plugin may declare geometry, but the browser component that draws a
   game is currently in-repo. Whether an external plugin may ship a renderer, and under what trust
   and loading model, is unresolved; until it is, an external game is replayable as text.
8. **Static replay export.** A self-contained bundle that opens a recorded game without a server
   would suit a published result. It is deferred, and the console API is kept data-driven so it
   remains possible.
9. **Historical presentation.** A record is replayable while its `rules_version` matches an installed
   plugin. How many historical rules versions to retain, so that old records remain viewable, is a
   policy question for the benchmark archive rather than an engine question.
