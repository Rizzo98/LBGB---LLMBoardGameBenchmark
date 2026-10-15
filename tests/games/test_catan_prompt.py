"""The shared game prompt (PRD-v1 FR-19.1 to FR-19.4; kanban card K-059).

The prompt is an artefact of the benchmark, not documentation for people: every player of every
Catan game is handed the same file, so what it contains is an experimental variable. Three things
are asserted here - that it exists and hashes to a pinned value, that it documents the rules, the
notation and the action semantics, and that it contains no advice.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.game import get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.prompts import digest
from lgbg.core.run import GameRun
from lgbg.games.catan.game import PROMPTS, prompt_hashes

GAME: Final[Any] = get_game("catan")
PINNED: Final[str] = "9f7828c89056096439c48c183607824af5dc40d7de3d2438402db69137d4b4a0"
"""The hash of the prompt as committed: an edit moves it, and this line has to move with it."""

ACTIONS: Final[tuple[str, ...]] = (
    "build_city",
    "build_road",
    "build_settlement",
    "buy_dev_card",
    "cancel_trade",
    "choose_partner",
    "choose_robber_victim",
    "discard_resources",
    "end_turn",
    "maritime_trade",
    "move_robber",
    "offer_trade",
    "place_free_road",
    "place_road",
    "place_settlement",
    "play_dev_card",
    "respond_trade",
    "roll_dice",
)

ADVICE: Final[tuple[str, ...]] = (
    "you should",
    "we recommend",
    "we suggest",
    "it is best to",
    "the best move",
    "a good idea",
    "try to",
    "strategy",
    "tip:",
)
"""Phrases only advice uses: the file may describe what is legal, never what is wise."""


def _prompt() -> str:
    return PROMPTS["game"].read_text(encoding="utf-8")


def test_the_prompt_exists_and_is_the_one_the_hash_pins() -> None:
    """FR-19.1 and FR-19.3: the artefact, and the hash a record would carry."""
    text = _prompt()

    assert len(text) > 2000, "a prompt that fits in a paragraph documents nothing"
    assert digest(text) == PINNED
    assert prompt_hashes() == {"game": PINNED}


def test_the_prompt_documents_the_rules_the_notation_and_every_action() -> None:
    """FR-19.1: what a player has to know before the first decision."""
    text = _prompt()

    for kind in ("hex", "vertex", "edge", "harbour"):
        assert kind in text, kind
    for action in ACTIONS:
        assert f"`{action}`" in text, f"{action} is not documented"
    assert "```json" in text, "worked examples, not just prose"


def test_the_prompt_contains_no_advice() -> None:
    """FR-19.2: the file says what is legal, and never what is worth doing."""
    text = _prompt().lower()

    for phrase in ADVICE:
        assert phrase not in text, f"the prompt advises: {phrase!r}"


def _played(directory: Path, hashes: dict[str, str]) -> Any:
    config = RunConfig(
        seed=20260701,
        players=4,
        interaction_protocol="decline_only",
        game_config=GameConfig({"board": "fixed:standard_a"}),
        prompt_hashes=hashes,
    )
    run = GameRun(GAME, config, game_id="g-prompt", directory=directory)
    run.finish()
    return GameLogReader(god_log_path(directory, "g-prompt")).read().header


def test_a_run_that_used_the_prompt_records_its_hash(tmp_path: Path) -> None:
    """FR-19.3: the header says which prompt the players were given."""
    used = _played(tmp_path, prompt_hashes())
    none = _played(tmp_path / "bare", {})

    assert dict(used.prompt_hashes) == {"game": PINNED}
    assert dict(none.prompt_hashes) == {}, "a scripted run is given no prompt, and says so"
