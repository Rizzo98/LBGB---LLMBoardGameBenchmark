"""The v2 artefact shapes, declared once, beside v1's record vocabulary (PRD-v2 FR-10, FR-11.10).

v1's god log is frozen and stays frozen: it holds the *game*, and nothing about a model may enter
it (FR-10.2). Everything a model adds - what it was asked, what it answered, what it cost, why it
failed - goes in two other artefacts, and this module is where their shapes are declared:

- **the run manifest** (`run.json`): the run's configuration, its seats and their agents, the
  experiment design and its derivation, every policy value, every prompt hash, the provider
  identities and the price table with the moment it was read (FR-10.1, FR-5.7, FR-5.9, FR-11.3,
  FR-11.4).
- **the decision record** (a line of `.meta.jsonl`): one model request within one decision turn,
  with its attempt index, the redo budget it was spent against, the rejection that prompted it, the
  route
  the gateway chose, whether native tool calling was used, its usage, cost, latency and failure kind
  (FR-10.3, FR-5.8).

Both are declared as JSON Schema *data* and checked by `core.schema`, the same validator that holds
a plugin to its own declared action surface. That is deliberate: a shape written as prose is a shape
nobody enforces, and a shape enforced by a second, general-purpose validator would be a dependency
this project does not need (FR-16.4).

Three decisions are worth stating, because they are the ones later slices would otherwise make again
differently:

- **The shapes are closed.** `additionalProperties` is false everywhere it can be, so a field a
  later slice needs is *added to the declared shape* and reviewed, rather than arriving in a record
  that no reader was told about.
- **There are no floats.** Every artefact here is written through `core.canonical`, the one
  serialiser, which refuses floats because float formatting is not stable across platforms and
  versions (ARCHITECTURE.md section 6). So money is integer micro-dollars, sampling parameters are
  integer thousandths, and latency is integer milliseconds. Nothing is lost by that: the exact
  payload the provider was sent is recorded verbatim in its own record (FR-5.4).
- **The transcript is provider-neutral; the payload is provider-exact.** A decision record's
  `messages` hold roles, content and tool calls in the shape every OpenAI-compatible gateway uses,
  so one reader serves every model. The exact bytes are the adapter's business and are recorded as
  bytes (FR-5.4, FR-5.5).

What is *not* here yet, on purpose: the declared set of failure kinds (FR-7.10, card K-025) and the
penny-level accounting of `results.json` (FR-10.6, card K-032). Both are fields on these shapes when
they arrive, which is the whole point of freezing the shapes first.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Final

from lgbg.core.config import declared_assist_levels, declared_rejection_details
from lgbg.core.log import KIND_ACTION, KIND_HEADER, KIND_PHASE, KIND_TERMINAL
from lgbg.core.schema import violations
from lgbg.core.types import JsonSchema, JsonValue

MANIFEST_SCHEMA_NAME: Final[str] = "lgbg.run.v1"
"""The run directory's format version, recorded in the manifest and understood by its reader."""

SIDECAR_DECISION: Final[str] = "decision"
"""The sidecar's record type for one model request. The runtime owns the name, as it owns all."""

CONTEXT_STRATEGIES: Final[tuple[str, ...]] = ("bounded_window", "delta_with_refresh", "full")
"""The context policies a run may declare (FR-8.2). The default is delta with refresh (FR-8.1)."""

ON_EXHAUSTED: Final[tuple[str, ...]] = ("abandon_game",)
"""What a decision turn does when its redo budget runs out (FR-7.5, Q3). One value, and declared."""

FAILURE_KINDS: Final[tuple[str, ...]] = (
    "malformed_arguments",
    "no_action",
    "redo_exhausted",
    "runaway",
    "timeout",
)
"""The declared ways a decision can fail (FR-7.10).

Declared like v1's rejection codes so results can count them without parsing text. Each names a
different budget and a different finding: malformed arguments are charged to the redo budget, a
runaway and prose-only are not, and a timeout abandons by the same rule as exhaustion."""

PRICE_UNITS: Final[tuple[str, ...]] = ("micro_usd_per_million_tokens",)
"""The unit a price table is expressed in. Integer units, for the reason the docstring gives."""

