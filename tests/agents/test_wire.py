"""The exact exchange, and the redaction that makes it safe to keep (PRD-v2 FR-5.4, FR-5.5, NFR-7).

The adapter records what it sent and what it received, body for body. The only transformation
allowed on the recorded copy is redaction: a credential must not reach an artefact, and the
sent request must be unchanged (FR-5.5).
"""

from __future__ import annotations

import json

from lgbg.agents.wire import (
    REDACTED,
    SENSITIVE_FIELDS,
    SENSITIVE_HEADERS,
    WireExchange,
    encode_request,
    redact,
    redact_headers,
)
from lgbg.core.types import JsonValue


def test_the_exchange_keeps_the_exact_bodies_and_headers() -> None:
    request = '{"model":"m","messages":[{"role":"user","content":"hi"}]}'
    response = '{"choices":[{"message":{"content":"ok"}}],"usage":{"prompt_tokens":1}}'
    exchange = WireExchange.capture(
        request=request,
        response=response,
        status_code=200,
        request_headers={"Content-Type": "application/json"},
        response_headers={"Content-Type": "application/json"},
    )

    assert exchange.request == request
    assert exchange.response == response
    assert exchange.status_code == 200
    assert exchange.to_mapping() == {
        "request": request,
        "response": response,
        "status_code": 200,
        "request_headers": {"Content-Type": "application/json"},
        "response_headers": {"Content-Type": "application/json"},
    }


def test_a_sensitive_header_is_redacted_and_an_ordinary_one_is_kept() -> None:
    headers = {
        "Authorization": "Bearer sk-secret",
        "X-Api-Key": "sk-secret",
        "Content-Type": "application/json",
    }

    recorded = redact_headers(headers)

    assert recorded["Authorization"] == REDACTED
    assert recorded["X-Api-Key"] == REDACTED
    assert recorded["Content-Type"] == "application/json"
    assert all("sk-secret" not in value for value in recorded.values())


def test_a_secret_anywhere_in_a_body_is_redacted_and_the_rest_is_verbatim() -> None:
    body = json.dumps({"model": "m", "echo": "the key is sk-secret", "n": 1})
    exchange = WireExchange.capture(
        request=body,
        response=None,
        request_headers={"Authorization": "Bearer sk-secret"},
        secrets=("sk-secret",),
    )

    assert "sk-secret" not in (exchange.request or "")
    assert "the key is [redacted]" in (exchange.request or "")
    assert '"model": "m"' in (exchange.request or "")
    assert exchange.response is None
    assert exchange.status_code is None


def test_nested_credential_fields_are_redacted_by_name() -> None:
    record: dict[str, JsonValue] = {
        "ok": True,
        "api_key": "sk-secret",
        "nested": {"password": "hunter2", "keep": "this"},
        "items": [{"access_token": "abc"}, 3],
    }

    assert redact(record) == {
        "ok": True,
        "api_key": REDACTED,
        "nested": {"password": REDACTED, "keep": "this"},
        "items": [{"access_token": REDACTED}, 3],
    }


def test_the_declared_sensitive_sets_cover_the_obvious_names() -> None:
    assert {"authorization", "x-api-key"} <= SENSITIVE_HEADERS
    assert {"api_key", "password", "secret", "token"} <= SENSITIVE_FIELDS


def test_encoding_a_request_is_the_text_that_is_sent() -> None:
    payload = {"messages": [{"content": "hi", "role": "user"}], "model": "m"}

    text = encode_request(payload)

    assert text == '{"messages":[{"content":"hi","role":"user"}],"model":"m"}'
    assert json.loads(text) == payload
    assert " " not in text


def test_an_exchange_round_trips_through_its_recorded_shape() -> None:
    exchange = WireExchange.capture(
        request='{"model":"m"}',
        response='{"ok":true}',
        status_code=200,
        request_headers={"Authorization": REDACTED},
        response_headers={},
    )

    assert WireExchange.from_mapping(exchange.to_mapping()) == exchange
