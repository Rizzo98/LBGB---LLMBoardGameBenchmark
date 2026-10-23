"""The session facade: one authority over mutable state (PRD-v2 FR-1.1 to FR-1.6, NFR-6).

Every surface v2 adds - the MCP server, the HTTP host, the runner, the CLI - is a transport over
this one component. That is the whole design, so what is asserted here is what the design claims:

- the operations the v1 engine already declares, and nothing else. A facade with a game-specific
  operation would be a facade that has to change when a game arrives, which is the boundary the
  plugin system exists to hold;
- one code path for two games of very different shapes, driven by the same test body;
- a rejection is a rejection, not a queue: an action for a player with no open decision comes back
  with the core's own code, moves nothing, and leaves the session usable;
- concurrency. Sessions advance in parallel without interfering - proved by identical hash chains,
  not by absence of exceptions - and one session may have several open decisions answered at once.

The last one is the reason the facade is the only mutable thing: a lock per session means two games
never wait on each other, and a surface above can hold a decision while another thread answers a
different one.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Final

import pytest

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.core.canonical import to_canonical_json
from lgbg.core.config import AssistLevel, RunConfig
from lgbg.core.errors import NOT_YOUR_DECISION, UNKNOWN_ACTION
from lgbg.core.game import Applied, ApplyResult, Rejected, get_game
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.core.replay import verify
from lgbg.core.types import Action, GameId
from lgbg.host.facade import (
    PUBLIC_OPERATIONS,
    SessionClosedError,
    SessionExistsError,
    SessionFacade,
    SessionNotFoundError,
)
from tests.games.fixture_game import FixtureGame  # noqa: F401 - importing registers the game

TESTS: Final[Path] = Path(__file__).resolve().parents[1]
CATAN_SCRIPTS: Final[Path] = TESTS / "fixtures" / "catan"

FIXTURE_SEATS: Final[int] = 2


def fixture_config(*, assist: AssistLevel = AssistLevel.L1, seed: int = 1) -> RunConfig:
    """The fixture game's run configuration: two seats, one protocol, a seed and an assist level."""
    return RunConfig(
        seed=seed, players=FIXTURE_SEATS, interaction_protocol="decline_only", assist=assist
    )


def action(entry: dict[str, Any]) -> Action:
    """One scripted action, as the v1 corpus writes it."""
    params = entry.get("params", {})
    return Action(player=int(entry["player"]), type=str(entry["type"]), params=params)


def read_log(directory: Path, game_id: GameId) -> Any:
    return GameLogReader(god_log_path(directory, game_id)).read()


def first_open(facade: SessionFacade, game_id: GameId) -> Action:
    """The fixture game's always-legal move, played by whoever is to act.

    Only the identity of the player who is to act comes from the facade; the action itself is this
    game's, and using it here keeps the test about concurrency rather than about choosing a move.
    """
    pending = facade.pending_decisions(game_id)
    assert pending, f"session {game_id} has no open decision to answer"
    return Action(player=pending[0].player, type="gamble", params={})


def play_to_a_win(facade: SessionFacade, game_id: GameId) -> None:
    """A deterministic, always-legal policy for the fixture game: bank, then score."""
    for _ in range(100):
        pending = facade.pending_decisions(game_id)
        if not pending:
            return
        player = pending[0].player
        seen = facade.projection(game_id, player)
        tokens = seen["tokens"]
        bank = seen["bank"]
        assert isinstance(tokens, int)
        assert isinstance(bank, int)
        type_ = "spend" if tokens >= 4 else ("take" if bank >= 1 else "gamble")
        facade.submit_action(game_id, Action(player=player, type=type_, params={}))
    raise AssertionError("the fixture game did not reach a winner within a hundred actions")


# --- the surface the facade offers --------------------------------------------------------------


def test_the_facade_offers_only_the_operations_the_engine_declares() -> None:
    """PRD-v2 FR-1.2: one closed set of operations, so an operation is a deliberate decision."""
    offered = {name for name in dir(SessionFacade) if not name.startswith("_")}

    assert offered == set(PUBLIC_OPERATIONS)


def test_no_source_in_the_host_layer_names_a_game() -> None:
    """PRD-v2 FR-1.2, SC-6: the layer cannot grow a game-specific operation without naming one."""
    host_sources = sorted((TESTS.parent / "lgbg" / "host").rglob("*.py"))

    assert host_sources, "control: the host layer must have sources to scan"
    offenders = [
        f"{path.name}: {name}"
        for path in host_sources
        for name in ("catan",)
        if name in path.read_text(encoding="utf-8").lower()
    ]

    assert offenders == [], "a game name in the host layer is a game-specific path: " + str(
        offenders
    )


def test_creating_a_session_gives_a_game_id_and_the_opening_projection() -> None:
    """'Create session' and 'read projection', against the state the game declares."""
    facade = SessionFacade()

    game_id = facade.create_session("fixture", fixture_config())

    assert game_id == "g-0001"
    assert facade.projection(game_id, 0) == {
        "bank": 12,
        "opponents": {"1": 0},
        "rounds": 0,
        "scores": {"0": 0, "1": 0},
        "tokens": 0,
        "turn": 0,
    }


