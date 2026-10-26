"""The v2 artefact contracts, frozen before a slice can invent one (PRD-v2 FR-10, FR-11.10, SC-4).

Card K-002 is the second half of slice 0, and it does not end in a demo on purpose. v1's god log is
frozen and stays frozen; everything a model adds goes in the manifest and the sidecar. Freezing
those shapes now is what makes slices 3 to 7 *add fields to a shape* rather than invent their own.

Three things are asserted here:

- Two fixtures - a run manifest and one decision record - validate against the declared shapes. A
  shape that only exists in prose accepts nothing, so the declarations are held to a record that
  could actually have been written.
- They refuse the things they exist to refuse: a missing policy value, an undeclared section, a
  float. A float is refused because the sidecar and the manifest are written through the same
  canonical serialiser as the god log, and a float there would be a record whose bytes are not
  stable across platforms (ARCHITECTURE.md section 6).
- The god log is unchanged, field for field, across every game of the v1 corpus, and the fields it
  has are the ones the runtime's own writer emits - so the declaration cannot quietly become a
  description of a log nobody writes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from lgbg.core.contracts import (
    DECISION_SCHEMA,
    GOD_LOG_FIELDS,
    MANIFEST_SCHEMA,
    validate_decision,
    validate_manifest,
)
from lgbg.core.log import (
    GOD_LOG_SCHEMA,
    KIND_ACTION,
    KIND_HEADER,
    KIND_PHASE,
    KIND_TERMINAL,
    record_from_mapping,
    record_to_mapping,
)

TESTS: Final[Path] = Path(__file__).resolve().parents[1]
FIXTURES: Final[Path] = TESTS / "fixtures" / "v2"
MANIFEST_FIXTURE: Final[Path] = FIXTURES / "run.json"
DECISIONS_FIXTURE: Final[Path] = FIXTURES / "decisions.jsonl"
GOLDEN_CORPUS: Final[Path] = TESTS / "golden" / "catan"


def _object(path: Path) -> dict[str, Any]:
    loaded: Any = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"{path} is not a JSON object"
    return loaded


def fixture_manifest() -> dict[str, Any]:
    return _object(MANIFEST_FIXTURE)


def fixture_decisions() -> list[dict[str, Any]]:
    """One record per line, exactly as a reader of the sidecar would see them."""
    records: list[dict[str, Any]] = []
    for line in DECISIONS_FIXTURE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            loaded: Any = json.loads(line)
            assert isinstance(loaded, dict)
            records.append(loaded)
    return records


def golden_records() -> list[dict[str, Any]]:
    """Every record of every v1 golden game, as written."""
    records: list[dict[str, Any]] = []
    for path in sorted(GOLDEN_CORPUS.glob("*.god.jsonl")):
        records.extend(
            record for record in map(json.loads, path.read_text(encoding="utf-8").splitlines())
        )
    return records


# --- the fixtures validate ---------------------------------------------------------------------


def test_the_manifest_fixture_validates() -> None:
    """A run manifest, as the runner will write it, fits the declared shape."""
    assert validate_manifest(fixture_manifest()) == []


def test_the_decision_fixture_validates() -> None:
    """A decision record, as the agent layer will write it, fits the declared shape."""
    decisions = fixture_decisions()

    assert decisions, "the sidecar fixture is empty, so it validates nothing"
    for record in decisions:
        assert validate_decision(record) == []


def test_the_manifest_shape_carries_what_the_card_names() -> None:
    """Design, seats, policies, prompt hashes, price table and provider identity (FR-10.1)."""
    required = set(_required(MANIFEST_SCHEMA))

    assert {
        "design",
        "seats",
        "policies",
        "prompts",
        "price_table",
        "providers",
        "config",
        "game",
    } <= required


def test_the_decision_shape_carries_what_the_card_names() -> None:
    """Attempt, redo budget, rejection, route, native tools, usage, cost, latency, failure."""
    required = set(_required(DECISION_SCHEMA))

    assert {
        "attempt",
        "redo_budget",
        "rejection",
        "route",
        "native_tools",
        "usage",
        "cost_micro_usd",
        "latency_ms",
        "failure",
        "outcome",
        "messages",
        "response",
        "wire",
    } <= required


def _required(schema: Mapping[str, Any]) -> list[str]:
    required: Any = schema.get("required", [])
    assert isinstance(required, list)
    return [str(name) for name in required]


# --- the shapes refuse what they exist to refuse ------------------------------------------------


def test_a_manifest_missing_a_policy_is_reported() -> None:
    """FR-10.1: every policy value is recorded, and an absent one is a failure rather than a gap."""
    manifest = fixture_manifest()
    policies = manifest["policies"]
    assert isinstance(policies, dict)
    del policies["redo_budget"]

    problems = validate_manifest(manifest)

    assert any("redo_budget" in problem for problem in problems), problems


def test_a_manifest_with_an_undeclared_section_is_reported() -> None:
    """The contract is closed: a section nobody declared is a shape drifting, not an extension."""
    manifest = fixture_manifest()
    manifest["notes"] = "a section no requirement asked for"

    problems = validate_manifest(manifest)

    assert any("notes" in problem for problem in problems), problems


def test_the_manifest_refuses_a_float() -> None:
    """Sampling parameters are recorded in a declared integer unit, never as a float.

    The reason is narrow and mechanical: every artefact in this project is written through the one
    canonical serialiser, which refuses floats because float formatting is not stable across
    platforms. Millis are what a record can hold, and the exact payload the provider saw is
    recorded verbatim in the sidecar (FR-5.4), so nothing is lost.
    """
    manifest = fixture_manifest()
    seats = manifest["seats"]
    assert isinstance(seats, list)
    sampling = seats[0]["sampling"]
    assert isinstance(sampling, dict)
    sampling["temperature_milli"] = 0.5

    problems = validate_manifest(manifest)

    assert any("temperature_milli" in problem for problem in problems), problems


def test_a_decision_record_with_a_zero_attempt_is_reported() -> None:
    """FR-10.3: the attempt index counts redo turns from one; zero would hide where a turn began."""
    record = fixture_decisions()[0]
    record["attempt"] = 0

    problems = validate_decision(record)

    assert any("attempt" in problem for problem in problems), problems


def test_a_decision_record_claiming_an_action_without_one_is_reported() -> None:
    """An outcome says what happened; 'action' with no action is a record that cannot be trusted."""
    record = fixture_decisions()[0]
    record["outcome"] = {"kind": "action"}

    problems = validate_decision(record)

    assert any("outcome" in problem for problem in problems), problems


# --- the god log is unchanged -------------------------------------------------------------------


def test_the_corpus_covers_every_record_kind() -> None:
    """Control: a corpus missing a kind would freeze that kind by assumption."""
    kinds = {record["t"] for record in golden_records()}

    assert kinds == {KIND_HEADER, KIND_ACTION, KIND_PHASE, KIND_TERMINAL}


def test_the_god_log_is_unchanged_field_for_field() -> None:
    """FR-10.2: the v1 record is frozen, and its fields are the ones declared here."""
    drifted: dict[str, set[str]] = {}
    for record in golden_records():
        declared = set(GOD_LOG_FIELDS[record["t"]])
        drift = set(record) ^ declared
        if drift:
            drifted.setdefault(record["t"], set()).update(drift)

    assert drifted == {}, f"the god log changed: {drifted}"


def test_the_writer_emits_exactly_the_declared_fields() -> None:
    """The declaration describes the runtime's writer, not a copy of a log it no longer produces."""
    for record in golden_records():
        parsed = record_from_mapping(record)
        written = record_to_mapping(parsed)
        assert set(written) == set(GOD_LOG_FIELDS[record["t"]]), record["t"]


def test_the_god_log_schema_is_still_the_v1_one() -> None:
    """A v2 artefact must not have changed the record's schema name or its major version."""
    headers = [record for record in golden_records() if record["t"] == KIND_HEADER]

    assert GOD_LOG_SCHEMA == "lgbg.game.v1"
    assert {record["schema"] for record in headers} == {GOD_LOG_SCHEMA}
