# KANBAN-v2 · PRD-v2 · horizontal slices

## Todo
### K-001 · Settle and pin the v2 dependencies

  - tags: [slice-0, infra, fr-16, sc-11]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] MCP SDK, ASGI server and provider-client dependencies chosen, pinned, and justified in the pyproject header comment
      - [ ] lgbg/core and lgbg/games still resolve to zero third-party runtime dependencies
      - [ ] A test asserts the core and games dependency list is empty, so the boundary fails the build when it erodes
    ```md
    - **Cuts through:** pyproject, uv.lock, the dependency-boundary test, every later layer
    - **Depends on:** nothing
    - **PRD:** FR-16.1 to FR-16.4, SC-11
    - **Why:** The boundary is cheapest to defend before there is pressure to break it. Once host and agents exist, an import that reaches back into core looks harmless and is not.
    - **Slice note:** slice 0 is the one exception to the thin-slicing rule and it does not end in a demo. The dependency decision and the frozen artefact shapes are what every later slice is built to, and guessing at them inside slice 1 is how the shape becomes three incompatible shapes. Recorded here rather than left as an omission.
    ```

### K-002 · Freeze the v2 artefact contracts

  - tags: [slice-0, records, fr-10, sc-4]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] run.json extended on paper: design, seats, policies, prompt hashes, price table, provider identity
      - [ ] The decision sidecar record shape declared: attempt, redo budget, rejection, route, native tools, usage, cost, latency, failure
      - [ ] A fixture manifest and a fixture decision record validate against the declared shape
      - [ ] The god log is confirmed unchanged, field for field
    ```md
    - **Cuts through:** run manifest, sidecar, the log reader, every later slice that writes a record
    - **Depends on:** nothing
    - **PRD:** FR-10.1 to FR-10.6, FR-11.10, SC-4
    - **Why:** v1's god log is frozen and stays frozen. Everything new goes in the sidecar, so freezing the sidecar shape now means slices 3 to 7 add fields to a shape instead of inventing one each.
    ```

### K-003 · Session facade over the v1 engine

  - tags: [slice-1, facade, fr-1, nfr-6]
  - priority: high
  - workload: Hard
  - defaultExpanded: true
  - steps:
      - [ ] One component owns mutable state: create, read projection, read pending decisions, submit action, read decision surface, read outcome
      - [ ] No game-specific operation exists anywhere in the facade
      - [ ] An action for a player with no open decision is rejected with the v1 core code, not queued
      - [ ] Concurrent access is safe: several sessions advance in parallel, and one session may have several open decisions answered at once
    ```md
    - **Cuts through:** lgbg/host, the v1 engine and log, the session registry, and the logging path
    - **Depends on:** K-002
    - **PRD:** FR-1.1 to FR-1.6, NFR-6
    - **Why:** The single authority. Every surface above is a transport over this, so whether the whole release can be trusted rests on this being the only mutable thing.
    ```

## In Progress

## Blocked

## Backlog

### K-004 · Prove the facade does not change the game

  - tags: [slice-1, facade, test, fr-1, sc-2]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] The same action sequence driven through the facade and through v1's GameRun produces byte-identical god logs
      - [ ] All seven v1 golden games replay through the new path with identical final hashes
      - [ ] The test is the corpus, not a new fixture: nothing is written that v1 did not already pin
    ```md
    - **Cuts through:** facade, core run, core log, the golden corpus
    - **Depends on:** K-003
    - **PRD:** FR-1.4, SC-2
    - **Why:** The cheapest possible proof that a new layer has not altered the game, and stronger than any new test could be: it asks whether v1's own evidence still holds through the new path.
    ```

### K-005 · Serve v1's generated tool definitions over MCP

  - tags: [slice-1, mcp, fr-3, sc-6]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] Tool definitions come from lgbg.core.tools.tool_definitions, with no per-game code
      - [ ] Each action type the plugin declares appears exactly once, with its declared input schema
      - [ ] An action tool call reaches the facade and returns the engine's answer, rejection included
    ```md
    - **Cuts through:** adapters/mcp, core/tools, the facade, the plugin's own schema
    - **Depends on:** K-003
    - **PRD:** FR-3.1, FR-3.2, SC-6
    - **Why:** v1 already emits the shape MCP wants. This is the proof that the plugin system delivers its claim, and it should stay small enough to be obviously correct.
    ```

