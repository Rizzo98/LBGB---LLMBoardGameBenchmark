"""The decision sidecar: written only when it is safe and shaped (PRD-v2 FR-10.4, NFR-7).

A record that cannot answer "what did the model see?" is not evidence, and a record that carries a
credential is a leak. The writer is the gate for both: redact, validate, then append.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lgbg.agents.providers.base import Completion
from lgbg.agents.sidecar import DecisionSidecar, SidecarError, wire_of
from lgbg.core.canonical import to_canonical_json
from lgbg.core.contracts import validate_decision

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "v2" / "decisions.jsonl"


def record() -> dict[str, Any]:
    loaded: Any = json.loads(FIXTURE.read_text(encoding="utf-8").splitlines()[0])
    assert isinstance(loaded, dict)
    return loaded


def test_a_valid_record_is_written_and_read_back(tmp_path: Path) -> None:
    sidecar = DecisionSidecar(tmp_path / "games" / "g-0001.meta.jsonl")

    sidecar.append(record())

    written = sidecar.path.read_text(encoding="utf-8").splitlines()
    assert len(written) == 1
    assert json.loads(written[0]) == record()
    assert sidecar.records() == [record()]


def test_a_record_missing_its_exchange_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    sidecar = DecisionSidecar(tmp_path / "g-0001.meta.jsonl")
    broken = record()
    del broken["wire"]

    with pytest.raises(SidecarError, match="wire"):
        sidecar.append(broken)

    assert not sidecar.path.exists()


def test_a_shape_violation_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    sidecar = DecisionSidecar(tmp_path / "g-0001.meta.jsonl")
    broken = record()
    broken["attempt"] = 0

    with pytest.raises(SidecarError, match="attempt"):
        sidecar.append(broken)

    assert not sidecar.path.exists()


def test_credentials_are_redacted_before_the_file_is_written(tmp_path: Path) -> None:
    sidecar = DecisionSidecar(tmp_path / "g-0001.meta.jsonl", secrets=("sk-live-secret",))
    leaking = record()
    wire = leaking["wire"]
    assert isinstance(wire, dict)
    wire["request_headers"] = {
        "Authorization": "Bearer sk-live-secret",
        "Content-Type": "application/json",
    }
    wire["request"] = '{"model":"m","echo":"sk-live-secret"}'

    sidecar.append(leaking)

    text = sidecar.path.read_text(encoding="utf-8")
    assert "sk-live-secret" not in text
    assert "[redacted]" in text
    stored = sidecar.records()[0]
    stored_wire = stored["wire"]
    assert isinstance(stored_wire, dict)
    headers = stored_wire["request_headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "[redacted]"
    assert validate_decision(stored) == []


def test_the_writer_uses_the_canonical_serialiser(tmp_path: Path) -> None:
    sidecar = DecisionSidecar(tmp_path / "g-0001.meta.jsonl")

    sidecar.append(record())

    line = sidecar.path.read_text(encoding="utf-8").strip()
    assert line == to_canonical_json(record())


def test_a_completion_without_an_exchange_is_refused() -> None:
    completion = Completion(text="hi", tool_calls=None, usage=None)

    with pytest.raises(SidecarError, match="exchange"):
        wire_of(completion)


def test_a_completion_with_an_exchange_yields_its_mapping() -> None:
    from lgbg.agents.providers.base import CallMetadata
    from lgbg.agents.wire import WireExchange

    exchange = WireExchange.capture(
        request='{"model":"m"}', response='{"ok":true}', status_code=200
    )
    completion = Completion(
        text="hi",
        tool_calls=None,
        usage=None,
        metadata=CallMetadata(model="m", route=None, native_tools=True, wire=exchange),
    )

    assert wire_of(completion) == exchange.to_mapping()
