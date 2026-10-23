"""The mock provider: every behaviour a model can have, named (PRD-v2 FR-5.2, PRD-v2 FR-15.1).

Slice 5 is where a model behaves badly, and none of it is testable against a real provider without
spending money and waiting for a network. The mock is therefore not a convenience double: it is the
fixture the failure policy is built on. Each behaviour is a named value, so a failure kind in a
record can be traced back to the behaviour that produced it.

The behaviours are scripted rather than clever. The mock has no opinion about Catan or legality:
the test supplies the action it should emit, or the mock emits prose, malformed arguments, a
timeout or an endless series of calls. That keeps the double honest - it cannot accidentally
"play well" because it knows the game.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from lgbg.agents.providers.base import (
    Completion,
    CompletionConfig,
    Message,
    Provider,
    ProviderTimeoutError,
    Role,
    ToolCall,
    ToolSpec,
)
from lgbg.agents.providers.mock import (
    RUNAWAY_TOOL,
    Behaviour,
    MockProvider,
    MockScriptError,
)

MESSAGES = [Message(role=Role.USER, content="It is your turn.")]
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
CONFIG = CompletionConfig(model="mock-model")


def complete(provider: MockProvider) -> Completion:
    return asyncio.run(provider.complete(MESSAGES, TOOLS, CONFIG))


def test_every_behaviour_is_named_and_distinct() -> None:
    assert {behaviour.value for behaviour in Behaviour} == {
        "correct-play",
        "always-illegal",
        "malformed-arguments",
        "prose-only",
        "timeout",
        "runaway",
    }


def test_the_mock_is_a_provider_and_labels_its_behaviour() -> None:
    action = ToolCall(id="call-1", name="take", arguments={})
    provider = MockProvider(Behaviour.CORRECT_PLAY, action=action)

    assert isinstance(provider, Provider)
    assert provider.behaviour is Behaviour.CORRECT_PLAY
    assert provider.label == "mock:correct-play"


def test_correct_play_returns_the_scripted_actions_in_order() -> None:
    first = ToolCall(id="call-1", name="take", arguments={})
    second = ToolCall(id="call-2", name="take", arguments={})
    provider = MockProvider(Behaviour.CORRECT_PLAY, actions=[first, second])

    assert complete(provider).tool_calls == (first,)
    assert complete(provider).tool_calls == (second,)


def test_correct_play_needs_something_to_play() -> None:
    with pytest.raises(ValueError, match="needs at least one action"):
        MockProvider(Behaviour.CORRECT_PLAY)


def test_a_script_that_runs_out_is_loud() -> None:
    provider = MockProvider(
        Behaviour.CORRECT_PLAY, action=ToolCall(id="call-1", name="take", arguments={})
    )
    complete(provider)

    with pytest.raises(MockScriptError):
        complete(provider)


def test_always_illegal_repeats_the_same_refused_action() -> None:
    illegal = ToolCall(id="call-illegal", name="spend", arguments={})
    provider = MockProvider(Behaviour.ALWAYS_ILLEGAL, action=illegal)

    assert complete(provider).tool_calls == (illegal,)
    assert complete(provider).tool_calls == (illegal,)


def test_malformed_arguments_are_a_known_tool_with_unparseable_arguments() -> None:
    provider = MockProvider(Behaviour.MALFORMED_ARGUMENTS)

    completion = complete(provider)
    assert completion.tool_calls is not None
    call = completion.tool_calls[0]
    assert call.name == TOOLS[0].name, "the tool exists; only the arguments are broken"
    assert isinstance(call.arguments, str)
    with pytest.raises(json.JSONDecodeError):
        json.loads(call.arguments)


def test_prose_only_emits_text_and_no_action() -> None:
    completion = complete(MockProvider(Behaviour.PROSE_ONLY))

    assert completion.text
    assert completion.tool_calls is None


def test_timeout_raises_the_provider_timeout() -> None:
    provider = MockProvider(Behaviour.TIMEOUT)

    with pytest.raises(ProviderTimeoutError):
        complete(provider)


def test_runaway_keeps_making_calls_and_never_stops() -> None:
    provider = MockProvider(Behaviour.RUNAWAY)

    completions = [complete(provider) for _ in range(20)]
    names: list[str] = []
    for completion in completions:
        assert completion.tool_calls is not None
        names.append(completion.tool_calls[0].name)

    assert set(names) == {RUNAWAY_TOOL}
    assert provider.calls == 20, "the behaviour is a runaway, not one long call"


def test_usage_is_known_by_default_and_can_be_omitted() -> None:
    action = ToolCall(id="call-1", name="take", arguments={})
    known = complete(MockProvider(Behaviour.CORRECT_PLAY, action=action))
    omitted = complete(MockProvider(Behaviour.CORRECT_PLAY, action=action, usage=None))

    assert known.usage is not None
    assert known.usage.total_tokens >= known.usage.prompt_tokens
    assert omitted.usage is None, "an omitted usage is unknown, not zero"
