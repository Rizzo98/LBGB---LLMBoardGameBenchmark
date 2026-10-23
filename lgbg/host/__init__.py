"""The host layer: the session facade and the HTTP/JSON API over it (PRD-v2 FR-1, FR-2).

One component owns mutable game state - the facade - and every surface above it is a transport.
The layer may import the engine and, in v2, third-party transport libraries; the engine may not
import it, so the arrow still points downward (ARCHITECTURE.md section 4).
"""

from lgbg.host.facade import (
    PUBLIC_OPERATIONS,
    SessionClosedError,
    SessionError,
    SessionExistsError,
    SessionFacade,
    SessionNotFoundError,
)
from lgbg.host.http import HOST_SCHEMA, HttpHost
from lgbg.host.registry import (
    InvalidSessionIdError,
    Registration,
    SessionRegistry,
)

__all__: list[str] = [
    "HOST_SCHEMA",
    "PUBLIC_OPERATIONS",
    "HttpHost",
    "InvalidSessionIdError",
    "Registration",
    "SessionClosedError",
    "SessionError",
    "SessionExistsError",
    "SessionFacade",
    "SessionNotFoundError",
    "SessionRegistry",
]
