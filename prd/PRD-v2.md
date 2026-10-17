# PRD-v2 — Model Play: the MCP Surface, the Agent Layer, and the Runner

| Field | Value |
|---|---|
| **Document** | PRD-v2 |
| **Release** | v2 |
| **Status** | Draft — awaiting approval |
| **Depends on** | `ARCHITECTURE.md` (architecture), `prd/PRD-v1.md` (delivered engine), `ACCEPTANCE-v1.md` (what v1 actually is) |
| **Game plugin** | `catan`, base game, 4 players — unchanged: `rules_version = catan-rules-6`, `schema_version = catan-actions-1` |
| **Supersedes** | — |
| **Deliverable type** | Library + service (HTTP host, MCP server) + CLI |

---

## 1. Summary

v1 delivered a game engine whose records cannot lie. v2 delivers the thing those records exist for:
**a language model playing the game.**

This release adds four layers on top of the v1 engine — a session facade, an HTTP/MCP surface, a
provider-agnostic agent layer, and a runner — and produces the first real measurement artefacts: run
directories containing complete, replayable games played by models, with every prompt, every
response, every token and every cost recorded.

It deliberately does **not** produce statistics. v2 answers *"what happened in these games?"* v3
answers *"what does that mean?"*

---

## 2. Background

### 2.1 What v1 handed us

v1 is complete and accepted (`ACCEPTANCE-v1.md`). The relevant facts, because v2 is built directly
on them:

| Asset | State |
|---|---|
| Engine | 0.1.0, Catan base 4-player, 917 tests, gate green (ruff, ruff format, mypy --strict, pytest) |
| Records | 7 golden games verified end to end, hash-chained, sidecar split |
| Determinism | Proven across `PYTHONHASHSEED`; ambient randomness fails the lint gate |
| Assist levels | L0/L1/L2 implemented, **byte-identical god logs** proven (SC-8) |
| Tool definitions | `lgbg/core/tools.py` already emits MCP-shaped `{name, description, inputSchema}` |
| Notation | `Game.render(observation, detail=...)` plus a delta renderer |
| Decision surface | `pending_decisions`, `legal_actions`, `action_domains`, `render_decision` |
| Declarations | `benchmark_profile()`, `rejection_codes()`, `check_invariants()` all present |
| Prompts | `prompts/game.md` written, hashed, no strategy advice |
| Dependencies | **zero** runtime third-party dependencies in `lgbg/core` and `lgbg/games` |

Four deviations were accepted at v1 (`ACCEPTANCE-v1.md`). Three of them do not affect v2. The
fourth matters: **NFR-2's 50 ms per game was missed by roughly nineteen times.** That is not a v2
blocker — once a model is in the loop, engine time is noise against inference latency — but it fixes
where v2's performance budget must actually go (§9).

### 2.2 The gap this release closes

The v1 engine can already tell you whether a game *record* is trustworthy. It cannot yet produce a
game played by a model, and it cannot yet tell you what that model did or what it cost.

### 2.3 The risk this release must manage

> **The harness is the most likely thing to end up being measured.**

Connecting a model to a game is a weekend of work. Making the result *attributable to the model* is
not, because every convenience added along the way — a retry, a context summary, a repaired tool
call, a helpful reminder of the rules — is a policy that interacts with the model and silently
becomes part of the finding. v1 enforced "the framework must do nothing helpful that is not logged
and constant across models" for a scripted player; v2 is where that rule acquires teeth, because now
there is a framework.

---

## 3. Goals

| # | Goal |
|---|---|
| G1 | A language model can play a complete game of Catan end to end, and the resulting record verifies and replays exactly as a scripted one does. |
| G2 | The agent surface changes **nothing** about the game: the same actions produce the same god log whether they arrive from a model, a script, or a human. |
| G3 | Any model can be plugged in behind one narrow interface, and models that behave badly are handled by declared, logged policy rather than by improvisation. |
| G4 | A run is auditable from its directory alone: every prompt, response, token, cost, and failure is recoverable months later. |
| G5 | Results are interpretable, which means a non-LLM reference player exists to compare against. |
| G6 | The whole thing is observable by a human before it is ever pointed at a model. |

---

## 4. Non-goals

| Out of scope | Note |
|---|---|
| **Statistics**: Elo, Bradley-Terry, confidence intervals, sample-size planning | PRD-v3. v2 emits *facts* per run; v3 draws *inferences* across runs. |
| **Leaderboards, dashboards, reports, a web UI** | PRD-v3. |
| **A second game plugin** | PRD-v3, deliberately: it is the true test of the v1 plugin boundary, and it should not be confounded with the agent layer landing. |
| Free-text negotiation between models | Permanently out of scope (`ARCHITECTURE.md` §3). Trading stays structured. |
| Self-play optimisation, fine-tuning, model training | — |
| Long-term agent memory across games | Each game starts clean. Memory is an experimental variable, not infrastructure. |
| Multi-process distributed execution | Single machine, single process pool. Parallelism within a run, not across machines. |
| Human play UI | The MCP **sandbox** profile is the human-facing surface, and it is a CLI client, not a UI. |
| Closing v1's accepted deviations | They stay accepted. Q5 in §15.1 settles the one that could have blocked a card. |

---

## 5. Success criteria

Each is binary and maps to an automated check in §12.

