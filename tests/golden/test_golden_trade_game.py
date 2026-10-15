"""Golden game 5: trades between players (K-053; PRD-v1 SC-1).

The four earlier fixtures never trade with each other - the bank is the only counterparty in the
base game as they play it. This one plays the whole game with the offer in it: forty-seven offers,
every one of them answered by every eligible seat and every one of them taken, twenty of them by
more than one seat at once, so the offerer had to choose. The base game of PRD-v1 section 8 is
exercised end to end by the five fixtures together, and this is the one that pins the trade.

The fixture is committed in two halves, both deterministic: the scripted action file is the input,
the god log is what the engine produced. The test plays the first and compares it to the second.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from lgbg.adapters.cli.script import drive, load_script
from lgbg.core.game import get_game
from lgbg.core.log import GameLogReader
from lgbg.core.replay import replay, verify
from lgbg.core.run import GameRun
from lgbg.games.catan import phases
from lgbg.games.catan.notation import render
from lgbg.games.catan.state import RESOURCE_ORDER, RESPONSE_ACCEPT, Phase

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
SCRIPT: Final[Path] = REPO_ROOT / "tests" / "fixtures" / "catan" / "trade_game.json"
RECORD: Final[Path] = REPO_ROOT / "tests" / "golden" / "catan" / "trade_game.god.jsonl"

INITIAL_STATE_HASH: Final[str] = "3b2925db696ca530"
FINAL_STATE_HASH: Final[str] = "385f4ac1f762534d"
ACTIONS: Final[int] = 598
OFFERS: Final[int] = 47
ANSWERS: Final[int] = 140
ACCEPTS: Final[int] = 74
DECLINES: Final[int] = 66
CHOICES: Final[int] = 20
SEATS: Final[int] = 4
TARGET: Final[int] = 10


def _log() -> Any:
    return GameLogReader(RECORD).read()


def _events(name: str) -> list[dict[str, Any]]:
    return [
        dict(event.payload)
        for record in _log().actions
        for event in record.events
        if event.type == name
    ]


def _states() -> list[Any]:
    log = _log()
    return replay(log, get_game(log.header.game)).states


def test_the_committed_record_replays_with_every_hash_verified() -> None:
    """SC-1: every intermediate state reconstructed, every hash asserted."""
    log = _log()
    game = get_game(log.header.game)

    report = verify(log, game)

    assert report.actions == ACTIONS
    assert report.rejections == 0
    assert log.header.initial_state_hash == INITIAL_STATE_HASH
    assert report.terminal_hash == FINAL_STATE_HASH
    assert replay(log, game).states[-1].phase is Phase.TERMINAL


def test_the_fixture_contains_offers_answers_and_completed_trades() -> None:
    """A fixture that stopped trading would still replay perfectly, so assert that it trades."""
    offered = _events("trade_offered")
    answers = _events("trade_responded")
    completed = _events("trade_completed")

    assert len(offered) == OFFERS
    assert len(answers) == ANSWERS
    assert len(completed) == OFFERS, "every offer in this fixture was taken"
    assert sum(1 for answer in answers if answer["response"] == "accept") == ACCEPTS
    assert sum(1 for answer in answers if answer["response"] == "decline") == DECLINES
    for trade in completed:
        assert trade["offerer"] != trade["partner"]
        assert set(trade["give"]) <= {resource.value for resource in RESOURCE_ORDER}
        assert set(trade["want"]) <= {resource.value for resource in RESOURCE_ORDER}


def test_the_offerer_chose_among_several_acceptors() -> None:
    """FR-14.5 in the record: the engine never picks, so choosing is an action of its own."""
    states = _states()
    choices = [
        record
        for record in _log().actions
        if record.action is not None and record.action.type == phases.CHOOSE_PARTNER
    ]

    assert len(choices) == CHOICES
    for record in choices:
        partner = record.action.params["partner"]
        before = states[record.seq]
        assert before.offer is not None, "a choice needs an offer that is still open"
        assert before.responses[partner] == RESPONSE_ACCEPT, "a partner who never accepted"
        assert record.action.player == before.offer.offerer, "and only the offerer chooses"


def test_every_trade_moves_exactly_what_it_announced() -> None:
    """FR-14.8 read off the record, move by move: the announced cards, and nothing else."""
    states = _states()
    seen = 0

    for record in _log().actions:
        for event in record.events:
            if event.type != "trade_completed":
                continue
            payload = dict(event.payload)
            offerer, partner = int(payload["offerer"]), int(payload["partner"])
            before, after = states[record.seq], states[record.seq + 1]
            for index, resource in enumerate(RESOURCE_ORDER):
                gave = int(payload["give"].get(resource.value, 0))
                wanted = int(payload["want"].get(resource.value, 0))
                gained = after.hands[offerer][index] - before.hands[offerer][index]
                lost = after.hands[partner][index] - before.hands[partner][index]
                assert gained == wanted - gave, f"{resource.value} at the offerer"
                assert lost == gave - wanted, f"{resource.value} at the partner"
                assert after.bank[index] == before.bank[index], "no trade with the bank happened"
                for seat in range(SEATS):
                    if seat not in (offerer, partner):
                        assert after.hands[seat][index] == before.hands[seat][index]
            assert after.offer is None, "the offer is over once the cards have moved"
            seen += 1

    assert seen == OFFERS


def test_every_intermediate_state_conserves_every_resource() -> None:
    """The trade's own invariant: nineteen of each card, in the bank and in the hands."""
    game = get_game("catan")
    states = _states()

    assert len(states) == ACTIONS + 1
    for state in states:
        assert game.check_invariants(state) == []


