# KANBAN-v2 · PRD-v2 · horizontal slices

## Todo

## In Progress

## Blocked

## Backlog






### K-017 · Verbatim payload recording

  - tags: [slice-3, provider, records, fr-5, sc-4]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] The exact request payload and the exact response are recorded for every call
      - [ ] Credentials are redacted before anything is written
      - [ ] The adapter never retries, summarises, repairs or otherwise alters a request; policy belongs above it where it is visible
    ```md
    - **Cuts through:** the adapter, the sidecar writer, the artefact contracts
    - **Depends on:** K-016
    - **PRD:** FR-5.4, FR-5.5, FR-10.4, FR-10.5, NFR-7
    - **Why:** A record that cannot answer what the model was shown is not evidence. The redaction requirement is what makes recording the raw payload safe.
    ```

### K-018 · Provider conformance suite

  - tags: [slice-3, test, fr-5, sc-9]
  - priority: medium
  - workload: Normal
  - steps:
      - [ ] One shared suite that both the mock and OpenRouter pass
      - [ ] It covers a model without native tool calling
      - [ ] A new adapter can be added by making the suite pass, with no change to the loop
    ```md
    - **Cuts through:** every adapter, the tool loop, the test suite
    - **Depends on:** K-017
    - **PRD:** FR-15.2, SC-9
    ```

### K-019 · The tool loop and the decision turn

  - tags: [slice-4, loop, fr-6]
  - priority: high
  - workload: Hard
  - defaultExpanded: true
  - steps:
      - [ ] One decision turn is one conversation, ending on an accepted action, redo exhaustion, step budget exhaustion, or timeout
      - [ ] Bounded read tool calls are allowed before acting
      - [ ] The loop is provider-agnostic and contains no provider branching
      - [ ] It offers the model no help that was not configured: no hints, no summarisation, no re-reading state on its behalf
    ```md
    - **Cuts through:** agents, the provider protocol, the MCP surface, the facade
    - **Depends on:** K-018, K-009
    - **PRD:** FR-6.1 to FR-6.6
    - **Why:** The single place where a convenience would become a confound. Every line of help added here is invisible in the results and permanent in the comparison.
    ```

### K-020 · Prompt assembly and hash enforcement

  - tags: [slice-4, agents, fr-9, sc-5]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] Separable layers: the game's game.md, a role system.md, a policy policy.md, and the shared redo prompt (the fourth arrives in slice 5)
      - [ ] Every artefact used in a run is hashed into the manifest, not only the game prompt
      - [ ] Hashes are recomputed before every game, and a mismatch aborts the run
      - [ ] Tool and resource descriptions derive from the plugin rather than being hand-written
    ```md
    - **Cuts through:** agents, core/prompts, the manifest, the MCP surface
    - **Depends on:** K-019
    - **PRD:** FR-9.1 to FR-9.6, SC-5
    - **Why:** A prompt edited mid-run turns one experiment into two, and nothing in the results would show it. Rehashing before every game is cheap and makes that failure impossible.
    ```

### K-021 · Cost and token accounting

  - tags: [slice-4, accounting, fr-13]
  - priority: medium
  - workload: Normal
  - steps:
      - [ ] Every decision turn records its usage and its latency
      - [ ] Cost is computed from the declared price table, and the table used is recorded in the manifest
      - [ ] Missing usage is reported as unknown and the run's total is marked partial, never silently zero
    ```md
    - **Cuts through:** agents, the manifest, the sidecar, results
    - **Depends on:** K-020
    - **PRD:** FR-13.1 to FR-13.4
    ```

### K-022 · A model plays a complete game

  - tags: [slice-4, test, fr-6, sc-1, sc-4]
  - priority: high
  - workload: Normal
  - defaultExpanded: true
  - steps:
      - [ ] One model plays a full game against reference or scripted seats
      - [ ] Every decision turn lands in the sidecar
      - [ ] The exact message list for any decision is reconstructed from the run directory alone, with nothing else
      - [ ] The god log verifies and replays like any v1 record
    ```md
    - **Cuts through:** everything in this slice
    - **Depends on:** K-021
    - **PRD:** FR-10.3, FR-10.4, SC-1, SC-4
    - **Slice exit:** the first record in this project that contains a model's actual play, and is still verifiable.
    ```

### K-023 · The redo loop

  - tags: [slice-5, policy, fr-7, sc-15]
  - priority: high
  - workload: Normal
  - defaultExpanded: true
  - steps:
      - [ ] A rejected action returns to the model inside the same decision turn, not as a fresh turn
      - [ ] The redo prompt is one shared artefact, hashed like any other prompt
      - [ ] The redo budget is a config value, identical for every model and every seat
      - [ ] The attempt index and the rejection that prompted each retry are recorded per attempt
    ```md
    - **Cuts through:** agents, the facade, the sidecar, the manifest, core/assist
    - **Depends on:** K-022
    - **PRD:** FR-7.1 to FR-7.4, FR-9.6, SC-15
    - **Why:** The table blocking an illegal move and asking the player to redo it, not a forfeit and not a substitute. It works because it never supplies a choice the model failed to make.
    - **Leak risk:** the redo turn is a channel through which L2 enumeration could reach an L0 model. FR-7.4 governs what it reveals, and K-012 is where that is proved.
    ```

