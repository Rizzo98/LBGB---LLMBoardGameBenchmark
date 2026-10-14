"""Run configuration (PRD-v1 FR-5.1 to FR-5.4).

The configuration is part of the record: it round-trips through the header exactly, because
a result whose configuration cannot be reconstructed is not reproducible. Unknown keys are
rejected rather than ignored, because a misspelled key that is silently dropped produces a
run that looks configured and is not.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Final

import pytest

from lgbg.core.config import (
    AssistLevel,
    ConfigError,
    GameConfig,
    RejectionDetail,
    RunConfig,
)
from lgbg.core.types import JsonValue

PROTOCOL: Final[str] = "decline_only"
GAME_OPTION_KEYS: Final[frozenset[str]] = frozenset({"board", "number_placement"})
SEED: Final[int] = 123456789


def _raw(**kwargs: JsonValue) -> dict[str, JsonValue]:
    """A configuration object as it arrives from a header or a scripted file."""
    return dict(kwargs)


def _standard() -> RunConfig:
    return RunConfig(
        seed=SEED,
        interaction_protocol=PROTOCOL,
        game_config=GameConfig({"board": "fixed:standard_a"}),
    )


def test_assist_defaults_to_l1_and_detail_to_the_matching_tier() -> None:
    config = _standard()

    assert config.assist is AssistLevel.L1
    assert config.rejection_detail is RejectionDetail.STANDARD


@pytest.mark.parametrize(
    ("assist", "expected"),
    [
        (AssistLevel.L0, RejectionDetail.MINIMAL),
        (AssistLevel.L1, RejectionDetail.STANDARD),
        (AssistLevel.L2, RejectionDetail.FULL),
    ],
)
def test_rejection_detail_defaults_to_the_tier_matching_assist(
    assist: AssistLevel, expected: RejectionDetail
) -> None:
    config = RunConfig(seed=SEED, assist=assist, interaction_protocol=PROTOCOL)

    assert config.rejection_detail is expected


def test_rejection_detail_is_independently_overridable() -> None:
    quiet = RunConfig(
        seed=SEED,
        assist=AssistLevel.L0,
        rejection_detail=RejectionDetail.FULL,
        interaction_protocol=PROTOCOL,
    )
    chatty = RunConfig(
        seed=SEED,
        assist=AssistLevel.L2,
        rejection_detail=RejectionDetail.MINIMAL,
        interaction_protocol=PROTOCOL,
    )

    assert quiet.rejection_detail is RejectionDetail.FULL
    assert chatty.rejection_detail is RejectionDetail.MINIMAL


def test_header_mapping_has_the_documented_flat_shape() -> None:
    config = RunConfig(
        seed=SEED,
        assist=AssistLevel.L2,
        interaction_protocol=PROTOCOL,
        prompt_hashes={"catan/game.md": "ab" * 32},
        game_config=GameConfig({"board": "fixed:standard_a", "number_placement": "spiral"}),
    )

    assert config.to_mapping() == {
        "seed": SEED,
        "assist": "L2",
        "rejection_detail": "full",
        "interaction_protocol": PROTOCOL,
        "prompt_hashes": {"catan/game.md": "ab" * 32},
        "board": "fixed:standard_a",
        "number_placement": "spiral",
    }


def test_config_round_trips_through_the_header_record_exactly() -> None:
    config = RunConfig(
        seed=SEED,
        assist=AssistLevel.L2,
        rejection_detail=RejectionDetail.MINIMAL,
        interaction_protocol=PROTOCOL,
        prompt_hashes={"catan/game.md": "ab" * 32},
        game_config=GameConfig({"board": "fixed:standard_a"}),
    )

    restored = RunConfig.from_mapping(config.to_mapping(), game_option_keys=GAME_OPTION_KEYS)

    assert restored == config
    assert restored.to_mapping() == config.to_mapping()


def test_unknown_key_is_rejected_rather_than_ignored() -> None:
    raw = _raw(seed=SEED, interaction_protocol=PROTOCOL, sead=SEED)

    with pytest.raises(ConfigError) as raised:
        RunConfig.from_mapping(raw, game_option_keys=GAME_OPTION_KEYS)

    assert "sead" in str(raised.value)


def test_game_option_not_declared_by_the_game_is_rejected() -> None:
    raw = _raw(seed=SEED, interaction_protocol=PROTOCOL, board="fixed:standard_a")

    with pytest.raises(ConfigError, match="board"):
        RunConfig.from_mapping(raw, game_option_keys=frozenset())


def test_declared_game_options_are_carried_opaque_to_the_core() -> None:
    raw = _raw(seed=SEED, interaction_protocol=PROTOCOL, board="fixed:standard_a")

    config = RunConfig.from_mapping(raw, game_option_keys=GAME_OPTION_KEYS)

    assert config.game_config.options == {"board": "fixed:standard_a"}


def test_game_option_may_not_shadow_a_core_key() -> None:
    with pytest.raises(ConfigError, match="seed"):
        RunConfig.from_mapping(_raw(seed=SEED), game_option_keys=frozenset({"seed"}))


def test_unknown_assist_level_is_rejected_with_the_accepted_values() -> None:
    raw = _raw(seed=SEED, assist="L3", interaction_protocol=PROTOCOL)

    with pytest.raises(ConfigError) as raised:
        RunConfig.from_mapping(raw, game_option_keys=GAME_OPTION_KEYS)

    assert "L3" in str(raised.value)
    assert "L0" in str(raised.value)


def test_unknown_rejection_detail_is_rejected() -> None:
    raw = _raw(seed=SEED, rejection_detail="verbose", interaction_protocol=PROTOCOL)

    with pytest.raises(ConfigError, match="verbose"):
        RunConfig.from_mapping(raw, game_option_keys=GAME_OPTION_KEYS)


def test_seed_must_be_an_integer() -> None:
    raw = _raw(seed="123", interaction_protocol=PROTOCOL)

    with pytest.raises(ConfigError, match="seed"):
        RunConfig.from_mapping(raw, game_option_keys=GAME_OPTION_KEYS)


def test_missing_required_keys_are_reported_together() -> None:
    with pytest.raises(ConfigError) as raised:
        RunConfig.from_mapping(_raw(), game_option_keys=GAME_OPTION_KEYS)

    message = str(raised.value)
    assert "seed" in message
    assert "interaction_protocol" in message


def test_prompt_hashes_must_be_a_mapping_of_strings() -> None:
    raw = _raw(seed=SEED, interaction_protocol=PROTOCOL, prompt_hashes={"game.md": 7})

    with pytest.raises(ConfigError, match="prompt_hashes"):
        RunConfig.from_mapping(raw, game_option_keys=GAME_OPTION_KEYS)


def test_config_is_immutable() -> None:
    config = _standard()

    with pytest.raises(FrozenInstanceError):
        config.seed = 1  # type: ignore[misc]


def test_configuration_does_not_alias_the_callers_mutables() -> None:
    options = {"board": "fixed:standard_a"}
    hashes = {"catan/game.md": "ab" * 32}
    config = RunConfig(
        seed=SEED,
        interaction_protocol=PROTOCOL,
        prompt_hashes=hashes,
        game_config=GameConfig(options),
    )

    options["board"] = "fixed:other"
    hashes["catan/game.md"] = "ff" * 32

    assert config.game_config.options == {"board": "fixed:standard_a"}
    assert config.prompt_hashes == {"catan/game.md": "ab" * 32}
