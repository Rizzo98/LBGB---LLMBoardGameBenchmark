# KANBAN-v1 · PRD-v1 · horizontal slices

## Todo
## In Progress

## Blocked

## Backlog






















### K-038 · Commit golden game 3: a complete, winnable game

  - tags: [slice-4, test, acceptance, sc-1]
  - priority: high
  - workload: Normal
  - defaultExpanded: true
  - steps:
      - [ ] Committed fixture plays to a 10-VP terminal record
      - [ ] Replays with every hash verified
      - [ ] Renders legibly through the CLI
    ```md
    - **Cuts through:** everything built so far
    - **Depends on:** K-037
    - **PRD:** SC-1
    - **Why:** Slice 4 exit, and the single most valuable checkpoint in the release: a complete Catan game, opening draft through winner, that replays.
    ```

### K-039 · Measure performance against NFR-2

  - tags: [slice-4, test, core]
  - priority: low
  - workload: Easy
  - steps:
      - [ ] Single-game simulation time and replay cost measured and recorded
      - [ ] If canonical JSON plus SHA-256 is the bottleneck, that finding is written down while it is still cheap to change
    ```md
    - **Cuts through:** the full pipeline, the profiler, the hash path
    - **Depends on:** K-038
    - **PRD:** NFR-2, risk R8
    ```

### K-040 · Implement the development deck, shuffle and purchase

  - tags: [slice-5, devcards, rng, fr-13]
  - priority: medium
  - workload: Normal
  - steps:
      - [ ] 25 cards with the Appendix A composition
      - [ ] Shuffled at game start from recorded draws
      - [ ] Purchase costs per Appendix A
      - [ ] An empty deck makes the action unavailable
    ```md
    - **Cuts through:** rules/devcards, core/rng, bank, per-player inventory
    - **Depends on:** K-030
    - **PRD:** FR-13.1, FR-13.2
    ```

### K-041 · Enforce development card timing rules

  - tags: [slice-5, devcards, phases, fr-13]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] Not playable on the turn purchased
      - [ ] At most one per turn
      - [ ] Per-card play windows follow the interpretation pinned in RULES.md
      - [ ] The knight-before-roll branch now activates, completing FR-10.1
    ```md
    - **Cuts through:** rules/devcards, turn history, phase machine, rejection codes
    - **Depends on:** K-040, K-022
    - **PRD:** FR-13.3, FR-13.4, FR-10.1
    ```

### K-042 · Implement the knight card

  - tags: [slice-5, devcards, robber, fr-12]
  - priority: medium
  - workload: Easy
  - steps:
      - [ ] Playing a knight runs the same robber flow as a 7: move, then optional steal
      - [ ] Increments the played-knight count
      - [ ] The robber flow is reused, not duplicated
    ```md
    - **Cuts through:** rules/devcards, the robber flow, largest-army counting
    - **Depends on:** K-041, K-027
    - **PRD:** FR-12.6
    ```

### K-043 · Implement the Road Building card

  - tags: [slice-5, devcards, building, fr-13]
  - priority: medium
  - workload: Normal
  - steps:
      - [ ] Two free roads placed through the normal road constraints
      - [ ] When fewer than two roads remain in supply, the shortfall follows the behaviour pinned in RULES.md, with a test
    ```md
    - **Cuts through:** rules/devcards, road building, piece supply
    - **Depends on:** K-041, K-031
    - **PRD:** FR-13.5
    ```

### K-044 · Implement the Year of Plenty card

  - tags: [slice-5, devcards, fr-13]
  - priority: medium
  - workload: Easy
  - steps:
      - [ ] Two resources taken from the bank, subject to availability
      - [ ] Whether duplicates are permitted follows RULES.md, with a test
    ```md
    - **Cuts through:** rules/devcards, bank, resource selection as a sub-decision
    - **Depends on:** K-041
    - **PRD:** FR-13.6
    ```

### K-045 · Implement the Monopoly card

  - tags: [slice-5, devcards, fr-13]
  - priority: medium
  - workload: Easy
  - steps:
      - [ ] All of the named resource transfers from every other player
      - [ ] The transfer is atomic in one event
    ```md
    - **Cuts through:** rules/devcards, every player's hand, events, projection
    - **Depends on:** K-041
    - **PRD:** FR-13.7
    ```

### K-046 · Implement victory point cards and hidden VP

  - tags: [slice-5, devcards, projection, victory, fr-13, fr-16]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] VP cards count toward the owner's total
      - [ ] Excluded from every other player's public total
      - [ ] Leak test asserts no projection, and no notation rendering of it, reveals another player's VP cards
    ```md
    - **Cuts through:** rules/victory, the projection allow-list, leak tests, notation
    - **Depends on:** K-041, K-036
    - **PRD:** FR-13.8, FR-16.4
    - **Why:** This is what makes who-is-leading indeterminate from any player's view, and why the spectator projection is a separate tested artefact.
    ```

### K-047 · Implement Largest Army

  - tags: [slice-5, devcards, victory, fr-13]
  - priority: medium
  - workload: Normal
  - steps:
      - [ ] First to 3 played knights holds the award
      - [ ] Transfer and vacate-on-tie per RULES.md
      - [ ] Behaviour is symmetric with Longest Road and tested the same way
    ```md
    - **Cuts through:** rules/devcards, victory accounting, award transfer, projection
    - **Depends on:** K-042
    - **PRD:** FR-13.9
    ```

### K-048 · Commit golden game 4: a development-card-driven win

  - tags: [slice-5, test, acceptance, sc-1]
  - priority: medium
  - workload: Easy
  - steps:
      - [ ] Committed fixture in which the winner reaches 10 via a development-card effect
      - [ ] Replays with every hash verified
    ```md
    - **Cuts through:** everything in slice 5
    - **Depends on:** K-046, K-047
    - **PRD:** SC-1
    - **Why:** Slice 5 exit: the full base-game rule surface except trading is exercised by a replaying golden game.
    ```

### K-049 · Model port access

  - tags: [slice-6, trading, board, fr-14]
  - priority: medium
  - workload: Normal
  - steps:
      - [ ] A player's available exchange ratios are derived from their coastal settlements and the board's port placement
      - [ ] The derivation is computed, not authored
    ```md
    - **Cuts through:** board ports, topology, a player's coastal settlements, action_domains
    - **Depends on:** K-032, K-013
    - **PRD:** FR-14.1
    ```

### K-050 · Implement maritime trade

  - tags: [slice-6, trading, rules, fr-14]
  - priority: medium
  - workload: Normal
  - steps:
      - [ ] 4:1, 3:1 and 2:1 ratios applied correctly per port access
      - [ ] Bank availability respected
      - [ ] An invalid ratio is rejected with a game code rather than silently accepted
    ```md
    - **Cuts through:** rules/trading, bank, port access, rejection codes
    - **Depends on:** K-049
    - **PRD:** FR-14.1
    ```

### K-051 · Implement player offers and concurrent responses

  - tags: [slice-6, trading, phases, fr-14]
  - priority: high
  - workload: Hard
  - defaultExpanded: true
  - steps:
      - [ ] Only the current player may open an offer
      - [ ] Every non-offering player holding cards receives a response request, concurrently
      - [ ] Offers naming resources the offerer lacks are rejected before broadcast
      - [ ] An offer is cancellable before resolution
    ```md
    - **Cuts through:** rules/trading, decision queue, projection, phase machine
    - **Depends on:** K-050, K-025
    - **PRD:** FR-14.2, FR-14.3, FR-14.4, FR-14.6, FR-14.7
    - **Why:** Second and harder exercise of the decision queue: out-of-turn decisions from several players at once. Blocked on open question Q7, whether counter-offers are needed.
    ```

### K-052 · Implement partner selection and atomic transfer

  - tags: [slice-6, trading, rules, fr-14]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] When several players accept, the offerer chooses; the engine never chooses
      - [ ] The completed trade transfers both sides atomically in one event and replays exactly
    ```md
    - **Cuts through:** rules/trading, decision queue, events, projection
    - **Depends on:** K-051
    - **PRD:** FR-14.5, FR-14.8, FR-14.9
    ```

### K-053 · Commit golden game 5: a completed trade

  - tags: [slice-6, test, acceptance, sc-1]
  - priority: medium
  - workload: Easy
  - steps:
      - [ ] Committed fixture containing a completed player-to-player trade
      - [ ] Replays with every hash verified
    ```md
    - **Cuts through:** everything in slice 6
    - **Depends on:** K-052
    - **PRD:** SC-1
    - **Why:** Slice 6 exit: the base game is feature-complete against PRD section 8.
    ```

### K-054 · Implement assist levels and rejection-detail tiers

  - tags: [slice-7, assist, cli, fr-17, sc-8]
  - priority: high
  - workload: Hard
  - defaultExpanded: true
  - steps:
      - [ ] L0 renders observation only, with minimal rejections that do not leak enumeration through error messages
      - [ ] L1 renders types, costs and parameter domains without enumerating the cross product
      - [ ] L2 renders the full legal action list with alternatives
      - [ ] apply has no notion of assist level and is byte-identical across all three
    ```md
    - **Cuts through:** renderers, action_domains and legal_actions, the rejection formatter, config
    - **Depends on:** K-034, K-030
    - **PRD:** FR-17.1, FR-17.3, FR-17.4
    - **Why:** The single most important benchmark-validity knob. If enumeration leaks at L0 through error messages, a model can brute-force its way from L0 to L2 without anyone noticing.
    ```

### K-055 · Add the assist-equivalence test

  - tags: [slice-7, test, assist, sc-8]
  - priority: high
  - workload: Easy
  - steps:
      - [ ] Running one scripted action file at L0, L1 and L2 produces byte-identical god logs
      - [ ] The only permitted difference is config.assist in the header
    ```md
    - **Cuts through:** config, engine, log, replay
    - **Depends on:** K-054
    - **PRD:** FR-17.2, SC-8
    - **Why:** The test that proves assist level is a clean experimental variable rather than an uncontrolled confound.
    ```

### K-056 · Declare action_schema and enforce conformance during play

  - tags: [slice-7, schemas, core, fr-18]
  - priority: high
  - workload: Hard
  - steps:
      - [ ] A JSON Schema keyed by action type covering every accepted action
      - [ ] Validation happens before rule logic
      - [ ] Unknown action types yield UNKNOWN_ACTION and schema violations yield BAD_PARAMS
      - [ ] A fuzz run asserts every action produced by the game validates against the schema
    ```md
    - **Cuts through:** action_schema.py, validation, every rule module, the fuzzer
    - **Depends on:** K-053
    - **PRD:** FR-18.1, FR-18.2, FR-18.5
    ```

### K-057 · Declare observation_schema

  - tags: [slice-7, schemas, projection, fr-18]
  - priority: medium
  - workload: Normal
  - steps:
      - [ ] Describes the projection shape
      - [ ] Every observation produced during a game validates against it
    ```md
    - **Cuts through:** observation_schema.py, projection, serialisation
    - **Depends on:** K-056
    - **PRD:** FR-18.3, FR-16.8
    ```

### K-058 · Generate tool definitions from the declared schemas

  - tags: [slice-7, schemas, test, fr-18]
  - priority: medium
  - workload: Normal
  - steps:
      - [ ] Tool definitions generated from action_schema with no game-specific code
      - [ ] A test asserts every action type appears with a correct parameter list
      - [ ] No MCP server is built; this proves the plug-and-play claim without pulling v2 scope into v1
    ```md
    - **Cuts through:** the schemas, a generator, a proof test
    - **Depends on:** K-057
    - **PRD:** FR-18.4
    - **Why:** If adding a game required hand-written tool definitions, the plugin system would have failed. This card is the evidence that it did not.
    ```

### K-059 · Write the shared game prompt

  - tags: [slice-7, prompts, notation, fr-19]
  - priority: medium
  - workload: Normal
  - steps:
      - [ ] Rules, notation and action semantics documented with worked examples
      - [ ] No strategy advice, opening recommendations or move evaluation guidance
      - [ ] SHA-256 recorded in prompt_hashes in the header record
      - [ ] A test asserts the file exists, hashes, and contains no advice section
    ```md
    - **Cuts through:** prompts/game.md, notation, the log header's prompt hashes
    - **Depends on:** K-019
    - **PRD:** FR-19.1, FR-19.2, FR-19.3
    - **Why:** Strategy advice in this file would mean the benchmark measures prompt engineering rather than the model. A result without a prompt hash is unreproducible.
    ```

