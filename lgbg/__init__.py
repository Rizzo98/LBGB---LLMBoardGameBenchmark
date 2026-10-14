"""LBGB - an LLM board game benchmark.

The package is layered strictly downwards (ARCHITECTURE.md section 4): core is game-agnostic
and never imports games; games never import a transport.
"""

__all__: list[str] = []
