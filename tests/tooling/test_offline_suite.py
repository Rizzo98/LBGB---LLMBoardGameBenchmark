"""The suite runs with no network and no keys (PRD-v2 FR-15.4, NFR-8).

This is not a claim about intent; it is a scan. A test that opens a connection or reads a
credential makes the suite depend on something a reviewer cannot reproduce, and the dependency is
usually invisible until it fails on a machine without the key.

The scan deliberately allows `httpx.MockTransport` and a client constructed around it: an adapter
test should exercise the real request-building code without a socket. What it rejects is a call
that would leave the process - the convenience verbs, `urlopen`, and a raw socket connection.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

TESTS: Final[Path] = Path(__file__).resolve().parents[1]

NETWORK_CALL: Final[re.Pattern[str]] = re.compile(
    r"\b(?:httpx|requests)\.(?:delete|get|head|patch|post|put|request|stream)\("
    r"|urllib\.request\.urlopen\("
    r"|socket\.(?:create_connection|socket)\("
)
"""A call that would leave the process. A mock transport is not one of these."""

API_KEY: Final[re.Pattern[str]] = re.compile(
    r"\b(?:ANTHROPIC|DEEPSEEK|OPENAI|OPENROUTER)_API_KEY\b"
)


def sources() -> list[Path]:
    """Every test source but this one: the guard names the shapes it rejects."""
    return [path for path in sorted(TESTS.rglob("*.py")) if path.name != Path(__file__).name]


def test_the_scan_found_the_suite() -> None:
    """Control: a scan of nothing proves nothing."""
    assert len(sources()) > 50


def test_no_test_opens_a_network_connection() -> None:
    offenders = [
        path.relative_to(TESTS).as_posix()
        for path in sources()
        if NETWORK_CALL.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == [], f"tests must use a mock transport, not a network: {offenders}"


def test_no_test_names_an_api_key() -> None:
    offenders = [
        path.relative_to(TESTS).as_posix()
        for path in sources()
        if API_KEY.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == [], f"no test may depend on a credential: {offenders}"


def test_the_scan_rejects_the_calls_it_should() -> None:
    """Control: the patterns must fire on the shapes they exist to catch."""
    for source in (
        "httpx.get('https://example.test')",
        "requests.post(url, json={})",
        "urllib.request.urlopen(url)",
        "socket.create_connection(('example.test', 80))",
        "socket.socket()",
        "os.environ['OPENROUTER_API_KEY']",
    ):
        assert NETWORK_CALL.search(source) or API_KEY.search(source), source
