# PRD-v3 — The Operator Console and the Replay Viewer

| Field | Value |
|---|---|
| **Document** | PRD-v3 |
| **Release** | v3 |
| **Status** | Draft — decisions settled, awaiting approval |
| **Depends on** | `ARCHITECTURE.md` (architecture), `prd/PRD-v1.md` (engine), `prd/PRD-v2.md` (records, runner, agents), `ACCEPTANCE-v1.md` (what v1 actually is), `ACCEPTANCE-v2.md` (pending) |
| **Game plugin** | `catan`, base game, 4 players — rules unchanged: `rules_version = catan-rules-6`, `schema_version = catan-actions-1`. The release adds a configuration schema, a replay view and a standings declaration; none changes a rule, an action, a player observation or a recorded hash. |
| **Supersedes** | The roadmap references in PRD-v2 that assign the web UI and statistics to v3; see §1.1. |
| **Deliverable type** | Local web application (ASGI server + static browser client), a read-only Python read model, and one CLI command. No engine semantics change. |

---

## 1. Summary

v1 built a game record that cannot lie. v2 built the model play that fills it. **v3 builds the human
interface to it.**

One local application, two halves:

- **The setup console.** Declare an experiment — game, seats, models, design, policies, budget — and
  see what it will do before it runs: how many games the design derives, which axes it does not
  control, which prompt hashes will be used, what the cost estimate is. Then launch it. The console
  validates the declaration, writes it, and invokes the existing `lgbg run` entry point; it does not
  execute the experiment itself.
- **The replay viewer.** Open an experiment, a game directory, or a single `.god.jsonl`; verify and
  replay it; draw the board; scrub through every state; switch between the spectator's god view and
  a seat's faithful view; inspect the exact request a model was shown and the exact response it gave.

It deliberately does **not** produce statistics. v3 answers *"what happened in this game, and what
did this model actually see?"* v4 answers *"what does that mean across games?"*

It deliberately does **not** put a live board on screen while a run is in progress. Execution is
headless; presentation is post hoc. That separation is what keeps the console out of the measurement
path.

### 1.1 Roadmap note

PRD-v2 assigned both statistics and a web UI to v3. This release splits them: **v3 is the operator
console; v4 is inference.** Forward references in PRD-v2 that assign the web UI to v3 are fulfilled
here. References that assign statistics to v3 are read as v4. PRD-v2's run-directory section is
amended by §11 of this document; its forward-looking statistics language is superseded where it
conflicts.

### 1.2 What this release is not

A dashboard. A leaderboard. A live play surface. An authoring tool for games or prompts. A record
editor. A hosted service. It is a **local instrument for looking at records and declaring runs**.

---

## 2. Background

### 2.1 What v1 and v2 handed us

| Asset | State |
|---|---|
| Engine | Catan base 4-player; 900+ tests; deterministic, hash-chained records |
| Replay | `replay()`, `verify()`, projection replay, localised failures, golden corpus |
| Projections | Player and spectator views, allow-listed, leak-tested |
| Rendering | `Game.render(observation, detail=...)`, one renderer shared by CLI and prompts |
| v2 records | Run directories, `results.json`, per-decision sidecar with exact messages and responses |
| v2 surface | Session facade, HTTP host, MCP, runner, mock and OpenRouter providers |
| v2 inspection | `inspect-run`: a text view of a run, one game, one seat's decision turns |
| Contracts | Frozen per-game manifest, decision record, results schema; zero runtime dependencies in `core` and `games` |

The engine and the records are ready. What is missing is a way to **see** them and a way to
**declare** a run without editing JSON by hand.

### 2.2 The gap this release closes

A Catan game is 400–800 action attempts. A run is many games. A decision is a prompt, a response, a
tool call, a rejection, a redo, a cost and a latency. `inspect-run` can print all of it; it cannot let
a person find the one decision that looked wrong, watch the board around it, and understand what the
model saw.

Separately, the operator's interface to the runner is a JSON file with a large key space. Its
validation lives in a CLI adapter. A GUI that hand-writes a form against the PRD's example would be a
second configuration implementation, guaranteed to drift from the runner.

### 2.3 The risks this release must manage

| Risk | Why it matters |
|---|---|
| **The GUI becomes a second source of truth** | A board recomputed in the browser, a score re-derived in a component, or a state read from the sidecar can all disagree with the record while looking authoritative. |
| **Hidden information leaks through the presentation layer** | A "seat view" assembled from the god view and filtered in the browser is not a projection. Catan's hands, development deck and discard choices are exactly what the benchmark hides. |
| **The console becomes part of what is measured** | A live board invites live hints, live intervention and a second assist surface. A GUI that can act on a live session is an experimental confound. |
| **Artefact churn under a new consumer** | PRD-v2 promises a root `run.json` and a flat `games/` directory; the tree produces neither. A console built against the documents would harden a layout the runner does not write. |
| **Scope creep** | Once there is a browser, there is pressure to add statistics, live play, prompt editing and a hosted service. Those are different releases. |

### 2.4 The invariant underneath every requirement

> **The record is the evidence. The console is a derived view of it.**

A view may be pretty, interactive and convenient. It may never produce a record, alter one, repair
one, or stand in for one in an argument. If the console and the record disagree, the record is right,
and the console is a bug.

---

## 3. Goals

| # | Goal |
|---|---|
| G1 | A person can open any recorded Catan game, see the board, and move through every state it contains. |
| G2 | A person can see what a model was actually shown and what it actually answered, for every decision in a game. |
| G3 | A person can declare a valid experiment without hand-editing JSON, and is told what the declaration derives and what it does not control before it runs. |
| G4 | The console never executes a game, never holds a live session, and never writes a record. |
| G5 | A seat view is faithful to that seat's projection; the god view is explicitly a different mode. |
| G6 | The console is game-agnostic: adding a game adds a view declaration and a renderer, not a shell. |
| G7 | The console is local, read-only over declared roots, and runs with no new runtime dependency in `core` or `games`. |
| G8 | The engine, the records, the CLI commands and the test suite keep working with the console absent. |

---

## 4. Non-goals

| Out of scope | Note |
|---|---|
| **Statistics**: Elo, Bradley-Terry, confidence intervals, sample-size planning, leaderboards | PRD-v4. The console may display counts that v2 already computed; it computes no inference. |
| **A live game GUI during execution** | Permanently a non-goal, not a v3 deferral. A run is headless. The console may show progress counts. |
| **Live play, human-vs-model, or model-vs-model through the console** | `play-live` over the MCP sandbox remains the human surface. The console does not own a session. |
| **Editing records, annotating decisions, editing prompts or game rules** | The console is read-only over artefacts. Prompt editing would defeat the hash checks. |
| **A hosted or multi-user service, authentication, remote access** | v3 binds to loopback. A shared deployment is a different product and a different security model. |
| **Static export of a replay bundle** | Deferred (ARCHITECTURE.md §17). The API is kept data-driven so it remains possible. |
| **A second game plugin** | v3 proves the view seam with a test-only second view, not a second game. A real second game is a later release. |
| **A generic scene-graph language** | Each game declares its own scene schema and supplies its own renderer. No universal drawing language. |
| **3D, animation engines, WebGL** | SVG is sufficient and testable. |
| **A second implementation of run-config validation in the browser** | The server validates with the same parser the CLI uses. |
| **Changing `run`, `inspect-run`, `replay`, `verify`, `fuzz` semantics** | They remain the execution and inspection path. The console calls them; it does not replace them. |

