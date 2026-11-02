"""The `lgbg console` command (PRD-v3 FR-8.1 to PRD-v3 FR-8.6, SC-9).

The command is a launcher, not a server implementation: it validates what it was asked to open,
prints the URL, and hands the ASGI application to uvicorn. The tests keep the server out of the
process by replacing the one function that would block.
"""

from __future__ import annotations

import contextlib
import io
import webbrowser
from pathlib import Path

import pytest

import lgbg.games  # noqa: F401 - registers Catan, which the golden record names
from lgbg.adapters.cli import console as console_module
from lgbg.adapters.cli.main import build_parser, main
from lgbg.console.records import ConsoleError, InvalidRootError

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "catan" / "full_game.god.jsonl"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    directory = tmp_path / "records"
    directory.mkdir()
    (directory / "full_game.god.jsonl").write_bytes(GOLDEN.read_bytes())
    return directory


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    directory = tmp_path / "dist"
    directory.mkdir()
    (directory / "index.html").write_text("<!doctype html><div id='app'></div>", encoding="utf-8")
    return directory


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    calls: list[tuple[str, int]] = []

    def fake_run(app: object, host: str, port: int) -> None:
        calls.append((host, port))

    monkeypatch.setattr(console_module, "run_server", fake_run)
    return calls


def test_the_command_prints_the_url_and_runs_the_server(
    root: Path,
    dist: Path,
    server: list[tuple[str, int]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = console_module.run_console(
        roots=[root], host="127.0.0.1", port=8765, no_browser=True, dist=dist
    )

    assert code == 0
    assert capsys.readouterr().out.strip() == "http://127.0.0.1:8765/"
    assert server == [("127.0.0.1", 8765)]


def test_a_browser_is_opened_unless_it_is_refused(
    root: Path,
    dist: Path,
    server: list[tuple[str, int]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", opened.append)

    console_module.run_console(
        roots=[root], host="127.0.0.1", port=8765, no_browser=False, dist=dist
    )

    assert opened == ["http://127.0.0.1:8765/"]


def test_a_public_address_is_refused(root: Path, dist: Path) -> None:
    with pytest.raises(ConsoleError, match="loopback"):
        console_module.run_console(
            roots=[root], host="192.0.2.10", port=8765, no_browser=True, dist=dist
        )


def test_a_missing_root_is_refused(dist: Path, tmp_path: Path) -> None:
    with pytest.raises(InvalidRootError):
        console_module.run_console(
            roots=[tmp_path / "absent"],
            host="127.0.0.1",
            port=8765,
            no_browser=True,
            dist=dist,
        )


def test_a_missing_build_names_the_build_command(root: Path, tmp_path: Path) -> None:
    with pytest.raises(ConsoleError, match="pnpm"):
        console_module.run_console(
            roots=[root],
            host="127.0.0.1",
            port=8765,
            no_browser=True,
            dist=tmp_path / "absent",
        )


def test_a_port_outside_the_range_is_refused(root: Path, dist: Path) -> None:
    with pytest.raises(ConsoleError, match="port"):
        console_module.run_console(
            roots=[root], host="127.0.0.1", port=70000, no_browser=True, dist=dist
        )


def test_the_cli_reports_a_missing_build_without_a_traceback(
    root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(console_module, "WEB_DIST", tmp_path / "absent")

    code = main(["console", "--root", str(root), "--no-browser"])

    error = capsys.readouterr().err
    assert code == 1
    assert error.startswith("error:")
    assert "pnpm" in error
    assert "Traceback" not in error


def test_the_cli_reports_a_missing_root_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["console", "--root", str(tmp_path / "absent"), "--no-browser"])

    error = capsys.readouterr().err
    assert code == 1
    assert error.startswith("error:")
    assert "not a directory" in error
    assert "Traceback" not in error


def test_the_cli_refuses_a_public_bind(
    root: Path, dist: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(console_module, "WEB_DIST", dist)

    code = main(["console", "--root", str(root), "--host", "192.0.2.10", "--no-browser"])

    assert code == 1


def test_the_console_has_no_host_or_session_options() -> None:
    parser = build_parser()
    args = parser.parse_args(["console", "--root", "records", "--no-browser"])

    assert args.command == "console"
    assert not hasattr(args, "session")
    assert not hasattr(args, "mcp")
    with contextlib.redirect_stderr(io.StringIO()), pytest.raises(SystemExit):
        parser.parse_args(["console", "--session", "g-0001"])
