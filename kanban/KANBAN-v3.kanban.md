# KANBAN-v3 · PRD-v3 · horizontal slices

## Todo

## In Progress

## Blocked

## Backlog

### K-001 · The console starts and opens a record

  - tags: [slice-1, console, cli, shell, fr-1, fr-7, sc-12]
  - priority: high
  - workload: Hard
  - defaultExpanded: true
  - steps:
      - [ ] `pnpm build` from the committed lockfile produces `web/dist`; `lgbg console --root tests/golden/catan --no-browser` prints its URL and serves it, and a missing build or root exits non-zero naming the build command
      - [ ] Opening `full_game` reports its game, rules version, action count and a verification result produced by `replay()` and `verify()`, not inferred from the absence of an error
      - [ ] The ASGI app is separate from `lgbg.host`, imports neither the host nor a game, and no lower layer imports the console; the Python suite passes with no Node and no built frontend
      - [ ] A path outside the declared roots, an unknown record and a non-loopback bind are refused, and every JSON response carries `"schema": "lgbg.console.v1"`
      - [ ] TypeScript strict and `svelte-check` pass, and the client's API types are checked against a committed contract fixture
    ```md
    - **Cuts through:** `lgbg/console/` (app, static serving, the standalone reader and its `/api/logs` resources, replay), the `console` CLI command, the `web/` shell and API client, `core/replay`, the layering test
    - **Depends on:** nothing
    - **PRD:** FR-1.1, FR-1.2, FR-1.5–FR-1.8, FR-2.2, FR-2.7, FR-2.9, FR-3.1, FR-7.1, FR-7.2, FR-7.3–FR-7.5, FR-7.7, FR-7.8, FR-8.1–FR-8.6, FR-9.1, FR-9.3–FR-9.5, FR-9.7, FR-10.7, FR-11.2, FR-11.4, SC-2, SC-9, SC-12
    - **Why:** The first slice crosses every seam at once — CLI, ASGI, static assets, a typed API contract and a browser — because a defect in any one of them will be found in the last one. Opening a standalone golden record keeps the run layout out of it, so transport is proven before the format is.
    - **Demo:** `uv run lgbg console --root tests/golden/catan` opens `full_game` and shows "verified · 743 actions · catan-rules-6".
    - **Slice note:** This is deliberately thinner than M1. A record that verifies is already useful to a reviewer, and it isolates console plumbing from board geometry.
    ```

### K-002 · The opening board, drawn from a declared scene

  - tags: [slice-1, view, catan, svg, fr-4, sc-1]
  - priority: high
  - workload: Hard
  - steps:
      - [ ] `Game.view()` and the `GameView` protocol exist; Catan supplies `view.py` with `catan-view-1`, a `view_schema()` and a pure `scene(state)`
      - [ ] The scene is integer-only and id-keyed, and its geometry is derived from the board's own topology, not a hand-authored table
      - [ ] Every identifier an observation can reference exists in the scene; a missing one fails a test rather than drawing nothing
      - [ ] The shell dispatches to a renderer by game name, and the Catan renderer draws terrain, tokens, ports and the robber on frame 0
    ```md
    - **Cuts through:** `core/game.py` (the view declaration), `games/catan/view.py`, the console scene endpoint, `web/src/lib/scene.ts`, `web/src/games/catan/`, the scene tests
    - **Depends on:** K-001
    - **PRD:** FR-3.6–FR-3.8, FR-4.2–FR-4.6, FR-5.2, FR-9.2, FR-9.8, FR-10.4, SC-1
    - **Why:** The scene is where the record's identifiers and the browser's geometry meet, and where a GUI starts inventing facts. Drawing one static position proves the coordinate system is the game's own before anything is animated.
    - **Demo:** the same record now shows the full opening board.
    ```

### K-003 · Every state in the record, one step at a time

  - tags: [slice-2, replay, timeline, fr-3, sc-1]
  - priority: high
  - workload: Hard
  - steps:
      - [ ] The timeline has one entry per action record, rejections included with an unchanged state; in spectator mode each entry carries the action, result, events, pre/post hashes and RNG draws
      - [ ] Each frame is the replayed `observe_spectator(state)`, not a scene or a sidecar read
      - [ ] Step forward/back, first/last and jump-to-seq move the board, and pieces, robber and dice are joined to the scene by their recorded identifiers
      - [ ] Replay runs off the event loop, once per game under single-flight, with an LRU of a small number of games; two concurrent opens of one game produce one replay
      - [ ] A response-size and request-time bound is enforced, and an oversized record fails with an explained error rather than hanging
    ```md
    - **Cuts through:** the console read model and cache, `core/replay`, the timeline endpoint, `web/src/lib/timeline.ts`, the step controls and the board's piece/robber/dice join
    - **Depends on:** K-002
    - **PRD:** FR-3.2–FR-3.4, FR-5.3, FR-7.6, FR-9.6, FR-10.1, SC-1
    - **Why:** Playback exercises the replayed state, the observation and the scene identifiers together over 743 frames. Doing it before modes keeps a filtering bug from hiding behind a playback bug.
    - **Demo:** arrow keys walk `full_game` from the empty board to the final position.
    ```

