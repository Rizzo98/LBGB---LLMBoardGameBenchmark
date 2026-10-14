"""The god log: the deterministic record and its sidecar (ARCHITECTURE.md section 8).

Two files per game, and the split is the point:

- '<game_id>.god.jsonl' is the deterministic core record. Every byte of it is reproducible
  from the seed, the configuration and the actions, and every hash in it is asserted on
  replay. Nothing non-deterministic can enter it by accident, because there is nowhere for
  it to hide (P9).
- '<game_id>.meta.jsonl' is the sidecar: wall-clock time, host, process id, agent payloads
  and costs - everything that is real and useful and never reproducible.

The runtime owns the record vocabulary (FR-3.9). A game's narrative belongs in events; a
game that adds a record type has broken the contract, and the reader refuses it.

Records are serialised through 'core.canonical.to_canonical_json', so the log uses the same
single serialisation path as state hashing and replay (P8).
"""

from __future__ import annotations

import json
import os
import socket
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, Final

from lgbg import __version__
from lgbg.core.canonical import to_canonical_json
from lgbg.core.errors import Rejection
from lgbg.core.rng import RngDraw
from lgbg.core.types import Action, Event, GameId, JsonValue, PlayerId, Seq

ENGINE_VERSION: Final[str] = __version__
"""Recorded in every header, so a record names the engine that produced it."""

GOD_LOG_SCHEMA: Final[str] = "lgbg.game.v1"
"""Schema of the god log. The major version is what a reader must understand."""

SUPPORTED_SCHEMA_MAJOR: Final[int] = 1
SCHEMA_PREFIX: Final[str] = "lgbg.game.v"

GOD_LOG_SUFFIX: Final[str] = ".god.jsonl"
SIDECAR_SUFFIX: Final[str] = ".meta.jsonl"
GAMES_DIRECTORY: Final[str] = "games"

KIND_HEADER: Final[str] = "header"
KIND_ACTION: Final[str] = "action"
KIND_PHASE: Final[str] = "phase"
KIND_TERMINAL: Final[str] = "terminal"
RECORD_KINDS: Final[tuple[str, ...]] = (KIND_HEADER, KIND_ACTION, KIND_PHASE, KIND_TERMINAL)


class LogError(Exception):
    """Base class for every log failure."""


class LogFormatError(LogError):
    """A record is malformed, or the log violates the record contract."""


class TruncatedLogError(LogError):
    """The log ends mid-record: a crashed writer leaves a parseable prefix, and the tail."""


class UnknownRecordTypeError(LogFormatError):
    """A record type the runtime does not own."""


class UnsupportedSchemaError(LogError):
    """The log's schema major version is not one this reader understands."""


def god_log_path(run_directory: Path, game_id: GameId) -> Path:
    """The deterministic record of one game, inside a run directory."""
    return run_directory / GAMES_DIRECTORY / f"{game_id}{GOD_LOG_SUFFIX}"


def sidecar_path(run_directory: Path, game_id: GameId) -> Path:
    """The non-deterministic companion of one game's record."""
    return run_directory / GAMES_DIRECTORY / f"{game_id}{SIDECAR_SUFFIX}"


def rejected_result(rejection: Rejection) -> dict[str, JsonValue]:
    """The 'result' object of a rejected action.

    The record always carries the full details; filtering them by tier is the renderer's
    job, because a record that had been filtered could never be analysed afterwards
    (ARCHITECTURE.md section 10.3).
    """
    return {
        "ok": False,
        "error": rejection.code.code,
        "message": rejection.message,
        "details": dict(rejection.details),
    }


@dataclass(frozen=True, slots=True)
class HeaderRecord:
    """The first line: what was run, under which rules, with which configuration."""

    game_id: GameId
    game: str
    rules_version: str
    schema_version: str
    players: int
    config: Mapping[str, JsonValue]
    prompt_hashes: Mapping[str, str]
    initial_state_hash: str
    schema: str = GOD_LOG_SCHEMA
    engine_version: str = ENGINE_VERSION

    kind = KIND_HEADER


@dataclass(frozen=True, slots=True)
class ActionRecord:
    """One action attempt, accepted or rejected. The replay input."""

    seq: Seq
    player: PlayerId
    action: Action
    result: Mapping[str, JsonValue]
    state_hash_prev: str
    state_hash: str
    rng: Sequence[RngDraw]
    events: Sequence[Event]
    request_id: str | None = None

    kind = KIND_ACTION


