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

**A refusal is answered in the same conversation (FR-7.1).** The engine's refusal is appended as the
tool result, then the one shared redo prompt is appended as a user message, and the provider is
called again. There is no new turn and no substituted action: the model keeps the transcript it
built and chooses again. The redo callable is injected rather than imported, so the loop still knows
no prompt file and no provider (FR-7.2, FR-9.6).

**Reads are data.** A read tool call is executed only when the model makes it, through the surface,
and its result is appended as a tool message. When reads are not configured they are not offered and
a call to one is answered as an error, not served.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
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
from lgbg.agents.wire import WireExchange


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


class AttemptOutcome(StrEnum):
    """What one provider call produced: an action, a read, a refusal or a failure.

    A call is the unit recorded in the sidecar, because a call is the unit of model interaction
    (FR-10.3). 'attempt' is narrower: it counts the submissions against the redo budget, so a read
    made before acting belongs to the same attempt as the action that follows it.
    """

    ACTION = "action"
    READ = "read"
    REJECTION = "rejection"
    FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class Attempt:
    """One provider call: what it was sent, what it answered and how long it took (FR-10.4).

    The call carries the attempt it belongs to and the refusal that prompted it, so a redo can be
    reconstructed attempt by attempt rather than inferred from the final record (FR-7.3, FR-10.3).
    """

    index: int
    completion: Completion | None
    latency_ms: int
    messages: tuple[Message, ...] = ()
    attempt: int = 1
    outcome: AttemptOutcome = AttemptOutcome.ACTION
    rejection: str | None = None
    prompted_by: str | None = None
    prompted_by_attempt: int | None = None
    failure: str | None = None
    wire: WireExchange | None = None
    """The exact exchange, when there is no completion to carry it (a timeout, FR-5.4)."""


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
    prompted_by: str | None = None
    prompted_by_attempt: int | None = None

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
        redo: Callable[[str], str] | None = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._provider = provider
        self._surface = surface
        self._policy = policy or TurnPolicy()
        self._redo = redo
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
            state.calls += 1
            state.attempts.append(
                Attempt(
                    index=state.calls,
                    attempt=state.redo_attempts + 1,
                    completion=None,
                    latency_ms=0,
                    messages=tuple(state.messages),
                    outcome=AttemptOutcome.FAILURE,
                    prompted_by=state.prompted_by,
                    prompted_by_attempt=state.prompted_by_attempt,
                    failure="timeout",
                )
            )
            return state.result(TurnOutcome.TIMEOUT, failure="timeout")

    async def _converse(self, state: _State, config: CompletionConfig) -> TurnResult:
        while state.calls < self._policy.step_budget:
            attempt = state.redo_attempts + 1
            sent = tuple(state.messages)
            started = self._clock()
            try:
                completion = await self._provider.complete(
                    state.messages, self._surface.tools, config
                )
            except ProviderTimeoutError as error:
                return self._timed_out(
                    state,
                    started=started,
                    sent=sent,
                    attempt=attempt,
                    wire=error.wire,
                )
            latency = max(0, self._clock() - started)
            state.calls += 1
            state.messages.append(
                Message(
                    role=Role.ASSISTANT,
                    content=completion.text,
                    tool_calls=completion.tool_calls,
                )
            )
            calls = tuple(completion.tool_calls or ())
            if not calls:
                state.attempts.append(
                    _attempt(
                        state,
                        sent=sent,
                        completion=completion,
                        latency_ms=latency,
                        attempt=attempt,
                        outcome=AttemptOutcome.FAILURE,
                        failure="no_action",
                    )
                )
                return state.result(TurnOutcome.NO_ACTION, failure="no_action")

            acted = False
            for position, call in enumerate(calls):
                if call.name in self._surface.read_names:
                    answer = await self._surface.read(call)
                    state.messages.append(_tool_message(call, answer.payload))
                    continue
                acted = True
                answer = await self._surface.act(call)
                state.messages.append(_tool_message(call, answer.payload))
                if answer.accepted:
                    state.action = call
                    state.attempts.append(
                        _attempt(
                            state,
                            sent=sent,
                            completion=completion,
                            latency_ms=latency,
                            attempt=attempt,
                            outcome=AttemptOutcome.ACTION,
                        )
                    )
                    return state.result(TurnOutcome.ACCEPTED)

                state.redo_attempts += 1
                exhausted = state.redo_attempts >= self._policy.redo_budget
                state.attempts.append(
                    _attempt(
                        state,
                        sent=sent,
                        completion=completion,
                        latency_ms=latency,
                        attempt=attempt,
                        outcome=AttemptOutcome.REJECTION,
                        rejection=answer.rejection,
                        failure=answer.failure or ("redo_exhausted" if exhausted else None),
                    )
                )
                state.rejection = answer.rejection
                state.prompted_by = answer.rejection
                state.prompted_by_attempt = attempt
                _unanswered(state, calls[position + 1 :])
                if exhausted:
                    return state.result(TurnOutcome.REDO_EXHAUSTED, failure="redo_exhausted")
                if self._redo is not None and answer.rejection is not None:
                    state.messages.append(
                        Message(role=Role.USER, content=self._redo(answer.rejection))
                    )
                break

            if not acted:
                state.attempts.append(
                    _attempt(
                        state,
                        sent=sent,
                        completion=completion,
                        latency_ms=latency,
                        attempt=attempt,
                        outcome=AttemptOutcome.READ,
                    )
                )

        if state.attempts:
            last = state.attempts[-1]
            state.attempts[-1] = replace(last, outcome=AttemptOutcome.FAILURE, failure="runaway")
        return state.result(TurnOutcome.STEP_BUDGET, failure="runaway")

    def _timed_out(
        self,
        state: _State,
        *,
        started: int,
        sent: tuple[Message, ...],
        attempt: int,
        wire: WireExchange | None,
    ) -> TurnResult:
        """A provider timeout ends the turn and is recorded as the failed call it was (FR-7.8).

        There is no completion to carry the exchange, so the call keeps the exchange the adapter
        attached to its error. A timeout with no exchange is recorded as null rather than
        pretending a response existed (FR-5.4).
        """
        latency = max(0, self._clock() - started)
        state.calls += 1
        state.attempts.append(
            Attempt(
                index=state.calls,
                attempt=attempt,
                completion=None,
                latency_ms=latency,
                messages=sent,
                outcome=AttemptOutcome.FAILURE,
                prompted_by=state.prompted_by,
                prompted_by_attempt=state.prompted_by_attempt,
                failure="timeout",
                wire=wire,
            )
        )
        return state.result(TurnOutcome.TIMEOUT, failure="timeout")


def _attempt(
    state: _State,
    *,
    sent: tuple[Message, ...],
    completion: Completion,
    latency_ms: int,
    attempt: int,
    outcome: AttemptOutcome,
    rejection: str | None = None,
    failure: str | None = None,
) -> Attempt:
    """One provider call, carrying the attempt it belongs to and what prompted it."""
    return Attempt(
        index=state.calls,
        attempt=attempt,
        completion=completion,
        latency_ms=latency_ms,
        messages=sent,
        outcome=outcome,
        rejection=rejection,
        prompted_by=state.prompted_by,
        prompted_by_attempt=state.prompted_by_attempt,
        failure=failure,
    )


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
    "AttemptOutcome",
    "DecisionTurn",
    "TurnOutcome",
    "TurnPolicy",
    "TurnResult",
]