### K-024 · Exhaustion abandons the game

  - tags: [slice-5, policy, records, fr-7, sc-15]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] Exhausting the redo budget stops the game and records it abandoned, with the failing decision, the final rejection, the attempt count and the responsible seat and model
      - [ ] No synthetic terminal record is written
      - [ ] verify reports an abandoned game as incomplete without failing the run
      - [ ] An abandoned game is excluded from outcome aggregates and counted per model
    ```md
    - **Cuts through:** agents, the runner's game loop, the log, results
    - **Depends on:** K-023
    - **PRD:** FR-7.5, FR-11.6, FR-11.6a, FR-11.8, SC-15
    - **Why:** A synthetic terminal record would make an abandoned game indistinguishable from a lost one, and the entire point is that they are different findings about a model.
    ```

### K-025 · Failure kinds and the no-hang guarantee

  - tags: [slice-5, policy, fr-7, sc-10]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] Failure kinds are an enumerable, declared set, like v1's rejection codes
      - [ ] Malformed tool call, prose-only, timeout and runaway are each handled and charged to the correct budget
      - [ ] A runaway does not consume a redo; prose-only does not consume a redo either
      - [ ] Every mock behaviour terminates, completed or abandoned
    ```md
    - **Cuts through:** agents, the mock provider, the log, results
    - **Depends on:** K-024
    - **PRD:** FR-7.6 to FR-7.11, SC-10, NFR-4
    - **Why:** Charging every failure to the same budget would misreport why a game ended. A looping model never proposed an illegal move, so its record must not say it did.
    ```

### K-026 · Context policy

  - tags: [slice-5, context, fr-8]
  - priority: medium
  - workload: Normal
  - steps:
      - [ ] The context strategy is a declared config value, with delta-with-refresh as the default
      - [ ] Three strategies supported: full every turn, delta with periodic refresh, bounded window
      - [ ] The strategy is recorded in the manifest and identical across models
      - [ ] The exact message list sent for any decision is reconstructible from the record
    ```md
    - **Cuts through:** agents, core/delta, notation, the manifest
    - **Depends on:** K-022
    - **PRD:** FR-8.1 to FR-8.4
    - **Why:** Full projection every turn is less confounded but pays the whole board on every decision, and on a 743-action game that is the difference between an affordable experiment and an unaffordable one.
    ```

### K-027 · The runner core

  - tags: [slice-6, runner, fr-11, fr-10]
  - priority: high
  - workload: Hard
  - steps:
      - [ ] Seats map to agents: an LLM agent, a reference player, or a scripted agent
      - [ ] A game runs to completion or abandonment entirely through the facade
      - [ ] The run manifest is written with config, seats, policies, prompt hashes, provider identity and the price table
      - [ ] The runner contains no game-specific logic; every game fact is a plugin declaration
    ```md
    - **Cuts through:** runner, the facade, agents, the manifest, results
    - **Depends on:** K-025, K-026
    - **PRD:** FR-11.1, FR-11.2, FR-11.7, FR-10.1, FR-10.2
    ```

### K-028 · The experiment-design matrix

  - tags: [slice-6, design, fr-11, sc-7]
  - priority: high
  - workload: Hard
  - defaultExpanded: true
  - steps:
      - [ ] seating (fixed, rotated, random) × initial_configuration (fixed, random, drawn per experiment or per game) × replicates
      - [ ] The game count is derived as replicates × (rotated ? seats : 1), and the derivation is recorded, not only the product
      - [ ] A rotated design is N cyclic shifts, so every agent occupies every seat index equally often, repeated agents included
      - [ ] Each game records its replicate index, rotation index, seat assignment, seed and configuration
    ```md
    - **Cuts through:** runner, the plugin's benchmark profile, the manifest, results
    - **Depends on:** K-027
    - **PRD:** FR-11.3, FR-11.4, FR-11.9, FR-11.10, SC-7
    - **Why:** Randomness is fought by declaring which axes vary and recording where each game sits in the design, not by mandating one rotation. The cyclic-shift rule handles a table mixing distinct and repeated agents without a special case.
    ```

### K-029 · Axes a game does not have

  - tags: [slice-6, design, fr-11]
  - priority: high
  - workload: Normal
  - defaultExpanded: true
  - steps:
      - [ ] Initial configuration varies only where the plugin declares configuration_is_variable
      - [ ] Asking a game with a single fixed starting position for a random configuration is a clear configuration error, never a silently ignored request
      - [ ] The single-game exploration case is first-class and is what an undeclared design gives
      - [ ] An uncontrolled axis is allowed but marked, and the marking travels into results.json
    ```md
    - **Cuts through:** runner, the plugin declaration in ARCHITECTURE section 7.10, results
    - **Depends on:** K-028
    - **PRD:** FR-11.11, FR-11.12, FR-11.13
    - **Why:** Seating and starting configuration are independent axes. A game whose starting position is fixed still gives one seat the first move, so it varies the first and not the second. A design model that assumed every game can be randomised would be wrong about such a game the day it arrived.
    ```

### K-030 · Reference players

  - tags: [slice-6, agents, fr-12, sc-8]
  - priority: medium
  - workload: Normal
  - steps:
      - [ ] A random-legal player, reusing v1's fuzz action selector rather than reimplementing one
      - [ ] A greedy-heuristic player: deterministic, and explainable in a paragraph
      - [ ] Both usable in any seat, including a table mixed with LLM agents
      - [ ] Neither is ever scored, and both appear only as reference rows
    ```md
    - **Cuts through:** agents, core/fuzzing, the runner, results
    - **Depends on:** K-027
    - **PRD:** FR-12.1 to FR-12.4, SC-8
    - **Why:** Without a non-LLM reference, a win rate is a number with no scale. These are what make the first model result interpretable rather than merely reproducible.
    ```