def test_pending_decisions_are_the_engines_own() -> None:
    """'Read pending decisions' adds nothing and hides nothing: it is the plugin's list."""
    facade = SessionFacade()
    game_id = facade.create_session("fixture", fixture_config())

    pending = facade.pending_decisions(game_id)

    assert [(request.request_id, request.player, request.kind) for request in pending] == [
        ("d0", 0, "turn")
    ]


def test_two_sessions_get_distinct_game_ids_and_a_duplicate_is_refused() -> None:
    """A registry that overwrites a live session would let two clients act on one game."""
    facade = SessionFacade()

    first = facade.create_session("fixture", fixture_config())
    second = facade.create_session("fixture", fixture_config())

    assert (first, second) == ("g-0001", "g-0002")
    with pytest.raises(SessionExistsError):
        facade.create_session("fixture", fixture_config(), game_id=first)


def test_listing_sessions_reports_open_ids_in_order_and_forgets_an_ended_one(
    tmp_path: Path,
) -> None:
    """PRD-v2 FR-3.4's sandbox reads the facade's registry, not a transport's memory."""
    facade = SessionFacade()
    later = facade.create_session("fixture", fixture_config(), game_id="g-0002", directory=tmp_path)
    earlier = facade.create_session(
        "fixture", fixture_config(), game_id="g-0001", directory=tmp_path
    )

    assert facade.list_sessions() == [earlier, later]

    facade.end_session(earlier)

    assert facade.list_sessions() == [later]


def test_reading_a_session_that_does_not_exist_is_reported_as_such() -> None:
    """A typo must not look like an empty game."""
    facade = SessionFacade()

    with pytest.raises(SessionNotFoundError):
        facade.projection("g-9999", 0)
    with pytest.raises(SessionNotFoundError):
        facade.pending_decisions("g-9999")
    with pytest.raises(SessionNotFoundError):
        facade.outcome("g-9999")


def test_submitting_a_legal_action_advances_the_game_and_records_it(tmp_path: Path) -> None:
    """'Submit action' is the only thing that changes state, and it lands in the god log."""
    facade = SessionFacade()
    game_id = facade.create_session("fixture", fixture_config(), directory=tmp_path)

    result = facade.submit_action(game_id, Action(player=0, type="take", params={}))

    assert isinstance(result, Applied)
    seen = facade.projection(game_id, 0)
    assert (seen["tokens"], seen["bank"], seen["turn"]) == (1, 11, 1)
    log = read_log(tmp_path, game_id)
    assert [record.result.get("ok") for record in log.actions] == [True]


# --- a rejection is a rejection -----------------------------------------------------------------


def test_an_action_for_a_player_with_no_open_decision_is_rejected_not_queued(
    tmp_path: Path,
) -> None:
    """FR-1.6: the core's own code, no state change, no queue, and a session still usable."""
    facade = SessionFacade()
    game_id = facade.create_session("fixture", fixture_config(), directory=tmp_path)
    before = facade.pending_decisions(game_id)

    result = facade.submit_action(game_id, Action(player=1, type="take", params={}))

    assert isinstance(result, Rejected)
    assert result.rejection.code is NOT_YOUR_DECISION
    assert facade.projection(game_id, 0)["tokens"] == 0
    assert facade.pending_decisions(game_id) == before
    assert isinstance(
        facade.submit_action(game_id, Action(player=0, type="take", params={})), Applied
    )
    assert [record.result.get("ok") for record in read_log(tmp_path, game_id).actions] == [
        False,
        True,
    ]


# --- the decision surface -----------------------------------------------------------------------


def test_the_decision_surface_is_the_one_renderer_at_the_runs_level() -> None:
    """PRD-v2 FR-1.2 with FR-3.9's spirit: one renderer, and the level is the run's choice."""
    facade = SessionFacade()
    silent = facade.create_session("fixture", fixture_config(assist=AssistLevel.L0))
    loud = facade.create_session("fixture", fixture_config(assist=AssistLevel.L2))

    at_l0 = facade.decision_surface(silent, 0)
    at_l2 = facade.decision_surface(loud, 0)

    assert at_l0 == to_canonical_json(dict(facade.projection(silent, 0)))
    assert "gamble" not in at_l0
    assert "gamble" in at_l2


# --- the outcome, and what a closed record means ------------------------------------------------


def test_the_outcome_is_unknown_until_the_game_ends(tmp_path: Path) -> None:
    """'Read outcome' answers None while a game is in progress, and the verdict once it is over."""
    facade = SessionFacade()
    game_id = facade.create_session("fixture", fixture_config(), directory=tmp_path)

    assert facade.outcome(game_id) is None
    play_to_a_win(facade, game_id)

    outcome = facade.outcome(game_id)
    assert outcome is not None
    assert outcome.winner == 0
    assert dict(outcome.scores) == {"0": 2, "1": 1}
    assert read_log(tmp_path, game_id).terminal is not None


