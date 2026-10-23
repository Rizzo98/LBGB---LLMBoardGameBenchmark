"""Serve the sandbox profile when the package itself is run (PRD-v2 D2)."""

from __future__ import annotations

from lgbg.adapters.mcp.sandbox import main

if __name__ == "__main__":
    raise SystemExit(main())
