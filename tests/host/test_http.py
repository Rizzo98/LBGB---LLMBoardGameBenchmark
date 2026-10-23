"""The HTTP host: a JSON API over the one facade (PRD-v2 FR-2.1 to PRD-v2 FR-2.7).

The tests call the application the way a server does - an ASGI scope in, ASGI messages out - and
never start a server. That is the interface the requirement names, and it is what lets the suite
run with no port and no network (NFR-8).

Two distinctions are asserted over and over, because they are the ones that blur in practice: an
illegal move is a 200 carrying the engine's rejection, and a failure to reach the engine at all is
an HTTP error. A client that cannot tell them apart cannot tell a bad model from a bad server.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Any

import pytest

import tests.games.fixture_game  # noqa: F401 - registers the fixture game
from lgbg.host.http import HOST_SCHEMA, HttpHost
from tests.host.support import Answer, call

REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION = "g-http"


@pytest.fixture
def app(tmp_path: Path) -> HttpHost:
    return HttpHost(directory=tmp_path)


def create(
    app: HttpHost,
    *,
    game: str = "fixture",
    seed: int = 1,
    players: int = 2,
    session_id: str = SESSION,
    assist: str = "L1",
) -> Answer:
    return call(
        app,
        "POST",
        "/sessions",
        json_body={
            "game": game,
            "seed": seed,
            "players": players,
            "interaction_protocol": "decline_only",
            "assist": assist,
            "session_id": session_id,
        },
    )


def test_create_then_read_state_decisions_surface_and_outcome(app: HttpHost) -> None:
    """PRD-v2 FR-2.1: the five reads and the one write a host exposes."""
    created = create(app)
    assert created.status == 201
    assert created.body == {"schema": HOST_SCHEMA, "session_id": SESSION}

    state = call(app, "GET", f"/sessions/{SESSION}/state?player=0")
    assert state.status == 200
    assert state.body["schema"] == HOST_SCHEMA
    assert state.body["player"] == 0
    assert state.body["state"]["turn"] == 0
    assert state.body["state"]["tokens"] == 0

    decisions = call(app, "GET", f"/sessions/{SESSION}/decisions")
    assert decisions.status == 200
    assert decisions.body["decisions"][0]["player"] == 0

    surface = call(app, "GET", f"/sessions/{SESSION}/surface?player=0")
    assert surface.status == 200
    assert "asking:" in surface.body["surface"], "L1 adds the decision surface"

    outcome = call(app, "GET", f"/sessions/{SESSION}/outcome")
    assert outcome.status == 200
    assert outcome.body == {"schema": HOST_SCHEMA, "outcome": None}


def test_an_illegal_move_is_a_200_with_the_engine_rejection(app: HttpHost) -> None:
    """PRD-v2 FR-2.3: the engine spoke, so the transport succeeded."""
    create(app)

    answer = call(
        app,
        "POST",
        f"/sessions/{SESSION}/actions",
        json_body={"player": 1, "type": "take", "params": {}},
    )

    assert answer.status == 200
    assert answer.body["schema"] == HOST_SCHEMA
    result = answer.body["result"]
    assert result["ok"] is False
    assert result["error"] == "NOT_YOUR_DECISION"
    assert result["details"] == {"open_players": [0]}, "the host keeps the record's full detail"
    assert call(app, "GET", f"/sessions/{SESSION}/state?player=0").body["state"]["turn"] == 0


def test_an_accepted_move_advances_the_game_and_is_visible(app: HttpHost) -> None:
    create(app)

    answer = call(
        app,
        "POST",
        f"/sessions/{SESSION}/actions",
        json_body={"player": 0, "type": "take", "params": {}},
    )

    assert answer.status == 200
    assert answer.body["result"]["ok"] is True
    assert answer.body["result"]["events"] == [
        {"type": "tokens_gained", "payload": {"player": 0, "amount": 1}}
    ]
    state = call(app, "GET", f"/sessions/{SESSION}/state?player=1").body["state"]
    assert state["turn"] == 1
    assert state["bank"] == 11


def test_transport_failures_are_http_errors_and_stay_json(app: HttpHost) -> None:
    """PRD-v2 FR-2.2 and PRD-v2 FR-2.3: everything is JSON, and a failure is not a 200."""
    create(app)

    unknown_path = call(app, "GET", "/nowhere")
    unknown_session = call(app, "GET", "/sessions/g-missing/state?player=0")
    malformed = call(app, "POST", f"/sessions/{SESSION}/actions", raw_body=b"{not json")
    wrong_method = call(app, "DELETE", f"/sessions/{SESSION}/state?player=0")
    no_seat = call(app, "GET", f"/sessions/{SESSION}/state")
    duplicate = create(app)

    assert unknown_path.status == 404
    assert unknown_session.status == 404
    assert malformed.status == 400
    assert wrong_method.status == 405
    assert no_seat.status == 400
    assert duplicate.status == 409
    for answer in (unknown_path, unknown_session, malformed, wrong_method, no_seat, duplicate):
        assert answer.headers["content-type"].startswith("application/json")
        assert answer.body["schema"] == HOST_SCHEMA
        assert "kind" in answer.body["error"]
        assert "message" in answer.body["error"]


def test_every_response_carries_the_schema_version(app: HttpHost) -> None:
    """PRD-v2 FR-2.2: a documented version, on success and on failure alike."""
    answers = [
        call(app, "GET", "/sessions"),
        create(app),
        call(app, "GET", f"/sessions/{SESSION}/state?player=0"),
        call(app, "GET", f"/sessions/{SESSION}/decisions"),
        call(app, "GET", f"/sessions/{SESSION}/surface?player=0"),
        call(app, "GET", f"/sessions/{SESSION}/outcome"),
        call(app, "GET", "/nowhere"),
    ]

    assert {answer.body["schema"] for answer in answers} == {HOST_SCHEMA}


def test_the_registry_lists_what_is_live_with_its_game(app: HttpHost) -> None:
    """PRD-v2 FR-2.4: a session id is meaningful only with the game it names."""
    assert create(app, session_id="g-one").status == 201
    assert create(app, seed=2, session_id="g-two").status == 201

    listed = call(app, "GET", "/sessions")

    assert listed.status == 200
    assert listed.body["sessions"] == [
        {"game": "fixture", "session_id": "g-one"},
        {"game": "fixture", "session_id": "g-two"},
    ]


def test_no_read_returns_a_god_view(app: HttpHost) -> None:
    """PRD-v2 FR-2.6: every observation read names a seat, with no unfiltered alternative."""
    create(app)

    missing = call(app, "GET", f"/sessions/{SESSION}/state")
    nonsensical = call(app, "GET", f"/sessions/{SESSION}/state?player=two")

    assert missing.status == 400
    assert nonsensical.status == 400


def test_ending_a_session_is_a_transport_success_and_the_game_is_gone(app: HttpHost) -> None:
    create(app)

    ended = call(app, "DELETE", f"/sessions/{SESSION}")

    assert ended.status == 200
    assert ended.body["ok"] is True
    assert call(app, "GET", f"/sessions/{SESSION}/outcome").status == 404


def test_a_lifespan_startup_and_shutdown_complete(app: HttpHost) -> None:
    """An ASGI server sends lifespan messages; the host must answer them, not hang."""
    messages: list[dict[str, Any]] = [
        {"type": "lifespan.startup"},
        {"type": "lifespan.shutdown"},
    ]
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return messages.pop(0)

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    asyncio.run(app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send))

    assert [message["type"] for message in sent] == [
        "lifespan.startup.complete",
        "lifespan.shutdown.complete",
    ]


def test_the_host_routes_against_asgi_without_a_web_framework() -> None:
    """PRD-v2 FR-2.7: no framework is bought for a handful of routes."""
    source = (REPO_ROOT / "lgbg" / "host" / "http.py").read_text(encoding="utf-8")
    banned = {"django", "fastapi", "flask", "quart", "sanic", "starlette", "tornado"}
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])

    assert imported & banned == set()
    assert "async def __call__" in source