### K-031 · Concurrent decision dispatch

  - tags: [slice-6, runner, fr-11, nfr-2]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] Concurrent decisions are dispatched in parallel rather than serially
      - [ ] Results are applied in the game's declared resolution order, so the record stays deterministic
      - [ ] Wall-clock cost does not scale with the number of concurrent decisions
      - [ ] A test asserts the record is identical whether the decisions are answered in parallel or serially
    ```md
    - **Cuts through:** runner, the facade's decision queue, the log
    - **Depends on:** K-027
    - **PRD:** FR-11.2, NFR-2
    - **Why:** Discards after a 7 and trade responses are concurrent by rule. Answering them serially multiplies a model-driven game's wall clock for no gain; answering them out of order would break the record.
    ```

### K-032 · results.json

  - tags: [slice-7, results, fr-10]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] Per game: outcome, place, actions, rejections by code, failures by kind, tokens, cost, latency, abandonment
      - [ ] Per seat and per model aggregates, with abandonment in its own row
      - [ ] The experiment design and any uncontrolled-axis marking carried through from the manifest
    ```md
    - **Cuts through:** runner, the manifest, the sidecar, the log
    - **Depends on:** K-029, K-031
    - **PRD:** FR-10.6, FR-11.8, FR-11.12
    - **Why:** v2 emits facts, not inferences. `results.json` is where a run states what happened; anything that would be a claim about models belongs to v3.
    ```

### K-033 · CLI completion

  - tags: [slice-7, cli, fr-14]
  - priority: medium
  - workload: Normal
  - steps:
      - [ ] serve, run, inspect-run and play-live
      - [ ] Every command exits non-zero on failure and prints no traceback for an expected failure
      - [ ] inspect-run shows the decision turns of one seat in one game, with the exact messages and responses
      - [ ] v1's replay, verify, inspect and fuzz are unchanged, and still verify v1 records exactly as before
    ```md
    - **Cuts through:** adapters/cli, the facade, results, the run directory
    - **Depends on:** K-032
    - **PRD:** FR-14.1 to FR-14.6
    - **Why:** Keeping the v1 commands working unchanged is the regression net for the whole release. A v2 record must verify with the same command that verifies a v1 one.
    ```

### K-034 · Unattended CI campaign

  - tags: [slice-7, test, sc-12, fr-14]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] At least 50 games on the mock provider, deliberately including every failing behaviour
      - [ ] Completes unattended, with bounded concurrency and no manual step
      - [ ] Produces results.json with per-game and per-seat accounting
      - [ ] Runs inside the existing gate, not beside it
    ```md
    - **Cuts through:** runner, agents, the mock, results, the gate
    - **Depends on:** K-033
    - **PRD:** SC-12, NFR-4
    - **Why:** Unattended operation is exactly what a mock can stress at scale and for free, which is why this criterion is the mock's and not the real provider's.
    ```

### K-035 · Budget-bounded real demonstration

  - tags: [slice-7, test, fr-13, sc-16]
  - priority: medium
  - workload: Normal
  - steps:
      - [ ] A run against OpenRouter that stops when its declared budget is exhausted
      - [ ] An estimated cost is stated before the run starts
      - [ ] The run reports what the budget bought: games, decisions, tokens, cost and abandonment rate
      - [ ] The number of games is reported as an outcome of the budget, not as an input
    ```md
    - **Cuts through:** runner, the OpenRouter adapter, cost accounting, results
    - **Depends on:** K-034
    - **PRD:** FR-13.3, NFR-3, SC-16
    - **Why:** The same game count costs roughly four dollars on a cheap model and ninety on a frontier one, so a fixed count would be measuring the wrong thing (Q7).
    ```

### K-036 · Traceability and the acceptance record

  - tags: [slice-8, acceptance, sc-13]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] Every functional requirement in PRD-v2 section 8 traced to at least one named test
      - [ ] SC-1 to SC-16 each demonstrated by a named command whose output is captured
      - [ ] Anything not met is written down as not met, with its reason, as v1's acceptance record did
      - [ ] The gate runs everything: ruff, ruff format, mypy and every test
    ```md
    - **Cuts through:** the entire release
    - **Depends on:** K-035
    - **PRD:** SC-13, section 5
    ```

### K-037 · Documentation for operators and adapter authors

  - tags: [slice-8, docs]
  - priority: low
  - workload: Easy
  - steps:
      - [ ] How to add a provider adapter, including the conformance suite as the acceptance test
      - [ ] How to read a run directory: what is in the god log, what is in the sidecar, what results.json aggregates
      - [ ] How to design a run: the three design axes and what each one controls
    ```md
    - **Cuts through:** README, the run directory, the design model
    - **Depends on:** K-036
    - **PRD:** D9
    ```

## Done

