"""The command line (PRD-v1 FR-20, section 10.3).

    lgbg new    --game NAME [--seed N] [--players N] [--assist L0|L1|L2] [--<option> VALUE]
    lgbg play   --script FILE --out DIR [--allow-rejections]
    lgbg replay LOG [--print-states]
    lgbg verify PATH [--strict]

Every command also accepts `--plugin MODULE` to import a module that registers games.

Every command exits non-zero on failure with a legible message, and never prints a traceback
for an expected failure (FR-20.7). An operator diagnosing a benchmark run from a stack trace
is an operator who cannot diagnose it at all.

Game-declared options are passed through as `--<option> VALUE` and by the run file; the core
never interprets them, which is what keeps this surface game-agnostic (P11).
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.adapters.cli.inspect_run import inspect_run as read_run
from lgbg.adapters.cli.live import play_live as run_live
from lgbg.adapters.cli.mcp_client import ClientError
from lgbg.adapters.cli.runfile import run_from_file
from lgbg.adapters.cli.script import ScriptError, drive, load_script
from lgbg.adapters.cli.serve import serve as serve_command
from lgbg.adapters.mcp.benchmark import DEFAULT_SESSION_ID
from lgbg.agents.context import ContextError
from lgbg.agents.pricing import UnknownPriceError
from lgbg.agents.prompting import PromptError
from lgbg.agents.providers.base import ProviderError
from lgbg.core.assist import render_decision
from lgbg.core.canonical import hash_state, to_canonical_json
from lgbg.core.config import DEFAULT_PLAYERS, AssistLevel, ConfigError, GameConfig, RunConfig
from lgbg.core.delta import render_delta
from lgbg.core.fuzzing import POLICIES, run_fuzz
from lgbg.core.game import Applied, GamePluginError, get_game
from lgbg.core.log import GOD_LOG_SUFFIX, GameLogReader, LogError
from lgbg.core.replay import ReplayError, replay, verify
from lgbg.core.run import AmbiguousRequestError, GameRun
from lgbg.core.types import Action, DecisionRequest, JsonValue
from lgbg.runner.design import DesignError
from lgbg.runner.game import GameError
from lgbg.runner.manifest import ManifestError
from lgbg.runner.results import ResultsError

EXPECTED_FAILURES: tuple[type[Exception], ...] = (
    ConfigError,
    GamePluginError,
    LogError,
    ReplayError,
    ScriptError,
    AmbiguousRequestError,
    ClientError,
    OSError,
    ContextError,
    PromptError,
    ProviderError,
    UnknownPriceError,
    DesignError,
    GameError,
    ManifestError,
    ResultsError,
)
"""Failures an operator is expected to cause, and so deserves a sentence, not a stack trace."""

DEFAULT_GAME_ID = "g-0001"
DEFAULT_FUZZ_SEED = 20260101
"""A seed for a fuzzed run when the operator does not care which one: any seed is a valid run."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lgbg", description="LLM Board Game Benchmark")
    commands = parser.add_subparsers(dest="command", required=True)

    new = commands.add_parser(
        "new", help="create a game from a configuration and show its decisions"
    )
    new.add_argument("--game", required=True, help="a registered game name")
    new.add_argument("--seed", type=int, default=1, help="the seed the run starts from")
    new.add_argument("--players", type=int, default=DEFAULT_PLAYERS, help="seats in the run")
    new.add_argument("--assist", default=None, help="L0, L1 or L2 (default L1)")
    new.add_argument("--rejection-detail", default=None, help="minimal, standard or full")
    new.add_argument("--protocol", default="decline_only", help="the interaction protocol")
    new.add_argument("--board", default=None, help="which board the game should use")
    _add_plugin_option(new)

    play = commands.add_parser("play", help="drive a game from a scripted action file")
    _add_plugin_option(play)
    source = play.add_mutually_exclusive_group(required=True)
    source.add_argument("--script", help="the scripted action file")
    source.add_argument(
        "--interactive",
        action="store_true",
        help="read one JSON action per line from standard input",
    )
    play.add_argument("--game", default="fixture", help="the game to play, when interactive")
    play.add_argument("--seed", type=int, default=1, help="the seed, when interactive")
    play.add_argument(
        "--players", type=int, default=DEFAULT_PLAYERS, help="seats, when interactive"
    )
    play.add_argument("--protocol", default="decline_only", help="the interaction protocol")
    play.add_argument("--board", default=None, help="which board the game should use")
    play.add_argument("--out", required=True, help="the run directory to write the record into")
    play.add_argument(
        "--game-id", default=DEFAULT_GAME_ID, help="the id this game is recorded under"
    )
    play.add_argument(
        "--allow-rejections",
        action="store_true",
        help="keep playing after a rejected action instead of stopping",
    )

    live = commands.add_parser(
        "play-live", help="play interactively through the MCP sandbox surface"
    )
    _add_plugin_option(live)
    live.add_argument("--game", required=True, help="a registered game name")
    live.add_argument("--seed", type=int, default=1, help="the seed the run starts from")
    live.add_argument("--players", type=int, default=DEFAULT_PLAYERS, help="seats in the run")
    live.add_argument("--protocol", default="decline_only", help="the interaction protocol")
    live.add_argument(
        "--session-id", default=DEFAULT_GAME_ID, help="the id this game is recorded under"
    )
    live.add_argument("--out", required=True, help="the run directory to write the record into")
    live.add_argument(
        "--player",
        type=int,
        default=0,
        help="the seat to show when the assist level exposes no decisions (L0)",
    )
    live.add_argument(
        "--assist",
        choices=[level.value for level in AssistLevel],
        default=AssistLevel.L1.value,
        help="what the resources reveal, fixed for the run",
    )
    live.add_argument("--detail", default="full", help="the renderer's detail level")

    serve = commands.add_parser("serve", help="start the HTTP host or one MCP profile over stdio")
    _add_plugin_option(serve)
    serve.add_argument("--game", default=None, help="the game an MCP surface serves")
    serve.add_argument("--http", default=None, metavar="HOST:PORT", help="serve the HTTP host")
    serve.add_argument(
        "--mcp",
        choices=["sandbox", "benchmark"],
        default=None,
        help="serve an MCP profile over stdio",
    )
    serve.add_argument(
        "--player", type=int, default=None, help="the seat a benchmark surface serves"
    )
    serve.add_argument("--seed", type=int, default=1, help="the seed the session starts from")
    serve.add_argument("--players", type=int, default=DEFAULT_PLAYERS, help="seats in the session")
    serve.add_argument(
        "--session-id", default=DEFAULT_SESSION_ID, help="the id the session is recorded under"
    )
    serve.add_argument("--protocol", default="decline_only", help="the interaction protocol")
    serve.add_argument("--record-dir", default=None, help="the run directory to record into")
    serve.add_argument(
        "--assist",
        choices=[level.value for level in AssistLevel],
        default=AssistLevel.L1.value,
        help="what the resources reveal, fixed for the process",
    )
    serve.add_argument("--detail", default="full", help="the renderer's detail level")

    run_command = commands.add_parser("run", help="play a run declared in a config file")
    _add_plugin_option(run_command)
    run_command.add_argument("--config", required=True, help="the run config file")
    run_command.add_argument("--out", default=None, help="the run directory to write")
    run_command.add_argument("--run-id", default=None, help="the id the run is recorded under")
    run_command.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="how many games may be in flight at once",
    )

    inspect_run_command = commands.add_parser(
        "inspect-run", help="read a run directory: games, one game, or one seat's turns"
    )
    _add_plugin_option(inspect_run_command)
    inspect_run_command.add_argument("path", help="a run directory holding results.json")
    inspect_run_command.add_argument("--game", default=None, help="one game's summary")
    inspect_run_command.add_argument(
        "--seat", type=int, default=None, help="with --game, that seat's decision turns"
    )

    replay_command = commands.add_parser("replay", help="replay a record, verifying every hash")
    _add_plugin_option(replay_command)
    replay_command.add_argument("log", help="a .god.jsonl record")
    replay_command.add_argument(
        "--print-states", action="store_true", help="print the state after every action"
    )
    replay_command.add_argument(
        "--delta",
        action="store_true",
        help="with --print-states, print only what changed at each step",
    )
    replay_command.add_argument(
        "--compact",
        action="store_true",
        help="render the printed states compactly, for reading a long game",
    )

    inspect_command = commands.add_parser(
        "inspect", help="dump a projection, or render the board alone"
    )
    _add_plugin_option(inspect_command)
    inspect_command.add_argument("log", help="a .god.jsonl record")
    inspect_command.add_argument(
        "--player", type=int, default=None, help="whose view to dump; the spectator's by default"
    )
    inspect_command.add_argument("--board", action="store_true", help="render the board alone")
    inspect_command.add_argument(
        "--seq", type=int, default=None, help="the state after this many actions, not the last"
    )
    inspect_command.add_argument("--compact", action="store_true", help="render compactly")
    inspect_command.add_argument(
        "--assist",
        choices=[level.value for level in AssistLevel],
        default=None,
        help="show the decision this player is given at that level of assistance",
    )

    verify_command = commands.add_parser(
        "verify", help="verify a record, or every record in a directory"
    )
    _add_plugin_option(verify_command)
    verify_command.add_argument("path", help="a .god.jsonl record, or a run directory")
    verify_command.add_argument(
        "--strict", action="store_true", help="treat a record with no terminal line as a failure"
    )

    fuzz_command = commands.add_parser(
        "fuzz", help="run one fuzzed game and report what the harness found"
    )
    _add_plugin_option(fuzz_command)
    fuzz_command.add_argument("--game", required=True, help="a registered game name")
    fuzz_command.add_argument("--seed", type=int, default=DEFAULT_FUZZ_SEED, help="the run seed")
    fuzz_command.add_argument("--players", type=int, default=DEFAULT_PLAYERS)
    fuzz_command.add_argument("--actions", type=int, default=400, help="the bound before livelock")
    fuzz_command.add_argument(
        "--policy", choices=sorted(POLICIES), default="uniform", help="how the driver chooses"
    )
    fuzz_command.add_argument("--out", default=None, help="a directory to record the game in")

    return parser


