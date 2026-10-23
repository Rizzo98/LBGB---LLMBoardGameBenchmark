"""The provider seam: one method, provider-neutral values (PRD-v2 FR-5.1, FR-5.6).

ARCHITECTURE.md section 13 is deliberately narrow:

    LLMProvider.complete(messages, tools, config) -> { text, tool_calls, usage }

Everything a gateway needs is expressible in those four values, and nothing else belongs in the
seam. The protocol has exactly one member, `complete`; the messages, tool calls and usage are
plain immutable data, so an adapter can translate them without the tool loop learning a vendor's
vocabulary. A provider is anything that satisfies the method, structurally - no base class to
inherit, no registration to remember.

**Usage is a triple or it is unknown (FR-5.6).** Providers differ in what they report; some omit
usage entirely, some omit only the total. A missing count is not zero: recording it as zero would
make an unknown cost look free and would silently corrupt every aggregate built on it. So a known
usage is three non-negative integers, an omitted total is derived from its parts, and an
incomplete report is `None` - the same null the sidecar contract already declares.

**The transcript is provider-neutral.** The exact request bytes belong to the adapter (FR-5.4);
this module holds the decoded conversation every provider receives, in the shape the frozen
decision record uses. That is what lets a record be reconstructed without knowing which gateway
produced it (FR-10.4).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable

from lgbg.core.types import JsonValue

SAMPLING_MAX: Final[int] = 1000
"""Sampling is recorded in thousandths, because the canonical serialiser has no floats."""


class Role(StrEnum):
    """The four roles a conversation is made of, spelled as the record spells them."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ProviderError(Exception):
    """A provider could not answer: a transport failure, not a game decision."""


class ProviderTimeoutError(ProviderError):
    """The provider did not answer in time. The policy above decides what that means."""


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One tool call the model asked for, parsed or raw.

    `arguments` is the decoded object when the provider parsed it, and the raw text when it did
    not (FR-7.6). Keeping the raw text is what lets the failure be recorded as what it was rather
    than repaired into something the model never said.
    """

    id: str
    name: str
    arguments: Mapping[str, JsonValue] | str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("a tool call must have an id")
        if not self.name:
            raise ValueError("a tool call must name a tool")

    def to_mapping(self) -> dict[str, JsonValue]:
        arguments: JsonValue = (
            self.arguments if isinstance(self.arguments, str) else dict(self.arguments)
        )
        return {"id": self.id, "name": self.name, "arguments": arguments}


@dataclass(frozen=True, slots=True)
class Message:
    """One turn of the provider-neutral transcript, with every field the record declares."""

    role: Role
    content: str | None
    tool_calls: tuple[ToolCall, ...] | None = None
    tool_call_id: str | None = None

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "role": self.role.value,
            "content": self.content,
            "tool_calls": (
                None if self.tool_calls is None else [call.to_mapping() for call in self.tool_calls]
            ),
            "tool_call_id": self.tool_call_id,
        }


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One tool offered to the model: the generated definition, without any protocol envelope."""

    name: str
    description: str
    input_schema: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class Usage:
    """What one call cost, in tokens. A known usage is always all three counts."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def __post_init__(self) -> None:
        for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer, got {value!r}")

    @classmethod
    def normalise(
        cls,
        *,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
    ) -> Usage | None:
        """The provider's report as a complete triple, or `None` when it cannot be known.

        A total the provider omitted is the sum of its parts, which is arithmetic rather than
        invention. A report missing either part is not completed by guessing: it is unknown.
        """
        if prompt_tokens is None or completion_tokens is None:
            return None
        total = total_tokens if total_tokens is not None else prompt_tokens + completion_tokens
        return cls(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True, slots=True)
class Sampling:
    """Sampling parameters in thousandths, the unit the run manifest declares (K-002)."""

    temperature_milli: int = 0
    top_p_milli: int = SAMPLING_MAX
    seed: int | None = None

    def __post_init__(self) -> None:
        for name in ("temperature_milli", "top_p_milli"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{name} must be an integer")
            if not 0 <= value <= SAMPLING_MAX:
                raise ValueError(f"{name} must be between 0 and {SAMPLING_MAX}, got {value}")
        if self.seed is not None and (
            not isinstance(self.seed, int) or isinstance(self.seed, bool)
        ):
            raise ValueError(f"seed must be an integer or None, got {self.seed!r}")

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "temperature_milli": self.temperature_milli,
            "top_p_milli": self.top_p_milli,
            "seed": self.seed,
        }


@dataclass(frozen=True, slots=True)
class CompletionConfig:
    """What the tool loop asks for: a model and the sampling it was configured with."""

    model: str
    sampling: Sampling = field(default_factory=Sampling)
    max_tokens: int | None = None

    def __post_init__(self) -> None:
        if not self.model:
            raise ValueError("a completion config must name its model")
        if self.max_tokens is not None and self.max_tokens < 1:
            raise ValueError(f"max_tokens must be positive, got {self.max_tokens}")


@dataclass(frozen=True, slots=True)
class Completion:
    """One answer: text, tool calls, and what it cost - or the explicit unknown."""

    text: str | None
    tool_calls: tuple[ToolCall, ...] | None
    usage: Usage | None

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "text": self.text,
            "tool_calls": (
                None if self.tool_calls is None else [call.to_mapping() for call in self.tool_calls]
            ),
        }


@runtime_checkable
class Provider(Protocol):
    """The one method every adapter implements, and the only one the loop may call."""

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        config: CompletionConfig,
    ) -> Completion: ...


__all__: list[str] = [
    "SAMPLING_MAX",
    "Completion",
    "CompletionConfig",
    "Message",
    "Provider",
    "ProviderError",
    "ProviderTimeoutError",
    "Role",
    "Sampling",
    "ToolCall",
    "ToolSpec",
    "Usage",
]
