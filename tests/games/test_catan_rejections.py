"""Every rejection the engine can raise is declared, and none is invented on the spot.

A rejection code is only useful as a metric if the set of them is closed and known: the illegal-
move rate is reported *by code*, and a code that only exists at one call site is a category with
one member that nobody can compare across games (FR-6.8). So the vocabulary is declared by the
plugin, the runtime's own codes are declared with it, and this test walks the source of the
engine to prove that nothing raises a code the declaration does not hold.

It is a source audit rather than a behavioural test on purpose. A behavioural test can only
provoke the refusals it thinks of, and the interesting failure is the code somebody raised in a
branch nobody thought about.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any, Final

from lgbg.core.errors import CORE_REJECTION_CODES, RejectionCode
from lgbg.core.game import get_game
from lgbg.games.catan.rejections import DECLARED_CODES, GAME_CODES

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PACKAGE: Final[Path] = REPO_ROOT / "lgbg"
CODE_MODULES: Final[tuple[str, ...]] = ("lgbg.core.errors", "lgbg.games.catan.rejections")
DEFINITIONS: Final[frozenset[Path]] = frozenset(
    REPO_ROOT / Path(module.replace(".", "/") + ".py") for module in CODE_MODULES
)


def _modules() -> list[Path]:
    """Every engine module that could raise a rejection: everything but the two vocabularies."""
    return sorted(path for path in PACKAGE.rglob("*.py") if path not in DEFINITIONS)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _raised(path: Path) -> list[str]:
    """The names this module passes as the code of a Rejection."""
    found: list[str] = []
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not isinstance(function, ast.Name) or function.id != "Rejection":
            continue
        for keyword in node.keywords:
            if keyword.arg != "code":
                continue
            assert isinstance(keyword.value, ast.Name), (
                f"{path.name}:{node.lineno} raises a code that is not a named constant; a code "
                "written at the call site is a category nobody declared"
            )
            found.append(keyword.value.id)
    return found


def _imported(path: Path) -> dict[str, str]:
    """Which code module each name in this file came from."""
    origins: dict[str, str] = {}
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.ImportFrom) and node.module in CODE_MODULES:
            for alias in node.names:
                origins[alias.asname or alias.name] = node.module
    return origins


def test_the_engine_raises_codes_and_this_scan_can_see_them() -> None:
    """The control: a scan that finds nothing would pass every assertion below."""
    raised = {path.name: _raised(path) for path in _modules()}

    assert raised["game.py"], "the plugin refuses refused actions with declared codes"
    assert "GAME_OVER" in raised["game.py"]
    assert sum(len(codes) for codes in raised.values()) >= 15


def test_every_code_the_engine_raises_is_declared_by_the_plugin() -> None:
    """FR-6.8: the declaration covers what the runtime raises, not only what the game does."""
    declared = {code.code for code in get_game("catan").rejection_codes()}

    for path in _modules():
        origins = _imported(path)
        for name in _raised(path):
            origin = origins.get(name)
            assert origin is not None, (
                f"{path.name} raises {name} without importing it from a declared vocabulary; "
                "a code from somewhere else is a code the metrics layer cannot enumerate"
            )
            code: Any = getattr(importlib.import_module(origin), name)
            assert isinstance(code, RejectionCode)
            assert code.code in declared, f"{path.name} raises {code.code}, which is undeclared"


def test_no_module_invents_a_rejection_code_of_its_own() -> None:
    """The vocabulary is two files; everywhere else a code is imported, never written.

    Importing the type for an annotation is fine - the plugin declares a list of them - but
    constructing one outside the vocabulary would be a code that exists at one call site.
    """
    for path in _modules():
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "RejectionCode", (
                    f"{path.name}:{node.lineno} builds a rejection code outside the declared "
                    "vocabulary"
                )


def test_the_declared_codes_are_unique_and_named_in_capitals() -> None:
    codes = [code.code for code in DECLARED_CODES]

    assert len(codes) == len(set(codes)), "a code declared twice is a code with two meanings"
    assert all(code.isupper() and " " not in code for code in codes)
    assert all(code.description for code in DECLARED_CODES), "a code is a code *and* its meaning"


def test_the_plugin_declares_the_runtime_codes_alongside_its_own() -> None:
    """The fuzz audit of K-063 compares what a run produced against this list, runtime included."""
    declared = list(DECLARED_CODES)

    assert set(GAME_CODES) < set(declared)
    assert set(CORE_REJECTION_CODES) < set(declared)
    assert list(get_game("catan").rejection_codes()) == declared
