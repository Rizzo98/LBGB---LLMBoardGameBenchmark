"""The tooling guard for ambient randomness.

PRD-v1 FR-2.7 and NFR-7 require that the core and the games package never import
'random' outside 'lgbg/core/rng.py', and that this is enforced by a lint rule rather
than by convention. A rule enforced by convention is a paragraph; a rule enforced by a
tool is a build failure.

These tests exist so that the guard cannot be quietly removed, and so that it is
demonstrated to fire on a deliberate violation (card K-002).
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_DIR = REPO_ROOT / ".probe"

VIOLATION = """import random


def roll_die() -> int:
    return random.randint(1, 6)
"""


def _ruff_check(target: Path) -> subprocess.CompletedProcess[str]:
    """Run the linter over one target, exactly as the gate does."""
    return subprocess.run(  # noqa: S603 - fixed argv, no shell, test-only
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--output-format",
            "concise",
            str(target),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_probe(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(VIOLATION, encoding="utf-8")


def test_lint_rule_fires_on_a_deliberate_ambient_randomness_import() -> None:
    probe = PROBE_DIR / "ambient_randomness_probe.py"
    _write_probe(probe)
    try:
        result = _ruff_check(probe)
    finally:
        probe.unlink()
        if PROBE_DIR.is_dir() and not any(PROBE_DIR.iterdir()):
            PROBE_DIR.rmdir()

    assert result.returncode == 1, "a bare 'import random' must fail the lint gate"
    assert "TID251" in result.stdout, result.stdout


def test_exempt_paths_are_explicit_and_pinned() -> None:
    """Widening the exemption must be a deliberate, reviewed change."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)

    per_file_ignores = pyproject["tool"]["ruff"]["lint"]["per-file-ignores"]
    exempt = sorted(path for path, rules in per_file_ignores.items() if "TID251" in rules)

    assert exempt == ["lgbg/adapters/**", "lgbg/core/rng.py", "scripts/**", "tests/**"]


def test_exempt_path_is_actually_exempt() -> None:
    """Control for the probe test: the exemption must be real, not assumed."""
    probe = REPO_ROOT / "tests" / "tooling" / "_exempt_path_probe.py"
    _write_probe(probe)
    try:
        result = _ruff_check(probe)
    finally:
        probe.unlink()

    assert result.returncode == 0, result.stdout


def test_package_sources_contain_no_ambient_randomness() -> None:
    result = _ruff_check(REPO_ROOT / "lgbg")

    assert result.returncode == 0, result.stdout + result.stderr
