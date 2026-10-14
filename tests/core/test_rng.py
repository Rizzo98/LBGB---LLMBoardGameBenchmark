"""The randomness seam (PRD-v1 FR-2.1 to FR-2.7, ARCHITECTURE.md section 5.4).

Every random draw is recorded with a semantic label, so replay validates *what* was drawn
and *why*, not merely that the stream did not run out. A positional stream silently
desynchronises the moment two call sites are reordered, and produces a replay that is
different but plausible - the worst failure mode a benchmark can have.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

import pytest

from lgbg.core.canonical import CanonicalJsonError
from lgbg.core.rng import (
    KIND_CHOICE,
    KIND_RANDINT,
    KIND_SHUFFLE,
    NullRandomSource,
    RandomSource,
    ReplayRandomSource,
    RngDraw,
    RngError,
    RngMismatchError,
    SeededRandomSource,
    UnconsumedDrawsError,
)

# Purpose labels are module constants, never inline strings (FR-2.3). The guard in
# tests/tooling/test_layering.py fails the build on a literal passed as a purpose.
DICE_ROLL: Final[str] = "dice_roll"
DECK_DEAL: Final[str] = "deck_deal"
RANDOM_SELECTION: Final[str] = "random_selection"
BOARD_LAYOUT: Final[str] = "board_layout"

ACTION: Final[str] = "#47"


def test_same_seed_produces_the_same_values() -> None:
    first = SeededRandomSource(123456789)
    second = SeededRandomSource(123456789)

    assert [first.randint(1, 6, purpose=DICE_ROLL) for _ in range(6)] == [
        second.randint(1, 6, purpose=DICE_ROLL) for _ in range(6)
    ]


def test_seeded_records_every_draw_in_order() -> None:
    source = SeededRandomSource(1)

    rolled = source.randint(1, 6, purpose=DICE_ROLL)
    picked = source.choice(["a", "b", "c"], purpose=RANDOM_SELECTION)

    assert source.draws() == [
        RngDraw(purpose=DICE_ROLL, kind=KIND_RANDINT, args={"lo": 1, "hi": 6}, value=rolled),
        RngDraw(purpose=RANDOM_SELECTION, kind=KIND_CHOICE, args={"n": 3}, value=picked),
    ]


def test_seeded_records_a_shuffle_as_a_permutation() -> None:
    source = SeededRandomSource(7)

    shuffled = source.shuffle([1, 2, 3, 4, 5], purpose=DECK_DEAL)

    assert sorted(shuffled) == [1, 2, 3, 4, 5]
    assert source.draws() == [
        RngDraw(purpose=DECK_DEAL, kind=KIND_SHUFFLE, args={"n": 5}, value=shuffled)
    ]


def test_shuffle_does_not_mutate_the_input() -> None:
    items = [1, 2, 3, 4, 5]

    SeededRandomSource(7).shuffle(items, purpose=DECK_DEAL)

    assert items == [1, 2, 3, 4, 5]


def test_choice_over_an_empty_sequence_is_a_loud_error() -> None:
    source = SeededRandomSource(3)

    with pytest.raises(RngError, match="empty"):
        source.choice([], purpose=RANDOM_SELECTION)


def test_choice_returns_a_member_of_the_input() -> None:
    source = SeededRandomSource(99)

    assert source.choice(["a", "b", "c"], purpose=RANDOM_SELECTION) in {"a", "b", "c"}


def test_draws_must_be_json_serialisable() -> None:
    source = SeededRandomSource(3)

    with pytest.raises(CanonicalJsonError):
        source.choice([{1, 2}], purpose=RANDOM_SELECTION)


@pytest.mark.parametrize(
    "draw",
    [
        pytest.param(lambda source: source.randint(1, 6, purpose=DICE_ROLL), id="randint"),
        pytest.param(lambda source: source.choice(["a"], purpose=RANDOM_SELECTION), id="choice"),
        pytest.param(lambda source: source.shuffle(["a"], purpose=BOARD_LAYOUT), id="shuffle"),
    ],
)
def test_null_source_raises_on_any_draw(draw: Callable[[RandomSource], object]) -> None:
    with pytest.raises(RngError, match="deterministic"):
        draw(NullRandomSource())


def test_both_real_sources_satisfy_the_protocol() -> None:
    """Checked by mypy: a source that drifts from the protocol breaks the gate."""
    sources: list[RandomSource] = [
        SeededRandomSource(1),
        ReplayRandomSource([], action=ACTION),
        NullRandomSource(),
    ]

    assert len(sources) == 3


def test_replay_returns_the_recorded_values_in_order() -> None:
    recorded = [
        RngDraw(purpose=DICE_ROLL, kind=KIND_RANDINT, args={"lo": 1, "hi": 6}, value=5),
        RngDraw(purpose=DECK_DEAL, kind=KIND_SHUFFLE, args={"n": 3}, value=[3, 1, 2]),
    ]
    source = ReplayRandomSource(recorded, action=ACTION)

    assert source.randint(1, 6, purpose=DICE_ROLL) == 5
    assert source.shuffle([1, 2, 3], purpose=DECK_DEAL) == [3, 1, 2]
    source.assert_exhausted()


def test_replay_reports_a_reordered_draw_with_action_index_and_purposes() -> None:
    recorded = [
        RngDraw(purpose=DICE_ROLL, kind=KIND_RANDINT, args={"lo": 1, "hi": 6}, value=5),
        RngDraw(purpose=DECK_DEAL, kind=KIND_CHOICE, args={"n": 2}, value=1),
    ]
    source = ReplayRandomSource(recorded, action=ACTION)

    with pytest.raises(RngMismatchError) as raised:
        source.choice(["a", "b"], purpose=RANDOM_SELECTION)

    message = str(raised.value)
    assert ACTION in message
    assert "#0" in message
    assert DICE_ROLL in message
    assert RANDOM_SELECTION in message


def test_replay_reports_a_kind_mismatch() -> None:
    recorded = [RngDraw(purpose=DECK_DEAL, kind=KIND_CHOICE, args={"n": 2}, value=1)]
    source = ReplayRandomSource(recorded, action=ACTION)

    with pytest.raises(RngMismatchError, match="kind"):
        source.randint(1, 6, purpose=DECK_DEAL)


def test_replay_reports_an_argument_mismatch() -> None:
    recorded = [RngDraw(purpose=DICE_ROLL, kind=KIND_RANDINT, args={"lo": 1, "hi": 6}, value=5)]
    source = ReplayRandomSource(recorded, action=ACTION)

    with pytest.raises(RngMismatchError, match="args"):
        source.randint(1, 12, purpose=DICE_ROLL)


def test_replay_reports_a_draw_beyond_the_record() -> None:
    source = ReplayRandomSource([], action=ACTION)

    with pytest.raises(RngMismatchError, match="no recorded draw"):
        source.randint(1, 6, purpose=DICE_ROLL)


def test_replay_reports_unconsumed_recorded_draws() -> None:
    recorded = [
        RngDraw(purpose=DICE_ROLL, kind=KIND_RANDINT, args={"lo": 1, "hi": 6}, value=5),
        RngDraw(purpose=DECK_DEAL, kind=KIND_CHOICE, args={"n": 2}, value=1),
    ]
    source = ReplayRandomSource(recorded, action=ACTION)
    source.randint(1, 6, purpose=DICE_ROLL)

    with pytest.raises(UnconsumedDrawsError) as raised:
        source.assert_exhausted()

    assert ACTION in str(raised.value)
    assert DECK_DEAL in str(raised.value)