### K-001 · Settle and pin the v2 dependencies

  - tags: [slice-0, infra, fr-16, sc-11]
  - priority: high
  - workload: Normal
  - steps:
      - [x] MCP SDK, ASGI server and provider-client dependencies chosen, pinned, and justified in the pyproject header comment
      - [x] lgbg/core and lgbg/games still resolve to zero third-party runtime dependencies
      - [x] A test asserts the core and games dependency list is empty, so the boundary fails the build when it erodes
    ```md
    - **Cuts through:** pyproject, uv.lock, the dependency-boundary test, every later layer
    - **Depends on:** nothing
    - **PRD:** FR-16.1 to FR-16.4, SC-11
    - **Why:** The boundary is cheapest to defend before there is pressure to break it. Once host and agents exist, an import that reaches back into core looks harmless and is not.
    - **Slice note:** slice 0 is the one exception to the thin-slicing rule and it does not end in a demo. The dependency decision and the frozen artefact shapes are what every later slice is built to, and guessing at them inside slice 1 is how the shape becomes three incompatible shapes. Recorded here rather than left as an omission.
    - **Evidence:** `pyproject.toml` declares three exactly-pinned dependencies, each justified in the file's own header comment: `mcp==1.30.0` (the official SDK, FR-16.3; the 1.x line rather than 2.x, whose tracing, JWT and second-validator additions are dependencies with no benchmark value), `uvicorn==0.54.0` (the ASGI server FR-2.7 buys, with no framework beside it) and `httpx==0.28.1` (the OpenRouter adapter's one HTTP client, because a vendor SDK would carry the retry and repair policy FR-5.5 forbids). `uv.lock` is regenerated, which is what CI's `uv sync --locked` reads. The boundary is `tests/tooling/test_dependency_boundary.py`: every module of `lgbg/core` and `lgbg/games` is parsed and any import that is neither the standard library nor `lgbg` fails the build, and every declared dependency must be exactly pinned and named in the header comment - with controls that prove the scan flags `import mcp`, that a version range is refused and that an unjustified name is reported.
    ```

### K-002 · Freeze the v2 artefact contracts

  - tags: [slice-0, records, fr-10, sc-4]
  - priority: high
  - workload: Normal
  - steps:
      - [x] run.json extended on paper: design, seats, policies, prompt hashes, price table, provider identity
      - [x] The decision sidecar record shape declared: attempt, redo budget, rejection, route, native tools, usage, cost, latency, failure
      - [x] A fixture manifest and a fixture decision record validate against the declared shape
      - [x] The god log is confirmed unchanged, field for field
    ```md
    - **Cuts through:** run manifest, sidecar, the log reader, every later slice that writes a record
    - **Depends on:** nothing
    - **PRD:** FR-10.1 to FR-10.6, FR-11.10, SC-4
    - **Why:** v1's god log is frozen and stays frozen. Everything new goes in the sidecar, so freezing the sidecar shape now means slices 3 to 7 add fields to a shape instead of inventing one each.
    - **Evidence:** `lgbg/core/contracts.py` declares both shapes as JSON Schema data, checked by v1's own `core.schema` validator rather than a second general-purpose one. The manifest carries the run config, the seats with their agents and sampling, the design with its derivation, every policy value, the four prompt hashes of FR-9.1, the provider identities and the price table with the time it was read. The decision record carries the attempt index, the redo budget, the rejection that prompted the retry, the upstream route, native-tool support, usage, cost, latency and failure kind. `tests/fixtures/v2/run.json` and `decisions.jsonl` validate against them, and both shapes are closed, so a later slice amends the declaration instead of inventing a record. Three decisions are written down in the module: money is integer micro-dollars, sampling integer thousandths and latency integer milliseconds, because every artefact is written through the one canonical serialiser and that serialiser refuses floats; the transcript is provider-neutral while the exact payload stays the adapter's (FR-5.4). `GOD_LOG_FIELDS` freezes the god log field for field, and `tests/core/test_contracts.py` holds both the seven-game corpus and the runtime's writer to it.
    ```

### K-003 · Session facade over the v1 engine

  - tags: [slice-1, facade, fr-1, nfr-6]
  - priority: high
  - workload: Hard
  - defaultExpanded: true
  - steps:
      - [x] One component owns mutable state: create, read projection, read pending decisions, submit action, read decision surface, read outcome
      - [x] No game-specific operation exists anywhere in the facade
      - [x] An action for a player with no open decision is rejected with the v1 core code, not queued
      - [x] Concurrent access is safe: several sessions advance in parallel, and one session may have several open decisions answered at once
    ```md
    - **Cuts through:** lgbg/host, the v1 engine and log, the session registry, and the logging path
    - **Depends on:** K-002
    - **PRD:** FR-1.1 to FR-1.6, NFR-6
    - **Why:** The single authority. Every surface above is a transport over this, so whether the whole release can be trusted rests on this being the only mutable thing.
    - **Evidence:** `lgbg/host/facade.py`: `SessionFacade` is the one mutable authority - create, read a projection, read the open decisions, submit an action, read the decision surface at the run's assist level, read the outcome, end the session - closed as a set in `PUBLIC_OPERATIONS` and asserted against the class, so an operation is a decision rather than an accident. One lock per session and one around the registry, so games advance in parallel; a session holding several open decisions answers each on a state that only moves when an action is accepted. The facade writes the terminal record itself the instant an accepted action makes the game terminal, so a completed game cannot be mistaken for an abandoned one, and `end_session` leaves a record with no terminal line that still replays. `tests/host/test_facade.py` covers the rejection path (the core's `NOT_YOUR_DECISION`, no state change, nothing queued), one code path over two games of different shapes, eight parallel sessions producing identical hash chains, and a four-way concurrent decision set answered at once and verified afterwards. `tests/tooling/test_layering.py` adds that the host layer never imports a game.
    ```