| # | Criterion |
|---|---|
| SC-1 | A complete 4-player game played by four LLM agents (mock provider in CI) produces a god log that verifies, replays to every intermediate state, and whose final hash matches a re-run from the recorded actions. |
| SC-2 | **Surface equivalence:** the same action sequence delivered through the MCP server, through the HTTP API, and in-process produces byte-identical god logs. |
| SC-3 | **Assist equivalence through the agent surface:** the same run at L0, L1 and L2 produces byte-identical god logs apart from the header's `assist` field. This must hold for a *model-driven* run, not only a scripted one. |
| SC-4 | A run directory alone is sufficient to reconstruct every model interaction: for every decision, the exact request messages, the exact response, the tool calls made, and the usage reported. |
| SC-5 | A prompt or policy file that changes without its hash changing the manifest is impossible: the run manifest's hashes are recomputed at the start of every game and a mismatch aborts the run. |
| SC-6 | An MCP client with no knowledge of Catan — driving only from `tools/list` and the exposed resources — plays a legal opening placement. No game-specific code exists in that client. |
| SC-7 | **Experiment design is declared and recorded.** Every game records its replicate index, rotation index, seat assignment and initial configuration; a four-seat rotated design with five replicates yields twenty games, in which each agent occupies every seat index equally often. |
| SC-8 | Two non-LLM reference players (random-legal and greedy-heuristic) complete full games and are never reported as scored participants. |
| SC-9 | Provider conformance: the OpenRouter adapter and the mock pass one shared conformance suite, covering both a model with native tool calling and one without. |
| SC-10 | Malformed behaviour is handled and logged, not fatal: a model that emits no action, an unparseable tool call, or a runaway loop is recorded with its failure kind and resolved by declared policy. No run can hang. |
| SC-11 | The gate stays green, and `lgbg/core` and `lgbg/games` still have **zero** third-party runtime dependencies. |
| SC-12 | A run of **≥ 50 games on the mock provider** completes unattended in CI — deliberately including every failing behaviour — and produces `results.json` with per-game and per-seat accounting: outcome, actions, rejections, tokens, cost, latency, failures, abandonments. |
| SC-13 | Every functional requirement in §8 is traced to at least one named test. |
| SC-14 | A human can play a full game by hand against the engine through the MCP sandbox profile, using only published tool and resource definitions. |
| SC-15 | An illegal action produces a **redo turn** carrying the single shared redo prompt under a retry budget identical for every model; if the budget is exhausted the game is recorded as **abandoned**, distinguishable from a completed game, and excluded from outcome aggregates. |
| SC-16 | A demonstration run against a real provider completes unattended until its **declared budget** is exhausted, and reports what that budget bought: games played, decisions taken, tokens, cost, and abandonment rate. The number of games is an outcome of the budget, not an input. |

---

## 6. Users and consumers

| Consumer | Uses |
|---|---|
| **The researcher** | Runs configurations, reads `results.json`, drills into a specific decision that looked wrong. |
| **A result reviewer** | Replays a published run's games and verifies its hashes without re-running any model. |
| **PRD-v3 implementers** | Consume the run directory format and `results.json` as their input. |
| **A future game-plugin author** | Confirms the MCP surface needs no per-game adapter code (SC-6). |

---

## 7. Deliverables

| ID | Deliverable |
|---|---|
| D1 | `lgbg/host/` — the session facade, the HTTP/JSON API, the session registry. |
| D2 | `lgbg/adapters/mcp/` — MCP server: stdio and HTTP transports, generated tools, observation resources, benchmark and sandbox profiles. |
| D3 | `lgbg/agents/` — provider abstraction, adapters, the tool loop, prompt assembly, failure policy, context policy, cost accounting. |
| D4 | `lgbg/runner/` — seat assignment, the experiment-design matrix, concurrent decision dispatch, run manifest, `results.json`. |
| D5 | Reference players: random-legal and greedy-heuristic. |
| D6 | CLI additions: `serve`, `run`, `play-live`, `inspect-run`. |
| D7 | A mock provider and a provider conformance suite. |
| D8 | Test suite: surface equivalence, assist equivalence, failure policy, provider conformance. |
| D9 | Documentation: how to add a provider, how to read a run directory. |

---

## 8. Functional requirements

### 8.1 The session facade — one authority

- **FR-1.1** There MUST be exactly one component that owns mutable game state: the **session facade**
  in `lgbg/host`. Every surface — MCP, HTTP, runner, CLI — acts through it.
- **FR-1.2** The facade MUST expose the operations the v1 engine already declares, and MUST NOT add
  game-specific operations: create session, read projection, read pending decisions, submit action,
  read decision surface at the configured assist level, read outcome.
- **FR-1.3** The runner MUST drive games through the facade, in-process, with no network hop. The MCP
  server MUST be able to bind to the same facade in-process OR proxy to it over HTTP.
- **FR-1.4** In-process, HTTP and MCP paths MUST produce byte-identical god logs for identical action
  sequences (SC-2). This is the single test that keeps the surfaces from drifting apart.
- **FR-1.5** The facade MUST be safe for concurrent access: several sessions may advance in parallel,
  and one session may have several open decisions being answered at once.
- **FR-1.6** The facade MUST reject any action whose player has no open decision, with the v1 core
  code, rather than accepting it into a queue.

> **Design note.** `ARCHITECTURE.md` §12.1 says MCP is a frontend over a canonical HTTP API. v2
> implements the *intent* — one authority, many transports — while allowing the common single-process
> case to skip the network hop. HTTP remains the transport when processes are actually separate. This
> is a refinement of the letter of §12.1, and it is recorded as such.

### 8.2 HTTP host

- **FR-2.1** The host MUST expose a JSON API over the facade: create a session, read state, read the
  decision surface, submit an action, read the outcome.
- **FR-2.2** Every response MUST be JSON and MUST be stable under a documented schema version.
- **FR-2.3** Transport-level failures MUST be distinguishable from game-level rejections: an illegal
  move is a 200 with a rejection body, not an HTTP error.
- **FR-2.4** The host MUST carry a session registry that assigns and validates `game_id`, so two
  clients cannot act on the same session under different assumptions.
- **FR-2.5** The host MUST NOT be a requirement for running a benchmark: the runner's in-process path
  MUST work with no server started.
