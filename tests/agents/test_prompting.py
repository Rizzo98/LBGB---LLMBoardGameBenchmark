"""Prompt assembly and hash enforcement (PRD-v2 FR-9.1 to FR-9.6).

A run is one experiment only if every model was given the same bytes. These tests hold the four
layers apart, hash all of them into the manifest, and prove that editing a file after the run
started is an abort rather than a silent second condition.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.adapters.mcp.server import Profile, build_server
from lgbg.agents.prompting import (
    PromptError,
    PromptHashError,
    PromptSet,
    game_prompt_path,
)
from lgbg.core.config import RunConfig
from lgbg.core.contracts import PROMPT_LAYERS, validate_manifest
from lgbg.core.game import get_game
from lgbg.core.prompts import digest
from lgbg.core.tools import describe_read, tool_definitions
from lgbg.host.facade import SessionFacade

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "v2" / "run.json"


def prompt_files(tmp_path: Path) -> tuple[Path, Path]:
    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "system.md").write_text("You are a player.\n", encoding="utf-8")
    (agent / "policy.md").write_text("No hints will be given.\n", encoding="utf-8")
    (agent / "redo.md").write_text("Refused: {rejection}. Try again.\n", encoding="utf-8")
    game = tmp_path / "game.md"
    game.write_text("# A game\n\nRules only.\n", encoding="utf-8")
    return agent, game


def test_the_four_layers_are_separable_and_all_hashed(tmp_path: Path) -> None:
    agent, game = prompt_files(tmp_path)
    prompts = PromptSet.load("catan", prompts_directory=agent, game_prompt=game)

    assert set(prompts.texts) == set(PROMPT_LAYERS)
    assert prompts.text("system") == "You are a player.\n"
    assert prompts.text("policy") == "No hints will be given.\n"
    assert prompts.text("game") == "# A game\n\nRules only.\n"
    assert prompts.hashes() == {layer: digest(prompts.text(layer)) for layer in PROMPT_LAYERS}


def test_the_catan_layers_are_the_files_the_plugin_ships() -> None:
    prompts = PromptSet.load("catan")

    assert prompts.text("game") == game_prompt_path("catan").read_text(encoding="utf-8")
    assert prompts.text("game").startswith("# CATAN")
    assert prompts.text("system").startswith("You are a player")
    assert prompts.text("policy").startswith("This is a measured game")
    assert prompts.text("redo").startswith("Your action was refused")
    assert prompts.hashes() != {}


def test_every_layer_is_recorded_in_the_manifest() -> None:
    prompts = PromptSet.load("catan")
    manifest: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    manifest["prompts"] = prompts.hashes()

    assert validate_manifest(manifest) == []
    assert set(manifest["prompts"]) == set(PROMPT_LAYERS)


def test_a_hash_mismatch_aborts_before_the_game(tmp_path: Path) -> None:
    agent, game = prompt_files(tmp_path)
    prompts = PromptSet.load("catan", prompts_directory=agent, game_prompt=game)
    prompts.verify()
    (agent / "policy.md").write_text("A hint will be given.\n", encoding="utf-8")

    with pytest.raises(PromptHashError, match="policy"):
        prompts.verify()


def test_a_manifest_hash_mismatch_is_an_abort(tmp_path: Path) -> None:
    agent, game = prompt_files(tmp_path)
    prompts = PromptSet.load("catan", prompts_directory=agent, game_prompt=game)
    expected = prompts.hashes()
    expected["game"] = "0" * 64

    with pytest.raises(PromptHashError, match="game"):
        prompts.verify(expected)


def test_a_manifest_missing_a_layer_is_an_abort(tmp_path: Path) -> None:
    agent, game = prompt_files(tmp_path)
    prompts = PromptSet.load("catan", prompts_directory=agent, game_prompt=game)
    expected = prompts.hashes()
    del expected["redo"]

    with pytest.raises(PromptHashError, match="missing"):
        prompts.verify(expected)


def test_a_missing_prompt_is_refused(tmp_path: Path) -> None:
    with pytest.raises(PromptError, match="missing"):
        PromptSet.load("catan", prompts_directory=tmp_path, game_prompt=tmp_path / "game.md")


def test_initial_messages_keep_each_layer_separate() -> None:
    prompts = PromptSet.load("catan")

    messages = prompts.initial_messages("the position")

    assert [message.role.value for message in messages] == [
        "system",
        "system",
        "system",
        "user",
    ]
    assert [message.content for message in messages] == [
        prompts.text("system"),
        prompts.text("policy"),
        prompts.text("game"),
        "the position",
    ]


def test_the_redo_prompt_is_one_shared_artefact_with_one_substitution() -> None:
    first = PromptSet.load("catan")
    second = PromptSet.load("catan")

    assert first.text("redo") == second.text("redo")
    assert "NO_SUCH_ACTION" in first.redo_text("NO_SUCH_ACTION")
    assert "{rejection}" not in first.redo_text("NO_SUCH_ACTION")


def test_the_game_prompt_path_is_the_plugin_convention() -> None:
    path = game_prompt_path("catan")

    assert path == Path("lgbg/games/catan/prompts/game.md").resolve()
    assert path.is_file()


def _surface() -> tuple[Any, str, Any]:
    facade = SessionFacade()
    game_id = facade.create_session(
        "catan", RunConfig(seed=1, players=4, interaction_protocol="decline_only")
    )
    server = build_server(facade, "catan", profile=Profile.BENCHMARK, session_id=game_id, player=0)
    return facade, game_id, server


def test_tool_descriptions_come_from_the_plugin_generator() -> None:
    _, _, server = _surface()
    plugin = get_game("catan")

    tools = asyncio.run(server._list_tools())

    assert [(tool.name, tool.description) for tool in tools] == [
        (str(definition["name"]), str(definition["description"]))
        for definition in tool_definitions(plugin)
    ]


def test_describe_reads_come_from_the_plugin_generator() -> None:
    _, game_id, server = _surface()
    plugin = get_game("catan")

    resources = asyncio.run(server._list_resources())

    assert {resource.name for resource in resources} == {
        describe_read(plugin, "state", game_id=game_id, player=0),
        describe_read(plugin, "decisions", game_id=game_id),
        describe_read(plugin, "surface", game_id=game_id, player=0),
    }
