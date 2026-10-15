"""The phase machine and the decision queue (PRD-v1 FR-9.1 to FR-9.4; ARCHITECTURE.md 5.6, 7.7).

A turn counter is not a sufficient primitive. Decisions are addressed to particular players,
several can be open at once, and some belong to players who are out of turn - a forced discard,
an answer to an offer. An engine modelled as "whose turn is it" cannot express those without
special cases, and the special cases are where rule bugs live.

So phases do not drive control flow here: they *produce* decision requests, and a phase ends
when its request set is empty. The tests below hold the machine to three things: that several
requests can be open at once, that their order is seat order and does not depend on how the
state was reached, and that entering a phase says so in the record.
"""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType
from typing import Final

import pytest

from lgbg.core.rng import SeededRandomSource
from lgbg.core.types import PHASE_STARTED_EVENT
from lgbg.games.catan.board.generation import load_board
from lgbg.games.catan.phases import (
    DISCARD_RESOURCES,
    PHASE_RULES,
    PhaseError,
    PhaseRule,
    advance,
    pending_decisions,
    resolution_order,
)
from lgbg.games.catan.state import (
    NO_OWNER,
    CatanState,
    Phase,
    initial_state,
)

PLAYERS: Final[int] = 4


def _opening() -> CatanState:
    return initial_state(load_board("standard_a"), players=PLAYERS, rng=SeededRandomSource(11))


def _settled(state: CatanState, *, settlements: int, roads: int) -> CatanState:
    """A setup state with a given number of pieces down, which is what closes a phase."""
    placed = state.placed
    return replace(
        state,
        placed=replace(
            placed,
            settlements=tuple(
                0 if site < settlements else NO_OWNER for site in range(len(placed.settlements))
            ),
            roads=tuple(0 if edge < roads else NO_OWNER for edge in range(len(placed.roads))),
        ),
    )


def test_the_opening_state_asks_the_first_player_for_one_decision() -> None:
    state = _opening()

    requests = pending_decisions(state)

    assert len(requests) == 1
    assert requests[0].player == 0
    assert requests[0].phase == Phase.SETUP_ROUND_1.value
    assert requests[0].kind == "place_settlement"


def test_every_phase_the_machine_can_enter_produces_requests() -> None:
    """A phase with no rule would be a turn nobody can take, so the table must cover them."""
    for phase in (Phase.SETUP_ROUND_1, Phase.SETUP_ROUND_1, Phase.TURN_PRODUCTION, Phase.DISCARD):
        assert phase in PHASE_RULES, f"{phase.value} has no rule"


def test_several_decisions_can_be_open_at_once() -> None:
    """FR-9.1: a phase may have zero, one or many open requests - and several is the norm."""
    state = replace(
        _opening(),
        phase=Phase.DISCARD,
        discards_pending=(2, 0, 1, 0),
    )

    requests = pending_decisions(state)

    assert [request.player for request in requests] == [0, 2]
    assert [request.kind for request in requests] == [DISCARD_RESOURCES] * 2
    assert [dict(request.context)["must_discard"] for request in requests] == [2, 1]


def test_open_requests_resolve_in_seat_order() -> None:
    """FR-9.3: seat order within a phase, so a record made concurrently matches one made in turn."""
    state = replace(_opening(), phase=Phase.DISCARD, discards_pending=(0, 1, 1, 1))

    requests = pending_decisions(state)

    assert [request.player for request in requests] == [1, 2, 3]
    assert requests == resolution_order(list(reversed(requests)))


def test_the_order_does_not_depend_on_how_the_state_was_reached() -> None:
    """Arrival order is not a thing the machine can see, and not a thing it may depend on."""
    first = replace(_opening(), phase=Phase.DISCARD, discards_pending=(1, 1, 0, 1))
    second = replace(first, phase_index=97, round=12, turn=3)

    assert [request.player for request in pending_decisions(first)] == [0, 1, 3]
    assert [request.player for request in pending_decisions(second)] == [0, 1, 3]


def test_a_phase_that_still_has_requests_does_not_advance() -> None:
    state = _opening()

    same, events = advance(state)

    assert same == state
    assert events == []


