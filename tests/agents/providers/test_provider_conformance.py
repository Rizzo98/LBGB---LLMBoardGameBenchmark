"""One conformance suite, every adapter (PRD-v2 FR-15.2, SC-9).

The point of the suite is that an adapter is accepted by passing the same properties as every
other adapter, not by passing its own tests. This file supplies the scenarios - the mock, OpenRouter
with native tools, OpenRouter through the text protocol - and asserts that each one reports no
failures. Adding a provider means adding a scenario here; the loop does not change, because it only
knows the Provider protocol.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any

import httpx
import pytest

from lgbg.agents.providers.base import (
    CallMetadata,
    Completion,
    CompletionConfig,
    Message,
    Provider,
    Role,
    ToolCall,
    ToolSpec,
    Usage,
)
from lgbg.agents.providers.conformance import failures
from lgbg.agents.providers.mock import DEFAULT_USAGE, Behaviour, MockProvider
from lgbg.agents.providers.openrouter import OpenRouterProvider
from lgbg.agents.wire import WireExchange

MODEL = "vendor/conformance-model"
MESSAGES = [Message(role=Role.USER, content="It is your turn.")]
TOOLS = [
    ToolSpec(
        name="take",
        description="the take action of fixture",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    )
]
CONFIG = CompletionConfig(model=MODEL)
USAGE = Usage(prompt_tokens=11, completion_tokens=7, total_tokens=18)
SENTINEL = "sk-conformance-secret"


class Gateway:
    """A tiny OpenAI-compatible gateway: one listing and one completion."""

    def __init__(self, *, native: bool, completion: dict[str, Any]) -> None:
        self.native = native
        self.completion = completion
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": MODEL,
                            "supported_parameters": ["tools"] if self.native else [],
                            "pricing": {"prompt": "0.0000005", "completion": "0.0000015"},
                        }
                    ]
                },
            )
        return httpx.Response(200, json=self.completion)

    @property
    def attempts(self) -> int:
        return sum(1 for request in self.requests if request.url.path.endswith("/chat/completions"))


def _completion_payload(*, content: Any = None, tool_calls: Any = None) -> dict[str, Any]:
    return {
        "id": "gen-1",
        "model": MODEL,
        "provider": "upstream-a",
        "choices": [
            {"message": {"role": "assistant", "content": content, "tool_calls": tool_calls}}
        ],
        "usage": USAGE.to_mapping(),
    }


def _native_call() -> dict[str, Any]:
    return {
        "id": "call-1",
        "type": "function",
        "function": {"name": "take", "arguments": "{}"},
    }


def _run_openrouter(
    *,
    native: bool,
    completion: dict[str, Any],
    expected_text: str | None,
    expected_tool: str | None,
) -> list[str]:
    gateway = Gateway(native=native, completion=completion)

    async def scenario() -> list[str]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(gateway)) as client:
            provider = OpenRouterProvider(client, api_key=SENTINEL)
            return await failures(
                provider,
                messages=MESSAGES,
                tools=TOOLS,
                config=CONFIG,
                native_tools=native,
                expected_text=expected_text,
                expected_tool=expected_tool,
                expected_usage=USAGE,
                attempt_count=lambda: gateway.attempts,
                secrets=(SENTINEL,),
            )

    return asyncio.run(scenario())


def mock_native() -> list[str]:
    provider = MockProvider(
        Behaviour.CORRECT_PLAY, action=ToolCall(id="call-1", name="take", arguments={})
    )

    async def scenario() -> list[str]:
        return await failures(
            provider,
            messages=MESSAGES,
            tools=TOOLS,
            config=CONFIG,
            native_tools=True,
            expected_text=None,
            expected_tool="take",
            expected_usage=DEFAULT_USAGE,
            attempt_count=lambda: provider.calls,
        )

    return asyncio.run(scenario())


def mock_unknown_usage() -> list[str]:
    provider = MockProvider(
        Behaviour.CORRECT_PLAY,
        action=ToolCall(id="call-1", name="take", arguments={}),
        usage=None,
    )

    async def scenario() -> list[str]:
        return await failures(
            provider,
            messages=MESSAGES,
            tools=TOOLS,
            config=CONFIG,
            native_tools=True,
            expected_text=None,
            expected_tool="take",
            expected_usage=None,
            attempt_count=lambda: provider.calls,
        )

    return asyncio.run(scenario())


def openrouter_native() -> list[str]:
    return _run_openrouter(
        native=True,
        completion=_completion_payload(tool_calls=[_native_call()]),
        expected_text=None,
        expected_tool="take",
    )


def openrouter_text() -> list[str]:
    body = '{"tool": "take", "arguments": {}}'
    return _run_openrouter(
        native=False,
        completion=_completion_payload(content=body),
        expected_text=body,
        expected_tool="take",
    )


@pytest.mark.parametrize(
    "scenario",
    [mock_native, mock_unknown_usage, openrouter_native, openrouter_text],
    ids=["mock-native", "mock-unknown-usage", "openrouter-native", "openrouter-text"],
)
def test_every_adapter_passes_the_shared_suite(scenario: Any) -> None:
    assert scenario() == []


def _valid_completion() -> Completion:
    exchange = WireExchange.capture(
        request=json.dumps({"model": MODEL}),
        response=json.dumps({"ok": True}),
        status_code=200,
    )
    return Completion(
        text=None,
        tool_calls=(ToolCall(id="call-1", name="take", arguments={}),),
        usage=USAGE,
        metadata=CallMetadata(model=MODEL, route=None, native_tools=False, wire=exchange),
    )


class _NoExchange:
    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        config: CompletionConfig,
    ) -> Completion:
        del messages, tools, config
        return Completion(
            text="prose",
            tool_calls=None,
            usage=USAGE,
            metadata=CallMetadata(model=MODEL, route=None, native_tools=False),
        )


def test_the_suite_refuses_a_completion_without_an_exchange() -> None:
    async def scenario() -> list[str]:
        return await failures(
            _NoExchange(),
            messages=MESSAGES,
            tools=TOOLS,
            config=CONFIG,
            native_tools=False,
            expected_text="prose",
            expected_tool=None,
            expected_usage=USAGE,
        )

    problems = asyncio.run(scenario())

    assert any("exchange" in problem for problem in problems), problems


class _TwoAttempts:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        config: CompletionConfig,
    ) -> Completion:
        del messages, tools, config
        self.calls += 2
        return _valid_completion()


def test_the_suite_refuses_an_adapter_that_retries() -> None:
    provider = _TwoAttempts()

    async def scenario() -> list[str]:
        return await failures(
            provider,
            messages=MESSAGES,
            tools=TOOLS,
            config=CONFIG,
            native_tools=False,
            expected_text=None,
            expected_tool="take",
            expected_usage=USAGE,
            attempt_count=lambda: provider.calls,
        )

    problems = asyncio.run(scenario())

    assert any("attempts" in problem for problem in problems), problems


def test_the_mock_provider_is_structurally_the_same_seam() -> None:
    provider = MockProvider(
        Behaviour.CORRECT_PLAY, action=ToolCall(id="call-1", name="take", arguments={})
    )

    assert isinstance(provider, Provider)
