"""The decision sidecar: one line per model request, written only after it is safe (FR-10.4, NFR-7).

The god log holds the game and nothing else. Everything a model adds goes here: the transcript it
was shown, the response it gave, the exchange in full, and later the accounting. The shape is
K-002's closed decision schema, so a writer cannot invent a field and a reader cannot be surprised
by one.

Two gates stand between a completion and the file:

- **Redaction.** The adapter already removes the credential it knows about, and this writer applies
  the same rule to the whole record with any secret the run supplies. Redaction happens before the
  file is opened, so a refused record leaves no partial line and no credential ever reaches disk.
- **Validation.** A record is checked against the declared shape before it is serialised. A writer
  that skipped this would turn a schema into documentation.

The file is appended one canonical line at a time, under a lock. A process that dies mid-write
leaves a truncated last line, which the reader sees as a truncation rather than mistaking it for a
complete record.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from threading import Lock

from lgbg.agents.accounting import DecisionUsage
from lgbg.agents.loop import Attempt
from lgbg.agents.providers.base import CallMetadata, Completion
from lgbg.agents.wire import redact
from lgbg.core.canonical import to_canonical_json
from lgbg.core.contracts import validate_abandonment, validate_decision
from lgbg.core.log import sidecar_path
from lgbg.core.types import GameId, JsonValue


class SidecarError(ValueError):
    """A record does not fit the declared decision shape, so it was not written."""


def decision_path(run_directory: Path, game_id: GameId) -> Path:
    """Where one game's decision records live, named by the same convention as its god log."""
    return sidecar_path(run_directory, game_id)


def wire_of(completion: Completion) -> dict[str, JsonValue]:
    """The exact exchange an answer carries, or a refusal when the adapter recorded none.

    Every provider is expected to attach one (FR-5.4). A missing exchange is not written as null
    for a successful call: that would turn "this adapter did not record" into "there was nothing
    to record", and the two are different findings.
    """
    metadata: CallMetadata | None = completion.metadata
    if metadata is None or metadata.wire is None:
        raise SidecarError("the completion carries no recorded request/response exchange")
    return metadata.wire.to_mapping()


def build_decision_record(
    *,
    game_id: GameId,
    seat: int,
    model: str,
    provider: str,
    request_id: str,
    attempt: Attempt,
    outcome: Mapping[str, JsonValue],
    accounting: DecisionUsage,
    redo_budget: int,
    at: str,
    host: str,
    pid: int,
    seq: int | None,
    rejection: Mapping[str, JsonValue] | None = None,
    failure: str | None = None,
) -> dict[str, JsonValue]:
    """One sidecar line: the exact request, the exact response, and what came of it (FR-10.3).

    The messages come from the attempt, not from the final conversation, because a redo turn's
    later messages are not what the earlier request was shown. A turn with no captured messages is
    refused rather than written as an empty list, which would make the record silently useless.
    """
    if not attempt.messages:
        raise SidecarError("the attempt carries no request messages")
    if accounting.model != model:
        raise SidecarError(f"the accounting entry is for {accounting.model!r}, not {model!r}")
    completion = attempt.completion
    metadata = completion.metadata
    return {
        "t": "decision",
        "at": at,
        "host": host,
        "pid": pid,
        "game_id": game_id,
        "seq": seq,
        "request_id": request_id,
        "player": seat,
        "seat": seat,
        "model": model,
        "provider": provider,
        "route": None if metadata is None else metadata.route,
        "native_tools": False if metadata is None else metadata.native_tools,
        "attempt": attempt.attempt,
        "redo_budget": redo_budget,
        "messages": [message.to_mapping() for message in attempt.messages],
        "response": completion.to_mapping(),
        "wire": wire_of(completion),
        "outcome": dict(outcome),
        "rejection": None if rejection is None else dict(rejection),
        "usage": None if completion.usage is None else completion.usage.to_mapping(),
        "cost_micro_usd": accounting.cost_micro_usd,
        "latency_ms": attempt.latency_ms,
        "failure": attempt.failure if failure is None else failure,
    }