PROMPT_LAYERS: Final[tuple[str, ...]] = ("game", "policy", "redo", "system")
"""The four separable prompt artefacts of FR-9.1, each hashed into the manifest (FR-9.3)."""

# --- the leaf shapes every artefact is built from -----------------------------------------------

_TEXT: Final[JsonSchema] = {"type": "string"}
_ANY_TEXT: Final[JsonSchema] = {"type": ["string", "null"]}
_INT: Final[JsonSchema] = {"type": "integer"}
_ANY_INT: Final[JsonSchema] = {"type": ["integer", "null"]}
_COUNT: Final[JsonSchema] = {"type": "integer", "minimum": 0}
_POSITIVE: Final[JsonSchema] = {"type": "integer", "minimum": 1}
_MILLI: Final[JsonSchema] = {"type": "integer", "minimum": 0, "maximum": 1000}
"""A sampling parameter in thousandths: a record holds integers, and 0.5 is 500 here."""

_DIGEST: Final[JsonSchema] = {
    "type": "string",
    "$comment": "lowercase hex sha256 of the artefact's bytes, as core.prompts.digest writes",
}


def _values(allowed: tuple[str, ...]) -> JsonSchema:
    """A declared set of words: what makes a policy value enumerable rather than free text."""
    return {"enum": list(allowed)}


def _nullable(shape: JsonSchema) -> JsonSchema:
    """A shape that may be absent, recorded as null rather than left out.

    Null and "missing" are different findings - a null usage means the provider omitted it
    (FR-5.6), and a missing one would mean this contract was not followed - so the field stays
    required and its absence is expressed.

    A type union rather than 'oneOf': the same acceptance, and a report that names the field that
    failed instead of saying that neither alternative fitted.
    """
    declared = shape.get("type")
    if isinstance(declared, str):
        declared_types: list[JsonValue] = [declared]
    elif isinstance(declared, Sequence):
        declared_types = list(declared)
    else:
        declared_types = []
    widened: dict[str, JsonValue] = {**shape, "type": [*declared_types, "null"]}
    if "enum" in shape:
        # A declared set that can be absent needs null in the set as well as in the type; a
        # validator that checks enum before type would otherwise refuse the legitimate absence.
        allowed = shape["enum"]
        if isinstance(allowed, Sequence) and not isinstance(allowed, str):
            widened["enum"] = [*allowed, None]
        if not declared_types:
            # An enum-only schema constrains by its set, not by a type: listing "null" alone
            # would refuse every declared value.
            widened.pop("type", None)
    return widened


_FALSE: Final[JsonSchema] = {"type": "boolean"}

_ACTION: Final[JsonSchema] = {
    "type": "object",
    "required": ["type", "params"],
    "properties": {"type": _TEXT, "params": {"type": "object"}},
    "additionalProperties": False,
}

_TOOL_CALL: Final[JsonSchema] = {
    "type": "object",
    "required": ["id", "name", "arguments"],
    "properties": {
        "id": _TEXT,
        "name": _TEXT,
        "arguments": {
            "type": ["object", "string"],
            "$comment": "the arguments as parsed, or the raw text when they did not parse (FR-7.6)",
        },
    },
    "additionalProperties": False,
}

_MESSAGE: Final[JsonSchema] = {
    "type": "object",
    "required": ["role", "content"],
    "properties": {
        "role": _values(("assistant", "system", "tool", "user")),
        "content": _ANY_TEXT,
        "tool_calls": _nullable({"type": "array", "items": _TOOL_CALL}),
        "tool_call_id": _ANY_TEXT,
    },
    "additionalProperties": False,
}

_RESPONSE: Final[JsonSchema] = {
    "type": "object",
    "required": ["text", "tool_calls"],
    "properties": {
        "text": _ANY_TEXT,
        "tool_calls": _nullable({"type": "array", "items": _TOOL_CALL}),
    },
    "additionalProperties": False,
}

