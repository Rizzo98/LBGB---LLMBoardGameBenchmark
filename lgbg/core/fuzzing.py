"""The generic fuzz harness (PRD-v1 FR-22; ARCHITECTURE.md 7.11, 15).

One harness, every game: it drives a plugin it knows nothing about with the actions the plugin
offers, and after every action asserts what that plugin declared about itself - its invariants
hold, its schema accepts everything it offers, a refusal leaves the position alone, an accepted
action says something happened, and observing changes nothing. It is never scored and never
presented as a bot (FR-22.6); finding a game that cannot survive its own declarations is the point.

A game that will not end is a *livelock*, reported apart from a rule failure (FR-22.4), because
the two send a reader to different places - and K-062 measured that a uniform-random Catan driver
can play four thousand actions without finishing, so the distinction is not hypothetical.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from lgbg.core.canonical import hash_state
from lgbg.core.config import RunConfig
from lgbg.core.game import Applied, Game
from lgbg.core.rng import Purpose, RandomSource, SeededRandomSource
from lgbg.core.run import GameRun
from lgbg.core.schema import validate_action
from lgbg.core.types import Action


@dataclass(frozen=True, slots=True)
class FuzzReport:
    """What one fuzzed game did, and every declaration it broke on the way."""

    actions: int
    accepted: int
    rejected: int
    finished: bool
    livelock: bool
    codes: tuple[str, ...]
    offenders: tuple[str, ...] = field(default=())

    @property
    def clean(self) -> bool:
        """Whether the game kept every promise it made about itself."""
        return not self.offenders


Selector = Callable[[Sequence[Action], RandomSource], Action]
"""How a policy picks one of the offered actions, drawing from a source of chance of its own."""


def uniform(offered: Sequence[Action], chooser: RandomSource) -> Action:
    """Any offered action, with equal chance: the wanderer."""
    return _pick(offered, chooser)


def maximal(offered: Sequence[Action], chooser: RandomSource) -> Action:
    """The action that says the most, which is the most committing one on offer."""
    most = max(len(action.params) for action in offered)
    return _pick([a for a in offered if len(a.params) == most], chooser)


def minimal(offered: Sequence[Action], chooser: RandomSource) -> Action:
    """The action that says the least: a driver that rolls and ends turns and little else."""
    fewest = min(len(action.params) for action in offered)
    return _pick([a for a in offered if len(a.params) == fewest], chooser)


def _pick(offered: Sequence[Action], chooser: RandomSource) -> Action:
    """One of these, drawn by index: a draw records what it chose, and an Action is not JSON."""
    return offered[chooser.randint(0, len(offered) - 1, purpose=DRIVER_CHOICE)]


POLICIES: Final[dict[str, Selector]] = {
    "maximal": maximal,
    "minimal": minimal,
    "uniform": uniform,
}
"""The three shapes of driver the card asks for, named for what they do to a decision (FR-22.5)."""


MAX_ACTIONS: Final[int] = 4000
"""The bound a game has to finish inside before it is called a livelock."""

DRIVER_CHOICE: Final[Purpose] = "fuzz_driver_choice"
"""The label the driver's draws are recorded under, so its choices are replayable too (FR-22.1)."""


def run_fuzz(
    game: Game,
    config: RunConfig,
    *,
    policy: Selector = uniform,
    max_actions: int = MAX_ACTIONS,
    directory: Path | None = None,
) -> FuzzReport:
    """Drive one game with offered actions, asserting its declarations after every one.

    The driver has a source of chance of its own, seeded from the run's seed and the game's name,
    so it drives the same way however the game's own draws fall (FR-22.1) - and nothing here knows
    what game it is driving (FR-22.5).
    """
    chooser = SeededRandomSource(_driver_seed(game, config))
    run = GameRun(game, config, game_id="fuzz", directory=directory)
    offenders: list[str] = []
    codes: list[str] = []
    accepted = rejected = 0

    for _ in range(max_actions):
        if game.is_terminal(run.state):
            break
        offered = [
            action
            for request in run.pending
            for action in game.legal_actions(run.state, request.player)
        ]
        offenders.extend(_offered_violations(game, offered))
        before = hash_state(run.state, game)
        result = run.submit(policy(offered, chooser))
        if isinstance(result, Applied):
            accepted += 1
        else:
            rejected += 1
            codes.append(result.rejection.code.code)
        offenders.extend(_after(game, run, result, config.players, before))

    finished = game.is_terminal(run.state)
    return FuzzReport(
        actions=accepted + rejected,
        accepted=accepted,
        rejected=rejected,
        finished=finished,
        livelock=not finished,
        codes=tuple(sorted(set(codes))),
        offenders=tuple(offenders),
    )


def _driver_seed(game: Game, config: RunConfig) -> int:
    """A seed apart from the game's: the name and the run seed, hashed into a stable integer."""
    text = f"{game.name}:{config.seed}".encode()
    return int(hashlib.sha256(text).hexdigest()[:12], 16)


def _offered_violations(game: Game, offered: Sequence[Action]) -> list[str]:
    """Every action a game offers is one its own declared schema accepts (FR-18.1)."""
    schema = game.action_schema()
    return [
        f"{action.type} {dict(action.params)} does not fit its declared schema"
        for action in offered
        if validate_action(schema, action) is not None
    ]


def _after(game: Game, run: GameRun, result: Any, players: int, before: str) -> list[str]:
    """The five things asserted after every action (FR-22.2, FR-22.3, FR-16.6).

    The invariants are the game's own, declared by the plugin, and this function has no idea what
    they mean - which is the point of the interface. The rest are the platform's: a refusal that
    moved the position, an accepted action that said nothing happened, an observation that changed
    what it was observing, and a projection that is not the same twice.
    """
    state = run.state
    found = [f"{v.invariant}: {v.detail}" for v in game.check_invariants(state)]
    if isinstance(result, Applied):
        if not result.events:
            found.append("an accepted action emitted no event")
        found.extend(_observation_violations(game, state, players))
    elif hash_state(state, game) != before:
        found.append(f"a refusal moved the position: {result.rejection.code.code}")
    return found


def _observation_violations(game: Game, state: Any, players: int) -> list[str]:
    """Observing is a reading: it changes nothing and answers the same twice (FR-16.6)."""
    before = hash_state(state, game)
    first = [game.observe_spectator(state)] + [game.observe(state, seat) for seat in range(players)]
    again = [game.observe_spectator(state)] + [game.observe(state, seat) for seat in range(players)]
    found: list[str] = []
    if first != again:
        found.append("an observation is not the same twice")
    if hash_state(state, game) != before:
        found.append("observing changed the position")
    return found
