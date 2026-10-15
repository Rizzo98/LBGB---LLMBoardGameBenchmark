"""The assist level is a rendering concern and nothing else (FR-17.1, FR-17.3; ARCHITECTURE 9).

Two things are checked here, and they are the two the benchmark's validity rests on. The tier
ladder has to be a ladder: the minimal view carries the code alone, the standard view adds the
sentence and the facts, and the full view adds the alternatives - so that a model at L0 cannot
recover the enumeration by making illegal moves and reading the answers. And the level has to be
readable in exactly one place: the engine's validation path must not be able to see it at all.

The second is asserted by a scan of the source rather than by a behavioural test, because the
failure it guards against is a future rule that quietly imports the enum to decide something.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from lgbg.core.assist import rejection_view, render_rejection
from lgbg.core.config import RejectionDetail
from lgbg.core.errors import Rejection, RejectionCode
from lgbg.core.game import Game
from lgbg.core.types import JsonValue

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PACKAGE: Final[Path] = REPO_ROOT / "lgbg"
MAY_READ_THE_LEVEL: Final[frozenset[str]] = frozenset({"config.py", "assist.py"})
"""Where in the core the level may appear: where it is configured, and where it renders."""

ADAPTERS: Final[Path] = PACKAGE / "adapters"
"""The front-ends, which parse the flag and hand the level to the renderer and nowhere else."""


def _may_read_the_level(path: Path) -> bool:
    """Whether this module is allowed to name the level.

    Two core modules and the front-ends. Never a rule, never the run, the log or the replay:
    those are the paths whose sameness across levels is the whole point of the level existing
    (FR-17.1, FR-17.2).
    """
    return path.name in MAY_READ_THE_LEVEL or ADAPTERS in path.parents


LEAKY: Final[Rejection] = Rejection(
    code=RejectionCode(code="NO_SUCH_REQUEST", description="the request is not open"),
    message="no open decision with request_id 'd3.0'",
    details={
        "request_id": "d3.0",
        "held": {"wood": 2, "ore": 1},
        "required": 3,
        "open": ["d3.0", "d3.1"],
        "legal_alternatives": [{"type": "end_turn"}, {"type": "roll_dice"}],
    },
)
"""A refusal carrying everything a lower tier must not repeat, alternatives included."""


def test_minimal_is_the_code_alone() -> None:
    """ARCHITECTURE 9.2: ok false and an error code, and nothing beside them."""
    view = rejection_view(LEAKY, detail=RejectionDetail.MINIMAL)

    assert view == {"ok": False, "error": "NO_SUCH_REQUEST"}


def test_standard_adds_the_sentence_and_the_facts_but_no_alternatives() -> None:
    """ARCHITECTURE 9.2: the error, what was required against what was held, no list."""
    view = rejection_view(LEAKY, detail=RejectionDetail.STANDARD)

    assert view["ok"] is False
    assert view["error"] == "NO_SUCH_REQUEST"
    assert view["message"] == LEAKY.message
    assert view["details"] == {
        "request_id": "d3.0",
        "held": {"wood": 2, "ore": 1},
        "required": 3,
    }


def test_full_carries_everything_the_rule_recorded() -> None:
    view = rejection_view(LEAKY, detail=RejectionDetail.FULL)

    assert _details(view) == dict(LEAKY.details)


def _details(view: dict[str, JsonValue]) -> Mapping[str, JsonValue]:
    """The details of a tiered view, asserted to be there, so the test can read into them."""
    details = view["details"]
    assert isinstance(details, Mapping)
    return details


def test_the_tiers_are_a_ladder_and_not_three_shapes() -> None:
    """Each tier is the one below it plus something, which is what makes them comparable."""
    minimal = rejection_view(LEAKY, detail=RejectionDetail.MINIMAL)
    standard = rejection_view(LEAKY, detail=RejectionDetail.STANDARD)
    full = rejection_view(LEAKY, detail=RejectionDetail.FULL)

    assert set(minimal) < set(standard) <= set(full)
    for key, value in minimal.items():
        assert standard[key] == value
        assert full[key] == value
    for key, value in standard.items():
        if key == "details":
            # The standard tier keeps the facts; the full tier keeps the facts and the rest.
            assert set(_details(standard)) <= set(_details(full))
            continue
        assert full[key] == value
    assert "legal_alternatives" in _details(full)


def test_a_minimal_refusal_cannot_leak_the_enumeration() -> None:
    """FR-17.3: no legal_alternatives and no parameter domain, by construction.

    The point of the tier is that a model cannot promote itself from L0 to L2 by making illegal
    moves and reading the answers, so what is asserted is the *text* it is handed: no list of
    alternatives, no request identifiers, and none of the action vocabulary a refusal beside it
    happens to carry.
    """
    text = render_rejection(LEAKY, detail=RejectionDetail.MINIMAL)

    assert text == "NO_SUCH_REQUEST"
    for leaked in ("legal_alternatives", "end_turn", "roll_dice", "d3.1", "request_id"):
        assert leaked not in text
    assert "details" not in rejection_view(LEAKY, detail=RejectionDetail.MINIMAL)


def test_a_standard_refusal_keeps_the_facts_it_is_allowed_to_keep() -> None:
    text = render_rejection(LEAKY, detail=RejectionDetail.STANDARD)

    assert text.startswith("NO_SUCH_REQUEST: ")
    assert "required" in text
    assert "held" in text
    assert "legal_alternatives" not in text
    assert "end_turn" not in text


def test_the_full_refusal_is_the_one_with_the_alternatives_in_it() -> None:
    text = render_rejection(LEAKY, detail=RejectionDetail.FULL)

    assert "legal_alternatives" in text
    assert "end_turn" in text


def test_apply_has_no_way_to_see_the_level() -> None:
    """FR-17.1: the protocol member takes a state, an action and a source, and nothing else."""
    parameters = list(inspect.signature(Game.apply).parameters)

    assert parameters == ["self", "state", "action", "rng"]


def test_no_rule_and_no_recording_path_can_name_the_level() -> None:
    """FR-17.1, structurally: a rule that imported the enum could decide something by it.

    A behavioural test can only show that the rules it thought of ignore the level; this is the
    scan that catches the rule nobody thought about, the same way the layering guard catches an
    import of a game from the core.
    """
    offenders: list[str] = []

    for path in sorted(PACKAGE.rglob("*.py")):
        if _may_read_the_level(path):
            continue
        text = path.read_text(encoding="utf-8")
        for name in ("AssistLevel", "RejectionDetail"):
            if name in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {name}")

    assert offenders == [], f"the level escapes into {offenders}"


def test_the_scan_is_not_vacuous() -> None:
    """The control: a scan that skipped everything would pass the test above."""
    naming = [
        path for path in PACKAGE.rglob("*.py") if "AssistLevel" in path.read_text(encoding="utf-8")
    ]

    assert {path.name for path in naming} >= set(MAY_READ_THE_LEVEL)
    assert any(ADAPTERS in path.parents for path in naming), "the flag is parsed somewhere"
    assert len(list(PACKAGE.rglob("*.py"))) > 20, "a scan of an empty tree passes anything"