- **FR-2.6** The host MUST NOT expose a surface that lets a player read another player's projection.
- **FR-2.7** The host MUST be an **ASGI** application. Routing MUST be written directly against the
  ASGI interface for the handful of endpoints the host serves; a web framework MUST NOT be added
  without a concrete need the interface does not meet. An ASGI server is the one transport dependency
  this buys (FR-16.2).

### 8.3 MCP server

- **FR-3.1** The MCP server MUST expose **tools for actions** and **resources for observation**,
  per `ARCHITECTURE.md` §12.2.
- **FR-3.2** Tool definitions MUST be generated by the v1 function that already exists,
  `lgbg.core.tools.tool_definitions`, with no per-game code (SC-6).
- **FR-3.3** The tool set MUST be **constant across assist levels**. Assist level gates what the
  *resources* reveal and what a rejection explains — never which actions appear to exist.
- **FR-3.4** The server MUST offer two profiles, and the profile MUST be fixed when the server is
  **constructed** — not switchable per request, and not a value read from a request:
  - **benchmark**: curated read/act tools only. The runner owns session creation.
  - **sandbox**: additionally offers lifecycle tools (`create_session`, `list_sessions`,
    `end_session`).
- **FR-3.4a** The two profiles MUST be reached through **separate entry points** sharing one server
  implementation. In the benchmark process the lifecycle tools are never constructed, so they are
  *absent* rather than gated. A configuration mistake, a malformed request, or a prompt injection
  cannot reach a capability the process does not hold.
- **FR-3.4b** A test MUST assert the absence: the benchmark entry point's served tool list MUST NOT
  contain any lifecycle tool. Absence is testable; intent is not.
- **FR-3.4c** The dividing line is who the client is. **A model is a player, never an operator.** It
  may act, observe and be rejected; it may not create, list, configure or end a game.
- **FR-3.5** Both transports MUST be supported: stdio (one server per client) and HTTP (shared
  server). Both MUST bind to the same facade behaviour (FR-1.4).
- **FR-3.6** Resources MUST include at least: the player's projection, the pending decisions, and — at
  L1 and above — the decision surface. At L2, the enumerated legal actions.
- **FR-3.7** Resource URIs MUST be game-agnostic in shape: `<game>://sessions/{id}/state?player=N` and
  siblings.
- **FR-3.8** A resource read MUST NOT consume randomness and MUST NOT mutate state (inherited from v1's
  `observe` purity).
- **FR-3.9** Resource renderings MUST come from the game's own `render` method at the detail level the
  run config declares — one renderer, not a second one written for MCP.

### 8.4 Assist levels on the agent surface

- **FR-4.1** At L0 the agent surface MUST expose the projection only. Rejections MUST be minimal and
  MUST NOT leak enumeration.
- **FR-4.2** At L1 the surface MUST add the decision surface: action types, costs, permitted parameter
  domains — never the cross product.
- **FR-4.3** At L2 the surface MUST add the enumerated legal actions and full rejection detail.
- **FR-4.4** Assist level MUST NOT be readable by, or adjustable by, the agent. It is set in the run
  config by the operator.
- **FR-4.5** SC-3 — assist equivalence through the agent surface — MUST be proven by test, not
  assumed from v1's scripted equivalence.

### 8.5 The LLM provider abstraction

- **FR-5.1** The abstraction MUST be narrow, per `ARCHITECTURE.md` §13:
  `complete(messages, tools, config) -> {text, tool_calls, usage}`.
- **FR-5.2** The first real provider MUST be **OpenRouter**, which reaches many model vendors through
  one OpenAI-compatible transport, alongside a **mock** provider used by the whole test suite.
  Shipping one gateway rather than N vendor SDKs is a deliberate benchmark decision: every model is
  then driven through the same request path, so a difference between two models is a difference
  between the models and not between two client libraries.
- **FR-5.3** A provider without native tool calling MUST be supported through a documented text
  protocol implemented in the adapter, not in the tool loop.
- **FR-5.4** The adapter MUST record, verbatim, the exact request payload and the exact response, for
  every call (SC-4).
- **FR-5.5** The adapter MUST NOT retry, summarise, repair or otherwise modify a request. Policy
  belongs to the layer above, where it is visible.
- **FR-5.6** Usage reporting MUST be normalised (prompt tokens, completion tokens, total) and MUST
  tolerate providers that omit it, marking the omission explicitly rather than recording zero.
- **FR-5.7** A provider's identity and version MUST be recorded in the run manifest.
- **FR-5.8** The adapter MUST record the model identifier, the upstream route the gateway selected, and
  whether the model accepted native tool calling for that request. The same logical model reachable
  through two upstreams is not the same model for measurement purposes, and a silent route change
  would look like a model change.
- **FR-5.9** Pricing MUST be read from the gateway's own model listing where it is available, and
  recorded in the manifest together with when it was read, rather than hardcoded in the repository. A
  price table that drifts silently makes every cost comparison meaningless.

### 8.6 The agent tool loop

- **FR-6.1** One **decision turn** = one model conversation about one open decision. It ends when the
  engine **accepts** an action, when the redo budget (§8.7) is exhausted, when the step budget is
  exhausted, or when a timeout fires.
- **FR-6.2** Within a decision turn the agent MAY make bounded read tool calls before acting.
- **FR-6.3** The step budget MUST be a declared run-config value and MUST be recorded.
- **FR-6.4** The tool loop MUST be provider-agnostic: it MUST NOT contain provider-specific branching.
- **FR-6.5** An action the engine rejects MUST be returned to the model **within the same decision
  turn** as a redo (§8.7). A rejection MUST NOT start a fresh decision turn and MUST NOT be hidden
  from the record.
- **FR-6.6** The loop MUST NOT offer the model help it was not configured to have: no automatic hints,
  no summarisation, no re-reading state on the model's behalf.