def test_playing_the_committed_script_reproduces_the_record_byte_for_byte(tmp_path: Path) -> None:
    """The regression net: a rule of the trade changing moves a hash, and this fails."""
    game = get_game("catan")
    script = load_script(SCRIPT)
    run = GameRun(game, script.config, game_id="g-0005", directory=tmp_path)

    drive(run, script)
    run.finish()

    produced = tmp_path / "games" / "g-0005.god.jsonl"
    assert produced.read_bytes() == RECORD.read_bytes()


def test_the_two_halves_of_the_fixture_agree() -> None:
    script = load_script(SCRIPT)
    actions = _log().actions

    assert len(script.actions) == len(actions) == ACTIONS
    for scripted, recorded in zip(script.actions, actions, strict=True):
        assert scripted.player == recorded.player
        assert scripted.type == recorded.action.type
        assert dict(scripted.params) == dict(recorded.action.params)


def test_every_intermediate_state_renders_and_keeps_the_answers_private() -> None:
    """FR-14.4 and FR-9.6 in the states: the offer is public, the answer tally is not."""
    log = _log()
    game = get_game(log.header.game)
    replayed = replay(log, game)
    offers_seen = 0

    for index, _record in enumerate(log.actions):
        state = replayed.states[index + 1]
        for seat in range(SEATS):
            text = render(game.observe(state, seat))
            assert "offer:" in text
            assert "responses" not in text
            assert "hands" not in text
            assert "dev_cards" not in text
        if state.offer is not None:
            offers_seen += 1
            announced = render(game.observe(state, 0))
            assert f"p{state.offer.offerer} gives " in announced

    assert offers_seen > 0, "the fixture must show an open offer to somebody"


def test_the_record_is_deterministic_text() -> None:
    raw = RECORD.read_bytes()

    assert b"\r" not in raw
    text = raw.decode("utf-8")
    for forbidden in ('"at":', '"host":', '"pid":'):
        assert forbidden not in text
    assert raw.endswith(b"\n")
    script = SCRIPT.read_bytes()
    assert b"\r" not in script, "the scripted half is LF only too"
    assert script.endswith(b"\n")


def test_the_record_carries_the_versions_it_was_produced_under() -> None:
    header = _log().header

    assert header.game == "catan"
    assert header.rules_version == "catan-rules-6"
    assert header.schema_version == "catan-actions-1"
    assert header.config["board"] == "fixed:standard_a"
    assert header.config["interaction_protocol"] == "decline_only"
    assert json.dumps(dict(header.prompt_hashes)) == "{}"


def test_the_fixture_ends_the_way_the_rules_say_it_does() -> None:
    log = _log()
    terminal = log.terminal
    game = get_game(log.header.game)
    final = replay(log, game).states[-1]

    assert terminal.total_actions == ACTIONS
    assert terminal.rejections == 0
    assert terminal.winner == 0
    assert int(terminal.final_scores["0"]) >= TARGET
    assert game.outcome(final).winner == terminal.winner