### K-004 · Playback that behaves like a timeline

  - tags: [slice-2, playback, panels, perf, fr-5, sc-11]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] Play/pause and keyboard control, each control carrying a screen-reader label
      - [ ] Phase, round, dice, hands, bank/supply and awards panels all derive from the current frame and never from a second read
      - [ ] Opening the 790-action record takes under two seconds and a frame change is constant-time in the loaded timeline
      - [ ] The performance number is asserted by a test that reports its measurement, not by a manual note
    ```md
    - **Cuts through:** the replay controls, the panel components, the read model's timing, the performance fixture
    - **Depends on:** K-003
    - **PRD:** FR-5.3, FR-5.5, FR-5.13, NFR-2, NFR-6, FR-10.9, SC-11
    - **Why:** A scrubber that re-replays on every tick is the difference between a viewer and a demo. The panels belong here because each is a different read of the same frame, and one panel reading elsewhere is a second source of truth.
    - **Demo:** press play on the 790-action game, let it run, and jump to the last frame without a reload.
    ```

### K-005 · Who is winning, according to the game

  - tags: [slice-2, standings, scoreboard, fr-3, sc-1]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] `Game.standings(state)` is declared and Catan implements it; it adds no field to the player observation and changes no hash or `catan-actions-1`
      - [ ] Spectator frames carry `standings` and the scoreboard renders exactly those numbers
      - [ ] `standings()` agrees with the terminal outcome and with each seat's own `points` where its projection exposes them
      - [ ] `standings()` is pure — no randomness, no mutation — and it does not enter the player projection, whose score remains `points`
    ```md
    - **Cuts through:** `core/game.py`, `games/catan/game.py`, the frame contract, the scoreboard component, the standings test
    - **Depends on:** K-003
    - **PRD:** FR-3.5, §11.4, SC-1, SC-2
    - **Why:** The scoreboard is the most tempting place to compute a rule in the browser. A declared `standings()` keeps the frozen observation schema frozen and the golden corpus drawable, while leaving the client no arithmetic to get wrong.
    - **Demo:** the spectator scoreboard tracks all four seats and matches the terminal verdict.
    ```

### K-006 · Seat mode is a projection, not a filter

  - tags: [slice-3, seat-mode, projection, security, fr-3, sc-3]
  - priority: high
  - workload: Hard
  - defaultExpanded: true
  - steps:
      - [ ] The mode control offers Spectator (labelled as revealing hidden information) and every seat the game declares (labelled with the seat)
      - [ ] In seat mode the server sends only that seat's frame, its own action and its own decision records, and no god-view event
      - [ ] The leak matrix runs over API payloads, not only projections: no hidden field, no other seat's transcript, no god-view event in any seat-mode response
      - [ ] The seat scoreboard comes from that seat's observation `points`, never filled from the spectator frame
      - [ ] Seat identity is conveyed by more than colour, and the mode switch is keyboard reachable
    ```md
    - **Cuts through:** the mode and filter in the read model, `observe(state, seat)`, the client mode switch, the panels' gap handling, the leak matrix
    - **Depends on:** K-005
    - **PRD:** FR-3.10, FR-5.4, FR-5.5, FR-5.13, FR-10.3, §10.2, SC-3
    - **Why:** Hidden information is the most likely way the console starts lying, and a filter in the browser is not a boundary. This is the slice where the projection rule is enforced where it can actually be enforced.
    - **Demo:** switch to Seat 2 and the other three hands and every god-view event disappear.
    ```

