"""The randomness seam (ARCHITECTURE.md section 5.4; PRD-v1 FR-2.1 to FR-2.7).

All randomness in the engine flows through an injected RandomSource. Nothing else may
import 'random' - the lint gate enforces that, because ambient randomness makes a result
unreproducible and untraceable.

Every draw carries a semantic 'purpose' label, and the three implementations exist to make
three different things true:

- SeededRandomSource drives a real game and records every draw it performs.
- ReplayRandomSource drives a replay and returns the recorded draws in order, refusing to
  continue when the purpose, kind or arguments disagree with the record. A positional
  stream would silently desynchronise and produce a *different but plausible* game; a
  labelled stream turns that into an immediate, localised error naming the action.
- NullRandomSource refuses every draw, so a test can prove that a code path - observe,
  legal_actions, action_domains, pending_decisions, check_invariants, outcome - performs
  none.

Draw values are recorded as canonical JSON, so a recorded draw is exactly what a record
can carry. The *shape* of a recorded draw is the log reader's business; here we compare
what was asked for against what was recorded.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, NoReturn, Protocol, TypeVar, cast

from lgbg.core.canonical import normalise
from lgbg.core.types import JsonValue

KIND_RANDINT: Final[str] = "randint"
KIND_CHOICE: Final[str] = "choice"
KIND_SHUFFLE: Final[str] = "shuffle"

type Purpose = str
"""A semantic label for one random draw, e.g. 'dice_roll' or 'steal'.

Labels are module-level constants at the call site, never inline strings (FR-2.3): a label
identifies a call site, and only a named label can be renamed safely or listed in a
declaration.
"""

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RngDraw:
    """One random draw, as recorded in a game record (ARCHITECTURE.md section 5.4)."""

    purpose: Purpose
    kind: str
    args: Mapping[str, JsonValue]
    value: JsonValue


class RngError(Exception):
    """Base class for every randomness failure."""


class RngMismatchError(RngError):
    """A draw does not match the recorded draw at this position of this action."""


class UnconsumedDrawsError(RngError):
    """The record holds draws that the replayed action never asked for."""


class RandomSource(Protocol):
    """The injected source of randomness (ARCHITECTURE.md section 5.4)."""

    def randint(self, lo: int, hi: int, *, purpose: Purpose) -> int: ...

    def choice(self, items: Sequence[T], *, purpose: Purpose) -> T: ...

    def shuffle(self, items: Sequence[T], *, purpose: Purpose) -> list[T]: ...

    def draws(self) -> list[RngDraw]: ...


class SeededRandomSource:
    """Drives a real game from a seed, recording every draw it performs.

    Wraps a *local* random.Random instance; the module-global functions are banned because
    they are ambient state shared with every other caller in the process.
    """

    def __init__(self, seed: int) -> None:
        self._random = random.Random(seed)
        self._draws: list[RngDraw] = []

    def randint(self, lo: int, hi: int, *, purpose: Purpose) -> int:
        value = self._random.randint(lo, hi)
        self._draws.append(
            RngDraw(purpose=purpose, kind=KIND_RANDINT, args={"lo": lo, "hi": hi}, value=value)
        )
        return value

    def choice(self, items: Sequence[T], *, purpose: Purpose) -> T:
        if not items:
            raise RngError(
                f"choice with an empty sequence (purpose {purpose!r}): there is nothing to choose"
            )
        value = self._random.choice(list(items))
        self._draws.append(
            RngDraw(
                purpose=purpose,
                kind=KIND_CHOICE,
                args={"n": len(items)},
                value=normalise(value),
            )
        )
        return value

    def shuffle(self, items: Sequence[T], *, purpose: Purpose) -> list[T]:
        shuffled = list(items)
        self._random.shuffle(shuffled)
        self._draws.append(
            RngDraw(
                purpose=purpose,
                kind=KIND_SHUFFLE,
                args={"n": len(items)},
                value=normalise(shuffled),
            )
        )
        return shuffled

    def draws(self) -> list[RngDraw]:
        """Every draw performed so far, in order.

        A copy, so a caller cannot edit the record. The engine takes one action's window by
        slicing on the length before the action.
        """
        return list(self._draws)


class ReplayRandomSource:
    """Drives a replay from the draws one action recorded.

    Constructed per action, with that action's recorded draws: the draw list is exhausted
    exactly at the end of the action, or 'assert_exhausted' says so (FR-2.5).
    """

    def __init__(self, draws: Sequence[RngDraw], *, action: str) -> None:
        self._draws = list(draws)
        self._action = action
        self._cursor = 0

    def randint(self, lo: int, hi: int, *, purpose: Purpose) -> int:
        draw = self._take(purpose, KIND_RANDINT, {"lo": lo, "hi": hi})
        return cast(int, draw.value)

    def choice(self, items: Sequence[T], *, purpose: Purpose) -> T:
        draw = self._take(purpose, KIND_CHOICE, {"n": len(items)})
        return cast(T, draw.value)

    def shuffle(self, items: Sequence[T], *, purpose: Purpose) -> list[T]:
        draw = self._take(purpose, KIND_SHUFFLE, {"n": len(items)})
        return cast(list[T], draw.value)

    def draws(self) -> list[RngDraw]:
        return list(self._draws)

    def assert_exhausted(self) -> None:
        """Assert the action consumed exactly the draws the record holds."""
        remaining = self._draws[self._cursor :]
        if remaining:
            raise UnconsumedDrawsError(
                f"action {self._action}: the record holds {len(self._draws)} draw(s) but "
                f"replay consumed {self._cursor}; draw #{self._cursor} "
                f"(purpose {remaining[0].purpose!r}) was never requested"
            )

    def _take(self, purpose: Purpose, kind: str, args: Mapping[str, JsonValue]) -> RngDraw:
        index = self._cursor
        if index >= len(self._draws):
            raise RngMismatchError(
                f"action {self._action} draw #{index}: no recorded draw; the record holds "
                f"{len(self._draws)} draw(s) and replay asked for another ({purpose!r})"
            )
        recorded = self._draws[index]
        if recorded.purpose != purpose:
            raise RngMismatchError(
                f"action {self._action} draw #{index}: expected purpose "
                f"{recorded.purpose!r}, got {purpose!r}"
            )
        if recorded.kind != kind:
            raise RngMismatchError(
                f"action {self._action} draw #{index}: expected kind {recorded.kind!r}, "
                f"got {kind!r}"
            )
        if dict(recorded.args) != dict(args):
            raise RngMismatchError(
                f"action {self._action} draw #{index}: expected args "
                f"{dict(recorded.args)!r}, got {dict(args)!r}"
            )
        self._cursor += 1
        return recorded


class NullRandomSource:
    """Refuses every draw, proving that a code path performs none (FR-2.6)."""

    def randint(self, lo: int, hi: int, *, purpose: Purpose) -> int:
        self._refuse(purpose)

    def choice(self, items: Sequence[T], *, purpose: Purpose) -> T:
        self._refuse(purpose)

    def shuffle(self, items: Sequence[T], *, purpose: Purpose) -> list[T]:
        self._refuse(purpose)

    def draws(self) -> list[RngDraw]:
        return []

    def _refuse(self, purpose: Purpose) -> NoReturn:
        raise RngError(
            f"NullRandomSource was asked for a draw (purpose {purpose!r}): "
            "this code path must be deterministic"
        )
