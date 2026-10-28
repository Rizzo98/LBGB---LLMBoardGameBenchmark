"""serve: the operator's way to start a surface (PRD-v2 FR-14.1 and PRD-v2 FR-3.4).

Two things are asserted. First, the command starts the surface the operator asked for: the HTTP
host, or one of the two MCP profiles over the transport that profile is reached by. Second, a real
benchmark process over stdio answers - the wiring is not merely constructed, it serves.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import TextResourceContents

import lgbg.adapters.cli.serve as serve_module
import tests.games.fixture_game  # noqa: F401 - importing registers the game
from lgbg.adapters.cli.main import main
from lgbg.adapters.mcp.server import Profile
from lgbg.host.http import HttpHost

REPO = Path(__file__).resolve().parents[2]


def test_serve_needs_something_to_serve(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["serve", "--game", "fixture"])

    _out, err = capsys.readouterr()
    assert code == 1
    assert "http" in err
    assert "mcp" in err
    assert "Traceback" not in err


def test_serve_starts_the_http_host(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The HTTP host is an ASGI application; serve hands it to the server with the address given."""
    seen: dict[str, object] = {}

    def fake_http(app: object, host: str, port: int) -> None:
        seen["app"] = app
        seen["host"] = host
        seen["port"] = port

    monkeypatch.setattr(serve_module, "run_http", fake_http)

    code = main(
        [
            "serve",
            "--http",
            "127.0.0.1:8111",
            "--record-dir",
            str(tmp_path),
        ]
    )

    out, err = capsys.readouterr()
    assert code == 0, err + out
    assert isinstance(seen["app"], HttpHost)
    assert seen["host"] == "127.0.0.1"
    assert seen["port"] == 8111


def test_serve_rejects_a_malformed_address(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serve_module, "run_http", lambda *args: None)

    code = main(["serve", "--game", "fixture", "--http", "nowhere"])

    _out, err = capsys.readouterr()
    assert code == 1
    assert "host:port" in err
    assert "Traceback" not in err


def test_serve_starts_a_chosen_mcp_profile_over_stdio(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Profile] = []

    def fake_stdio(surface: object) -> None:
        seen.append(surface.profile)  # type: ignore[attr-defined]

    monkeypatch.setattr(serve_module, "run_stdio", fake_stdio)

    assert main(["serve", "--game", "fixture", "--mcp", "sandbox", "--players", "2"]) == 0
    assert seen[0].value == "sandbox"

    assert (
        main(
            [
                "serve",
                "--game",
                "fixture",
                "--mcp",
                "benchmark",
                "--player",
                "0",
                "--players",
                "2",
                "--seed",
                "1",
                "--session-id",
                "g-0001",
            ]
        )
        == 0
    )
    assert seen[1].value == "benchmark"


def test_serve_serves_the_sandbox_profile_over_a_real_stdio_process(tmp_path: Path) -> None:
    """SC-14's entry point: a client can start serve and open a game through it."""
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "lgbg.adapters.cli",
            "serve",
            "--game",
            "fixture",
            "--mcp",
            "sandbox",
            "--plugin",
            "tests.games.fixture_game",
            "--record-dir",
            str(tmp_path),
            "--players",
            "2",
        ],
        cwd=str(REPO),
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )

    async def scenario() -> tuple[set[str], str]:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as client,
        ):
            await client.initialize()
            tools = {tool.name for tool in (await client.list_tools()).tools}
            created = await client.call_tool("create_session", {"seed": 1, "players": 2})
            assert created.structuredContent is not None
            game_id = str(created.structuredContent["session_id"])
            state = await client.read_resource(
                f"fixture://sessions/{game_id}/state?player=0"  # type: ignore[arg-type]
            )
            content = state.contents[0]
            assert isinstance(content, TextResourceContents)
            return tools, content.text

    tools, projection = asyncio.run(asyncio.wait_for(scenario(), timeout=30))

    assert {"create_session", "list_sessions", "end_session"} <= tools
    assert '"tokens":0' in projection
