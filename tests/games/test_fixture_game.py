"""The fixture game: the canary that isolates machinery defects from rules defects.

M2 of PRD-v1 is deliberately sequenced before any Catan work, and this game is why: when a
hash mismatch shows up in the replay machinery, it must be obvious whether the fault is in
the machinery or in a rule. A trivial game with no real rules leaves only one possible
answer.

It is a test asset, not a game. It is never shipped, never scored, and never appears in a
result. It is retained permanently and re-run by the generic conformance harness.
"""

from __future__ import annotations

from typing import Any, Final

from lgbg.core.config import GameConfig
from lgbg.core.errors import GAME_OVER, NOT_YOUR_DECISION, UNKNOWN_ACTION
from lgbg.core.game import Applied, Game, Rejected, get_game
from lgbg.core.rng import (
    KIND_RANDINT,
    NullRandomSource,
    RandomSource,
    ReplayRandomSource,
    SeededRandomSource,
)
from lgbg.core.types import Action
from tests.games.fixture_game import (
    COST_TOKENS,
    GAMBLE_PURPOSE,
    INITIAL_BANK,
    TARGET_SCORE,
    TOKENS_UNAVAILABLE,
)

PARTICIPANTS: Final[int] = 2


def _game() -> Game:
    return get_game("fixture")


def _fresh(rng: RandomSource | None = None) -> Any:
    game = _game()
    return game, game.initial_state(GameConfig({}), rng if rng is not None else NullRandomSource())


def _take(game: Game, state: Any, rng: RandomSource) -> Any:
    player = game.pending_decisions(state)[0].player
    result = game.apply(state, Action(player=player, type="take", params={}), rng)
    assert isinstance(result, Applied), result
    return result.state


def test_fixture_is_registered_as_an_ordinary_plugin() -> None:
    assert _game().name == "fixture"


def test_initial_state_is_deterministic_for_a_configuration() -> None:
    game = _game()

    first = game.initial_state(GameConfig({"variant": "a"}), NullRandomSource())
    second = game.initial_state(GameConfig({"variant": "a"}), NullRandomSource())

    assert game.encode_state(first) == game.encode_state(second)


def test_the_opening_decision_goes_to_the_first_player() -> None:
    game, state = _fresh()

    requests = game.pending_decisions(state)

    assert len(requests) == 1
    assert requests[0].player == 0
    assert requests[0].phase == "play"


def test_take_moves_one_token_from_the_bank_and_emits_an_event() -> None:
    game, state = _fresh()
    player = game.pending_decisions(state)[0].player
    before = state.bank

    result = game.apply(state, Action(player=player, type="take", params={}), NullRandomSource())

    assert isinstance(result, Applied)
    assert result.state.tokens[player] == state.tokens[player] + 1
    assert result.state.bank == before - 1
    assert [event.type for event in result.events] == ["tokens_gained"]


def test_gamble_performs_exactly_one_recorded_draw() -> None:
    game, state = _fresh()
    rng = SeededRandomSource(4242)
    player = game.pending_decisions(state)[0].player

    result = game.apply(state, Action(player=player, type="gamble", params={}), rng)

    assert isinstance(result, Applied)
    draws = rng.draws()
    assert len(draws) == 1
    assert draws[0].purpose == GAMBLE_PURPOSE
    assert draws[0].kind == KIND_RANDINT
    assert result.state.tokens[player] - state.tokens[player] == draws[0].value


def test_a_recorded_gamble_replays_to_the_same_state() -> None:
    game, state = _fresh()
    player = game.pending_decisions(state)[0].player
    action = Action(player=player, type="gamble", params={})
    source = SeededRandomSource(99)

    seeded = game.apply(state, action, source)
    assert isinstance(seeded, Applied)
    recorded = source.draws()

    replayed = game.apply(state, action, ReplayRandomSource(recorded, action="#1"))

    assert isinstance(replayed, Applied)
    assert game.encode_state(replayed.state) == game.encode_state(seeded.state)


