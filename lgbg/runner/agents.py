"""The declared set of agents a seat can be played by (PRD-v2 FR-11.1).

The runner assigns an **agent** to every seat, and there are exactly three kinds, declared here
because a record has to name one and results have to tell them apart:

- an **LLM agent** owns a provider, a model identity and its sampling parameters. It is the only
  kind that reaches a model, spends tokens, and is ever reported as scored (FR-11.1).
- a **reference player** is test infrastructure: it chooses one of the game's own legal actions and
  never a model's, so the runner can be exercised without a provider. It is never scored and never
  appears in a comparison. It receives the plugin, the position, the seat and the open decision, so
  the fuzz harness's selectors can be reused rather than reimplemented.
- a **scripted agent** replays a recorded action list. It is how a fixture, a golden record or a
  smoke test plays without an agent at all, and it must never be mistaken for one.

The three kinds share a declared spelling, `AgentKind`, which is the manifest's own vocabulary.
The union is deliberate and small: adding a fourth kind of player is then a reviewed change to the
manifest, to results, and to this module together.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from lgbg.agents.providers.base import Provider, Sampling
from lgbg.core.game import Game
from lgbg.core.rng import RandomSource
from lgbg.core.types import Action, DecisionRequest, PlayerId, State


class AgentKind(StrEnum):
    """How a seat is played, in the words the manifest records (FR-11.1)."""

    LLM = "llm"
    REFERENCE = "reference"
    SCRIPTED = "scripted"


@dataclass(frozen=True, slots=True)
class ReferenceView:
    """What a reference player is given to choose from: the game, the position, the question.

    Not a prompt and not an observation. A reference player is not a model, so the projection that
    hides information from a player would only bend its policy; it reads the engine's position and
    the plugin's own legal-action enumeration through one read of the facade (K-027).
    """

    game: Game
    state: State
    seat: PlayerId
    request: DecisionRequest
    chooser: RandomSource
    """A source the runner derives from the run's seed, the seat and the decision, so a reference
    player that draws is still reproducible and two runs of the same design agree byte for byte.

    A draw records its value, so an action is chosen by index rather than passed to `choice`: the
    fuzz harness's selectors already work that way, and a reference player reuses them (FR-11.1)."""


class ReferencePlayer(Protocol):
    """A non-LLM policy, usable in any seat of any table; test infrastructure, never scored."""

    @property
    def name(self) -> str:
        """How the manifest identifies this player. Never a model name (FR-11.1)."""
        ...

    def choose(self, view: ReferenceView) -> Action:
        """One legal action for the seat that is being asked."""
        ...


@dataclass(frozen=True, slots=True)
class LlmAgent:
    """One seat played by a provider, with the identity the manifest records."""

    provider: Provider
    model: str
    provider_id: str
    provider_version: str
    sampling: Sampling = field(default_factory=Sampling)

    def __post_init__(self) -> None:
        if not self.model:
            raise ValueError("an LLM agent needs a model")
        if not self.provider_id or not self.provider_version:
            raise ValueError("an LLM agent needs a provider identity and version")

    @property
    def kind(self) -> AgentKind:
        return AgentKind.LLM

    @property
    def name(self) -> str:
        return self.model


@dataclass(frozen=True, slots=True)
class ReferenceAgent:
    """One seat played by a declared, non-model policy."""

    player: ReferencePlayer

    def __post_init__(self) -> None:
        if not self.player.name:
            raise ValueError("a reference player needs a name")

    @property
    def kind(self) -> AgentKind:
        return AgentKind.REFERENCE

    @property
    def name(self) -> str:
        return self.player.name


@dataclass(frozen=True, slots=True)
class ScriptedAgent:
    """One seat played from a recorded action list, never through a provider."""

    actions: Sequence[Action]

    def __post_init__(self) -> None:
        if not self.actions:
            raise ValueError("a scripted agent needs at least one action")

    @property
    def kind(self) -> AgentKind:
        return AgentKind.SCRIPTED

    @property
    def name(self) -> str:
        return AgentKind.SCRIPTED.value


type Agent = LlmAgent | ReferenceAgent | ScriptedAgent
"""Every way a seat may be played. There is no fourth kind, by declaration."""


__all__: list[str] = [
    "Agent",
    "AgentKind",
    "LlmAgent",
    "ReferenceAgent",
    "ReferencePlayer",
    "ReferenceView",
    "ScriptedAgent",
]
