"""The price table a run used, in the unit every artefact records (FR-5.9, FR-13.2).

Money is integer micro-dollars per million tokens, because the canonical serialiser refuses floats
and a price that drifts silently makes every cost comparison meaningless. The table is data: it is
read from the gateway, stamped with the moment it was read, and carried into the manifest. Cost
accounting asks this module for a model's price rather than importing a provider.

Keeping the table here rather than in an adapter means a run's accounting does not depend on which
gateway produced the prices; a second provider's table is the same shape.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from lgbg.core.contracts import PRICE_UNITS
from lgbg.core.types import JsonValue

PRICE_UNIT: Final[str] = PRICE_UNITS[0]
"""The manifest's price unit: integer micro-dollars per million tokens."""


class UnknownPriceError(LookupError):
    """The table has no price for that model. A cost of zero would be an invented price."""


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """One model's price in the unit the manifest declares."""

    model: str
    prompt: int
    completion: int

    def __post_init__(self) -> None:
        if not self.model:
            raise ValueError("a price must name its model")
        for name in ("prompt", "completion"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer, got {value!r}")

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"model": self.model, "prompt": self.prompt, "completion": self.completion}


@dataclass(frozen=True, slots=True)
class PriceTable:
    """The prices a run used, and when they were read (FR-5.9, FR-13.2)."""

    source: str
    read_at: str
    unit: str
    models: tuple[ModelPrice, ...]

    def __post_init__(self) -> None:
        if self.unit not in PRICE_UNITS:
            raise ValueError(f"price unit {self.unit!r} is not one of {PRICE_UNITS}")
        if not self.models:
            raise ValueError("a price table needs at least one model")
        if len({price.model for price in self.models}) != len(self.models):
            raise ValueError("a price table names each model once")

    def price_for(self, model: str) -> ModelPrice:
        """That model's price, refusing an absent one rather than treating it as free."""
        for price in self.models:
            if price.model == model:
                return price
        known = sorted(price.model for price in self.models)
        raise UnknownPriceError(f"no price for {model!r}; the table names {known}")

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "source": self.source,
            "read_at": self.read_at,
            "unit": self.unit,
            "models": [price.to_mapping() for price in self.models],
        }


def table_of(source: str, read_at: str, models: Sequence[ModelPrice]) -> PriceTable:
    """A table in the one unit, so a caller cannot pass a different one by accident."""
    return PriceTable(source=source, read_at=read_at, unit=PRICE_UNIT, models=tuple(models))


__all__: list[str] = [
    "PRICE_UNIT",
    "ModelPrice",
    "PriceTable",
    "UnknownPriceError",
    "table_of",
]
