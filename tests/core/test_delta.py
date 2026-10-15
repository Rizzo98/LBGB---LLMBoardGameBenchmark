"""The third rendering: what changed between two projections (FR-19.4; kanban card K-060).

Full and compact describe a position; a delta describes a step. It is asserted here to be a
function of the two positions and nothing else - the same pair renders to the same string, a pair
that is equal renders to a sentence rather than to nothing, and a field that appears or vanishes
counts as moved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from lgbg.core.delta import UNCHANGED, changed_fields, render_delta
from lgbg.core.types import Observation

CHECKOUT: Final[Path] = Path(__file__).resolve().parents[2]
BEFORE: Final[Observation] = {
    "turn": 0,
    "pieces": {"roads": [], "settlements": [[14, 0]]},
    "dice": None,
}
AFTER: Final[Observation] = {
    "turn": 0,
    "pieces": {"roads": [[17, 0]], "settlements": [[14, 0]]},
    "dice": [3, 4],
}


def test_only_the_fields_that_moved_are_reported() -> None:
    moved = changed_fields(BEFORE, AFTER)

    assert set(moved) == {"dice", "pieces"}
    assert moved["dice"] == (None, [3, 4])
    assert render_delta(BEFORE, AFTER).splitlines()[0] == "delta: 2 field(s)"


def test_a_step_that_changed_nothing_says_so() -> None:
    assert changed_fields(BEFORE, BEFORE) == {}
    assert render_delta(BEFORE, BEFORE) == UNCHANGED


def test_a_field_that_appears_or_vanishes_counts_as_moved() -> None:
    appeared = changed_fields({}, {"turn": 0})
    vanished = changed_fields({"turn": 0}, {})

    assert set(appeared) == {"turn"}
    assert set(vanished) == {"turn"}


def test_the_rendering_is_stable_and_ordered() -> None:
    first = render_delta(BEFORE, AFTER)
    second = render_delta(BEFORE, AFTER)
    names = [line.split(":")[0].strip() for line in first.splitlines()[1:]]

    assert first == second
    assert names == sorted(names), "one order, whatever the dictionaries did"


def test_the_delta_is_game_agnostic_by_construction() -> None:
    """It compares two projections and never looks inside one, so any game may use it."""
    source = (CHECKOUT / "lgbg" / "core" / "delta.py").read_text(encoding="utf-8")

    assert "lgbg.games" not in source
    assert set(changed_fields(BEFORE, AFTER)) <= set(BEFORE) | set(AFTER)
