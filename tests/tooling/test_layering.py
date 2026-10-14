"""Architectural guards that are cheaper as tests than as paragraphs (PRD-v1 FR-1.1, FR-6.2).

These are not style checks. Each one asserts a structural rule from ARCHITECTURE.md that
would otherwise be enforced only by review, and each fails the build when broken.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "lgbg"

# The single module permitted to call the stdlib serialiser directly. Everything else
# goes through core.canonical.to_canonical_json, so that hashing and replay cannot drift
# apart (ARCHITECTURE.md P8, FR-1.1).
SERIALISATION_OWNER = "canonical.py"


def _python_sources() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def test_package_sources_were_actually_found() -> None:
    """Control: a guard that scans nothing passes vacuously."""
    assert len(_python_sources()) >= 3


def test_only_the_canonical_module_serialises_json() -> None:
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _python_sources()
        if path.name != SERIALISATION_OWNER and "json.dumps(" in path.read_text(encoding="utf-8")
    ]

    assert offenders == [], "call to_canonical_json(..) from core.canonical instead: " + ", ".join(
        offenders
    )