### K-004 · Prove the facade does not change the game

  - tags: [slice-1, facade, test, fr-1, sc-2]
  - priority: high
  - workload: Normal
  - steps:
      - [x] The same action sequence driven through the facade and through v1's GameRun produces byte-identical god logs
      - [x] All seven v1 golden games replay through the new path with identical final hashes
      - [x] The test is the corpus, not a new fixture: nothing is written that v1 did not already pin
    ```md
    - **Cuts through:** facade, core run, core log, the golden corpus
    - **Depends on:** K-003
    - **PRD:** FR-1.4, SC-2
    - **Why:** The cheapest possible proof that a new layer has not altered the game, and stronger than any new test could be: it asks whether v1's own evidence still holds through the new path.
    - **Evidence:** `tests/host/test_facade_equivalence.py` (9 tests) reads only v1's corpus: the seven committed records under `tests/golden/catan`, and the action sequence each one already carries. The complete 743-action `full_game` is driven once through a bare `GameRun` and once through `SessionFacade`; the produced god logs are compared byte for byte and then against the committed record. All seven records are replayed action by action through a fresh facade, each new log is walked by v1's own `verify`, and its final hash is compared with the hash that verifier reports for the committed record; the two games that stop before termination use the same path, with the facade leaving no synthetic terminal line. The control test pins the corpus to the seven names, so a shrinking corpus cannot quietly test less. A deliberate mutation - removing the facade's terminal settling - made the byte-identity test fail, and was reverted.
    ```

### K-005 · Serve v1's generated tool definitions over MCP

  - tags: [slice-1, mcp, fr-3, sc-6]
  - priority: high
  - workload: Normal
  - steps:
      - [x] Tool definitions come from lgbg.core.tools.tool_definitions, with no per-game code
      - [x] Each action type the plugin declares appears exactly once, with its declared input schema
      - [x] An action tool call reaches the facade and returns the engine's answer, rejection included
    ```md
    - **Cuts through:** adapters/mcp, core/tools, the facade, the plugin's own schema
    - **Depends on:** K-003
    - **PRD:** FR-3.1, FR-3.2, SC-6
    - **Why:** v1 already emits the shape MCP wants. This is the proof that the plugin system delivers its claim, and it should stay small enough to be obviously correct.
    - **Evidence:** `lgbg/adapters/mcp/server.py` calls `tool_definitions` for the game and maps every generated name, description and `inputSchema` onto `types.Tool`; no action is named in the adapter. A benchmark surface is bound to one session and seat, so its action schema is the plugin's exactly, including the `oneOf` union. `tests/adapters/mcp/test_mcp_tools.py` pins names, descriptions and schemas against the generator, proves each action appears once, drives an accepted and a rejected action through the facade (the rejection keeps state and returns `TOKENS_UNAVAILABLE`), proves the tool set is identical at L0 and L2, and scans the adapter for game nouns. A deliberate mutation replacing the generator's description with a literal failed the generator test, and was reverted.
    ```

