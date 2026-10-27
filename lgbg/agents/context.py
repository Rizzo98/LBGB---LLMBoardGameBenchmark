"""Context policy: what the model is shown of the position, and how it is recorded (FR-8).

Full projection every turn is the cleanest context and the most expensive one: on a 743-action game
it pays for the whole board on every decision. The default is therefore a delta projection with a
periodic full refresh, and the two alternatives are explicit policy values rather than emergent
behaviour:

- **full**: the decision surface, including the whole projection, every turn;
- **delta_with_refresh**: a full projection on the first decision and every refresh interval, and
  the delta from the same seat's previous projection in between, with the current decision surface
  appended because the question itself changes every turn;
- **bounded_window**: the last N decision surfaces for that seat.

The builder is stateful only in what it remembers per seat - the previous observation and the recent
surfaces - and that state is exactly what the sidecar's recorded messages make unnecessary for a
reader: the messages sent are stored verbatim, so which strategy produced them is a property of the
manifest, not a guess. The three strategies are declared in core.contracts and one policy object is
shared by every seat and model in a run (FR-8.1 to FR-8.4).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from lgbg.agents.prompting import PromptSet
from lgbg.agents.providers.base import Message, Role
from lgbg.core.contracts import CONTEXT_STRATEGIES
from lgbg.core.delta import render_delta
from lgbg.core.game import Game
from lgbg.core.types import JsonValue, Observation, PlayerId


class ContextStrategy(StrEnum):
    """The three declared ways a run can build the position part of its messages (FR-8.2)."""

    FULL = "full"
    DELTA_WITH_REFRESH = "delta_with_refresh"
    BOUNDED_WINDOW = "bounded_window"


class ContextError(ValueError):
    """The context cannot be built as declared."""


@dataclass(frozen=True, slots=True)
class ContextPolicy:
    """One run's context choice, recorded in the manifest and shared by every seat (FR-8.3)."""

    strategy: ContextStrategy = ContextStrategy.DELTA_WITH_REFRESH
    refresh_every: int = 10
    window: int = 3

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, ContextStrategy):
            raise ContextError(f"unknown context strategy {self.strategy!r}")
        if self.refresh_every < 1:
            raise ContextError("refresh_every must be at least 1")
        if self.window < 1:
            raise ContextError("window must be at least 1")

    def to_mapping(self) -> dict[str, JsonValue]:
        """The policy fields the manifest carries, under the names the shape declares."""
        return {
            "context": self.strategy.value,
            "context_refresh_every": self.refresh_every,
            "context_window": self.window,
        }


class ContextBuilder:
    """Builds the message list for one decision under one declared strategy (FR-8.1).

    A builder belongs to one game: the previous observation and the recent surfaces are per seat,
    because two seats have different projections and a refresh for one is not a refresh for the
    other.
    """

    def __init__(
        self,
        policy: ContextPolicy,
        *,
        game: Game,
    ) -> None:
        self._policy = policy
        self._game = game
        self._previous: dict[PlayerId, Observation] = {}
        self._recent: dict[PlayerId, deque[str]] = {}

    @property
    def policy(self) -> ContextPolicy:
        return self._policy

    def messages(
        self,
        prompts: PromptSet,
        *,
        seat: PlayerId,
        decision: int,
        decision_surface: str,
        observation: Observation,
    ) -> tuple[Message, ...]:
        """The exact messages for one decision, under the declared strategy.

        'decision' is the seat's own zero-based decision index, which is what a refresh interval is
        counted in: a seat that has acted five times refreshes on the same schedule whether or not
        other seats acted in between.
        """
        if decision < 0:
            raise ContextError("a decision index cannot be negative")
        if self._policy.strategy is ContextStrategy.FULL:
            return prompts.initial_messages(decision_surface)
        if self._policy.strategy is ContextStrategy.BOUNDED_WINDOW:
            recent = self._recent.setdefault(seat, deque(maxlen=self._policy.window))
            recent.append(decision_surface)
            return (
                *prompts.system_messages(),
                *(Message(role=Role.USER, content=text) for text in recent),
            )

        previous = self._previous.get(seat)
        self._previous[seat] = observation
        if previous is None or decision % self._policy.refresh_every == 0:
            return prompts.initial_messages(decision_surface)
        content = render_delta(previous, observation)
        surface = self._surface_of(decision_surface, observation)
        if surface:
            content = f"{content}\n\n{surface}"
        return prompts.initial_messages(content)

    def _surface_of(self, decision_surface: str, observation: Observation) -> str:
        """The part of the decision surface that is not the projection.

        The facade renders a decision as the game's own projection followed by the asking line and
        the level's domains or actions. Recomputing that projection here is what lets the delta
        replace it while the question keeps travelling (FR-8.2).
        """
        projection = self._game.render(observation)
        if not decision_surface.startswith(projection):
            raise ContextError(
                "the decision surface does not begin with the seat's projection; the context "
                "cannot be split into a delta and a question"
            )
        return decision_surface[len(projection) :].strip("\n")


if {strategy.value for strategy in ContextStrategy} != set(CONTEXT_STRATEGIES):
    raise RuntimeError(
        "the context strategies and the declared manifest vocabulary have drifted apart"
    )


__all__: Final[list[str]] = [
    "ContextBuilder",
    "ContextError",
    "ContextPolicy",
    "ContextStrategy",
]
