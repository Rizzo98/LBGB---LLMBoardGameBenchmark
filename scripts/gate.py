"""The tooling gate: one command that decides whether the tree is acceptable.

Order matters and is cheapest-and-most-mechanical first, so that by the time a human or a
model reads the output, only decisions remain:

    ruff check      lint, including the architectural bans that are not style
    ruff format     layout, after the autofixes above have had their say
    mypy            types
    pytest          tests

This is the check-only form, safe to run in CI and before a commit. To apply the
autofixes instead of reporting them, run the ruff autofix step by hand first; see README.md.

Usage:
    uv run python scripts/gate.py
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence

STEPS: Sequence[tuple[str, Sequence[str]]] = (
    ("lint", (sys.executable, "-m", "ruff", "check", ".")),
    ("format", (sys.executable, "-m", "ruff", "format", "--check", ".")),
    ("types", (sys.executable, "-m", "mypy", ".")),
    ("tests", (sys.executable, "-m", "pytest")),
)


def main() -> int:
    for name, command in STEPS:
        print("==> " + name + ": " + " ".join(command[1:]), flush=True)
        result = subprocess.run(command, check=False)  # noqa: S603
        if result.returncode != 0:
            print("==> " + name + " FAILED (exit " + str(result.returncode) + ")", flush=True)
            return result.returncode
    print("==> gate passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