@dataclass(frozen=True, slots=True)
class PhaseRecord:
    """A phase transition, logged because it makes a record greppable and replay debuggable.

    Its 'seq' is the seq of the next action: a phase transition is not an action attempt and
    does not consume a number in the action sequence.
    """

    seq: Seq
    phase: str
    detail: Mapping[str, JsonValue] = field(default_factory=dict)

    kind = KIND_PHASE


@dataclass(frozen=True, slots=True)
class TerminalRecord:
    """The last line. Counts that only the runtime can know are here, not in the outcome."""

    seq: Seq
    winner: PlayerId | None
    final_scores: Mapping[str, int]
    rounds: int
    total_actions: int
    rejections: int
    state_hash: str

    kind = KIND_TERMINAL


type GameRecord = HeaderRecord | ActionRecord | PhaseRecord | TerminalRecord


def _rng_to_mapping(draw: RngDraw) -> dict[str, JsonValue]:
    return {
        "args": dict(draw.args),
        "kind": draw.kind,
        "purpose": draw.purpose,
        "value": draw.value,
    }


def _event_to_mapping(event: Event) -> dict[str, JsonValue]:
    return {"payload": dict(event.payload), "type": event.type}


def record_to_mapping(record: GameRecord) -> dict[str, JsonValue]:
    """The JSON object of one record, as it appears on its line of the log."""
    match record:
        case HeaderRecord():
            return {
                "t": KIND_HEADER,
                "config": dict(record.config),
                "engine_version": record.engine_version,
                "game": record.game,
                "game_id": record.game_id,
                "initial_state_hash": record.initial_state_hash,
                "players": record.players,
                "prompt_hashes": dict(record.prompt_hashes),
                "rules_version": record.rules_version,
                "schema": record.schema,
                "schema_version": record.schema_version,
            }
        case ActionRecord():
            return {
                "t": KIND_ACTION,
                "action": {"params": dict(record.action.params), "type": record.action.type},
                "events": [_event_to_mapping(event) for event in record.events],
                "player": record.player,
                "request_id": record.request_id,
                "result": dict(record.result),
                "rng": [_rng_to_mapping(draw) for draw in record.rng],
                "seq": record.seq,
                "state_hash": record.state_hash,
                "state_hash_prev": record.state_hash_prev,
            }
        case PhaseRecord():
            return {
                "t": KIND_PHASE,
                "detail": dict(record.detail),
                "phase": record.phase,
                "seq": record.seq,
            }
        case TerminalRecord():
            return {
                "t": KIND_TERMINAL,
                "final_scores": dict(record.final_scores),
                "rejections": record.rejections,
                "rounds": record.rounds,
                "seq": record.seq,
                "state_hash": record.state_hash,
                "total_actions": record.total_actions,
                "winner": record.winner,
            }


