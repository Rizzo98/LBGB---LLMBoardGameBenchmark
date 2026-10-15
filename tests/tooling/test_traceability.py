"""Every requirement traced to a test, or recorded with the evidence that holds it up (SC-9).

Built rather than written down: a hand-written table is a second copy of the suite and would drift
from it. Not found in the tests means it must be in UNTRACED below.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

CHECKOUT: Final[Path] = Path(__file__).resolve().parents[2]
PRD: Final[Path] = CHECKOUT / "prd" / "PRD-v1.md"
TESTS: Final[Path] = CHECKOUT / "tests"

GATE: Final[str] = "scripts/gate.py, the CI configuration and the lockfile"
CORE: Final[str] = "tests/core - the module of that requirement's area"
CLI: Final[str] = "tests/cli and tests/golden"
FUZZ: Final[str] = "lgbg/core/fuzzing.py and tests/core/test_fuzzing.py (K-064)"

UNTRACED: Final[dict[str, str]] = {
    **dict.fromkeys(("FR-1.2", "FR-1.3", "FR-1.4"), GATE),
    **dict.fromkeys(("FR-2.2", "FR-2.5", "FR-3.3", "FR-3.4", "FR-3.5"), CORE),
    **dict.fromkeys(("FR-3.6", "FR-3.7", "FR-4.2", "FR-4.3", "FR-4.5"), CORE),
    **dict.fromkeys(("FR-5.2", "FR-6.3", "FR-6.4", "FR-7.5", "FR-7.7"), CORE),
    **dict.fromkeys(("FR-20.3", "FR-21.1", "FR-21.3"), CLI),
    # FR-20.6, FR-22.4 and FR-22.5 came off this list when their tests were written: the fuzz
    # command, the livelock verdict and the fixture-game run each name the requirement they hold.
    **dict.fromkeys(("FR-22.1", "FR-22.2", "FR-22.3", "FR-22.6"), FUZZ),
}


def matrix() -> dict[str, list[str]]:
    """Every functional requirement in the PRD, and the test files that name it."""
    prd = PRD.read_text(encoding="utf-8")
    ids = sorted(set(re.findall(r"\*\*(FR-\d+\.\d+)\*\*", prd)))
    sources = {
        path.relative_to(CHECKOUT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(TESTS.rglob("*.py"))
        # Not this file: it names every untraced identifier in its own list, and a matrix that
        # cited itself would find every requirement traced and would prove nothing at all.
        if path.name != Path(__file__).name
    }
    return {name: [file for file, text in sources.items() if name in text] for name in ids}


def test_every_requirement_is_traced_or_recorded_with_a_reason() -> None:
    """The matrix is complete, and every gap in it has somewhere to look next."""
    traced = matrix()
    untraced = sorted(name for name, files in traced.items() if not files)

    assert len(traced) > 100, "a matrix of a handful of requirements is not a matrix"
    assert set(untraced) == set(UNTRACED), (
        f"gaps: {sorted(set(untraced) - set(UNTRACED))}; "
        f"recorded but now traced: {sorted(set(UNTRACED) - set(untraced))}"
    )
    for name, evidence in UNTRACED.items():
        assert len(evidence) > 20, f"{name} needs a reason, not a shrug"


def test_most_requirements_are_traced_by_name() -> None:
    traced = matrix()
    named = [name for name, files in traced.items() if files]

    assert len(named) > 100, f"only {len(named)} of {len(traced)} are named by a test"
