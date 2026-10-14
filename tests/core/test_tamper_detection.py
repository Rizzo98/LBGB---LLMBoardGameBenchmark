"""Tamper detection, one mutation site at a time (PRD-v1 SC-4).

A verification that only says "this record is bad" is not falsifiable: it cannot tell a
deliberate edit from a version skew from a bug in the verifier itself. So every mutation named
by SC-4 gets its own case, and each case asserts *where* verification failed and *why* - the
seq, and the kind of failure.

The record under test is a real one, produced by the engine, not a hand-written fixture: a
mutation suite over invented input proves only that the suite agrees with itself.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import pytest

from lgbg.core.log import GameLogReader
from lgbg.core.replay import ReplayError, ReplayFailure, verify
from tests.games.fixture_game import FixtureGame
from tests.support.records import record_fixture_game, rewrite_records

# records[0] is the header, records[1] is seq 0, records[2] is seq 1: mutations below target
# the second action, so a verifier that reported the wrong seq would be caught.
TARGET: Final[int] = 2
TARGET_SEQ: Final[int] = 1


def _mutate_action_type(records: list[dict[str, Any]]) -> None:
    # 'spend' is not affordable at seq 1, so the engine refuses an action the record calls
    # accepted: the mutation is caught by the outcome, deterministically.
    records[TARGET]["action"]["type"] = "spend"


def _mutate_draw_value(records: list[dict[str, Any]]) -> None:
    draw = records[TARGET]["rng"][0]
    draw["value"] = draw["value"] % 3 + 1  # a value the record cannot have held


def _mutate_draw_purpose(records: list[dict[str, Any]]) -> None:
    records[TARGET]["rng"][0]["purpose"] = "deck_deal"


def _mutate_draw_arguments(records: list[dict[str, Any]]) -> None:
    records[TARGET]["rng"][0]["args"]["hi"] = 6


def _mutate_event_payload(records: list[dict[str, Any]]) -> None:
    records[TARGET]["events"][0]["payload"]["amount"] = 9


def _mutate_state_hash_prev(records: list[dict[str, Any]]) -> None:
    records[TARGET]["state_hash_prev"] = "deadbeefdeadbeef"


def _mutate_state_hash(records: list[dict[str, Any]]) -> None:
    records[TARGET]["state_hash"] = "deadbeefdeadbeef"


def _mutate_terminal_hash(records: list[dict[str, Any]]) -> None:
    records[-1]["state_hash"] = "deadbeefdeadbeef"


def _mutate_header_initial_hash(records: list[dict[str, Any]]) -> None:
    records[0]["initial_state_hash"] = "deadbeefdeadbeef"


def _drop_a_recorded_draw(records: list[dict[str, Any]]) -> None:
    records[TARGET]["rng"] = []


def _add_a_recorded_draw(records: list[dict[str, Any]]) -> None:
    records[TARGET]["rng"].append(
        {"args": {"lo": 1, "hi": 3}, "kind": "randint", "purpose": "gamble_bonus", "value": 1}
    )


# The reported kind is the first divergence replay reaches, not the last: a changed draw
# value is reported as an event mismatch, because the recorded narrative disagrees before the
# state hash is ever compared.
MUTATIONS: Final[list[tuple[str, Callable[[list[dict[str, Any]]], None], int, ReplayFailure]]] = [
    ("the recorded action", _mutate_action_type, TARGET_SEQ, ReplayFailure.RESULT_MISMATCH),
    ("a draw value", _mutate_draw_value, TARGET_SEQ, ReplayFailure.EVENT_MISMATCH),
    ("a draw purpose", _mutate_draw_purpose, TARGET_SEQ, ReplayFailure.RNG_MISMATCH),
    ("a draw argument", _mutate_draw_arguments, TARGET_SEQ, ReplayFailure.RNG_MISMATCH),
    ("an event payload", _mutate_event_payload, TARGET_SEQ, ReplayFailure.EVENT_MISMATCH),
    ("state_hash_prev", _mutate_state_hash_prev, TARGET_SEQ, ReplayFailure.HASH_MISMATCH),
    ("state_hash", _mutate_state_hash, TARGET_SEQ, ReplayFailure.HASH_MISMATCH),
    ("the removed draw", _drop_a_recorded_draw, TARGET_SEQ, ReplayFailure.RNG_MISMATCH),
    ("an extra draw", _add_a_recorded_draw, TARGET_SEQ, ReplayFailure.RNG_EXHAUSTION),
    ("the terminal state hash", _mutate_terminal_hash, 6, ReplayFailure.HASH_MISMATCH),
    (
        "the header's initial hash",
        _mutate_header_initial_hash,
        0,
        ReplayFailure.INITIAL_STATE_MISMATCH,
    ),
]


@pytest.mark.parametrize(
    ("mutation", "seq", "kind"),
    [(mutation, seq, kind) for _name, mutation, seq, kind in MUTATIONS],
    ids=[name for name, _mutation, _seq, _kind in MUTATIONS],
)
def test_a_tampered_record_fails_verification_at_the_mutated_seq(
    tmp_path: Path,
    mutation: Callable[[list[dict[str, Any]]], None],
    seq: int,
    kind: ReplayFailure,
) -> None:
    path = record_fixture_game(tmp_path)
    rewrite_records(path, mutation)

    with pytest.raises(ReplayError) as raised:
        verify(GameLogReader(path).read(), FixtureGame())

    assert raised.value.kind is kind
    assert raised.value.seq == seq


def test_a_tampered_rejection_code_is_caught(tmp_path: Path) -> None:
    """A rejection does not move the state hash, so its code needs its own guard."""
    path = record_fixture_game(tmp_path, with_rejection=True)
    rewrite_records(path, lambda records: records[3]["result"].__setitem__("error", "BANK_EMPTY"))

    with pytest.raises(ReplayError) as raised:
        verify(GameLogReader(path).read(), FixtureGame())

    assert raised.value.kind is ReplayFailure.RESULT_MISMATCH
    assert raised.value.seq == 2


def test_an_untampered_record_verifies(tmp_path: Path) -> None:
    """The control: without it, a verifier that failed on everything would pass the suite."""
    path = record_fixture_game(tmp_path)

    report = verify(GameLogReader(path).read(), FixtureGame())

    assert report.actions == 6
    assert report.rejections == 0
