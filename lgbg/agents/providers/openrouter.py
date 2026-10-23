"""The OpenRouter adapter: one gateway, every model (PRD-v2 FR-5.2, FR-5.3, FR-5.8, FR-5.9).

OpenRouter is OpenAI-compatible over HTTP. Every model is driven through the same request path, so
a difference between two models is a difference between the models rather than between two client
libraries (FR-5.2). The adapter is deliberately thin: it builds the wire request, parses the wire
answer, and returns the provider-neutral values the loop already knows. It does not retry, repair,
summarise or otherwise alter a request - policy belongs above it, where it is visible (FR-5.5).

**Native tools, or a documented text protocol (FR-5.3).** The gateway's model listing says whether
a model accepts `tools`. When it does, the adapter sends native function definitions and parses
native tool calls. When it does not, the adapter sends one shared system instruction:

    To take an action, reply with one JSON object and nothing else:
    {"tool": "<tool name>", "arguments": {...}}

and parses that object back into the same ToolCall. The loop never learns that this model is
different. Prose that does not contain the object stays prose; the adapter does not invent an
action the model did not choose.

**What the record needs (FR-5.8).** Every answer carries CallMetadata: the logical model asked
for, the upstream route the gateway selected, and whether native tool calling was used. The route
is a separate field because the same logical model reached through two upstreams is not the same
measurement; a silent route change must be visible rather than look like a model change.

**Pricing is data, not a constant (FR-5.9).** `read_pricing` fetches the gateway's own listing,
converts each per-token decimal into integer micro-dollars per million tokens, and stamps the
result with the moment it was read. A price that cannot be expressed in that unit is refused
rather than rounded: a cost table that is quietly wrong is worse than one that is absent.

The HTTP client is injected, so a test drives a MockTransport and the adapter never owns a
connection it did not receive (NFR-8).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final

import httpx

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
from lgbg.core.canonical import to_canonical_json
from lgbg.core.contracts import PRICE_UNITS

NAME: Final[str] = "openrouter"
VERSION: Final[str] = "1"
DEFAULT_BASE_URL: Final[str] = "https://openrouter.ai/api/v1"

PRICE_UNIT: Final[str] = PRICE_UNITS[0]
"""The manifest's price unit: integer micro-dollars per million tokens."""

_PRICE_SCALE: Final[Decimal] = Decimal(1_000_000_000_000)
"""Per-token USD to micro-USD per million tokens: 1e6 dollars and 1e6 tokens."""

_FENCE: Final[str] = "\u0060\u0060\u0060"

TEXT_PROTOCOL: Final[str] = (
    "This model is connected through a text interface. To take an action, reply with one JSON "
    'object and nothing else: {"tool": "<tool name>", "arguments": {...}}. The arguments must '
    "be a JSON object. You may wrap the object in a fenced code block, but do not add any other "
    "text."
)
"""The one instruction a model without native tool calling receives (FR-5.3)."""


class PricingUnavailableError(ProviderError):
    """The gateway listed no price, or one this record's unit cannot express."""


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """One entry of the gateway's model listing: capabilities and prices."""

    id: str
    supported_parameters: tuple[str, ...]
    prompt_micro_usd_per_million: int | None
    completion_micro_usd_per_million: int | None

    @property
    def supports_tools(self) -> bool:
        """Whether this model accepts native tool calling, as the gateway declares it."""
        return "tools" in self.supported_parameters


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """One model's price in the unit the manifest declares."""

    model: str
    prompt: int
    completion: int

    def to_mapping(self) -> dict[str, Any]:
        return {"model": self.model, "prompt": self.prompt, "completion": self.completion}


@dataclass(frozen=True, slots=True)
class PriceTable:
    """The prices a run used, and when they were read (FR-5.9)."""

    source: str
    read_at: str
    unit: str
    models: tuple[ModelPrice, ...]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "read_at": self.read_at,
            "unit": self.unit,
            "models": [price.to_mapping() for price in self.models],
        }