### K-006 · Observation and decision resources

  - tags: [slice-1, mcp, fr-3, sc-14]
  - priority: high
  - workload: Normal
  - steps:
      - [x] A resource for the player's projection and one for the pending decisions
      - [x] Resource URIs are game-agnostic in shape and never name a game mechanic
      - [x] Renderings come from the game's own render method, so the CLI and MCP share one renderer
      - [x] A resource read consumes no randomness and mutates nothing
    ```md
    - **Cuts through:** adapters/mcp resources, Game.render, the facade, notation
    - **Depends on:** K-005
    - **PRD:** FR-3.6 to FR-3.9
    - **Why:** A second renderer written for MCP would drift from the CLI's, and divergent renderings of the same state are a confound in anything a model is shown.
    - **Evidence:** `lgbg/adapters/mcp/server.py` advertises and serves `state` and `decisions` at `<game>://sessions/{id}/...`; a state read is `Game.render(facade.projection(...))` and a decisions read is the facade's own list through the canonical serialiser. `tests/adapters/mcp/test_mcp_resources.py` compares fixture and Catan renderings with the game's own renderer, pins the URI shape, and proves purity by reading resources five times in one run and comparing its god log byte for byte with an unread control after the same random action. A deliberate mutation replacing the renderer with canonical JSON failed the Catan test, and was reverted.
    ```

### K-007 · Stdio transport and the two profile entry points

  - tags: [slice-1, mcp, fr-3, sc-14]
  - priority: high
  - workload: Hard
  - defaultExpanded: true
  - steps:
      - [x] stdio transport serves a live session
      - [x] The sandbox entry point offers lifecycle tools; the benchmark entry point does not
      - [x] The profile is fixed when the server is constructed; no request and no configuration value can change it
      - [x] A test asserts that the benchmark entry point's served tool list contains no lifecycle tool
    ```md
    - **Cuts through:** adapters/mcp, the two CLI entry points, the facade factory
    - **Depends on:** K-006
    - **PRD:** FR-3.4, FR-3.4a, FR-3.4b, FR-3.4c, FR-3.5
    - **Why:** A model is a player, never an operator. Absence rather than gating is the mechanism, and the test is what turns absence into a fact instead of an intention (Q6).
    - **Evidence:** `build_server` fixes `Profile` at construction; `benchmark.py` and `sandbox.py` are separate entry points sharing it. The benchmark surface is bound to a runner-owned session and seat and never constructs lifecycle tools; the sandbox surface constructs `create_session`, `list_sessions` and `end_session`, with `list_sessions` reading the facade's own registry. `serve_stdio` runs either server over the SDK's stdio transport. `tests/adapters/mcp/test_mcp_profiles.py` asserts absence from the benchmark tool list (with a control that actions are still served), presence in sandbox, lifecycle create/list/end, and drives both entry points as real subprocesses over stdio: benchmark acts and reads, sandbox creates and reads. A deliberate mutation constructing lifecycle tools for both profiles failed the absence test, and was reverted.
    ```

### K-008 · A client that knows nothing about Catan

  - tags: [slice-1, cli, mcp, sc-6]
  - priority: medium
  - workload: Normal
  - steps:
      - [x] A client drives itself entirely from tools/list and the exposed resources
      - [x] It creates a session, reads a projection, and plays a legal opening placement
      - [x] No game-specific code exists in the client at all
    ```md
    - **Cuts through:** adapters/cli, the MCP client path, the facade
    - **Depends on:** K-007
    - **PRD:** FR-3.2, SC-6
    - **Why:** This is the only honest test of plug-and-play. If the client must know what a settlement is, the surface has failed no matter how many tests pass.
    - **Evidence:** `lgbg/adapters/cli/mcp_client.py` holds `GameClient`: it reads `tools/list` and `list_resources`, opens a session through the advertised lifecycle tool, reads the projection resource, takes the first decision from the decisions resource, and builds the action arguments from that action tool's own JSON Schema. It names no game, action, piece or coordinate. `tests/cli/test_mcp_client.py` starts the real sandbox server over stdio, asks it for a Catan session, reads the projection, acts on the first opening decision, and asserts the action was accepted, that the god log holds exactly that one accepted action, and that v1's `verify` replays it; a source scan rejects any game name or action name in the client. A deliberate mutation ignoring the decision's `schema_ref` and choosing the first action tool instead was rejected and failed the test, and was reverted.
    ```

### K-009 · A complete game played through the MCP surface

  - tags: [slice-1, mcp, test, sc-14, fr-1]
  - priority: high
  - workload: Normal
  - defaultExpanded: true
  - steps:
      - [x] A scripted client plays a complete four-player game through the real stdio transport
      - [x] The resulting god log verifies and replays to every intermediate state
      - [x] A human plays a full game by hand through play-live, using only the published tools and resources
      - [x] Both paths produce records that verify; neither is a special case
    ```md
    - **Cuts through:** everything in this slice
    - **Depends on:** K-008
    - **PRD:** FR-1.4, SC-14
    - **Slice exit:** the named command is a played game, not a passing unit test.
    - **Why this ordering:** if the first thing driven through the surface were a model, a defect in the surface and a defect in the agent would look identical, and the debugging budget would go to the wrong layer.
    - **Evidence:** `tests/adapters/mcp/test_full_game.py` drives the committed 743-action four-player fixture through the real sandbox server over stdio, one generated action tool at a time; the resulting god log is byte-identical to `tests/golden/catan/full_game.god.jsonl`, v1's `verify` reports 743 actions and no rejections, and `replay` yields all 744 intermediate states plus the terminal record. `lgbg/adapters/cli/live.py` adds the slice's named command, `python -m lgbg.adapters.cli play-live`, which starts the same sandbox entry point over stdio, opens a session through `create_session`, shows the projection and decisions, and reads one JSON action per line. `tests/cli/test_play_live.py` feeds the same 743 actions to that command and gets the same byte-identical record and the same verified replay. Both paths go through `GameClient` and the MCP tools/resources; neither touches the facade directly. A deliberate mutation dropping an action's parameters made the first tool call fail validation and broke the scripted test, and was reverted.
    ```

### K-010 · Assist level gates the resource surface

  - tags: [slice-2, mcp, fr-4, assist]
  - priority: high
  - workload: Hard
  - defaultExpanded: true
  - steps:
      - [x] At L0 only the projection is exposed, and rejection detail is minimal and leaks no enumeration
      - [x] At L1 the decision surface is added: action types, costs, permitted parameter domains, never the cross product
      - [x] At L2 enumerated legal actions and full rejection detail
      - [x] Assist level is set by the operator and is not readable or adjustable by the client
    ```md
    - **Cuts through:** adapters/mcp resources, core/assist, the facade, run config
    - **Depends on:** K-009
    - **PRD:** FR-4.1 to FR-4.4
    - **Why:** v1 proved the levels with scripted actions and no surface. The surface is new, so the leak channels are new.
    - **Evidence:** `lgbg/adapters/mcp/server.py` adds `SURFACE_RESOURCE` (`<game>://sessions/{id}/surface?player=N`) and gates the decision reads on the level fixed at construction: `_list_resources` advertises only `state` at L0 and adds `decisions` plus `surface` at L1/L2, while `_read_resource` refuses the decision reads at L0 even when a client guesses the URI. `_read_surface` is `facade.decision_surface`, so it is v1's one `render_decision` at the run's level - domains at L1, enumeration at L2 - rather than a second renderer. `_act` answers a refusal with `rejection_view` at `DEFAULT_DETAIL_FOR_ASSIST[assist]`: L0 is `{"ok": false, "error": ...}` and nothing beside it, L1 keeps the facts, L2 keeps the alternative lists. The level is an operator argument to `build_server`; no tool or resource carries it, and `create_session` declares no `assist` field for a request to set. `tests/adapters/mcp/test_mcp_assist.py` holds the ladder: L0 advertises state only and refuses `decisions`/`surface`; L1's surface equals the facade's and names `vertex=one of ...` without enumerating; L2 lists the placements and drops the domain line; a real Catan setup-road refusal (`NOT_CONNECTED`) has keys exactly `{ok,error}` at L0, `{edge,must_touch}` at L1, and `touches` at L2; a sandbox `create_session` carrying `assist` is rejected by the served schema. `tests/cli/test_play_live.py` covers the product path at L0, where `--player` names the seat because there is no decisions resource. Two deliberate mutations - always advertising the decision resources, and always rendering full rejections - each failed the L0 tests and were reverted. Gate: 997 passed, 1 skipped.
    ```

### K-011 · The tool set is constant across assist levels

  - tags: [slice-2, mcp, test, fr-3, fr-4]
  - priority: high
  - workload: Easy
  - steps:
      - [x] tools/list is identical at L0, L1 and L2
      - [x] Assist level changes only what a resource reveals and what a rejection explains
      - [x] A test compares the served tool list across all three levels
    ```md
    - **Cuts through:** the tool generator, the resource surface, config
    - **Depends on:** K-010
    - **PRD:** FR-3.3
    - **Why:** If the tool list shrank at L0, the action vocabulary itself would become an assist channel and assist level would stop being a clean variable.
    - **Evidence:** `tests/adapters/mcp/test_mcp_tools.py` replaces the two-level comparison with `test_tools_list_is_identical_at_all_three_assist_levels`, parametrized over the benchmark and sandbox profiles: every served tool's name, description and full `inputSchema` must be equal at L0, L1 and L2. The sandbox is included because its lifecycle schemas are the ones that could plausibly have grown a level, and the benchmark because a missing action at L0 would make the vocabulary itself a hint. `test_the_projection_and_pending_decisions_do_not_move_with_the_level` holds the other half of FR-3.3: the projection resource is byte-identical at all three levels, and the pending-decisions resource is identical at L1 and L2. What does move is confined to the decision surface and the refusal, which K-010's tests assert. A deliberate mutation dropping one tool from `tools/list` at L0 failed both profile cases, and was reverted. Gate: 999 passed, 1 skipped.
    ```

### K-012 · Assist equivalence through the MCP surface

  - tags: [slice-2, test, fr-4, sc-3]
  - priority: high
  - workload: Normal
  - steps:
      - [x] One scripted action file played at L0, L1 and L2 through the real transport produces byte-identical god logs, apart from the header's assist field
      - [x] The test drives stdio, not the facade directly
      - [x] The redo turn is covered: a rejection at L0 must not reveal the alternatives a rejection at L2 does
    ```md
    - **Cuts through:** MCP surface, config, the log, replay
    - **Depends on:** K-011
    - **PRD:** FR-4.5, FR-7.4, SC-3
    - **Why:** v1 proved this for a scripted player with no surface. Proving it again through one is not redundant: the surface is exactly where a level can leak.
    - **Evidence:** `tests/adapters/mcp/test_assist_equivalence.py` plays one committed script (`tests/fixtures/v2/assist_script.json`, 21 attempts including two refusals and a terminal verdict) three times through the real sandbox entry point over stdio, one process per level. The records are byte-identical below the header; the only header fields that move are `assist` and the `rejection_detail` tier it defaults to, and the test asserts that nothing else moved. The L0 record verifies with v1's `verify` and replays to all 22 states. The redo turn is followed on a wrong-seat attempt: L0 answers `{"ok": false, "error": "NOT_YOUR_DECISION"}`, L1 adds the sentence but withholds the list, L2 adds `details: {"open_players": [0]}`, and the god log keeps that detail at every level. Two deliberate mutations - making every refusal full-detail, and letting the level enter an action record's result - each failed the relevant test and were reverted. Gate: 1001 passed, 1 skipped.
    ```

### K-013 · The HTTP host, and three surfaces that agree

  - tags: [slice-2, host, facade, fr-2, sc-2]
  - priority: medium
  - workload: Hard
  - steps:
      - [x] ASGI application with routing written directly against the ASGI interface, no framework
      - [x] A session registry assigns and validates game_id
      - [x] An illegal move is a 200 with a rejection body; transport failures are HTTP errors, and the two are never confused
      - [x] The same actions through MCP, HTTP and in-process produce byte-identical god logs
    ```md
    - **Cuts through:** host, facade, registry, the equivalence test
    - **Depends on:** K-009
    - **PRD:** FR-2.1 to FR-2.7, FR-1.4, SC-2
    - **Why:** Three surfaces, one hash. This is the test that stops the transports drifting into three subtly different games.
    - **Evidence:** `lgbg/host/http.py` is `HttpHost`, an ASGI application whose routing is a method-and-segment dispatch written against the interface: `POST/GET /sessions`, `DELETE /sessions/{id}`, and `GET state|decisions|surface|outcome` plus `POST actions`. Every response, success or failure, carries `"schema": "lgbg.host.v1"`; a rejection is a 200 whose body is the engine's full refusal, while a malformed body, an unknown session, a wrong method and a duplicate id are 400, 404, 405 and 409 with the same JSON envelope. `lgbg/host/registry.py` is the host's table over the facade: it validates the id as a path segment, allocates it through the facade, records the game, refuses a second claim, and is consulted on every route so a session the host did not open is not served through it. The HTTP body is read by `RunConfig.from_mapping`, so the transport does not re-implement the configuration ladder and never names the assist enum. `tests/host/test_http.py` (10 tests) drives the application with raw ASGI scopes, covering every route, the 200-rejection/HTTP-error split, the schema version, the seat requirement and the lifespan handshake; `tests/host/test_registry.py` covers allocation, collision, malformed ids and ending; `tests/host/test_surface_equivalence.py` plays the committed 21-attempt script through MCP, HTTP and the facade in-process and asserts the three god logs are byte-identical, then verifies and replays each. Two deliberate mutations - turning a rejection into a 400, and letting the HTTP path alter an action - each failed and were reverted. Gate: 1016 passed, 1 skipped.
    ```

### K-014 · Provider protocol and usage normalisation

  - tags: [slice-3, provider, fr-5]
  - priority: high
  - workload: Normal
  - steps:
      - [x] The narrow interface of ARCHITECTURE section 13, and nothing wider
      - [x] Usage normalised to prompt, completion and total tokens
      - [x] A provider that omits usage is marked unknown, never recorded as zero
    ```md
    - **Cuts through:** agents/providers, config, cost accounting
    - **Depends on:** K-002
    - **PRD:** FR-5.1, FR-5.6
    - **Evidence:** `lgbg/agents/providers/base.py` declares `Provider` as a runtime-checkable protocol whose only member is `complete(messages, tools, config) -> Completion`; a test asserts the protocol's attribute set is exactly `{"complete"}`, that it is asynchronous, and that the parameter list is the one ARCHITECTURE.md section 13 names. The request and answer are plain immutable values: `Message`, `ToolCall` (arguments as an object or as unparsed text, per FR-7.6), `ToolSpec`, `Completion`, and `CompletionConfig` carrying a model and integer-thousandth `Sampling`. `Usage` is a non-negative triple; `Usage.normalise` derives a total the provider omitted from its parts, and returns `None` when either part is missing, so an omission is unknown rather than zero. A zero report stays a known `Usage(0, 0, 0)`. The value mappings are checked against K-002's frozen decision schema, with `usage` both a triple and `null`. A deliberate mutation turning an omitted usage into `Usage(0, 0, 0)` failed four tests and was reverted. Gate: 1033 passed, 1 skipped.
    ```

### K-015 · The mock provider

  - tags: [slice-3, provider, test, fr-5, fr-15]
  - priority: high
  - workload: Normal
  - defaultExpanded: true
  - steps:
      - [x] Scripted behaviours: correct play, always-illegal, malformed arguments, prose-only, timeout, runaway
      - [x] Every test in the suite uses it; no test needs network access or a key
      - [x] Its behaviours are named, so a failure kind in a record can be traced to the behaviour that caused it
    ```md
    - **Cuts through:** agents/providers, the tool loop, every policy test in slice 5
    - **Depends on:** K-014
    - **PRD:** FR-5.2, FR-15.1, FR-15.4, NFR-8
    - **Why:** Everything genuinely hard about v2 is a model behaving badly. The mock is what makes those behaviours testable at all, so it has to exist before the code that handles them, not after.
    - **Evidence:** `lgbg/agents/providers/mock.py` declares `Behaviour` with six named values - `correct-play`, `always-illegal`, `malformed-arguments`, `prose-only`, `timeout`, `runaway` - and `MockProvider`, which is structurally a `Provider`. Correct play returns a scripted action per decision and raises `MockScriptError` rather than repeating the last move when the script ends; always-illegal repeats the supplied refused action; malformed arguments name a real offered tool but carry unparseable text, the shape the record keeps; prose-only emits text and no call; timeout raises `ProviderTimeoutError`; runaway keeps emitting calls to `read_state`, so only the step budget can stop it. `label` is `mock:<behaviour>` and `calls` counts attempts, so a record can name the behaviour that produced a failure. Usage is reported by default and can be omitted, in which case it is `None`. `tests/agents/providers/test_mock.py` (11 tests) covers every behaviour, the script-exhaustion path and both usage answers; `tests/tooling/test_offline_suite.py` (4 tests) scans every test source for a call that would leave the process or an API-key name, excluding its own patterns, so the no-network/no-key property is enforced rather than asserted. Two deliberate mutations - turning timeout into text and coercing prose into a tool call - each failed and were reverted. Gate: 1048 passed, 1 skipped.
    ```

### K-016 · The OpenRouter adapter

  - tags: [slice-3, provider, fr-5, sc-9]
  - priority: high
  - workload: Hard
  - steps:
      - [x] Native tool calling, with model id, upstream route and native-tool support recorded per request
      - [x] A documented text protocol for a model without native tool calling, implemented in the adapter rather than the loop
      - [x] Pricing read from the gateway's model listing and recorded with the time it was read
      - [x] The same logical model routed differently is visible in the record
    ```md
    - **Cuts through:** agents/providers, the run manifest, cost accounting
    - **Depends on:** K-014, K-015
    - **PRD:** FR-5.2, FR-5.3, FR-5.8, FR-5.9
    - **Why:** One gateway is a benchmark decision: every model is then driven through the same request path, so a difference between models is not a difference between two client libraries.
    - **Evidence:** `lgbg/agents/providers/openrouter.py` is `OpenRouterProvider`: one OpenAI-compatible request path for every model. `complete` reads the gateway's listing once, decides native versus text from `supported_parameters`, sends function definitions or the one `TEXT_PROTOCOL` system instruction, and returns `CallMetadata` with the configured model, the response's `provider` route and whether native tools were used; the metadata rides on `Completion` and is deliberately outside the frozen response mapping. Native calls parse JSON-string arguments and keep the raw text when they do not parse; the text protocol parses one JSON object, optionally fenced, into the same `ToolCall`, while anything else stays prose. `read_pricing` reads the same listing, converts per-token decimal prices to integer micro-dollars per million tokens with `Decimal`, refuses negative or sub-micro prices, and stamps the table with an injected clock; the table validates against K-002's frozen manifest. `tests/agents/providers/test_openrouter.py` (20 tests) drives `httpx.MockTransport` only: native request and response, both text-protocol shapes, prose, malformed arguments, usage, route changes, pricing, unknown models, unrepresentable prices, a 500 that is not retried, a timeout, wire history and the structural seam. Two deliberate mutations - treating every model as native, and using 10^6 instead of 10^12 for the price scale - each failed and were reverted. Gate: 1068 passed, 1 skipped.
    ```