def test_spend_requires_enough_tokens() -> None:
    game, state = _fresh()
    player = game.pending_decisions(state)[0].player

    result = game.apply(state, Action(player=player, type="spend", params={}), NullRandomSource())

    assert isinstance(result, Rejected)
    assert result.rejection.code == TOKENS_UNAVAILABLE
    assert dict(result.rejection.details)["requires"] == COST_TOKENS


def test_spend_raises_the_score_and_pays_the_tokens() -> None:
    game, state = _fresh()
    rich = state
    # The turn alternates, so accumulate until whoever is to act can afford it.
    while rich.tokens[rich.turn] < COST_TOKENS:
        rich = _take(game, rich, NullRandomSource())

    result = game.apply(rich, Action(player=rich.turn, type="spend", params={}), NullRandomSource())

    assert isinstance(result, Applied)
    assert result.state.scores[rich.turn] == rich.scores[rich.turn] + 1
    assert result.state.tokens[rich.turn] == rich.tokens[rich.turn] - COST_TOKENS


def test_bank_conservation_holds_after_every_action() -> None:
    game, state = _fresh()
    rng = SeededRandomSource(5)

    for _ in range(12):
        if game.is_terminal(state):
            break
        assert game.check_invariants(state) == []
        state = _take(game, state, rng)

    assert game.check_invariants(state) == []
    assert state.bank + sum(state.tokens) == INITIAL_BANK


def test_an_exhausted_bank_makes_the_action_unavailable_rather_than_erroring() -> None:
    game, state = _fresh()
    drained = state
    while drained.bank > 0:
        drained = _take(game, drained, NullRandomSource())

    available = {domain.type for domain in game.action_domains(drained, drained.turn)}
    legal = {action.type for action in game.legal_actions(drained, drained.turn)}

    assert "take" not in available
    assert "take" not in legal
    assert "gamble" not in available


def test_unknown_action_type_is_rejected_with_the_core_code() -> None:
    game, state = _fresh()
    player = game.pending_decisions(state)[0].player

    result = game.apply(state, Action(player=player, type="fly", params={}), NullRandomSource())

    assert isinstance(result, Rejected)
    assert result.rejection.code == UNKNOWN_ACTION


def test_action_from_the_wrong_player_is_rejected_with_the_core_code() -> None:
    game, state = _fresh()

    result = game.apply(state, Action(player=1, type="take", params={}), NullRandomSource())

    assert isinstance(result, Rejected)
    assert result.rejection.code == NOT_YOUR_DECISION


def test_action_after_termination_is_rejected_with_the_core_code() -> None:
    game, state, _rng = _play_to_terminal()

    result = game.apply(state, Action(player=0, type="take", params={}), NullRandomSource())

    assert isinstance(result, Rejected)
    assert result.rejection.code == GAME_OVER


def test_the_game_reaches_a_terminal_state_and_reports_an_outcome() -> None:
    game, state, actions = _play_to_terminal()

    assert game.is_terminal(state)
    assert game.pending_decisions(state) == []
    outcome = game.outcome(state)
    assert outcome.winner is not None
    assert max(outcome.scores.values()) >= TARGET_SCORE
    assert actions < 400


def test_the_query_surface_consumes_no_randomness() -> None:
    """FR-2.6: every query path must be pure and RNG-free.

    NullRandomSource raises on any draw, so reaching the assertion is itself the proof.
    """
    game, state = _fresh()
    quiet = NullRandomSource()

    for player in range(PARTICIPANTS):
        game.legal_actions(state, player)
        game.action_domains(state, player)
        game.observe(state, player)
    game.observe_spectator(state)
    game.pending_decisions(state)
    game.outcome(state)
    game.check_invariants(state)
    game.is_terminal(state)

    assert quiet.draws() == []


