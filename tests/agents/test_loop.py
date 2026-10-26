"""The decision turn: one conversation, four endings, no unconfigured help (PRD-v2 FR-6).

The loop is the place where a convenience becomes a confound. These tests hold it to the narrow
contract: it appends only what the provider said and what the surface answered, it calls one
provider at a time, it stops on the budget it was given, and it never reads unless asked.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from lgbg.agents.loop import DecisionTurn, TurnOutcome, TurnPolicy, TurnResult
from lgbg.agents.providers.base import (
    Completion,
    CompletionConfig,
    Message,
    Provider,
    ProviderTimeoutError,
    Role,
    ToolCall,
    ToolSpec,
    Usage,
)
from lgbg.agents.surface import ToolAnswer

CONFIG = CompletionConfig(model="test-model")
MESSAGES = [
    Message(role=Role.SYSTEM, content="You are playing."),
    Message(role=Role.USER, content="It is your turn."),
]
ACTION = ToolCall(id="call-1", name="take", arguments={})
READ = ToolCall(id="call-read", name="read_state", arguments={})
USAGE = Usage(prompt_tokens=3, completion_tokens=4, total_tokens=7)
ACTION_TOOL = ToolSpec(
    name="take",
    description="the take action of fixture",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
)
READ_TOOL = ToolSpec(
    name="read_state",
    description="Read your current projection of the game.",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
)


@dataclass
class Surface:
    """A surface whose reads and answers are scripted, so the loop is the only thing under test."""

    replies: list[ToolAnswer] = field(default_factory=list)
    reads_enabled: bool = True
    read_payload: str = "the state"
    acts: list[ToolCall] = field(default_factory=list)
    reads: list[ToolCall] = field(default_factory=list)

    @property
    def tools(self) -> Sequence[ToolSpec]:
        return [ACTION_TOOL, READ_TOOL] if self.reads_enabled else [ACTION_TOOL]

    @property
    def read_names(self) -> frozenset[str]:
        return frozenset({"read_state"}) if self.reads_enabled else frozenset()

    async def read(self, call: ToolCall) -> ToolAnswer:
        self.reads.append(call)
        return ToolAnswer(accepted=True, payload=self.read_payload)

    async def act(self, call: ToolCall) -> ToolAnswer:
        self.acts.append(call)
        if not self.replies:
            raise AssertionError("the surface was asked for more actions than it has answers")
        return self.replies.pop(0)


class Scripted:
    """A provider that returns a fixed sequence of completions and counts its calls."""

    def __init__(self, completions: Sequence[Completion]) -> None:
        self._completions = list(completions)
        self.calls = 0
        self.seen: list[tuple[Message, ...]] = []

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        config: CompletionConfig,
    ) -> Completion:
        del tools, config
        self.calls += 1
        self.seen.append(tuple(messages))
        if not self._completions:
            raise AssertionError("the provider was asked for more completions than it has")
        return self._completions.pop(0)


class Slow:
    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        config: CompletionConfig,
    ) -> Completion:
        del messages, tools, config
        await asyncio.sleep(1)
        return _completion(ACTION)


class Timeout:
    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        config: CompletionConfig,
    ) -> Completion:
        del messages, tools, config
        raise ProviderTimeoutError("slow")


def _completion(call: ToolCall | None, *, text: str | None = None) -> Completion:
    return Completion(
        text=text,
        tool_calls=None if call is None else (call,),
        usage=USAGE,
    )


def run(provider: Provider, surface: Surface, *, policy: TurnPolicy | None = None) -> TurnResult:
    turn = DecisionTurn(provider, surface, policy=policy)
    return asyncio.run(turn.run(MESSAGES, CONFIG))


def test_an_accepted_action_ends_the_turn() -> None:
    surface = Surface(replies=[ToolAnswer(accepted=True, payload='{"ok":true}')])
    provider = Scripted([_completion(ACTION)])

    result = run(provider, surface)

    assert result.outcome is TurnOutcome.ACCEPTED
    assert result.action == ACTION
    assert result.attempts[0].index == 1
    assert surface.acts == [ACTION]
    assert surface.reads == []
    assert result.messages[-1].role is Role.TOOL
    assert result.messages[-1].content == '{"ok":true}'
    assert result.messages[-1].tool_call_id == ACTION.id


def test_a_rejection_is_retried_inside_the_same_conversation() -> None:
    surface = Surface(
        replies=[
            ToolAnswer(accepted=False, payload='{"ok":false,"error":"NO"}', rejection="NO"),
            ToolAnswer(accepted=True, payload='{"ok":true}'),
        ]
    )
    provider = Scripted([_completion(ACTION), _completion(ACTION)])

    result = run(provider, surface)

    assert result.outcome is TurnOutcome.ACCEPTED
    assert result.redo_attempts == 1
    assert provider.calls == 2
    assert surface.acts == [ACTION, ACTION]
    rejection = result.messages[-3]
    assert rejection.role is Role.TOOL
    assert rejection.content == '{"ok":false,"error":"NO"}'


def test_redo_exhaustion_ends_the_turn_and_keeps_the_last_rejection() -> None:
    surface = Surface(
        replies=[
            ToolAnswer(accepted=False, payload='{"ok":false,"error":"NO"}', rejection="NO"),
            ToolAnswer(accepted=False, payload='{"ok":false,"error":"NO"}', rejection="NO"),
            ToolAnswer(accepted=False, payload='{"ok":false,"error":"NO"}', rejection="NO"),
        ]
    )
    provider = Scripted([_completion(ACTION), _completion(ACTION), _completion(ACTION)])

    result = run(provider, surface, policy=TurnPolicy(redo_budget=2))

    assert result.outcome is TurnOutcome.REDO_EXHAUSTED
    assert result.redo_attempts == 2
    assert provider.calls == 2
    assert result.rejection == "NO"


def test_the_step_budget_stops_a_runaway_that_only_reads() -> None:
    surface = Surface()
    provider = Scripted([_completion(READ) for _ in range(10)])

    result = run(provider, surface, policy=TurnPolicy(step_budget=3))

    assert result.outcome is TurnOutcome.STEP_BUDGET
    assert provider.calls == 3
    assert len(surface.reads) == 3
    assert result.redo_attempts == 0, "reads are not illegal actions"
    assert len(result.attempts) == 3


def test_a_read_is_executed_only_when_the_model_asks() -> None:
    surface = Surface(replies=[ToolAnswer(accepted=True, payload='{"ok":true}')])
    provider = Scripted([_completion(READ), _completion(ACTION)])

    result = run(provider, surface)

    assert result.outcome is TurnOutcome.ACCEPTED
    assert surface.reads == [READ]
    assert surface.acts == [ACTION]
    assert result.messages[3].role is Role.TOOL
    assert result.messages[3].content == "the state"


def test_a_read_is_not_served_when_reads_are_not_configured() -> None:
    surface = Surface(
        replies=[
            ToolAnswer(
                accepted=False, payload='{"ok":false,"error":"UNKNOWN"}', rejection="UNKNOWN"
            )
        ],
        reads_enabled=False,
    )
    provider = Scripted([_completion(READ)])

    result = run(provider, surface, policy=TurnPolicy(redo_budget=1))

    assert result.outcome is TurnOutcome.REDO_EXHAUSTED
    assert surface.reads == [], "an unconfigured read must not reach the facade"
    assert surface.acts == [READ]


def test_the_decision_timeout_ends_the_turn() -> None:
    surface = Surface()

    result = run(Slow(), surface, policy=TurnPolicy(decision_timeout_s=0.05))

    assert result.outcome is TurnOutcome.TIMEOUT
    assert result.failure == "timeout"


def test_a_provider_timeout_is_the_decision_timeout() -> None:
    surface = Surface()

    result = run(Timeout(), surface)

    assert result.outcome is TurnOutcome.TIMEOUT
    assert result.failure == "timeout"


def test_prose_without_a_tool_call_is_recorded_and_not_coerced() -> None:
    surface = Surface()
    provider = Scripted([_completion(None, text="I pass.")])

    result = run(provider, surface)

    assert result.outcome is TurnOutcome.NO_ACTION
    assert result.action is None
    assert surface.acts == []
    assert result.messages[-1].content == "I pass."


def test_the_loop_appends_no_help_of_its_own() -> None:
    surface = Surface(replies=[ToolAnswer(accepted=True, payload='{"ok":true}')])
    provider = Scripted([_completion(ACTION)])

    result = run(provider, surface)

    added = result.messages[len(MESSAGES) :]
    assert {message.role for message in added} <= {Role.ASSISTANT, Role.TOOL}
    assert all(message.role not in {Role.SYSTEM, Role.USER} for message in added)


def test_the_loop_names_no_provider_or_transport() -> None:
    from pathlib import Path

    source = Path(__file__).resolve().parents[2] / "lgbg" / "agents" / "loop.py"
    text = source.read_text(encoding="utf-8").lower()

    for forbidden in ("openrouter", "mockprovider", "facadesurface", "httpx", "mcp"):
        assert forbidden not in text, f"the loop branches on {forbidden!r}"


def test_a_turn_needs_a_message() -> None:
    turn = DecisionTurn(Scripted([]), Surface())

    with pytest.raises(ValueError, match="message"):
        asyncio.run(turn.run([], CONFIG))