def test_a_finished_game_still_reads_but_no_longer_accepts_actions(tmp_path: Path) -> None:
    """The record is closed the moment the game is over, and the position stays readable."""
    facade = SessionFacade()
    game_id = facade.create_session("fixture", fixture_config(), directory=tmp_path)
    play_to_a_win(facade, game_id)

    with pytest.raises(SessionClosedError):
        facade.submit_action(game_id, Action(player=0, type="gamble", params={}))
    assert facade.pending_decisions(game_id) == []


def test_ending_a_session_closes_its_record_without_a_terminal_line(tmp_path: Path) -> None:
    """An abandoned record: complete, replayable, and honestly without a verdict (PRD-v2 FR-7.5)."""
    facade = SessionFacade()
    game_id = facade.create_session("fixture", fixture_config(), directory=tmp_path)
    facade.submit_action(game_id, Action(player=0, type="take", params={}))

    facade.end_session(game_id)

    log = read_log(tmp_path, game_id)
    assert log.terminal is None
    assert verify(log, get_game("fixture")).actions == 1
    with pytest.raises(SessionNotFoundError):
        facade.outcome(game_id)


# --- the same code path, whatever the game -------------------------------------------------------


@pytest.mark.parametrize(("game", "seats"), [("fixture", 2), ("catan", 4)])
def test_two_games_of_different_shapes_are_driven_by_one_code_path(game: str, seats: int) -> None:
    """SC-6's claim, held from below: no game fact is needed to create, read and be rejected."""
    facade = SessionFacade()
    game_id = facade.create_session(
        game, RunConfig(seed=1, players=seats, interaction_protocol="decline_only")
    )

    assert facade.outcome(game_id) is None
    assert facade.projection(game_id, 0)
    assert facade.pending_decisions(game_id)
    assert facade.decision_surface(game_id, 0)
    refusal = facade.submit_action(game_id, Action(player=0, type="no_such_action", params={}))
    assert isinstance(refusal, Rejected)
    assert refusal.rejection.code is UNKNOWN_ACTION


# --- concurrency ---------------------------------------------------------------------------------


def test_several_sessions_advance_in_parallel_without_interfering(tmp_path: Path) -> None:
    """NFR-6: parallel sessions produce the same hash chains, so neither one disturbed the other."""
    facade = SessionFacade()
    ids = [
        facade.create_session(
            "fixture", fixture_config(), directory=tmp_path, game_id=f"g-{index:04d}"
        )
        for index in range(8)
    ]

    def play(game_id: GameId) -> list[str]:
        hashes: list[str] = []
        for _ in range(12):
            facade.submit_action(game_id, first_open(facade, game_id))
        hashes.extend(record.state_hash for record in read_log(tmp_path, game_id).actions)
        return hashes

    with ThreadPoolExecutor(max_workers=len(ids)) as pool:
        chains = list(pool.map(play, ids))

    assert len({tuple(chain) for chain in chains}) == 1, "sessions interfered with each other"
    for game_id in ids:
        assert verify(read_log(tmp_path, game_id), get_game("fixture")).actions == 12


def test_one_session_may_have_several_open_decisions_answered_at_once(tmp_path: Path) -> None:
    """FR-1.5: a table decides concurrently by rule, so one session holds several open decisions."""
    script: dict[str, Any] = json.loads((CATAN_SCRIPTS / "random_game.json").read_text("utf-8"))
    entries: list[dict[str, Any]] = script["actions"]
    facade = SessionFacade()
    game_id = facade.create_session(
        script["game"],
        RunConfig.from_mapping(script["config"], game_option_keys=None),
        directory=tmp_path,
    )
    for entry in entries[:34]:
        assert isinstance(
            facade.submit_action(game_id, action(entry), request_id=entry.get("request_id")),
            Applied,
        )

    open_now = facade.pending_decisions(game_id)
    assert len(open_now) == 4, "this fixture is chosen because four players decide at once"

    def answer(entry: dict[str, Any]) -> ApplyResult:
        return facade.submit_action(game_id, action(entry), request_id=entry.get("request_id"))

    with ThreadPoolExecutor(max_workers=len(open_now)) as pool:
        answered = list(pool.map(answer, entries[34:38]))

    # The four trade responses are not independent: accepting one ends the trade and closes
    # the others. What is asserted is that four concurrent answers each reached the engine,
    # none interleaved a record, and the game still replays; which of them the rules accept
    # is the game's decision, not the lock's.
    assert len(answered) == 4
    assert all(isinstance(result, Applied | Rejected) for result in answered)
    assert any(isinstance(result, Applied) for result in answered)
    assert len(read_log(tmp_path, game_id).actions) == 38
    still_open = {request.request_id for request in facade.pending_decisions(game_id)}
    assert still_open.isdisjoint({request.request_id for request in open_now})
    facade.end_session(game_id)
    assert verify(read_log(tmp_path, game_id), get_game(script["game"])).actions == 38