### 8.7 Illegal actions, failure and termination

Every policy below MUST be a value in the run config, recorded in the manifest, and applied
identically to every model in a comparison.

**The illegal action is answered with a redo, not with a forfeit and not with a substitute.**

- **FR-7.1** When the engine rejects an action, the agent MUST be told the rejection and asked again,
  within the same decision turn, until it produces a legal action or exhausts its retry budget.

  > **Why a redo loop.** At a real table, a player who attempts an illegal move is stopped by the other
  > players and asked to try again; nobody picks a move for them. A redo loop is that behaviour made
  > explicit. It is legitimate in a way a fallback is not, because it never supplies a choice the model
  > failed to make. Substituting a baseline move would make the scored player part baseline, and the
  > result could no longer be attributed to the model.

- **FR-7.2** The redo prompt MUST be a single artefact shared by every model, every seat and every
  game, and MUST be hashed into the manifest like any other prompt (§8.9). A model given differently
  worded feedback is not being measured against the others.
- **FR-7.3** The redo budget MUST be a declared run-config value, recorded in the manifest, and
  **identical for every model and every seat in a comparison**. It MUST NOT vary per model.
- **FR-7.4** What a redo reveals is governed by the rejection-detail tier (§8.4): at minimal detail the
  model is told only that the action was not legal; at full detail it may be shown the alternatives.
  **The redo turn is a new channel through which enumeration could leak at L0**, and it MUST be covered
  by the assist-equivalence test (SC-3).
- **FR-7.5** **Exhaustion abandons the game.** If a model cannot produce a legal action within its
  budget, the game stops there: a game whose decision-maker has failed to that degree is no longer
  producing a measurement worth completing.
  - The game MUST be recorded as **abandoned**, carrying the failing decision, the final rejection, the
    number of attempts, and the seat and model responsible.
  - An abandoned game's god log has **no terminal record**. A synthetic one MUST NOT be written.
  - An abandoned game MUST be excluded from outcome aggregates and reported in its own row.
  - Abandonment MUST be reported **per model** in `results.json`: a model that abandons games is a
    different finding from one that loses them.
- **FR-7.6** **Malformed tool call**: a bounded repair attempt inside the same decision turn where the
  provider's API supports it, charged to the same redo budget; otherwise a recorded failure of a
  named kind.
- **FR-7.7** **No action emitted**: a model that responds with prose and no tool call MUST be recorded
  with that failure kind and MUST NOT be coerced into an action. It is not an illegal action, so it
  MUST NOT silently consume a redo.
- **FR-7.8** **Timeout**: per decision turn and per game. A timed-out decision resolves by the same
  abandonment rule as exhaustion (FR-7.5), because a model that cannot answer in time has failed in
  the same way.
- **FR-7.9** **Runaway**: a model that exceeds the step budget inside one decision turn is recorded as
  a runaway and ends the decision turn. A runaway is not an illegal action and MUST NOT be charged to
  the redo budget.
- **FR-7.10** Failure kinds MUST be an enumerable set, declared like v1's rejection codes, so the
  results layer can count them without parsing text.
- **FR-7.11** No failure mode may hang the runner: every game MUST reach a conclusion, **completed or
  abandoned**.

### 8.8 Context policy

- **FR-8.1** The context strategy MUST be a declared run-config value, not an emergent behaviour. The
  **default MUST be delta projection with periodic full refresh.** Full projection every turn is less
  confounded but pays the whole board on every decision, and on a 790-action game that difference is
  large enough to decide which experiments are affordable at all.