### K-006 · Observation and decision resources

  - tags: [slice-1, mcp, fr-3, sc-14]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] A resource for the player's projection and one for the pending decisions
      - [ ] Resource URIs are game-agnostic in shape and never name a game mechanic
      - [ ] Renderings come from the game's own render method, so the CLI and MCP share one renderer
      - [ ] A resource read consumes no randomness and mutates nothing
    ```md
    - **Cuts through:** adapters/mcp resources, Game.render, the facade, notation
    - **Depends on:** K-005
    - **PRD:** FR-3.6 to FR-3.9
    - **Why:** A second renderer written for MCP would drift from the CLI's, and divergent renderings of the same state are a confound in anything a model is shown.
    ```

### K-007 · Stdio transport and the two profile entry points

  - tags: [slice-1, mcp, fr-3, sc-14]
  - priority: high
  - workload: Hard
  - defaultExpanded: true
  - steps:
      - [ ] stdio transport serves a live session
      - [ ] The sandbox entry point offers lifecycle tools; the benchmark entry point does not
      - [ ] The profile is fixed when the server is constructed; no request and no configuration value can change it
      - [ ] A test asserts that the benchmark entry point's served tool list contains no lifecycle tool
    ```md
    - **Cuts through:** adapters/mcp, the two CLI entry points, the facade factory
    - **Depends on:** K-006
    - **PRD:** FR-3.4, FR-3.4a, FR-3.4b, FR-3.4c, FR-3.5
    - **Why:** A model is a player, never an operator. Absence rather than gating is the mechanism, and the test is what turns absence into a fact instead of an intention (Q6).
    ```

### K-008 · A client that knows nothing about Catan

  - tags: [slice-1, cli, mcp, sc-6]
  - priority: medium
  - workload: Normal
  - steps:
      - [ ] A client drives itself entirely from tools/list and the exposed resources
      - [ ] It creates a session, reads a projection, and plays a legal opening placement
      - [ ] No game-specific code exists in the client at all
    ```md
    - **Cuts through:** adapters/cli, the MCP client path, the facade
    - **Depends on:** K-007
    - **PRD:** FR-3.2, SC-6
    - **Why:** This is the only honest test of plug-and-play. If the client must know what a settlement is, the surface has failed no matter how many tests pass.
    ```

### K-009 · A complete game played through the MCP surface

  - tags: [slice-1, mcp, test, sc-14, fr-1]
  - priority: high
  - workload: Normal
  - defaultExpanded: true
  - steps:
      - [ ] A scripted client plays a complete four-player game through the real stdio transport
      - [ ] The resulting god log verifies and replays to every intermediate state
      - [ ] A human plays a full game by hand through play-live, using only the published tools and resources
      - [ ] Both paths produce records that verify; neither is a special case
    ```md
    - **Cuts through:** everything in this slice
    - **Depends on:** K-008
    - **PRD:** FR-1.4, SC-14
    - **Slice exit:** the named command is a played game, not a passing unit test.
    - **Why this ordering:** if the first thing driven through the surface were a model, a defect in the surface and a defect in the agent would look identical, and the debugging budget would go to the wrong layer.
    ```

### K-010 · Assist level gates the resource surface

  - tags: [slice-2, mcp, fr-4, assist]
  - priority: high
  - workload: Hard
  - steps:
      - [ ] At L0 only the projection is exposed, and rejection detail is minimal and leaks no enumeration
      - [ ] At L1 the decision surface is added: action types, costs, permitted parameter domains, never the cross product
      - [ ] At L2 enumerated legal actions and full rejection detail
      - [ ] Assist level is set by the operator and is not readable or adjustable by the client
    ```md
    - **Cuts through:** adapters/mcp resources, core/assist, the facade, run config
    - **Depends on:** K-009
    - **PRD:** FR-4.1 to FR-4.4
    - **Why:** v1 proved the levels with scripted actions and no surface. The surface is new, so the leak channels are new.
    ```

