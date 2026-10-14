"""Core data types shared across the runtime (ARCHITECTURE.md section 5).

'JsonValue' is the boundary type of the whole system: actions arrive as JSON, state is
encoded to JSON for hashing, and records are JSON lines on disk. Anything that crosses a
boundary is a JsonValue and nothing else.
"""

from __future__ import annotations

type JsonValue = bool | int | str | list[JsonValue] | dict[str, JsonValue] | None
