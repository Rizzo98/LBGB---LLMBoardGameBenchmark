"""Prompt assembly and the hash that makes a mid-run edit impossible (FR-9.1 to FR-9.6).

Four artefacts, kept separate because they answer four different questions:

- the game's own game.md: what the game is, how a position is written, what each action means;
- the role system.md: that the model is a player in a measured game;
- the provider policy policy.md: what help it will and will not receive;
- the shared redo.md: the one sentence every model gets when the engine refuses an action.

Separate files are not enough on their own; a run is only an experiment if every model was given the
same bytes. So the set carries a hash per layer (FR-9.3), the manifest requires all four (K-002),
and verify re-reads the files and compares them before every game (FR-9.4). A file edited
between two games is then an abort, not a silent second experiment.

The game prompt path is a convention, not a table: lgbg/games/<game>/prompts/game.md. The agent
prompts are not game-specific and live once in lgbg/agents/prompts. Nothing here interprets a
prompt: hashing and assembling are the whole of it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

from lgbg.agents.providers.base import Message, Role
from lgbg.core.contracts import PROMPT_LAYERS
from lgbg.core.prompts import digest

PROMPTS_DIRECTORY: Final[Path] = Path(__file__).with_name("prompts")
"""Where the three agent-policy artefacts live, shared by every game and every model."""

GAME_PROMPT_NAME: Final[str] = "game.md"
REDO_PLACEHOLDER: Final[str] = "{rejection}"
"""The one substitution the shared redo prompt permits."""


class PromptError(ValueError):
    """A prompt artefact is missing, empty or not usable as a run's prompt."""


class PromptHashError(PromptError):
    """A prompt changed after the run recorded its hash. The run must abort (FR-9.4)."""


@dataclass(frozen=True, slots=True)
class PromptSet:
    """The four prompt layers of one game, with their sources and hashes."""

    game: str
    texts: Mapping[str, str]
    sources: Mapping[str, Path]

    def __post_init__(self) -> None:
        object.__setattr__(self, "texts", MappingProxyType(dict(self.texts)))
        object.__setattr__(self, "sources", MappingProxyType(dict(self.sources)))
        missing = [layer for layer in PROMPT_LAYERS if layer not in self.texts]
        if missing:
            raise PromptError(f"the prompt set is missing layer(s) {missing}")

    @classmethod
    def load(
        cls,
        game: str,
        *,
        prompts_directory: Path | None = None,
        game_prompt: Path | None = None,
    ) -> PromptSet:
        """Read all four layers from disk, refusing a missing or empty artefact."""
        directory = PROMPTS_DIRECTORY if prompts_directory is None else prompts_directory
        files: dict[str, Path] = {
            "game": game_prompt_path(game) if game_prompt is None else game_prompt,
            "policy": directory / "policy.md",
            "redo": directory / "redo.md",
            "system": directory / "system.md",
        }
        texts: dict[str, str] = {}
        for layer in PROMPT_LAYERS:
            path = files[layer]
            if not path.is_file():
                raise PromptError(f"the {layer} prompt is missing at {path}")
            text = path.read_text(encoding="utf-8")
            if not text.strip():
                raise PromptError(f"the {layer} prompt at {path} is empty")
            texts[layer] = text
        return cls(game=game, texts=texts, sources=files)

    def text(self, layer: str) -> str:
        """One layer, by the name the manifest uses."""
        if layer not in self.texts:
            raise PromptError(f"unknown prompt layer {layer!r}")
        return self.texts[layer]

    def hashes(self) -> dict[str, str]:
        """The hash of every layer, as the manifest carries them (FR-9.3)."""
        return {layer: digest(self.texts[layer]) for layer in PROMPT_LAYERS}

    def verify(self, expected: Mapping[str, str] | None = None) -> None:
        """Re-read every file and abort if anything changed (FR-9.4).

        Passing 'expected' checks against the hashes a manifest recorded; passing nothing checks
        against the hashes this set was loaded with. Either way the files are read again, because
        the value of the check is that it sees the file, not the copy this object already holds.
        """
        current = {
            layer: digest(self.sources[layer].read_text(encoding="utf-8"))
            for layer in PROMPT_LAYERS
        }
        wanted = self.hashes() if expected is None else dict(expected)
        missing = [layer for layer in PROMPT_LAYERS if layer not in wanted]
        unexpected = [layer for layer in wanted if layer not in PROMPT_LAYERS]
        changed = [layer for layer in PROMPT_LAYERS if current[layer] != wanted.get(layer)]
        if missing or unexpected or changed:
            parts: list[str] = []
            if missing:
                parts.append(f"missing {missing}")
            if unexpected:
                parts.append(f"unexpected {unexpected}")
            if changed:
                parts.append(f"changed {changed}")
            raise PromptHashError("prompt hash mismatch: " + "; ".join(parts))

    def system_messages(self) -> tuple[Message, ...]:
        """The three prompt layers, in the order every strategy puts them.

        Kept separate rather than concatenated, so a reader of the sidecar can tell which artefact
        said what and a hash names one file rather than a blend.
        """
        return (
            Message(role=Role.SYSTEM, content=self.text("system")),
            Message(role=Role.SYSTEM, content=self.text("policy")),
            Message(role=Role.SYSTEM, content=self.text("game")),
        )

    def initial_messages(self, state: str) -> tuple[Message, ...]:
        """The conversation before the model's first answer: the layers, then the state."""
        return (*self.system_messages(), Message(role=Role.USER, content=state))

    def redo_text(self, rejection: str) -> str:
        """The shared redo prompt with the engine's refusal substituted (FR-7.2, FR-9.6)."""
        return self.text("redo").replace(REDO_PLACEHOLDER, rejection)


def game_prompt_path(game: str) -> Path:
    """The one game prompt a plugin ships, by the convention the prompt layer declares."""
    return Path(__file__).resolve().parents[1] / "games" / game / "prompts" / GAME_PROMPT_NAME


def layers() -> Sequence[str]:
    """The layer names, in manifest order, so a caller need not repeat them."""
    return PROMPT_LAYERS


__all__: list[str] = [
    "GAME_PROMPT_NAME",
    "PROMPTS_DIRECTORY",
    "REDO_PLACEHOLDER",
    "PromptError",
    "PromptHashError",
    "PromptSet",
    "game_prompt_path",
    "layers",
]