class OpenRouterProvider:
    """The one real provider: an OpenAI-compatible request over OpenRouter (FR-5.2)."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        clock: Callable[[], str] | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("an api key is required to talk to the gateway")
        self._client = client
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._clock = _utc_now if clock is None else clock
        self._models: dict[str, ModelInfo] | None = None
        self._read_at: str | None = None

    @property
    def name(self) -> str:
        return NAME

    @property
    def version(self) -> str:
        return VERSION

    @property
    def models_url(self) -> str:
        return f"{self._base_url}/models"

    @property
    def chat_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    # --- the seam ---------------------------------------------------------------------------

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        config: CompletionConfig,
    ) -> Completion:
        """One request, one answer, and the metadata the record needs (FR-5.8)."""
        info = (await self._listing()).get(config.model)
        if info is None:
            raise ProviderError(f"model {config.model!r} has no listing at the gateway")
        native = info.supports_tools and bool(tools)
        text_protocol = bool(tools) and not info.supports_tools

        wire_messages = [_wire_message(message) for message in messages]
        if text_protocol:
            wire_messages.insert(0, {"role": "system", "content": TEXT_PROTOCOL})

        payload: dict[str, Any] = {
            "model": config.model,
            "messages": wire_messages,
            "temperature": config.sampling.temperature_milli / 1000,
            "top_p": config.sampling.top_p_milli / 1000,
            "usage": {"include": True},
        }
        if config.sampling.seed is not None:
            payload["seed"] = config.sampling.seed
        if config.max_tokens is not None:
            payload["max_tokens"] = config.max_tokens
        if native:
            payload["tools"] = [_wire_tool(tool) for tool in tools]
            payload["tool_choice"] = "auto"

        body = await self._request(self.chat_url, payload=payload)
        return _completion(body, config=config, native=native, text_protocol=text_protocol)

    async def read_pricing(self, models: Sequence[str]) -> PriceTable:
        """The gateway's prices for these models, in the manifest's unit and stamped."""
        listing = await self._listing()
        unique = tuple(dict.fromkeys(models))
        if not unique:
            raise ValueError("read_pricing needs at least one model")
        prices: list[ModelPrice] = []
        for model in unique:
            info = listing.get(model)
            if info is None:
                raise ProviderError(f"model {model!r} has no listing at the gateway")
            prompt = info.prompt_micro_usd_per_million
            completion = info.completion_micro_usd_per_million
            if prompt is None or completion is None:
                raise PricingUnavailableError(
                    f"model {model!r} has no price that {PRICE_UNIT} can express"
                )
            prices.append(ModelPrice(model=model, prompt=prompt, completion=completion))
        if self._read_at is None:
            raise ProviderError("the model listing was read without a timestamp")
        return PriceTable(
            source=self.models_url,
            read_at=self._read_at,
            unit=PRICE_UNIT,
            models=tuple(prices),
        )

    # --- the gateway ------------------------------------------------------------------------

    async def _listing(self) -> dict[str, ModelInfo]:
        """The gateway's model listing, read once per adapter (FR-5.9)."""
        if self._models is not None:
            return self._models
        body = await self._request(self.models_url)
        data = body.get("data")
        if not isinstance(data, list):
            raise ProviderError("the gateway's model listing has no data array")
        models: dict[str, ModelInfo] = {}
        for entry in data:
            parsed = _model_info(entry)
            if parsed is not None:
                models[parsed.id] = parsed
        self._models = models
        self._read_at = self._clock()
        return models

    async def _request(
        self, url: str, *, payload: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        """One HTTP exchange. A transport failure is a provider failure, never a retry."""
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            if payload is None:
                response = await self._client.get(url, headers=headers)
            else:
                response = await self._client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as error:
            raise ProviderTimeoutError(f"the gateway timed out at {url}") from error
        except httpx.HTTPError as error:
            raise ProviderError(f"the gateway could not be reached: {error}") from error
        if response.status_code >= 400:
            raise ProviderError(
                f"the gateway answered {response.status_code}: {_error_message(response)}"
            )
        try:
            body: Any = response.json()
        except ValueError as error:
            raise ProviderError("the gateway answered with something that is not JSON") from error
        if not isinstance(body, Mapping):
            raise ProviderError("the gateway answered with a non-object JSON value")
        if body.get("error") is not None:
            raise ProviderError(f"the gateway reported an error: {_error_text(body['error'])}")
        return body


# --- wire translation ----------------------------------------------------------------------


def _wire_message(message: Message) -> dict[str, Any]:
    """One transcript message as OpenAI-compatible JSON.

    Null envelopes are omitted: the record keeps every field, but a user message carrying
    `tool_calls: null` is not something every gateway accepts.
    """
    wire: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.tool_calls is not None:
        wire["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": _wire_arguments(call.arguments)},
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id is not None:
        wire["tool_call_id"] = message.tool_call_id
    return wire


def _wire_arguments(arguments: Mapping[str, Any] | str) -> str:
    return arguments if isinstance(arguments, str) else to_canonical_json(arguments)


def _wire_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": dict(tool.input_schema),
        },
    }


# --- response parsing ----------------------------------------------------------------------


