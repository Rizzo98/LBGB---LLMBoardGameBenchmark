# PRD-v1 — Engine Core and Verifiable Replay

| Field | Value |
|---|---|
| **Document** | PRD-v1 |
| **Release** | v1 |
| **Status** | Draft — awaiting approval |
| **Depends on** | `ARCHITECTURE.md` (source of truth for architecture; versionless and game-agnostic) |
| **Game plugin** | Settlers of Catan, base game, 4 players |
| **Plugin rules doc** | `games/catan/RULES.md` (deliverable D1) |
| **Supersedes** | — |
| **Deliverable type** | Library + CLI. No service, no network surface. |

---

## 1. Summary

Build the game engine core and the verifiable-replay machinery for LBGB, together with the first game
plugin: Settlers of Catan, base game, 4 players.

The release delivers no LLM integration, no MCP server, and no player bots. It delivers a Python
library and CLI that can run a complete Catan game from a scripted action file, produce a hash-chained
game record, and replay that record back to **every intermediate state** with every hash verified.

This release exists because everything downstream — MCP surfaces, LLM agents, scoring, leaderboards —
is computed from game records. If the records are not trustworthy, no result derived from them is
falsifiable.

The release also serves a second purpose: Catan is the **reference implementation of the game plugin
interface**. It is deliberately chosen to be awkward, because a plugin interface that only works for a
simple game is not an interface.

---

## 2. Background

LBGB is a benchmark that uses board games to measure reasoning and planning in LLMs. Catan is the
first game because it exercises long-horizon planning, resource conversion, spatial reasoning,
probability assessment, and multi-agent negotiation.

Before any model is measured, the substrate must be correct. Two failure modes are unacceptable and
are the whole justification for this release:

1. **A replay that is plausible but wrong.** If replay silently diverges, benchmark results become
   unfalsifiable and undebuggable. This is why randomness is recorded per draw with semantic labels
   rather than as a seed (`ARCHITECTURE.md` §5.4).
2. **A rule implemented from memory.** Rules implemented from recollection rather than the rulebook
   produce a game that is subtly not Catan. Every measurement on it is invalid, and the error is
   typically undiscoverable after the fact.

### 2.1 Why Catan stresses the plugin interface

Catan is a good first game precisely because it is not a clean turn-based game. Any plugin interface
must survive the following, and this release is where we find out whether ours does:

| Catan feature | What it demands of the platform |
|---|---|
| Forced discards when a 7 is rolled | Several players deciding concurrently, not one turn at a time |
| Player-to-player trade responses | Decisions addressed to players who are out of turn |
| The opening snake draft | Setup is a phase like any other, not a special case |
| Dev cards that are unplayable until the turn after purchase | Rules that reference turn history |
| Hidden victory-point cards | "Who is leading" is not derivable from any player's view |
| A seized card revealed only to the seizer | Knowledge that is asymmetric, not merely private |
| Two awards that change hands mid-game | Derived state that must be recomputed on every transition |

---

## 3. Goals

| # | Goal |
|---|---|
| G1 | A trustworthy, hash-verified replay capability for any recorded game. |
| G2 | A faithful implementation of the Catan base game, verified against the official rulebook. |
| G3 | A game-plugin interface that is genuinely sufficient for a second, different game without rework of the core. |
| G4 | Assist levels L0/L1/L2 implemented and selectable per run, with the guarantee that they never affect game legality. |
| G5 | A machine-checkable corpus of invariant assertions that catches engine defects during development rather than during benchmarking. |
| G6 | The declarations later releases depend on — action and observation schemas, player projections, a benchmark profile, game invariants, prompt artefacts — present and complete. |

---

## 4. Non-goals

Explicitly **not** in this release. Each of these requires its own PRD.

| Out of scope | Note |
|---|---|
| LLM providers, agents, tool loops | PRD-v2 |
| MCP server or any network surface | PRD-v2 |
| Heuristic, search-based, or random **bots** | Scored players are out of scope. See §8.22 for the fuzz driver, which is a test harness and is never scored. |
| HTTP host / session registry | PRD-v2 |
| Scoring, Elo, statistics, dashboards | PRD-v4 |
| Web UI or replay viewer | PRD-v3 (operator console and replay viewer); the CLI's `replay` command is the v1 substitute until then. |
| Free-text trade negotiation | Permanently out of scope for benchmark runs (`ARCHITECTURE.md` §3). |
| Expansions (Seafarers, Cities & Knights) | A new plugin, not a flag on this one. |
| Variable player counts (3 or 5–6) | Base 4-player only. |
| Performance tuning beyond the NFR targets in §9 | — |

---

## 5. Success criteria

The release is accepted when **all** of the following hold. These are binary and each maps to an
automated check in §12.

