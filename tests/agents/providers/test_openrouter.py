"""The OpenRouter adapter: one gateway, every model (PRD-v2 FR-5.2, PRD-v2 FR-5.3).

The requirements this file holds: PRD-v2 FR-5.8 (route and native-tool recording) and
PRD-v2 FR-5.9 (pricing from the gateway).

OpenRouter is one OpenAI-compatible transport in front of many vendors. The adapter's job is to
make every model arrive through the same request path, so a difference between two models is a
difference between the models rather than between two client libraries. Everything the record
needs to tell those apart is carried out of the adapter: the logical model, the upstream route the
gateway chose, whether native tool calling was used, and what the answer cost.

A model without native tool calling is the interesting case. The adapter sends a documented text
protocol instead of `tools`, and parses the answer back into the same `ToolCall` value the loop
already understands; the loop never learns that this model is different (PRD-v2 FR-5.3).

Pricing comes from the gateway's own model listing, converted once to integer micro-dollars per
million tokens and stamped with the moment it was read. Nothing here is hardcoded: a price table
that drifts silently would make every cost comparison meaningless (PRD-v2 FR-5.9).

Every test drives `httpx.MockTransport`; no socket is opened (NFR-8).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest

from lgbg.agents.providers.base import (
    CallMetadata,
    CompletionConfig,
    Message,
    Provider,
    ProviderError,
    ProviderTimeoutError,
    Role,
    Sampling,
    ToolCall,
    ToolSpec,
    Usage,
)
from lgbg.agents.providers.openrouter import (
    DEFAULT_BASE_URL,
    NAME,
    TEXT_PROTOCOL,
    VERSION,
    OpenRouterProvider,
    PricingUnavailableError,
)
from lgbg.core.contracts import validate_manifest

MODEL = "vendor/model-a"
READ_AT = "2026-02-11T09:30:00+00:00"
RUN_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "v2" / "run.json"

MESSAGES = [Message(role=Role.USER, content="It is your turn.")]
DEFAULT_USAGE = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
TOOLS = [
    ToolSpec(
        name="take",
        description="the take action of fixture",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    )
]
CONFIG = CompletionConfig(
    model=MODEL,
    sampling=Sampling(temperature_milli=500, top_p_milli=1000, seed=7),
    max_tokens=64,
)

Handler = Callable[[httpx.Request], httpx.Response]


class Gateway:
    """A fake OpenRouter: one listing and a queue of completions, recording every request."""

    def __init__(self, models: Any, completions: Sequence[Any]) -> None:
        self.models = models
        self.completions = list(completions)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/api/v1/models":
            return httpx.Response(200, json=self.models)
        if request.url.path == "/api/v1/chat/completions":
            if not self.completions:
                raise AssertionError("the gateway was asked for more completions than it has")
            return httpx.Response(200, json=self.completions.pop(0))
        raise AssertionError(f"unexpected path {request.url.path}")

    @property
    def chat_requests(self) -> list[httpx.Request]:
        return [
            request for request in self.requests if request.url.path.endswith("/chat/completions")
        ]

    @property
    def model_requests(self) -> list[httpx.Request]:
        return [request for request in self.requests if request.url.path.endswith("/models")]


def run[T](
    handler: Handler,
    action: Callable[[OpenRouterProvider], Awaitable[T]],
    *,
    clock: Callable[[], str] | None = None,
) -> T:
    """Drive one scenario against a MockTransport, then close the client."""

    async def scenario() -> T:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OpenRouterProvider(client, api_key="test-key", clock=clock)
            return await action(provider)

    return asyncio.run(scenario())


def model_entry(
    model: str = MODEL,
    *,
    tools: bool = True,
    prompt: str = "0.0000005",
    completion: str = "0.0000015",
) -> dict[str, Any]:
    return {
        "id": model,
        "supported_parameters": ["tools"] if tools else [],
        "pricing": {"prompt": prompt, "completion": completion},
    }


def models_payload(*, tools: bool = True) -> dict[str, Any]:
    return {"data": [model_entry(tools=tools)]}


def native_call(
    *, arguments: str = "{}", name: str = "take", call_id: str = "call-1"
) -> dict[str, Any]:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def completion_payload(
    *,
    content: Any = None,
    tool_calls: Any = None,
    provider: Any = "upstream-a",
    usage: Any = None,
) -> dict[str, Any]:
    payload = {
        "id": "gen-1",
        "model": MODEL,
        "choices": [
            {"message": {"role": "assistant", "content": content, "tool_calls": tool_calls}}
        ],
        "usage": DEFAULT_USAGE if usage is None else usage,
    }
    if provider is not None:
        payload["provider"] = provider
    return payload


def test_a_native_tool_call_is_parsed_and_recorded() -> None:
    gateway = Gateway(models_payload(), [completion_payload(tool_calls=[native_call()])])

    completion = run(gateway, lambda provider: provider.complete(MESSAGES, TOOLS, CONFIG))

    assert completion.tool_calls == (ToolCall(id="call-1", name="take", arguments={}),)
    assert completion.metadata == CallMetadata(model=MODEL, route="upstream-a", native_tools=True)
    payload = json.loads(gateway.chat_requests[0].content)
    assert payload["model"] == MODEL
    assert payload["messages"] == [{"role": "user", "content": "It is your turn."}]
    assert payload["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "take",
                "description": "the take action of fixture",
                "parameters": TOOLS[0].input_schema,
            },
        }
    ]
    assert payload["tool_choice"] == "auto"
    assert payload["temperature"] == 0.5
    assert payload["top_p"] == 1.0
    assert payload["seed"] == 7
    assert payload["max_tokens"] == 64
    assert payload["usage"] == {"include": True}
    assert gateway.model_requests[0].headers["authorization"] == "Bearer test-key"


def test_a_model_without_native_tools_gets_the_text_protocol() -> None:
    body = '{"tool": "take", "arguments": {}}'
    gateway = Gateway(models_payload(tools=False), [completion_payload(content=body)])

    completion = run(gateway, lambda provider: provider.complete(MESSAGES, TOOLS, CONFIG))

    assert completion.text == body
    assert completion.tool_calls == (ToolCall(id="gen-1-text", name="take", arguments={}),)
    assert completion.metadata is not None
    assert completion.metadata.native_tools is False
    payload = json.loads(gateway.chat_requests[0].content)
    assert "tools" not in payload
    assert payload["messages"][0] == {"role": "system", "content": TEXT_PROTOCOL}
    assert payload["messages"][1] == {"role": "user", "content": "It is your turn."}
    assert "tool_choice" not in payload


def test_the_text_protocol_accepts_a_fenced_object() -> None:
    body = '```json\n{"tool": "take", "arguments": {}}\n```'
    gateway = Gateway(models_payload(tools=False), [completion_payload(content=body)])

    completion = run(gateway, lambda provider: provider.complete(MESSAGES, TOOLS, CONFIG))

    assert completion.tool_calls == (ToolCall(id="gen-1-text", name="take", arguments={}),)


def test_prose_is_left_as_prose_and_not_invented_into_an_action() -> None:
    gateway = Gateway(models_payload(tools=False), [completion_payload(content="I pass.")])

    completion = run(gateway, lambda provider: provider.complete(MESSAGES, TOOLS, CONFIG))

    assert completion.text == "I pass."
    assert completion.tool_calls is None


def test_a_text_object_is_not_an_action_when_no_tools_were_offered() -> None:
    body = '{"tool": "take", "arguments": {}}'
    gateway = Gateway(models_payload(tools=False), [completion_payload(content=body)])

    completion = run(gateway, lambda provider: provider.complete(MESSAGES, [], CONFIG))

    assert completion.text == body
    assert completion.tool_calls is None, "no tool was offered, so no tool call exists to make"
    payload = json.loads(gateway.chat_requests[0].content)
    assert "tools" not in payload
    assert all(message["role"] != "system" for message in payload["messages"])


def test_native_arguments_that_do_not_parse_are_kept_as_text() -> None:
    gateway = Gateway(
        models_payload(),
        [completion_payload(tool_calls=[native_call(arguments="{not json")])],
    )

    completion = run(gateway, lambda provider: provider.complete(MESSAGES, TOOLS, CONFIG))

    assert completion.tool_calls is not None
    assert completion.tool_calls[0].arguments == "{not json"


def test_usage_is_normalised_and_an_omitted_total_is_derived() -> None:
    gateway = Gateway(
        models_payload(),
        [completion_payload(usage={"prompt_tokens": 3, "completion_tokens": 4})],
    )

    completion = run(gateway, lambda provider: provider.complete(MESSAGES, TOOLS, CONFIG))

    assert completion.usage == Usage(prompt_tokens=3, completion_tokens=4, total_tokens=7)


def test_an_omitted_usage_is_unknown_not_zero() -> None:
    payload = completion_payload()
    del payload["usage"]
    gateway = Gateway(models_payload(), [payload])

    completion = run(gateway, lambda provider: provider.complete(MESSAGES, TOOLS, CONFIG))

    assert completion.usage is None


def test_the_same_logical_model_routed_differently_is_visible_in_the_record() -> None:
    gateway = Gateway(
        models_payload(),
        [completion_payload(provider="upstream-a"), completion_payload(provider="upstream-b")],
    )

    async def two_calls(provider: OpenRouterProvider) -> tuple[Any, Any]:
        first = await provider.complete(MESSAGES, TOOLS, CONFIG)
        second = await provider.complete(MESSAGES, TOOLS, CONFIG)
        return first, second

    first, second = run(gateway, two_calls)

    assert first.metadata.model == second.metadata.model == MODEL
    assert first.metadata.route == "upstream-a"
    assert second.metadata.route == "upstream-b"
    assert first.metadata.native_tools is second.metadata.native_tools is True
    assert len(gateway.model_requests) == 1, "the listing is read once, not once per call"


def test_pricing_is_read_from_the_listing_with_the_time_it_was_read() -> None:
    gateway = Gateway(
        {
            "data": [
                model_entry(MODEL),
                model_entry("vendor/other", prompt="0", completion="0.000000000001"),
            ]
        },
        [],
    )

    table = run(
        gateway,
        lambda provider: provider.read_pricing([MODEL, "vendor/other"]),
        clock=lambda: READ_AT,
    )

    assert table.to_mapping() == {
        "source": f"{DEFAULT_BASE_URL}/models",
        "read_at": READ_AT,
        "unit": "micro_usd_per_million_tokens",
        "models": [
            {"model": MODEL, "prompt": 500000, "completion": 1500000},
            {"model": "vendor/other", "prompt": 0, "completion": 1},
        ],
    }
    manifest = json.loads(RUN_FIXTURE.read_text(encoding="utf-8"))
    manifest["price_table"] = table.to_mapping()
    assert validate_manifest(manifest) == []


def test_a_model_missing_from_the_listing_has_no_price() -> None:
    gateway = Gateway(models_payload(), [])

    with pytest.raises(ProviderError, match="no listing"):
        run(gateway, lambda provider: provider.read_pricing(["vendor/missing"]))


@pytest.mark.parametrize(
    "pricing",
    [
        {"prompt": "-1", "completion": "0"},
        {"prompt": "0.0000000000005", "completion": "0"},
        {},
    ],
)
def test_a_price_that_cannot_be_expressed_in_micro_dollars_is_refused(
    pricing: dict[str, str],
) -> None:
    entry = model_entry()
    entry["pricing"] = pricing
    gateway = Gateway({"data": [entry]}, [])

    with pytest.raises(PricingUnavailableError):
        run(gateway, lambda provider: provider.read_pricing([MODEL]))


def test_a_gateway_error_is_a_provider_error_and_is_not_retried() -> None:
    chat_calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=models_payload())
        chat_calls.append(request)
        return httpx.Response(500, json={"error": {"message": "upstream exploded"}})

    with pytest.raises(ProviderError, match="500"):
        run(handler, lambda provider: provider.complete(MESSAGES, TOOLS, CONFIG))

    assert len(chat_calls) == 1, "the adapter must not retry; policy belongs above it"


def test_a_timeout_is_a_provider_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=models_payload())
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderTimeoutError):
        run(handler, lambda provider: provider.complete(MESSAGES, TOOLS, CONFIG))


def test_a_tool_call_without_a_name_is_a_provider_error() -> None:
    gateway = Gateway(
        models_payload(),
        [
            completion_payload(
                tool_calls=[{"id": "call-1", "type": "function", "function": {"arguments": "{}"}}]
            )
        ],
    )

    with pytest.raises(ProviderError, match="name"):
        run(gateway, lambda provider: provider.complete(MESSAGES, TOOLS, CONFIG))


def test_the_wire_messages_carry_tool_history_without_null_envelopes() -> None:
    messages = [
        Message(
            role=Role.ASSISTANT,
            content=None,
            tool_calls=(ToolCall(id="call-1", name="take", arguments={}),),
        ),
        Message(role=Role.TOOL, content='{"ok":true}', tool_call_id="call-1"),
    ]
    gateway = Gateway(models_payload(), [completion_payload(content="done")])

    run(gateway, lambda provider: provider.complete(messages, [], CONFIG))

    payload = json.loads(gateway.chat_requests[0].content)
    assert payload["messages"] == [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "take", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "content": '{"ok":true}', "tool_call_id": "call-1"},
    ]


def test_the_adapter_is_a_provider_and_names_itself() -> None:
    gateway = Gateway(models_payload(), [])

    async def scenario() -> tuple[bool, str, str]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(gateway)) as client:
            provider = OpenRouterProvider(client, api_key="key")
            return isinstance(provider, Provider), provider.name, provider.version

    assert asyncio.run(scenario()) == (True, NAME, VERSION)


def test_a_missing_api_key_is_refused() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient() as client:
            with pytest.raises(ValueError, match="api key"):
                OpenRouterProvider(client, api_key="")

    asyncio.run(scenario())
