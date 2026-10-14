"""LBGB - an LLM board game benchmark.

The package is layered strictly downwards (ARCHITECTURE.md section 4): core is game-agnostic
and never imports games; games never import a transport.
"""

from typing import Final

__version__: Final[str] = "0.1.0"
"""Engine version, recorded in every game log header so a record names its producer."""

__all__: list[str] = ["__version__"]
