"""The dependency boundary, enforced rather than described (PRD-v2 FR-16.1 to FR-16.4, SC-11).

v1 shipped an engine with no third-party runtime dependency at all, and that is what makes a v1
record readable by a machine that has this repository and nothing else. v2 adds transports, a
provider client and a runner, so the boundary now has pressure on it for the first time: an
import that reaches back into the engine looks harmless and is not.

Two rules are checked here, and neither is a style preference:

- The engine - `lgbg/core` and `lgbg/games` - imports the standard library and this package and
  nothing else (FR-16.1).
- Every dependency the project declares is pinned to one exact version and justified in the
  header of `pyproject.toml` (FR-16.2). A version range would let two runs of the same
  configuration be driven through two client libraries, and nothing in the record would say so.

Both checks are written so that they cannot pass vacuously: each has a control that feeds it an
input it must reject, because a guard that cannot fail is a paragraph with a test's name on it.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PACKAGE_ROOT: Final[Path] = REPO_ROOT / "lgbg"
PYPROJECT: Final[Path] = REPO_ROOT / "pyproject.toml"

ENGINE_PACKAGES: Final[tuple[str, ...]] = ("core", "games")
"""The packages that must keep zero third-party runtime dependencies (FR-16.1, SC-11)."""

OWN_PACKAGE: Final[str] = "lgbg"
"""Imports inside the project are not third-party, whichever layer they name."""

EXACT_PIN: Final[re.Pattern[str]] = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]*==[A-Za-z0-9][A-Za-z0-9._+-]*"
)
"""One name and one exact version. No range, no extras, no marker: nothing to drift."""

NAME: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9._-]+")
"""The distribution a requirement string names, before any version or extra."""


# --- the engine's import surface -------------------------------------------------------------


def third_party_imports(source: str) -> set[str]:
    """Every top-level module this source imports that is neither stdlib nor this package.

    Parsed rather than pattern-matched for the reason the layering guard gives: a docstring that
    mentions a forbidden import is not a forbidden import.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        for name in names:
            root = name.split(".")[0]
            if root not in sys.stdlib_module_names and root != OWN_PACKAGE:
                found.add(root)
    return found


def engine_sources() -> list[Path]:
    """Every module of the two packages that must stay dependency-free."""
    return sorted(
        path for package in ENGINE_PACKAGES for path in (PACKAGE_ROOT / package).rglob("*.py")
    )


def engine_imports() -> dict[str, set[str]]:
    """The third-party modules each engine source imports. Offenders only."""
    offenders: dict[str, set[str]] = {}
    for path in engine_sources():
        modules = third_party_imports(path.read_text(encoding="utf-8"))
        if modules:
            offenders[path.relative_to(REPO_ROOT).as_posix()] = modules
    return offenders


def test_the_engine_packages_were_actually_found() -> None:
    """Control: a scan of nothing reports no imports and proves nothing."""
    assert len(engine_sources()) >= 20


def test_no_new_core_dependencies() -> None:
    """FR-16.1, SC-11: the engine imports the standard library and this package, period."""
    offenders = [
        f"{path} imports {sorted(modules)}" for path, modules in sorted(engine_imports().items())
    ]

    assert offenders == [], (
        "lgbg/core and lgbg/games must keep zero third-party runtime dependencies; "
        "the import belongs in lgbg/host, lgbg/adapters, lgbg/agents or lgbg/runner: "
        + "; ".join(offenders)
    )


def test_the_import_scan_rejects_a_third_party_import() -> None:
    """Control for the guard above: it must flag a package the engine may not use."""
    source = "import mcp\nfrom httpx import Client\nfrom lgbg.core.types import Action\n"

    assert third_party_imports(source) == {"httpx", "mcp"}


# --- the declared dependencies ---------------------------------------------------------------


def pyproject() -> dict[str, Any]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def runtime_requirements() -> list[str]:
    """What the project declares it needs at runtime, which is what a run is built from."""
    declared = pyproject()["project"]
    requirements = declared.get("dependencies", [])
    return [str(requirement) for requirement in requirements]


def dev_requirements() -> list[str]:
    """What the gate itself needs; pinned by the lockfile, justified in the same header."""
    groups = pyproject().get("dependency-groups", {})
    dev = groups.get("dev", [])
    return [str(requirement) for requirement in dev]


def header_comment() -> str:
    """The comment block pyproject.toml opens with: where the dependency policy is written."""
    lines: list[str] = []
    for line in PYPROJECT.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            lines.append(line)
            continue
        if line.strip():
            break
    return "\n".join(lines)


def unjustified(requirements: list[str], header: str) -> list[str]:
    """The requirements whose distribution is not named anywhere in the header comment."""
    written = header.lower()
    offenders: list[str] = []
    for requirement in requirements:
        match = NAME.match(requirement)
        if match is None or match.group(0).lower() not in written:
            offenders.append(requirement)
    return offenders


def unpinned(requirements: list[str]) -> list[str]:
    """The requirements that would let a client library change between two comparable runs."""
    return [requirement for requirement in requirements if not EXACT_PIN.fullmatch(requirement)]


def test_runtime_dependencies_are_declared_and_exactly_pinned() -> None:
    """FR-16.2: the v2 layers declare what they need, and each dependency has one version."""
    requirements = runtime_requirements()

    assert requirements, "the v2 layers need dependencies; declaring none is not a decision"
    assert unpinned(requirements) == [], (
        "pin each dependency to one exact version, so two runs cannot be driven through two "
        "client libraries without the record showing it"
    )


def test_every_declared_dependency_is_justified_in_the_header() -> None:
    """FR-16.2: a dependency that is not justified in the file is not a decision, it is a habit."""
    requirements = runtime_requirements() + dev_requirements()

    assert requirements, "the project declares no dependencies at all"
    assert unjustified(requirements, header_comment()) == [], (
        "name each dependency and say why it is here in the header comment of pyproject.toml"
    )


def test_the_justification_check_rejects_an_unjustified_dependency() -> None:
    """Control: the header check must fail for a dependency the header does not mention."""
    missing = unjustified(["redis==5.0.1", "mcp==1.30.0"], header="# mcp: the official SDK")

    assert missing == ["redis==5.0.1"]


def test_the_pin_check_rejects_a_version_range() -> None:
    """Control: a range is exactly what the pinning rule exists to refuse."""
    offenders = unpinned(["mcp>=1.30.0", "httpx~=0.28", "uvicorn==0.54.0"])

    assert offenders == ["mcp>=1.30.0", "httpx~=0.28"]
