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


def test_the_host_layer_never_imports_a_game() -> None:
    """PRD-v2 FR-1.2: a facade that imports a game is a facade that knows which games exist.

    Games reach the host through the registry, by name, the same way they reach any other caller -
    so adding a game stays a plugin decision rather than a change to the one component every
    surface sits on. Importing the package for its registration side effect is a *front-end*'s job,
    which is why the CLI does it and the host does not.
    """
    host_sources = sorted((PACKAGE_ROOT / "host").rglob("*.py"))

    assert host_sources, "control: a guard that scans nothing passes vacuously"

    offenders = sorted(
        f"{path.relative_to(REPO_ROOT)} imports {module}"
        for path in host_sources
        for module in _imported_modules(path)
        if module == "lgbg.games" or module.startswith("lgbg.games.")
    )

    assert offenders == [], "a game reaches the host as a registered name, never as an import"


def test_the_runner_layer_never_imports_a_game() -> None:
    """PRD-v2 FR-11.7: a game reaches the runner as a registered name, never as an import.

    The runner is the first layer that decides *which* games a run contains, which is exactly the
    place a convenient `from lgbg.games import catan` would appear. It must not: the seat mapping
    and the manifest are game-agnostic, and a game's facts reach them as declarations.
    """
    runner_sources = sorted((PACKAGE_ROOT / "runner").rglob("*.py"))

    assert runner_sources, "control: a guard that scans nothing passes vacuously"

    offenders = sorted(
        f"{path.relative_to(REPO_ROOT)} imports {module}"
        for path in runner_sources
        for module in _imported_modules(path)
        if module == "lgbg.games" or module.startswith("lgbg.games.")
    )

    assert offenders == [], "the runner must not name a game: " + ", ".join(offenders)


def test_no_source_in_the_runner_names_a_game() -> None:
    """The same rule, for the code a convenience edit would actually write: a literal game name."""
    runner_sources = sorted((PACKAGE_ROOT / "runner").rglob("*.py"))

    assert runner_sources, "control: the runner layer must have sources to scan"
    offenders = [
        f"{path.name}: {name}"
        for path in runner_sources
        for name in ("catan",)
        if name in path.read_text(encoding="utf-8").lower()
    ]

    assert offenders == [], "a game name in the runner is a game-specific path: " + str(offenders)