_USAGE: Final[JsonSchema] = _nullable(
    {
        "type": "object",
        "required": ["prompt_tokens", "completion_tokens", "total_tokens"],
        "properties": {
            "prompt_tokens": _COUNT,
            "completion_tokens": _COUNT,
            "total_tokens": _COUNT,
        },
        "additionalProperties": False,
        "$comment": "null means the provider omitted usage, which is recorded as unknown and never "
        "as zero (FR-5.6, FR-13.4)",
    }
)

_WIRE: Final[JsonSchema] = _nullable(
    {
        "type": "object",
        "required": [
            "request",
            "request_headers",
            "response",
            "response_headers",
            "status_code",
        ],
        "properties": {
            "request": _ANY_TEXT,
            "response": _ANY_TEXT,
            "status_code": _ANY_INT,
            "request_headers": {"type": "object", "additionalProperties": _TEXT},
            "response_headers": {"type": "object", "additionalProperties": _TEXT},
        },
        "additionalProperties": False,
        "$comment": "the exact bodies sent and received, as text; credentials already redacted "
        "(FR-5.4, FR-10.5, NFR-7)",
    }
)

_REJECTION: Final[JsonSchema] = _nullable(
    {
        "type": "object",
        "required": ["code", "detail", "attempt"],
        "properties": {
            "code": _TEXT,
            "detail": _values(declared_rejection_details()),
            "attempt": _POSITIVE,
        },
        "additionalProperties": False,
    }
)

_OUTCOME: Final[JsonSchema] = {
    "oneOf": [
        {
            "type": "object",
            "required": ["kind", "action"],
            "properties": {"kind": {"const": "action"}, "action": _ACTION},
            "additionalProperties": False,
        },
        {
            "type": "object",
            "required": ["kind"],
            "properties": {"kind": _values(("failure", "read", "rejection"))},
            "additionalProperties": False,
        },
    ]
}

# --- run.json -----------------------------------------------------------------------------------

_GAME: Final[JsonSchema] = {
    "type": "object",
    "required": ["name", "rules_version", "schema_version"],
    "properties": {"name": _TEXT, "rules_version": _TEXT, "schema_version": _TEXT},
    "additionalProperties": False,
}

_CONFIG: Final[JsonSchema] = {
    "type": "object",
    "required": ["assist", "interaction_protocol", "players", "rejection_detail", "seed"],
    "properties": {
        "seed": _INT,
        "players": {"type": "integer", "minimum": 2},
        "assist": _values(declared_assist_levels()),
        "rejection_detail": _values(declared_rejection_details()),
        "interaction_protocol": _TEXT,
    },
    "additionalProperties": True,
    "$comment": "the game's own options are declared by the plugin and carried opaquely (P11); the "
    "prompt hashes live in 'prompts' and nowhere else, since two copies of a hash is one copy that "
    "can be wrong",
}

_SAMPLING: Final[JsonSchema] = _nullable(
    {
        "type": "object",
        "required": ["temperature_milli", "top_p_milli", "seed"],
        "properties": {
            "temperature_milli": _MILLI,
            "top_p_milli": _MILLI,
            "seed": _ANY_INT,
        },
        "additionalProperties": False,
    }
)

_SEAT: Final[JsonSchema] = {
    "type": "object",
    "required": ["agent", "model", "player", "provider", "sampling", "seat"],
    "properties": {
        "seat": _COUNT,
        "agent": _values(("llm", "reference", "scripted")),
        "player": _ANY_TEXT,
        "model": _ANY_TEXT,
        "provider": _ANY_TEXT,
        "sampling": _SAMPLING,
    },
    "additionalProperties": False,
}