---

## 5. Success criteria

Each is binary and maps to at least one named test in §12.

| # | Criterion |
|---|---|
| SC-1 | A person can open a Catan record from the golden corpus, see the opening board, and reach every state by sequence number; the scene's identifiers are the identifiers in the record. |
| SC-2 | Opening a record verifies its hash chain and shows the verification result. A tampered record fails at a localised sequence number; a record whose `rules_version` or `schema_version` does not match is refused with a stated reason. |
| SC-3 | Spectator and seat views are distinct. Seat mode is built from that seat's projection only; an automated leak matrix finds no hidden field, no other seat's transcript, and no god-view event in any seat-mode payload. |
| SC-4 | The decision inspector reconstructs the exact messages, response, tool calls, usage, cost, latency, rejection and failure for a decision turn, including attempts that have no action sequence number. |
| SC-5 | The run browser lists experiments and their games, and distinguishes completed, abandoned and incomplete games without inventing a terminal state. |
| SC-6 | A declaration built in the console is accepted unchanged by `lgbg run`; loading it back produces the same form; the console and the CLI accept and reject the same declarations with the same messages. |
| SC-7 | Preflight reports the derived game count, every uncontrolled axis, the prompt hashes, the price-table provenance, and a cost estimate or an explicit statement that one is unavailable. |
| SC-8 | Launching spawns the existing runner in a separate process. Killing the console does not stop the run. No endpoint exposes a live session or a live board. |
| SC-9 | The console binds to loopback, reads only under declared roots, refuses traversal and symlink escape, and renders model and prompt text as text (an automated XSS test). |
| SC-10 | A test-only second game view is displayed by the same shell, reader and API with no change to shell code; a scan finds no game-specific name in the generic console modules. |
| SC-11 | A 790-action game opens in under two seconds on the development machine, and moving to another frame after loading does not re-replay the game. |
| SC-12 | The Python suite passes offline with no frontend build, `core` and `games` still have zero third-party runtime dependencies, mypy strict and the TypeScript checks are green. |
| SC-13 | Every functional requirement in §8 is traced to at least one named test. |
| SC-14 | A permalink identifies an exact `(run, game, seq, mode)` and restores it after a reload. |

---

## 6. Users and consumers

| Consumer | Uses |
|---|---|
| **The researcher** | Declares a run, watches it cost what it was expected to cost, opens a game and finds the decision that looked wrong. |
| **The result reviewer** | Opens a published run directory, verifies its records without re-running a model, and cites a permalink to a specific decision. |
| **The operator** | Launches and monitors a run; sees the design's caveats before spending money. |
| **A future game-view author** | Adds a `view.py` and a renderer and confirms the shell does not know the game. |
| **The PRD-v4 implementer** | Consumes the same run directory and `results.json`; the console has not changed them. |

---

## 7. Deliverables

| ID | Deliverable |
|---|---|
| D1 | `lgbg/console/` — the ASGI application, the one run-directory reader, the replay read model, the operator declaration service, and static-asset serving. |
| D2 | `web/` — the Svelte 5 + Vite + TypeScript browser client: shell, run browser, configuration editor, replay controls, panels, Catan renderer. |
| D3 | `lgbg/games/catan/view.py` — the Catan static scene; `config_schema()` and `standings()` on the game. |
| D4 | `lgbg console` — the CLI command. |
| D5 | Plugin declarations: `Game.config_schema()`, `Game.standings()`, `Game.view()` and the `GameView` protocol (ARCHITECTURE.md §7.1, §7.12). |
| D6 | The shared run-declaration schema and parser, moved out of the CLI adapter so the console and the CLI use one validator. The provider catalogue moves down with it. |
| D7 | The v2 artefact prerequisites: root experiment manifest, nested per-game layout, per-game `game.json`, atomic writes, updated readers (§11). |
| D8 | Tests and fixtures: golden-corpus replay, seat-mode leak matrix, scene contract, compatibility, one-validator round-trip, path safety, second view, performance. |
| D9 | Documentation: how to add a game view, how to read a run in the console, what the setup form declares and what it refuses. |
| D10 | `ACCEPTANCE-v3.md` — every success criterion demonstrated by a named command, with its output; deviations recorded as deviations. |

---

## 8. Functional requirements

### 8.1 Boundaries and process

- **FR-1.1** The console MUST be a separate ASGI application from `lgbg.host`. It MUST NOT import the
  host, own a `SessionFacade`, or create a live session.
- **FR-1.2** The console MUST be read-only over records. It MUST NOT write, amend, truncate, rename or
  delete anything under a declared root.
- **FR-1.3** The console MUST NOT execute an experiment in its own process. It MUST write the declared
  configuration to a temporary file and launch the existing `run` entry point in a subprocess.
- **FR-1.4** The console MUST NOT expose a live-game endpoint: no projection, decision surface,
  action submission, or live board for a game still in progress.
- **FR-1.5** No package below the console (`core`, `host`, `games`, `agents`, `runner`) may import
  `lgbg.console`. The CLI adapter may import it only to start the `console` command, and tests may
  import it. A layering test MUST assert the lower layers.
- **FR-1.6** The engine, the CLI, the runner and their tests MUST work with the console absent and
  without a frontend build.
- **FR-1.7** The console MUST bind to loopback by default and MUST refuse a non-loopback address in
  v3. The address and port MUST be printed when the server starts.
- **FR-1.8** No response MAY contain a credential, an API key, a bearer token or an environment
  value. Provider keys are read by the spawned runner, not by the console.

### 8.2 Run directories and discovery

- **FR-2.1** The console MUST read exactly one canonical layout (§11.1). It MUST NOT recursively glob
  for `*.god.jsonl`, because a glob hides a layout drift instead of reporting it.
- **FR-2.2** The console MUST distinguish and open three units: an **experiment directory** (root
  `run.json`), a **game directory** (per-game `game.json` and its records), and a **standalone
  record** (a `.god.jsonl` file under a declared root).
- **FR-2.3** Discovery MUST list without replaying. Replay MUST happen only when a unit is opened.
- **FR-2.4** A game with a terminal record MUST be reported as **completed**. A game with an
  abandonment record and no terminal record MUST be reported as **abandoned**. A game with neither,
  including a game still being written, MUST be reported as **incomplete**; no terminal state may be
  synthesised for it. An incomplete game MUST be listed but MUST NOT be replayed or drawn: the board
  is available only for a completed or abandoned game.
- **FR-2.5** `results.json` is authoritative for a finished run's aggregates. Its absence MUST mean
  "the run did not finish", not an error; the console lists what it can find and says so.
