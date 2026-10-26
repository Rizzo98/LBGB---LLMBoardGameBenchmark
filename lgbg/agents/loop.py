"""The decision turn: one conversation, one action, and no help that was not configured (FR-6).

A decision turn is the unit the benchmark measures. It starts with the messages the caller built and
ends in exactly one of four ways:

- the engine accepts an action;
- the redo budget is exhausted;
- the step budget is exhausted;
- the decision timeout fires.

Everything between is the model's conversation. The loop appends the assistant's answer and the tool
results, and calls the provider again. It never invents a tool result, never re-reads state on the
model's behalf, never summarises the transcript and never adds a hint: those are the confounds
ARCHITECTURE.md section 13 forbids, and the only help the model gets is the tools the surface was
configured to offer (FR-6.6).

The loop knows one provider method and one surface protocol. It has no branch on a provider, a game
or a model: a new adapter passes the conformance suite (K-018) and the loop does not change.

**Budgets are attempts, not calls.** The step budget counts provider calls, so a runaway that keeps
reading is stopped. The redo budget counts refused actions, so a model that reads more does not lose
retries. The distinction matters because the two failures mean different things (FR-7.9).

**Reads are data.** A read tool call is executed only when the model makes it, through the surface,
and its result is appended as a tool message. When reads are not configured they are not offered and
a call to one is answered as an error, not served.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from lgbg.agents.providers.base import (
    Completion,
    CompletionConfig,
    Message,
    Provider,
    ProviderTimeoutError,
    Role,
    ToolCall,
)
from lgbg.agents.surface import AgentSurface


class TurnOutcome(StrEnum):
    """How one decision turn ended. The first four are the endings FR-6.1 declares."""

    ACCEPTED = "accepted"
    REDO_EXHAUSTED = "redo_exhausted"
    STEP_BUDGET = "step_budget"
    TIMEOUT = "timeout"
    NO_ACTION = "no_action"


@dataclass(frozen=True, slots=True)
class TurnPolicy:
    """The budgets a decision turn is run under, recorded in the manifest (FR-6.3, FR-7.3)."""

    step_budget: int = 8
    redo_budget: int = 3
    decision_timeout_s: float = 120.0

    def __post_init__(self) -> None:
        if self.step_budget < 1:
            raise ValueError("step_budget must be at least 1")
        if self.redo_budget < 1:
            raise ValueError("redo_budget must be at least 1")
        if self.decision_timeout_s <= 0:
            raise ValueError("decision_timeout_s must be positive")


@dataclass(frozen=True, slots=True)
class Attempt:
    """One provider call: what it was sent, what it answered and how long it took (FR-10.4)."""

    index: int
    completion: Completion
    latency_ms: int
    messages: tuple[Message, ...] = ()


@dataclass(frozen=True, slots=True)
class TurnResult:
    """What a decision turn produced, including the conversation that produced it."""

    outcome: TurnOutcome
    messages: tuple[Message, ...]
    attempts: tuple[Attempt, ...]
    action: ToolCall | None = None
    rejection: str | None = None
    redo_attempts: int = 0
    failure: str | None = None

    @property
    def accepted(self) -> bool:
        return self.outcome is TurnOutcome.ACCEPTED


@dataclass(slots=True)
class _State:
    """The mutable conversation, kept local to one turn and returned as a frozen result."""

    messages: list[Message]
    attempts: list[Attempt] = field(default_factory=list)
    calls: int = 0
    redo_attempts: int = 0
    action: ToolCall | None = None
    rejection: str | None = None

    def result(self, outcome: TurnOutcome, *, failure: str | None = None) -> TurnResult:
        return TurnResult(
            outcome=outcome,
            messages=tuple(self.messages),
            attempts=tuple(self.attempts),
            action=self.action,
            rejection=self.rejection,
            redo_attempts=self.redo_attempts,
            failure=failure,
        )


class DecisionTurn:
    """One provider-agnostic conversation about one open decision (FR-6.1 to FR-6.6)."""

    def __init__(
        self,
        provider: Provider,
        surface: AgentSurface,
        *,
        policy: TurnPolicy | None = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._provider = provider
        self._surface = surface
        self._policy = policy or TurnPolicy()
        self._clock = _monotonic_millis if clock is None else clock

    async def run(
        self,
        messages: Sequence[Message],
        config: CompletionConfig,
    ) -> TurnResult:
        """Run one turn to one of its declared endings. The provider is called one at a time."""
        if not messages:
            raise ValueError("a decision turn needs at least one message")
        state = _State(messages=list(messages))
        try:
            return await asyncio.wait_for(
                self._converse(state, config), timeout=self._policy.decision_timeout_s
            )
        except TimeoutError:
            return state.result(TurnOutcome.TIMEOUT, failure="timeout")

    async def _converse(self, state: _State, config: CompletionConfig) -> TurnResult:
        while state.calls < self._policy.step_budget:
            started = self._clock()
            try:
                completion = await self._provider.complete(
                    state.messages, self._surface.tools, config
                )
            except ProviderTimeoutError:
                return state.result(TurnOutcome.TIMEOUT, failure="timeout")
            latency = max(0, self._clock() - started)
            state.calls += 1
            state.attempts.append(
                Attempt(
                    index=state.calls,
                    completion=completion,
                    latency_ms=latency,
                    messages=tuple(state.messages),
                )
            )
            state.messages.append(
                Message(
                    role=Role.ASSISTANT,
                    content=completion.text,
                    tool_calls=completion.tool_calls,
                )
            )
            calls = tuple(completion.tool_calls or ())
            if not calls:
                return state.result(TurnOutcome.NO_ACTION, failure="no_action")
            for position, call in enumerate(calls):
                if call.name in self._surface.read_names:
                    answer = await self._surface.read(call)
                    state.messages.append(_tool_message(call, answer.payload))
                    continue
                answer = await self._surface.act(call)
                state.messages.append(_tool_message(call, answer.payload))
                if answer.accepted:
                    state.action = call
                    return state.result(TurnOutcome.ACCEPTED)
                state.redo_attempts += 1
                state.rejection = answer.rejection
                if state.redo_attempts >= self._policy.redo_budget:
                    _unanswered(state, calls[position + 1 :])
                    return state.result(TurnOutcome.REDO_EXHAUSTED, failure="redo_exhausted")
                _unanswered(state, calls[position + 1 :])
                break
        return state.result(TurnOutcome.STEP_BUDGET, failure="step_budget")


def _tool_message(call: ToolCall, payload: str) -> Message:
    return Message(role=Role.TOOL, content=payload, tool_call_id=call.id)


def _unanswered(state: _State, calls: Sequence[ToolCall]) -> None:
    """Answer the tool calls this response made after the action, so the transcript stays valid."""
    for call in calls:
        state.messages.append(_tool_message(call, '{"ok":false,"error":"NOT_EXECUTED"}'))


def _monotonic_millis() -> int:
    return time.monotonic_ns() // 1_000_000


__all__: Final[list[str]] = [
    "Attempt",
    "DecisionTurn",
    "TurnOutcome",
    "TurnPolicy",
    "TurnResult",
]
