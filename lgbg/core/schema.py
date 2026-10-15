"""A JSON Schema subset, enough to hold a plugin to its own declarations (ARCHITECTURE.md 7.3).

The plugin interface declares its action surface as *data* - a JSON Schema keyed by action type -
and this module is what makes that data binding rather than decorative: an action the schema does
not describe never reaches rule logic (PRD-v1 FR-18.1, FR-18.2).

The engine carries no third-party dependency, so this is a validator for the subset the schemas
actually use rather than a general implementation, and the subset is **declared**: a keyword in
this module's list is enforced, an annotation is ignored, and anything else raises. That last part
is the point. A validator that skipped the keywords it did not know would be an engine claiming to
enforce a contract it was quietly ignoring - the same failure the projection's allow-list exists to
prevent, in the other direction.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from lgbg.core.errors import BAD_PARAMS, UNKNOWN_ACTION, Rejection
from lgbg.core.types import Action, JsonSchema, JsonValue

SUPPORTED: Final[frozenset[str]] = frozenset(
    {
        "additionalProperties",
        "const",
        "enum",
        "items",
        "maxItems",
        "maximum",
        "minItems",
        "minimum",
        "oneOf",
        "properties",
        "required",
        "type",
    }
)
"""The keywords this validator enforces. Everything else is either an annotation or an error."""

ANNOTATIONS: Final[frozenset[str]] = frozenset(
    {"$comment", "$id", "$schema", "default", "description", "examples", "title"}
)
"""Keywords that describe a schema to a reader and change nothing about what it accepts."""


class SchemaError(Exception):
    """The declared schema uses a keyword this engine does not implement."""


def validate_action(schema: JsonSchema, action: Action) -> Rejection | None:
    """The refusal an action earns before any rule sees it, or None when it is well formed.

    An action type the game does not declare is UNKNOWN_ACTION, and a declared type whose
    parameters do not fit its schema is BAD_PARAMS. Both are refusals rather than exceptions: an
    action arriving from outside is a normal event, and the record keeps the refusal like any
    other (FR-18.2).
    """
    declared = schema.get(action.type)
    if declared is None:
        return Rejection(
            code=UNKNOWN_ACTION,
            message=f"{action.type!r} is not an action this game declares",
            details={"action_type": action.type, "known": sorted(schema)},
        )
    if not isinstance(declared, Mapping):
        raise SchemaError(f"the schema for {action.type!r} is not an object")
    found = violations(dict(action.params), declared, where=action.type)
    if not found:
        return None
    return Rejection(
        code=BAD_PARAMS,
        message=f"the parameters of {action.type!r} do not fit its declared schema",
        details={"action_type": action.type, "violations": found},
    )


def violations(value: JsonValue, schema: JsonSchema, *, where: str = "") -> list[str]:
    """Every way this value fails this schema, as sentences a rejection can carry.

    All of them rather than the first: a refusal is more useful the more of it a player can act
    on, and the walk is over the schema's own keywords, which is a handful. A violation says where
    it happened; with no path given, the value itself is the path, so no message starts with a
    bare colon.
    """
    where = where or "value"
    if not isinstance(schema, Mapping):
        raise SchemaError(f"{where}: a schema must be an object")
    _check_keywords(schema, where)
    found: list[str] = []
    allowed = _types_of(schema, where)
    if allowed is not None and not _is_type(value, allowed):
        found.append(f"{where}: expected {' or '.join(allowed)}, got {_kind(value)}")
    if "enum" in schema and value not in _as_sequence(schema["enum"], where, "enum"):
        found.append(f"{where}: {_short(value)} is not one of the declared values")
    if "const" in schema and value != schema["const"]:
        found.append(f"{where}: must be {_short(schema['const'])}")
    found.extend(_number_bounds(value, schema, where))
    found.extend(_length_bounds(value, schema, where))
    if isinstance(value, Mapping):
        found.extend(_object_violations(value, schema, where))
    elif isinstance(value, Sequence) and not isinstance(value, str):
        found.extend(_array_violations(value, schema, where))
    found.extend(_one_of(value, schema, where))
    return found


def _check_keywords(schema: JsonSchema, where: str) -> None:
    """Refuse a schema this engine cannot enforce, rather than enforcing part of it."""
    unknown = sorted(name for name in schema if name not in SUPPORTED and name not in ANNOTATIONS)
    if unknown:
        raise SchemaError(
            f"{where}: the engine does not implement {unknown}; declare it with the keywords in "
            f"{sorted(SUPPORTED)} or it would be a contract nothing enforces"
        )


def _types_of(schema: JsonSchema, where: str) -> list[str] | None:
    declared = schema.get("type")
    if declared is None:
        return None
    names = _as_sequence(declared, where, "type")
    for name in names:
        if not isinstance(name, str) or name not in _KINDS:
            raise SchemaError(f"{where}: {name!r} is not a JSON type")
    return [str(name) for name in names]


_KINDS: Final[frozenset[str]] = frozenset(
    {"array", "boolean", "integer", "null", "number", "object", "string"}
)


def _is_type(value: JsonValue, allowed: Sequence[str]) -> bool:
    return any(
        _kind(value) == name or (name == "number" and _kind(value) == "integer") for name in allowed
    )


def _kind(value: JsonValue) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, Sequence):
        return "array"
    return "null"


def _one_of(value: JsonValue, schema: JsonSchema, where: str) -> list[str]:
    """Alternative shapes of one action: exactly one branch must fit (a card's parameters).

    Exactly one, and not at least one: two branches that both fit would be a schema whose meaning
    depends on which one is read first, which is how a contract becomes ambiguous.
    """
    branches = schema.get("oneOf")
    if branches is None:
        return []
    candidates = _as_sequence(branches, where, "oneOf")
    failures = [
        violations(value, branch, where=where)
        for branch in candidates
        if isinstance(branch, Mapping)
    ]
    fitting = [found for found in failures if not found]
    if len(fitting) == 1:
        return []
    if not fitting:
        # Say what the nearest shape objected to: "neither fits" on its own is a refusal nobody
        # can act on, and the branch with the fewest complaints is the one worth quoting.
        nearest = min(failures, key=len)
        return [f"{where}: no declared shape fits; nearest says {nearest[0]}"]
    return [f"{where}: {len(fitting)} of the {len(candidates)} declared shapes fit"]


def _object_violations(value: Mapping[str, JsonValue], schema: JsonSchema, where: str) -> list[str]:
    found: list[str] = []
    properties = schema.get("properties")
    known = properties if isinstance(properties, Mapping) else {}
    required = schema.get("required")
    for name in _as_sequence(required, where, "required") if required is not None else []:
        if name not in value:
            found.append(f"{where}: {name!r} is required")
    for name, spec in known.items():
        if name in value and isinstance(spec, Mapping):
            found.extend(violations(value[name], spec, where=f"{where}.{name}"))
    extra = schema.get("additionalProperties", True)
    if extra is False:
        for name in sorted(value):
            if name not in known:
                found.append(f"{where}: {name!r} is not a parameter this action declares")
    elif isinstance(extra, Mapping):
        for name in sorted(value):
            if name not in known:
                found.extend(violations(value[name], extra, where=f"{where}.{name}"))
    return found


def _array_violations(value: Sequence[JsonValue], schema: JsonSchema, where: str) -> list[str]:
    items = schema.get("items")
    if not isinstance(items, Mapping):
        return []
    found: list[str] = []
    for index, item in enumerate(value):
        found.extend(violations(item, items, where=f"{where}[{index}]"))
    return found


def _number_bounds(value: JsonValue, schema: JsonSchema, where: str) -> list[str]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return []
    found: list[str] = []
    for keyword, holds in (("minimum", value.__ge__), ("maximum", value.__le__)):
        bound = schema.get(keyword)
        if isinstance(bound, (int, float)) and not holds(bound):
            found.append(f"{where}: {value} is out of range ({keyword} {bound})")
    return found


def _length_bounds(value: JsonValue, schema: JsonSchema, where: str) -> list[str]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        return []
    found: list[str] = []
    length = len(value)
    for keyword, holds in (("minItems", length.__ge__), ("maxItems", length.__le__)):
        bound = schema.get(keyword)
        if isinstance(bound, int) and not holds(bound):
            found.append(f"{where}: {length} items is out of range ({keyword} {bound})")
    return found


def _as_sequence(value: JsonValue, where: str, keyword: str) -> list[JsonValue]:
    """A keyword that may be written as one value or as a list of them, read as a list."""
    if isinstance(value, Sequence) and not isinstance(value, str):
        return list(value)
    return [value]


def _short(value: JsonValue) -> str:
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."
