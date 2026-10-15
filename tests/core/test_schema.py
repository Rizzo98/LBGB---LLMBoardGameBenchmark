"""The declared schema is binding, and only as far as it is declared (PRD-v1 FR-18.1, FR-18.2).

Two things are asserted here. The validator implements a *declared* subset of JSON Schema, so a
keyword it does not know is an error rather than something quietly skipped - a contract the engine
claims to enforce and does not is worse than no contract. And the core turns a violation into the
two refusals FR-18.2 names: an action the game never declared is UNKNOWN_ACTION, and a declared
action whose parameters do not fit is BAD_PARAMS.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from lgbg.core.errors import BAD_PARAMS, UNKNOWN_ACTION
from lgbg.core.schema import SchemaError, validate_action, violations
from lgbg.core.types import Action

DECLARED: Final[dict[str, Any]] = {
    "edge": {
        "type": "object",
        "properties": {"edge": {"type": "integer", "minimum": 0, "maximum": 71}},
        "required": ["edge"],
        "additionalProperties": False,
    },
    "named": {
        "type": "object",
        "properties": {"resource": {"enum": ["brick", "ore"]}},
        "required": ["resource"],
        "additionalProperties": False,
    },
    "free": {"type": "object", "properties": {}, "additionalProperties": False},
}


def _action(name: str, **params: Any) -> Action:
    return Action(player=0, type=name, params=dict(params))


def test_a_well_formed_action_passes_and_a_malformed_one_names_what_is_wrong() -> None:
    assert violations({"edge": 3}, DECLARED["edge"]) == []

    missing = violations({}, DECLARED["edge"])
    assert missing == ["value: 'edge' is required"]


def test_a_parameter_the_action_does_not_declare_is_refused() -> None:
    """A closed object is closed: a typo in a parameter name is not a silent extra."""
    found = violations({"edge": 3, "vertex": 4}, DECLARED["edge"])

    assert len(found) == 1
    assert "vertex" in found[0]
    assert violations({"edge": 3, "vertex": 4}, DECLARED["free"])


def test_the_json_types_are_checked_as_json_and_not_as_python() -> None:
    """True is an int in Python and a boolean in JSON, and the schema means the latter."""
    assert violations({"edge": True}, DECLARED["edge"])
    assert violations({"edge": "3"}, DECLARED["edge"])
    assert violations({"resource": "wood"}, DECLARED["named"])
    assert violations({"edge": [3]}, DECLARED["edge"]), "an array is not an integer"
    assert violations({"edge": 72}, DECLARED["edge"]), "above the maximum"
    assert violations({"edge": -1}, DECLARED["edge"]), "below the minimum"


def test_every_violation_is_reported_rather_than_the_first() -> None:
    found = violations({"edge": 99, "vertex": 1}, DECLARED["edge"])

    assert len(found) == 2, found


def test_a_schema_keyword_the_engine_does_not_implement_is_an_error() -> None:
    """The subset is declared, so a contract the engine cannot enforce is refused."""
    with pytest.raises(SchemaError, match="does not implement"):
        violations({}, {"type": "object", "anyOf": []})

    # An annotation describes a schema to a reader and changes nothing about what it accepts.
    assert violations({}, {"type": "object", "description": "a note"}) == []


def test_exactly_one_alternative_shape_must_fit() -> None:
    """One shape per case: two that fit would make the contract ambiguous."""
    shapes: dict[str, Any] = {
        "oneOf": [
            {
                "type": "object",
                "properties": {"a": {"const": 1}},
                "required": ["a"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {"b": {"type": "string"}},
                "required": ["b"],
                "additionalProperties": False,
            },
        ]
    }

    assert violations({"a": 1}, shapes) == []
    assert violations({"b": "x"}, shapes) == []
    assert violations({"c": 1}, shapes), "no shape fits"


def test_an_undeclared_action_type_is_unknown_and_a_bad_parameter_is_bad_params() -> None:
    """FR-18.2: the two refusals a declared surface produces, and nothing else."""
    unknown = validate_action(DECLARED, _action("teleport"))

    assert unknown is not None
    assert unknown.code == UNKNOWN_ACTION
    assert unknown.details["known"] == sorted(DECLARED)

    malformed = validate_action(DECLARED, _action("edge", edge="north"))

    assert malformed is not None
    assert malformed.code == BAD_PARAMS
    assert malformed.details["action_type"] == "edge"
    assert malformed.details["violations"]


def test_a_well_formed_action_earns_no_refusal_at_all() -> None:
    assert validate_action(DECLARED, _action("edge", edge=3)) is None
    assert validate_action(DECLARED, _action("free")) is None
