"""inspect-run: read a run directory the way a reviewer does (PRD-v2 FR-14.3).

Three reads, each one level deeper than the last:

    inspect-run DIR                     every game, one line each
    inspect-run DIR --game ID           one game's outcome, design and per-seat split
    inspect-run DIR --game ID --seat N  that seat's decision turns, with the exact messages
                                        it was sent and the exact response it gave

The artefact is the source. The list and the per-game summary come from results.json, which the
runner already validated before writing; the conversation comes from the game's sidecar, which is
the record of what the model saw and said. Nothing is recomputed and no model is called, so a
reviewer can read a run months after the gateway that produced it has changed.

Exactness is the point of the third read: the messages and the response are printed as canonical
JSON, not summarised. A summary would be a second account of the record, and the first thing a
reviewer needs is the record itself.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from lgbg.core.canonical import to_canonical_json
from lgbg.core.config import ConfigError
from lgbg.runner.results import RESULTS_FILENAME

_MESSAGES_HEADING: Final[str] = "messages:"
_RESPONSE_HEADING: Final[str] = "response:"


def inspect_run(*, root: Path, game: str | None, seat: int | None) -> int:
    """Print the requested level of the run. Returns a process exit code."""
    if seat is not None and game is None:
        raise ConfigError("--seat reads one game's decisions, so --game is required")
    payload = _results(root)
    games = _games(payload)
    if game is None:
        _print_games(games)
        return 0
    chosen = _find(games, game)
    if seat is None:
        _print_game(chosen)
        return 0
    _print_turns(root, game, seat)
    return 0


def _results(root: Path) -> dict[str, Any]:
    path = root / RESULTS_FILENAME
    if not path.is_file():
        raise ConfigError(f"{root} holds no {RESULTS_FILENAME}, so it is not a run directory")
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigError(f"{path} is not JSON: {error}") from None
    if not isinstance(payload, Mapping):
        raise ConfigError(f"{path} must hold a JSON object")
    return {str(key): value for key, value in payload.items()}


def _games(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("games")
    if not isinstance(raw, list):
        raise ConfigError("results.json has no games array")
    return [
        {str(key): value for key, value in item.items()}
        for item in raw
        if isinstance(item, Mapping)
    ]


def _find(games: list[dict[str, Any]], game_id: str) -> dict[str, Any]:
    for game in games:
        if game.get("game_id") == game_id:
            return game
    known = [str(game.get("game_id")) for game in games]
    raise ConfigError(f"{game_id} is not in this run; the games are {known}")


def _print_games(games: list[dict[str, Any]]) -> None:
    print(f"games: {len(games)}")
    for game in games:
        status = "completed" if game.get("completed") is True else "abandoned"
        outcome = game.get("outcome")
        winner = outcome.get("winner") if isinstance(outcome, Mapping) else None
        ending = "" if winner is None else f" winner {winner}"
        print(
            f"  {game.get('game_id')}  {status}{ending}  actions {game.get('actions')}  "
            f"tokens {game.get('total_tokens')}  cost {game.get('cost_micro_usd')}µ$"
        )


def _print_game(game: Mapping[str, Any]) -> None:
    print(f"game: {game.get('game_id')}")
    print(f"completed: {game.get('completed')}")
    outcome = game.get("outcome")
    if isinstance(outcome, Mapping):
        print(f"outcome: winner {outcome.get('winner')}  scores {_json(outcome.get('scores'))}")
    else:
        print("outcome: none (the game was abandoned)")
    print(f"actions: {game.get('actions')}  rejections: {_json(game.get('rejections_by_code'))}")
    print(f"failures: {_json(game.get('failures_by_kind'))}")
    print(
        f"tokens: {game.get('total_tokens')}  cost: {game.get('cost_micro_usd')}µ$  "
        f"latency: {game.get('latency_ms')}ms  partial: {game.get('partial')}"
    )
    design = game.get("design")
    if isinstance(design, Mapping):
        print(
            f"design: {design.get('seating')}  "
            f"configuration {design.get('initial_configuration')}  "
            f"replicate {design.get('replicate')}  rotation {design.get('rotation')}"
        )
    abandonment = game.get("abandonment")
    if isinstance(abandonment, Mapping):
        print(
            f"abandoned: seat {abandonment.get('seat')}  {abandonment.get('failure')}  "
            f"attempts {abandonment.get('attempts')}"
        )
    seats = game.get("seats")
    if isinstance(seats, list):
        for row in seats:
            if not isinstance(row, Mapping):
                continue
            print(
                f"  seat {row.get('seat')}  {row.get('agent')} {row.get('model') or ''}  "
                f"{row.get('outcome') or 'no outcome'}  place {row.get('place')}  "
                f"actions {row.get('actions')}  tokens {row.get('total_tokens')}  "
                f"cost {row.get('cost_micro_usd')}µ$"
            )


def _print_turns(root: Path, game_id: str, seat: int) -> None:
    sidecar = _sidecar(root, game_id)
    turns = 0
    for record in _records(sidecar):
        if record.get("t") != "decision" or record.get("seat") != seat:
            continue
        turns += 1
        _print_turn(record)
    if turns == 0:
        print(f"game {game_id} has no decision turns for seat {seat}")
        return
    print(f"decision turns: {turns} for seat {seat} in {game_id}")


def _print_turn(record: Mapping[str, Any]) -> None:
    outcome = record.get("outcome")
    kind = outcome.get("kind") if isinstance(outcome, Mapping) else None
    print(
        f"decision {record.get('request_id')}  seat {record.get('seat')}  "
        f"model {record.get('model')}  attempt {record.get('attempt')}  outcome {kind}"
    )
    print(_MESSAGES_HEADING)
    messages = record.get("messages")
    if isinstance(messages, list):
        for message in messages:
            print("  " + _json(message))
    print(_RESPONSE_HEADING)
    print("  " + _json(record.get("response")))
    usage = record.get("usage")
    print(
        f"usage: {_json(usage)}  cost: {record.get('cost_micro_usd')}µ$  "
        f"latency: {record.get('latency_ms')}ms"
    )
    rejection = record.get("rejection")
    if rejection is not None:
        print(f"rejection: {_json(rejection)}")
    if record.get("failure") is not None:
        print(f"failure: {record.get('failure')}")


def _sidecar(root: Path, game_id: str) -> Path:
    direct = root / game_id / "games" / f"{game_id}.meta.jsonl"
    if direct.is_file():
        return direct
    matches = sorted(root.rglob(f"{game_id}.meta.jsonl"))
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ConfigError(f"{game_id} has no .meta.jsonl sidecar under {root}")
    raise ConfigError(f"{game_id} has more than one sidecar under {root}")


def _records(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ConfigError(f"{path} cannot be read: {error}") from None
    records: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            item: Any = json.loads(line)
        except json.JSONDecodeError as error:
            raise ConfigError(f"{path} is not JSON lines: {error}") from None
        if isinstance(item, Mapping):
            records.append({str(key): value for key, value in item.items()})
    return records


def _json(value: object) -> str:
    if value is None or isinstance(value, bool | int | str):
        return to_canonical_json(value)
    if isinstance(value, Mapping):
        return to_canonical_json({str(key): item for key, item in value.items()})
    if isinstance(value, list):
        return to_canonical_json(list(value))
    return str(value)


__all__: Final[list[str]] = ["inspect_run"]