- **FR-8.2** At minimum three strategies MUST be supported: full projection every turn, delta
  projection (using v1's delta renderer) with periodic full refresh, and a bounded window of recent
  turns.
- **FR-8.3** The strategy MUST be recorded in the manifest and MUST be identical across models in a
  comparison.
- **FR-8.4** Context construction MUST be reproducible from the record: given the record, the exact
  message list sent for any decision MUST be reconstructible (SC-4).

### 8.9 Prompt assembly

- **FR-9.1** Four prompt layers MUST exist and be separable: the game's `game.md` (v1), a role
  `system.md`, a provider policy `policy.md`, and the single shared redo prompt of FR-7.2.
- **FR-9.2** The game prompt MUST continue to contain no strategy advice (v1 FR-19.2, enforced by test).
- **FR-9.3** **Every** prompt artefact used in a run — including any policy text — MUST be hashed into
  the manifest, not just the game prompt.
- **FR-9.4** The manifest's hashes MUST be recomputed before every game and a mismatch MUST abort the
  run (SC-5). A prompt edited mid-run is a comparison of two different experiments.
- **FR-9.5** Tool descriptions and resource descriptions are prompt surface: they MUST be derived from
  the game's declaration, not hand-written per game, and their provenance MUST be the same generator
  everywhere.
- **FR-9.6** The redo prompt MUST be identical across every model. Where an adapter must differ in
  *transmission* — a model without native tool calling receives the same words inside a text frame —
  that difference MUST be recorded, so a wording difference can never be mistaken for a model
  difference.

### 8.10 Run manifest and records

- **FR-10.1** A run directory MUST contain `run.json` describing: run id, game and version, all game
  config values, seat assignment, model and provider identities, sampling parameters, every policy
  value (§8.7, §8.8), and every prompt hash.
- **FR-10.2** The god log MUST remain exactly the v1 format and MUST remain deterministic over recorded
  actions. Nothing about a model may enter it.
- **FR-10.3** All model interaction MUST go in the `.meta.jsonl` sidecar, extending it with: request
  messages, response payload, tool calls, usage, cost, latency, failure kind, the attempt index against
  the redo budget, the rejection that prompted each retry, the upstream route, and whether native tool
  calling was used.
- **FR-10.4** The sidecar MUST be sufficient to answer "what exactly did the model see, and what did it
  say?" for every decision, without consulting anything outside the run directory.
- **FR-10.5** Secrets MUST NOT be recorded. A recorded request MUST be redacted of credentials.
- **FR-10.6** `results.json` MUST summarise per game and per seat: outcome, place, actions, rejection
  counts by code, failure counts by kind, tokens, cost, and wall-clock latency.

### 8.11 The runner and experiment design

- **FR-11.1** The runner MUST assign an **agent** to each seat, from a declared set: an LLM agent, a
  reference player, or a scripted agent.
- **FR-11.2** The runner MUST dispatch **concurrent decisions in parallel** and apply results in the
  game's declared resolution order, so that wall-clock cost does not scale with concurrency while the
  record stays deterministic.
- **FR-11.3** A run MUST declare an **experiment design** with three independent parameters:
  - `seating`: `fixed` | `rotated` | `random`
  - `initial_configuration`: `fixed:<name>` | `random`, and when random, whether the draw happens
    once per experiment or once per game
  - `replicates`: how many independent experiments to play

  Seating and initial configuration are **separate axes, not one "mirroring" switch**. They are
  different sources of variance and they are not present in the same games.
- **FR-11.4** The number of games MUST be **derived** from the design, never stated separately:

  > games = replicates × (seating is `rotated` ? seats : 1)

  Five replicates of a four-seat rotated design is twenty games. The manifest MUST report the
  derivation, not only the product, so the number fifty can be traced to a decision rather than
  guessed at.
- **FR-11.9** A `rotated` design MUST contain exactly N games for N seats, where game k applies a
  cyclic shift of the agent-to-seat mapping by k. Over the set, every agent occupies every seat index
  equally often — including when the table mixes distinct agents with repeated ones, where an agent
  holding r seats occupies each seat index r times. No special case is needed for a repeated agent.
- **FR-11.5** The runner MUST be able to run many games unattended, with bounded concurrency, resuming
  without corrupting completed games.
- **FR-11.6** A game that fails at the agent layer MUST be recorded as exactly one of **completed** or
  **abandoned** (FR-7.5). It MUST NOT produce a record that looks complete but is not, and an
  abandoned game MUST NOT be given a synthetic terminal record.
- **FR-11.6a** `verify` over a run directory containing an abandoned game MUST report that game as
  incomplete and MUST NOT fail the whole run, nor silently pass it.
- **FR-11.7** The runner MUST NOT contain game-specific logic; every game fact comes from the plugin's
  declarations.
- **FR-11.8** The runner MUST count abandonments per model and per seat, and MUST report them separately
  from outcomes in `results.json`.
- **FR-11.10** Every game MUST record the design that produced it: replicate index, rotation index,
  seat assignment, seed, and the initial configuration used. A result that cannot be attributed to a
  point in the design cannot be compared with any other run.
- **FR-11.11** The axes MUST be independently optional, because **not every game has variation in its
  setup**:
  - **Seating** varies in any game with more than one seat, including one whose starting position is
    fully determined. Equalising seat exposure matters exactly as much there — a game with fixed
    pieces still gives one seat the first move.
  - **Initial configuration** varies only where the plugin declares that its starting position admits
    more than one arrangement (`benchmark_profile.configuration_is_variable`). Asking a game with a
    single starting position for a random one MUST be a clear configuration error, never a silently
    ignored request.
- **FR-11.12** A design that leaves an axis uncontrolled MUST still be allowed — exploration and smoke
  tests need the one-game case, and forbidding it would push people outside the system — but the run
  MUST be **marked** as not controlling that axis, and the marking MUST travel into `results.json`.
  Data that carries its own caveat is safe. A caveat that lives in someone's memory is not.
- **FR-11.13** The single-game exploration case MUST be first-class: one game, randomly assigned seats,
  randomly drawn initial configuration, no replicates. It is the default when no design is declared.

### 8.12 Reference players

- **FR-12.1** A **random-legal** player MUST exist, reusing the v1 fuzz harness's action selector rather
  than reimplementing one.
- **FR-12.2** A **greedy-heuristic** player MUST exist: a documented, deterministic policy that expands,
  builds toward production, and takes available positive trades. It MUST be good enough to beat
  random comfortably, and it MUST be simple enough to explain in a paragraph.
- **FR-12.3** Neither reference player is ever scored or reported as a model. They appear in results
  only as reference rows.
- **FR-12.4** A reference player MUST be usable in any seat, including mixed seats with LLM agents.

### 8.13 Cost and token accounting

- **FR-13.1** Every decision turn MUST record its token usage and its latency.
- **FR-13.2** Cost MUST be computed from a declared price table per model, and the table used MUST be
  recorded in the manifest.
- **FR-13.3** A run MUST report total cost, cost per game, and cost per decision.
- **FR-13.4** Missing usage from a provider MUST be reported as unknown, never as zero, and the run's
  cost total MUST be reported as partial if any decision is unknown.

### 8.14 CLI

- **FR-14.1** `serve` — start the HTTP host and/or the MCP server in a chosen profile and transport.
- **FR-14.2** `run` — execute a run from a config file, unattended, writing a run directory.
- **FR-14.3** `inspect-run` — read a run directory: list games, show per-game summary, show the
  decision turns of one seat in one game, including the exact messages and responses.
- **FR-14.4** `play-live` — drive a game interactively through the MCP sandbox surface, so a human
  can validate the surface before pointing a model at it.
- **FR-14.5** All commands MUST exit non-zero on failure and MUST NOT print a traceback for an expected
  failure, matching v1's CLI contract (FR-20.7).
- **FR-14.6** `replay`, `verify`, `inspect`, `fuzz` from v1 MUST keep working unchanged, and
  MUST verify a v2 record exactly as they verify a v1 one.

### 8.15 Test harness and mock provider

- **FR-15.1** A **mock provider** MUST exist with scripted behaviours: always-illegal, always-timeout,
  malformed-args, prose-only, and correct-play. It is what makes the failure policy testable without
  network access or cost.
- **FR-15.2** Provider adapters MUST share one conformance suite (SC-9).
- **FR-15.3** A recording/replaying provider wrapper MUST exist so a captured run can be replayed
  through the agent layer offline, for regression tests.
- **FR-15.4** The whole v2 test suite MUST pass with no network access and no API keys.

### 8.16 Dependency policy

- **FR-16.1** `lgbg/core` and `lgbg/games` MUST keep **zero** third-party runtime dependencies
  (v1 SC-10; SC-11 here).
- **FR-16.2** New dependencies are confined to `lgbg/host`, `lgbg/adapters/mcp`, `lgbg/agents` and
  `lgbg/runner`, and each MUST be justified in `pyproject.toml`'s header comment.
- **FR-16.3** The MCP protocol MUST be implemented against the official Python SDK rather than
  reimplemented; a hand-rolled protocol is a maintenance liability with no benchmark value.
- **FR-16.4** A dependency that carries game logic or model logic is forbidden in any layer.

---

## 9. Non-functional requirements

| # | Requirement |
|---|---|
| NFR-1 | **Determinism of records.** `ARCHITECTURE.md` §6 remains normative. The god log stays deterministic over recorded actions; no model output may enter it. |
| NFR-2 | **Performance, redefined.** v1's per-game engine budget is not a v2 gate, because inference dominates. What v2 MUST bound: engine overhead per decision turn at **< 5 ms p95** measured in isolation, and per-decision wall clock MUST be attributable to the provider, not to the harness. The harness's own share MUST be reported. |
| NFR-3 | **Cost legibility.** A run MUST be able to state, before it starts, an estimated cost, and MUST stop if a declared budget is exceeded. |
| NFR-4 | **Robustness.** No agent behaviour may hang a run; every game terminates. |
| NFR-5 | **Auditability.** Every claim in a result MUST be traceable to a record on disk. |
| NFR-6 | **Concurrency safety.** Parallel sessions MUST NOT interfere; a torn record MUST be detectable. |
| NFR-7 | **Secret hygiene.** No credential appears in any artefact. |
| NFR-8 | **Offline testability.** The suite runs with no network and no keys. |
| NFR-9 | **Portability.** Linux, macOS, Windows. |
| NFR-10 | **Typing and lint.** mypy strict and ruff clean continue to hold for the new packages. |

---

## 10. The reproducibility contract

This section is normative and should be read as the v2 counterpart to `ARCHITECTURE.md` §6. It exists
because an LLM benchmark cannot have the single-layer determinism a game engine has, and pretending
otherwise is how benchmarks become unfalsifiable.

### 10.1 Three layers, only one of which is exact

| Layer | Guarantee | Mechanism |
|---|---|---|
| **Game** | **Exact.** Given the recorded actions, the game replays to every intermediate state, hash-verified. | Unchanged from v1. |
| **Decision context** | **Recorded.** Given a decision, the exact messages sent and the exact response received are recoverable. | Sidecar (FR-10.3, FR-10.4). |
| **Model choice** | **Not repeatable.** Re-running a model will produce different actions. | Recorded, not promised. |

### 10.2 What this means, stated plainly

- A v2 run is **replayable but not re-executable**. You can always inspect what happened. You cannot
  generally make it happen again.
- A result MUST therefore never be reported as "the model plays Catan at X%" without its run directory.
  The directory *is* the evidence; the number is a summary of it.
- Comparisons MUST hold every controllable factor constant: prompts by hash, assist level, context
  strategy, redo budget, step budget, sampling parameters, board, and seed. The manifest exists to
  make a violation of this visible rather than invisible.
- **An abandoned game is not a loss.** It is a game that produced no outcome. Recording one as a defeat
  would quietly reward a model that plays badly-but-legally over a model that fails decisively, so
  abandonment is reported as its own count and never folded into a win rate.

### 10.3 What v2 MUST record so that v3 can reason statistically

Sampling parameters, provider identity and version, timestamps, and per-decision usage — so that v3 can
state how much of the observed variance is the model and how much is everything else.

---

## 11. Artefact contracts

### 11.1 Run directory

```text
runs/<run_id>/
  run.json                  manifest: config, seats, models, policies, prompt hashes, price table
  results.json              per-game and per-seat accounting
  games/
    <game_id>.god.jsonl     unchanged v1 format - deterministic, hash-chained
    <game_id>.meta.jsonl    extended: model interactions per decision turn
```

### 11.2 Run config file

```jsonc
{
  "game": "catan",
  "config": { "seed": 123456789, "board": "fixed:standard_a", "assist": "L1" },
  "seats": [
    { "seat": 0, "agent": "llm", "model": "<model-id>", "provider": "<provider-id>", "temperature": 0.0 },
    { "seat": 1, "agent": "heuristic" },
    { "seat": 2, "agent": "llm", "model": "<model-id>", "provider": "<provider-id>", "temperature": 0.0 },
    { "seat": 3, "agent": "random" }
  ],
  "design": {
    "seating": "rotated",
    "initial_configuration": "random",
    "configuration_scope": "per_experiment",
    "replicates": 5
  },
  "policies": {
    "context": "delta_with_refresh",
    "redo_budget": 3,
    "on_exhausted": "abandon_game",
    "step_budget": 8,
    "decision_timeout_s": 120,
    "budget_usd": 25.0
  }
}
```

### 11.3 Sidecar record, per decision turn

```jsonc
{"t":"decision","game_id":"g-0001","seq":47,"request_id":"d91","player":2,"seat":2,
 "model":"<model-id>","provider":"<provider-id>","route":"<upstream>","native_tools":true,
 "attempt":2,"redo_budget":3,
 "messages":[{"role":"system","content":"..."},{"role":"user","content":"..."}],
 "response":{"text":"...","tool_calls":[...]},
 "outcome":{"kind":"action","action":{"type":"build_road","params":{"edge":17}}},
 "rejection":{"code":"INSUFFICIENT_COMPONENTS","detail":"standard","attempt":1},
 "usage":{"prompt_tokens":1234,"completion_tokens":56,"total_tokens":1290},
 "cost_usd":0.0012,"latency_ms":4180,"failure":null}
```

`attempt` counts the redo turn within the decision, so a record shows how much of the retry budget a
normalisation consumed rather than hiding it. A rejected attempt records `rejection` with the code the
engine returned and no action; the attempt that finally succeeds carries the same `request_id` as the
ones it superseded.

A decision that ends without a legal action records `failure` with a kind from the declared set
(FR-7.10) and no action — and, when the redo budget is exhausted, the game is abandoned (FR-7.5) and
its god log carries no terminal record.

---

## 12. Acceptance test plan

| Test | Covers |
|---|---|
| `test_surface_equivalence` | FR-1.4, SC-2 — one action file, three surfaces, one hash |
| `test_mcp_tools_generated` | FR-3.2, SC-6 — tools come from the v1 generator |
| `test_mcp_resources_by_assist` | FR-3.4, FR-4.1–FR-4.3 — what each level reveals |
| `test_assist_equivalence_agent` | FR-4.5, SC-3 |
| `test_provider_conformance` | FR-5.2, FR-5.3, SC-9 |
| `test_provider_records_payload` | FR-5.4, SC-4 |
| `test_manifest_rehashes` | FR-9.3–FR-9.4, SC-5 |
| `test_sidecar_reconstructs` | FR-10.4, SC-4 |
| `test_design_derivation` | FR-11.4, SC-7 — five replicates of four seats is twenty games, and the derivation is recorded |
| `test_rotation_balance` | FR-11.9, SC-7 — every agent occupies every seat index equally often, including a repeated agent |
| `test_design_recorded` | FR-11.10, SC-7 — each game carries its replicate, rotation, seat and configuration |
| `test_config_variability` | FR-11.11 — a game declaring one fixed starting position rejects a random-configuration design |
| `test_uncontrolled_design_marked` | FR-11.12 — the marking travels into `results.json` |
| `test_one_game_default` | FR-11.13 — an undeclared design gives one game, random seats, random configuration |
| `test_profile_absence` | FR-3.4b — the benchmark entry point serves no lifecycle tool |
| `test_reference_players` | FR-12.1–FR-12.4, SC-8 |
| `test_redo_loop` | FR-7.1–FR-7.4, SC-15 — an illegal action gets a redo inside the same decision turn, under one shared prompt |
| `test_redo_uniform` | FR-7.3, FR-9.6 — every model and seat receives the same redo budget and the same words |
| `test_abandonment` | FR-7.5, FR-11.6, FR-11.6a, FR-11.8 — exhaustion abandons the game, writes no terminal record, and stays out of outcome aggregates |
| `test_failure_policies` | FR-7.6–FR-7.10, SC-10, using one mock behaviour each |
| `test_no_hang` | FR-7.11, NFR-4 — every mock behaviour terminates, completed or abandoned |
| `test_cost_accounting` | FR-13.1–FR-13.4 |
| `test_cli_unattended_run` | FR-14.2, SC-12 — ≥ 50 games on the mock, unattended |
| `test_sandbox_human_play` | FR-3.4, SC-14 |
| `test_v1_cli_unchanged` | FR-14.6 — v1 records still verify |
| `test_no_new_core_dependencies` | FR-16.1, SC-11 |
| `test_no_secrets_in_artefacts` | FR-10.5, NFR-7 |
| `test_traceability` | SC-13 |

---

## 13. Milestones

| # | Milestone | Definition of Done |
|---|---|---|
| **M0** | Dependency and protocol decisions | Settled by §15.1: **OpenRouter** as the provider gateway, **ASGI** with routing against the interface directly, the **redo loop** as the illegal-action default, **delta-with-refresh** as the context default. MCP SDK chosen and justified (FR-16.2). Run directory format frozen. |
| **M1** | Session facade | Facade over the v1 engine with in-process access; engine-overhead measurement; v1 CLI unaffected. FR-1. |
| **M2** | MCP surface, both profiles | Tools generated by the v1 function, observation resources, stdio transport. Benchmark and sandbox as **separate entry points** over one implementation, profile fixed at construction, absence of lifecycle tools tested. A human plays a full game by hand. FR-3, SC-6, SC-14. |
| **M3** | Assist levels on the surface, and the equivalence proof | FR-4, SC-3. |
| **M4** | Provider abstraction and the OpenRouter adapter | The OpenRouter adapter, the mock, conformance suite, payload and routing recording, pricing capture. FR-5, FR-15.1–FR-15.2, SC-4, SC-9. |
| **M5** | Tool loop and one model playing | One model plays a full game; sidecar records every decision turn. FR-6, SC-1. |
| **M6** | Redo loop, failure and context policy | The redo loop with its shared prompt and budget; abandonment on exhaustion; failure kinds; context strategies. FR-7, FR-8, SC-10, SC-15. |
| **M7** | Runner and experiment design | Seats, the design matrix (seating × configuration × replicates), rotation, per-game design records, reference players. FR-11, FR-12, SC-7, SC-8. |
| **M8** | HTTP host and registry | FR-2, SC-2 complete (all three surfaces). |
| **M9** | Accounting and unattended runs | FR-13, FR-14.2, `results.json`, the CI campaign on the mock, the budget-bounded demonstration run. SC-12, SC-16. |
| **M10** | CLI completion, documentation, acceptance | FR-14, D9, SC-1…SC-16 evidenced in an acceptance record. |

**M2 before M4 is deliberate.** A human playing by hand through the MCP surface proves the surface is
correct before a model is introduced. If the first thing driven through the surface is a model, a bug
in the surface and a bug in the agent look identical.

---

## 14. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | The harness, not the model, is what gets measured | High | High | FR-6.6, FR-7.1–FR-7.11, FR-8.1–FR-8.3: every policy is a recorded config value; SC-3 and SC-5 make drift fail the build |
| R2 | The MCP surface and the runner diverge into two different games | High | High | FR-1.1–FR-1.4, SC-2: one facade, one equivalence test |
| R3 | Assist level leaks through the agent surface | Medium | High | FR-3.3 (constant tool set), FR-4, SC-3 proven on a model-driven run |
| R4 | A prompt is edited mid-run and two conditions are compared as one | Medium | High | FR-9.4: rehash before every game, abort on mismatch (SC-5) |
| R5 | Provider APIs differ enough to make models incomparable | High | Medium | FR-5.3, FR-5.6, FR-5.7, SC-9; record provider version; keep the abstraction narrow |
| R6 | Failure handling quietly becomes a rescue mechanism that flatters one model | High | High | FR-7.1–FR-7.5: one shared redo prompt, one redo budget for every model, no substituted move; abandonments counted per model (FR-11.8) |
| R7 | Context strategy silently determines performance | Medium | High | FR-8.1–FR-8.3: declared, recorded, identical across models; delta-with-refresh fixed as the default so the confound at least stays constant |
| R8 | Costs explode during development | High | Medium | Mock provider for all tests (FR-15.4); budget cap (NFR-3); unattended runs sized after M5 |
| R9 | v1's dependency-free core erodes under v2 pressure | Medium | Medium | FR-16.1, SC-11 |
| R10 | Records lack enough to reconstruct a decision | Medium | High | FR-10.4, SC-4 tested from the artefact alone |
| R11 | Concurrency produces records that look complete but are torn | Medium | High | NFR-6, FR-11.6 |
| R12 | Two runs produce numbers that look comparable but were designed differently | High | High | FR-11.10 records each game's point in the design; FR-11.12 marks every uncontrolled axis in `results.json`; v3 refuses to compare across designs |

---

## 15. Decisions and open questions

### 15.1 Resolved

| # | Question | Resolution |
|---|---|---|
| Q1 | Which providers ship in v2? | **OpenRouter**, one gateway reaching many vendors, so every model is driven through the same request path and a difference between two models is not a difference between two client libraries (FR-5.2). Model id, upstream route and native-tool-calling support are recorded per request (FR-5.8); pricing is read from the gateway and recorded with its read time (FR-5.9). The mock ships alongside it. |
| Q2 | HTTP framework? | **ASGI**, with routing written directly against the ASGI interface and no framework until a concrete need appears (FR-2.7). |
| Q3 | Default illegal-action resolution? | **Redo loop.** An illegal action is answered by asking the model again with one shared redo prompt, under a retry budget identical for every model — the table blocking a move and asking the player to redo it, not a forfeit and not a substitute choice. Exhausting the budget abandons the game rather than completing it with fabricated play. Illegal-move counts are recorded in v2 and become a reported metric in v3 (FR-7.1–FR-7.5, SC-15). |
| Q4 | Default context strategy? | **Delta with periodic full refresh** (FR-8.1). |
| Q5 | Close v1's event-sufficiency gap? | **Carry it to v3**, and consider formally withdrawing the requirement there. Closing it needs a second implementation of every state transition, which would drift from `apply`; nothing in v2 depends on it, and adding a protocol member while landing the agent layer would confound two changes at once. |
| Q6 | Sandbox profile: a flag, or a separate entry point? | **Separate entry points over one implementation**, profile fixed at construction, with the lifecycle tools *absent* from the benchmark process rather than gated behind a value — and a test asserting the absence (FR-3.4–FR-3.4c). The rule underneath: **a model is a player, never an operator.** |
| Q7 | How many games is "an unattended run"? | **Split into two criteria.** SC-12 is a CI campaign of ≥ 50 games on the mock provider, where unattended operation is the thing being proved and cost is zero. SC-16 is a real-provider demonstration bounded by **declared budget** rather than by a game count, because the same count costs roughly $4 on a cheap model and roughly $90 on a frontier one. |
| Q8 | Is mirroring mandatory, or a default? | **Replaced by an experiment-design model.** Randomness is fought by declaring which axes vary and recording them per game, not by mandating a single rotation. Seating and initial configuration are independent axes — a game with a fixed start varies only the first — and the game count is derived from the design rather than stated (FR-11.3–FR-11.13). |

### 15.2 Open

None at the time of writing.

New questions are appended here and answered explicitly rather than settled by assumption. That is not
a formality: every one of Q5–Q8 above changed a requirement once it was asked out loud, and Q8 changed
a whole section.

---

## 16. Traceability

| Requirement group | Architecture reference |
|---|---|
| FR-1 | §12.1 (MCP is a frontend), §4 (layering) |
| FR-2 | §12.1, §12.3 (server profiles) |
| FR-3 | §12.2 (resources for reading, tools for acting), §7.3 (schemas as data) |
| FR-4 | §9 (assist levels) |
| FR-5 | §13 (agent layer constraints) |
| FR-6, FR-7 | §13, §10 (error model) |
| FR-8 | §12.4 (notation detail levels), §13 |
| FR-9 | §11 (prompt layer) |
| FR-10, FR-11 | §8 (logging and event sourcing), §7.10 (benchmark profile) |
| FR-12 | §15 (measurement layer) |
| FR-13 | §15 |
| FR-16 | §4 (layering), §7.3 |

---

## 17. Sign-off

| Role | Name | Decision | Date |
|---|---|---|---|
| Product owner | | | |
| Architecture owner | | | |
