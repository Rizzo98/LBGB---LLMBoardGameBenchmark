"""Token and cost accounting: known stays known, unknown stays unknown (PRD-v2 FR-13).

A cost total is only useful if it says how complete it is. These tests hold the two halves: the
arithmetic from a declared table, and the explicit unknown that stops an omitted usage being
recorded as free.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lgbg.agents.accounting import RunAccounting, cost_micro_usd
from lgbg.agents.loop import Attempt, TurnOutcome, TurnResult
from lgbg.agents.pricing import PRICE_UNIT, ModelPrice, PriceTable, UnknownPriceError
from lgbg.agents.providers.base import Completion, Usage
from lgbg.core.contracts import validate_manifest

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "v2" / "run.json"
READ_AT = "2026-02-11T09:30:00+00:00"

PRICES = PriceTable(
    source="https://example.invalid/models",
    read_at=READ_AT,
    unit=PRICE_UNIT,
    models=(
        ModelPrice(model="vendor/model-a", prompt=250_000, completion=1_000_000),
        ModelPrice(model="vendor/model-b", prompt=3_000_000, completion=15_000_000),
    ),
)


def test_cost_is_tokens_times_price_per_million() -> None:
    usage = Usage(prompt_tokens=1_000, completion_tokens=1_000, total_tokens=2_000)
    price = PRICES.price_for("vendor/model-a")

    assert cost_micro_usd(usage, price) == 1_250


def test_a_nonzero_call_cannot_round_down_to_free() -> None:
    usage = Usage(prompt_tokens=1, completion_tokens=0, total_tokens=1)
    price = ModelPrice(model="m", prompt=1, completion=0)

    assert cost_micro_usd(usage, price) == 1
    assert cost_micro_usd(Usage(0, 0, 0), price) == 0


def test_an_unknown_usage_has_no_cost() -> None:
    assert cost_micro_usd(None, PRICES.price_for("vendor/model-a")) is None


def test_an_unknown_usage_makes_the_run_partial_not_free() -> None:
    accounting = RunAccounting(PRICES)
    accounting.record(
        model="vendor/model-a",
        usage=Usage(prompt_tokens=1_000, completion_tokens=1_000, total_tokens=2_000),
        latency_ms=10,
    )
    accounting.record(model="vendor/model-a", usage=None, latency_ms=20)

    assert accounting.partial is True
    assert accounting.unknown_usage_decisions == 1
    assert accounting.total_cost_micro_usd == 1_250, "the known part is still reported"
    mapping = accounting.to_mapping()
    assert mapping["partial"] is True
    assert mapping["unknown_usage_decisions"] == 1
    assert mapping["cost_micro_usd"] == 1_250


def test_a_run_with_only_unknown_usage_is_partial_rather_than_silently_zero() -> None:
    accounting = RunAccounting(PRICES)
    entry = accounting.record(model="vendor/model-a", usage=None, latency_ms=5)

    assert entry.cost_micro_usd is None
    assert accounting.total_cost_micro_usd == 0
    assert accounting.partial is True
    assert accounting.to_mapping()["unknown_usage_decisions"] == 1


def test_a_fully_known_run_is_not_partial() -> None:
    accounting = RunAccounting(PRICES)
    accounting.record(
        model="vendor/model-a",
        usage=Usage(prompt_tokens=1_000, completion_tokens=1_000, total_tokens=2_000),
        latency_ms=10,
    )

    assert accounting.partial is False
    assert accounting.to_mapping()["partial"] is False


def test_per_model_arithmetic_is_reported_separately() -> None:
    accounting = RunAccounting(PRICES)
    accounting.record(
        model="vendor/model-a",
        usage=Usage(prompt_tokens=1_000, completion_tokens=1_000, total_tokens=2_000),
        latency_ms=10,
    )
    accounting.record(
        model="vendor/model-b",
        usage=Usage(prompt_tokens=1_000, completion_tokens=1_000, total_tokens=2_000),
        latency_ms=20,
    )

    rows = accounting.per_model()

    assert [row["model"] for row in rows] == ["vendor/model-a", "vendor/model-b"]
    assert rows[0]["cost_micro_usd"] == 1_250
    assert rows[1]["cost_micro_usd"] == 18_000
    assert all(row["partial"] is False for row in rows)


def test_a_model_without_a_price_is_refused() -> None:
    accounting = RunAccounting(PRICES)

    with pytest.raises(UnknownPriceError, match="no price"):
        accounting.record(model="vendor/missing", usage=None, latency_ms=1)


def test_a_negative_latency_is_refused() -> None:
    accounting = RunAccounting(PRICES)

    with pytest.raises(ValueError, match="latency"):
        accounting.record(
            model="vendor/model-a",
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            latency_ms=-1,
        )


def test_the_table_used_is_recorded_in_the_manifest() -> None:
    accounting = RunAccounting(PRICES)
    manifest: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    manifest.update(accounting.manifest_fragment())

    assert validate_manifest(manifest) == []
    assert manifest["price_table"] == PRICES.to_mapping()


def test_a_decision_turn_records_every_attempt_with_its_latency() -> None:
    accounting = RunAccounting(PRICES)
    first = Attempt(
        index=1,
        completion=Completion(
            text=None,
            tool_calls=None,
            usage=Usage(prompt_tokens=1_000, completion_tokens=1_000, total_tokens=2_000),
        ),
        latency_ms=42,
        messages=(),
    )
    second = Attempt(
        index=2,
        completion=Completion(text=None, tool_calls=None, usage=None),
        latency_ms=7,
        messages=(),
    )
    result = TurnResult(
        outcome=TurnOutcome.ACCEPTED,
        messages=(),
        attempts=(first, second),
        redo_attempts=0,
    )

    entries = accounting.record_turn(result, model="vendor/model-a")

    assert [entry.latency_ms for entry in entries] == [42, 7]
    assert [entry.cost_micro_usd for entry in entries] == [1_250, None]
    assert accounting.partial is True
