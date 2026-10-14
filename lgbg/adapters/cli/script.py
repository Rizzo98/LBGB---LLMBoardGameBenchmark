"""The scripted action file and its driver (PRD-v1 FR-21, section 10.2).

A script is how a game is reproduced without an agent: the same file, the same record, every
time. It declares the game, the configuration, and an ordered list of actions.

Two rules make the file usable as a fixture rather than as a suggestion:

- An action may name the decision it answers; if it does not, it must belong to exactly one
  open decision, and an ambiguous choice is an error rather than a guess (FR-21.2).
- A rejected action stops the driver (FR-21.3). A fixture that quietly continued past a
  rejection would produce a record nobody could explain.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lgbg.core.config import RunConfig
from lgbg.core.game import ApplyResult, Rejected
from lgbg.core.run import GameRun
from lgbg.core.types import Action, JsonValue, PlayerId


class ScriptError(Exception):
    """The script cannot be read, or describes something that cannot be played."""


@dataclass(frozen=True, slots=True)
class ScriptedAction:
    """One entry of the script's action list."""

    player: PlayerId
    type: str
    params: Mapping[str, JsonValue]
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class Script:
    """A game to play, and how to play it."""

    game: str
    config: RunConfig
    actions: list[ScriptedAction]


def load_script(path: Path) -> Script:
    """Read a scripted action file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ScriptError(f"cannot read the script {path}: {error}") from error
    try:
        raw: Any = json.loads(text)
    except json.JSONDecodeError as error:
        raise ScriptError(f"{path}: not valid JSON: {error}") from error
    if not isinstance(raw, Mapping):
        raise ScriptError(f"{path}: a script must be a JSON object")

    game = raw.get("game")
    if not isinstance(game, str) or not game:
        raise ScriptError(f"{path}: a script must name a game")
    config = raw.get("config", {})
    if not isinstance(config, Mapping):
        raise ScriptError(f"{path}: 'config' must be a JSON object")
    entries = raw.get("actions", [])
    if not isinstance(entries, list):
        raise ScriptError(f"{path}: 'actions' must be a JSON array")
    return Script(
        game=game,
        config=RunConfig.from_mapping(config, game_option_keys=None),
        actions=[_action(entry, index, path) for index, entry in enumerate(entries)],
    )


def _action(entry: Any, index: int, path: Path) -> ScriptedAction:
    if not isinstance(entry, Mapping):
        raise ScriptError(f"{path}: action {index} must be a JSON object")
    player = entry.get("player")
    if not isinstance(player, int) or isinstance(player, bool):
        raise ScriptError(f"{path}: action {index} must name a player, as a seat number")
    type_ = entry.get("type")
    if not isinstance(type_, str) or not type_:
        raise ScriptError(f"{path}: action {index} must name a type")
    params = entry.get("params", {})
    if not isinstance(params, Mapping):
        raise ScriptError(f"{path}: action {index} 'params' must be a JSON object")
    request_id = entry.get("request_id")
    if request_id is not None and not isinstance(request_id, str):
        raise ScriptError(f"{path}: action {index} 'request_id' must be a string")
    return ScriptedAction(player=player, type=type_, params=params, request_id=request_id)


def drive(run: GameRun, script: Script, *, allow_rejections: bool = False) -> list[ApplyResult]:
    """Play a script against a run, stopping at the first rejection unless allowed (FR-21.3)."""
    results: list[ApplyResult] = []
    for index, scripted in enumerate(script.actions):
        result = run.submit(
            Action(player=scripted.player, type=scripted.type, params=scripted.params),
            request_id=scripted.request_id,
        )
        if isinstance(result, Rejected) and not allow_rejections:
            raise ScriptError(
                f"action {index} ({scripted.type!r} by player {scripted.player}) was rejected: "
                f"{result.rejection.code.code}: {result.rejection.message}"
            )
        results.append(result)
    return results
