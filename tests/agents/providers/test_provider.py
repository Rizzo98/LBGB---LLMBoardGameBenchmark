"""The provider abstraction, and nothing beyond it (PRD-v2 FR-5.1, FR-5.6).

ARCHITECTURE.md section 13 asks for one narrow seam:
`complete(messages, tools, config) -> {text, tool_calls, usage}`. This module holds the protocol to
that shape: the protocol's only member is `complete`, the request is a provider-neutral
transcript, and the answer is text, tool calls and usage.

Usage is the part that is easy to get quietly wrong. Providers differ in what they report, and an
omitted count is not a count of zero: recording it as zero would make a free decision look free.
The rule here is that usage is either a complete triple of integers or it is `None`, the explicit
unknown the sidecar contract already declares.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path

import pytest

from lgbg.agents.providers.base import (
    Completion,
    CompletionConfig,
    Message,
    Provider,
    Role,
    Sampling,
    ToolCall,
    ToolSpec,
    Usage,
)
from lgbg.core.contracts import validate_decision
from lgbg.core.types import JsonValue

DECISION_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "v2" / "decisions.jsonl"


def test_the_protocol_has_complete_and_nothing_else() -> None:
    """FR-5.1: the narrow seam is the whole interface a provider must satisfy."""
    assert vars(Provider)["__protocol_attrs__"] == {"complete"}
    assert inspect.iscoroutinefunction(Provider.complete)
    signature = inspect.signature(Provider.complete)
    assert list(signature.parameters) == ["self", "messages", "tools", "config"]


def test_a_provider_is_anything_that_can_complete() -> None:
    """Structural typing: an adapter satisfies the seam without importing a base class."""

    class Stub:
        async def complete(
            self,
            messages: list[Message],
            tools: list[ToolSpec],
            config: CompletionConfig,
        ) -> Completion:
            del messages, tools, config
            return Completion(text="hello", tool_calls=None, usage=None)

    provider = Stub()

    assert isinstance(provider, Provider)
    completion = asyncio.run(provider.complete([], [], CompletionConfig(model="stub")))
    assert completion.text == "hello"


@pytest.mark.parametrize(
    ("prompt", "completion", "total", "expected"),
    [
        (3, 4, None, Usage(3, 4, 7)),
        (3, 4, 9, Usage(3, 4, 9)),
        (0, 0, None, Usage(0, 0, 0)),
        (None, 4, None, None),
        (3, None, None, None),
        (None, None, None, None),
    ],
)
def test_usage_is_normalised_to_a_complete_triple_or_unknown(
    prompt: int | None, completion: int | None, total: int | None, expected: Usage | None
) -> None:
    """FR-5.6: three counts, and a total that can be derived when the provider omits it."""
    assert (
        Usage.normalise(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)
        == expected
    )


def test_zero_is_a_known_usage_and_an_omission_is_not_zero() -> None:
    """FR-5.6 and FR-13.4: 'free' and 'unknown' are different findings, not the same number."""
    zero = Usage.normalise(prompt_tokens=0, completion_tokens=0, total_tokens=None)
    assert zero == Usage(0, 0, 0)
    assert Usage.normalise(prompt_tokens=None, completion_tokens=None, total_tokens=None) is None
    assert Completion(text="prose", tool_calls=None, usage=None).usage is None


def test_a_negative_count_is_not_a_usage() -> None:
    with pytest.raises(ValueError, match="prompt_tokens must be a non-negative integer"):
        Usage(prompt_tokens=-1, completion_tokens=2, total_tokens=1)


def test_sampling_is_integer_thousandths_and_validated() -> None:
    """The manifest holds integers; 0.5 is 500 here, for the reason the contract gives."""
    sampling = Sampling(temperature_milli=500, top_p_milli=1000, seed=7)

    assert sampling.to_mapping() == {
        "temperature_milli": 500,
        "top_p_milli": 1000,
        "seed": 7,
    }
    with pytest.raises(ValueError, match="temperature_milli must be between"):
        Sampling(temperature_milli=1001)
    with pytest.raises(ValueError, match="top_p_milli must be between"):
        Sampling(top_p_milli=-1)


def test_the_completion_config_names_the_model_and_carries_sampling() -> None:
    config = CompletionConfig(model="vendor/model-a", sampling=Sampling(seed=3), max_tokens=64)

    assert config.model == "vendor/model-a"
    assert config.sampling.seed == 3
    assert config.max_tokens == 64
    with pytest.raises(ValueError, match="must name its model"):
        CompletionConfig(model="")
    with pytest.raises(ValueError, match="max_tokens must be positive"):
        CompletionConfig(model="m", max_tokens=0)


def test_a_message_maps_to_the_frozen_transcript_shape() -> None:
    """K-002's decision record is the target: nulls are present, not left out."""
    call = ToolCall(id="call-1", name="build_road", arguments={"edge": 12})
    message = Message(role=Role.ASSISTANT, content=None, tool_calls=(call,))

    assert message.to_mapping() == {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "call-1", "name": "build_road", "arguments": {"edge": 12}}],
        "tool_call_id": None,
    }


def test_a_tool_call_keeps_arguments_that_did_not_parse_as_text() -> None:
    """FR-7.6: a malformed call is a recorded failure, so the raw text has to survive."""
    call = ToolCall(id="call-2", name="build_road", arguments="{not json")

    assert call.to_mapping() == {"id": "call-2", "name": "build_road", "arguments": "{not json"}


def test_a_completion_maps_to_the_frozen_response_shape() -> None:
    usage = Usage(prompt_tokens=11, completion_tokens=7, total_tokens=18)
    completion = Completion(
        text=None,
        tool_calls=(ToolCall(id="call-3", name="take", arguments={}),),
        usage=usage,
    )

    assert completion.to_mapping() == {
        "text": None,
        "tool_calls": [{"id": "call-3", "name": "take", "arguments": {}}],
    }
    assert usage.to_mapping() == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }


def test_the_messages_are_provider_neutral_values() -> None:
    """A transcript is plain data: no client, no vendor and no mutable state in it."""
    message = Message(role=Role.USER, content="It is your turn.")

    assert message.role is Role.USER
    assert isinstance(message.to_mapping()["role"], str)
    assert not hasattr(message, "to_openai")


def _fixture_record() -> dict[str, JsonValue]:
    first = DECISION_FIXTURE.read_text(encoding="utf-8").splitlines()[0]
    record: dict[str, JsonValue] = json.loads(first)
    return record


def test_the_values_fit_the_frozen_decision_contract() -> None:
    """K-002's shape is the target, and an unknown usage is one of its accepted values."""
    record = _fixture_record()
    record["messages"] = [Message(role=Role.USER, content="It is your turn.").to_mapping()]
    record["response"] = Completion(
        text=None,
        tool_calls=(ToolCall(id="call-1", name="take", arguments={}),),
        usage=None,
    ).to_mapping()
    record["usage"] = Usage(prompt_tokens=1, completion_tokens=2, total_tokens=3).to_mapping()
    assert validate_decision(record) == []

    record["usage"] = None
    assert validate_decision(record) == [], "an omitted usage is declared as null, not as zero"
