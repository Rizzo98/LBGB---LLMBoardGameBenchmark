"""The console's ASGI application (PRD-v3 FR-7.1 to PRD-v3 FR-7.8, PRD-v3 FR-8.4).

Every response carries the console schema, a record that cannot be verified is a 200 finding
rather than a transport error, and a browser without a build is told which command produces one.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

import pytest

import lgbg.games  # noqa: F401 - registers Catan, which the golden record names
from lgbg.console.app import CONSOLE_SCHEMA, ConsoleApp
from lgbg.console.records import LogStore
from tests.console.support import Answer, call

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "catan" / "full_game.god.jsonl"
SHELL_MARKER = "console-shell"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    shutil.copyfile(GOLDEN, tmp_path / "full_game.god.jsonl")
    return tmp_path


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    directory = tmp_path / "dist"
    assets = directory / "assets"
    assets.mkdir(parents=True)
    (directory / "index.html").write_text(
        f"<!doctype html><title>LBGB</title><div id='{SHELL_MARKER}'></div>", encoding="utf-8"
    )
    (assets / "app-abc123.js").write_text("console.log('console');\n", encoding="utf-8")
    return directory


@pytest.fixture
def app(root: Path, dist: Path) -> ConsoleApp:
    return ConsoleApp(LogStore([root]), dist)


def test_health_carries_the_console_envelope(app: ConsoleApp) -> None:
    answer = call(app, "GET", "/api/health")

    assert answer.status == 200
    assert answer.body["schema"] == CONSOLE_SCHEMA
    assert answer.body["ok"] is True


def test_listing_reports_each_record_without_verifying_it(app: ConsoleApp) -> None:
    answer = call(app, "GET", "/api/logs")

    assert answer.status == 200
    assert answer.body["schema"] == CONSOLE_SCHEMA
    assert answer.body["logs"] == [
        {"log": "full_game", "game": "catan", "rules_version": "catan-rules-6", "problem": None}
    ]
    assert "actions" not in answer.body["logs"][0]


def test_opening_a_record_reports_the_verified_chain(app: ConsoleApp) -> None:
    answer = call(app, "GET", "/api/logs/full_game")

    assert answer.status == 200
    assert answer.body["schema"] == CONSOLE_SCHEMA
    assert answer.body["log"] == "full_game"
    assert answer.body["game"] == "catan"
    assert answer.body["rules_version"] == "catan-rules-6"
    assert answer.body["actions"] == 743
    assert answer.body["rejections"] == 0
    assert answer.body["verified"] is True
    assert answer.body["completed"] is True
    assert answer.body["failure"] is None


def test_an_unknown_record_is_a_json_404(app: ConsoleApp) -> None:
    answer = call(app, "GET", "/api/logs/absent")

    assert answer.status == 404
    assert answer.body["schema"] == CONSOLE_SCHEMA
    assert answer.body["error"]["code"] == "unknown_log"


def test_a_handle_that_is_a_path_is_a_json_400(app: ConsoleApp) -> None:
    answer = call(app, "GET", "/api/logs/..")

    assert answer.status == 400
    assert answer.body["schema"] == CONSOLE_SCHEMA
    assert answer.body["error"]["code"] == "invalid_log"


def test_an_unsupported_method_is_405_with_allow(app: ConsoleApp) -> None:
    answer = call(app, "POST", "/api/logs")

    assert answer.status == 405
    assert answer.headers["allow"] == "GET"
    assert answer.body["schema"] == CONSOLE_SCHEMA


def test_the_shell_is_served_with_the_build_present(app: ConsoleApp) -> None:
    answer = call(app, "GET", "/")

    assert answer.status == 200
    assert answer.headers["content-type"].startswith("text/html")
    assert SHELL_MARKER in answer.text
    assert answer.headers["cache-control"] == "no-cache"


def test_a_hashed_asset_is_served_and_cached_immutably(app: ConsoleApp) -> None:
    answer = call(app, "GET", "/assets/app-abc123.js")

    assert answer.status == 200
    assert "javascript" in answer.headers["content-type"]
    assert "immutable" in answer.headers["cache-control"]


def test_a_missing_build_names_the_build_command(tmp_path: Path) -> None:
    app = ConsoleApp(LogStore([tmp_path]), tmp_path / "absent")

    answer = call(app, "GET", "/")

    assert answer.status == 503
    assert "pnpm" in answer.text


def test_a_missing_asset_is_404_and_a_path_cannot_climb_out(app: ConsoleApp) -> None:
    missing = call(app, "GET", "/assets/absent.js")
    climbed = call(app, "GET", "/assets/../../secret")

    assert missing.status == 404
    assert climbed.status == 404


def test_an_unknown_api_route_is_json_404(app: ConsoleApp) -> None:
    answer = call(app, "GET", "/api/nowhere")

    assert answer.status == 404
    assert answer.body["schema"] == CONSOLE_SCHEMA


def test_the_console_serves_no_cors_header(app: ConsoleApp) -> None:
    answer = call(app, "GET", "/api/health")

    assert not any(name.startswith("access-control-") for name in answer.headers)


def test_a_lifespan_startup_and_shutdown_complete(app: ConsoleApp) -> None:
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


def test_every_json_answer_names_the_schema(app: ConsoleApp) -> None:
    answers: list[Answer] = [
        call(app, "GET", "/api/health"),
        call(app, "GET", "/api/logs"),
        call(app, "GET", "/api/logs/full_game"),
        call(app, "GET", "/api/logs/absent"),
        call(app, "GET", "/api/logs/.."),
        call(app, "GET", "/api/nowhere"),
    ]

    assert all(answer.body["schema"] == CONSOLE_SCHEMA for answer in answers)
