"""The run manifest: what a run declares before a single action is played (PRD-v2 FR-10.1).

The manifest is the run's own account of itself, and it is written once, before the first decision:
run id, game and versions, every configuration value, the seats and which agent played each one,
every policy value, every prompt hash, the provider identities, the experiment design, and the price
table with the moment it was read. A result whose configuration cannot be reconstructed is not an
experiment, so the shape is frozen in `core.contracts` and checked against it here before it is
written.

Two rules make it honest rather than merely complete:

- **The prompts are hashed once and checked before every game.** The set carries a hash per layer,
  and `run_game` re-reads the files before playing (FR-9.4), so a prompt edited between two games
  aborts the run instead of silently creating a second experiment.
- **Nothing here knows a game.** Which game's options exist, what its starting configuration is
  called, and how many seats it has are the caller's and the plugin's declarations. The manifest
  records them; this module never reads one out of another (FR-11.7).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from lgbg import __version__
from lgbg.agents.context import ContextPolicy
from lgbg.agents.loop import TurnPolicy
from lgbg.agents.pricing import PriceTable
from lgbg.agents.prompting import PromptSet
from lgbg.core.config import RunConfig
from lgbg.core.contracts import MANIFEST_SCHEMA_NAME
from lgbg.core.game import Game
from lgbg.core.types import JsonValue, PlayerId
from lgbg.runner.agents import Agent, LlmAgent, ReferenceAgent, ScriptedAgent
from lgbg.runner.design import GameDesign

DEFAULT_GAME_TIMEOUT_S: Final[int] = 7200
"""The wall-clock bound one game may take before it is abandoned, in seconds (FR-7.11)."""


class ManifestError(RuntimeError):
    """The manifest this run would write does not fit the frozen shape."""


def build_manifest(
    *,
    game: Game,
    config: RunConfig,
    run_id: str,
    seats: Mapping[PlayerId, Agent],
    prompts: PromptSet,
    price_table: PriceTable,
    policy: TurnPolicy,
    context: ContextPolicy,
    design: GameDesign | None = None,
) -> dict[str, JsonValue]:
    """The `run.json` one game writes, checked against the declared shape before it is stored."""
    chosen = GameDesign.single_game() if design is None else design
    game_config = dict(config.to_mapping().items())
    game_config.pop("prompt_hashes", None)
    timeout = int(policy.decision_timeout_s)
    if timeout != policy.decision_timeout_s or timeout < 1:
        raise ManifestError("the manifest records decision_timeout_s as whole seconds, at least 1")
    _validate_seats(seats, config.players)
    seat_rows = [_seat_row(seat, seats[seat]) for seat in range(config.players)]
    return {
        "schema": MANIFEST_SCHEMA_NAME,
        "run_id": run_id,
        "engine_version": __version__,
        "game": {
            "name": game.name,
            "rules_version": game.rules_version,
            "schema_version": game.schema_version,
        },
        "config": game_config,
        "seats": seat_rows,
        "design": chosen.to_mapping(),
        "policies": {
            **context.to_mapping(),
            "redo_budget": policy.redo_budget,
            "on_exhausted": "abandon_game",
            "step_budget": policy.step_budget,
            "decision_timeout_s": timeout,
            "game_timeout_s": DEFAULT_GAME_TIMEOUT_S,
            "budget_micro_usd": None,
        },
        "prompts": prompts.hashes(),
        "providers": _provider_rows(seats),
        "price_table": price_table.to_mapping(),
    }


def _validate_seats(seats: Mapping[PlayerId, Agent], players: int) -> None:
    """Every seat of the game has exactly one agent, and the game has no extra seats."""
    expected = set(range(players))
    missing = sorted(expected - set(seats))
    if missing:
        raise ManifestError(f"seat {missing[0]} has no agent")
    extra = sorted(set(seats) - expected)
    if extra:
        raise ManifestError(f"seat {extra[0]} is not in a {players}-seat game")


def _seat_row(seat: PlayerId, agent: Agent) -> dict[str, JsonValue]:
    """One seat's agent, in the manifest's own vocabulary (FR-11.1)."""
    if isinstance(agent, LlmAgent):
        return {
            "seat": seat,
            "agent": agent.kind.value,
            "player": None,
            "model": agent.model,
            "provider": agent.provider_id,
            "sampling": agent.sampling.to_mapping(),
        }
    if isinstance(agent, ReferenceAgent):
        return {
            "seat": seat,
            "agent": agent.kind.value,
            "player": agent.name,
            "model": None,
            "provider": None,
            "sampling": None,
        }
    if not isinstance(agent, ScriptedAgent):
        raise ManifestError(f"seat {seat} has an agent kind the manifest does not declare")
    return {
        "seat": seat,
        "agent": agent.kind.value,
        "player": agent.name,
        "model": None,
        "provider": None,
        "sampling": None,
    }


def _provider_rows(seats: Mapping[PlayerId, Agent]) -> list[JsonValue]:
    """Every provider identity a model seat used, once each and in seat order (FR-10.1)."""
    rows: list[JsonValue] = []
    seen: set[tuple[str, str]] = set()
    for agent in seats.values():
        if not isinstance(agent, LlmAgent):
            continue
        identity = (agent.provider_id, agent.provider_version)
        if identity in seen:
            continue
        seen.add(identity)
        rows.append({"id": agent.provider_id, "version": agent.provider_version})
    return rows


__all__: list[str] = [
    "DEFAULT_GAME_TIMEOUT_S",
    "ManifestError",
    "build_manifest",
]