- **FR-2.6** A run's manifest, a game's manifest and the terminal record MUST be read without
  mutating them. A truncated log MUST be reported as incomplete at the truncation point.
- **FR-2.7** Before drawing, the console MUST check the record's `game`, `rules_version` and
  `schema_version` against the installed plugin and the log reader's supported schema major.
  - A different game or `rules_version` MUST be refused for drawing.
  - A different `schema_version` MUST be refused for drawing.
  - A different `engine_version` is informational when the replay verifies; the console MUST show it
    as a note.
  - A successful `replay()` is the proof of reconstruction; a failed one MUST name the sequence and
    the failure kind and MUST NOT be drawn. The console reports the failure and the last sequence it
    verified, rather than a plausible board.
- **FR-2.8** A record from the pre-v3 layout (a per-game `run.json`, no root manifest) MUST NOT be
  supported. v2 has not yet been accepted, so its artefacts are regenerated under §11. The golden
  corpus is a set of standalone records and MUST remain viewable.
- **FR-2.9** The console MUST persist no derived state: no cached frames, no rendered scenes, no
  thumbnails. Its in-memory cache is an optimisation with no artefact.

### 8.3 The replay read model

- **FR-3.1** Opening a game MUST run `core.replay.replay()` and verify every recorded hash. The result
  MUST be reported as a structured verification report, not inferred from the absence of an error.
- **FR-3.2** The read model MUST keep the replayed states for the open game in a bounded cache
  (LRU of a small number of games), MUST serve one replay per game under concurrent requests
  (single-flight), and MUST run replay off the event loop so one open does not block other requests.
- **FR-3.3** A **frame** MUST be the game's observation plus the declared scoreboard, not a new
  scene contract:
  - spectator mode uses `observe_spectator(state)`;
  - seat mode uses `observe(state, seat)`.
  The read model MUST NOT add facts to a frame that the game does not declare through observation or
  `standings()`.
- **FR-3.4** The timeline MUST be aligned one-to-one with the action records, including rejected
  attempts, whose state is unchanged. Each step MUST carry its sequence, action, result, events,
  pre/post hashes and RNG draws in spectator mode; seat mode is filtered per FR-3.10.
- **FR-3.5** The spectator view MUST include a scoreboard. It MUST come from `Game.standings(state)`,
  not from a renderer or a client-side calculation. The seat scoreboard MUST come from the seat's own
  observation `points`. `standings()` MUST be tested against the terminal outcome and against each
  seat's own `points` where the projection exposes it.
- **FR-3.6** The static scene MUST come from `Game.view().scene(initial_state)`, MUST be validated
  against `view_schema()`, and MUST use the canonical identifiers of the game.
- **FR-3.7** The scene MUST contain integers only. A float in a scene is a defect and MUST fail a
  test. Coordinates are in a fixed view box; the client scales them.
- **FR-3.8** Every identifier that an observation can reference (pieces, robber, ports, dice or any
  game-specific reference) MUST be present in the scene. A missing identifier MUST be a test failure,
  not a silent empty drawing.
- **FR-3.9** The sidecar MUST be read lazily, per decision turn, and MUST be grouped by
  `request_id` so several attempts of one decision stay together. A failure record with no `seq`
  MUST still appear in its decision group.
- **FR-3.10** Seat mode is a projection boundary enforced by the server:
  - The timeline MUST contain only the seat's frame and its own action/decision; another seat's
    action parameters and events MUST NOT be sent.
  - The decision endpoint MUST return only that seat's records.
  - The raw god-log record view, other seats' transcripts, and god-view events MUST NOT be
    available in seat mode. The UI MUST offer spectator mode for them, clearly labelled.
  - A test MUST assert the absence, not the intention.
- **FR-3.11** The notation endpoint MUST use `Game.render(observation, detail=...)`, the one renderer
  the CLI and the prompts use. The console MUST NOT implement a second textual renderer.
- **FR-3.12** The read model MUST expose phase transitions and the terminal record. An abandoned game
  MUST show its abandonment record and the last reconstructed state, with no terminal record.
- **FR-3.13** A replay failure MUST be localised to a sequence and a failure kind (the existing
  `ReplayError`), and MUST be returned as a finding about the record rather than a generic server
  error.

### 8.4 The game view declaration

- **FR-4.1** `Game.view()` MUST be optional. A game without a view MUST still be listed, opened and
  rendered as text through `Game.render`; absence of a renderer is not an error.
- **FR-4.2** A view MUST declare `schema_version`, `view_schema()` and `scene(state)`. The scene MUST
  be a pure function of the state's board structure.
- **FR-4.3** The scene MUST be derived from the game's coordinate system, never from a hand-authored
  table. The structural self-check of the board MUST continue to be the test that the geometry is
  sound.
- **FR-4.4** The scene MUST contain only public structure. No hidden hand, deck order, discard choice
  or unrevealed card may appear in a scene.
- **FR-4.5** The Catan view MUST expose, keyed by the existing identifiers: hex centres, hex-to-vertex
  and hex-to-edge incidence, vertex points, edge endpoints, and the port edge positions. Terrain,
  token, robber, pieces and port faces remain in the observation and are joined by identifier.
- **FR-4.6** The browser MUST have one renderer per game, registered by the game's name. The shell,
  the timeline, the panels and the API MUST be game-agnostic.
- **FR-4.7** A test-only second game view MUST be renderable by the same shell. Adding it MUST NOT
  require a shell change.
- **FR-4.8** A layering test MUST find no game-specific name or rule in `lgbg/console/**` or in the
  shell's generic modules. Game names may appear only in the renderer registry and in the game's own
  package.
- **FR-4.9** The console MUST refuse a view whose `schema_version` it does not implement, with a
  stated reason.

`config_schema()`, `standings()` and `view()` are additive declarations. They MUST NOT change
`action_schema()`, the player `observation_schema()` or a recorded hash, so Catan's
`schema_version` stays `catan-actions-1` and the existing records remain drawable. The view's own
`schema_version` versions the presentation contract separately.

### 8.5 The replay user interface

- **FR-5.1** The application MUST offer navigation: experiments → games → replay, and a direct path
  from a record.
- **FR-5.2** The replay MUST draw the board from the scene and the current frame only. It MUST NOT
  compute a rule, a legal move, a score, a hand or a hidden fact on the client.
- **FR-5.3** The replay MUST support: step forward/back, jump to any sequence, play/pause, first/last,
  and keyboard equivalents. Moving to another frame after opening MUST be O(1) in the loaded
  timeline.