### K-007 · Find the decision that looked wrong

  - tags: [slice-4, decisions, sidecar, fr-5, sc-4]
  - priority: high
  - workload: Hard
  - steps:
      - [ ] The sidecar is read lazily per decision turn, grouped by `request_id`, and a failure record with no `seq` still appears in its group
      - [ ] The inspector shows the exact messages, exact response, tool calls, usage, cost, latency, each rejection and the attempt index against the redo budget
      - [ ] A turn with three attempts shows three records, not the last one
      - [ ] Every model-supplied string is inserted as text, and an automated XSS test asserts it
    ```md
    - **Cuts through:** the sidecar reader, the decision endpoint, the inspector component, the v2 record shapes, a mock run fixture with a retry
    - **Depends on:** KANBAN-v2 K-038, K-006
    - **PRD:** FR-3.9, FR-5.6, FR-5.11, SC-4
    - **Why:** This is the release's strongest reason to exist: a person can see what a model was shown and what it answered. It also joins the god log and the sidecar by a key neither owns, which is the join most likely to drift.
    - **Demo:** open a decision with a retry and read both attempts, the refusal between them and the exact prompt.
    ```

### K-008 · The record, the notation and the permalink

  - tags: [slice-4, record, notation, permalink, fr-5, sc-14]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] The record panel shows the selected action, its events, RNG draws and hash chain in spectator mode, and only the seat's own action in seat mode
      - [ ] The notation panel is the game's own `render(observe(...))` for the current mode; no second textual renderer exists
      - [ ] A permalink encodes `(run, game, seq, mode, seat)` and restores the same view after a reload
      - [ ] Empty states are explicit: no sidecar, no notation, no decision and no record for this seq
    ```md
    - **Cuts through:** the record and notation endpoints, the notation panel, the URL parser, the client's view state
    - **Depends on:** K-007
    - **PRD:** FR-3.11, FR-5.7, FR-5.8, FR-5.9, FR-5.12, SC-14
    - **Why:** The notation panel is the proof that the console did not write a second renderer, and the permalink is what makes a claim about a game citable. Both are cheap once the inspector exists.
    - **Demo:** copy the link at seq 412 in Seat 2, reload, and land on the same frame with the same notation.
    ```

### K-009 · Browse an experiment without replaying it

  - tags: [slice-5, runs, discovery, fr-2, sc-5]
  - priority: high
  - workload: Hard
  - steps:
      - [ ] The console reads exactly one layout — root `run.json`, `<game_id>/game.json`, `<game_id>/games/<game_id>.god.jsonl` — and never recursively globs for records
      - [ ] Experiments list their games with completed/abandoned/incomplete derived from terminal and abandonment records, never invented
      - [ ] Discovery reads manifests and record headers only, and replay happens when a game is opened
      - [ ] `results.json` is authoritative when present, and its absence means "did not finish" rather than an error
      - [ ] The pre-v3 layout is refused with a sentence naming the expected `game.json`
    ```md
    - **Cuts through:** the discovery reader, the manifest schemas, the run browser, the runs API, the v2 layout and its readers
    - **Depends on:** KANBAN-v2 K-038, K-004
    - **PRD:** FR-2.1–FR-2.3, FR-2.5, FR-2.8, FR-5.1, SC-5
    - **Why:** Discovery is where the console and the runner agree on a format. Listing without replaying is also what keeps a twenty-game experiment cheap to open.
    - **Demo:** point the console at `runs/`, open an experiment and see its games and statuses without a board being replayed.
    ```

### K-010 · When the record cannot be drawn

  - tags: [slice-5, compatibility, status, fr-2, fr-3, sc-2, sc-5]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] A changed `game`, `rules_version` or `schema_version` is refused for drawing with a stated reason; a changed `engine_version` is a note when the replay verifies
      - [ ] A tampered record fails at a localised sequence and failure kind, and no board is drawn for it
      - [ ] An abandoned game shows its abandonment record and last reconstructed state; an incomplete game is listed but not drawn and is given no terminal state
      - [ ] The status banner states verified / failed at seq N / abandoned / incomplete / incompatible, with the record's versions
      - [ ] A truncated log is reported as incomplete at the truncation point
    ```md
    - **Cuts through:** the compatibility check, the verification report, the status banner, the replay failure path, the tamper and truncation fixtures
    - **Depends on:** K-009
    - **PRD:** FR-2.4, FR-2.6, FR-2.7, FR-3.12, FR-3.13, FR-5.10, FR-5.12, FR-10.5, SC-2, SC-5
    - **Why:** The console must never show the last state that happened to work. Each of these paths is a way a viewer could present a plausible board for a record that is not trustworthy.
    - **Demo:** open a tampered copy and see "failed at seq 219 · hash mismatch" with no board, and an interrupted game listed as incomplete.
    ```