def _add_plugin_option(parser: argparse.ArgumentParser) -> None:
    """Let an operator register games that do not ship with the engine (section 7.4).

    In-repo plugins are imported already. This is the explicit-import path for a game that
    lives elsewhere - including a test asset, which is how the fixture game is played by hand.
    """
    parser.add_argument(
        "--plugin",
        action="append",
        default=[],
        metavar="MODULE",
        help="import a module that registers games; repeatable",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    try:
        for module in args.plugin:
            importlib.import_module(module)
        if extra and args.command not in ("new", "fuzz", "play-live", "serve"):
            parser.error(f"unrecognised arguments: {' '.join(extra)}")
        match args.command:
            case "new":
                return _new(args, _game_options(extra))
            case "fuzz":
                return _fuzz(args, _game_options(extra))
            case "play":
                return _play(args)
            case "play-live":
                return _play_live(args, _game_options(extra))
            case "serve":
                return _serve(args, _game_options(extra))
            case "run":
                return _run(args)
            case "inspect-run":
                return read_run(root=Path(args.path), game=args.game, seat=args.seat)
            case "replay":
                return _replay(args)
            case "inspect":
                return _inspect(args)
            case _:
                return _verify(args)
    except EXPECTED_FAILURES as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _game_options(extra: Sequence[str]) -> dict[str, JsonValue]:
    """Turn '--board fixed:standard_a' into a game-declared option.

    The value is read as JSON when it can be, so '--tokens 5' is a number and
    '--board fixed:standard_a' is a string.
    """
    options: dict[str, JsonValue] = {}
    index = 0
    while index < len(extra):
        flag = extra[index]
        if not flag.startswith("--") or index + 1 >= len(extra):
            raise ConfigError(f"game options are given as --name value, got {flag!r}")
        key = flag[2:].replace("-", "_")
        if key in options:
            raise ConfigError(f"game option {flag} was given twice")
        options[key] = _as_json(extra[index + 1])
        index += 2
    return options


def _as_json(text: str) -> JsonValue:
    try:
        value: Any = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(value, bool | int | str) or value is None:
        return value
    return text


def _new(args: argparse.Namespace, game_options: dict[str, JsonValue]) -> int:
    game = get_game(args.game)
    raw: dict[str, JsonValue] = {
        "seed": args.seed,
        "players": args.players,
        "interaction_protocol": args.protocol,
    }
    raw.update(game_options)
    if args.assist is not None:
        raw["assist"] = args.assist
    if args.rejection_detail is not None:
        raw["rejection_detail"] = args.rejection_detail
    config = RunConfig.from_mapping(raw, game_option_keys=None)

    run = GameRun(game, config, game_id=DEFAULT_GAME_ID)
    print(f"game: {game.name} (rules {game.rules_version}, schema {game.schema_version})")
    print(f"seed: {config.seed}  players: {config.players}  assist: {config.assist}")
    print(f"initial state hash: {hash_state(run.state, game)}")
    _print_requests(run.pending)
    run.close()
    return 0


def _print_requests(requests: Sequence[DecisionRequest]) -> None:
    if not requests:
        print("open decisions: none")
        return
    print(f"open decisions: {len(requests)}")
    for request in requests:
        context = to_canonical_json(request.context)
        print(
            f"  {request.request_id}  player {request.player}  kind {request.kind}  "
            f"phase {request.phase}  schema {request.schema_ref}  context {context}"
        )


def _play_live(args: argparse.Namespace, game_options: dict[str, JsonValue]) -> int:
    """Drive one interactive game through the MCP sandbox surface (FR-14.4)."""
    return run_live(
        game=args.game,
        seed=args.seed,
        players=args.players,
        protocol=args.protocol,
        session_id=args.session_id,
        out=Path(args.out),
        assist=AssistLevel(args.assist),
        detail=args.detail,
        plugins=args.plugin,
        game_options=game_options,
        player=args.player,
    )


def _serve(args: argparse.Namespace, game_options: dict[str, JsonValue]) -> int:
    """Start the HTTP host or one MCP profile (FR-14.1)."""
    return serve_command(
        game=args.game,
        http=args.http,
        mcp=args.mcp,
        player=args.player,
        seed=args.seed,
        players=args.players,
        session_id=args.session_id,
        protocol=args.protocol,
        record_dir=None if args.record_dir is None else Path(args.record_dir),
        assist=AssistLevel(args.assist),
        detail=args.detail,
        game_options=game_options,
    )


def _run(args: argparse.Namespace) -> int:
    """Play a run declared in a config file, unattended, and report what it wrote (FR-14.2)."""
    result = run_from_file(
        Path(args.config),
        out=None if args.out is None else Path(args.out),
        run_id=args.run_id,
        concurrency=args.concurrency,
    )
    payload = json.loads(result.results_path.read_text(encoding="utf-8"))
    summary = payload["summary"]
    print(f"run: {result.run_id}  root: {result.root}")
    print(
        f"games: {summary['games']}  completed: {summary['completed']}  "
        f"abandoned: {summary['abandoned']}"
    )
    print(
        f"tokens: {summary['total_tokens']}  cost: {summary['cost_micro_usd']}µ$  "
        f"latency: {summary['latency_ms']}ms"
    )
    print(f"results: {result.results_path}")
    return 0


def _play_interactively(args: argparse.Namespace) -> int:
    """Drive a game by hand: one JSON action per line on standard input (FR-20.2).

    Recording an interactive session back into a scripted file is open question Q6 and is not
    in this release. The record on disk is still a full record, so a session can be replayed,
    verified and inspected exactly like a scripted one.
    """
    game = get_game(args.game)
    settings: dict[str, JsonValue] = {
        "seed": args.seed,
        "players": args.players,
        "interaction_protocol": args.protocol,
    }
    if args.board is not None:
        settings["board"] = args.board
    config = RunConfig.from_mapping(settings, game_option_keys=None)
    out = Path(args.out)
    run = GameRun(game, config, game_id=args.game_id, directory=out)
    print(game.render(game.observe_spectator(run.state), detail="compact"))
    _print_requests(run.pending)

    for number, line in enumerate(sys.stdin, start=1):
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
            action = Action(
                player=int(payload["player"]),
                type=str(payload["type"]),
                params=payload.get("params", {}),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            print(f"error: line {number}: {error}", file=sys.stderr)
            run.close()
            return 1
        result = run.submit(action, request_id=payload.get("request_id"))
        if isinstance(result, Applied):
            print(f"{number}: accepted {action.type} by seat {action.player}")
        else:
            print(
                f"{number}: rejected {result.rejection.code.code}: {result.rejection.message}",
                file=sys.stderr,
            )

    terminal = run.finish()
    print(f"attempts: {terminal.total_actions}  rejections: {terminal.rejections}")
    print(f"record: {out / 'games' / (args.game_id + GOD_LOG_SUFFIX)}")
    return 0


def _inspect(args: argparse.Namespace) -> int:
    """Dump one view of one state (FR-20.5).

    The rendering is the game's own (ARCHITECTURE.md section 11.3): the CLI prints what the
    game says a projection looks like, and knows nothing about boards itself.
    """
    log = GameLogReader(Path(args.log)).read()
    game = get_game(log.header.game)
    replayed = replay(log, game)
    last = len(replayed.states) - 1
    index = last if args.seq is None else max(0, min(args.seq + 1, last))
    state = replayed.states[index]
    if args.assist is not None:
        # What one player is shown, at the level the run was configured for (FR-17.4). The
        # level is a property of the interface, so an operator can look at the same position
        # through all three lenses without the game changing underneath.
        if args.player is None:
            print("error: --assist shows a decision, so --player is required", file=sys.stderr)
            return 1
        print(render_decision(game, state, args.player, assist=AssistLevel(args.assist)))
        return 0
    observation = (
        game.observe_spectator(state) if args.player is None else game.observe(state, args.player)
    )
    detail = "board" if args.board else ("compact" if args.compact else "full")
    try:
        print(game.render(observation, detail=detail))
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def _play(args: argparse.Namespace) -> int:
    if args.interactive:
        return _play_interactively(args)
    script = load_script(Path(args.script))
    game = get_game(script.game)
    out = Path(args.out)
    run = GameRun(game, script.config, game_id=args.game_id, directory=out)

    failure: ScriptError | None = None
    try:
        drive(run, script, allow_rejections=args.allow_rejections)
    except ScriptError as error:
        failure = error
    terminal = run.finish()

    print(f"game: {game.name} ({args.game_id})")
    print(f"attempts: {terminal.total_actions}  rejections: {terminal.rejections}")
    scores = to_canonical_json(dict(terminal.final_scores))
    print(f"outcome: winner {terminal.winner}  scores {scores}  rounds {terminal.rounds}")
    print(f"record: {out / 'games' / (args.game_id + GOD_LOG_SUFFIX)}")
    if failure is not None:
        print(f"error: {failure}", file=sys.stderr)
        return 1
    return 0


def _fuzz(args: argparse.Namespace, game_options: dict[str, JsonValue]) -> int:
    """Run one fuzzed game and report what the harness found (FR-20.6; FR-22.1 to FR-22.6).

    The command is the harness with a face on it: the report goes to stdout, and a game that
    broke one of its own declarations exits non-zero with the violations on stderr, because an
    operator reading a pipeline needs the difference between a wide run and a broken plugin.
    """
    game = get_game(args.game)
    config = RunConfig(
        seed=args.seed,
        players=args.players,
        interaction_protocol="decline_only",
        game_config=GameConfig(game_options),
    )
    directory = None if args.out is None else Path(args.out)
    report = run_fuzz(
        game, config, policy=POLICIES[args.policy], max_actions=args.actions, directory=directory
    )
    counted = f"{report.actions} actions, {report.accepted} accepted, {report.rejected} refused"
    print(f"{game.name}: {counted}")
    print("codes: " + (" ".join(report.codes) if report.codes else "none"))
    print("outcome: " + ("livelock" if report.livelock else "finished"))
    for offender in report.offenders:
        print(f"violated: {offender}", file=sys.stderr)
    return 1 if report.offenders else 0


def _replay(args: argparse.Namespace) -> int:
    log = GameLogReader(Path(args.log)).read()
    game = get_game(log.header.game)

    replayed = replay(log, game)

    detail = "compact" if args.compact else "full"
    print(f"game: {log.header.game} ({log.header.game_id})  rules {log.header.rules_version}")
    if args.print_states:
        # Rendered by the game's own notation, through the protocol: the CLI does not know
        # what a board looks like, and must not learn (ARCHITECTURE.md section 11.3).
        print("initial state:")
        print(game.render(game.observe_spectator(replayed.states[0]), detail=detail))
    for index, record in enumerate(log.actions):
        status = "ok" if record.result.get("ok") is True else f"rejected {record.result['error']}"
        print(
            f"seq {record.seq}  player {record.player}  {record.action.type}  {status}  "
            f"{record.state_hash_prev} -> {record.state_hash}"
        )
        if args.print_states:
            now = game.observe_spectator(replayed.states[index + 1])
            if args.delta:
                # A step, not a position (FR-19.4). The comparison is of two projections, so it
                # is the core's and the CLI still knows nothing about boards.
                print(f"delta after seq {record.seq}:")
                print(render_delta(game.observe_spectator(replayed.states[index]), now))
            else:
                print(f"state after seq {record.seq}:")
                print(game.render(now, detail=detail))
    print(
        f"verified {replayed.actions} action(s), {replayed.rejections} rejection(s); "
        f"final hash {replayed.terminal_hash}"
    )
    return 0


def _verify(args: argparse.Namespace) -> int:
    target = Path(args.path)
    if not target.exists():
        raise FileNotFoundError(f"{target} does not exist")
    logs = sorted(target.rglob("*" + GOD_LOG_SUFFIX)) if target.is_dir() else [target]
    if not logs:
        raise FileNotFoundError(f"{target} holds no {GOD_LOG_SUFFIX} record")

    failures = 0
    for path in logs:
        try:
            log = GameLogReader(path).read()
            if args.strict and log.terminal is None:
                raise LogError(f"{path}: the record has no terminal line")
            report = verify(log, get_game(log.header.game))
        except EXPECTED_FAILURES as error:
            failures += 1
            print(f"failed: {path}: {error}", file=sys.stderr)
            continue
        status = "ok" if report.completed else "incomplete"
        ending = "" if report.completed else ", no terminal record"
        print(
            f"{status}: {path}: {report.actions} action(s), {report.rejections} rejection(s), "
            f"final hash {report.terminal_hash}{ending}"
        )
    return 1 if failures else 0