def _object(value: JsonValue, what: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise LogFormatError(f"{what} must be a JSON object, got {value!r}")
    return value


def _string_map(value: JsonValue, what: str) -> Mapping[str, str]:
    fields = _object(value, what)
    strings: dict[str, str] = {}
    for key, item in fields.items():
        if not isinstance(item, str):
            raise LogFormatError(f"{what}[{key!r}] must be a string, got {item!r}")
        strings[key] = item
    return strings


def _sequence(value: JsonValue, what: str) -> Sequence[JsonValue]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise LogFormatError(f"{what} must be a JSON array, got {value!r}")
    return value


def _text(fields: Mapping[str, JsonValue], key: str, what: str) -> str:
    value = fields.get(key)
    if not isinstance(value, str):
        raise LogFormatError(f"{what}.{key} must be a string, got {value!r}")
    return value


def _integer(fields: Mapping[str, JsonValue], key: str, what: str) -> int:
    value = fields.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise LogFormatError(f"{what}.{key} must be an integer, got {value!r}")
    return value


def _optional_integer(fields: Mapping[str, JsonValue], key: str, what: str) -> int | None:
    value = fields.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise LogFormatError(f"{what}.{key} must be an integer or null, got {value!r}")
    return value


def _rng_from_mapping(raw: JsonValue) -> RngDraw:
    fields = _object(raw, "rng draw")
    return RngDraw(
        purpose=_text(fields, "purpose", "rng draw"),
        kind=_text(fields, "kind", "rng draw"),
        args=_object(fields.get("args"), "rng draw.args"),
        value=fields.get("value"),
    )


def _event_from_mapping(raw: JsonValue) -> Event:
    fields = _object(raw, "event")
    return Event(
        type=_text(fields, "type", "event"), payload=_object(fields.get("payload"), "event.payload")
    )


def record_from_mapping(mapping: Mapping[str, JsonValue]) -> GameRecord:
    """Parse one record, rejecting anything the runtime does not own (FR-3.9)."""
    kind = mapping.get("t")
    if kind not in RECORD_KINDS:
        raise UnknownRecordTypeError(
            f"unknown record type {kind!r}; the runtime owns {list(RECORD_KINDS)}"
        )
    if kind == KIND_HEADER:
        return HeaderRecord(
            game_id=_text(mapping, "game_id", "header"),
            game=_text(mapping, "game", "header"),
            rules_version=_text(mapping, "rules_version", "header"),
            schema_version=_text(mapping, "schema_version", "header"),
            players=_integer(mapping, "players", "header"),
            config=_object(mapping.get("config"), "header.config"),
            prompt_hashes=_string_map(mapping.get("prompt_hashes"), "header.prompt_hashes"),
            initial_state_hash=_text(mapping, "initial_state_hash", "header"),
            schema=_text(mapping, "schema", "header"),
            engine_version=_text(mapping, "engine_version", "header"),
        )
    if kind == KIND_ACTION:
        action = _object(mapping.get("action"), "action.action")
        request_id = mapping.get("request_id")
        return ActionRecord(
            seq=_integer(mapping, "seq", "action"),
            player=_integer(mapping, "player", "action"),
            action=Action(
                player=_integer(mapping, "player", "action"),
                type=_text(action, "type", "action.action"),
                params=_object(action.get("params"), "action.action.params"),
            ),
            result=_object(mapping.get("result"), "action.result"),
            state_hash_prev=_text(mapping, "state_hash_prev", "action"),
            state_hash=_text(mapping, "state_hash", "action"),
            rng=[_rng_from_mapping(item) for item in _sequence(mapping.get("rng"), "action.rng")],
            events=[
                _event_from_mapping(item)
                for item in _sequence(mapping.get("events"), "action.events")
            ],
            request_id=None if request_id is None else str(request_id),
        )
    if kind == KIND_PHASE:
        return PhaseRecord(
            seq=_integer(mapping, "seq", "phase"),
            phase=_text(mapping, "phase", "phase"),
            detail=_object(mapping.get("detail", {}), "phase.detail"),
        )
    scores = _object(mapping.get("final_scores"), "terminal.final_scores")
    return TerminalRecord(
        seq=_integer(mapping, "seq", "terminal"),
        winner=_optional_integer(mapping, "winner", "terminal"),
        final_scores={key: _integer(scores, key, "terminal.final_scores") for key in scores},
        rounds=_integer(mapping, "rounds", "terminal"),
        total_actions=_integer(mapping, "total_actions", "terminal"),
        rejections=_integer(mapping, "rejections", "terminal"),
        state_hash=_text(mapping, "state_hash", "terminal"),
    )


class GameLogWriter:
    """Writes one game's deterministic record, one canonical JSON object per line.

    Flushed after every record, so a crashed process leaves a truncated prefix that the
    reader can still use rather than an empty file (FR-3.8).
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle: IO[str] = path.open("w", encoding="utf-8", newline="\n")
        self._next_seq = 0
        self._header_written = False
        self._terminal_written = False

    def write_header(self, record: HeaderRecord) -> None:
        if self._header_written:
            raise LogFormatError("a header may only be written once, as the first line")
        self._write(record)
        self._header_written = True

    def write_action(self, record: ActionRecord) -> None:
        self._require_open()
        if record.player != record.action.player:
            raise LogFormatError(
                f"action record: player {record.player} disagrees with the action's player "
                f"{record.action.player}"
            )
        self._require_next_seq(record.seq)
        self._write(record)
        self._next_seq += 1

    def write_phase(self, record: PhaseRecord) -> None:
        self._require_open()
        self._require_next_seq(record.seq)
        self._write(record)

    def write_terminal(self, record: TerminalRecord) -> None:
        self._require_open()
        self._write(record)
        self._terminal_written = True

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.flush()
            os.fsync(self._handle.fileno())
            self._handle.close()

    def __enter__(self) -> GameLogWriter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _require_open(self) -> None:
        if not self._header_written:
            raise LogFormatError("the header record must be written first")
        if self._terminal_written:
            raise LogFormatError("nothing may follow the terminal record")

    def _require_next_seq(self, seq: Seq) -> None:
        if seq != self._next_seq:
            raise LogFormatError(
                f"records must be written in order: expected seq {self._next_seq}, got {seq}"
            )

    def _write(self, record: GameRecord) -> None:
        self._handle.write(to_canonical_json(record_to_mapping(record)) + "\n")
        self._handle.flush()


class SidecarWriter:
    """Writes the non-deterministic companion: when, where, and how much it cost.

    The clock is injected so that a test can assert what is written without depending on
    the wall clock, which is the same reason the engine may not read one.
    """

    def __init__(self, path: Path, *, clock: Callable[[], str] | None = None) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle: IO[str] = path.open("w", encoding="utf-8", newline="\n")
        self._clock = _utc_now if clock is None else clock

    def write(self, kind: str, payload: Mapping[str, JsonValue]) -> None:
        record: dict[str, JsonValue] = {
            "t": kind,
            "at": self._clock(),
            "host": socket.gethostname(),
            "pid": os.getpid(),
        }
        record.update(payload)
        self._handle.write(to_canonical_json(record) + "\n")
        self._handle.flush()

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.flush()
            os.fsync(self._handle.fileno())
            self._handle.close()

    def __enter__(self) -> SidecarWriter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class GameLog:
    """A parsed record. Replay and verification are the next layer up."""

    header: HeaderRecord
    records: Sequence[GameRecord]

    @property
    def actions(self) -> list[ActionRecord]:
        return [record for record in self.records if isinstance(record, ActionRecord)]

    @property
    def phases(self) -> list[PhaseRecord]:
        return [record for record in self.records if isinstance(record, PhaseRecord)]

    @property
    def terminal(self) -> TerminalRecord | None:
        for record in self.records:
            if isinstance(record, TerminalRecord):
                return record
        return None


class GameLogReader:
    """Reads one game's record, reporting truncation distinctly from malformation."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> GameLog:
        text = self._path.read_text(encoding="utf-8")
        if not text:
            raise TruncatedLogError(
                f"{self._path}: the log is empty; a game log begins with a header record"
            )
        lines = text.splitlines()
        if not text.endswith("\n"):
            raise TruncatedLogError(
                f"{self._path}: line {len(lines)} is incomplete; the record was cut short"
            )

        parsed: list[GameRecord] = []
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                raise LogFormatError(f"{self._path}: line {number} is blank")
            try:
                raw: Any = json.loads(line)
            except json.JSONDecodeError as error:
                raise LogFormatError(f"{self._path}: line {number} is not JSON: {error}") from error
            parsed.append(record_from_mapping(_object(raw, f"line {number}")))

        return self._validate(parsed)

    def _validate(self, records: list[GameRecord]) -> GameLog:
        header = records[0]
        if not isinstance(header, HeaderRecord):
            raise LogFormatError(
                f"{self._path}: a log begins with a header record, not {header.kind}"
            )
        self._require_supported_schema(header.schema)

        expected_seq = 0
        terminal_seen = False
        for record in records[1:]:
            if terminal_seen:
                raise LogFormatError(
                    f"{self._path}: nothing may follow the terminal record, found {record.kind}"
                )
            if isinstance(record, ActionRecord):
                if record.seq != expected_seq:
                    raise LogFormatError(
                        f"{self._path}: action seq must run 0, 1, 2, ...; expected {expected_seq}, "
                        f"got {record.seq}"
                    )
                expected_seq += 1
            elif isinstance(record, PhaseRecord) and record.seq > expected_seq:
                raise LogFormatError(
                    f"{self._path}: phase record names seq {record.seq} but only {expected_seq} "
                    "action(s) have been recorded"
                )
            elif isinstance(record, TerminalRecord):
                terminal_seen = True

        return GameLog(header=header, records=tuple(records))

    def _require_supported_schema(self, schema: str) -> None:
        if not schema.startswith(SCHEMA_PREFIX):
            raise UnsupportedSchemaError(
                f"{self._path}: unrecognised log schema {schema!r}; this reader understands "
                f"{GOD_LOG_SCHEMA}"
            )
        major_text = schema[len(SCHEMA_PREFIX) :].split(".")[0]
        try:
            major = int(major_text)
        except ValueError:
            raise UnsupportedSchemaError(
                f"{self._path}: unrecognised log schema {schema!r}; the major version must be "
                f"an integer, and this reader understands {SUPPORTED_SCHEMA_MAJOR}"
            ) from None
        if major != SUPPORTED_SCHEMA_MAJOR:
            raise UnsupportedSchemaError(
                f"{self._path}: log schema {schema!r} has major version {major}, and this reader "
                f"understands {SUPPORTED_SCHEMA_MAJOR}"
            )