def _completion(
    body: Mapping[str, Any],
    *,
    config: CompletionConfig,
    native: bool,
    text_protocol: bool,
) -> Completion:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("the gateway returned no choices")
    first = choices[0]
    if not isinstance(first, Mapping):
        raise ProviderError("the gateway returned a malformed choice")
    message = first.get("message")
    if not isinstance(message, Mapping):
        raise ProviderError("the gateway returned no message")
    content = message.get("content")
    text = content if isinstance(content, str) else None

    calls: tuple[ToolCall, ...] | None = None
    if native:
        raw_calls = message.get("tool_calls")
        if raw_calls is not None:
            calls = _native_tool_calls(raw_calls) or None
    elif text_protocol and text is not None:
        call = _text_tool_call(text, _response_id(body))
        if call is not None:
            calls = (call,)

    route = body.get("provider")
    return Completion(
        text=text,
        tool_calls=calls,
        usage=_usage(body.get("usage")),
        metadata=CallMetadata(
            model=config.model,
            route=route if isinstance(route, str) else None,
            native_tools=native,
        ),
    )


def _native_tool_calls(raw: object) -> tuple[ToolCall, ...]:
    if not isinstance(raw, list):
        raise ProviderError("tool_calls must be an array")
    calls: list[ToolCall] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ProviderError("a tool call is not an object")
        function = item.get("function")
        if not isinstance(function, Mapping):
            raise ProviderError("a tool call has no function")
        name = function.get("name")
        if not isinstance(name, str) or not name:
            raise ProviderError("a tool call must name a tool")
        call_id = item.get("id")
        if not isinstance(call_id, str) or not call_id:
            call_id = f"call-{index}"
        calls.append(
            ToolCall(
                id=call_id,
                name=name,
                arguments=_arguments(function.get("arguments")),
            )
        )
    return tuple(calls)


def _arguments(raw: object) -> Mapping[str, Any] | str:
    """The parsed arguments, or the raw text when they did not parse (FR-7.6)."""
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        return parsed if isinstance(parsed, Mapping) else raw
    if raw is None:
        return {}
    return to_canonical_json(raw)


def _text_tool_call(text: str, response_id: str) -> ToolCall | None:
    """The documented text protocol, parsed; anything else stays prose (FR-5.3)."""
    candidate = text.strip()
    if candidate.startswith(_FENCE) and candidate.endswith(_FENCE):
        lines = candidate.splitlines()
        if len(lines) >= 2:
            candidate = "\n".join(lines[1:-1]).strip()
    try:
        payload: Any = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping):
        return None
    name = payload.get("tool")
    if not isinstance(name, str) or not name:
        return None
    arguments = payload.get("arguments", {})
    if isinstance(arguments, Mapping):
        return ToolCall(id=f"{response_id}-text", name=name, arguments=dict(arguments))
    if isinstance(arguments, str):
        return ToolCall(id=f"{response_id}-text", name=name, arguments=arguments)
    return None


def _usage(raw: object) -> Usage | None:
    if not isinstance(raw, Mapping):
        return None
    return Usage.normalise(
        prompt_tokens=_count(raw.get("prompt_tokens")),
        completion_tokens=_count(raw.get("completion_tokens")),
        total_tokens=_count(raw.get("total_tokens")),
    )


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _response_id(body: Mapping[str, Any]) -> str:
    value = body.get("id")
    return value if isinstance(value, str) and value else "response"


def _model_info(entry: object) -> ModelInfo | None:
    if not isinstance(entry, Mapping):
        return None
    model_id = entry.get("id")
    if not isinstance(model_id, str) or not model_id:
        return None
    raw_parameters = entry.get("supported_parameters")
    parameters = (
        tuple(item for item in raw_parameters if isinstance(item, str))
        if isinstance(raw_parameters, list)
        else ()
    )
    pricing = entry.get("pricing")
    prompt = completion = None
    if isinstance(pricing, Mapping):
        prompt = _micro_usd_per_million(pricing.get("prompt"))
        completion = _micro_usd_per_million(pricing.get("completion"))
    return ModelInfo(
        id=model_id,
        supported_parameters=parameters,
        prompt_micro_usd_per_million=prompt,
        completion_micro_usd_per_million=completion,
    )


def _micro_usd_per_million(value: object) -> int | None:
    """A per-token USD decimal as integer micro-dollars per million tokens."""
    if not isinstance(value, str):
        return None
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    scaled = amount * _PRICE_SCALE
    if scaled != scaled.to_integral_value():
        return None
    return int(scaled)


def _error_message(response: httpx.Response) -> str:
    try:
        body: Any = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, Mapping):
        return _error_text(body.get("error")) or response.text[:200]
    return response.text[:200]


def _error_text(error: object) -> str:
    if isinstance(error, Mapping):
        message = error.get("message")
        return message if isinstance(message, str) else ""
    if isinstance(error, str):
        return error
    return ""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


__all__: list[str] = [
    "DEFAULT_BASE_URL",
    "NAME",
    "PRICE_UNIT",
    "TEXT_PROTOCOL",
    "VERSION",
    "ModelInfo",
    "ModelPrice",
    "OpenRouterProvider",
    "PriceTable",
    "PricingUnavailableError",
]