def build_abandonment_record(
    *,
    game_id: GameId,
    request_id: str,
    seat: int,
    model: str,
    provider: str,
    attempts: int,
    redo_budget: int,
    final_rejection: Mapping[str, JsonValue] | None,
    failure: str,
    actions: int,
    at: str,
    host: str,
    pid: int,
) -> dict[str, JsonValue]:
    """One abandonment record: the game ended because this seat could not act (FR-7.5).

    It is not a terminal record and does not pretend to be a verdict. It names the failing
    decision, the refusal that ended it, how much of the redo budget was spent, and the seat and
    model responsible, which is what makes abandonment a finding about a model rather than a
    missing game (FR-11.6, FR-11.8).
    """
    return {
        "t": "abandonment",
        "at": at,
        "host": host,
        "pid": pid,
        "game_id": game_id,
        "request_id": request_id,
        "player": seat,
        "seat": seat,
        "model": model,
        "provider": provider,
        "attempts": attempts,
        "redo_budget": redo_budget,
        "final_rejection": None if final_rejection is None else dict(final_rejection),
        "failure": failure,
        "actions": actions,
    }


def messages_from_run(
    run_directory: Path,
    game_id: GameId,
    request_id: str,
    *,
    attempt: int | None = None,
) -> list[dict[str, JsonValue]]:
    """The exact messages one call was sent, read from the run directory and nothing else.

    This is the reader SC-4 asks for: it needs no provider, no prompt file and no live game. A
    decision with a redo has several records sharing one request id; without an attempt number the
    last one is returned, which is the call that produced the final answer. Naming an attempt
    returns the call that belonged to it, so every retry can be reconstructed, not only the last
    (FR-7.3, FR-10.4).
    """
    found: dict[str, JsonValue] | None = None
    for record in DecisionSidecar(decision_path(run_directory, game_id)).records():
        if record.get("request_id") != request_id:
            continue
        if attempt is not None and record.get("attempt") != attempt:
            continue
        found = record
    if found is None:
        wanted = "" if attempt is None else f" attempt {attempt}"
        raise SidecarError(f"no decision record for {request_id!r}{wanted}")
    messages = found.get("messages")
    if not isinstance(messages, list):
        raise SidecarError(f"decision {request_id!r} carries no message list")
    return [dict(message) for message in messages if isinstance(message, dict)]


class DecisionSidecar:
    """The append-only decision record of one game."""

    def __init__(self, path: Path, *, secrets: Sequence[str] = ()) -> None:
        self._path = path
        self._secrets = tuple(secret for secret in secrets if secret)
        self._lock = Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: Mapping[str, JsonValue]) -> None:
        """Redact, validate, then append one decision line. A refused record writes nothing."""
        self._append(record, validate_decision, kind="decision")

    def append_abandonment(self, record: Mapping[str, JsonValue]) -> None:
        """Append the record that says the game produced no outcome (FR-7.5)."""
        self._append(record, validate_abandonment, kind="abandonment")

    def _append(
        self,
        record: Mapping[str, JsonValue],
        validate: Callable[[Mapping[str, JsonValue]], list[str]],
        *,
        kind: str,
    ) -> None:
        cleaned = redact(dict(record), secrets=self._secrets)
        if not isinstance(cleaned, Mapping):
            raise SidecarError(f"a {kind} record must be an object")
        problems = validate(cleaned)
        if problems:
            raise SidecarError("; ".join(problems))
        line = to_canonical_json(cleaned)
        with self._lock, self._path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def records(self) -> list[dict[str, JsonValue]]:
        """Every record written so far, in order. A reader, not a second source of truth."""
        if not self._path.exists():
            return []
        found: list[dict[str, JsonValue]] = []
        for number, line in enumerate(self._path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            loaded = _load(line, number)
            found.append(loaded)
        return found


def _load(line: str, number: int) -> dict[str, JsonValue]:
    import json

    try:
        value = json.loads(line)
    except json.JSONDecodeError as error:
        raise SidecarError(f"line {number} is not JSON: {error}") from error
    if not isinstance(value, dict):
        raise SidecarError(f"line {number} is not an object")
    return value


__all__: list[str] = [
    "DecisionSidecar",
    "SidecarError",
    "build_abandonment_record",
    "build_decision_record",
    "decision_path",
    "messages_from_run",
    "wire_of",
]
