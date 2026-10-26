"""The mock provider: every behaviour a model can have, named (PRD-v2 FR-5.2, FR-15.1).

Slice 5 is where a model behaves badly, and none of it is testable against a real provider without
spending money and waiting for a network. The mock is therefore not a convenience double: it is the
fixture the failure policy is built on. Each behaviour is a named value, so a failure kind in a
record can be traced back to the behaviour that produced it.

The behaviours are scripted rather than clever. The mock has no opinion about Catan or legality:
the caller supplies the action it should emit, or the mock emits prose, malformed arguments, a
timeout or an endless series of calls. That keeps the double honest - it cannot accidentally
"play well" because it knows the game. A correct-play script is a sequence of actions, one per
decision turn, and asking beyond its end is loud rather than a repeat of the last move: a script
that has run out is a test that made one decision too many, not a model that suddenly improvised.

No behaviour touches the network, the clock or the environment (PRD-v2 FR-15.4, NFR-8).
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Final

from lgbg.agents.providers.base import (
    CallMetadata,
    Completion,
    CompletionConfig,
    Message,
    ProviderError,
    ProviderTimeoutError,
    ToolCall,
    ToolSpec,
    Usage,
)
from lgbg.agents.wire import WireExchange, encode_request

NAME: Final[str] = "mock"
VERSION: Final[str] = "1"

DEFAULT_USAGE: Final[Usage] = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
"""What the mock reports unless a test asks it to omit usage (FR-5.6)."""

MALFORMED_ARGUMENTS: Final[str] = "{not json"
"""The raw text a parser cannot decode: the shape FR-7.6 records, not a repaired object."""

PROSE: Final[str] = "I would rather not move."
RUNAWAY_TOOL: Final[str] = "read_state"
"""The call a runaway keeps making; it answers nothing, so only the step budget stops it."""

DEFAULT_TOOL: Final[str] = "action"
"""What malformed arguments name when the caller offered no tools."""


class Behaviour(StrEnum):
    """The named ways a model can behave, and the label a record can carry."""

    CORRECT_PLAY = "correct-play"
    ALWAYS_ILLEGAL = "always-illegal"
    MALFORMED_ARGUMENTS = "malformed-arguments"
    PROSE_ONLY = "prose-only"
    TIMEOUT = "timeout"
    RUNAWAY = "runaway"


class MockScriptError(ProviderError):
    """The script has no answer left; the caller asked for one decision too many."""


class MockProvider:
    """A provider whose every answer is one of the named behaviours (FR-15.1)."""

    def __init__(
        self,
        behaviour: Behaviour,
        *,
        action: ToolCall | None = None,
        actions: Sequence[ToolCall] = (),
        usage: Usage | None = DEFAULT_USAGE,
    ) -> None:
        self._behaviour = behaviour
        self._actions: list[ToolCall] = (
            list(actions) if actions else ([] if action is None else [action])
        )
        if behaviour in {Behaviour.CORRECT_PLAY, Behaviour.ALWAYS_ILLEGAL} and not self._actions:
            raise ValueError(f"the {behaviour.value} behaviour needs at least one action")
        self._usage = usage
        self._calls = 0
        self._next_action = 0

    @property
    def behaviour(self) -> Behaviour:
        """Which named behaviour this provider plays. There is no setter by design."""
        return self._behaviour

    @property
    def label(self) -> str:
        """The provider identity a record can carry, with the behaviour attached."""
        return f"{NAME}:{self._behaviour.value}"

    @property
    def calls(self) -> int:
        """How many completions have been asked for, which is what a runaway test counts."""
        return self._calls

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        config: CompletionConfig,
    ) -> Completion:
        self._calls += 1
        request = encode_request(_wire_request(messages, tools, config))
        if self._behaviour is Behaviour.TIMEOUT:
            raise ProviderTimeoutError(
                "the mock timed out",
                wire=_wire(request, None, None),
            )
        if self._behaviour is Behaviour.PROSE_ONLY:
            return _answer(
                request, config.model, Completion(text=PROSE, tool_calls=None, usage=self._usage)
            )
        if self._behaviour is Behaviour.MALFORMED_ARGUMENTS:
            name = tools[0].name if tools else DEFAULT_TOOL
            return _answer(
                request,
                config.model,
                Completion(
                    text=None,
                    tool_calls=(
                        ToolCall(
                            id=f"mock-malformed-{self._calls}",
                            name=name,
                            arguments=MALFORMED_ARGUMENTS,
                        ),
                    ),
                    usage=self._usage,
                ),
            )
        if self._behaviour is Behaviour.RUNAWAY:
            return _answer(
                request,
                config.model,
                Completion(
                    text=None,
                    tool_calls=(
                        ToolCall(
                            id=f"mock-runaway-{self._calls}",
                            name=RUNAWAY_TOOL,
                            arguments={},
                        ),
                    ),
                    usage=self._usage,
                ),
            )
        if self._behaviour is Behaviour.ALWAYS_ILLEGAL:
            return _answer(
                request,
                config.model,
                Completion(text=None, tool_calls=(self._actions[0],), usage=self._usage),
            )
        if self._next_action >= len(self._actions):
            raise MockScriptError(
                f"the {self._behaviour.value} script has no answer after {len(self._actions)}"
            )
        action = self._actions[self._next_action]
        self._next_action += 1
        return _answer(
            request,
            config.model,
            Completion(text=None, tool_calls=(action,), usage=self._usage),
        )


def _wire_request(
    messages: Sequence[Message],
    tools: Sequence[ToolSpec],
    config: CompletionConfig,
) -> dict[str, object]:
    """What this provider was asked, in the shape a record can read without knowing it is mock."""
    return {
        "max_tokens": config.max_tokens,
        "messages": [message.to_mapping() for message in messages],
        "model": config.model,
        "sampling": config.sampling.to_mapping(),
        "tools": [
            {
                "description": tool.description,
                "input_schema": dict(tool.input_schema),
                "name": tool.name,
            }
            for tool in tools
        ],
    }


def _wire(request: str, response: str | None, status_code: int | None) -> WireExchange:
    return WireExchange.capture(
        request=request,
        response=response,
        status_code=status_code,
        request_headers={"protocol": "mock"},
        response_headers={"protocol": "mock"},
    )


def _answer(request: str, model: str, completion: Completion) -> Completion:
    """Attach the exchange to an answer, so no mock call is unrecorded (FR-5.4)."""
    response = encode_request(completion.to_mapping())
    return Completion(
        text=completion.text,
        tool_calls=completion.tool_calls,
        usage=completion.usage,
        metadata=CallMetadata(
            model=model,
            route=None,
            native_tools=True,
            wire=_wire(request, response, 200),
        ),
    )


__all__: list[str] = [
    "DEFAULT_USAGE",
    "MALFORMED_ARGUMENTS",
    "NAME",
    "PROSE",
    "RUNAWAY_TOOL",
    "VERSION",
    "Behaviour",
    "MockProvider",
    "MockScriptError",
]