- **FR-5.4** The mode control MUST offer **Spectator** (god view) and **Seat N** (that seat's view).
  Spectator MUST be labelled as revealing hidden information; seat mode MUST be labelled with the
  seat.
- **FR-5.5** Panels MUST derive from the current mode's frame: board, per-seat state, scoreboard,
  bank/supply/awards, dice/phase/round, and the decision that produced the frame where the record
  names it. A panel MUST NOT fill a seat-mode gap from the spectator data.
- **FR-5.6** The decision inspector MUST show, for the selected decision: the exact messages, the
  exact response, tool calls, usage, cost, latency, the rejection that prompted each retry, the
  attempt index against the redo budget, and any failure kind. It MUST group by `request_id`.
- **FR-5.7** The record panel MUST show the selected action record, its events, RNG draws and hash
  chain in spectator mode. In seat mode it MUST be limited to the seat's own action and MUST NOT
  expose god-view events.
- **FR-5.8** The notation panel MUST show the exact text the game's renderer produces for the current
  mode: `Game.render(observe(state, seat))` in seat mode and `Game.render(observe_spectator(state))`
  in spectator mode. It MUST NOT implement a second textual renderer.
- **FR-5.9** A permalink MUST encode `(run, game, seq, mode, seat)` and MUST restore the same view
  after a reload. The URL is the UI state; no server-side session is needed.
- **FR-5.10** A status banner MUST state: verified / verification failed at seq N / abandoned /
  incomplete / incompatible, with the record's game, rules version and engine version.
- **FR-5.11** Every prompt, response and model-supplied string MUST be inserted as text, never as
  HTML. An automated XSS test MUST assert it.
- **FR-5.12** Empty, missing and error states MUST be explicit: no run, no games, no sidecar, no
  renderer, no decision for this seq. A blank panel is not an acceptable error state.
- **FR-5.13** Keyboard and screen-reader access MUST be provided for the controls; seat identity MUST
  not rely on colour alone.

### 8.6 The setup console

- **FR-6.1** The setup form MUST be driven by one declared run-file schema (`lgbg.runfile.v1`), served
  by the console, with sections: game, seats, design, policies, advanced. It MUST NOT hard-code field
  lists that duplicate the runner's parser.
- **FR-6.1a** The declaration parser and its catalogues MUST be pure: no network access, no provider
  construction, no price fetch. Building agents remains the CLI's job; the console only reads the
  declaration.
- **FR-6.2** Game-specific options MUST be rendered from `Game.config_schema()`. Catan's `board` and
  `number_placement` are the first instance. `players` is a core configuration field derived from the
  seats table, not a game option; the form MUST keep the two consistent.
- **FR-6.3** The form MUST offer provider choices from one declared catalogue and model identifiers
  as operator-entered strings or catalogue entries. It MUST NOT fetch prices or models silently.
- **FR-6.4** The seats table MUST enforce the v2 rules: exactly one agent per seat, the same provider
  across seats, every scored seat an LLM, and reference/mock seats marked as not scored. A
  declaration that breaks a rule MUST be refused with the same message the CLI gives.
- **FR-6.5** The design section MUST expose the three independent axes — seating, initial
  configuration, replicates — and MUST derive the game count from them. It MUST mark every axis the
  design leaves uncontrolled. It MUST disable a configuration axis the plugin declares it does not
  have, with an explanation.
- **FR-6.6** Policy fields MUST come from the runner's declared defaults and accepted values. When
  v2's budget cap is available, the form MUST expose it; a budget value MUST NOT be invented by the
  console.
- **FR-6.7** Preflight MUST show: validation errors and warnings, the derived game count and its
  derivation, uncontrolled axes, the four prompt hashes, the price source and read time (or "not
  read"), a cost estimate from the runner's estimator or an explicit "unavailable", and whether the
  required provider key is present (as a boolean, never a value).
- **FR-6.8** The form MUST support save/download, load, and a raw-JSON tab. A load MUST round-trip
  without losing a field. A raw edit MUST be validated by the same server validator.
- **FR-6.9** Client-side validation MUST be limited to what the schema says; the authoritative
  validation MUST be the runner's parser. The console MUST NOT silently repair, default or drop a
  field.
- **FR-6.10** Launch MUST post the declaration, validate it again, write it to a temporary file, and
  spawn `lgbg run` as a subprocess with a declared run id and output directory. The console MUST
  return the run directory and a launch identifier (not a serialised process object); it MUST NOT
  import the runner.
- **FR-6.11** Progress MUST be derived from the run directory (the root manifest's plan, game
  directories, terminal records, `results.json` when present). It MUST show counts and status only;
  it MUST NOT show a board or a live projection.
- **FR-6.12** The console MAY cancel a run it launched in this process, by signalling the process. It
  MUST leave the record untouched and MUST report the run as incomplete/cancelled, never as
  completed.
- **FR-6.13** The console MUST NOT edit a prompt. It MUST show the prompt hashes that will be used and
  MUST warn when a loaded run's manifest carries hashes different from the files on disk.
- **FR-6.14** The console MUST NOT record a secret. It MUST show only whether the provider key is
  present.
- **FR-6.15** A run id collision MUST be refused, never overwritten.

### 8.7 The console API

- **FR-7.1** Every API response MUST be JSON and MUST carry `"schema": "lgbg.console.v1"`.
- **FR-7.2** The API MUST offer at least the following. `POST /api/runs` takes the declaration in the
  run-file shape. The timeline, decision, record and notation endpoints take `mode=spectator` or
  `mode=seat&seat=N`; in seat mode their results are filtered per FR-3.10.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/games` | Registered games, their configuration schema, view availability and benchmark profile. |
| `GET` | `/api/config/schema` | The run-file schema and the catalogues the form needs. |
| `POST` | `/api/config/validate` | Validate a declaration; return errors, warnings, derivation, prompts, prices and estimate. |
| `GET` | `/api/runs` | Discovered experiments with status. |
| `GET` | `/api/runs/{run}` | Experiment manifest, design, plan and caveats. |
| `GET` | `/api/runs/{run}/games` | Games with completed/abandoned/incomplete status. |
| `GET` | `/api/runs/{run}/games/{game}` | Game manifest, header, terminal record and verification summary. |
| `GET` | `/api/runs/{run}/games/{game}/scene` | The static scene. |
| `GET` | `/api/runs/{run}/games/{game}/timeline` | Verified frames and per-step metadata for a mode. |
| `GET` | `/api/runs/{run}/games/{game}/record/{seq}` | One god-log record (spectator only). |
| `GET` | `/api/runs/{run}/games/{game}/decision/{seq}` | Decision attempts for the turn containing `seq`. |
| `GET` | `/api/runs/{run}/games/{game}/notation` | The exact textual rendering for a seq and mode. |
| `POST` | `/api/runs` | Validate, write and launch a declaration. |
| `POST` | `/api/runs/{run}/cancel` | Signal a run this process launched. |
| `GET` | `/api/health` | Liveness and version. |

- **FR-7.3** Read endpoints MUST be pure: no mutation, no RNG, no replay of a different game.
- **FR-7.4** A missing path MUST be `404`; a malformed request `400`; an unsupported method `405`; an
  internal failure `500` with a JSON body. A record that does not verify, an incompatible version or
  an abandoned game are **findings about the record** and MUST return `200` with a structured status,
  not a transport error.
- **FR-7.5** The API MUST NOT expose a raw filesystem path outside the declared roots, and MUST NOT
  accept a path parameter it has not resolved and checked.
- **FR-7.6** The API MUST bound response size and request time; a replay of a very large game MUST NOT
  hang the server. It MUST return a clear error if a bound is exceeded.
- **FR-7.7** Static assets MUST be served with the correct content type, immutable caching for hashed
  filenames, and a SPA fallback only for the shell route.
- **FR-7.8** CORS MUST be disabled. The console is same-origin and loopback-only.

### 8.8 The CLI

- **FR-8.1** `lgbg console` MUST start the console, with:
  `--root DIR` (repeatable; default `runs/`), `--run DIR`, `--game ID`, `--config FILE`,
  `--host` (loopback only, default `127.0.0.1`), `--port` (default `8765`), `--no-browser`.
- **FR-8.2** The command MUST print the URL and MUST open a browser unless `--no-browser`.
- **FR-8.3** The command MUST exit non-zero on failure and MUST NOT print a traceback for an expected
  failure, matching v1's CLI contract.
- **FR-8.4** A missing frontend build MUST produce a clear message naming the build command, not a
  blank page.
- **FR-8.5** `new`, `play`, `play-live`, `serve`, `run`, `inspect-run`, `replay`, `inspect`, `verify`
  and `fuzz` MUST keep working unchanged.
- **FR-8.6** `console` MUST NOT start the HTTP host or an MCP profile, and MUST NOT accept a
  `--session` option.

### 8.9 Frontend and build

- **FR-9.1** The browser client MUST be Svelte 5 + Vite + TypeScript, strict, with no SSR.
- **FR-9.2** The board MUST be inline SVG. The project MUST NOT add D3, Canvas/WebGL, a chart library,
  a UI component library, a general router, a state-management library or a JSON-Schema form library.
- **FR-9.3** Node and the frontend packages MUST be build-time only. They MUST NOT be required to run
  the engine, the CLI, the runner or the Python test suite.
- **FR-9.4** The build MUST be reproducible from a committed lockfile. `pnpm build` (or the declared
  package manager) MUST produce `web/dist`, which the console serves.
- **FR-9.5** TypeScript MUST be strict and linted with Biome; `svelte-check` MUST pass. `any` requires
  a written justification in the code.
- **FR-9.6** Pure frontend logic — frame selection, URL parsing, scene-to-pixel layout, mode
  filtering — MUST be unit-tested with Vitest. A browser smoke test is optional and MUST NOT be part
  of the offline Python gate.
- **FR-9.7** The frontend MUST treat the API payloads as typed data. A contract fixture MUST assert
  the shapes the client consumes; a server change that breaks the client MUST fail a test.
- **FR-9.8** The client MUST NOT compute game facts (FR-5.2) and MUST NOT read the god log directly.

### 8.10 Testing and fixtures

- **FR-10.1** The seven-game golden corpus MUST be openable and verifiable through the read model.
- **FR-10.2** A test-only second `GameView` MUST exist and be rendered by the shell.
- **FR-10.3** The Catan leak matrix MUST be extended to the seat-mode API payloads, not only to the
  projections.
- **FR-10.4** Scene tests MUST assert `view_schema()` validity, identifier coverage, integer
  coordinates, and the absence of hidden fields.
- **FR-10.5** Compatibility tests MUST assert refusal for a changed `rules_version` and
  `schema_version`, and a localised failure for a tampered record.
- **FR-10.6** Declaration tests MUST assert console/CLI validation equivalence and form round-trip.
- **FR-10.7** Security tests MUST assert traversal refusal, symlink-escape refusal, non-loopback
  refusal, and text escaping.
- **FR-10.8** Launch tests MUST use the mock provider and assert that the run directory is a normal
  run directory and that the console process is not required for it to finish.
- **FR-10.9** A performance benchmark MUST open the 790-action record and report the time; the
  acceptance record MUST include the measurement.
- **FR-10.10** A traceability matrix over §8 MUST be maintained, as v1 and v2 did.

### 8.11 Dependency policy

- **FR-11.1** `lgbg/core` and `lgbg/games` MUST keep zero third-party runtime dependencies.
- **FR-11.2** The console's Python side MUST use the standard library plus the already-pinned
  `uvicorn`. No web framework, HTTP client library or template engine is added.
- **FR-11.3** The frontend dependencies are build-time only, pinned in the lockfile, and confined to
  `web/`. They MUST NOT carry game or model logic.
- **FR-11.4** The console MUST not be a dependency of `run`, `serve`, `verify`, `replay`, or the
  engine, CLI and runner test suites.
- **FR-11.5** No dependency may carry game logic or model logic.

### 8.12 Artefact prerequisites (delivered under v2)

These are not console features. They are the record changes the console needs, and they MUST land
before the first console milestone. They MUST be cut onto the v2 board as a hardening card before
M1; they are not on it yet.

- **FR-12.1** The canonical layout MUST be:

  ```text
  runs/<run_id>/
    run.json                    experiment manifest (lgbg.experiment.v1), written before play
    results.json                outcome aggregates, written when the run ends
    <game_id>/                  one directory per game: the portable unit
      game.json                 the game's own manifest (lgbg.run.v1)
      games/
        <game_id>.god.jsonl     deterministic record
        <game_id>.meta.jsonl    sidecar
  ```

- **FR-12.2** The root `run.json` MUST be written **before the first game starts**, MUST contain the
  experiment declaration, its derivation and the full plan, and MUST be checked against a declared
  schema (`lgbg.experiment.v1`) before it is written.
- **FR-12.3** The root manifest MUST contain: schema, run id, creation time, engine version,
  game/versions, the template configuration, seats and agents, design axes, derivation, uncontrolled
  axes, the plan (game id, replicate, rotation, seat map, seed, initial configuration), policies,
  prompt hashes, provider identities, and the price table with its read time. It MUST contain no
  secret.
- **FR-12.4** The per-game manifest MUST be renamed from `run.json` to `game.json`, MUST keep its
  current content and `lgbg.run.v1` schema, and MUST remain self-sufficient for replay.
- **FR-12.5** The root manifest and the per-game manifest MUST be written atomically (temporary file
  plus replace), so a crash never leaves a half-written manifest that looks complete.
- **FR-12.6** `results.json` MUST keep its current schema and content.
- **FR-12.7** `inspect-run`, `verify` and the runner's results reader MUST read the new layout and
  MUST keep working on a standalone `.god.jsonl`. v1 records MUST verify exactly as before.
- **FR-12.8** ARCHITECTURE.md §8.2 and PRD-v2 §11.1 MUST be amended to the canonical layout.
- **FR-12.9** No legacy-layout reader is required. v2 is not accepted yet, so its runs are
  regenerated; the golden corpus is standalone and remains supported.
- **FR-12.10** These changes MUST NOT alter a game rule, an action, a player observation, a state
  hash, a god-log byte or a `results.json` field.

---

## 9. Non-functional requirements

| # | Requirement |
|---|---|
| NFR-1 | **Derived-only.** The console writes no record and persists no derived state. Every frame is recomputable from the artefacts. |
| NFR-2 | **Performance.** A 790-action Catan game MUST open in under 2 seconds on the development machine, and a frame change after load MUST be O(1) in the loaded timeline. |
| NFR-3 | **Local safety.** Loopback only; declared roots only; no traversal or symlink escape; model text escaped. |
| NFR-4 | **Offline testability.** The Python suite runs with no network, no keys, no Node and no built frontend. |
| NFR-5 | **Integer presentation payloads.** Scenes and derived timeline metadata contain no floats. |
| NFR-6 | **Accessibility.** Keyboard control for scrubbing and mode changes; seat identity not by colour alone. |
| NFR-7 | **Secret hygiene.** No credential appears in a response, a log or an artefact. |
| NFR-8 | **Portability.** Linux, macOS and Windows; a path is resolved before it is used. |
| NFR-9 | **Typing and lint.** mypy strict for `lgbg/console`; TypeScript strict and `svelte-check` for `web/`; Biome clean. |
| NFR-10 | **Robustness.** No request may hang; a huge or malformed record produces a bounded, explained failure. |
| NFR-11 | **Maintainability.** No UI framework beyond Svelte, no component kit, no client-side game logic; the shell must stay small enough to audit. |
| NFR-12 | **Reproducibility of the view.** The same record and the same console version produce the same scene and timeline; the record, not the screenshot, is the evidence. |

---

## 10. The presentation contract

This section is normative and is the v3 counterpart to PRD-v2 §10.

### 10.1 Three layers, only one of which is exact

| Layer | Guarantee | Mechanism |
|---|---|---|
| **Record** | **Exact.** The game replays to every state, hash-verified. | v1, unchanged. |
| **View** | **Derived.** A frame is the projection of a replayed state; a scene is a declared geometry. | `replay()`, `observe*()`, `standings()`, `view().scene()`. |
| **Presentation** | **Ephemeral.** A layout, a colour, a panel, a URL. | The browser client. |

### 10.2 What this means, stated plainly

- The console **cannot** make a result more true. It can only make it legible.
- A screenshot is not evidence. A permalink is a pointer to a position in a record, not to a
  rendering; a later console version may draw it differently.
- If the console cannot reconstruct a record, it says so. It never repairs, guesses or shows the last
  state that happened to work.
- Seat mode is a projection boundary enforced by the server. The god view is a different mode with a
  different label; it is not a checkbox that quietly upgrades a seat view.
- A run's `run.json` and `results.json` are the operator's record. The console does not edit them.
- The console is not a measurement surface. No action taken in it may enter a scored game.

### 10.3 What the console must never do

- Write, amend or delete a `.god.jsonl`, `.meta.jsonl`, `game.json`, `run.json` or `results.json`.
- Synthesise a terminal record for an abandoned or interrupted game.
- Compute a statistic across games.
- Send the god view to a seat-mode client and filter it in the browser.
- Draw a board whose identifiers do not match the record.
- Start a live session, submit an action to a live game, or show a live board.
- Edit a prompt or a rule.
- Show a model's text as markup.

---

## 11. Artefact contracts

### 11.1 Run directory

```text
runs/<run_id>/
  run.json                    experiment manifest — declaration, derivation and plan
  results.json                per-game and per-seat accounting (v2 schema)
  g-0000/
    game.json                 per-game manifest (v2 `run.json` content, renamed)
    games/
      g-0000.god.jsonl
      g-0000.meta.jsonl
  g-0001/
    ...
```

A **game directory** is the portable unit: copy it anywhere and it replays. An **experiment
directory** adds the declaration, the plan and the aggregates.

### 11.2 Root experiment manifest

Field values are illustrative; the shape is normative. The shape is declared as JSON Schema data and
checked before the file is written.

```jsonc
{
  "schema": "lgbg.experiment.v1",
  "run_id": "catan-two-models-2026-10-29",
  "created_at": "2026-10-29T15:00:00+00:00",
  "engine_version": "0.2.0",
  "game": {
    "name": "catan",
    "rules_version": "catan-rules-6",
    "schema_version": "catan-actions-1"
  },
  "config": {
    "seed": 123456789,
    "players": 4,
    "assist": "L1",
    "rejection_detail": "standard",
    "interaction_protocol": "decline_only",
    "board": "fixed:standard_a"
  },
  "seats": [
    {"seat": 0, "agent": "llm", "player": null, "model": "<model-a>", "provider": "openrouter",
     "sampling": {"temperature_milli": 0, "top_p_milli": 1000, "seed": null}},
    {"seat": 1, "agent": "llm", "player": null, "model": "<model-b>", "provider": "openrouter",
     "sampling": {"temperature_milli": 0, "top_p_milli": 1000, "seed": null}},
    {"seat": 2, "agent": "llm", "player": null, "model": "<model-a>", "provider": "openrouter",
     "sampling": {"temperature_milli": 0, "top_p_milli": 1000, "seed": null}},
    {"seat": 3, "agent": "llm", "player": null, "model": "<model-b>", "provider": "openrouter",
     "sampling": {"temperature_milli": 0, "top_p_milli": 1000, "seed": null}}
  ],
  "design": {
    "seating": "rotated",
    "initial_configuration": "fixed:standard_a",
    "configuration_scope": "per_experiment",
    "replicates": 5
  },
  "derivation": {
    "rule": "games = replicates x seatings",
    "replicates": 5,
    "seatings": 4,
    "games": 20
  },
  "uncontrolled": [],
  "plan": [
    {
      "game_id": "g-0000",
      "replicate": 0,
      "rotation": 0,
      "seat_map": [0, 1, 2, 3],
      "seed": 123456789,
      "initial_configuration": "fixed:standard_a"
    }
    // g-0001 ... g-0019, one entry per planned game
  ],
  "policies": {
    "context": "delta_with_refresh",
    "context_refresh_every": 8,
    "context_window": 12,
    "redo_budget": 3,
    "on_exhausted": "abandon_game",
    "step_budget": 8,
    "decision_timeout_s": 120,
    "game_timeout_s": 7200,
    "budget_micro_usd": null
  },
  "prompts": {"game": "<sha256>", "system": "<sha256>", "policy": "<sha256>", "redo": "<sha256>"},
  "providers": [{"id": "openrouter", "version": "<version>"}],
  "price_table": {
    "source": "<gateway listing>",
    "read_at": "2026-10-29T14:55:00+00:00",
    "unit": "micro_usd_per_million_tokens",
    "models": [
      {"model": "<model-a>", "prompt": 0, "completion": 0},
      {"model": "<model-b>", "prompt": 0, "completion": 0}
    ]
  }
}
```

The plan is the part that must exist before play. Without it, a crashed run has no record of what it
intended to do.

### 11.3 Console API examples

**Validation.**

```jsonc
POST /api/config/validate
{
  "schema": "lgbg.console.v1",
  "ok": false,
  "errors": [{"path": "seats[2].provider", "message": "every seat must name the same provider"}],
  "warnings": ["seating is fixed: positional asymmetry is not controlled"],
  "derivation": {"games": 20, "replicates": 5, "seatings": 4},
  "uncontrolled": ["seating"],
  "prompts": {"game": "<sha256>", "system": "<sha256>", "policy": "<sha256>", "redo": "<sha256>"},
  "price_table": null,
  "estimate": {"known": false, "reason": "no price table; read prices from the gateway first"}
}
```

**Timeline.**

```jsonc
GET /api/runs/<run>/games/g-0000/timeline?mode=spectator
{
  "schema": "lgbg.console.v1",
  "game_id": "g-0000",
  "mode": "spectator",
  "verified": true,
  "completed": true,
  "terminal": {"seq": 743, "winner": 1, "scores": {"0": 7, "1": 10, "2": 6, "3": 8}},
  "frames": [
    {"seq": 0, "frame": {"phase": "setup", "turn": 0, "round": 0, "...": "..."}},
    {"seq": 1, "action": {"type": "place_settlement", "params": {"site": 12}},
     "result": {"ok": true}, "events": [{"type": "...", "payload": {"...": "..."}}],
     "hash": "9f8e...", "frame": {"...": "..."}}
  ]
}
```

**Scene.** Static, integer, keyed by the game's canonical identifiers. The observation supplies
terrain, tokens, pieces and the robber; the scene supplies the geometry those identifiers refer to.

```jsonc
{
  "schema": "lgbg.console.v1",
  "game": "catan",
  "rules_version": "catan-rules-6",
  "view_schema_version": "catan-view-1",
  "scene": {
    "view_box": [0, 0, 2000, 1800],
    "hexes": [{"id": 0, "center": [1000, 900], "vertices": [0, 1, 2, 3, 4, 5],
               "edges": [0, 1, 2, 3, 4, 5]}],
    "vertices": [{"id": 0, "point": [1000, 780]}],
    "edges": [{"id": 0, "points": [[1000, 780], [1120, 850]], "hexes": [0, 1]}]
  }
}
```

### 11.4 Frame contract

A frame is the game's observation plus the declared scoreboard:

```jsonc
{
  "observation": {"phase": "play", "turn": 2, "round": 3, "dice": [4, 5], "board": {...}, "...": "..."},
  "standings": {"0": 5, "1": 7, "2": 4, "3": 3}
}
```

`standings` is present in spectator mode only. In seat mode the scoreboard comes from the seat's own
observation `points`; the console does not fill it from the god view.

---

## 12. Acceptance test plan

| Test | Covers |
|---|---|
| `test_open_golden_game` | SC-1, FR-3.1 — every golden game opens and reaches every seq |
| `test_timeline_matches_replay` | FR-3.3, FR-3.4 — frames are the replayed observations; rejections included |
| `test_scene_contract` | FR-3.6, FR-3.7, FR-3.8, FR-4.2–FR-4.5 — schema, ids, integers, public only |
| `test_scene_hidden_fields` | FR-4.4 — no hidden fact in a scene |
| `test_seat_mode_leaks` | SC-3, FR-3.10 — the leak matrix over API payloads |
| `test_seat_mode_decision_filter` | FR-3.10 — another seat's transcript is absent |
| `test_spectator_mode_complete` | FR-3.4, FR-3.5 — god view has the record and standings |
| `test_version_refusal` | SC-2, FR-2.7, FR-4.9 — rules/schema/view mismatch refused |
| `test_standings` | FR-3.5, §15.5 — `standings()` agrees with the outcome and own points |
| `test_api_envelope` | FR-7.1, FR-7.2 — every API response carries the schema and the documented shape |
| `test_static_assets` | FR-7.7, FR-8.4 — correct types, SPA fallback, clear missing-build error |
| `test_tamper_localised` | FR-2.7, FR-3.13 — a tampered record fails at a seq |
| `test_abandoned_and_incomplete` | FR-2.4, FR-3.12 — no synthetic terminal |
| `test_run_layout` | FR-2.1, FR-12.1 — one layout, read without globbing |
| `test_root_manifest` | FR-12.2, FR-12.3 — written before play, plan present, shape valid |
| `test_manifest_atomic` | FR-12.5 — a crash leaves no plausible half-manifest |
| `test_config_roundtrip` | SC-6, FR-6.8 — form → file → form is lossless |
| `test_validation_equivalence` | FR-6.9 — console and CLI reject the same declarations identically |
| `test_preflight` | SC-7, FR-6.5, FR-6.7 — derivation, caveats, prompts, prices, estimate |
| `test_launch_subprocess` | SC-8, FR-6.10 — a normal run directory; console not in the path |
| `test_no_live_endpoints` | FR-1.4 — absence is asserted |
| `test_path_safety` | SC-9, FR-7.5 — traversal and symlink escape refused |
| `test_xss_escaping` | SC-9, FR-5.11 — model text is not markup |
| `test_second_view` | SC-10, FR-4.7 — the shell renders a second game |
| `test_game_view_optional` | FR-4.1 — a game without a view is listed and readable as text |
| `test_config_schema_purity` | FR-6.1a, FR-6.2, FR-11.2 — schema and catalogues need no network |
| `test_progress_and_cancel` | FR-6.11, FR-6.12 — status from files; a cancelled run is incomplete |
| `test_run_id_collision` | FR-6.15 — an existing run is never overwritten |
| `test_no_secrets` | FR-1.8, FR-6.14, NFR-7 — no key or environment value in a response |
| `test_api_errors` | FR-7.3, FR-7.4 — pure reads; findings are 200, transport failures are not |
| `test_console_cli` | FR-8.1–FR-8.6 — options, exit codes, no host and no session |
| `test_frontend_optional` | FR-8.4, FR-9.3 — a missing build is explained; the Python suite still passes |
| `test_no_game_specific_console` | FR-4.8 — no game name in generic modules |
| `test_permalink` | SC-14, FR-5.9 — run/game/seq/mode restores |
| `test_performance_open` | SC-11, NFR-2 — the 790-action record opens under budget |
| `test_no_core_dependencies` | SC-12, FR-11.1 — the boundary does not erode |
| `test_v1_v2_cli_unchanged` | FR-8.5, FR-12.7 — old commands still work |
| `test_traceability` | SC-13 — every §8 requirement has a named test |

Frontend tests: `web/src/lib/timeline.test.ts`, `web/src/lib/scene.test.ts`,
`web/src/lib/mode.test.ts`, and an optional `web/e2e/replay.spec.ts`. The optional browser test is
not part of the offline Python gate.

---

## 13. Milestones

| # | Milestone | Definition of Done |
|---|---|---|
| **M0** | v2 artefact prerequisites | Root `run.json` written atomically before play, nested layout, `game.json`, readers updated, `inspect-run`/`verify` green. Delivered under v2. FR-12. |
| **M1** | One record, one board | Console ASGI app, the one run reader, replay + verify, scene API, Catan renderer for the opening board, a golden game opens with a verification badge. FR-2, FR-3.1, FR-3.6, FR-4. |
| **M2** | Playback | Full timeline, pieces, robber, dice, hands, bank, awards, scrub/play/pause/keyboard, cached replay. FR-3.2–FR-3.4, FR-5.2–FR-5.3. |
| **M3** | Modes and the leak matrix | Spectator/seat switch, server-side filtering, scoreboards, hidden-information tests. FR-3.5, FR-3.10, FR-5.4–FR-5.5, SC-3. |
| **M4** | Decisions and evidence | Decision inspector, record panel, notation panel, permalinks, status banner. FR-3.9, FR-3.11, FR-5.6–FR-5.10, SC-4, SC-14. |
| **M5** | Run browser | Experiments → games, completed/abandoned/incomplete, missing results, version notes. FR-2.4–FR-2.6, FR-5.1, SC-5. |
| **M6** | Setup without launch | One run-file schema, form, game options, seats, design, policies, preflight, save/load/raw, one validator. FR-6.1–FR-6.9, SC-6, SC-7. |
| **M7** | Launch and progress | Subprocess launch, run id, progress from files, cancel, loopback/roots/security. FR-1, FR-6.10–FR-6.15, FR-7, FR-8, SC-8, SC-9. |
| **M8** | Second view, performance, acceptance | Test-only second view, no-game-specific scan, performance measurement, docs, traceability, acceptance record. SC-10–SC-13. |

**M0 before M1 is deliberate.** The console's discovery layer is a consumer of the directory format;
freezing a consumer against a format the runner does not write is how two layouts become permanent.

**Viewer before creator is deliberate.** The record is the contract, and the viewer is the test of
it. The setup form is ordinary work over a contract that already exists; the replay is where the
risky interfaces (replay, projection, geometry, sidecar join) meet.

---

## 14. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | The browser becomes a second rules engine | Medium | High | P12; frames are observations; `standings` from the game; scene id coverage; no client-side facts. |
| R2 | Hidden information leaks through seat mode | Medium | High | Server-enforced projection; god view is a separate mode; leak matrix over API payloads; raw records are spectator-only. |
| R3 | The console contaminates a run | Low | High | No live session; no live board; spawn the CLI; console death does not affect a run; no writes under roots. |
| R4 | The record layout changes again after the console ships | Medium | High | M0 fixes it before M1; one reader; no globbing; schema-checked manifests; docs amended. |
| R5 | The Node toolchain erodes the dependency boundary | Medium | Medium | Build-time only; `core`/`games` boundary test; Python suite needs no Node. |
| R6 | Replay latency makes scrubbing unpleasant | Medium | Medium | Replay once, cache states, O(1) frame access, measure the 790-action record. |
| R7 | Model text becomes an XSS vector | Low | High | Text nodes only; automated escaping test; no raw HTML rendering. |
| R8 | The shell overfits to Catan | Medium | High | Test-only second view; no game name in generic modules; view declaration as the seam. |
| R9 | Old records become unviewable | Medium | Medium | Explicit compatibility check; historical plugin policy recorded as an open question; no silent guessing. |
| R10 | Setup form drifts from the runner | High | High | One declared schema and parser; round-trip and equivalence tests; no client-side repair. |
| R11 | Launch leaves orphan processes or a half-run | Medium | Medium | Process handle per launch; cancel by signal; the runner owns the record; incomplete is a status. |
| R12 | Scope creep into statistics or live play | High | High | §4 non-goals; separate ASGI app; no live endpoint; V4 owns inference. |
| R13 | The frontend is untested and rots | Medium | Medium | Thin shell, pure functions tested, typed API fixtures, optional browser smoke. |

---

## 15. Decisions and open questions

### 15.1 Resolved

| # | Question | Resolution |
|---|---|---|
| Q1 | Scope: GUI plus statistics, or GUI only? | **v3 is the operator console and replay viewer; v4 is inference.** The roadmap split is recorded in §1.1. |
| Q2 | Run layout? | **Nested per-game directories plus a root experiment manifest.** The root manifest is written before play and carries the plan; the per-game directory is portable. FR-12, ARCHITECTURE.md §8.2. |
| Q3 | Frontend technology? | **Svelte 5 + Vite + TypeScript + inline SVG.** No SSR, no UI kit, no D3, no router/state/form library. Node is build-time only. FR-9. |
| Q4 | How does a run start? | **The console writes a declaration and spawns the existing `run` command.** It never executes the runner in-process. FR-1.3, FR-6.10. |
| Q5 | Is a seat view in v3? | **Yes**, because hidden information is the most likely way a GUI starts lying. Server-enforced, with a leak matrix. FR-3.10. |
| Q6 | What schema does the root manifest use? | **`lgbg.experiment.v1`**, separate from the per-game `lgbg.run.v1`. FR-12.2, §11.2. |
| Q7 | Do old v2 runs need a legacy reader? | **No.** v2 is not accepted yet; its runs are regenerated. Standalone v1 golden records remain supported. FR-2.8, FR-12.9. |
| Q8 | Progress transport? | **Poll the run directory.** No websocket, no server-sent events, no live game state. FR-6.11. |
| Q9 | Can the console cancel a run? | **Yes, only a run it launched in this process**, by signalling the process. The record is left untouched and the run is reported incomplete/cancelled. FR-6.12. |
| Q10 | Where does the scoreboard come from? | **`Game.standings()` in spectator mode; the seat's own observation `points` in seat mode.** No score is computed by a renderer. FR-3.5. |

### 15.2 Open

| # | Question | Current position |
|---|---|---|
| Q11 | Static export of a replay | Deferred; keep the API data-driven so a self-contained bundle remains possible. |
| Q12 | Third-party renderers | Not in v3. An external game is replayable as text; a renderer contract and trust model are future work. |
| Q13 | Visual regression testing | No screenshot diffs in v3. Scene JSON is golden-tested; the browser smoke test is optional. |
| Q14 | Historical plugin retention | A record is viewable while its rules version is installed. How many old versions to keep is an archive policy, not a console feature. |
| Q15 | Packaging the frontend | v3 runs from the checkout (`package = false`). Whether a wheel ships prebuilt assets is a later distribution decision. |

---

## 16. Traceability

| Requirement group | Architecture reference |
|---|---|
| FR-1 | §4 (nothing imports the console), §12.4 (read-only, no live session) |
| FR-2 | §8.2 (run artefacts), §7.9 (versions), §12.4 (compatibility) |
| FR-3 | §5.6 (decisions), §7.8 (projection), §8 (replay), §12.4 (frames) |
| FR-4 | §7.12 (view declaration), §7.5 (derived structure), §15.5 (presentation tests) |
| FR-5 | §7.8 (seat view is a projection), §12.4 (no god view in the client), §15.5 |
| FR-6 | §7.12 (configuration schema), §12.4 (declare, never execute) |
| FR-7 | §12.1 (frontend over the same authority), §12.4 (local, scoped) |
| FR-8 | §12.4 (the console is one surface, not a second runner) |
| FR-9 | §4 (layering), §7.12 (declared views) |
| FR-10 | §15.1–§15.5 (testing strategy) |
| FR-11 | §4 (dependency direction), §7.3 (schemas as data) |
| FR-12 | §8.2 (file layout), §8.1 (the record is a program) |

---

## 17. Sign-off

| Role | Name | Decision | Date |
|---|---|---|---|
| Product owner | | | |
| Architecture owner | | | |