def test_a_closed_phase_advances_and_says_so_in_the_record() -> None:
    """FR-9.4: every transition emits a phase_started event."""
    state = _settled(_opening(), settlements=PLAYERS, roads=PLAYERS)

    advanced, events = advance(state)

    assert advanced.phase is Phase.SETUP_ROUND_2
    assert [event.type for event in events] == [PHASE_STARTED_EVENT]
    assert dict(events[0].payload) == {
        "index": state.phase_index + 1,
        "phase": Phase.SETUP_ROUND_2.value,
        "turn": state.turn,
    }


def test_the_draft_stays_in_one_phase_while_it_has_a_step_left() -> None:
    """RULES.md 4.4: round one is one phase, ended by all eight steps being done."""
    state = _settled(_opening(), settlements=1, roads=1)

    same, events = advance(state)

    assert same.phase is Phase.SETUP_ROUND_1
    assert events == []


def test_the_setup_ends_into_the_production_phase_once_everybody_has_placed_twice() -> None:
    state = replace(
        _settled(_opening(), settlements=PLAYERS * 2, roads=PLAYERS * 2),
        phase=Phase.SETUP_ROUND_2,
    )

    advanced, _events = advance(state)

    assert advanced.phase is Phase.TURN_PRODUCTION
    request = pending_decisions(advanced)[0]
    assert request.kind == "take_turn"
    assert request.schema_ref == "roll_dice", "the roll is what the turn opens with"
    assert request.player == advanced.turn


def test_each_phase_instance_has_its_own_decision_identifiers() -> None:
    """Decision ids come from the state, so replay derives the same identifiers."""
    first = pending_decisions(_opening())
    later = pending_decisions(
        replace(
            _settled(_opening(), settlements=1, roads=0), phase_index=4, phase=Phase.SETUP_ROUND_1
        )
    )

    assert first[0].request_id != later[0].request_id
    assert first[0].request_id == f"d{_opening().phase_index}.0"


def _without_a_rule_for(phase: Phase, monkeypatch: pytest.MonkeyPatch) -> None:
    """Take a phase out of the machine's table: what a card that has not landed looks like.

    Every phase of RULES.md 4.4 has a rule, so the condition these tests are about cannot be
    found in the game any more; it is produced. The table is what the machine consults, and a
    phase missing from it is exactly the case the loud failure exists for.
    """
    import lgbg.games.catan.phases as machine

    implemented = dict(PHASE_RULES)
    del implemented[phase]
    monkeypatch.setattr(machine, "PHASE_RULES", MappingProxyType(implemented))


def test_an_unimplemented_phase_is_reported_rather_than_answered_with_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A phase whose card has not landed must fail loudly, not silently stall the game."""
    _without_a_rule_for(Phase.TRADE_RESPONSE, monkeypatch)
    state = replace(_opening(), phase=Phase.TRADE_RESPONSE)

    with pytest.raises(PhaseError, match="trade_response"):
        pending_decisions(state)


def test_a_phase_that_closes_the_moment_it_opens_closes_in_the_same_action() -> None:
    """A seven nobody has to answer is over before it begins, and the game moves on with it."""
    state = replace(_opening(), phase=Phase.TURN_PRODUCTION, dice=(3, 4), turn=0)

    advanced, events = advance(state)

    assert advanced.phase is Phase.ROBBER
    assert [dict(event.payload)["phase"] for event in events] == ["discard", "robber"]


def test_a_closed_phase_whose_transition_has_not_landed_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A phase with no requests and nowhere to go is where the machine waits, loudly."""
    import lgbg.games.catan.phases as machine

    unfinished = dict(PHASE_RULES)
    rule = unfinished[Phase.TRADE_RESPONSE]
    unfinished[Phase.TRADE_RESPONSE] = PhaseRule(rule.requests, None)
    monkeypatch.setattr(machine, "PHASE_RULES", MappingProxyType(unfinished))
    state = replace(_opening(), phase=Phase.TRADE_RESPONSE)

    with pytest.raises(PhaseError, match="trade_response"):
        advance(state)


def test_the_finished_phase_never_advances() -> None:
    """OVER has no requests and nowhere to go; asking is not an error, it is the end."""
    state = replace(_opening(), phase=Phase.TERMINAL)

    same, events = advance(state)

    assert same == state
    assert events == []


def test_requests_carry_a_declared_schema_reference() -> None:
    """The schema reference is what the renderer and the tool generator key on (FR-18)."""
    for state in (
        _opening(),
        replace(_opening(), phase=Phase.DISCARD, discards_pending=(1, 0, 0, 0)),
    ):
        for request in pending_decisions(state):
            assert request.schema_ref
            assert request.kind
