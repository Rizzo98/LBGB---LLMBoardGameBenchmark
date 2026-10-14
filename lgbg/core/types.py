"""Core data types shared across the runtime (ARCHITECTURE.md section 5).

'JsonValue' is the boundary type of the whole system: actions arrive as JSON, state is
encoded to JSON for hashing, and records are JSON lines on disk. Anything that crosses a
boundary is a JsonValue and nothing else.

Arrays and objects are typed as 'Sequence' and 'Mapping' rather than 'list' and 'dict', so
that an ordinary literal - {"edge": 17}, [1, 2, 3] - is accepted without a cast. They are
read-only at every boundary: 'core.canonical.to_canonical_json' is what turns them into
concrete arrays and objects, and it rejects anything that is not JSON.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

type JsonValue = bool | int | str | Sequence[JsonValue] | Mapping[str, JsonValue] | None
