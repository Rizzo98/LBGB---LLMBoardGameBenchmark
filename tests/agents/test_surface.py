"""The agent surface: generated tools, pure reads, one action path (PRD-v2 FR-6.2, FR-6.6).

The surface is where the loop meets the game, so these tests hold the seam rather than a game: the
action tools are the plugin's own generated definitions, the reads are the facade's pure reads, and
an action reaches the facade exactly once. A model cannot choose a seat or open a game here.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.agents.loop import DecisionTurn, TurnOutcome
from lgbg.agents.providers.base import (
    CompletionConfig,
    Message,
    Role,
    ToolCall,
)
from lgbg.agents.providers.mock import Behaviour, MockProvider
from lgbg.agents.surface import (
    READ_DECISIONS,
    READ_STATE,
    READ_SURFACE,
    READ_TOOLS,
    FacadeSurface,
)
from lgbg.core.assist import rejection_view
from lgbg.core.config import RejectionDetail, RunConfig
from lgbg.core.game import get_game
from lgbg.core.tools import tool_definitions
from lgbg.host.facade import SessionFacade
from tests.games.fixture_game import FixtureGame  # noqa: F401 - importing registers the game

SEAT = 0


def session(
    *, detail: RejectionDetail = RejectionDetail.STANDARD, read_tools: bool = True
) -> tuple[SessionFacade, str, FacadeSurface]:
    facade = SessionFacade()
    config = RunConfig(seed=1, players=2, interaction_protocol="decline_only")
    game_id = facade.create_session("fixture", config)
    surface = FacadeSurface(
        facade,
        "fixture",
        game_id,
        SEAT,
        read_tools=read_tools,
        refusal_view=lambda rejection: rejection_view(rejection, detail=detail),
    )
    return facade, game_id, surface


def act(surface: FacadeSurface, call: ToolCall) -> Any:
    return asyncio.run(surface.act(call))


def read(surface: FacadeSurface, call: ToolCall) -> Any:
    return asyncio.run(surface.read(call))


def test_the_action_tools_are_the_plugin_generator_output() -> None:
    _, _, surface = session()

    generated = tool_definitions(get_game("fixture"))
    served = [tool for tool in surface.tools if tool.name not in READ_TOOLS]

    assert [(tool.name, tool.description, dict(tool.input_schema)) for tool in served] == [
        (str(item["name"]), str(item["description"]), dict(item["inputSchema"]))  # type: ignore[arg-type]
        for item in generated
    ]


def test_reads_are_offered_only_when_configured() -> None:
    _, _, with_reads = session(read_tools=True)
    _, _, without_reads = session(read_tools=False)

    assert {tool.name for tool in with_reads.tools} == {
        *{tool.name for tool in without_reads.tools},
        *READ_TOOLS,
    }
    assert with_reads.read_names == READ_TOOLS
    assert without_reads.read_names == frozenset()


def test_read_state_is_the_plugin_renderer() -> None:
    facade, game_id, surface = session()

    answer = read(surface, ToolCall(id="r1", name=READ_STATE, arguments={}))

    game = get_game("fixture")
    expected = game.render(facade.projection(game_id, SEAT), detail="full")
    assert answer.accepted is True
    assert answer.payload == expected


def test_read_decisions_is_this_seat_only() -> None:
    _, _, surface = session()

    answer = read(surface, ToolCall(id="r1", name=READ_DECISIONS, arguments={}))

    decisions = json.loads(answer.payload)
    assert decisions
    assert {entry["player"] for entry in decisions} == {SEAT}


def test_read_surface_is_the_facade_decision_surface() -> None:
    facade, game_id, surface = session()

    answer = read(surface, ToolCall(id="r1", name=READ_SURFACE, arguments={}))

    assert answer.payload == facade.decision_surface(game_id, SEAT)


def test_reads_mutate_nothing() -> None:
    facade, game_id, surface = session()
    before = facade.pending_decisions(game_id)

    first = read(surface, ToolCall(id="r1", name=READ_STATE, arguments={}))
    second = read(surface, ToolCall(id="r2", name=READ_STATE, arguments={}))

    assert first.payload == second.payload
    assert facade.pending_decisions(game_id) == before


def test_an_accepted_action_goes_through_the_facade() -> None:
    facade, game_id, surface = session()
    before = facade.projection(game_id, SEAT)

    answer = act(surface, ToolCall(id="a1", name="gamble", arguments={}))

    assert answer.accepted is True
    assert json.loads(answer.payload)["ok"] is True
    assert facade.projection(game_id, SEAT) != before


def test_a_rejection_carries_the_configured_detail() -> None:
    _, _, surface = session(detail=RejectionDetail.MINIMAL)

    answer = act(surface, ToolCall(id="a1", name="spend", arguments={}))

    assert answer.accepted is False
    assert set(json.loads(answer.payload)) == {"ok", "error"}
    assert answer.rejection == "TOKENS_UNAVAILABLE"


def test_malformed_arguments_are_refused_without_reaching_the_facade() -> None:
    facade, game_id, surface = session()
    before = facade.pending_decisions(game_id)

    answer = act(surface, ToolCall(id="a1", name="gamble", arguments="{not json"))

    assert answer.accepted is False
    assert answer.rejection == "MALFORMED_ARGUMENTS"
    assert facade.pending_decisions(game_id) == before


def test_a_read_that_was_not_offered_is_refused() -> None:
    _, _, surface = session()

    answer = read(surface, ToolCall(id="r1", name="read_other", arguments={}))

    assert answer.accepted is False
    assert answer.rejection == "UNKNOWN_READ"


def test_a_mock_model_plays_one_decision_through_the_facade() -> None:
    facade, game_id, surface = session()
    before = facade.projection(game_id, SEAT)
    provider = MockProvider(
        Behaviour.CORRECT_PLAY,
        action=ToolCall(id="call-1", name="gamble", arguments={}),
    )
    messages: Sequence[Message] = [
        Message(role=Role.SYSTEM, content="You are playing fixture."),
        Message(role=Role.USER, content="It is your turn."),
    ]

    result = asyncio.run(
        DecisionTurn(provider, surface).run(messages, CompletionConfig(model="mock"))
    )

    assert result.outcome is TurnOutcome.ACCEPTED
    assert result.action is not None
    assert result.action.name == "gamble"
    assert facade.projection(game_id, SEAT) != before