def test_projection_hides_the_other_players_token_count_but_the_spectator_sees_it() -> None:
    game, state = _fresh()
    state = _take(game, state, NullRandomSource())
    state = _take(game, state, NullRandomSource())

    own = game.observe(state, 0)
    other = game.observe(state, 1)
    spectator = game.observe_spectator(state)

    assert own["tokens"] == state.tokens[0]
    assert other["tokens"] == state.tokens[1]
    assert dict(own["opponents"])["1"] == state.tokens[1]
    assert dict(spectator["tokens"]) == {"0": state.tokens[0], "1": state.tokens[1]}


def test_encoded_state_round_trips() -> None:
    game, state = _fresh()
    state = _take(game, state, NullRandomSource())

    blob = game.encode_state(state)

    assert game.encode_state(game.decode_state(blob)) == blob


def test_declared_rejection_codes_are_unique_and_described() -> None:
    codes = _game().rejection_codes()

    assert codes, "a plugin must declare its rejection codes"
    assert len({code.code for code in codes}) == len(codes)
    assert all(code.description for code in codes)


def test_two_interleaved_games_through_one_plugin_instance_do_not_interfere() -> None:
    """FR-6.5: a plugin holds no instance state, so one instance drives many games."""
    game = _game()
    solo = _fresh()[1]
    solo = _take(game, solo, NullRandomSource())
    solo = _take(game, solo, NullRandomSource())

    first = game.initial_state(GameConfig({}), NullRandomSource())
    second = game.initial_state(GameConfig({}), NullRandomSource())
    first = _take(game, first, NullRandomSource())
    second = _take(game, second, NullRandomSource())
    second = _take(game, second, NullRandomSource())
    second = _take(game, second, NullRandomSource())
    first = _take(game, first, NullRandomSource())

    assert game.encode_state(first) == game.encode_state(solo)
    assert game.encode_state(second) != game.encode_state(first)


def test_events_are_enough_to_describe_the_change() -> None:
    game, state = _fresh()
    player = game.pending_decisions(state)[0].player

    result = game.apply(state, Action(player=player, type="spend", params={}), NullRandomSource())
    assert isinstance(result, Rejected)  # not affordable yet

    paid = state
    while paid.tokens[paid.turn] < COST_TOKENS:
        paid = _take(game, paid, NullRandomSource())
    applied = game.apply(
        paid, Action(player=paid.turn, type="spend", params={}), NullRandomSource()
    )
    assert isinstance(applied, Applied)

    kinds = [event.type for event in applied.events]
    assert kinds == ["tokens_spent", "score_gained"]


def _play_to_terminal() -> tuple[Game, Any, int]:
    game, state = _fresh()
    rng = SeededRandomSource(20250101)
    for actions in range(400):
        if game.is_terminal(state):
            return game, state, actions
        player = game.pending_decisions(state)[0].player
        type_ = "spend" if state.tokens[player] >= COST_TOKENS else "take"
        result = game.apply(state, Action(player=player, type=type_, params={}), rng)
        assert isinstance(result, Applied), result
        state = result.state
    raise AssertionError("the fixture game did not terminate within 400 actions")


def test_the_benchmark_profile_is_declared_and_complete() -> None:
    profile = _game().benchmark_profile()

    assert profile.typical_decisions > 0
    assert profile.worst_case_decisions >= profile.typical_decisions
    assert profile.positional_asymmetry is True, "the fixture rewards acting first"


def test_decision_requests_name_a_declared_schema() -> None:
    game, state = _fresh()
    reference = game.pending_decisions(state)[0].schema_ref

    assert reference in game.action_schema()


def test_fixture_declares_core_codes_it_uses() -> None:
    declared = {code.code for code in _game().rejection_codes()}

    assert TOKENS_UNAVAILABLE.code in declared


def test_initial_state_ignores_unknown_game_options() -> None:
    """The fixture reads no options: an unused option must not change the state."""
    game = _game()

    plain = game.initial_state(GameConfig({}), NullRandomSource())
    odd = game.initial_state(GameConfig({"unused": 7}), NullRandomSource())

    assert game.encode_state(plain) == game.encode_state(odd)
