"""The verbatim exchange and the redaction that makes recording it safe (PRD-v2 FR-5.4, FR-5.5).

A record that cannot answer "what exactly was the model shown, and what did it say?" is not
evidence. So the adapter keeps the exact request body it sent and the exact response body it
received, as text: those are the bytes, and re-serialising a decoded object would be a second
rendering that could differ from the first.

The credential in an OpenAI-compatible request is a header, which is why headers are recorded with
their sensitive values replaced rather than omitted. A body that happens to contain the key - a
test that echoes it, a provider that reports it back - is redacted by exact match. Redaction
happens when the exchange is built, before any writer sees it, and the sidecar applies the same
rule again as a second gate (NFR-7).

PRD-v2 FR-5.5 is the other half: the adapter never retries, summarises, repairs or otherwise
changes a request. The recorded request is the request that was sent.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from lgbg.core.canonical import to_wire_json
from lgbg.core.types import JsonValue

REDACTED: Final[str] = "[redacted]"
"""What a credential becomes. A marker, not an empty string: absent and redacted are different."""

SENSITIVE_HEADERS: Final[frozenset[str]] = frozenset(
    {"authorization", "cookie", "proxy-authorization", "set-cookie", "x-api-key"}
)
"""Header names whose value is a credential. Compared case-insensitively."""

SENSITIVE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "password",
        "refresh_token",
        "secret",
        "token",
    }
)
"""Object keys whose value is a credential, wherever they appear in a record."""


def redact_text(text: str, *, secrets: Sequence[str] = ()) -> str:
    """The text with every known secret replaced.

    Longer secrets are replaced first, so a short one cannot mask part of a longer one.
    """
    for secret in sorted((secret for secret in secrets if secret), key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    return text


def redact_headers(headers: Mapping[str, str], *, secrets: Sequence[str] = ()) -> dict[str, str]:
    """The headers with sensitive names and known secret values replaced."""
    return {
        name: (
            REDACTED if name.lower() in SENSITIVE_HEADERS else redact_text(value, secrets=secrets)
        )
        for name, value in headers.items()
    }


def redact(value: JsonValue, *, secrets: Sequence[str] = ()) -> JsonValue:
    """A record with every credential-shaped field and every known secret replaced."""
    if isinstance(value, Mapping):
        return {
            key: (REDACTED if key.lower() in SENSITIVE_FIELDS else redact(item, secrets=secrets))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, secrets=secrets) for item in value]
    if isinstance(value, str):
        return redact_text(value, secrets=secrets)
    return value


@dataclass(frozen=True, slots=True)
class WireExchange:
    """One HTTP exchange, body for body, with credentials already removed.

    'request' and 'response' are the exact bodies as text. A failed call has a request and no
    response; a timeout has neither response nor status. Both are recorded as null rather than
    omitted, so a reader can tell "there was no answer" from "this record forgot to say".
    """

    request: str | None
    response: str | None
    status_code: int | None = None
    request_headers: Mapping[str, str] = field(default_factory=dict)
    response_headers: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def capture(
        cls,
        *,
        request: str | None,
        response: str | None,
        status_code: int | None = None,
        request_headers: Mapping[str, str] | None = None,
        response_headers: Mapping[str, str] | None = None,
        secrets: Sequence[str] = (),
    ) -> WireExchange:
        """One exchange with every credential removed before the value exists."""
        return cls(
            request=None if request is None else redact_text(request, secrets=secrets),
            response=None if response is None else redact_text(response, secrets=secrets),
            status_code=status_code,
            request_headers=redact_headers(request_headers or {}, secrets=secrets),
            response_headers=redact_headers(response_headers or {}, secrets=secrets),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "request": self.request,
            "response": self.response,
            "status_code": self.status_code,
            "request_headers": dict(self.request_headers),
            "response_headers": dict(self.response_headers),
        }

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, JsonValue]) -> WireExchange:
        """Read a recorded exchange back, refusing a shape this value cannot hold."""
        request = mapping.get("request")
        response = mapping.get("response")
        status = mapping.get("status_code")
        headers = mapping.get("request_headers")
        response_headers = mapping.get("response_headers")
        if request is not None and not isinstance(request, str):
            raise ValueError("wire request must be text or null")
        if response is not None and not isinstance(response, str):
            raise ValueError("wire response must be text or null")
        if status is not None and (not isinstance(status, int) or isinstance(status, bool)):
            raise ValueError("wire status_code must be an integer or null")
        return cls(
            request=request,
            response=response,
            status_code=status,
            request_headers=_headers(headers),
            response_headers=_headers(response_headers),
        )


def _headers(value: JsonValue) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("wire headers must be an object")
    headers: dict[str, str] = {}
    for name, item in value.items():
        if not isinstance(item, str):
            raise ValueError(f"wire header {name!r} must be text")
        headers[name] = item
    return headers


def encode_request(payload: Mapping[str, Any]) -> str:
    """The exact JSON text a request body is sent as.

    Compact separators and stable key order make the recorded text and the sent bytes the same
    string, which is what 'verbatim' has to mean for a test to be able to compare them.
    """
    return to_wire_json(payload)


__all__: list[str] = [
    "REDACTED",
    "SENSITIVE_FIELDS",
    "SENSITIVE_HEADERS",
    "WireExchange",
    "encode_request",
    "redact",
    "redact_headers",
    "redact_text",
]