### K-011 · Declare a table in a form, not by hand

  - tags: [slice-6, setup, schema, validation, fr-6, sc-6]
  - priority: high
  - workload: Hard
  - steps:
      - [ ] One `lgbg.runfile.v1` schema and parser live below the CLI, are pure, and are used by both the console and `run`
      - [ ] The form is generated from the schema's sections and offers providers from one catalogue with models as catalogue entries or operator-entered strings
      - [ ] The seat rules are enforced with the CLI's own messages: one agent per seat, one provider, every scored seat an LLM
      - [ ] Save, load and a raw-JSON tab round-trip without losing a field, a raw edit is validated by the same parser, and `--config` preloads the form
      - [ ] The console and the CLI accept and reject the same declarations with the same message
    ```md
    - **Cuts through:** a pure run-file module below the CLI (split from the CLI's agent construction), the CLI adapter, the config endpoints, the form and raw tab, the round-trip test
    - **Depends on:** KANBAN-v2 K-038, K-001
    - **PRD:** FR-6.1, FR-6.1a, FR-6.3, FR-6.4, FR-6.8, FR-6.9, FR-8.1, FR-10.6, SC-6
    - **Why:** A form written against the PRD's example is a second configuration implementation and will drift. One parser with two callers is the only cut that keeps them identical, and validating the same file twice is what proves it.
    - **Demo:** build a four-seat table, save it, reload it, and hand the same file to `lgbg run`.
    ```

### K-012 · What the design actually derives

  - tags: [slice-6, design, config-schema, fr-6, sc-7]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] `Game.config_schema()` is declared on the protocol and implemented by every registered game; Catan's `board` and `number_placement` are rendered, and `players` is derived from the seats table
      - [ ] The three design axes are exposed and the game count is derived as `replicates × seatings`, with the derivation shown
      - [ ] Every uncontrolled axis is marked, and a configuration axis the plugin does not have is disabled with an explanation
      - [ ] A declaration asking a fixed-start game for a random configuration is refused, not silently ignored
      - [ ] `GET /api/games` reports each registered game's configuration schema and whether it has a view
    ```md
    - **Cuts through:** `core/game.py` (`config_schema`), `games/catan/game.py`, the registered-games endpoint, the design section, the derivation display, the matrix's rules
    - **Depends on:** K-011
    - **PRD:** FR-6.2, FR-6.5, SC-7
    - **Why:** The design is where a run's claims are made before money is spent. Showing the derivation and the axes it does not control is the only moment an operator can notice the experiment does not measure what they think.
    - **Demo:** choose rotated seating × 5 replicates, see "20 games", and see the seating caveat.
    ```

### K-013 · What it will cost and what it will send

  - tags: [slice-6, preflight, costs, prompts, fr-6, sc-7]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] Preflight shows errors and warnings, the derivation, uncontrolled axes, the four prompt hashes, the price source and read time, and an estimate or an explicit "unavailable"
      - [ ] The provider key is reported as a boolean, never a value, and no response carries a secret or an environment value
      - [ ] Policies and the budget cap come from the runner's declared defaults and accepted values
      - [ ] A loaded declaration whose prompt hashes differ from the files on disk is warned about, and no prompt can be edited
    ```md
    - **Cuts through:** the preflight endpoint, the prompt hashes, the price table, the estimator, the policy section, the key check
    - **Depends on:** K-012
    - **PRD:** FR-6.6, FR-6.7, FR-6.13, FR-6.14, FR-1.8, NFR-7, SC-7
    - **Why:** Preflight is the console's honest answer to "what will this do?". It is also the first place a secret could leak into a response and the first place a stale price table could quietly become a budget.
    - **Demo:** a preflight panel naming the four hashes, the price read time, the estimate and whether the key is present.
    ```

### K-014 · Launch a run, and keep the console out of it

  - tags: [slice-7, launch, process, fr-1, fr-6, sc-8]
  - priority: high
  - workload: Hard
  - defaultExpanded: true
  - steps:
      - [ ] Launch validates again, writes a temporary declaration and spawns `lgbg run` with a run id and output directory; the runner is not imported
      - [ ] The console returns the run directory and a launch identifier, not a serialised process object
      - [ ] Killing the console does not stop the run, and the run directory is a normal one `inspect-run` reads
      - [ ] A run id collision is refused and nothing is overwritten
      - [ ] No endpoint exposes a live session, projection, action or board, and no response carries a credential
    ```md
    - **Cuts through:** the launch endpoint, the subprocess and its handle, the run id allocator, the temporary declaration, the absence tests
    - **Depends on:** K-013
    - **PRD:** FR-1.3, FR-1.4, FR-6.10, FR-6.15, FR-10.8, SC-8
    - **Why:** Launching is the one write path, and it must write nothing a run owns. Putting the runner in a subprocess turns "kill the console and the run survives" into a fact instead of a hope.
    - **Demo:** press Launch, kill the console, and the run keeps playing and `inspect-run` reads it afterwards.
    ```