_DESIGN: Final[JsonSchema] = {
    "type": "object",
    "required": [
        "configuration_scope",
        "derivation",
        "initial_configuration",
        "replicate",
        "replicates",
        "rotation",
        "seating",
        "uncontrolled",
    ],
    "properties": {
        "seating": _values(("fixed", "random", "rotated")),
        "initial_configuration": _TEXT,
        "configuration_scope": _values(("per_experiment", "per_game")),
        "replicates": _POSITIVE,
        "replicate": _COUNT,
        "rotation": _COUNT,
        "uncontrolled": {"type": "array", "items": _TEXT},
        "derivation": {
            "type": "object",
            "required": ["games", "replicates", "rule", "seatings"],
            "properties": {
                "rule": _TEXT,
                "replicates": _COUNT,
                "seatings": _POSITIVE,
                "games": _COUNT,
            },
            "additionalProperties": False,
            "$comment": "the derivation, not only the product, so a game count can be traced to a "
            "decision rather than guessed at (FR-11.4)",
        },
    },
    "additionalProperties": False,
    "$comment": "replicate and rotation are this game's point in the design: every game can be "
    "attributed to a replicate and a seating, which is what makes two results comparable "
    "(FR-11.10)",
}

_POLICIES: Final[JsonSchema] = {
    "type": "object",
    "required": [
        "budget_micro_usd",
        "context",
        "context_refresh_every",
        "context_window",
        "decision_timeout_s",
        "game_timeout_s",
        "on_exhausted",
        "redo_budget",
        "step_budget",
    ],
    "properties": {
        "context": _values(CONTEXT_STRATEGIES),
        "context_refresh_every": _POSITIVE,
        "context_window": _POSITIVE,
        "redo_budget": _COUNT,
        "on_exhausted": _values(ON_EXHAUSTED),
        "step_budget": _POSITIVE,
        "decision_timeout_s": _POSITIVE,
        "game_timeout_s": _POSITIVE,
        "budget_micro_usd": _ANY_INT,
    },
    "additionalProperties": False,
    "$comment": "every policy is a declared value, recorded identically for every model, so no "
    "policy can vary per model without the manifest showing it (FR-6.3, FR-7.3, FR-8.3)",
}

_PROVIDER: Final[JsonSchema] = {
    "type": "object",
    "required": ["id", "version"],
    "properties": {"id": _TEXT, "version": _TEXT},
    "additionalProperties": False,
}

