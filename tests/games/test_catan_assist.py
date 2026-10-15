"""What each assist level shows a Catan player (FR-17.3 to FR-17.5; ARCHITECTURE.md 9).

The three levels are asserted against the same position, and each assertion is a *subtraction*
or a *count* rather than a description. L0 is the game's own rendering of the observation and
nothing else, so a model that is given it has to build the action from the rules. L1 names each
action type once, with its cost and the permitted values of each parameter, and never the cross
product - which is the whole difference between describing a choice and making it. L2 is the
enumeration the surface promises.

One refusal is followed all the way through as well, because that is where enumeration leaks if
nobody looks: the text a player is handed at the hardest level must not contain the alternatives,
while the *record* keeps them at every level, which is what makes the levels comparable.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

from lgbg.adapters.cli.script import drive, load_script
from lgbg.core.assist import render_decision
from lgbg.core.canonical import to_canonical_json
from lgbg.core.config import AssistLevel, GameConfig, RejectionDetail, RunConfig
from lgbg.core.game import Rejected, get_game
from lgbg.core.log import god_log_path
from lgbg.core.rng import SeededRandomSource
from lgbg.core.run import GameRun
from lgbg.core.types import Action
from lgbg.games.catan import phases
from lgbg.games.catan.state import CatanState, Phase
from tests.games.catan_boards import holding, layout

GAME: Final[Any] = get_game("catan")
PLAYERS: Final[int] = 4
SEED: Final[int] = 20260501
LEVELS: Final[tuple[AssistLevel, ...]] = (AssistLevel.L0, AssistLevel.L1, AssistLevel.L2)


def _opening() -> CatanState:
    state: CatanState = GAME.initial_state(
        GameConfig({"board": "fixed:standard_a", "players": PLAYERS}), SeededRandomSource(SEED)
    )
    return state


def _turn() -> CatanState:
    """The action phase, seat 0 to act, with cards in every hand and a trade on offer."""
    state = layout(_opening())
    for seat, cards in enumerate(({"wood": 2, "ore": 1}, {"wool": 1}, {"wheat": 2}, {"brick": 1})):
        state = holding(state, seat, **cards)
    return state


def _text(state: CatanState, level: AssistLevel, seat: int = 0) -> str:
    return render_decision(GAME, state, seat, assist=level)


def _lines(text: str, kind: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith(f"  {kind}")]


FIXTURE: Final[Path] = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "catan" / "trade_game.json"
)
"""The scripted half of golden game 5: 598 actions, every phase, and the trades."""


def _driven(tmp_path: Path, level: AssistLevel, tier: RejectionDetail | None = None) -> list[str]:
    """Drive the committed script at one level, and return the record as lines."""
    script = load_script(FIXTURE)
    config = RunConfig(
        seed=script.config.seed,
        players=script.config.players,
        assist=level,
        rejection_detail=tier,
        interaction_protocol=script.config.interaction_protocol,
        game_config=script.config.game_config,
    )
    directory = tmp_path / f"{level.value}-{tier.value if tier else 'default'}"
    run = GameRun(GAME, config, game_id="g-0005", directory=directory)
    drive(run, script)
    run.finish()
    text = god_log_path(directory, "g-0005").read_text(encoding="utf-8")
    return text.splitlines()


def _without_the_level(lines: list[str]) -> list[str]:
    """The record with the two fields the level determines blanked out of its header."""
    header = json.loads(lines[0])
    config = dict(header["config"])
    config["assist"] = "?"
    config["rejection_detail"] = "?"
    header["config"] = config
    return [to_canonical_json(header), *lines[1:]]


def test_the_same_script_at_three_levels_produces_one_record(tmp_path: Path) -> None:
    """SC-8 and FR-17.2: 598 actions driven three times, and one set of bytes."""
    records = {level: _driven(tmp_path, level) for level in LEVELS}
    lengths = {level: len(record) for level, record in records.items()}

    assert len(set(lengths.values())) == 1, f"different lengths: {lengths}"
    assert lengths[AssistLevel.L0] > 500, "the fixture must play a game"
    for level in LEVELS:
        assert records[level][1:] == records[AssistLevel.L0][1:]
    for level in LEVELS:
        assert _without_the_level(records[level]) == _without_the_level(records[AssistLevel.L0])


def test_the_header_is_the_only_place_the_level_appears(tmp_path: Path) -> None:
    """The difference is one line, and inside it two fields - not the whole header."""
    honest = json.loads(_driven(tmp_path, AssistLevel.L0)[0])
    told = json.loads(_driven(tmp_path, AssistLevel.L2)[0])

    assert honest["config"]["assist"] == "L0"
    assert told["config"]["assist"] == "L2"
    assert honest["config"]["rejection_detail"] == "minimal", "the tier follows the level"
    assert told["config"]["rejection_detail"] == "full"
    for key, value in honest.items():
        if key == "config":
            continue
        assert value == told[key], f"{key} moved with the level"
    moved = {key for key in honest["config"] if honest["config"][key] != told["config"][key]}
    assert moved == {"assist", "rejection_detail"}, "and nothing else in the header moved"


def test_the_tier_can_be_overridden_without_touching_the_record(tmp_path: Path) -> None:
    """FR-5.3 and ARCHITECTURE 9.4: enumeration at one tier, errors at another.

    The two fields are separate on purpose - a run that enumerates actions while refusing them
    in one word is a condition somebody will want to measure - and neither of them reaches the
    engine, which is what this pair of runs shows.
    """
    bare = _driven(tmp_path, AssistLevel.L0, RejectionDetail.FULL)
    rich = _driven(tmp_path, AssistLevel.L2, RejectionDetail.MINIMAL)

    assert json.loads(bare[0])["config"]["rejection_detail"] == "full"
    assert json.loads(rich[0])["config"]["rejection_detail"] == "minimal"
    assert bare[1:] == rich[1:]
    assert _without_the_level(bare) == _without_the_level(rich)


def test_l0_is_the_observation_and_nothing_else() -> None:
    """FR-17.3 and ARCHITECTURE 9.2: raw observation, and no enumeration of any kind."""
    state = _turn()
    text = _text(state, AssistLevel.L0)

    assert text == GAME.render(GAME.observe(state, 0))
    assert "asking" not in text
    assert "cost=" not in text
    for action in GAME.legal_actions(state, 0):
        assert action.type not in text, f"{action.type} is an act, not an observation"


def test_l1_names_each_action_type_once_with_its_cost_and_its_domains() -> None:
    """FR-17.4: types, costs and parameter domains, without the cross product."""
    state = _turn()
    text = _text(state, AssistLevel.L1)
    offered = {action.type for action in GAME.legal_actions(state, 0)}

    for name in offered:
        assert len(_lines(text, name)) == 1, f"{name} is described once, not enumerated"
    assert "cost=" in text
    assert "one of" in _lines(text, phases.OFFER_TRADE)[0], "a parameter shows its domain"
    assert len(_lines(text, phases.OFFER_TRADE)) == 1


def test_l2_lists_the_actions_the_domains_only_describe() -> None:
    """FR-17.5: the enumeration, one action to a line."""
    state = _turn()
    text = _text(state, AssistLevel.L2)
    enumerated = GAME.legal_actions(state, 0)
    written = text.splitlines()

    assert len(written) > len(_text(state, AssistLevel.L1).splitlines())
    for action in enumerated:
        assert f"  {_independent_line(action)}" in written, action
    offers = [action for action in enumerated if action.type == phases.OFFER_TRADE]
    assert len(_lines(text, phases.OFFER_TRADE)) == len(offers)


def test_the_three_levels_show_one_observation() -> None:
    """The level adds to what a player is shown; it never changes the position itself."""
    state = _turn()
    bare = _text(state, AssistLevel.L0)

    for level in (AssistLevel.L1, AssistLevel.L2):
        assert _text(state, level).startswith(bare)
    asked = GAME.pending_decisions(state)[0]
    assert f"{asked.request_id} {asked.kind}" in _text(state, AssistLevel.L1)


def _independent_line(action: Action) -> str:
    """The same line written out again here, so the module is not its own witness."""
    given = " ".join(
        f"{name}={to_canonical_json(value)}" for name, value in sorted(action.params.items())
    )
    return f"{action.type} {given}".rstrip()


def _discarding() -> CatanState:
    """A seven seat 0 must answer: nine cards in hand, four of them owed to the bank."""
    state = holding(_turn(), 0, wood=3, ore=3, wool=3)
    return replace(state, phase=Phase.DISCARD, discards_pending=(4, 0, 0, 0))


def test_a_discard_is_described_as_ranges_and_enumerated_as_compositions() -> None:
    """The cross product in the open: five counts whose sum the domain cannot express."""
    state = _discarding()
    described = _lines(_text(state, AssistLevel.L1), phases.DISCARD_RESOURCES)
    enumerated = _lines(_text(state, AssistLevel.L2), phases.DISCARD_RESOURCES)

    assert len(described) == 1, "one line for the type"
    assert "0..3" in described[0], "each count is a range, not a value"
    assert len(enumerated) == len(GAME.legal_actions(state, 0))
    assert len(enumerated) > len(described)
    assert all("0.." not in line for line in enumerated), "a composition is a composition"


def _recorded(tmp_path: Path, level: AssistLevel) -> list[str]:
    """One run per level, each recording the same refused attempt."""
    config = RunConfig(
        seed=SEED,
        players=PLAYERS,
        assist=level,
        interaction_protocol="decline_only",
        game_config=GameConfig({"board": "fixed:standard_a"}),
    )
    directory = tmp_path / level.value
    run = GameRun(GAME, config, game_id="g-assist", directory=directory)
    refused = run.submit(Action(player=0, type="teleport", params={}))
    assert isinstance(refused, Rejected)
    run.finish()
    text = god_log_path(directory, "g-assist").read_text(encoding="utf-8")
    return text.splitlines()


def _header_without_the_level(header: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(header)
    config = dict(cleaned["config"])
    config["assist"] = "?"
    config["rejection_detail"] = "?"
    cleaned["config"] = config
    return cleaned


def test_the_record_keeps_the_refusal_in_full_whatever_the_tier_is(tmp_path: Path) -> None:
    """FR-17.2 in the small: the level changes what is told, never what is recorded."""
    recorded = {level: _recorded(tmp_path, level) for level in LEVELS}
    actions = {
        level: [line for line in lines if '"t":"action"' in line]
        for level, lines in recorded.items()
    }
    headers = {level: json.loads(lines[0]) for level, lines in recorded.items()}

    assert actions[AssistLevel.L0] == actions[AssistLevel.L1] == actions[AssistLevel.L2]
    for level, kept in actions.items():
        assert '"known"' in kept[0], f"the record lost the details at {level}"
        assert "UNKNOWN_ACTION" in kept[0]

    reference = _header_without_the_level(headers[AssistLevel.L0])
    for header in headers.values():
        assert _header_without_the_level(header) == reference
