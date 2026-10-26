"""Token and cost accounting from the declared price table (FR-13.1 to FR-13.4).

The record already carries one usage and one latency per provider call (K-017, K-019). This
module is the arithmetic on top of them, and it has one rule that matters more than the sums: an
unknown
usage stays unknown. A provider that omits usage does not get a zero, because a zero would make an
unknown cost look free and every aggregate after it would be quietly wrong (FR-13.4).

Money is integer micro-dollars. A price is micro-dollars per million tokens, so a call costs
tokens x price / 1,000,000 micro-dollars; the division rounds up, so a call with any usage at all
can never be reported as free. A run that includes one unknown decision is marked partial and the
count of unknown decisions is reported beside the total, rather than the total pretending to be
complete.

The table used is part of the accounting value, not a global: manifest_fragment is the piece of
run.json that records it (FR-13.2), and the same table answers every price lookup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from lgbg.agents.loop import TurnResult
from lgbg.agents.pricing import ModelPrice, PriceTable
from lgbg.agents.providers.base import Usage
from lgbg.core.types import JsonValue

MICRO_USD_PER_UNIT: Final[int] = 1_000_000
"""Tokens x (micro-dollars per million tokens) is micro-dollars after this division."""


def cost_micro_usd(usage: Usage | None, price: ModelPrice) -> int | None:
    """What one call cost in integer micro-dollars, or None when usage is unknown.

    The ceiling division is deliberate: a call that used tokens cannot round down to zero. The
    alternative would make a cheap model's decisions free-looking and a budget meaningless.
    """
    if usage is None:
        return None
    numerator = usage.prompt_tokens * price.prompt + usage.completion_tokens * price.completion
    return (numerator + MICRO_USD_PER_UNIT - 1) // MICRO_USD_PER_UNIT


@dataclass(frozen=True, slots=True)
class DecisionUsage:
    """One provider call's accounting: the usage it reported, its latency, and its cost."""

    model: str
    usage: Usage | None
    latency_ms: int
    cost_micro_usd: int | None

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "model": self.model,
            "usage": None if self.usage is None else self.usage.to_mapping(),
            "cost_micro_usd": self.cost_micro_usd,
            "latency_ms": self.latency_ms,
        }


@dataclass(slots=True)
class RunAccounting:
    """Every decision's usage and latency, and the run totals they add up to."""

    price_table: PriceTable
    decisions: list[DecisionUsage] = field(default_factory=list)

    def record(self, *, model: str, usage: Usage | None, latency_ms: int) -> DecisionUsage:
        """Add one call. An unknown usage is recorded as unknown and makes the run partial."""
        if latency_ms < 0:
            raise ValueError(f"latency_ms must be non-negative, got {latency_ms}")
        price = self.price_table.price_for(model)
        entry = DecisionUsage(
            model=model,
            usage=usage,
            latency_ms=latency_ms,
            cost_micro_usd=cost_micro_usd(usage, price),
        )
        self.decisions.append(entry)
        return entry

    def record_turn(self, result: TurnResult, *, model: str) -> tuple[DecisionUsage, ...]:
        """Every provider call in one decision turn, in order (FR-13.1)."""
        return tuple(
            self.record(
                model=model,
                usage=attempt.completion.usage,
                latency_ms=attempt.latency_ms,
            )
            for attempt in result.attempts
        )

    @property
    def partial(self) -> bool:
        """Whether any decision's usage was unknown (FR-13.4)."""
        return any(decision.usage is None for decision in self.decisions)

    @property
    def unknown_usage_decisions(self) -> int:
        return sum(1 for decision in self.decisions if decision.usage is None)

    @property
    def total_cost_micro_usd(self) -> int:
        """The known cost. Meaningful as a total only beside 'partial'."""
        return sum(decision.cost_micro_usd or 0 for decision in self.decisions)

    @property
    def total_tokens(self) -> tuple[int, int, int]:
        """Prompt, completion and total tokens over the decisions whose usage is known."""
        prompt = sum(decision.usage.prompt_tokens for decision in self.decisions if decision.usage)
        completion = sum(
            decision.usage.completion_tokens for decision in self.decisions if decision.usage
        )
        return prompt, completion, prompt + completion

    def per_model(self) -> list[dict[str, JsonValue]]:
        """The same arithmetic per model, with its own partial flag."""
        models = sorted({decision.model for decision in self.decisions})
        rows: list[dict[str, JsonValue]] = []
        for model in models:
            mine = [decision for decision in self.decisions if decision.model == model]
            prompt = sum(item.usage.prompt_tokens for item in mine if item.usage)
            completion = sum(item.usage.completion_tokens for item in mine if item.usage)
            rows.append(
                {
                    "model": model,
                    "decisions": len(mine),
                    "prompt_tokens": prompt,
                    "completion_tokens": completion,
                    "total_tokens": prompt + completion,
                    "cost_micro_usd": sum(item.cost_micro_usd or 0 for item in mine),
                    "partial": any(item.usage is None for item in mine),
                }
            )
        return rows

    def to_mapping(self) -> dict[str, JsonValue]:
        prompt, completion, total = self.total_tokens
        return {
            "decisions": len(self.decisions),
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            "cost_micro_usd": self.total_cost_micro_usd,
            "partial": self.partial,
            "unknown_usage_decisions": self.unknown_usage_decisions,
            "per_model": self.per_model(),
            "price_table": self.price_table.to_mapping(),
        }

    def manifest_fragment(self) -> dict[str, JsonValue]:
        """The piece of run.json that records the table the run used (FR-13.2)."""
        return {"price_table": self.price_table.to_mapping()}


__all__: list[str] = [
    "MICRO_USD_PER_UNIT",
    "DecisionUsage",
    "RunAccounting",
    "cost_micro_usd",
]
