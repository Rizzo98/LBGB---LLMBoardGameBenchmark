"""Core data types shared across the runtime (ARCHITECTURE.md section 5).

'JsonValue' is the boundary type of the whole system: actions arrive as JSON, state is
encoded to JSON for hashing, and records are JSON lines on disk. Anything that crosses a
boundary is a JsonValue and nothing else.

Arrays and objects are typed as 'Sequence' and 'Mapping' rather than 'list' and 'dict', so
that an ordinary literal - {"edge": 17}, [1, 2, 3] - is accepted without a cast. They are
read-only at every boundary: 'core.canonical.to_canonical_json' is what turns them into
concrete arrays and objects, and it rejects anything that is not JSON.

'State' is deliberately untyped here. State is game-specific, and a core that knew its
shape would not be game-agnostic (P11); plugins state their own state type, and the
protocol is stated over 'Any' at this boundary only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

type JsonValue = bool | int | str | Sequence[JsonValue] | Mapping[str, JsonValue] | None

type JsonSchema = Mapping[str, JsonValue]
"""A JSON Schema document, declared by a plugin as data (ARCHITECTURE.md section 7.3)."""

type State = Any
"""Game-specific state, opaque to the core (P11)."""

type GameId = str
"""e.g. "g-0001"."""

type PlayerId = int
"""Seat index. Seat order is additionally the tie-break ordering."""

type Seq = int
"""Monotonically increasing, starting at 0 for the initial state."""

type Component = str
"""A game-declared component: a piece, a resource, a card (ARCHITECTURE.md section 7.2)."""

PHASE_STARTED_EVENT: Final[str] = "phase_started"
"""The event a game emits when it enters a phase.

The runtime keys on this name to write its own phase record (ARCHITECTURE.md section 8.4):
the record is redundant with the event, but it makes a record greppable and replay
debuggable. A game therefore announces a transition with this event type, and no game may
introduce a record type of its own (FR-3.9).
"""

type Observation = Mapping[str, JsonValue]
"""What one observer may see. Built from an allow-list, never a deny-list."""


@dataclass(frozen=True, slots=True)
class Action:
    """An intent from outside the world, and therefore untrusted (ARCHITECTURE.md 5.2)."""

    player: PlayerId
    type: str
    params: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class Event:
    """The narrative of the game, and by contract sufficient to describe every change."""

    type: str
    payload: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    """A decision addressed to one player (ARCHITECTURE.md section 5.6).

    The central abstraction: several may be open at once, some to players who are out of
    turn.
    """

    request_id: str
    player: PlayerId
    kind: str
    schema_ref: str
    context: Mapping[str, JsonValue]
    phase: str


@dataclass(frozen=True, slots=True)
class ParamDomain:
    """The permitted values of one action parameter (ARCHITECTURE.md section 7.2)."""

    kind: str
    values: Sequence[JsonValue] | None = None
    lo: int | None = None
    hi: int | None = None


@dataclass(frozen=True, slots=True)
class ActionDomain:
    """What an action type costs and what its parameters may be.

    Deliberately cross-product-free: "this action is available, and here is the permitted
    set for each parameter", not an enumeration of every resulting action.
    """

    type: str
    cost: Mapping[Component, int] | None = None
    params: Mapping[str, ParamDomain] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Outcome:
    """The game's own verdict. The runtime adds record-level counts (actions, rejections)."""

    winner: PlayerId | None
    scores: Mapping[str, int]
    rounds: int
