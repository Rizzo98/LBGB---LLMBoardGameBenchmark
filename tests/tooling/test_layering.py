"""Architectural guards that are cheaper as tests than as paragraphs (PRD-v1 FR-1.1, FR-6.2).

These are not style checks. Each one asserts a structural rule from ARCHITECTURE.md that
would otherwise be enforced only by review, and each fails the build when broken.
"""

from __future__ import annotations

import ast
import re
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


def test_purpose_labels_are_named_constants_not_literals() -> None:
    """FR-2.3: a purpose label identifies a call site, so it must be a named constant.

    An inline literal cannot be found by a reader, renamed safely, or listed in a
    declaration, so a registry of purposes is only possible if they are named.
    """
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _python_sources()
        if re.search(r"purpose\s*=\s*[\"']", path.read_text(encoding="utf-8"))
    ]

    assert offenders == [], (
        "pass a module-level purpose constant instead of a literal: " + ", ".join(offenders)
    )


def _imported_modules(path: Path) -> set[str]:
    """Every module named by an import statement in one file.

    Parsed rather than pattern-matched: a docstring that mentions a forbidden import is
    not a forbidden import, and a guard that cannot tell the difference gets deleted.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def test_core_never_imports_games() -> None:
    """FR-6.2: the core never imports a game, so the arrow points strictly downward."""
    core_sources = sorted((PACKAGE_ROOT / "core").rglob("*.py"))

    assert len(core_sources) >= 3, "control: a guard that scans nothing passes vacuously"

    offenders = sorted(
        f"{path.relative_to(REPO_ROOT)} imports {module}"
        for path in core_sources
        for module in _imported_modules(path)
        if module == "lgbg.games" or module.startswith("lgbg.games.")
    )

    assert offenders == [], "game facts reach the core as declarations, never as imports"