### K-060 · Add notation detail levels

  - tags: [slice-7, notation, prompts, fr-19]
  - priority: low
  - workload: Normal
  - steps:
      - [ ] Full, compact and delta-only renderings, all deterministic and stable
      - [ ] All three consumed by the CLI so their behaviour is observable before an agent ever sees them
    ```md
    - **Cuts through:** notation.py, projection, CLI, the prompt
    - **Depends on:** K-059
    - **PRD:** FR-19.4
    - **Why:** How the state is rendered measurably changes model performance, so renderings must be held constant across models. That makes them a first-class artefact, not a debugging convenience.
    ```

### K-061 · Declare game invariants

  - tags: [slice-8, rules, test, fr-6]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] Resource conservation: per resource, bank plus all hands equals 19
      - [ ] Piece conservation: per player and piece type, supply plus on board equals initial count
      - [ ] check_invariants is pure and RNG-free
    ```md
    - **Cuts through:** check_invariants, state, the generic harness
    - **Depends on:** K-053
    - **PRD:** FR-6.9
    - **Why:** Declared by the plugin so one generic harness can validate any game, including games that do not exist yet.
    ```

### K-062 · Declare the benchmark profile

  - tags: [slice-8, test, fr-6, sc-13]
  - priority: medium
  - workload: Easy
  - steps:
      - [ ] Declares positional asymmetry present, so mirrored pairings are required
      - [ ] Declares outcome shape, variance class and interaction character
      - [ ] Declares the decision-length distribution
      - [ ] A test asserts the profile is complete
    ```md
    - **Cuts through:** the plugin, the runner's future needs, documented experimental design
    - **Depends on:** K-053
    - **PRD:** FR-6.7, SC-13
    - **Why:** Blocked by open question Q8: declarative data or computed in plugin code. Seat order is a real advantage in Catan, so unmirrored pairings silently flatter whoever moves first.
    ```

### K-063 · Audit the rejection-code declaration

  - tags: [slice-8, test, fr-6, sc-13]
  - priority: medium
  - workload: Easy
  - steps:
      - [ ] Every code raised anywhere in a fuzz run appears in rejection_codes()
      - [ ] A test fails on any undeclared code
    ```md
    - **Cuts through:** rejection_codes, every rule module, the metrics surface
    - **Depends on:** K-061
    - **PRD:** FR-6.8, SC-13
    - **Why:** Declaring codes is what makes rejection-code distribution a game-agnostic metric.
    ```

### K-064 · Build the generic fuzz harness

  - tags: [slice-8, fuzz, test, fr-22, sc-2]
  - priority: high
  - workload: Extreme
  - defaultExpanded: true
  - steps:
      - [ ] After every action asserts: no exception, declared invariants, event sufficiency, rejection invariance, projection purity, schema conformance
      - [ ] Asserts termination within a bounded action count, reporting livelock distinctly from a rule failure
      - [ ] Contains no Catan-specific logic of its own
      - [ ] Multiple driver policies: uniform, resource-seeking, build-seeking
      - [ ] Runs against any registered plugin, including the slice-1 fixture game
    ```md
    - **Cuts through:** the harness, declared invariants, schemas, projection, replay
    - **Depends on:** K-061, K-056, K-034
    - **PRD:** FR-22.1 to FR-22.6
    - **Why:** Because invariants are declared rather than hardcoded, this one harness validates every game, present and future. It is a test harness, never scored, never presented as a bot.
    ```

### K-065 · Build the projection leak suite

  - tags: [slice-8, projection, test, fr-16, sc-6]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] One test per hidden field per observer
      - [ ] Asserts non-exposure in the raw projection
      - [ ] Asserts non-exposure in every notation rendering of it
    ```md
    - **Cuts through:** projection, the allow-list, notation, every observer
    - **Depends on:** K-057, K-060
    - **PRD:** FR-16.6, SC-6
    ```

### K-066 · Sweep requirement coverage and build the traceability matrix

  - tags: [slice-8, test, acceptance, sc-9, sc-11]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] Every functional requirement traced to at least one named test
      - [ ] Gaps either filled or explicitly recorded as deferred with a reason
      - [ ] longest_road.py and projection.py at 100 percent coverage
      - [ ] core/ and rules/ at 90 percent or above
    ```md
    - **Cuts through:** all of PRD section 8, the test suite, the traceability table
    - **Depends on:** K-064, K-065
    - **PRD:** SC-9, SC-11
    - **Open question:** Q5, confirm the coverage thresholds (90 percent overall, 100 percent on the two named modules).
    ```

### K-067 · Run the full fuzz campaign and validate performance

  - tags: [slice-8, fuzz, test, sc-2]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] At least 10,000 games across at least 1,000 seeds
      - [ ] Zero uncaught exceptions
      - [ ] All declared invariants hold
      - [ ] Single-game and replay timings within NFR-2
      - [ ] Results recorded
    ```md
    - **Cuts through:** the harness, the whole engine, the NFR budgets
    - **Depends on:** K-066
    - **PRD:** SC-2, NFR-2
    ```

### K-068 · Run acceptance and record the evidence

  - tags: [slice-8, acceptance, sc-1]
  - priority: high
  - workload: Normal
  - defaultExpanded: true
  - steps:
      - [ ] SC-1 through SC-13 each demonstrated by a named command
      - [ ] Command output captured in the acceptance record
      - [ ] Golden corpus of at least 7 games replays end to end
    ```md
    - **Cuts through:** the entire release
    - **Depends on:** K-067
    - **PRD:** section 5, all SC
    - **Why:** Slice 8 exit, and the release exit. Nothing in this project is accepted on the basis of a suite that merely passes; it is accepted on the basis of named commands whose output is recorded.
    ```

## Done

### K-001 · Pin Catan rules in games/catan/RULES.md

  - tags: [slice-0, docs, rules, fr-6, sc-12]
  - priority: high
  - workload: Normal
  - defaultExpanded: true
  - steps:
      - [x] Every rule area in PRD-v1 section 8 is stated and cited to the official rulebook
      - [x] All eight listed ambiguities resolved with chosen interpretation AND the alternative considered
      - [x] Board composition, costs, deck composition and VP values confirmed against the rulebook, not copied from the PRD
      - [x] Reviewed against PRD-v1 section 8 before any rules code is written
    ```md
    - **Cuts through:** rules authority, PRD section 11, every later rules card
    - **Depends on:** nothing
    - **PRD:** section 11, SC-12
    - **Why:** First because every rules card downstream is unverifiable without it. A wrong rule is the one defect that cannot be detected later.
    - **Evidence:** `lgbg/games/catan/RULES.md` (1597 lines, LF-only, 124765 bytes), written before any rules code. Seven sources are retrieved and cited, with a precedence pinned in section 2.1: the CATAN Studio 6th-edition rulebook (CN3081, April 2025) is primary, the World Championship 2025 tournament rules win where they say they do, the 5th-edition Games Rules & Almanac, the 25th-anniversary basic rules, the official base-game FAQ and the KOSMOS Big Box manual fill the rest. All eight ambiguities are resolved in section 5 with the alternative considered; section 2.3 lists eleven claims for which no primary source exists, each pinned as a project decision. Section 6 reproduces all 16 Appendix A rows with citations, and no Appendix A *value* disagrees with the rulebook.
    - **Pointers later cards must use:** `rules_version = "catan-rules-1"` (section 1.2; any pinned-rule change bumps it and invalidates the golden corpus). Section 3.1 pins all nine random draw sites with their kind, args and purpose labels, including "two independent randint(1,6), never one randint(2,12)" and "purchase performs no draw" - K-023, K-027 and K-040 must use those labels. Section 5.10 pins 22 further interpretations, notably that Longest Road is the maximum over simple paths *and* simple cycles: a simple-path-only search would contradict the FAQ's six-roads-in-a-hexagon answer.
    - **One claim is verified rather than assumed:** the pinned number-token sequence produces zero adjacent 6/8 pairs over all 114 (starting corner, desert position) configurations, whereas ascending or descending numeric order produces adjacent reds in all 114 (section 2.3).
    - **PRD corrections (D-1 to D-4, section 6.2):** no Appendix A value disagrees, but four PRD statements need correction: 54 vertices and 72 edges are *derived*, not stated by any rulebook; FR-10.4's general case is all-or-nothing per resource, with a partial grant only when exactly one player is affected; FR-8.4 grants one card *per adjacent hex*, not one of each resource; FR-10.1's `(knight)` is an example, since any playable development card may precede the roll. Later cards must follow RULES.md: K-018 (FR-8.4), K-024 (FR-10.4) and K-022 (FR-10.1).
    ```

### K-002 · Scaffold repo, tooling, CI and lockfile

  - tags: [slice-1, infra, fr-6]
  - priority: high
  - workload: Normal
  - steps:
      - [x] ruff and mypy run in CI and locally
      - [x] Custom ruff rule banning import random outside core/rng.py is active and demonstrated to fire on a deliberate violation
      - [x] Fresh clone runs the full test suite with one documented command
      - [x] Lockfile pinned; Python 3.12+ declared
    ```md
    - **Cuts through:** packaging, lint, typing, CI, the random-import ban
    - **Depends on:** nothing
    - **PRD:** NFR-4, NFR-5, NFR-6, NFR-7, NFR-8
    - **Evidence:** gate is `uv run python scripts/gate.py` (lint, format, mypy, pytest). tests/tooling/test_no_ambient_randomness.py proves the TID251 ban fires on a deliberate import and that the exempt path is genuinely exempt. The one documented command was run against a fresh `git clone` in a temp directory: gate passed. uv.lock committed and `uv sync --locked` verified.
    ```

### K-003 · Implement canonical JSON and state hashing

  - tags: [slice-1, core, fr-1]
  - priority: high
  - workload: Easy
  - steps:
      - [x] to_canonical_json is the single serialisation path used for hashing and replay
      - [x] Sorted keys, no insignificant whitespace, ensure_ascii true
      - [x] hash_state returns a truncated SHA-256 digest from one named width constant
      - [x] A fixed test vector pins the exact bytes so accidental changes are caught
    ```md
    - **Cuts through:** core/canonical, core/types, the fixture game encoder
    - **Depends on:** K-002
    - **PRD:** FR-1.1 to FR-1.5
    - **Evidence:** tests/core/test_canonical_json.py pins the canonical bytes and digest of a fixed vector; tests/tooling/test_layering.py asserts json.dumps is called only in core/canonical.py, which is what makes FR-1.1 a fact rather than an intention. Floats and non-string keys are rejected as determinism guards. Hash width confirmed at 16 hex characters, resolving Q2 as proposed by the PRD. FR-1.5 (encode_state totality) is asserted by the fuzzer at K-064.
    ```

