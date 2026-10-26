"""The provider conformance suite: one contract every adapter passes (FR-15.2, SC-9).

An adapter is not accepted because it works once against its own tests. It is accepted because it
satisfies a shared list of properties, run on a scenario that adapter can produce. The list is
deliberately about the seam ARCHITECTURE.md section 13 declares, not about any vendor:

- the object is structurally a Provider, and one complete call performs exactly one attempt;
- the answer carries text and/or tool calls, and every call names a tool that was offered;
- usage is either a complete non-negative triple or explicitly unknown, never a silent zero;
- metadata names the logical model and whether native tools were used;
- the exact exchange is attached, its bodies parse, and the request names the model;
- no supplied secret appears anywhere in the recorded exchange (NFR-7).

The function returns a list of failures rather than raising, so a test can show all of them at once
and so a new adapter can call it from its own test file without importing pytest. The conformance
test runs it for the mock and for OpenRouter with native tools and with the text protocol. Adding
an adapter means adding a scenario; it does not mean changing the loop, because the loop only knows
Provider.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Final

from lgbg.agents.providers.base import (
    CompletionConfig,
    Message,
    Provider,
    ToolSpec,
    Usage,
)
from lgbg.core.canonical import to_canonical_json
from lgbg.core.types import JsonValue


async def failures(
    provider: Provider,
    *,
    messages: Sequence[Message],
    tools: Sequence[ToolSpec],
    config: CompletionConfig,
    native_tools: bool,
    expected_text: str | None,
    expected_tool: str | None,
    expected_usage: Usage | None,
    attempt_count: Callable[[], int] | None = None,
    secrets: Sequence[str] = (),
) -> list[str]:
    """Every way this provider fails the shared contract for this scenario, or none.

    'attempt_count' is how an adapter exposes the requests it actually made. Without it the
    no-retry property cannot be checked from outside, which is why the suite asks for it rather
    than assuming it.
    """
    problems: list[str] = []
    if not isinstance(provider, Provider):
        problems.append("the adapter does not satisfy the Provider protocol")
    before = None if attempt_count is None else attempt_count()
    try:
        completion = await provider.complete(messages, tools, config)
    except Exception as error:  # the report is the point, not the exception
        return [*problems, f"complete raised {error!r}"]
    after = None if attempt_count is None else attempt_count()
    if before is not None and after is not None and after - before != 1:
        problems.append(f"one complete call made {after - before} attempts, not 1")

    offered = {tool.name for tool in tools}
    calls = tuple(completion.tool_calls or ())
    names = [call.name for call in calls]
    if expected_text is None:
        if completion.text is not None:
            problems.append(f"expected no text, got {completion.text!r}")
    elif completion.text != expected_text:
        problems.append(f"text is {completion.text!r}, expected {expected_text!r}")
    if expected_tool is None:
        if calls:
            problems.append(f"expected no tool call, got {names!r}")
    elif names != [expected_tool]:
        problems.append(f"tool calls are {names!r}, expected [{expected_tool!r}]")
    for name in names:
        if name not in offered:
            problems.append(f"tool call {name!r} names no offered tool")

    usage = completion.usage
    if expected_usage is None:
        if usage is not None:
            problems.append(f"expected unknown usage, got {usage.to_mapping()!r}")
    elif usage != expected_usage:
        problems.append(f"usage is {usage!r}, expected {expected_usage!r}")
    elif usage is not None and usage.total_tokens != usage.prompt_tokens + usage.completion_tokens:
        problems.append(f"usage total {usage.total_tokens} is not prompt + completion")

    metadata = completion.metadata
    if metadata is None:
        problems.append("the answer carries no CallMetadata")
    else:
        if metadata.model != config.model:
            problems.append(f"metadata model is {metadata.model!r}, expected {config.model!r}")
        if metadata.native_tools is not native_tools:
            problems.append(f"native_tools is {metadata.native_tools!r}, expected {native_tools!r}")
        if metadata.wire is None:
            problems.append("the answer carries no recorded exchange")
        else:
            problems.extend(_wire_problems(metadata.wire.to_mapping(), config.model, secrets))

    if set(completion.to_mapping()) != {"text", "tool_calls"}:
        problems.append("the response mapping is not exactly {text, tool_calls}")
    return problems


def _wire_problems(wire: Mapping[str, JsonValue], model: str, secrets: Sequence[str]) -> list[str]:
    problems: list[str] = []
    request = wire.get("request")
    response = wire.get("response")
    if not isinstance(request, str):
        problems.append("the recorded request is not text")
    else:
        problems.extend(_json_problems(request, "request"))
        try:
            parsed = json.loads(request)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and parsed.get("model") != model:
            problems.append(f"the recorded request names {parsed.get('model')!r}, not {model!r}")
    if not isinstance(response, str):
        problems.append("the recorded response is not text")
    else:
        problems.extend(_json_problems(response, "response"))
    recorded = to_canonical_json(wire)
    for secret in secrets:
        if secret and secret in recorded:
            problems.append("a supplied secret appears in the recorded exchange")
            break
    return problems


def _json_problems(text: str, which: str) -> list[str]:
    try:
        json.loads(text)
    except json.JSONDecodeError as error:
        return [f"the recorded {which} is not JSON: {error}"]
    return []


__all__: Final[list[str]] = ["failures"]