### K-011 · The tool set is constant across assist levels

  - tags: [slice-2, mcp, test, fr-3, fr-4]
  - priority: high
  - workload: Easy
  - steps:
      - [ ] tools/list is identical at L0, L1 and L2
      - [ ] Assist level changes only what a resource reveals and what a rejection explains
      - [ ] A test compares the served tool list across all three levels
    ```md
    - **Cuts through:** the tool generator, the resource surface, config
    - **Depends on:** K-010
    - **PRD:** FR-3.3
    - **Why:** If the tool list shrank at L0, the action vocabulary itself would become an assist channel and assist level would stop being a clean variable.
    ```

### K-012 · Assist equivalence through the MCP surface

  - tags: [slice-2, test, fr-4, sc-3]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] One scripted action file played at L0, L1 and L2 through the real transport produces byte-identical god logs, apart from the header's assist field
      - [ ] The test drives stdio, not the facade directly
      - [ ] The redo turn is covered: a rejection at L0 must not reveal the alternatives a rejection at L2 does
    ```md
    - **Cuts through:** MCP surface, config, the log, replay
    - **Depends on:** K-011
    - **PRD:** FR-4.5, FR-7.4, SC-3
    - **Why:** v1 proved this for a scripted player with no surface. Proving it again through one is not redundant: the surface is exactly where a level can leak.
    ```

### K-013 · The HTTP host, and three surfaces that agree

  - tags: [slice-2, host, facade, fr-2, sc-2]
  - priority: medium
  - workload: Hard
  - steps:
      - [ ] ASGI application with routing written directly against the ASGI interface, no framework
      - [ ] A session registry assigns and validates game_id
      - [ ] An illegal move is a 200 with a rejection body; transport failures are HTTP errors, and the two are never confused
      - [ ] The same actions through MCP, HTTP and in-process produce byte-identical god logs
    ```md
    - **Cuts through:** host, facade, registry, the equivalence test
    - **Depends on:** K-009
    - **PRD:** FR-2.1 to FR-2.7, FR-1.4, SC-2
    - **Why:** Three surfaces, one hash. This is the test that stops the transports drifting into three subtly different games.
    ```

### K-014 · Provider protocol and usage normalisation

  - tags: [slice-3, provider, fr-5]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] The narrow interface of ARCHITECTURE section 13, and nothing wider
      - [ ] Usage normalised to prompt, completion and total tokens
      - [ ] A provider that omits usage is marked unknown, never recorded as zero
    ```md
    - **Cuts through:** agents/providers, config, cost accounting
    - **Depends on:** K-002
    - **PRD:** FR-5.1, FR-5.6
    ```

### K-015 · The mock provider

  - tags: [slice-3, provider, test, fr-5, fr-15]
  - priority: high
  - workload: Normal
  - defaultExpanded: true
  - steps:
      - [ ] Scripted behaviours: correct play, always-illegal, malformed arguments, prose-only, timeout, runaway
      - [ ] Every test in the suite uses it; no test needs network access or a key
      - [ ] Its behaviours are named, so a failure kind in a record can be traced to the behaviour that caused it
    ```md
    - **Cuts through:** agents/providers, the tool loop, every policy test in slice 5
    - **Depends on:** K-014
    - **PRD:** FR-5.2, FR-15.1, FR-15.4, NFR-8
    - **Why:** Everything genuinely hard about v2 is a model behaving badly. The mock is what makes those behaviours testable at all, so it has to exist before the code that handles them, not after.
    ```

### K-016 · The OpenRouter adapter

  - tags: [slice-3, provider, fr-5, sc-9]
  - priority: high
  - workload: Hard
  - steps:
      - [ ] Native tool calling, with model id, upstream route and native-tool support recorded per request
      - [ ] A documented text protocol for a model without native tool calling, implemented in the adapter rather than the loop
      - [ ] Pricing read from the gateway's model listing and recorded with the time it was read
      - [ ] The same logical model routed differently is visible in the record
    ```md
    - **Cuts through:** agents/providers, the run manifest, cost accounting
    - **Depends on:** K-014, K-015
    - **PRD:** FR-5.2, FR-5.3, FR-5.8, FR-5.9
    - **Why:** One gateway is a benchmark decision: every model is then driven through the same request path, so a difference between models is not a difference between two client libraries.
    ```

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
