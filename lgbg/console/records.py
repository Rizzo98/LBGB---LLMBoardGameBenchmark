"""The console's read-only view of a standalone record (PRD-v3 FR-2.2, FR-2.7, FR-3.1).

A record is addressed by a *name*, never a path. A root is declared, the ``.god.jsonl`` files
directly under it are listed, and a handle resolves only inside that root. Listing reads one line
per record, so it stays cheap; opening parses and verifies the whole record, so the status is a
finding about the chain rather than a guess from the file's existence.

Nothing here writes. A failure is a value: a tampered record, a truncated tail, an unknown game
and an unsupported schema all come back as a :class:`LogSummary` with ``verified`` false and a
localised :class:`Failure`, which is what lets the API answer 200 with a finding instead of a 500.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from lgbg.core.game import GamePluginError, get_game
from lgbg.core.log import (
    GOD_LOG_SUFFIX,
    GameLog,
    GameLogReader,
    HeaderRecord,
    LogError,
    LogFormatError,
    TruncatedLogError,
    UnsupportedSchemaError,
    record_from_mapping,
)
from lgbg.core.replay import ReplayError, replay
from lgbg.core.types import JsonValue

VALID_LOG_ID: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
"""A handle is a file name without its suffix: no separator, no traversal, no leading dot."""


class ConsoleError(Exception):
    """Base class for the failures an operator starts the console with."""


class InvalidRootError(ConsoleError):
    """A declared root is not a directory."""


class InvalidLogIdError(ConsoleError):
    """A handle is not a record name."""


class UnknownLogError(ConsoleError):
    """No record under the declared roots has that handle, or it resolves outside them."""


@dataclass(frozen=True, slots=True)
class LogEntry:
    """One record found under a root. A malformed header is reported, not hidden."""

    id: str
    path: Path
    game: str | None
    rules_version: str | None
    problem: str | None = None


@dataclass(frozen=True, slots=True)
class Failure:
    """Why a record could not be verified, localised where the replay layer can localise it."""

    kind: str
    seq: int | None
    detail: str


@dataclass(frozen=True, slots=True)
class LogSummary:
    """What opening one record reports: the header, the chain and the verification finding."""

    id: str
    game: str | None
    rules_version: str | None
    schema_version: str | None
    engine_version: str | None
    actions: int | None
    rejections: int | None
    verified: bool
    completed: bool | None
    terminal_hash: str | None
    failure: Failure | None


class LogStore:
    """The declared roots, and the only way a record is opened.

    Roots are resolved once, at construction. A missing directory is refused there rather than
    silently yielding an empty list, because an empty console and a mistyped ``--root`` look the
    same to an operator and mean different things.
    """

    def __init__(self, roots: Sequence[Path]) -> None:
        resolved: list[Path] = []
        for root in roots:
            path = root.resolve()
            if not path.is_dir():
                raise InvalidRootError(f"not a directory: {root}")
            resolved.append(path)
        self._roots: tuple[Path, ...] = tuple(resolved)

    @property
    def roots(self) -> tuple[Path, ...]:
        return self._roots

    def entries(self) -> list[LogEntry]:
        """Every record directly under a root, ordered by handle, first root winning a clash."""
        found: dict[str, LogEntry] = {}
        for root in self._roots:
            for path in sorted(root.iterdir(), key=lambda item: item.name):
                if not path.name.endswith(GOD_LOG_SUFFIX):
                    continue
                handle = path.name[: -len(GOD_LOG_SUFFIX)]
                if not handle or not VALID_LOG_ID.fullmatch(handle):
                    continue
                if not path.is_file():
                    continue
                resolved = path.resolve()
                if not resolved.is_relative_to(root):
                    continue
                found.setdefault(handle, _entry(handle, resolved))
        return sorted(found.values(), key=lambda entry: entry.id)

    def resolve(self, handle: str) -> LogEntry:
        """Open one handle, refusing a path, a traversal and a symlink that leaves the roots."""
        if not VALID_LOG_ID.fullmatch(handle):
            raise InvalidLogIdError(f"not a record name: {handle!r}")
        for root in self._roots:
            candidate = root / f"{handle}{GOD_LOG_SUFFIX}"
            if not candidate.is_file():
                continue
            resolved = candidate.resolve()
            if not resolved.is_relative_to(root):
                raise UnknownLogError(f"{handle!r} resolves outside the declared root")
            return _entry(handle, resolved)
        raise UnknownLogError(f"no record named {handle!r} under the declared roots")


def read_summary(entry: LogEntry) -> LogSummary:
    """Verify one record and report the result, including every way it can be unverifiable."""
    if entry.problem is not None:
        return _unverified(entry, Failure("unreadable", None, entry.problem))

    try:
        log = _read_log(entry.path)
    except TruncatedLogError as error:
        return _unverified(entry, Failure("truncated", None, str(error)))
    except UnsupportedSchemaError as error:
        return _unverified(entry, Failure("unsupported_schema", None, str(error)))
    except (LogError, OSError) as error:
        return _unverified(entry, Failure("malformed", None, str(error)))

    header = log.header
    try:
        game = get_game(header.game)
    except GamePluginError as error:
        return _unverified(entry, Failure("unknown_game", None, str(error)))

    if header.rules_version != game.rules_version or header.schema_version != game.schema_version:
        return _unverified(
            entry,
            Failure(
                "incompatible",
                None,
                f"record {header.rules_version}/{header.schema_version} does not match the "
                f"installed {game.rules_version}/{game.schema_version}",
            ),
        )

    try:
        replayed = replay(log, game)
    except ReplayError as error:
        return _unverified(entry, Failure(error.kind.value, error.seq, error.detail))
    except LogError as error:
        return _unverified(entry, Failure("malformed", None, str(error)))

    return LogSummary(
        id=entry.id,
        game=header.game,
        rules_version=header.rules_version,
        schema_version=header.schema_version,
        engine_version=header.engine_version,
        actions=replayed.actions,
        rejections=replayed.rejections,
        verified=True,
        completed=log.terminal is not None,
        terminal_hash=replayed.terminal_hash,
        failure=None,
    )


def _read_log(path: Path) -> GameLog:
    return GameLogReader(path).read()


def _entry(handle: str, path: Path) -> LogEntry:
    try:
        header = _read_header(path)
    except (LogError, OSError, ValueError) as error:
        return LogEntry(id=handle, path=path, game=None, rules_version=None, problem=str(error))
    return LogEntry(
        id=handle,
        path=path,
        game=header.game,
        rules_version=header.rules_version,
        problem=None,
    )


def _read_header(path: Path) -> HeaderRecord:
    """Read the first line only: a listing must not pay for the whole record."""
    with path.open("r", encoding="utf-8") as handle:
        first = handle.readline()
    if not first.strip():
        raise LogFormatError(f"{path}: the record is empty")
    try:
        raw: object = json.loads(first)
    except json.JSONDecodeError as error:
        raise LogFormatError(f"{path}: the header is not JSON: {error}") from error
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        raise LogFormatError(f"{path}: the header is not a JSON object")
    record = record_from_mapping(cast("dict[str, JsonValue]", raw))
    if not isinstance(record, HeaderRecord):
        raise LogFormatError(f"{path}: the record does not begin with a header")
    return record


def _unverified(entry: LogEntry, failure: Failure) -> LogSummary:
    return LogSummary(
        id=entry.id,
        game=entry.game,
        rules_version=entry.rules_version,
        schema_version=None,
        engine_version=None,
        actions=None,
        rejections=None,
        verified=False,
        completed=None,
        terminal_hash=None,
        failure=failure,
    )


__all__ = [
    "ConsoleError",
    "Failure",
    "InvalidLogIdError",
    "InvalidRootError",
    "LogEntry",
    "LogStore",
    "LogSummary",
    "UnknownLogError",
    "read_summary",
]