### K-015 · Progress without a live board

  - tags: [slice-7, progress, cancel, fr-6]
  - priority: medium
  - workload: Normal
  - steps:
      - [ ] Progress is derived by polling the run directory — plan, game directories, terminal records, `results.json` — and shows counts and status only
      - [ ] Cancelling signals only a run this process launched, leaves the record untouched and reports the run incomplete/cancelled
      - [ ] A cancelled or interrupted run is never reported as completed
      - [ ] No websocket, no server-sent events, and no board or projection appears while a game is in progress
    ```md
    - **Cuts through:** the progress poller, the cancel endpoint, the run browser's status, the process handle
    - **Depends on:** K-014
    - **PRD:** FR-6.11, FR-6.12, FR-1.4, Q8, Q9
    - **Why:** An operator needs to know a run is alive without being able to watch it play. Reading the files the runner already writes keeps the console on the record's side of the boundary.
    - **Demo:** watch "7 of 20 games" rise, cancel, and find the run listed as incomplete.
    ```

### K-016 · The shell does not know Catan

  - tags: [slice-8, genericity, views, fr-4, sc-10]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] A test-only second `GameView` is rendered by the same shell, reader and API with no change to shell code
      - [ ] A scan finds no game-specific name or rule in `lgbg/console/**` or in the shell's generic modules
      - [ ] A game without a view is listed and readable as text through `Game.render`
      - [ ] Adding the second view touches only its own package and the renderer registry, and the console refuses a view version it does not implement
    ```md
    - **Cuts through:** the view registry, the shell, the console package, the test-only game, the layering scan
    - **Depends on:** K-015
    - **PRD:** FR-4.1, FR-4.7, FR-4.8, FR-4.9, FR-10.2, SC-10
    - **Why:** This is the only honest test that the console is game-agnostic. Doing it after the features exist catches every place the shell quietly assumed hexes.
    - **Demo:** the same console draws the test game, and the diff touches no shell module.
    ```

### K-017 · Documentation for view authors and operators

  - tags: [slice-8, docs]
  - priority: low
  - workload: Easy
  - steps:
      - [ ] How to add a game view: the declarations, the scene rules, the renderer registry and the tests that must pass
      - [ ] How to read a run in the console: experiments, games, modes, decisions and permalinks
      - [ ] What the setup form declares, what it refuses, and what the console never writes
      - [ ] The README's release status, run layout and documentation map name the console, `web/` and the acceptance record
    ```md
    - **Cuts through:** the README, a docs page, the CLI's error message, the example view
    - **Depends on:** K-016
    - **PRD:** D9, FR-8.4
    - **Why:** A second view author is the user who discovers whether the seam is real, and the operator is the user who discovers whether the refusals are documented. Both are cheaper now than after the release.
    - **Demo:** a new reader follows the page and gets a scene drawn without reading `lgbg/console`.
    ```

### K-018 · Acceptance and the traceability record

  - tags: [slice-8, acceptance, traceability, sc-12, sc-13]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] Every functional requirement in PRD-v3 §8 is traced to at least one named test, with FR-12 traced through KANBAN-v2 K-038
      - [ ] SC-1 to SC-14 are each demonstrated by a named command whose output is captured
      - [ ] The gate runs ruff, ruff format, mypy, the Python suite, `svelte-check`, Vitest and the frontend build, and the Python suite alone still needs no Node
      - [ ] The old commands still work unchanged, and anything not met is recorded as not met with its reason
    ```md
    - **Cuts through:** the whole release, the gate, `ACCEPTANCE-v3.md`
    - **Depends on:** K-017
    - **PRD:** SC-12, SC-13, D10, FR-8.5, FR-10.10, FR-11.1–FR-11.5
    - **Why:** The release claims the console cannot change a result. The acceptance record is where that claim is checked against commands rather than argued.
    - **Demo:** `ACCEPTANCE-v3.md` with a command and its output for every criterion.
    ```

## Done
