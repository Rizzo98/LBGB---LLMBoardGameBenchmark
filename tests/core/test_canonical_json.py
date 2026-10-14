"""Canonical serialisation and state hashing (PRD-v1 FR-1.1 to FR-1.5).

'to_canonical_json' is the single serialisation path used for both hashing and replay
(ARCHITECTURE.md section 6, P8). Two implementations would drift, so the tests here pin
the exact bytes of a fixed vector: any accidental change to the canonical form is a
deliberate, reviewed event, not a silent one.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from lgbg.core.canonical import (
    TRUNCATED_HASH_HEX_CHARS,
    CanonicalJsonError,
    hash_state,
    to_canonical_json,
)


class _EchoGame:
    """A game whose encoded state is the state itself; hashing needs no more than this."""

    def encode_state(self, state: Any) -> Any:
        return state


# A payload shaped like a real encoded game state: nested objects, arrays of objects,
# nulls, and string-keyed maps. Its canonical bytes are pinned below.
PINNED_STATE: dict[str, Any] = {
    "robber": None,
    "player": 2,
    "resources": {"wood": 3, "brick": 0},
    "pieces": [{"kind": "road", "edge": 17}],
    "names": {"0": "a", "1": "b"},
}
PINNED_CANONICAL = (
    '{"names":{"0":"a","1":"b"},"pieces":[{"edge":17,"kind":"road"}],'
    '"player":2,"resources":{"brick":0,"wood":3},"robber":null}'
)
PINNED_DIGEST = "02c2eecd25d3544b"


def test_sorts_object_keys() -> None:
    assert to_canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_emits_no_insignificant_whitespace() -> None:
    assert to_canonical_json({"a": [1, 2], "b": {"c": None}}) == '{"a":[1,2],"b":{"c":null}}'


def test_escapes_non_ascii_text() -> None:
    assert to_canonical_json({"a": "caf\u00e9"}) == '{"a":"caf\\u00e9"}'


def test_normalises_tuples_to_arrays() -> None:
    assert to_canonical_json({"a": (1, 2)}) == to_canonical_json({"a": [1, 2]})


def test_rejects_floats_because_state_must_be_integral() -> None:
    with pytest.raises(CanonicalJsonError, match="float"):
        to_canonical_json({"ratio": 0.5})


def test_rejects_non_string_object_keys() -> None:
    with pytest.raises(CanonicalJsonError, match="key"):
        to_canonical_json({1: "a"})


def test_rejects_values_that_are_not_json() -> None:
    with pytest.raises(CanonicalJsonError):
        to_canonical_json({"a": {1, 2}})


def test_fixed_vector_pins_the_exact_bytes() -> None:
    assert to_canonical_json(PINNED_STATE) == PINNED_CANONICAL


def test_hash_width_is_one_named_constant() -> None:
    digest = hash_state(PINNED_STATE, _EchoGame())

    assert TRUNCATED_HASH_HEX_CHARS == 16
    assert len(digest) == TRUNCATED_HASH_HEX_CHARS
    assert digest == digest.lower()


def test_fixed_vector_pins_the_exact_digest() -> None:
    assert hash_state(PINNED_STATE, _EchoGame()) == PINNED_DIGEST


def test_hash_is_a_truncated_sha256_of_the_canonical_bytes() -> None:
    expected = hashlib.sha256(PINNED_CANONICAL.encode("utf-8")).hexdigest()[
        :TRUNCATED_HASH_HEX_CHARS
    ]

    assert hash_state(PINNED_STATE, _EchoGame()) == expected


def test_hash_is_stable_across_key_insertion_order() -> None:
    reordered = {
        "names": {"1": "b", "0": "a"},
        "pieces": [{"edge": 17, "kind": "road"}],
        "player": 2,
        "resources": {"brick": 0, "wood": 3},
        "robber": None,
    }

    assert hash_state(reordered, _EchoGame()) == hash_state(PINNED_STATE, _EchoGame())


def test_different_states_hash_differently() -> None:
    other = dict(PINNED_STATE, player=3)

    assert hash_state(other, _EchoGame()) != hash_state(PINNED_STATE, _EchoGame())