_PRICE_TABLE: Final[JsonSchema] = {
    "type": "object",
    "required": ["models", "read_at", "source", "unit"],
    "properties": {
        "source": _TEXT,
        "read_at": _TEXT,
        "unit": _values(PRICE_UNITS),
        "models": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["completion", "model", "prompt"],
                "properties": {"model": _TEXT, "prompt": _COUNT, "completion": _COUNT},
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}

MANIFEST_SCHEMA: Final[JsonSchema] = {
    "type": "object",
    "required": [
        "config",
        "design",
        "engine_version",
        "game",
        "policies",
        "price_table",
        "prompts",
        "providers",
        "run_id",
        "schema",
        "seats",
    ],
    "properties": {
        "schema": {"const": MANIFEST_SCHEMA_NAME},
        "run_id": _TEXT,
        "engine_version": _TEXT,
        "game": _GAME,
        "config": _CONFIG,
        "seats": {"type": "array", "items": _SEAT, "minItems": 2},
        "design": _DESIGN,
        "policies": _POLICIES,
        "prompts": {
            "type": "object",
            "required": list(PROMPT_LAYERS),
            "properties": dict.fromkeys(PROMPT_LAYERS, _DIGEST),
            "additionalProperties": False,
        },
        "providers": {
            "type": "array",
            "items": _PROVIDER,
            "$comment": "empty for a table of reference players and scripts: a run with no model "
            "seat used no provider, and an invented identity would be a lie (FR-11.1, FR-12.3)",
        },
        "price_table": _PRICE_TABLE,
    },
    "additionalProperties": False,
}

# --- one decision record, a line of .meta.jsonl -------------------------------------------------

DECISION_SCHEMA: Final[JsonSchema] = {
    "type": "object",
    "required": [
        "at",
        "attempt",
        "cost_micro_usd",
        "failure",
        "game_id",
        "host",
        "latency_ms",
        "messages",
        "model",
        "native_tools",
        "outcome",
        "pid",
        "player",
        "provider",
        "redo_budget",
        "rejection",
        "request_id",
        "response",
        "route",
        "seat",
        "wire",
        "seq",
        "t",
        "usage",
    ],
    "properties": {
        "t": {"const": SIDECAR_DECISION},
        "at": _TEXT,
        "host": _TEXT,
        "pid": _COUNT,
        "game_id": _TEXT,
        "seq": _ANY_INT,
        "request_id": _TEXT,
        "player": _COUNT,
        "seat": _COUNT,
        "model": _TEXT,
        "provider": _TEXT,
        "route": _ANY_TEXT,
        "native_tools": _FALSE,
        "attempt": _POSITIVE,
        "redo_budget": _COUNT,
        "messages": {"type": "array", "items": _MESSAGE, "minItems": 1},
        "response": _RESPONSE,
        "wire": _WIRE,
        "outcome": _OUTCOME,
        "rejection": _REJECTION,
        "usage": _USAGE,
        "cost_micro_usd": _ANY_INT,
        "latency_ms": _COUNT,
        "failure": _nullable(_values(FAILURE_KINDS)),
    },
    "additionalProperties": False,
    "$comment": "seq is the god-log seq of the attempt this record accounts for, and null when the "
    "attempt produced no action at all (FR-7.7); request_id is shared by every attempt of one "
    "decision turn, so a redo shows what it superseded",
}

# --- one abandonment record, a line of the same .meta.jsonl -------------------------------

ABANDONMENT_SCHEMA: Final[JsonSchema] = {
    "type": "object",
    "required": [
        "actions",
        "at",
        "attempts",
        "calls",
        "failure",
        "final_rejection",
        "game_id",
        "host",
        "model",
        "pid",
        "player",
        "provider",
        "redo_budget",
        "request_id",
        "seat",
        "t",
    ],
    "properties": {
        "t": {"const": "abandonment"},
        "at": _TEXT,
        "host": _TEXT,
        "pid": _COUNT,
        "game_id": _TEXT,
        "request_id": _TEXT,
        "player": _COUNT,
        "seat": _COUNT,
        "model": _TEXT,
        "provider": _TEXT,
        "attempts": _COUNT,
        "calls": _COUNT,
        "redo_budget": _COUNT,
        "final_rejection": _REJECTION,
        "failure": _values(FAILURE_KINDS),
        "actions": _COUNT,
    },
    "additionalProperties": False,
    "$comment": "the game produced no outcome: the failing decision, the refusal that ended it, "
    "how much of the redo budget was spent, and whose seat and model failed (FR-7.5, FR-11.6a)",
}


GOD_LOG_FIELDS: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        KIND_HEADER: frozenset(
            {
                "config",
                "engine_version",
                "game",
                "game_id",
                "initial_state_hash",
                "players",
                "prompt_hashes",
                "rules_version",
                "schema",
                "schema_version",
                "t",
            }
        ),
        KIND_ACTION: frozenset(
            {
                "action",
                "events",
                "player",
                "request_id",
                "result",
                "rng",
                "seq",
                "state_hash",
                "state_hash_prev",
                "t",
            }
        ),
        KIND_PHASE: frozenset({"detail", "phase", "seq", "t"}),
        KIND_TERMINAL: frozenset(
            {
                "final_scores",
                "rejections",
                "rounds",
                "seq",
                "state_hash",
                "t",
                "total_actions",
                "winner",
            }
        ),
    }
)
"""The v1 god log, frozen field for field (FR-10.2).

A declaration rather than a comment, so that `tests/core/test_contracts.py` can hold both the
v1 corpus and the runtime's own writer to it: a field added to a record type in v1 breaks a
reader that was promised the shape, and a field removed breaks the corpus it was proved on.
"""


def validate_manifest(record: Mapping[str, JsonValue]) -> list[str]:
    """Every way this manifest fails its declared shape, or an empty list when it fits."""
    return violations(dict(record), MANIFEST_SCHEMA, where="run.json")


def validate_decision(record: Mapping[str, JsonValue]) -> list[str]:
    """Every way this decision record fails its declared shape, or an empty list when it fits."""
    return violations(dict(record), DECISION_SCHEMA, where="decision")


def validate_abandonment(record: Mapping[str, JsonValue]) -> list[str]:
    """Every way this abandonment record fails its declared shape, or an empty list when it fits."""
    return violations(dict(record), ABANDONMENT_SCHEMA, where="abandonment")
