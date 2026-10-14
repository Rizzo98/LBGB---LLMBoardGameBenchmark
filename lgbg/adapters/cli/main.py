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
from lgbg.adapters.cli.script import ScriptError, drive, load_script
from lgbg.core.canonical import hash_state, to_canonical_json
from lgbg.core.config import DEFAULT_PLAYERS, ConfigError, RunConfig
from lgbg.core.game import GamePluginError, get_game
from lgbg.core.log import GOD_LOG_SUFFIX, GameLogReader, LogError
from lgbg.core.replay import ReplayError, replay, verify
from lgbg.core.run import AmbiguousRequestError, GameRun
from lgbg.core.types import DecisionRequest, JsonValue

EXPECTED_FAILURES: tuple[type[Exception], ...] = (
    ConfigError,
    GamePluginError,
    LogError,
    ReplayError,
    ScriptError,
    AmbiguousRequestError,
    OSError,
)
"""Failures an operator is expected to cause, and so deserves a sentence, not a stack trace."""

DEFAULT_GAME_ID = "g-0001"


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
    _add_plugin_option(new)

    play = commands.add_parser("play", help="drive a game from a scripted action file")
    _add_plugin_option(play)
    play.add_argument("--script", required=True, help="the scripted action file")
    play.add_argument("--out", required=True, help="the run directory to write the record into")
    play.add_argument(
        "--game-id", default=DEFAULT_GAME_ID, help="the id this game is recorded under"
    )
    play.add_argument(
        "--allow-rejections",
        action="store_true",
        help="keep playing after a rejected action instead of stopping",
    )

    replay_command = commands.add_parser("replay", help="replay a record, verifying every hash")
    _add_plugin_option(replay_command)
    replay_command.add_argument("log", help="a .god.jsonl record")
    replay_command.add_argument(
        "--print-states", action="store_true", help="print the state after every action"
    )
    replay_command.add_argument(
        "--compact",
        action="store_true",
        help="render the printed states compactly, for reading a long game",
    )

    verify_command = commands.add_parser(
        "verify", help="verify a record, or every record in a directory"
    )
    _add_plugin_option(verify_command)
    verify_command.add_argument("path", help="a .god.jsonl record, or a run directory")
    verify_command.add_argument(
        "--strict", action="store_true", help="treat a record with no terminal line as a failure"
    )

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
        if extra and args.command != "new":
            parser.error(f"unrecognised arguments: {' '.join(extra)}")
        match args.command:
            case "new":
                return _new(args, _game_options(extra))
            case "play":
                return _play(args)
            case "replay":
                return _replay(args)
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


def _play(args: argparse.Namespace) -> int:
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
            print(f"state after seq {record.seq}:")
            print(game.render(game.observe_spectator(replayed.states[index + 1]), detail=detail))
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
        print(
            f"ok: {path}: {report.actions} action(s), {report.rejections} rejection(s), "
            f"final hash {report.terminal_hash}"
        )
    return 1 if failures else 0
