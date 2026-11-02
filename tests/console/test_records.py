"""The console's standalone-record reader (PRD-v3 FR-2.2, PRD-v3 FR-2.7, PRD-v3 FR-3.1).

The console never guesses where a record is: a root is declared, the records directly under it
are listed, and a handle resolves to a file inside that root. The tests drive the real golden
record rather than a fabricated one, because the reader's job is to open what the engine wrote.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

import lgbg.games  # noqa: F401 - registers Catan, which the golden record names
from lgbg.console.records import (
    InvalidLogIdError,
    InvalidRootError,
    LogStore,
    UnknownLogError,
    read_summary,
)

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "catan" / "full_game.god.jsonl"


def golden_copy(directory: Path, name: str = "full_game") -> Path:
    path = directory / f"{name}.god.jsonl"
    shutil.copyfile(GOLDEN, path)
    return path


@pytest.fixture
def root(tmp_path: Path) -> Path:
    golden_copy(tmp_path)
    return tmp_path


def test_discovers_records_directly_under_a_declared_root(root: Path) -> None:
    nested = root / "games"
    nested.mkdir()
    golden_copy(nested, "nested")

    entries = LogStore([root]).entries()

    assert [entry.id for entry in entries] == ["full_game"]
    assert entries[0].game == "catan"


def test_listing_reads_only_the_header(tmp_path: Path) -> None:
    """A truncated tail does not hide the record's existence, and is not parsed for a listing."""
    header = GOLDEN.read_text(encoding="utf-8").splitlines()[0]
    (tmp_path / "cut.god.jsonl").write_text(header + "\nnot json\n", encoding="utf-8")

    entries = LogStore([tmp_path]).entries()

    assert [entry.id for entry in entries] == ["cut"]
    summary = read_summary(entries[0])
    assert summary.verified is False
    assert summary.failure is not None


def test_summary_reconstructs_the_golden_record(root: Path) -> None:
    entry = LogStore([root]).resolve("full_game")

    summary = read_summary(entry)

    assert summary.game == "catan"
    assert summary.rules_version == "catan-rules-6"
    assert summary.actions == 743
    assert summary.rejections == 0
    assert summary.verified is True
    assert summary.completed is True
    assert summary.terminal_hash
    assert summary.failure is None


def test_a_tampered_record_is_a_finding_not_a_crash(root: Path) -> None:
    path = root / "full_game.god.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    changed = json.loads(lines[2])
    changed["state_hash"] = "0" * 16
    lines[2] = json.dumps(changed, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = read_summary(LogStore([root]).resolve("full_game"))

    assert summary.verified is False
    assert summary.actions is None
    assert summary.failure is not None
    assert summary.failure.seq is not None


def test_a_truncated_record_names_the_truncation(root: Path) -> None:
    path = root / "full_game.god.jsonl"
    text = path.read_text(encoding="utf-8")
    path.write_text(text[:-12], encoding="utf-8")

    summary = read_summary(LogStore([root]).resolve("full_game"))

    assert summary.verified is False
    assert summary.failure is not None
    assert summary.failure.kind == "truncated"


def test_an_unknown_game_is_a_finding(tmp_path: Path) -> None:
    lines = GOLDEN.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    header["game"] = "no-such-game"
    lines[0] = json.dumps(header, separators=(",", ":"))
    path = tmp_path / "unknown.god.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = read_summary(LogStore([tmp_path]).resolve("unknown"))

    assert summary.game == "no-such-game"
    assert summary.verified is False
    assert summary.failure is not None
    assert summary.failure.kind == "unknown_game"


def test_a_record_from_another_rules_version_is_refused(tmp_path: Path) -> None:
    lines = GOLDEN.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    header["rules_version"] = "catan-rules-5"
    lines[0] = json.dumps(header, separators=(",", ":"))
    path = tmp_path / "old.god.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = read_summary(LogStore([tmp_path]).resolve("old"))

    assert summary.verified is False
    assert summary.failure is not None
    assert summary.failure.kind == "incompatible"


@pytest.mark.parametrize("handle", ["../full_game", "games/full_game", "", ".hidden", "a\\b"])
def test_a_handle_is_a_name_not_a_path(root: Path, handle: str) -> None:
    with pytest.raises(InvalidLogIdError):
        LogStore([root]).resolve(handle)


def test_a_missing_handle_is_unknown(root: Path) -> None:
    with pytest.raises(UnknownLogError):
        LogStore([root]).resolve("absent")


def test_a_symlink_out_of_the_root_is_not_listed_or_opened(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = golden_copy(tmp_path_factory.mktemp("outside"), "escape")
    link = tmp_path / "escape.god.jsonl"
    try:
        os.symlink(outside, link)
    except OSError:
        pytest.skip("this platform does not allow symlinks")

    store = LogStore([tmp_path])

    assert store.entries() == []
    with pytest.raises(UnknownLogError):
        store.resolve("escape")


def test_a_root_must_be_a_directory(tmp_path: Path) -> None:
    with pytest.raises(InvalidRootError):
        LogStore([tmp_path / "absent"])