### K-004 · Implement the RNG trio and recorded draws

  - tags: [slice-1, core, rng, fr-2]
  - priority: high
  - workload: Normal
  - steps:
      - [x] Seeded, Replay and Null sources behave per ARCHITECTURE section 5.4
      - [x] Purpose labels come from module constants, never inline strings
      - [x] Replay with a reordered draw fails, naming the action, draw index, expected purpose and actual purpose
      - [x] NullRandomSource raises on any draw
    ```md
    - **Cuts through:** core/rng, core/types, determinism tests
    - **Depends on:** K-003
    - **PRD:** FR-2.1 to FR-2.7
    - **Evidence:** tests/core/test_rng.py (17 tests). A reordered draw reports `action #47 draw #0: expected purpose 'dice_roll', got 'random_selection'`; an unconsumed recorded draw is reported by assert_exhausted. tests/tooling/test_layering.py fails the build on a literal passed as a purpose, which is what makes FR-2.3 enforceable rather than advisory. Both real sources are assigned to a `RandomSource`-typed variable, so the protocol conformance is checked by mypy on every run.
    ```

### K-005 · Implement RunConfig and strict key validation

  - tags: [slice-1, core, config, fr-5]
  - priority: medium
  - workload: Easy
  - steps:
      - [x] Config round-trips through the header record exactly
      - [x] assist defaults to L1; rejection_detail defaults to the matching tier but is independently overridable
      - [x] Unknown or misspelled keys are rejected with a clear error rather than silently ignored
    ```md
    - **Cuts through:** core/config, the log header, CLI arguments
    - **Depends on:** K-003
    - **PRD:** FR-5.1 to FR-5.4
    - **Evidence:** tests/core/test_config.py (18 tests). The header mapping is pinned to its documented flat shape and round-trips exactly, including an explicit rejection_detail override. Game options are carried opaquely and merged flat, so the core never learns what a board is (P11); a game option may not shadow a core key, and an undeclared key is an unknown key.
    ```

### K-006 · Define the Game protocol and plugin registry

  - tags: [slice-1, core, registry, fr-6]
  - priority: high
  - workload: Normal
  - steps:
      - [x] Protocol of ARCHITECTURE section 7.1 exists in full
      - [x] register_game decorator registers by name
      - [x] Entry-point discovery via importlib.metadata group lgbg.games works
      - [x] A test asserts lgbg.core never imports lgbg.games
    ```md
    - **Cuts through:** core/game, every game plugin, the layering test
    - **Depends on:** K-003
    - **PRD:** FR-6.1 to FR-6.6
    - **Evidence:** tests/core/test_game_registry.py (14 tests). The protocol's member set is asserted against the architecture's list, member by member. The registry hands out one shared instance per game (that is what makes FR-6.5 testable) and refuses a plugin that declares no name, rules_version or schema_version. Entry-point discovery is tested by substituting the loader, and the test asserts the group name is lgbg.games. tests/tooling/test_layering.py parses the core's imports with `ast` and fails if any reaches lgbg.games, so a docstring mention cannot mask a real import.
    ```

### K-007 · Build the fixture game as a permanent test canary

  - tags: [slice-1, test, registry, fr-6]
  - priority: medium
  - workload: Easy
  - defaultExpanded: true
  - steps:
      - [x] A minimal toy game with two or three action types, one random draw, and a terminal condition
      - [x] Implemented purely as a test asset, not shipped as a real game
      - [x] Exercises the full protocol without any real rules
      - [x] Retained permanently after slice 1 and re-run by the slice-8 harness
    ```md
    - **Cuts through:** the registry, every core component, all later integration tests
    - **Depends on:** K-004, K-005, K-006
    - **PRD:** FR-6.1
    - **Why:** Deliberate exception to horizontal slicing. It isolates pipeline defects from rules defects: a hash mismatch here is in the machinery; a hash mismatch in slice 2 could be either, and by then the machinery is already proven.
    - **Evidence:** tests/games/fixture_game.py and tests/games/test_fixture_game.py (24 tests). Three action types (take, gamble, spend), one recorded draw, a limited bank shared by two players, hidden per-player holdings, a token-conservation invariant, and a terminal condition. It already exhibits two behaviours Catan depends on: an exhausted bank makes an action unavailable rather than erroring, and a gamble replayed from its recorded draw reaches a byte-identical state. Two interleaved games through one shared instance cannot interfere (FR-6.5).
    ```

### K-008 · Implement the log writer and reader

  - tags: [slice-1, core, log, fr-3]
  - priority: high
  - workload: Normal
  - steps:
      - [x] Header, action and terminal records written in order with a monotonic seq
      - [x] Rejected actions produce a record whose state_hash equals state_hash_prev
      - [x] A truncated file reports truncation rather than raising an opaque parse error
      - [x] Unknown schema major version is rejected clearly
      - [x] No timestamp, hostname or pid appears in the god log; they go to the sidecar
    ```md
    - **Cuts through:** core/log, core/canonical, the fixture game, the sidecar split
    - **Depends on:** K-003, K-007
    - **PRD:** FR-3.1 to FR-3.9
    - **Evidence:** tests/core/test_log.py (18 tests). Records are written through to_canonical_json, so the log and the hash chain share one serialisation path. Truncation is reported distinctly from malformation, an unknown record type is refused (FR-3.9), a gap in the action sequence is refused by the writer and again by the reader, and a test asserts the god log contains no at/host/pid key while the sidecar carries all three. The writer flushes per record, and a test reads the file while it is still open to prove a crash leaves a parseable prefix.
    ```

### K-009 · Implement replay, verify and projection replay

  - tags: [slice-1, core, replay, fr-4]
  - priority: high
  - workload: Hard
  - defaultExpanded: true
  - steps:
      - [x] replay rebuilds state after every record and verifies both hashes
      - [x] verify checks the chain without materialising intermediate states
      - [x] projection_replay rebuilds one player's observation sequence
      - [x] Every failure kind reports the offending seq and the reason: hash mismatch, RNG purpose mismatch, RNG exhaustion, event mismatch, unknown action
    ```md
    - **Cuts through:** core/replay, core/log, core/rng, the fixture game
    - **Depends on:** K-008
    - **PRD:** FR-4.1 to FR-4.7
    - **Why:** The heart of the release. Everything downstream is computed from records this card makes trustworthy.
    - **Evidence:** tests/core/test_replay.py (23 tests) plays the fixture game into a real record and then tampers with it at each mutation site: the state before an action, the state after one, the action itself, an undeclared action type, a draw value, a draw purpose, a dropped draw, a surplus draw, an event payload, the initial state hash, and three fields of the terminal record. Each failure names its kind and its seq, e.g. `seq 1: hash_mismatch: ...`. Replay runs through the normal apply path, so there is no second implementation of the rules, and a recorded rejection replays with an unchanged hash (SC-5). verify keeps one state in a deque while consuming the chain, which is what makes FR-4.4's cheap corpus check real.
    ```

### K-010 · Wire the CLI skeleton against the fixture game

  - tags: [slice-1, cli, fr-20, fr-21]
  - priority: medium
  - workload: Normal
  - steps:
      - [x] new, play, replay and verify work end to end against the fixture game
      - [x] verify exits non-zero and names the seq on failure
      - [x] Expected failures print a message, never a Python traceback
    ```md
    - **Cuts through:** CLI, config, log, replay, the registry
    - **Depends on:** K-009
    - **PRD:** FR-20.1 to FR-20.4, FR-20.7
    - **Evidence:** tests/cli/test_cli.py (19 tests) runs the commands in process, and the whole path was also run from a shell: `new` printed the opening decision, `play` recorded a scripted game, `replay --print-states` printed every intermediate state with both hashes, `verify` reported the counts, and after a single tampered hash `verify` exited 1 with `seq 0: hash_mismatch: state_hash is deadbeef... but replay produced ...`. A rejected action stops the driver with a sentence on stderr and exit 1, and the record still ends with a terminal line, because the record of a failed run is what one needs afterwards.
    - **Added:** `lgbg/core/run.py` (GameRun) is the runtime loop this card needed: one record per attempt, both hashes, the draws of that action, core-level request validation, and an explicit finish (FR-3.2, FR-9.2, FR-15.5). Also `--plugin MODULE` on every command, the explicit-import discovery path of ARCHITECTURE.md section 7.4, without which a game outside the engine could not be driven by hand.
    - **Fixture finding:** the fixture game could reach a state where the player to act had no legal move (the bank drained into the other player's holding). A gamble is now always legal and gains nothing on an empty bank, so the game cannot livelock - the property FR-22.4 will assert.
    ```

### K-011 · Add determinism and tamper-detection tests

  - tags: [slice-1, test, replay, fr-4, sc-3, sc-4]
  - priority: high
  - workload: Normal
  - steps:
      - [x] Identical inputs produce identical hash chains across two processes with different PYTHONHASHSEED
      - [x] Parametrised tamper test mutates a record action, a draw value, a draw purpose, an event payload, state_hash_prev and state_hash
      - [x] Each mutation fails verification at the correct seq
    ```md
    - **Cuts through:** determinism contract, CLI, log, replay
    - **Depends on:** K-010
    - **PRD:** SC-3, SC-4
    - **Why:** Slice 1 exit: play then verify on the fixture game passes, and the tamper suite catches every mutation site.
    - **Evidence:** tests/core/test_determinism_cross_process.py plays the same game in two child interpreters under PYTHONHASHSEED 0 and 987654321 and compares the records byte for byte, asserting first that the two processes really did have different hash seeds. tests/core/test_tamper_detection.py is a parametrised table over 11 mutation sites - the recorded action, a draw value, a draw purpose, a draw argument, an event payload, state_hash_prev, state_hash, a dropped draw, a surplus draw, the terminal hash and the header's initial hash - each asserting both the seq and the kind of failure, with an untampered control so a verifier that failed on everything could not pass.
    - **Slice 1 exit:** `lgbg new`, `play`, `replay --print-states` and `verify` all run end to end against the fixture game; a recorded game replays with every hash verified; and every mutation named by SC-4 is caught at the right seq with the right reason. The replay machinery is proven before a single rule of Catan exists (PRD M2).
    ```

### K-012 · Derive board topology and assert structural invariants

  - tags: [slice-2, board, test, fr-7, sc-7]
  - priority: high
  - workload: Extreme
  - defaultExpanded: true
  - steps:
      - [x] Vertices and edges derived from hex axial coordinates; no authored adjacency or incidence tables anywhere
      - [x] Exactly 19 hexes, 54 vertices, 72 edges, with symmetric adjacency
      - [x] Integer identifiers assigned by canonical sort of derived coordinates, and the derivation documented
      - [x] Self-check asserts counts, adjacency symmetry, degree distribution, coast versus interior classification
      - [x] Self-check runs as a test at import under test
    ```md
    - **Cuts through:** board/topology, the coordinate model, the structural invariant test
    - **Depends on:** K-002
    - **PRD:** FR-7.1, FR-7.2, FR-7.3, FR-6.10, SC-7
    - **Why:** Largest card in slice 2 and on the critical path for slices 2 through 6. Identifiers get frozen here: they appear in every recorded action, so changing the derivation invalidates every existing record.
    - **Open question:** Q3, answered by this card as proposed below; no record exists yet, so a change is still free until the first golden game (K-021).
    - **Evidence:** tests/games/test_topology.py (20 tests), lgbg/games/catan/board/topology.py. A corner is identified by the sorted cube triple of the three hexes meeting there, so vertices are those triples deduplicated; edges are the segments between consecutive corners, deduplicated as vertex pairs. Identifiers: hexes by (row, column), vertices by their sorted cube triple, edges by their sorted vertex pair - all sorts of derived coordinates, never of enumeration order.
    - **Why the derivation is real, not a table in disguise:** a seven-hex board (a shape nobody authored) derives a different, still consistent board; and reversing the input order changes no identifier. Euler `V - E + H = 1` is asserted for boards of radius 1, 2 and 3, not only the standard one.
    - **Counts derived independently of the implementation:** 19 hexes, 54 vertices, 72 edges; vertices 24 interior / 12 two-hex / 18 boundary; edges 42 interior / 30 coastal (the 30 the nine ports go on); degrees 36 of 3 and 18 of 2. The module docstring reproduces the argument: the corner and edge handshakes plus Euler.
    - **Self-check:** `check_structure` reports broken incidence in both directions, degree and classification disagreements, the handshakes and Euler. It runs at import in the test module (ARCHITECTURE.md 7.5), and `test_the_structural_self_check_has_teeth` drops an edge and asserts it is reported, so the check cannot be vacuous.
    ```

### K-013 · Build board layout, ports, number tokens and one curated board

  - tags: [slice-2, board, fr-7]
  - priority: high
  - workload: Normal
  - steps:
      - [x] Canonical hex arrangement implemented
      - [x] 9 ports placed with the 4 by 3:1 and 5 by 2:1 distribution
      - [x] Number placement follows the rule pinned in RULES.md
      - [x] One curated fixed board loads from JSON data
      - [x] Random generation consumes recorded draws
    ```md
    - **Cuts through:** board/layout, board/generation, curated board data loading
    - **Depends on:** K-012
    - **PRD:** FR-7.4, FR-7.5, FR-7.6
    - **Why:** Blocked by open question Q1: how many curated boards, and chosen for what property.
    - **Evidence:** tests/games/test_board_layout.py (61 tests), lgbg/games/catan/board/layout.py, generation.py, boards/standard_a.json.
### K-014 · Define CatanState and its serialisation

  - tags: [slice-2, state, core, fr-1]
  - priority: high
  - workload: Normal
  - steps:
      - [x] Frozen, slotted dataclasses; integers only; no floats, sets or unordered iteration
      - [x] encode_state is total: every reachable state serialises without error
      - [x] The initial state hashes deterministically for a given seed and board
    ```md
    - **Cuts through:** state.py, core/canonical, the hash chain
    - **Depends on:** K-013, K-003
    - **PRD:** FR-1.5
    - **Evidence:** tests/games/test_catan_state.py (13 tests), lgbg/games/catan/state.py. The state is frozen and slotted (assigning to a field raises, and there is no `__dict__`); a fully populated state round-trips through encode/decode with every field intact; the encoded form contains only JSON types and no floats, asserted by walking it; and the opening state hashes identically for the same seed and differently for another, because the deck differs.
    - **The field set is fixed now, deliberately.** Later slices need development cards, awards and a trade offer, and `encode_state` is what every recorded hash is computed from: a field added after the golden corpus exists would invalidate it. Fixing the shape in slice 2 costs nothing. The one exception is `Phase`, which is stored by name, so later slices may add phases without touching a hash.
    - **Encoding choices:** counts sit in a canonical order (`RESOURCE_ORDER`, `CARD_ORDER`) written as a list, with the orders pinned as constants and asserted, because a silently reordered tuple would reinterpret every recorded hand. Occupancy is sparse - `[site, seat]` sorted by site - because a list of seventy-two minus-ones is not something a person reads. The board is encoded with the state (terrain, tokens, ports, its name and the corner the tokens were laid from), so the hash covers the board that decided everything that happened on it.
    - **Correction (found while working K-026):** the `RESOURCE_ORDER` this card shipped was wood, brick, wool, wheat, ore - an order the engine had picked for itself. RULES.md section 3 pins the canonical order as **brick, wood, wool, wheat, ore**, the order in which the rulebook lists the five resource-card stacks, and states that every list, projection and hash that enumerates resources uses it. The order of the counts inside a hand is written into every encoded state, so this was a wrong hash basis and not a cosmetic difference. The `Resource` enum and `RESOURCE_ORDER` were brought into line, `rules_version` went from `catan-rules-2` to `catan-rules-3` with the reason recorded in RULES.md section 1.2, and the golden fixture was regenerated: the initial-state hash is unchanged (the opening position is uniform) and every hash after the first endowment moved. The pin is now asserted in two places rather than one - tests/games/test_catan_state.py for the constant, and tests/golden/catan/setup_game.god.jsonl for every hand a game actually records.
- **Second correction (K-026):** the field set this card fixed was one field short. The robber phase has two steps - the robber moves, and then a victim is chosen - and the move leaves no trace, because a robber that has just moved sits on a hex exactly like one that has not. A phase rule is a function of the state and cannot see which request it has already handed out, so `robber_moved_at` (the `phase_index` the move happened in) was added; the encoded state carries it, `rules_version` went to `catan-rules-4`, and the golden fixture was regenerated. The card's own reasoning held: the field set is worth fixing early *because* adding one is expensive - expensive here means a version bump and one regenerated fixture, which is the price of getting the shape wrong, paid while it was still small.
    - **One draw:** the opening state shuffles the 25-card deck through draw D5, asserted with its pinned label and argument; nothing else in the opening consumes randomness.
    - **Not yet:** `initial_state` builds the opening position, but no Game plugin is registered yet. That arrives with the setup phase (K-017), which is the first card that needs decisions rather than just a state.
    ```

### K-015 · Build projection v0 for board and pieces

  - tags: [slice-2, projection, board, fr-16]
  - priority: medium
  - workload: Normal
  - steps:
      - [x] observe returns the board, the robber position and every player's placed pieces
      - [x] Built from an explicit allow-list, never a deny-list
      - [x] NullRandomSource proves observe consumes no randomness
      - [x] Resource hands are deliberately absent; they arrive in slice 3
    ```md
    - **Cuts through:** projection.py, state, the observation schema sketch, CLI inspect
    - **Depends on:** K-014
    - **PRD:** FR-16.5, FR-16.7
    - **Evidence:** tests/games/test_catan_projection.py (18 tests), lgbg/games/catan/projection.py. The observation is assembled by walking a declared list of (name, extractor) pairs, so the keys are exactly the allow-list and a field added to the state cannot reach anyone's view until somebody names it here. That is FR-16.5 as a mechanism rather than a promise: `test_the_observation_holds_exactly_the_allowed_fields` fails the moment the two diverge.
    - **Two projections, tested apart:** the spectator's is the player's allow-list plus the fields the god view holds back, and the test asserts it is a strict superset rather than a copy. With hidden victory-point cards, who is ahead is not determinable from any player's view, which is why the spectator projection is its own artefact (FR-16.7).
    - **Public now:** the board with terrain and tokens, the nine ports, the robber, every player's placed settlements, cities and roads, the supply of unbuilt pieces, the bank, the turn, the phase, the round, the dice and the two awards. Hidden now, on purpose: hands, the deck, cards bought this turn. Each arrives with the slice that needs it and with the leak test that proves it does not escape (FR-16.6, K-065).
    - **Purity:** observe takes no source of randomness at all - it is not handed one to misuse - and a test asserts that observing twice gives the same answer and leaves the encoded state unchanged (FR-2.6). The observer is a parameter rather than a flag, so a view that differs between players will need no new interface.
    ```

### K-016 · Implement the phase machine and decision requests

  - tags: [slice-2, phases, core, fr-9]
  - priority: high
  - workload: Hard
  - defaultExpanded: true
  - steps:
      - [x] Phases produce decision requests rather than driving control flow
      - [x] Several requests can be open simultaneously
      - [x] Resolution order is deterministic and independent of arrival order
      - [x] Every transition emits a phase_started event and a phase record
    ```md
    - **Cuts through:** phases.py, pending_decisions, state, events, the log's phase records
    - **Depends on:** K-014
    - **PRD:** FR-9.1 to FR-9.4
    - **Why:** The decision queue is the central abstraction. A turn counter cannot express concurrent or out-of-turn decisions, and special-casing them is where rule bugs live.
    - **Evidence:** tests/games/test_catan_phases.py (16 tests) plus a core test for the phase record in tests/core/test_run.py. A phase is a declared rule: who is asked, and where the game goes once nobody is; pending_decisions derives from that table, so a phase that exists only as a name cannot silently answer with nothing - it raises. Several decisions open at once is exercised through the discard phase (three players over the limit, in seat order); the transition into it on a seven arrives with K-025, and the robber phase's rules with K-026.
    - **Resolution order:** seat order, then request identifier. The test feeds resolution_order a reversed list, and rebuilds it from a state reached a different way, because a record produced by four players deciding concurrently must be byte-identical to one produced by them deciding in turn (FR-9.3).
    - **Events and records:** the machine emits phase_started, and the runtime keys on that event type to write a phase record - so a game never invents a record type of its own (FR-3.9), and a log can be read without replaying it. The event name is a core constant, and the record is verified by replay like everything else.
    - **Design change found by a test:** the draft's progress was a setup_selections counter in the state, which the machine would have had to keep consistent with the pieces on the board. Two counters that must agree is a bug farm, so the counter is gone and progress is derived from the placements: the settlement phase closes when settlements lead roads. Changing the state's shape costs nothing today, and would cost a corpus tomorrow.
    - **Why the whole phase vocabulary is named now:** a phase is stored by name in the encoded state, and the encoding is what every hash covers. Naming every phase once, in the slice that is cheap to change, avoids renaming one later and invalidating the golden corpus.
    ```

### K-017 · Implement the setup snake draft

  - tags: [slice-2, rules, setup, fr-8]
  - priority: high
  - workload: Normal
  - steps:
      - [x] Order 0,1,2,3,3,2,1,0
      - [x] Each selection is a settlement placement followed by an adjacent road
      - [x] Distance rule and connectivity enforced with specific game rejection codes
      - [x] Setup expressed entirely as decision requests, with no special-cased code path
    ```md
    - **Cuts through:** rules/setup, phase machine, projection, rejection codes
    - **Depends on:** K-016
    - **PRD:** FR-8.1, FR-8.2, FR-8.3, FR-8.5
    - **Evidence:** tests/games/test_catan_setup.py (21 tests), lgbg/games/catan/rules/setup.py, and the plugin that makes it a game: lgbg/games/catan/game.py, registering as `catan` with `rules_version catan-rules-1`. A whole draft of sixteen actions runs through the ordinary runtime and its record replays with every hash verified, which is the slice's exit condition.
    - **The snake is derived, not written down:** `setup_order(players)` returns seats ascending then descending, so the rulebook's 0,1,2,3,3,2,1,0 is a consequence of the shape rather than a literal a different seat count would silently falsify. The draft's progress is derived from the roads on the board, and the seat is asserted to follow the snake across all eight steps.
    - **Every refusal is its own code:** an occupied vertex (`VERTEX_OCCUPIED`), a vertex one edge too close (`TOO_CLOSE`, with the blocking vertices in the details), an occupied edge (`EDGE_OCCUPIED`), a road that does not attach to the settlement just placed (`NOT_CONNECTED`), an exhausted supply (`NO_PIECES_REMAINING`), and an off-board site (`BAD_PARAMS`). A metric that cannot tell an occupied vertex from a too-close one measures nothing.
    - **No special case for setup:** the draft is a phase in phases.py and two rule functions, sharing the action path with everything that follows (FR-8.5). The one state field it needed is `setup_vertex`, the vertex whose road is still owed, because the rule is that the road attaches to *this* settlement rather than to any of the player's settlements.
    - **The plugin exists now:** every protocol member is answered, honestly for the slice - the schema declares the two setup actions, victory points count settlements and cities (dev cards and awards arrive with K-036), the invariants are the two conservation laws, and the benchmark profile is the shape Catan has (K-062 audits it). `lgbg new --game catan` now prints a real opening decision.
    ```

### K-018 · Implement the bank and starting endowment

  - tags: [slice-2, rules, setup, fr-8]
  - priority: medium
  - workload: Easy
  - steps:
      - [x] Bank holds 19 of each resource
      - [x] Second settlement grants one of each adjacent non-desert resource, limited by bank supply
      - [x] Total resources conserve across the transaction
    ```md
    - **Cuts through:** rules/setup, bank state, projection, the conservation invariant sketch
    - **Depends on:** K-017
    - **PRD:** FR-8.4
    - **Evidence:** tests/games/test_catan_endowment.py (17 tests), lgbg/games/catan/rules/setup.py. The bank starts with 19 of each resource, a second settlement is endowed immediately, and every grant is drawn from the bank, so bank plus all hands is 19 per resource before and after - asserted after every placement of a whole draft through the plugin's own check_invariants.
    - **The criterion's wording is the PRD's shorthand, and RULES.md corrects it.** FR-8.4 says one of each resource from the adjacent non-desert hexes; correction D-3 pins one card **per adjacent hex**, of that hex's type, so two forest hexes next to one settlement grant two wood. That is what is implemented, and what test_two_hexes_of_the_same_terrain_grant_two_cards asserts. The distinction is the whole reason a player chooses a corner, so it is not a wording detail.
    - **Exhaustion is defined, not accidental:** the entitlements are taken in the order the second settlements were placed - seats 3, 2, 1, 0 - which falls out of endowing immediately rather than being a separate rule, and a short bank gives what remains while the shortfall is lost (RULES.md 4.3 item 8, a pinned project decision with no primary source). The endowment event names what was granted and what was lost, so the record explains a shortfall instead of merely containing one.
    - **A test double, and why:** the curated board's balance property is that no vertex sees the same terrain twice, so the two-hexes-two-cards case cannot be exercised on it. The test builds a board with two forest hexes at one vertex - a deliberate double, not a board the engine can generate.
    ```

### K-019 · Implement notation v0 for board rendering

  - tags: [slice-2, notation, cli, fr-19]
  - priority: medium
  - workload: Normal
  - steps:
      - [x] A full and a compact rendering of a projection, both stable and deterministic
      - [x] Both are consumed by the CLI so a human can follow a game without reading JSON
      - [x] The renderer is the single source used later by prompts and MCP resources
    ```md
    - **Cuts through:** notation.py, projection, CLI, later the prompt
    - **Depends on:** K-015
    - **PRD:** FR-19.4
    - **Evidence:** tests/games/test_catan_notation.py (14 tests), lgbg/games/catan/notation.py, plus two CLI tests driving `replay --print-states` and `--compact` against a real Catan record.
    - **The board is laid out as a board.** The hexes are numbered row by row, and the renderer derives the rows from how many hexes there are: a hexagon of radius r has 3r(r+1)+1 hexes in rows of r+1 ... 2r+1 ... r+1, so the full rendering reproduces the shape - five rows of 3, 4, 5, 4, 3 - rather than listing nineteen lines. Spatial reasoning is one of the things this benchmark measures, so the rendering must not flatten the board.
    - **Two details that differ only in shape.** Full is aligned and multi-line; compact is one line per projection for a token budget. A test asserts that the facts of one are present in the other, so a rendering cannot quietly lose something.
    - **The renderer never decides what may be seen.** It renders the projection it is handed, field by field, and a field the projection left out cannot appear - asserted by rendering one player's view and the spectator's and checking that hands appears in exactly one of them. An unrecognised field is rendered rather than dropped, deliberately: rendering fails open, because the allow-list in projection.py is the only gate.
    - **The seam that keeps the CLI game-agnostic:** a `render` member on the Game protocol, so a game declares how its own projections are written down. The CLI calls it without knowing what a board is (ARCHITECTURE.md 11.3), and the prompt generator and MCP resources will call the same one. Adding a protocol member is the planned revision of ARCHITECTURE.md 17.5, not a workaround.
    - **A rendering is not the record.** The hashed state is still `encode_state`; notation is a projection of a projection, so a change of wording cannot invalidate a record - and the tests keep that distinction by asserting stability rather than the exact text of a paragraph.
    ```

### K-020 · Run the CLI against real Catan

  - tags: [slice-2, cli, fr-20, fr-21]
  - priority: medium
  - workload: Normal
  - steps:
      - [x] lgbg new --game catan prints the opening decision
      - [x] play accepts a scripted file and drives the draft
      - [x] inspect --board renders the board
      - [x] Scripted driver resolves an unambiguous request without an explicit request_id and errors when ambiguous
    ```md
    - **Cuts through:** CLI, registry, config, phases, notation, log, replay
    - **Depends on:** K-017, K-019
    - **PRD:** FR-20.5, FR-21.1 to FR-21.4
    - **Open question:** Q6, whether play records interactive sessions into a scripted file in this release.
    - **Evidence:** eight new CLI tests in tests/cli/test_cli.py, plus a shell run of the whole surface. `new --game catan` prints the opening decision and the initial state hash; `play --script` drives a whole sixteen-action draft and the record verifies; `inspect --board` prints the board as a board, `inspect --player 1` prints that seat's own view, and with no player it prints the spectator's god view; and `verify` accepts the run.
    - **A defect found and fixed on the way:** `legal_actions` offered *every* empty vertex and *every* empty edge, so a driver that trusted it would have recorded rejections it did not choose. Enumeration is now filtered by the rules that will judge it - the distance rule for a settlement, incidence to the settlement just placed for a setup road - and the draft's fixture is recorded by asking the game for its legal actions, so the fixture cannot drift from the rules. A test asserts every enumerated action is accepted, which is what would have caught it.
    - **Ambiguity is an error, not a guess** (FR-21.2): with two decisions open for one player, an action that names neither fails with both request identifiers in the message. The test uses an out-of-tree plugin with two open requests, which is also the case the Catan discard phase will exercise at K-025.
    - **Q6 answered as 'not this release':** `play --interactive` reads one JSON action per line from standard input, so a game can be driven by hand (FR-20.2), but an interactive session is not written back into a scripted file. The record on disk is still a full record, so a session can be replayed, verified and inspected like a scripted one; recording is a convenience, not a gap in the evidence.
    - **`--board` is the game's extra detail level.** The CLI stays game-agnostic: it prints what the game's own renderer says a projection looks like (ARCHITECTURE.md 11.3). `full` and `compact` are required of any game; `board` is Catan's own.
    ```

### K-021 · Commit golden game 1: setup through terminal

  - tags: [slice-2, test, acceptance, sc-1]
  - priority: medium
  - workload: Easy
  - steps:
      - [x] A scripted setup-only game is committed as a fixture
      - [x] Its god log replays with every hash verified
      - [x] It fails loudly if any rule in slice 2 regresses
    ```md
    - **Cuts through:** everything in slice 2
    - **Depends on:** K-020
    - **PRD:** SC-1
    - **Why:** Slice 2 exit: replay with --print-states renders the board after each of the eight opening placements and every hash verifies.
    - **Evidence:** tests/golden/test_golden_games.py (9 tests), with the fixture in two halves: tests/fixtures/catan/setup_game.json is the scripted input, and tests/golden/catan/setup_game.god.jsonl is the record it produced - 16 actions, 16 phase records, 34 lines, 9612 bytes. `lgbg verify tests/golden` reports `16 action(s), 0 rejection(s), final hash 90d1be41a7d264c0`, and `replay --print-states` renders the board after every placement.
    - **The regression net was demonstrated, not asserted.** With the snake order deliberately broken to ascending-only, three golden tests failed - hash verification, the byte-for-byte reproduction, and the rendering walk - and all nine passed again on revert. That is the property the card claims: a rule that moves a hash cannot pass unnoticed, so the change must be a deliberate decision to bump `rules_version` and regenerate (ARCHITECTURE.md 15.3).
    - **The fixture is played, not written.** scripts/make_golden_setup.py asks the game for its own legal actions, so the script cannot drift from the rules it pins; it is committed so the provenance of the record is reproducible rather than remembered.
    - **Hashes pinned as literals as well as bytes.** The initial state hash `ef8474ab042614f9` and the final `90d1be41a7d264c0` are literals in the test, so even a careless regeneration of the golden file fails until someone reads the diff.
    - **Only the deterministic half is committed.** The sidecar is left behind: it holds the wall clock and the host, and the point of the split is that nothing like that can be in the record. A test asserts the record has no `at`, `host` or `pid`, and no carriage returns.
    - **Slice 2 exit.** Board, layout, ports, tokens, state, projection, phase machine, setup draft, endowment, notation and the CLI all run against real Catan, and their interaction is pinned by a game that replays. Slice 3 - the turn structure, dice and production - starts on top of a substrate whose divergence would be caught before a rule is added to it.
    ```

### K-022 · Open the turn with a roll decision

  - tags: [slice-3, phases, rules, fr-10]
  - priority: medium
  - workload: Easy
  - steps:
      - [x] A turn opens a decision offering the roll
      - [x] The phase closes correctly and advances to resolution
    ```md
    - **Cuts through:** phase machine, phases.py, the turn rules, CLI rendering of open decisions
    - **Depends on:** K-017
    - **PRD:** FR-9.5 partial, FR-10.1 partial
    - **Why:** Playing a knight before the roll is deferred to slice 5; that is the documented reason FR-10.1 is not yet fully satisfied here.
    - **Evidence:** tests/games/test_catan_turn.py (12 tests), lgbg/games/catan/rules/turn.py. A turn opens by offering the roll to the seat whose turn it is; the roll consumes draws D6 and D7 - two independent randint(1,6), never one randint(2,12) - which become visible in the state and in a `dice_rolled` event; the production phase then closes, into the action phase on any total but a seven, and into the discard phase on a seven (FR-10.5). Ending the turn opens the next seat's production phase and advances the round when it wraps to seat 0.
    - **A real divergence found and corrected, and it is the important part of this card.** The `Phase` enum written in K-016 had invented its own names - `setup_settlement`, `setup_road`, `turn_start`, `over`, and a `trade_partner` phase that does not exist - while RULES.md section 4.4, written long before as the pinned statement of the turn structure, names the phases `setup_round_1`, `setup_round_2`, `turn_production`, `discard`, `robber`, `action`, `road_building`, `trade_response`, `terminal`. The engine was therefore a second, contradicting account of the same rules, and the disagreement lived in every record. The enum now matches that table word for word, and the setup is one phase per round rather than two per step, as the table says.
    - **The cost was paid deliberately and now:** the phase name is part of the encoded state and therefore of every hash, so the golden fixture was regenerated in the same change (20 records; the initial hash moved from `ef8474ab042614f9` to `e3d0eb448c320086`) and the plugin's `rules_version` was bumped to `catan-rules-2`, which RULES.md section 1.2 records with the reason. Doing this at 1 golden game rather than at 7 is the whole argument for pinning the vocabulary early.
    - **One transition function:** `phases.begin` is now the only place a phase is entered, so a phase cannot be reached without a `phase_started` event - not by advancing, and not by an action that moves the game on, which is how `end_turn` opens the next seat's turn.
    - **What arrives with later cards:** production itself and the bank limits (K-023, K-024); the discard action, so a seven currently opens a phase whose requests cannot yet be answered (K-025); the robber (K-026); `play_dev_card` before the roll, which is why FR-10.1 is only partly satisfied here (K-042); and the rest of the action phase (K-030 onwards).
    - **Correction (found while working K-031):** this card put the turn's rules in `lgbg/games/catan/rules/turn.py`, a module ARCHITECTURE.md section 4.1's code layout does not have - the layout names the rule modules, and the turn is not one of them: production.py owns "resource generation and supply limits" and, in RULES.md section 7's mapping, "4.5 (production and dice)" with draws D6 and D7. The roll therefore moved into production.py, where the dice and what they pay are one subject, and `end_turn` moved into phases.py, because ending a turn is nothing but a transition and the machine is where transitions live. `turn.py` is gone, the tree matches the layout of record, and `tests/games/test_catan_turn.py` still pins the same behaviour.
    ```

### K-023 · Implement dice and production

  - tags: [slice-3, rules, production, rng, fr-10]
  - priority: high
  - workload: Normal
  - steps:
      - [x] Two independent d6 recorded as draws
      - [x] Production grants 1 per settlement and 2 per city on matching, unblocked hexes
      - [x] A production event names every recipient and amount so replay can verify it
    ```md
    - **Cuts through:** rules/production, core/rng, events, projection, replay
    - **Depends on:** K-022
    - **PRD:** FR-10.2, FR-10.3
    - **Evidence:** tests/games/test_catan_production.py (11 tests), lgbg/games/catan/rules/production.py. The two dice draws were already in place from K-022 (draws D6 and D7, two independent randint(1,6), asserted there); this card pays them out. Every hex showing the rolled total, and not holding the robber, pays one card per settlement on it and two per city, into the corresponding resource.
    - **The demand is computed before anything is paid** (RULES.md 4.5 item 4), which is what makes K-024's bank-shortage rule meaningful: 'the players affected' is only well defined if the whole demand is known before distribution starts. The event therefore carries both `granted` and `shortfall`, and a test starves the bank to show the demand reported rather than silently shared out.
    - **Until K-024, production never overdraws the bank.** The cap used here keeps resource conservation and non-negativity true at every step; K-024 replaces the cap with the pinned rule - all-or-nothing per resource, with a partial grant only when exactly one player is affected (RULES.md correction D-2).
    - **A seven pays nothing at all** (FR-10.5): the roll emits the dice event and no production event, and the phase machine takes the turn to the discard phase. Both branches are asserted from the same roll.
    - **Production is a fold, not engine instrumentation** (ARCHITECTURE.md section 14): the rules module is a pure function of the state and the total, so any metric over production can be recomputed from a record after the fact.
    ```

### K-024 · Handle bank-limited production

  - tags: [slice-3, rules, production, fr-10]
  - priority: medium
  - workload: Easy
  - steps:
      - [x] When the bank cannot cover a distribution, the shortfall follows the behaviour pinned in RULES.md
      - [x] The outcome is deterministic
      - [x] A test drives the bank to exhaustion and asserts the result
    ```md
    - **Cuts through:** rules/production, bank state, the pinned rule, tests
    - **Depends on:** K-023
    - **PRD:** FR-10.4
    - **Evidence:** lgbg/games/catan/rules/production.py (`_distribution`), tests/games/test_catan_production.py (17 tests). The rule of RULES.md 4.6 is decided once per resource, for all affected players at the same time: full payment when the bank covers the demand, the whole remainder to a lone claimant, and nothing at all when two or more players earn the resource.
    - **Both branches are asserted, not only the partial one** (RULES.md correction D-2). A city worth two wheat and a settlement worth one, against a bank holding two, pays nobody: the same demand that would have covered the smaller claim is withheld from both, which is the difference between the pinned rule and the cap K-023 shipped.
    - **Independence is asserted too** (4.6 item 3). The test uses the two hexes of this board that share the number 5 and disagree about terrain - a wheat hex and a wood hex - and starves only the wheat: the wheat is withheld from two players while the wood is paid in full to the same two.
    - **Determinism is the property, not the implementation.** The same state is produced twice, and the same position built from the vertex list in reverse, and all three results must be equal - so no part of the distribution may depend on the order demand was accumulated in or on the order seats are visited.
    - **Conservation survives the shortage** (FR-6.9): withheld cards stay in the bank, so bank plus all hands is unchanged by production and never negative. The test compares the total before and after rather than against 19, because it starves the bank by hand.
    - **The event is the account of the shortage.** `granted` names what each player actually received and `shortfall` what they were owed and did not get, so a record explains a short roll without the reader having to reconstruct the bank from the start of the game.
    ```

### K-025 · Implement the concurrent discard phase on a 7

  - tags: [slice-3, phases, rules, robber, fr-9, fr-12]
  - priority: high
  - workload: Normal
  - steps:
      - [x] A 7 skips production and opens concurrent requests to every player holding more than 7 cards
      - [x] Discard is floor(hand/2), any resource composition allowed
      - [x] The phase closes only when all requests resolve
      - [x] It is NOT implemented as sequential private turns
    ```md
    - **Cuts through:** phase machine, decision queue, projection, events
    - **Depends on:** K-023, K-016
    - **PRD:** FR-9.5, FR-12.1, FR-12.2, FR-10.5
    - **Why:** First genuine test of the decision queue. Simulating concurrent decisions as private turns changes what players can observe about each other, and therefore changes the game.
    - **Evidence:** lgbg/games/catan/rules/robber.py, lgbg/games/catan/phases.py, tests/games/test_catan_discard.py (20 tests). A seven computes every amount once, at the roll, and stores it in `discards_pending`; the phase then opens one `discard_resources` request per eligible seat, in seat order, and each request carries the amount the seven forced - not a number recomputed from a hand that has already shrunk. That is what makes the concurrency a property of the state rather than a promise in a docstring.
    - **The decision kind was renamed to the name the rules pin.** RULES.md 4.4's table says a discard is answered with `discard_resources`, one request per eligible player; the placeholder `discard` was a name the engine had invented for a request the rules already named. Renaming it before the first record carries one is the same discipline K-022 applied to the phase names.
    - **A phase that closes the moment it opens now closes in the same action.** With nobody over the limit a seven has nothing to ask, so `advance` no longer stops there: it walks out of every closed phase and announces each transition, which is why a seven in a fresh position records `phase_started(discard)` and `phase_started(robber)` together. Without that, a game could sit in a phase whose request set was empty from the start, waiting for an action that could never be legal.
    - **Any composition is allowed, and the enumeration is exactly that set** (FR-12.2, FR-17.5): `legal_actions` offers every composition of the forced amount that fits the hand, and the test re-derives that set independently, asserts each offered action is accepted, and asserts the free cross product is not on offer. A discard of the wrong size is refused with `WRONG_DISCARD_TOTAL`, and one naming cards the player does not hold with the new `NOT_ENOUGH_RESOURCES`.
    - **The discard is a move, not a destruction** (FR-6.9): the cards go to the bank, and the conservation invariant is asserted after the phase. The tests deal every hand out of the bank, so the position is one the rules could have produced rather than one that merely looks plausible.
    - **The robber phase is where the machine now waits** (K-026): entering it is a transition like any other, and asking it for decisions is still a loud error.
    ```

### K-026 · Implement robber movement and production blocking

  - tags: [slice-3, robber, rules, fr-12]
  - priority: medium
  - workload: Easy
  - steps:
      - [x] Current player moves the robber to a different hex
      - [x] A blocked hex produces nothing
      - [x] Steal adjacency is derived from topology, not authored
    ```md
    - **Cuts through:** rules/robber, board topology, projection, production
    - **Depends on:** K-025
    - **PRD:** FR-12.3
    - **Evidence:** lgbg/games/catan/rules/robber.py (`move_robber`, `destinations`, `robber_victims`), lgbg/games/catan/phases.py (`_robber_requests`), tests/games/test_catan_robber.py (18 tests). The robber phase now has its two steps: the mover is asked for `move_robber`, and once it has moved, for `choose_robber_victim` if the new hex carries somebody else's building - the second request is open and unanswerable, which is where K-027 lands.
    - **Progress is read from the state, not remembered by the machine.** The robber is the one step in the game that leaves no trace: a robber that has just moved sits on a hex exactly like one that has not. A phase rule is a function of the state - it cannot see what it has already handed out - so the state records the phase instance the move happened in (`robber_moved_at`, compared against `phase_index`, the same number the decision identifiers are built from). A fresh robber phase, after a seven or after a knight, therefore asks for the move again without any reset, and the phase that has already moved asks for the victim.
    - **That is one new state field, and it was not free.** `encode_state` is what every hash is computed from, so the field moved every hash: `rules_version` went from `catan-rules-3` to `catan-rules-4`, the reason is recorded in RULES.md section 1.2, the golden fixture was regenerated, and the correction is recorded on K-014, the card that fixed the field set. Paying the price at the second golden game rather than the tenth is the point of the discipline.
    - **Blocking is asserted through the roll, not around it** (FR-12.3). The test places a settlement on each of the two hexes that share the number 5, rolls a 5 twice - once with the robber on the desert, once with it on one of those hexes - and asserts that the first roll pays the blocked hex and the second does not, while the hex that shares its number is still paid. `produce` blocks by hex identity, so no separate rule had to be written for it, and none was.
    - **The neighbours are derived twice, by different routes.** `robber_victims` walks the robber's hex to its vertices and reads the occupancy; the test re-derives the same set through the inverse relation (`hexes_at(vertex)`) and compares, so a change that made the two agree by accident - an authored list, a cached set - would fail. A city counts like a settlement, the mover is never a candidate, and holding cards is deliberately not part of candidacy: the rules let the mover name a victim who holds nothing and get nothing.
    - **Every hex but one is a destination.** The desert included, and the current hex refused with `ROBBER_SAME_HEX`; a second move in the same phase with `ROBBER_ALREADY_MOVED`; an unknown hex, a missing parameter or a non-integer with `BAD_PARAMS`. The enumeration in `legal_actions` is exactly the set the rule accepts, checked by applying every action it offers.
    ```

### K-027 · Implement steal with recorded draw and asymmetric visibility

  - tags: [slice-3, robber, rng, projection, fr-12]
  - priority: high
  - workload: Normal
  - steps:
      - [x] One random resource moves from a chosen adjacent opponent
      - [x] Thief learns what was taken; victim learns what left their hand
      - [x] The draw is recorded and replays exactly
    ```md
    - **Cuts through:** rules/robber, core/rng, the per-observer projection, replay
    - **Depends on:** K-026
    - **PRD:** FR-12.4, FR-12.5
    - **Why:** First card where the projection must express asymmetric knowledge rather than merely private state.
    - **Evidence:** lgbg/games/catan/rules/robber.py (`choose_robber_victim`, `steal`, draw `robber_steal`), lgbg/games/catan/projection.py (the first observer-relative field), lgbg/games/catan/notation.py, tests/games/test_catan_steal.py (24 tests).
    - **One card, drawn over the cards and not over the types** (draw D8, RULES.md 3.1 and 4.9 item 6). The draw is a single `choice` over the victim's hand materialised in canonical resource order and repeated by count, so a hand of three wood and one ore loses wood three times in four - which is what drawing one card out of a physical hand means. The test asserts the purpose label, the kind, the argument (the size of the hand, not the number of resource types), and the value; over 240 fixed seeds it asserts that both are reachable and that wood outweighs ore by more than two to one, which a per-type draw would not do.
    - **`choice` returns a resource name and not the enum member, deliberately.** A replay returns whatever the record holds - and a record holds JSON - so a live draw handing back a `Resource` and a replayed draw handing back a `str` would be two different kinds of answer to the same question. The steal reads the name and finds the position itself, so the live path and the replayed path are the same code (FR-2.4).
    - **The engine does not ask a question whose answer is already settled** (RULES.md 4.9 item 5). With exactly one candidate, the move *is* the steal: it draws D8 and robs that player, and the phase closes into the action phase. Only with two or more candidates is `choose_robber_victim` opened, and only then does a name mean anything - naming a victim before the move, or in the phase that follows it, is refused. A mandatory steal is never left unrunnable, and the same hand cannot be robbed twice.
    - **The first observer-relative field.** The projection was built from an allow-list that took no account of who was asking; FR-12.5 needs the opposite, so `OBSERVER_FIELDS` now declares the fields that answer differently per observer, and the player's view is the public position plus their own hand. The thief sees the card it gained, the victim sees it leave, and a third player is told nothing about anybody's cards - all asserted on one position. `hands` (the spectator's view of everyone) stays a different field with a different shape, and the "the spectator sees everything a player sees" assertion now excludes the observer-relative fields explicitly instead of pretending they line up.
    - **FR-12.4's wording is corrected (RULES.md D-5).** The PRD says the steal is from an opponent "holding at least one card"; the rulebook lets the mover name a card-less victim and get nothing, and the steal is mandatory, so reading the PRD literally would make the move unrunnable when every candidate is empty-handed. The candidates are every other player with a building on the robber's hex, a victim who holds nothing yields nothing, and no draw is consumed - asserted with the null source. Two inline-code spans mangled into section signs in the D-4 row are repaired in the same change.
    ```

### K-028 · Extend projection to resource hands

  - tags: [slice-3, projection, test, fr-16]
  - priority: high
  - workload: Normal
  - steps:
      - [x] Own hand exact; other players' total count only
      - [x] A leak test asserts no other player's card composition is reachable from a projection, including through the notation rendering
    ```md
    - **Cuts through:** projection.py, the allow-list, leak tests, notation
    - **Depends on:** K-027
    - **PRD:** FR-16.1, FR-16.2, FR-16.6
    - **Evidence:** lgbg/games/catan/projection.py (`_hand_counts` in the allow-list), lgbg/games/catan/notation.py, tests/games/test_catan_leaks.py (10 tests). The player's view now holds both halves of the FR-16.1 row: `hand`, exact and the observer's own, and `hand_counts`, how many cards each seat holds - a fact the rules assume everybody has, since hands are counted across the table. The composition of anybody else's hand is nowhere in it.
    - **The leak tests are indistinguishability tests, not searches.** Reading a dictionary and failing to spot the hand proves nothing, so each hidden field is held to a stronger property: two positions that differ *only* in that field must project to exactly the same observation for every observer not entitled to see it. For hands the two positions are built by making two seats trade hands, which leaves the bank, every hand size and every other public fact identical - so any observable difference would have to have come from the cards themselves.
    - **Every test carries its own control.** The two owners and the spectator *do* see the difference between those two positions; without that, a passing test could be passing because the two positions were the same position. This is the failure mode of leak tests, and it is cheap to rule out.
    - **The renderer is held to the same standard** (FR-16.6, 'including through the notation rendering'). A projection that is clean and a renderer that prints something else is still a leak, and the renderer here prints every field it does not recognise - it fails open, deliberately - so the assertion has to be made on the rendered text: identical for the two positions, in both details, and containing no hand but the observer's own.
    - **The blunt test is kept as well**, for the reader who wants to see the claim without the argument: walk the whole observation, at any depth, and assert that it contains no row of five counts and no other seat's hand - and that the one composition it does hold is the observer's own.
    - **The other hidden fields each got their test in the same shape:** the deck order, another player's development cards, what another player owes the bank on a seven, and an unconsumed trade response. FR-16.6 asks for one leak test per hidden field, and every hidden field that exists at this point has one; the hidden victory-point cards arrive with K-036 and will bring theirs.
    - **`observation_schema()` now requires `hand_counts` and documents `hand`** (FR-16.8): the declared shape and the projection cannot drift apart unnoticed. `hand` is declared as optional rather than required because the spectator has no hand of their own - it sees every hand as `hands` - and the schema describes both views.
    ```

### K-029 · Commit golden game 2: a 7, a discard, a steal

  - tags: [slice-3, test, acceptance, sc-1]
  - priority: medium
  - workload: Easy
  - steps:
      - [x] Committed fixture whose log provably contains a discard and a steal
      - [x] Replays with every hash verified
    ```md
    - **Cuts through:** everything in slice 3
    - **Depends on:** K-028
    - **PRD:** SC-1
    - **Why:** Slice 3 exit: a mid-game record replays to a state where resources have moved through dice, a forced discard and a seizure.
    - **Evidence:** tests/fixtures/catan/seven_game.json, tests/golden/catan/seven_game.god.jsonl, tests/golden/test_golden_midgame.py (11 tests), scripts/make_golden_midgame.py. Forty-three actions over three rounds, and in them exactly one forced discard - seat 3 returns six cards, two ore, two wheat and two wool - and exactly one seizure - seat 0 takes a wool off seat 3 after moving the robber from the desert onto hex 3. Every hash is pinned as a literal and the record is compared byte for byte when the fixture is replayed.
    - **The fixture is played, not written.** Every action in it came from the game's own `legal_actions`, so the script cannot drift from the rules it is supposed to pin, and the test that drives the committed script through a fresh run and compares the bytes is what turns the pair into a regression net rather than a transcript nobody checks.
    - **The two golden games are one game.** This fixture uses golden game 1's seed and its first sixteen actions are the draft, so its first sixteen *records* are byte-identical to game 1's - asserted, not assumed. A change to the opening moves both fixtures and the two tests fail together, which is the cheap half of a cross-check that would otherwise need a third artefact.
    - **"Provably contains" is taken literally.** The test does not merely find a `discarded` event: it replays the log, takes the state the discard was answered against, and asserts that the player was over the limit, that the number returned is `floor(hand / 2)`, that every returned card arrived in the bank, that the roll which forced it paid no production at all, and that the steal moved exactly one card of the named resource from the victim's hand to the thief's. The conservation invariants hold after it, so the game moved cards rather than making them.
    - **Slice 3 ends here** (SC-1): a mid-game record in which resources have moved through the dice, the endowment, a forced discard and a seizure replays with every hash verified, every intermediate state renders for the table and for each player, and the file is deterministic text with the versions it was produced under.
    ```

### K-030 · Implement costs, spending and game rejection codes

  - tags: [slice-4, rules, building, fr-11]
  - priority: high
  - workload: Normal
  - steps:
      - [x] Costs exactly as in PRD Appendix A
      - [x] Insufficient-resource and unavailable-target rejections carry structured details
      - [x] Every code raised is declared via rejection_codes()
    ```md
    - **Cuts through:** rules/building, bank, core/errors, the plugin's code declaration
    - **Depends on:** K-018
    - **PRD:** FR-11.1, FR-11.7, FR-6.8
    - **Evidence:** lgbg/games/catan/rules/building.py (`COSTS`, `cost_of`, `shortfall`, `affordable`, `pay`), tests/games/test_catan_building_costs.py (13 tests), tests/games/test_catan_rejections.py (5 tests).
    - **The prices are one table, and they are not five-count tuples.** Each price is written resource by resource - the way RULES.md 4.7 and Appendix A write it - and turned into a hand by `cost_of`, which is the single place the canonical resource order is applied to a price. A cost can therefore only be wrong in one place, and the test that checks it writes the four prices out a third time by hand from the rulebook rather than from the table under test.
    - **Paying is atomic by construction** (FR-11.7). The shortfall is computed before a single card moves, so a player who cannot afford something loses nothing and the rejection carries the reason in a form a metric can read: the build, the cost, and exactly which resources were short by how much. Half-paying is not a state the code can reach, which is why there is no test for it.
    - **A payment is a fact in the record.** `pay` returns the position and a `resources_spent` event naming the build and its cost, so a build that was paid for is stated rather than inferred from a smaller hand. The caller keeps its own event (a road placed, a settlement built) and the two sit side by side in the action.
    - **Every rejection code is declared, and the test that proves it reads the source.** A behavioural test can only provoke the refusals it thinks of; the interesting failure is the code somebody raised in a branch nobody thought about. So the audit parses every module under `lgbg/` except the two vocabularies, collects the name passed as `code=` to every `Rejection(...)`, and asserts that each one was imported from the declared vocabulary and appears in the plugin's own `rejection_codes()`. It also refuses a `RejectionCode(...)` built anywhere but in the two vocabulary files, and refuses a code written at the call site instead of named.
    - **The audit has a control**, because a scan that finds nothing passes every assertion above: it asserts that the scan sees at least fifteen raised codes and that `game.py` is among the modules seen. The declaration must also cover what the *runtime* raises, not only what the game does - a rejection the runtime can produce and the plugin does not declare is a hole the fuzz audit of K-063 would find in a much more expensive way.
    - **The unavailable-target codes were already declared and structured** by the setup work (occupied vertex, occupied edge, too close, not connected, no pieces remaining), so this card's contribution to that step is the proof that none of them is missing from the declaration - and the vocabulary is now closed, which is what makes an illegal-move rate by code comparable across games (FR-6.8).
    ```

### K-031 · Implement road building

  - tags: [slice-4, rules, building, fr-11]
  - priority: high
  - workload: Normal
  - steps:
      - [x] Connectivity to the player's own network enforced
      - [x] Edge occupancy rejected with a specific code
      - [x] 15-road limit tracked; exhaustion makes the action unavailable rather than erroring
    ```md
    - **Cuts through:** rules/building, topology, piece supply, projection, events
    - **Depends on:** K-030
    - **PRD:** FR-11.2, FR-11.3, FR-11.5
    - **Evidence:** lgbg/games/catan/rules/building.py (`connection_points`, `road_targets`, `can_build_road`, `build_road`), lgbg/games/catan/phases.py (the action phase offers what can be taken), lgbg/games/catan/game.py, tests/games/test_catan_roads.py (16 tests).
    - **Connectivity is a property of the vertex, not of the edge.** `connection_points` answers the only question the rules ask - which vertices does this player's network reach - and it answers it once for the whole board. RULES.md 4.7 item 3 is a statement about that set: a vertex carrying both the player's road and an opponent's building connects nothing further, which is exactly what stops a road from being built on the other side of somebody else's settlement. Both halves are asserted, the refusal and the legal case where the network reaches the *other* end.
    - **The refusals are ordered the way the rules treat the questions** - is there a piece, is the edge empty, does it connect, is there a price in hand - so the code a player sees is the first thing that was actually wrong, and the price is paid last. A road refused for any other reason therefore costs nothing, which the test asserts by refusing on an empty hand after all the geometry is settled.
    - **Exhaustion is unavailability, not an error** (FR-11.5, RULES.md 4.7). `can_build_road` reports whether the action is on the table, and the action phase's request lists what it offers, so a player at their road limit is never offered a road; an attempt anyway is refused with `NO_PIECES_REMAINING` naming the piece. The boundary is tested from both sides: the fifteenth road can still be built, and the sixteenth cannot.
    - **Every fixture is charged for what it places.** The test positions lay pieces on the board and take them out of their owners' supplies, and take cards out of the bank - so `check_invariants` on the result means something. The exhaustion fixture lays out the rest of the player's fifteen roads rather than simply declaring the supply empty.
    - **The action is enumerated from the rule that judges it.** The action phase lists the actions it offers, and each offered action is enumerated by the rule that will accept or refuse it, so what is offered is exactly what is accepted - asserted by building every offered road and refusing an edge that is not offered. This is the shape K-034 completes for the rest of the action surface.
    - **One vocabulary for pieces.** The piece-supply helpers moved into building.py (the module the layout gives 'piece placement, costs, piece and adjacency constraints' to) and the draft now uses them, so `piece_taken` has a single definition rather than one per builder.
    ```

### K-032 · Implement settlement building

  - tags: [slice-4, rules, building, fr-11]
  - priority: high
  - workload: Normal
  - steps:
      - [x] Distance rule enforced at exactly distance 2
      - [x] Boundary tests at distance 1 and distance 3
      - [x] Connectivity enforced
      - [x] 5-settlement limit tracked
    ```md
    - **Cuts through:** rules/building, topology, distance rule, piece supply
    - **Depends on:** K-031
    - **PRD:** FR-11.4
    - **Evidence:** lgbg/games/catan/rules/building.py (`neighbouring_vertices`, `settlement_targets`, `can_build_settlement`, `build_settlement`), tests/games/test_catan_settlements.py (18 tests), tests/games/catan_boards.py (the fixtures the building tests share).
    - **The distance rule is measured in the unit the rulebook measures it in.** RULES.md 4.7 states it over the vertices reachable by a single edge, so `neighbouring_vertices` is that set and the rule is a predicate over it - there is no second, hand-rolled notion of "near" anywhere in the engine. The boundary is asserted from both sides: one edge away is refused, two and three are not, because the mistake implementations make is measuring the wrong distance, not forgetting the rule.
    - **Both halves of the rule are pinned by tests.** The neighbourhood blocks a building **of any colour**, so a test places the player's *own* settlement on the neighbouring vertex, and another places a city rather than a settlement: RULES.md says "the placing player's own included" and "any settlement or city", and both are the sort of clause that gets read as prose and implemented as neither.
    - **The limit is a supply, not a counter.** Five settlements is what the player owns, so the fixture puts four on the board and builds the fifth - which is exactly the case where the supply runs out - rather than declaring a supply of one. The fifth build succeeds, the sixth is refused with `NO_PIECES_REMAINING`, and `can_build_settlement` is false afterwards, so the action is not on the table either (FR-11.5).
    - **A settlement does what a settlement is for** (FR-11.4): the test asserts the point it is worth, and then rolls the number of an adjacent hex and asserts the card arrives - the production link is the whole point of building one, and it is cheap to check it end to end rather than trusting two modules to agree.
    - **The refusals are ordered, and the price is paid last**, so a settlement refused for any other reason costs nothing: the test that cannot afford one asserts the position is untouched as well as the code.
    - **The fixtures moved into a declared helper** (tests/games/catan_boards.py), because a settlement needs a network, a price and a clear neighbourhood at once, and a third hand-written position builder would have drifted from the first two. Everything it places is charged to a supply and to the bank, so a conservation check on a result means something.
    ```

### K-033 · Implement city upgrade

  - tags: [slice-4, rules, building, fr-11]
  - priority: medium
  - workload: Easy
  - steps:
      - [x] Upgrading an own settlement returns the settlement to supply
      - [x] Production rises to 2 and VP to 2
      - [x] 4-city limit enforced
    ```md
    - **Cuts through:** rules/building, piece supply, production value, victory accounting
    - **Depends on:** K-032
    - **PRD:** FR-11.6
    - **Evidence:** lgbg/games/catan/rules/building.py (`city_targets`, `can_build_city`, `build_city`, `return_piece`), lgbg/games/catan/rejections.py (`NOT_YOUR_SETTLEMENT`), tests/games/test_catan_cities.py (13 tests).
    - **A city is an upgrade, and the test asks from three directions** because that is what the rule is: an empty vertex is refused, an opponent's settlement is refused, and the player's own settlement is upgraded where it stands. RULES.md is explicit that a city may never be placed on an empty vertex "for any price" (S5), and the only way to be sure an implementation honours that is to ask it for an empty vertex and read the refusal - which names the vertex and, when somebody else owns it, the owner.
    - **Two pieces move in opposite directions and the ledger stays true.** The city comes out of the supply and the settlement goes back into it, in the same action, and the test asserts the whole supply row plus `check_invariants` on the result: a player who upgrades has not lost a settlement, they have moved one from the board back into supply, and the piece conservation law says so.
    - **The build names and the piece names are different words, and now different constants.** This card's first draft passed the build name `"settlement"` where the supply wants the piece `"settlements"`, and got a `KeyError` from a helper whose whole job was to make that impossible. `ROADS`/`SETTLEMENTS`/`CITIES` are now declared beside `ROAD`/`SETTLEMENT`/`CITY`, with the reason: you build a settlement, and five settlements is what you own.
    - **What a city is for, asserted rather than assumed** (FR-11.6): the point value is checked against the old one (two, not three - a settlement's point is replaced, not added), and a roll of an adjacent number pays two cards where a settlement paid one, through the same production path the settlement card tests.
    - **The four-city limit is the supply again**, not a counter: the fixture lays out three cities standing and two settlements to upgrade, so the fourth city is built against a supply that genuinely holds one, and the fifth attempt is refused with `NO_PIECES_REMAINING` while `can_build_city` stays false - the action is not offered either (FR-11.5).
    - **The upgrade composes with the piece helpers** rather than reaching into the supply itself: `spend_piece` and `return_piece` now take and return the supply tuple, so an action that moves two pieces writes one expression and the two halves cannot disagree about which player they are charging.
    ```

### K-034 · Implement legal_actions and action_domains

  - tags: [slice-4, core, rules, fr-17]
  - priority: high
  - workload: Hard
  - steps:
      - [x] Complete enumeration of currently legal actions
      - [x] Cross-product-free domain description per ARCHITECTURE section 7.2
      - [x] Both are pure and RNG-free, proven with NullRandomSource
      - [x] A test asserts every enumerated action is accepted and a sample of non-enumerated actions is rejected
    ```md
    - **Cuts through:** the plugin interface, every rule module, the L1 and L2 renderers, the fuzzer
    - **Depends on:** K-033, K-030
    - **PRD:** FR-17.4, FR-17.5, FR-17.6
    - **Evidence:** lgbg/games/catan/game.py (`PARAMETER`, `COST_OF`, `_targets`, `_actions_of_type`, `_domain_of`), tests/games/test_catan_action_surface.py (15 tests).
    - **The two halves are one fact stated twice, and now they are read from one table.** `PARAMETER` says which parameter carries the target an action names; from it the enumeration produces one action per permitted value and the domain description produces one entry with those values in it. A phase therefore needs no new code in the interface layer: `_legal_actions_for` is a fold over the table rather than a branch per phase, and the branch-per-phase version it replaced could not have been kept in step with the domains by hand.
    - **The description is not an enumeration** (ARCHITECTURE 7.2): a build is one entry carrying an `id_set` of edges, not one entry per edge, and the test asserts the shape rather than the count - one domain per action type, fewer domains than actions, one parameter named.
    - **Costs come from the price table, and the mapping is explicit.** The first draft looked a price up by the *action* name and silently produced a free build: an action is named for what it does (`build_road`) and a price for what it buys (`road`). `COST_OF` states the mapping, and the test asserts the three build costs against the rulebook's own table - which is exactly the kind of difference that would otherwise never be noticed until a game was too cheap.
    - **The discard is the one domain that cannot be exact, and it says so.** A discard is five counts whose sum is the forced amount: the domain shape can express the range of each count and not the constraint between them, so it is described permissively and the sum is left to the rule. A description may be permissive; it may not promise a value the rule refuses, which is why every other set is built from the rule's own target list.
    - **Purity is asserted in the strongest form available**: neither function takes a source of randomness at all - the test reads their signatures - and calling either twice gives the same answer with the encoded state unchanged (FR-17.6).
    - **Completeness is asserted over a whole recorded game**, not one convenient position: the test replays golden game 2 and applies *every* action the surface offers at *every* step, asserting each is accepted - more than a hundred checks. FR-17.5 is a promise about the enumeration, and a promise is only worth as much as the range it was tested over; the failures that matter are at the steps nobody wrote a fixture for. The same test file checks the converse on a rich position: a road on an occupied edge, a settlement one vertex too close, an upgrade of a vertex nobody built on, an action type the game does not have and an action by a seat that is not to move are all refused.
    - **The schema cannot drift from the implementation** (FR-18.1, FR-18.5): `set(action_schema()) == set(ACTIONS)`, and every action type the enumeration or the domains produce is a key of the schema.
    ```

### K-035 · Implement Longest Road and award transfer rules

  - tags: [slice-4, rules, victory, fr-13, sc-11]
  - priority: high
  - workload: Extreme
  - defaultExpanded: true
  - steps:
      - [x] Exhaustive simple-path search; never a heuristic or greedy approximation
      - [x] Minimum 5 continuous roads
      - [x] Broken by opposing settlements or cities
      - [x] Ties vacate the award; re-acquisition handled per RULES.md
      - [x] Dedicated test matrix covering branching, breaking, tying and re-acquisition
      - [x] 100 percent coverage on longest_road.py
    ```md
    - **Cuts through:** rules/longest_road, topology, victory accounting, projection, events
    - **Depends on:** K-031
    - **PRD:** FR-13.9, FR-13.10, SC-11
    - **Why:** Pulled forward out of milestone M6 deliberately. Settlements and cities alone cap at 9 VP, so without an award slice 4 cannot end with a winnable game. Classic bug magnet: breadth is not length, and an opposing settlement truncates a path.
    - **Evidence:** lgbg/games/catan/rules/longest_road.py (`road_length`, `holder`, `recompute`), wired into `build_road`, `build_settlement` and `build_city`; tests/games/test_catan_longest_road.py (14 tests). Measured with `coverage run --source=lgbg`: 58 statements, 0 missed, **100 percent** on the module.
    - **The search is the rulebook's definition and nothing else** (FR-13.10): a continuous road is a simple path *or* a simple cycle, so the walk is a depth-first enumeration of every simple road with two endings - an edge back to the start closes a cycle, and a vertex already on the walk cannot be visited twice. RULES.md 4.10 item 4 forbids a greedy or approximate computation, so there is no shortcut here: the branching a fifteen-road network has is small, and being wrong about a two-point award is worse than being slow about it.
    - **The matrix is the six ways this rule is usually got wrong.** A T of six roads is a longest road of *four*, not six - breadth is not length, and it is the assertion the classic implementation fails. An opponent's settlement truncates a path, and so does an opponent's city, but a player's *own* building does not and another player's *road* does not: a building of another colour ends the road, a road of another colour is simply not part of it. A loop counts its whole length, which is why the enumeration starts from every vertex rather than from a leaf. And the card is held by a player, not owned by the board, so a tie has two different answers depending on who holds it.
    - **Recomputation happens where the rules say it does** (item 6, "after every state transition"), which in practice means the transitions that can change a road or break one: building a road, and building a settlement or a city. The settlement case is the one worth naming - a settlement placed in the middle of somebody's road is exactly how a Longest Road is broken, so the recomputation runs there too and the test drives it through `apply` on another player's turn (items 7 and 8: automatic, and not only on the holder's turn).
    - **The fixtures walk the board rather than naming edge numbers**, so a test that says "a line of six" is a line of six on whatever board the plugin ships, and the T is found by searching for a junction that genuinely has three free branches of two. That cost three fixture bugs and one hang while the card was written, all of them in the *tests* - which is where the mistakes should be when a rule is this easy to state and this easy to get subtly wrong.
    - **What this card does not do:** the two points the card is worth are not yet counted. `victory_points` still reports settlements and cities only, and the award's value is declared here (`longest_road.VALUE`) for K-036 to add, with the accounting and the win detection that go with it.
    ```

### K-036 · Implement victory accounting and win detection

  - tags: [slice-4, rules, victory, fr-15]
  - priority: high
  - workload: Normal
  - steps:
      - [x] Scoring per PRD Appendix A
      - [x] Win condition and its timing follow the interpretation pinned in RULES.md
      - [x] Explicit test for the own-turn timing edge case
    ```md
    - **Cuts through:** rules/victory, every scoring source, projection, terminality
    - **Depends on:** K-035, K-033
    - **PRD:** FR-15.1, FR-15.2
    - **Evidence:** lgbg/games/catan/rules/victory.py (`POINTS`, `TARGET`, `victory_points`, `check`), wired into `game.apply`, `game.victory_points` and `game.outcome`; tests/games/test_catan_victory.py (14 tests).
    - **The five terms of Appendix A are asserted literally**, and the opening position is asserted to be worth two points to everybody (RULES.md 4.13 item 11), because that is the number every later card's arithmetic assumes. The total is the *true* total - victory-point cards count whether or not they have been shown - since it is the number the game ends on; what other players may compute is a different number and belongs to the projection (FR-16.4).
    - **The timing is the card.** The condition is checked after every transition and applied to the player *whose turn it is*, so a total that reaches ten during somebody else's turn does not end the game: `check` is asserted to leave such a position alone, and the same player is then asserted to win at the start of their own turn - with no die rolled, which is the rulebook's own answer to the question (S5). The state enters `terminal` through the ordinary transition function, so the record carries a `phase_started(terminal)` beside a `game_won` event naming the player, the points and the target.
    - **One declaration of the target.** `VICTORY_TARGET` in state.py and the rule module's `TARGET` were two constants with the same number in them, which is one more than the game needs; the state module's copy is gone, and the state test now asserts the rule module's. The same discipline as the resource order: a number the rules own lives with the rule that applies it.
    - **No claim action exists** (item 7), and the existing `GAME_OVER` guard makes the rest true: an action after the win is rejected, asserted directly rather than assumed.
    - **The fixture taught the card something.** Its first version handed seat 0 the Longest Road award without the roads to justify it, and the engine took the card straight back: the recomputation wired in K-035 fired inside the very action the test was driving, so the tenth point never arrived. The fixture now builds its points from pieces alone, and the second attempt failed honestly as well - nine points had already put all four cities on the board, so the winning upgrade was refused with `NO_PIECES_REMAINING`. Two failures, both of them the fixture being wrong rather than the rule, and both of them caught because the pieces are charged for what they place.
    - **Purity is asserted in the same form as the action surface** (FR-15.3): `check` takes only a state - the test reads its signature - gives the same answer twice, and leaves the encoding unchanged.
    ```

### K-037 · Implement terminality, outcome and the terminal record

  - tags: [slice-4, core, log, fr-15]
  - priority: medium
  - workload: Easy
  - steps:
      - [x] is_terminal and outcome are pure and RNG-free
      - [x] Outcome reports final VP per player, winner, turn count and total actions
      - [x] Any action after termination is rejected with a core code
    ```md
    - **Cuts through:** is_terminal and outcome, the phase machine, log, CLI
    - **Depends on:** K-036
    - **PRD:** FR-15.3, FR-15.4, FR-15.5
    - **Evidence:** lgbg/games/catan/phases.py (`pending_decisions` answers a finished game), tests/games/test_catan_terminal.py (14 tests).
    - **One thing was actually broken, and it was the one a driver would hit first.** A finished game has no rule in the phase table, so `pending_decisions` raised the "this phase's card has not landed" error - which meant `legal_actions` on a won game raised an exception instead of answering that there is nothing left to do. A finished game is now an explicit case: it asks nobody anything, and says so by returning nothing. The distinction is the whole point of the error it replaced, and it is now written down where it is made: an unimplemented phase is a bug, a finished game is an answer.
    - **The verdict is asserted pure in the same form as everywhere else** (FR-15.3): neither `is_terminal` nor `outcome` takes a source of randomness - the test reads their signatures - and asking a won game twice gives the same answer with the encoding unchanged, and does not revive it.
    - **The rejection after termination is swept over the whole declared surface** rather than sampled: every action type in `action_schema()` is applied to a finished game and refused with `GAME_OVER`, with the hash asserted unchanged (FR-3.4, FR-15.5). Sampling would have been easier and would have missed exactly the action type somebody adds next.
    - **The outcome is asserted against the scoring rule rather than against literals**: the scores are compared to `victory_points`, so the two cannot drift, and the winner is asserted to be the player whose turn it is (which is the only player `check` may terminate for).
    - **What is deliberately not here: the end-to-end terminal record.** A `GameRun` cannot be handed a position, so a test cannot conjure a run that ends in a win - the record the runtime writes for a won game has to come from a game actually played to a win. That is K-038, the next card on the board, and the card that needed it says so rather than testing a hand-built log and calling it end to end.
    - **The last test is the scoring term nobody can see:** a victory-point card in a hand is counted from the god view (RULES.md 4.13 item 2), and the position it is in is nine points - so the game does not end, which is the same assertion from the other side.
    ```
