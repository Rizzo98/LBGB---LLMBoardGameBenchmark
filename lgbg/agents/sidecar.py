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
from collections.abc import Mapping, Sequence
from pathlib import Path
from threading import Lock

from lgbg.agents.providers.base import CallMetadata, Completion
from lgbg.agents.wire import redact
from lgbg.core.canonical import to_canonical_json
from lgbg.core.contracts import validate_decision
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
        """Redact, validate, then append one line. A refused record writes nothing."""
        cleaned = redact(dict(record), secrets=self._secrets)
        if not isinstance(cleaned, Mapping):
            raise SidecarError("a decision record must be an object")
        problems = validate_decision(cleaned)
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
    "decision_path",
    "wire_of",
]
