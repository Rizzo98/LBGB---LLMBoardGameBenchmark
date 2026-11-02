"""The server and the browser client agree on one payload (PRD-v3 FR-9.7).

The fixture is the API's answer for the golden record, committed under ``web/``. The compiler
checks it against the shell's TypeScript type, and this test checks it against the server. A field
renamed on one side fails at least one of the two, which is cheaper than discovering the drift in
a browser.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import lgbg.games  # noqa: F401 - registers Catan, which the golden record names
from lgbg.console.app import ConsoleApp
from lgbg.console.records import LogStore
from tests.console.support import call

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "web" / "src" / "contract" / "log.json"
GOLDEN = REPO_ROOT / "tests" / "golden" / "catan" / "full_game.god.jsonl"


def test_the_contract_fixture_is_the_payload_the_server_sends(tmp_path: Path) -> None:
    shutil.copyfile(GOLDEN, tmp_path / "full_game.god.jsonl")
    app = ConsoleApp(LogStore([tmp_path]), tmp_path / "dist")

    answer = call(app, "GET", "/api/logs/full_game")

    assert answer.status == 200
    assert answer.body == json.loads(FIXTURE.read_text(encoding="utf-8"))
