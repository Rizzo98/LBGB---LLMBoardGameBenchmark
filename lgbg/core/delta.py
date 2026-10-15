"""What changed between two projections (PRD-v1 FR-19.4).

The third rendering, and the only one that needs two positions: full and compact describe a state,
and a delta describes the step between two of them, which is what a reader of a long game wants,
and what a prompt would show a model that has already been told the position.

It lives in the core because comparing two projections is game-agnostic by construction: the
fields are canonical JSON and the comparison never looks inside one. The CLI can therefore offer
the delta without learning what a board looks like, which is the rule the other renderings live
under as well.
"""

from __future__ import annotations

from typing import Final

from lgbg.core.canonical import to_canonical_json
from lgbg.core.types import JsonValue, Observation

UNCHANGED: Final[str] = "delta: no change"
"""What a step that changed nothing renders as: a sentence, not an empty string."""


def changed_fields(
    before: Observation, after: Observation
) -> dict[str, tuple[JsonValue, JsonValue]]:
    """Every field whose value moved, as before and after, keyed by field name."""
    moved: dict[str, tuple[JsonValue, JsonValue]] = {}
    for name in sorted(set(before) | set(after)):
        was = before.get(name)
        now = after.get(name)
        if to_canonical_json(was) != to_canonical_json(now):
            moved[name] = (was, now)
    return moved


def render_delta(before: Observation, after: Observation) -> str:
    """The step between two projections, one line per field that moved (FR-19.4).

    A field that appeared or vanished counts as moved, which is why the comparison is over the
    union of the two key sets rather than over one of them.
    """
    moved = changed_fields(before, after)
    if not moved:
        return UNCHANGED
    lines = [f"delta: {len(moved)} field(s)"]
    for name, (was, now) in moved.items():
        lines.append(f"  {name}: {to_canonical_json(was)} -> {to_canonical_json(now)}")
    return "\n".join(lines)