| # | Criterion |
|---|---|
| SC-1 | A complete 4-player game driven by a scripted action file replays to every intermediate state with all hashes verified, for at least 3 distinct (seed, board) combinations. |
| SC-2 | The fuzzer completes ≥ 10,000 games across ≥ 1,000 seeds with zero uncaught exceptions and all declared invariants holding. |
| SC-3 | Determinism holds across separate processes with differing `PYTHONHASHSEED`: identical hash chains for identical (seed, action) inputs. |
| SC-4 | Tamper detection is localised: mutating any single record, RNG draw value, or state hash causes verification to fail and to report the correct `seq`. |
| SC-5 | Rejection invariance holds for every logged rejection in the corpus: the state hash is unchanged across a rejected action. |
| SC-6 | Hidden-information leak tests pass for every hidden field in §8.16 — no projection exposes another player's card identities or the deck order. |
| SC-7 | The structural self-check passes: 19 hexes, 54 vertices, 72 edges, symmetric adjacency, correct coast/interior classification, 9 ports correctly distributed. |
| SC-8 | Running the same scripted action file at assist levels L0, L1, and L2 produces byte-identical god logs (excluding the header's `config.assist` field). |
| SC-9 | Every functional requirement in §8 is traced to at least one automated test. |
| SC-10 | `lgbg/core/` and `lgbg/games/` have zero third-party runtime dependencies. |
| SC-11 | ≥ 90% line coverage on `lgbg/core/` and `lgbg/games/catan/rules/`, with `longest_road.py` and `projection.py` at 100%. |
| SC-12 | `games/catan/RULES.md` is complete: every rule area in §8 is pinned with a rulebook citation, and every listed ambiguity is resolved. |
| SC-13 | The plugin declares a complete benchmark profile and a complete rejection-code set, and a fuzz run produces no rejection code absent from that set. |

---

## 6. Users and consumers

| Consumer | Uses |
|---|---|
| **The maintainer** | Runs games, inspects records, debugs rules via `replay --print-states`. |
| **PRD-v2 implementers** | Consume `action_schema()`, `observation_schema()`, `observe()`, `pending_decisions()`, `benchmark_profile()`, the log format, and `notation.py`. |
| **Result reviewers** | Verify a published result by re-running `verify` on its game records. |
| **Future game implementers** | Use the plugin interface, and this plugin as the reference implementation. |

---

## 7. Deliverables

| ID | Deliverable |
|---|---|
| D1 | `games/catan/RULES.md` — pinned rule interpretations with citations. |
| D2 | `lgbg/core/` — runtime: canonical JSON, hashing, RNG, log, replay, config, plugin registry. |
| D3 | `lgbg/games/catan/` — the Catan plugin. |
| D4 | `lgbg/adapters/cli/` — `new`, `play`, `replay`, `verify`, `inspect`, `fuzz`. |
| D5 | Scripted action file format and driver. |
| D6 | Test suite covering all of §8. |
| D7 | Golden game corpus committed as fixtures. |
| D8 | Curated fixed board JSON files. |
| D9 | `games/catan/prompts/game.md` — the shared rules/notation prompt. |

---

## 8. Functional requirements

`MUST` / `SHOULD` / `MAY` per RFC 2119. Every requirement is intended to be directly
testable. Rule values cited as "Appendix A" are listed in the appendix to this document and must
additionally be pinned with citations in `RULES.md`.

### 8.1 Core runtime — canonical serialisation and hashing

- **FR-1.1** The core MUST provide `to_canonical_json(obj)` as the single serialisation path used
  for both hashing and replay.
- **FR-1.2** Canonical output MUST use sorted keys, no insignificant whitespace, and
  `ensure_ascii=True`, per `ARCHITECTURE.md` §6, clause 3.
- **FR-1.3** The core MUST provide `hash_state(state, game) -> str`, returning a truncated SHA-256
  hex digest.
- **FR-1.4** The hash width MUST be a single named constant, used everywhere, with no inline literals.
- **FR-1.5** `encode_state` MUST be a total function: every reachable state serialises without
  error. Verified by the fuzzer on every action.

### 8.2 Core runtime — randomness

- **FR-2.1** All randomness MUST flow through an injected `RandomSource`.
- **FR-2.2** `SeededRandomSource` MUST wrap a local `random.Random(seed)` instance and MUST
  record every draw as an `RngDraw` carrying `purpose`, `kind`, `args`, and
  `value`.
- **FR-2.3** Every draw call site MUST pass a `purpose` label drawn from a set of module constants,
  not inline strings.
- **FR-2.4** `ReplayRandomSource` MUST return recorded draws in order and MUST raise a localised
  error when `purpose`, `kind`, or `args` disagree with the record.
- **FR-2.5** `ReplayRandomSource` MUST raise if the recorded draw list is not exhausted exactly at
  the end of an action.
- **FR-2.6** `NullRandomSource` MUST raise on any draw, and MUST be used in tests to prove that
  `observe`, `legal_actions`, `action_domains`, `pending_decisions`,
  `check_invariants`, and `outcome` perform no randomness.
- **FR-2.7** The core and games packages MUST NOT import `random` outside `core/rng.py`.
  Enforced by a lint rule, not by convention.

### 8.3 Core runtime — event log

- **FR-3.1** The core MUST write one JSONL file per game containing a `header` record first and a
  `terminal` record last.
- **FR-3.2** Every action attempt — accepted or rejected — MUST produce exactly one `action` record,
  in order, with a monotonically increasing `seq` starting at 0.
- **FR-3.3** Each `action` record MUST carry `state_hash_prev`, `state_hash`,
  `rng`, and `events`.
- **FR-3.4** For a rejected action, `state_hash` MUST equal `state_hash_prev`.
- **FR-3.5** The header record MUST record `rules_version`, `schema_version`, the full run
  configuration, and `prompt_hashes`.
- **FR-3.6** Non-deterministic data (wall-clock timestamps, hostname, process id) MUST be written to a
  separate `.meta.jsonl` sidecar and MUST NOT appear in the god log.
- **FR-3.7** The log reader MUST reject a god log whose `schema` major version it does not
  understand, with a clear error.
- **FR-3.8** The writer MUST flush each record durably enough that a crashed process leaves a
  truncated-but-parseable-prefix log, and the reader MUST report truncation rather than raising an
  opaque parse error.
- **FR-3.9** The plugin MUST NOT introduce new record types; Catan-specific narrative MUST be carried
  in events.

### 8.4 Core runtime — replay and verification

- **FR-4.1** `replay(log, game)` MUST reconstruct the state after every `action` record by
  applying the recorded action through the normal `apply` path with a `ReplayRandomSource`.
- **FR-4.2** Replay MUST verify `state_hash_prev` and `state_hash` at every step and MUST
  fail with the offending `seq` when either disagrees.
- **FR-4.3** Replay MUST verify that the recorded `events` equal the events produced during replay.
- **FR-4.4** `verify(log)` MUST check the full hash chain without materialising every intermediate
  state, so that it can be run cheaply over a large corpus.
- **FR-4.5** Replay MUST support starting from the initial state, and MAY support resuming from a
  caller-supplied state plus `seq`.
- **FR-4.6** `projection_replay(log, game, player)` MUST reconstruct the exact sequence of
  observations a given player saw.
- **FR-4.7** Verification failures MUST identify the failure kind (hash mismatch, RNG purpose mismatch,
  RNG exhaustion, event mismatch, unknown action) and the `seq`.

### 8.5 Core runtime — configuration

- **FR-5.1** `RunConfig` MUST carry: seed, board selector, `assist`,
  `rejection_detail`, interaction protocol, number-placement rule, and prompt hashes.
- **FR-5.2** `RunConfig` MUST serialise to the header record and round-trip exactly.
- **FR-5.3** `assist` MUST default to `L1`; `rejection_detail` MUST default to the
  tier corresponding to `assist` and MUST be independently overridable.
- **FR-5.4** Unknown or misspelled config keys MUST be rejected, not silently ignored.

### 8.6 Game plugin interface and registry

- **FR-6.1** The core MUST define the `Game` protocol of `ARCHITECTURE.md` §7.1.
- **FR-6.2** `lgbg.core` MUST NOT import `lgbg.games`. Enforced by a test.
- **FR-6.3** A `@register_game` decorator MUST register plugins into a registry keyed by name.
- **FR-6.4** The registry MUST support discovery via
  `importlib.metadata.entry_points(group="lgbg.games")` in addition to explicit import.
- **FR-6.5** `Game` implementations MUST be stateless: no instance state may survive across
  `apply` calls. Enforced by a test that runs two interleaved games through one plugin instance.
- **FR-6.6** A game MUST declare `name`, `rules_version`, and `schema_version`.
- **FR-6.7** The Catan plugin MUST declare a `BenchmarkProfile` stating: positional asymmetry
  (present — earlier seats confer advantage, so mirrored pairings are REQUIRED), outcome shape (single
  winner, ranked places derivable), variance class (high, driven by repeated random production),
  interaction character (mixed — adversarial with a structured cooperative channel), and decision-length
  distribution (typical and worst case).
- **FR-6.8** The Catan plugin MUST declare its rejection codes via `rejection_codes()`. A fuzz run
  MUST NOT produce a rejection code absent from that declaration.
- **FR-6.9** The Catan plugin MUST implement `check_invariants(state)` returning at least: resource
  conservation (per resource, bank plus all hands equals 19) and piece conservation (per player and
  piece type, supply plus on-board equals the initial count).
- **FR-6.10** The Catan plugin MUST implement the structural self-check required by
  `ARCHITECTURE.md` §7.5, and it MUST run as a test.

### 8.7 Catan — board

- **FR-7.1** Topology MUST be derived from hex axial coordinates; adjacency tables MUST NOT be
  hand-written.
- **FR-7.2** The derivation MUST produce exactly 19 hexes, 54 vertices, and 72 edges, with symmetric
  adjacency.
- **FR-7.3** Vertex and edge identifiers MUST be integers assigned by a canonical sort of their derived
  coordinates, so the scheme is reproducible and documented.
- **FR-7.4** The board MUST support `fixed:<name>` (loading curated JSON) and `random`
  (seeded generation).
- **FR-7.5** Number-token placement MUST support the configured rule and MUST consume recorded RNG draws
  when random.
- **FR-7.6** Ports MUST be placed on the 9 coastal port positions with the correct 4×3:1 and 5×2:1
  distribution (Appendix A).
- **FR-7.7** At least 3 curated fixed boards MUST be committed with documented selection rationale.

### 8.8 Catan — setup phase

- **FR-8.1** Setup MUST follow the snake order 0,1,2,3,3,2,1,0.
- **FR-8.2** Each selection MUST be a settlement placement followed by an adjacent road placement.
- **FR-8.3** Setup placements MUST respect the distance rule and connectivity constraints.
- **FR-8.4** The second settlement MUST grant one of each resource from adjacent non-desert hexes, subject
  to bank availability.
- **FR-8.5** Setup MUST be expressed as decision requests, not as special-cased code paths
  (`ARCHITECTURE.md` §5.6, §7.7).

### 8.9 Catan — turn structure and decision queue

- **FR-9.1** The engine MUST expose `pending_decisions(state)` and MAY have zero, one, or many open
  requests.
- **FR-9.2** All player input MUST arrive as an `Action` matched to an open `DecisionRequest`;
  an action for a non-open request MUST be rejected with `NO_SUCH_REQUEST` or
  `NOT_YOUR_DECISION`.
- **FR-9.3** Simultaneously-open requests MUST resolve in a deterministic, documented order (seat order
  within a phase), independent of arrival order.
- **FR-9.4** Each phase transition MUST emit a `phase_started` event and a `phase` record.
- **FR-9.5** The discard phase after a 7 MUST open requests to all players holding more than 7 cards
  concurrently, and MUST NOT be simulated as sequential private turns.
- **FR-9.6** The trade-response phase MUST open requests to all non-offering players concurrently.

### 8.10 Catan — production and dice

- **FR-10.1** A turn MUST begin with a decision offering `roll_dice` or a legal
  `play_dev_card` (knight).
- **FR-10.2** The roll MUST be two independent d6, recorded as `RngDraw`s.
- **FR-10.3** Production MUST grant 1 per settlement and 2 per city on matching, non-robber-occupied
  hexes.
- **FR-10.4** Production MUST be limited by bank supply; a partial distribution MUST be deterministic and
  documented in `RULES.md`.
- **FR-10.5** A roll of 7 MUST skip production and open the discard phase.

### 8.11 Catan — building and pieces

- **FR-11.1** Costs MUST be exactly those in Appendix A.
- **FR-11.2** Each player MUST start with 15 roads, 5 settlements, 4 cities (Appendix A); the count MUST
  be tracked and enforced.
- **FR-11.3** Piece exhaustion MUST make the corresponding build action unavailable, not produce an error.
- **FR-11.4** Settlements MUST respect the distance rule at exactly distance 2.
- **FR-11.5** Roads MUST connect to the player's own network, except during setup where they must connect
  to the settlement just placed.
- **FR-11.6** Cities MUST upgrade an existing own settlement.
- **FR-11.7** Building MUST be rejected with the specific rejection code from the plugin's declared set
  (`ARCHITECTURE.md` §10).

### 8.12 Catan — robber and discards

- **FR-12.1** A player holding more than 7 resource cards MUST discard `floor(hand / 2)`.
- **FR-12.2** A discard MUST allow any composition of resources the player holds.
- **FR-12.3** The current player MUST move the robber to a different hex.
- **FR-12.4** A steal MUST transfer one random resource from a chosen adjacent opponent holding at least
  one card, with the draw recorded.
- **FR-12.5** The stolen card's identity MUST be visible to the thief and its removal visible to the
  victim, per the projection table in `ARCHITECTURE.md` §7.8.
- **FR-12.6** Playing a knight MUST trigger the same robber flow.

### 8.13 Catan — development cards

- **FR-13.1** The deck MUST contain 25 cards with the exact composition in Appendix A and MUST be
  shuffled at game start from recorded draws.
- **FR-13.2** Dev-card purchase MUST draw from the deck; an empty deck MUST make the action unavailable.
- **FR-13.3** A card MUST NOT be playable on the turn it was purchased.
- **FR-13.4** At most one dev card MUST be playable per turn.
- **FR-13.5** `road_building` MUST place 2 free roads, limited by remaining road supply; the
  shortfall behaviour MUST be pinned in `RULES.md` and tested.
- **FR-13.6** `year_of_plenty` MUST take 2 resources from the bank, subject to availability; whether
  duplicates are allowed MUST be pinned in `RULES.md` and tested.
- **FR-13.7** `monopoly` MUST transfer all of the named resource from all other players.
- **FR-13.8** `victory_point` MUST count toward the win total and MUST be excluded from every other
  player's public VP total.
- **FR-13.9** Longest Road and Largest Army MUST be computed and transferred per `RULES.md`,
  including the vacate-on-tie rule.
- **FR-13.10** `longest_road.py` MUST compute road length by exhaustive simple-path search and MUST
  NOT use a heuristic or greedy approximation.

### 8.14 Catan — trading

- **FR-14.1** Maritime trade MUST support 4:1 default, 3:1 generic port, and 2:1 specific port ratios,
  based on the player's port access.
- **FR-14.2** Player-to-player trade MUST be structured: `offer_trade{give, want}` followed by
  `respond_trade{accept|decline}`.
- **FR-14.3** Only the current player MAY open an offer.
- **FR-14.4** All non-offering players holding cards MUST be given a response request.
- **FR-14.5** When multiple players accept, the offerer MUST select the partner; the engine MUST NOT pick.
- **FR-14.6** An offer MUST be cancellable before resolution.
- **FR-14.7** Offers MUST NOT involve resources the offerer does not hold; such an offer MUST be rejected
  before it is broadcast.
- **FR-14.8** A completed trade MUST transfer cards atomically in one event.
- **FR-14.9** Free-text negotiation MUST NOT be part of the protocol.

### 8.15 Catan — victory and termination

- **FR-15.1** Total VP MUST be settlements 1, cities 2, VP cards 1, Longest Road 2, Largest Army 2
  (Appendix A).
- **FR-15.2** The win condition and its timing MUST follow the interpretation pinned in `RULES.md`,
  and MUST be tested explicitly.
- **FR-15.3** `is_terminal` and `outcome` MUST be pure and RNG-free.
- **FR-15.4** The outcome MUST report final VP per player, the winner, turn count, and total actions.
- **FR-15.5** The engine MUST reject any action after termination with `GAME_OVER`.

### 8.16 Catan — observation and projection

- **FR-16.1** `observe(state, player)` MUST return exactly the information in the table below.
- **FR-16.2** Other players' resource hand contents MUST NOT be exposed — only the total count.
- **FR-16.3** Other players' dev-card identities and the deck order MUST NOT be exposed.
- **FR-16.4** VP dev cards MUST be excluded from other players' public VP total.
- **FR-16.5** The projection MUST be built from an explicit allow-list. A field added to state MUST NOT
  appear in a projection unless explicitly added to that projection's allow-list.
- **FR-16.6** Each hidden field MUST have a dedicated leak test asserting non-exposure.
- **FR-16.7** `observe_spectator(state)` MUST be a distinct, separately-tested projection exposing
  the full god view.
- **FR-16.8** The observation MUST be serialisable and MUST validate against `observation_schema()`.

**Catan projection table:**

| Data | Own view | Other players' view |
|---|---|---|
| Resource hand | exact counts | total count only |
| Dev cards | exact card types | count of unplayed cards only |
| VP dev cards | counted | **excluded from public VP** |
| Pieces remaining | exact | exact (public) |
| Longest road / largest army holder | public | public |
| Deck order | never (spectator only) | never |
| A card stolen from you | you learn which card left your hand | only the thief learns what was taken |

**Consequence: "who is winning" is not fully determinable from any player's view**, because hidden VP
cards exist. That is correct and intentional, and it is why the spectator projection is a separate,
separately-tested artefact.

### 8.17 Assist levels

- **FR-17.1** `apply` MUST NOT accept, read, or depend on the assist level. Verified by test.
- **FR-17.2** The same action sequence at L0, L1, and L2 MUST produce identical god logs apart from the
  header's `config.assist` field (SC-8).
- **FR-17.3** At L0, rejection `details` MUST NOT include `legal_alternatives` or any
  parameter-domain information.
- **FR-17.4** At L1, the renderer MUST expose action types, costs, and parameter domains via
  `ActionDomain`, without enumerating the cross product.
- **FR-17.5** At L2, `legal_actions` MUST return a complete, correct enumeration. Completeness MUST
  be verified by a test that asserts every enumerated action is accepted and a sample of non-enumerated
  actions is rejected.
- **FR-17.6** `legal_actions` and `action_domains` MUST be pure and RNG-free.

### 8.18 Schemas

- **FR-18.1** `action_schema()` MUST return a JSON Schema keyed by action type covering every
  action the game accepts.
- **FR-18.2** Every incoming action MUST be validated against the schema before reaching rule logic, and
  a schema violation MUST produce `UNKNOWN_ACTION` or `BAD_PARAMS`.
- **FR-18.3** `observation_schema()` MUST describe the projection shape.
- **FR-18.4** Schemas MUST be derivable into MCP tool definitions without game-specific code. Proven by a
  test that generates definitions from the schema and asserts each action type appears with a correct
  parameter list.
- **FR-18.5** A test MUST assert that every action type produced by `action_domains` and
  `legal_actions` during a full game appears in `action_schema()` — schemas and
  implementation cannot drift.

### 8.19 Prompt artefacts

- **FR-19.1** `games/catan/prompts/game.md` MUST exist and document rules, board notation, and
  action semantics.
- **FR-19.2** It MUST NOT contain strategy advice, opening recommendations, or move evaluation guidance.
- **FR-19.3** Its SHA-256 hash MUST be computed and recorded in the game header's `prompt_hashes`.
- **FR-19.4** `notation.py` MUST provide at least a full and a compact rendering of a projection,
  used by both the CLI and (later) prompts and MCP resources.

### 8.20 CLI

- **FR-20.1** `new` — create a game from a config and print its pending decisions.
- **FR-20.2** `play` — drive a game by hand or from a scripted action file; MAY record interactive
  play back into a scripted file.
- **FR-20.3** `replay` — replay a god log, verifying hashes, with `--print-states` to dump
  each intermediate state.
- **FR-20.4** `verify` — verify a log or a directory of logs; exit non-zero on failure and print the
  offending `seq`.
- **FR-20.5** `inspect` — dump a projection for a given player, or render the board.
- **FR-20.6** `fuzz` — run N random-legal games across seeds with all declared invariants checked.
- **FR-20.7** All commands MUST exit non-zero on failure with a legible message, and MUST NOT print a
  Python traceback for an expected failure (illegal action, verification failure, bad config).

### 8.21 Scripted game driver

- **FR-21.1** A scripted action file MUST declare the game and config, plus an ordered list of actions.
- **FR-21.2** Each action MAY name a `request_id</BQ>; if omitted, it MUST apply to the sole open
  request for that player, and MUST be an error if the choice is ambiguous.
- **FR-21.3** The driver MUST fail loudly on a rejected action rather than continuing, unless
  `--allow-rejections` is passed.
- **FR-21.4** The driver MUST emit a god log identical to one produced interactively.

### 8.22 Fuzzer and invariant harness

- **FR-22.1** The fuzzer MUST drive random-legal action sequences with a seeded driver RNG separate from
  the game RNG.
- **FR-22.2** It MUST check the game's **declared invariants** (§7.11 of `ARCHITECTURE.md`) after
  every action, and MUST contain no Catan-specific invariant logic of its own.
- **FR-22.3** It MUST additionally assert, after every action: no exception, event sufficiency (applying
  events to the pre-state reproduces the post-state), rejection invariance, projection purity, and schema
  conformance of every action produced.
- **FR-22.4** It MUST assert termination within a bounded action count and report a livelock distinctly
  from a rule failure.
- **FR-22.5** It MUST be runnable against any registered game plugin, not only Catan, so it serves as a
  conformance harness for future plugins.
- **FR-22.6** Its action selector MUST be usable as a library by later non-scored drivers, but MUST NOT be
  presented or scored as a bot.

---

## 9. Non-functional requirements

| # | Requirement |
|---|---|
| NFR-1 | **Determinism.** `ARCHITECTURE.md` §6 is normative. Any violation is a defect, not a tradeoff. |
| NFR-2 | **Performance.** A single 4-player game MUST simulate in < 50 ms with the fuzz driver on a modern core; 10,000 games MUST complete in < 30 minutes single-threaded; replay MUST cost no more than 2× the original play. |
| NFR-3 | **Portability.** Linux, macOS, and Windows. No platform-specific code paths. |
| NFR-4 | **Runtime dependencies.** `lgbg/core/` and `lgbg/games/` MUST use the standard library only. Test and dev dependencies are unrestricted. |
| NFR-5 | **Typing.** Full type annotations; `mypy --strict` clean on `lgbg/core/`; no untyped `def` in `lgbg/games/`. |
| NFR-6 | **Python floor.** Python 3.12 or newer. |
| NFR-7 | **Lint/format.** `ruff` clean, including a rule banning `import random` outside `core/rng.py`. |
| NFR-8 | **Reproducible dev environment.** Pinned lockfile; a fresh clone can run the full test suite with one documented command. |
| NFR-9 | **Log compatibility.** Readers reject unknown log schema major versions with a clear message; minor additions are backward-compatible. |
| NFR-10 | **Documentation.** Every rule module has a docstring stating the rules it implements and citing `RULES.md`. Public core APIs are documented. |
| NFR-11 | **Failure legibility.** Verification and rule failures name the offending `seq`, action, and reason. A benchmark operator must be able to diagnose from the message alone. |

---

## 10. Artefact contracts

### 10.1 God log

Defined in `ARCHITECTURE.md` §8. This PRD requires only that the format is implemented exactly as
specified there and that the reader/writer round-trip is tested.

### 10.2 Scripted action file

```jsonc
{
  "game": "catan",
  "config": {
    "seed": 123456789,
    "board": "fixed:standard_a",
    "assist": "L1",
    "number_placement": "spiral_no_adjacent_red",
    "interaction_protocol": "decline_only"
  },
  "actions": [
    { "request_id": "d1", "player": 0, "type": "place_settlement", "params": { "vertex": 12 } },
    { "player": 0, "type": "place_road", "params": { "edge": 17 } }
  ]
}
```

`request_id` is optional where unambiguous (FR-21.2).

### 10.3 CLI surface

```
lgbg new   --game catan --seed 123 --board fixed:standard_a [--assist L1]
lgbg play  --script game.json --out runs/demo
lgbg replay runs/demo/games/g-0001.god.jsonl [--print-states]
lgbg verify runs/demo [--strict]
lgbg inspect runs/demo/games/g-0001.god.jsonl --player 2 [--board]
lgbg fuzz  --games 10000 --seeds 1000 [--invariants all]
```

---

## 11. Prerequisite deliverable — games/catan/RULES.md

`RULES.md` is milestone **M0** and blocks all rule implementation
(`ARCHITECTURE.md` §7.9). For every rule area in §8 it MUST state:

1. The rule as implemented.
2. A citation to the official rulebook.
3. Where the rulebook is ambiguous, the chosen interpretation **and the alternative considered**.

The following ambiguities are known and MUST be resolved explicitly:

- Board number-token placement procedure.
- Development-card timing relative to the roll, per card type.
- Win condition timing — whether victory is achievable only on a player's own turn.
- Whether Year of Plenty permits two of the same resource.
- Bank exhaustion during production.
- Road Building when fewer than two roads remain in supply.
- Whether a player may trade with the bank below the required port ratio when the bank lacks the
  requested resource.
- Largest Army and Longest Road vacating on a tie, and re-acquisition afterwards.

---

## 12. Acceptance test plan

| Test | Covers |
|---|---|
| `test_topology_invariants` | FR-7.2, FR-6.10, SC-7 |
| `test_board_loading` | FR-7.4, FR-7.7 |
| `test_setup_snake_order` | FR-8.1 – FR-8.5 |
| `test_decision_queue` | FR-9.1 – FR-9.6 |
| `test_production` | FR-10.1 – FR-10.5, including bank exhaustion |
| `test_building_rules` | FR-11.1 – FR-11.7, including distance rule at exactly 2 |
| `test_robber_and_discards` | FR-12.1 – FR-12.6 |
| `test_dev_cards` | FR-13.1 – FR-13.9 |
| `test_longest_road` | FR-13.10 — branch, break, tie, and vacate cases |
| `test_trading` | FR-14.1 – FR-14.9 |
| `test_victory` | FR-15.1 – FR-15.5 |
| `test_projection_leaks` | FR-16.1 – FR-16.8, SC-6 — one test per hidden field |
| `test_assist_level_equivalence` | FR-17.1 – FR-17.6, SC-8 |
| `test_schema_completeness` | FR-18.1 – FR-18.5 |
| `test_prompt_artefacts` | FR-19.1 – FR-19.4 |
| `test_cli` | FR-20.1 – FR-20.7 |
| `test_scripted_driver` | FR-21.1 – FR-21.4 |
| `test_benchmark_profile` | FR-6.7 — profile is complete and declares positional asymmetry |
| `test_rejection_code_declaration` | FR-6.8, SC-13 |
| `test_declared_invariants` | FR-6.9, FR-22.2 |
| `test_determinism_cross_process` | FR-2.1 – FR-2.7, SC-3 |
| `test_log_round_trip` | FR-3.1 – FR-3.9 |
| `test_tamper_detection` | FR-4.1 – FR-4.7, SC-4 — parametrised over mutation site |
| `test_rejection_invariance` | FR-3.4, SC-5 |
| `test_fuzz_smoke` | FR-22.1 – FR-22.6 (short run in CI) |
| `test_fuzz_full` | SC-2 (scheduled or manual run, not per-commit) |
| `test_core_does_not_import_games` | FR-6.2 |
| `test_plugin_statelessness` | FR-6.5 |
| `test_no_edge_effects` | FR-2.6, FR-15.3, FR-17.6 |
| `test_golden_games` | FR-4.1 – FR-4.7, SC-1 — corpus at ≥ 3 (seed, board) pairs |

---

## 13. Milestones

Each milestone's Definition of Done includes: tests written and passing, `ruff` and `mypy`
clean, and no regression in previously passing tests.

| # | Milestone | Definition of Done |
|---|---|---|
| **M0** | Rule pinning and scaffold | `RULES.md` complete (§11). Repo scaffold, tooling, CI, lockfile. |
| **M1** | Core runtime | `to_canonical_json`, `hash_state`, all three `RandomSource` implementations, `RunConfig`. FR-1, FR-2, FR-5. |
| **M2** | Log and replay engine | Log writer/reader, hash chain, replay, verify, projection replay, tamper detection — validated against a **trivial fixture game**, not Catan, so replay defects are isolated from rules defects. FR-3, FR-4. |
| **M3** | Board | Topology derivation, structural self-check, layout, ports, fixed and random generation, ≥ 3 curated boards. Identifiers frozen here. FR-7. |
| **M4** | State and setup phase | `CatanState`, decision-request machinery, `pending_decisions`, setup snake draft, projection skeleton with allow-list. FR-6, FR-8. |
| **M5** | Turn structure, production, building | Phase machine, dice, production, roads/settlements/cities, piece and bank limits. FR-9, FR-10, FR-11. |
| **M6** | Robber, development cards, awards | Discards, robber, steal, full dev deck and effects, Longest Road, Largest Army. FR-12, FR-13. |
| **M7** | Trading | Maritime ratios and ports, structured player-to-player offers and responses. FR-14. |
| **M8** | Victory and full rule suite | Win detection, terminality, outcome, and the complete rule test matrix. FR-15, §12 rule tests. |
| **M9** | Observation, schemas, prompts, assist levels | Complete projection with leak tests, action and observation schemas, assist-level enforcement, `game.md`, `notation.py`. FR-16, FR-17, FR-18, FR-19. |
| **M10** | CLI and scripted driver | All six commands, scripted action file, interactive recording. FR-20, FR-21. |
| **M11** | Declarations, fuzzer, golden corpus, acceptance | Benchmark profile, rejection-code declaration, declared invariants, full generic harness, ≥ 3 golden games committed, SC-1 through SC-13 demonstrated and recorded. FR-6.7 – FR-6.9, FR-22. |

M2 is deliberately sequenced before any Catan work: it validates the replay machinery against a trivial
game where the only possible defects are in the machinery itself.

---

## 14. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | A rule is implemented from memory and is wrong | High | High | `RULES.md` at M0 with citations; rule changes bump `rules_version` and regenerate goldens |
| R2 | Longest Road computed incorrectly | High | High | Exhaustive simple-path search only (FR-13.10); dedicated test matrix for branch/break/tie/vacate; 100% coverage required (SC-11) |
| R3 | Hidden information leaks into a projection | Medium | High | Allow-list construction (FR-16.5); one leak test per hidden field; 100% coverage on `projection.py` |
| R4 | Determinism broken by a later refactor | Medium | High | Golden corpus in CI; a hash change is a hard failure requiring a deliberate `rules_version` bump |
| R5 | Board identifier scheme changed after records exist, invalidating them | Medium | Medium | Identifiers frozen at M3; golden board fixtures; derivation documented |
| R6 | Plugin interface over-abstracted before a second game exists | High | Medium | Keep the interface minimal and schema-driven; accept that it changes at the second game, and version that change |
| R7 | Scope creep into bots, MCP, or LLM work | Medium | Medium | §4 non-goals are explicit; new scope requires a new PRD |
| R8 | Canonical JSON plus SHA-256 per action becomes the performance bottleneck | Medium | Low | Measure at M2; NFR-2 sets the budget; if needed, hash a compact structural encoding rather than JSON |
| R9 | Catan's rule surface grows during implementation | Medium | Medium | `RULES.md` is the scope fence; anything not in it is a new requirement, not a clarification |
| R10 | Fuzz driver masks defects by exploring only shallow lines | Low | Medium | Multiple driver policies (uniform, resource-seeking, build-seeking) and a coverage report over rule modules |
| R11 | Game-specific logic leaks into the core while building Catan | Medium | High | `test_core_does_not_import_games`; FR-22.2 forbids Catan-specific invariant logic in the harness; review the core diff at every milestone |

---

## 15. Open questions

| # | Question | Blocks | Owner |
|---|---|---|---|
| Q1 | Number and selection criteria for the curated fixed boards | M3 | Maintainer |
| Q2 | Confirm hash width of 16 hex characters | M1 | Maintainer |
| Q3 | Confirm the board identifier derivation before it is frozen | M3 | Maintainer |
| Q4 | Confirm the fuzz driver does not violate the "no bots" non-goal — proposed reading: it is a test harness, never scored, never in a result | M11 | Maintainer |
| Q5 | Confirm the ≥ 90% coverage threshold, with 100% on `longest_road.py` and `projection.py` | M1 | Maintainer |
| Q6 | Whether `play` should support recording interactive sessions into a scripted file in this release or later | M10 | Maintainer |
| Q7 | Whether counter-offers (`accept_decline_counter`) are needed, or `accept_decline` is sufficient for the benchmark | M7 | Maintainer |
| Q8 | Whether the benchmark profile should be declarative data or computed in plugin code | M11 | Maintainer |

---

## 16. Traceability

| Requirement group | Architecture reference |
|---|---|
| FR-1 | §6 (Determinism contract), §6.1 (State hashing) |
| FR-2 | §5.4 (Random draws) |
| FR-3, FR-4 | §8 (Logging and event sourcing) |
| FR-5 | §5.1, §9 |
| FR-6 | §7.1 – §7.4, §7.5, §7.10, §7.11 |
| FR-7 | §7.5 (Spatial structure), §7.6 (Initial configuration) |
| FR-8 | §5.6 (Decision requests), §7.7 (Phase and decision structure) |
| FR-9 | §5.6, §7.7 |
| FR-10 – FR-15 | §7.7, §7.9, §10 (Error model) |
| FR-16 | §7.8 (Hidden information and projection) |
| FR-17 | §9 (Assist levels) |
| FR-18 | §7.3 (Schemas as data) |
| FR-19 | §11 (Prompt layer) |
| FR-20, FR-21 | §4 (Layered architecture) |
| FR-22 | §7.11 (Game-declared invariants), §15.4 (Fuzzing) |

---

## Appendix A — Catan rule reference values

Values below are the requirements this release implements. Each MUST also be pinned with a rulebook
citation in `games/catan/RULES.md` (§11).

| Item | Value |
|---|---|
| Terrain | 4 forest (wood), 4 pasture (sheep), 4 field (wheat), 3 hills (brick), 3 mountains (ore), 1 desert |
| Number tokens | 2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12 (18 tokens, no 7) |
| Structure | 19 hexes, 54 vertices, 72 edges |
| Ports | 9 total: 4 × 3:1 generic, 5 × 2:1 specific (one per resource) |
| Bank | 19 of each resource |
| Player pieces | 15 roads, 5 settlements, 4 cities |
| Road cost | 1 wood, 1 brick |
| Settlement cost | 1 wood, 1 brick, 1 sheep, 1 wheat |
| City cost | 2 wheat, 3 ore |
| Development card cost | 1 sheep, 1 wheat, 1 ore |
| Development deck | 25 cards: 14 knight, 5 victory point, 2 road building, 2 year of plenty, 2 monopoly |
| Victory points | settlement 1, city 2, VP card 1, Longest Road 2, Largest Army 2 |
| Largest Army threshold | 3 played knights |
| Longest Road threshold | 5 continuous roads |
| Win condition | 10 victory points |
| Discard on a 7 | `floor(hand / 2)` from every player holding more than 7 cards |

---

## 17. Sign-off

| Role | Name | Decision | Date |
|---|---|---|---|
| Product owner | | | |
| Architecture owner | | | |
