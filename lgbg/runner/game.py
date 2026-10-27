"""One game played by the runner: every seat an agent, every action through the facade (K-027).

This is the smallest complete path from a table of agents to a verifiable record. The runner owns
the seat-to-agent mapping (FR-11.1) and the run manifest (FR-10.1); it owns no game fact. It asks
the plugin registry for the game by name, drives the facade, and writes down what happened.

The three kinds of seat play differently and are recorded the same way:

- an **LLM agent** goes through the provider-agnostic loop. Every provider call becomes a decision
  record in the sidecar, with the exact messages it was sent, and the run's price table accounts
  for it (FR-10.3, FR-13.1).
- a **reference player** is asked for one of the game's own legal actions. It costs a decision, not
  a call, so it is counted in the god log and nowhere in the sidecar (FR-12.3).
- a **scripted agent** submits its recorded actions directly. It is how a fixture plays a seat with
  no agent at all, and the manifest says so.

**That the game runs entirely through the facade** is the property this slice adds. Reading the
position for a reference player is the facade's `snapshot` and submitting an action is its
`submit_action`; the runner never applies a rule itself and never keeps a second copy of the game.

**A game ends one of two ways, and the record says which.** A completed game has a terminal record
in the god log and a verdict. An abandoned game has no terminal record and one `abandonment` line
in the sidecar naming the decision, the seat and the model that failed (FR-7.5, FR-11.6). No
synthetic winner is ever written, so an abandoned game stays distinguishable from a loss.

Concurrency is K-031's, and this module is deliberately serial: decisions are answered in the
game's own resolution order, one at a time, which is the order the record must hold anyway.
"""

from __future__ import annotations

import hashlib
import os
import socket
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from lgbg.agents.accounting import RunAccounting
from lgbg.agents.context import ContextBuilder, ContextPolicy
from lgbg.agents.loop import (
    Attempt,
    AttemptOutcome,
    DecisionTurn,
    TurnPolicy,
    TurnResult,
)
from lgbg.agents.pricing import PriceTable
from lgbg.agents.prompting import PromptSet
from lgbg.agents.providers.base import CompletionConfig, ToolCall
from lgbg.agents.sidecar import (
    DecisionSidecar,
    build_abandonment_record,
    build_decision_record,
    decision_path,
)
from lgbg.agents.surface import FacadeSurface
from lgbg.core.assist import rejection_view
from lgbg.core.canonical import to_canonical_json
from lgbg.core.config import RunConfig
from lgbg.core.contracts import validate_manifest
from lgbg.core.game import Applied, get_game
from lgbg.core.rng import SeededRandomSource
from lgbg.core.types import Action, DecisionRequest, GameId, JsonValue, PlayerId
from lgbg.host.facade import SessionFacade
from lgbg.runner.agents import (
    Agent,
    LlmAgent,
    ReferenceAgent,
    ReferenceView,
    ScriptedAgent,
)
from lgbg.runner.design import GameDesign
from lgbg.runner.manifest import DEFAULT_GAME_TIMEOUT_S, ManifestError, build_manifest

REFERENCE_SEED_LABEL: Final[str] = "lgbg.reference"
"""The label the reference player's own chooser is seeded from, so its draws are reproducible."""


class GameError(RuntimeError):
    """The game could not be driven to a completed verdict."""


class GameAbortedError(GameError):
    """The driver could not continue for a reason that is not the model's failure."""


@dataclass(frozen=True, slots=True)
class Abandonment:
    """Why a game produced no outcome: the failing decision, the refusal, and whose fault it was.

    An abandoned game is not a loss. It is a game that stopped because its decision-maker could not
    produce a legal action, and the record says so instead of inventing a terminal state (FR-7.5).
    """

    request_id: str
    seat: PlayerId
    model: str
    provider: str
    failure: str
    attempts: int
    calls: int
    redo_budget: int
    final_rejection: Mapping[str, JsonValue] | None


@dataclass(frozen=True, slots=True)
class GameResult:
    """What one played game produced on disk."""

    game_id: GameId
    directory: Path
    manifest_path: Path
    sidecar_path: Path
    decisions: int
    actions: int
    completed: bool
    abandonment: Abandonment | None = None
    winner: PlayerId | None = None
    scores: Mapping[str, int] = field(default_factory=dict)
    model_seats: Mapping[PlayerId, str] = field(default_factory=dict)


async def run_game(
    *,
    game: str,
    config: RunConfig,
    directory: Path,
    run_id: str,
    requested_id: GameId | None = None,
    seats: Mapping[PlayerId, Agent],
    prompts: PromptSet,
    price_table: PriceTable,
    design: GameDesign | None = None,
    policy: TurnPolicy | None = None,
    context: ContextPolicy | None = None,
    render_detail: str = "full",
    clock: Callable[[], str] | None = None,
) -> GameResult:
    """Play one game to a verdict or an abandonment, and write its run directory.

    'requested_id' is the identity the *runner* wants the game to have; left out, the facade assigns
    one. An experiment names its games so that a directory, a record and a plan entry agree.
    """
    prompts.verify()
    plugin = get_game(game)
    budgets = policy or TurnPolicy()
    context_policy = context or ContextPolicy()
    manifest = build_manifest(
        game=plugin,
        config=config,
        run_id=run_id,
        seats=seats,
        prompts=prompts,
        price_table=price_table,
        policy=budgets,
        context=context_policy,
        design=design,
    )
    problems = validate_manifest(manifest)
    if problems:
        raise ManifestError("; ".join(problems))
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "run.json"
    manifest_path.write_text(to_canonical_json(manifest) + "\n", encoding="utf-8")

    facade = SessionFacade()
    game_id = facade.create_session(game, config, game_id=requested_id, directory=directory)
    sidecar = DecisionSidecar(decision_path(directory, game_id))
    accounting = RunAccounting(price_table)
    model_seats = {seat: spec.model for seat, spec in seats.items() if isinstance(spec, LlmAgent)}
    scripts = {
        seat: deque(spec.actions) for seat, spec in seats.items() if isinstance(spec, ScriptedAgent)
    }
    surfaces = {
        seat: FacadeSurface(
            facade,
            game,
            game_id,
            seat,
            refusal_view=lambda rejection: rejection_view(
                rejection, detail=config.rejection_detail
            ),
        )
        for seat, spec in seats.items()
        if isinstance(spec, LlmAgent)
    }
    turns = {
        seat: DecisionTurn(
            spec.provider,
            surfaces[seat],
            policy=budgets,
            redo=prompts.redo_text,
        )
        for seat, spec in seats.items()
        if isinstance(spec, LlmAgent)
    }
    context_builder = ContextBuilder(context_policy, game=plugin)
    seat_decisions: dict[PlayerId, int] = {}
    reference_decisions: dict[PlayerId, int] = {}
    now = _utc_now if clock is None else clock
    actions = 0
    decisions = 0
    attempted = 0
    try:
        while True:
            pending = facade.pending_decisions(game_id)
            if not pending:
                break
            decision = pending[0]
            seat = decision.player
            spec = seats.get(seat)
            if spec is None:
                raise GameAbortedError(f"seat {seat} has no agent")
            if isinstance(spec, ScriptedAgent):
                actions, attempted = _scripted(
                    facade,
                    game_id,
                    seat,
                    decision.request_id,
                    spec,
                    scripts[seat],
                    actions,
                    attempted,
                )
                continue
            if isinstance(spec, ReferenceAgent):
                actions, attempted = _reference(
                    facade,
                    game_id,
                    seat,
                    decision.request_id,
                    decision,
                    spec,
                    reference_decisions,
                    config.seed,
                    actions,
                    attempted,
                )
                continue
            if not isinstance(spec, LlmAgent):
                raise GameAbortedError(f"seat {seat} has an agent the runner cannot drive")
            state = facade.decision_surface(game_id, seat)
            observation = facade.projection(game_id, seat)
            messages = context_builder.messages(
                prompts,
                seat=seat,
                decision=seat_decisions.get(seat, 0),
                decision_surface=state,
                observation=observation,
            )
            seat_decisions[seat] = seat_decisions.get(seat, 0) + 1
            turn = await turns[seat].run(
                messages,
                CompletionConfig(model=spec.model, sampling=spec.sampling),
            )
            request_id = f"{game_id}-d{decisions + 1:04d}"
            entries = accounting.record_turn(turn, model=spec.model)
            if len(entries) != len(turn.attempts):
                raise GameError("the accounting and the attempts disagree about the call count")
            for entry, attempt in zip(entries, turn.attempts, strict=True):
                outcome = _turn_attempt_outcome(attempt, turn.action)
                seq = None
                if attempt.outcome in {AttemptOutcome.ACTION, AttemptOutcome.REJECTION}:
                    seq = attempted
                    attempted += 1
                sidecar.append(
                    build_decision_record(
                        game_id=game_id,
                        seat=seat,
                        model=spec.model,
                        provider=spec.provider_id,
                        request_id=request_id,
                        attempt=attempt,
                        outcome=outcome,
                        rejection=_rejection_of(attempt, config),
                        accounting=entry,
                        redo_budget=budgets.redo_budget,
                        at=now(),
                        host=socket.gethostname(),
                        pid=os.getpid(),
                        seq=seq,
                    )
                )
            decisions += 1
            if not turn.accepted:
                return _abandoned(
                    game_id=game_id,
                    directory=directory,
                    manifest_path=manifest_path,
                    sidecar=sidecar,
                    seat=seat,
                    request_id=request_id,
                    spec=spec,
                    turn=turn,
                    config=config,
                    policy=budgets,
                    actions=actions,
                    decisions=decisions,
                    model_seats=model_seats,
                    at=now(),
                )
            if turn.action is None or not isinstance(turn.action.arguments, Mapping):
                raise GameAbortedError(f"seat {seat} accepted no usable action")
            actions += 1
        final = facade.outcome(game_id)
        if final is None:
            raise GameAbortedError("the game stopped without a verdict")
        return GameResult(
            game_id=game_id,
            directory=directory,
            manifest_path=manifest_path,
            sidecar_path=sidecar.path,
            decisions=decisions,
            actions=actions,
            completed=True,
            winner=final.winner,
            scores=dict(final.scores),
            model_seats=model_seats,
        )
    finally:
        facade.end_session(game_id)


def _scripted(
    facade: SessionFacade,
    game_id: GameId,
    seat: PlayerId,
    request_id: str,
    spec: ScriptedAgent,
    script: deque[Action],
    actions: int,
    attempted: int,
) -> tuple[int, int]:
    """Answer one decision from a recorded list, refusing a script that ran out or was refused."""
    if not script:
        raise GameAbortedError(f"scripted seat {seat} ran out of actions")
    result = facade.submit_action(game_id, script.popleft(), request_id=request_id)
    if not isinstance(result, Applied):
        raise GameAbortedError(f"scripted seat {seat} was refused: {result.rejection.code.code}")
    return actions + 1, attempted + 1


def _reference(
    facade: SessionFacade,
    game_id: GameId,
    seat: PlayerId,
    request_id: str,
    decision: DecisionRequest,
    spec: ReferenceAgent,
    seen: dict[PlayerId, int],
    seed: int,
    actions: int,
    attempted: int,
) -> tuple[int, int]:
    """Ask a reference player for one of the game's own legal actions and submit it.

    The chooser is derived from the run's seed, the seat and the decision's ordinal, so a policy
    that draws is reproducible without the policy having to know anything about the run.

    A refusal aborts rather than abandons. Abandonment is what a *model* failure the redo budget
    could not rescue produces (FR-7.5); a reference player returning an illegal action is a defect
    in the harness, and recording it as a model's abandonment would blame the wrong thing.
    """
    ordinal = seen.get(seat, 0)
    seen[seat] = ordinal + 1
    snapshot = facade.snapshot(game_id)
    view = ReferenceView(
        game=snapshot.game,
        state=snapshot.state,
        seat=seat,
        request=decision,
        chooser=SeededRandomSource(
            _reference_seed(name=spec.name, run_seed=seed, seat=seat, ordinal=ordinal)
        ),
    )
    action = spec.player.choose(view)
    result = facade.submit_action(game_id, action, request_id=request_id)
    if not isinstance(result, Applied):
        raise GameAbortedError(
            f"reference seat {seat} ({spec.name}) chose an action the engine refused: "
            f"{result.rejection.code.code}"
        )
    return actions + 1, attempted + 1


def _reference_seed(*, name: str, run_seed: int, seat: PlayerId, ordinal: int) -> int:
    """A seed of its own, derived from the run's, so two runs of one design drive the same way."""
    text = f"{REFERENCE_SEED_LABEL}:{name}:{run_seed}:{seat}:{ordinal}".encode()
    return int(hashlib.sha256(text).hexdigest()[:12], 16)


def _abandoned(
    *,
    game_id: GameId,
    directory: Path,
    manifest_path: Path,
    sidecar: DecisionSidecar,
    seat: PlayerId,
    request_id: str,
    spec: LlmAgent,
    turn: TurnResult,
    config: RunConfig,
    policy: TurnPolicy,
    actions: int,
    decisions: int,
    model_seats: Mapping[PlayerId, str],
    at: str,
) -> GameResult:
    """Stop the game where it is, record why, and return an incomplete result (FR-7.5).

    The god log is closed without a terminal record; the sidecar gets one abandonment record
    naming the failing decision and the seat that failed. No outcome is invented, so an abandoned
    game stays distinguishable from a loss (FR-11.6).
    """
    last = turn.attempts[-1] if turn.attempts else None
    final_rejection = _rejection_of(last, config) if last is not None else None
    attempts = turn.redo_attempts
    calls = len(turn.attempts)
    failure = turn.failure or turn.outcome.value
    sidecar.append_abandonment(
        build_abandonment_record(
            game_id=game_id,
            request_id=request_id,
            seat=seat,
            model=spec.model,
            provider=spec.provider_id,
            attempts=attempts,
            calls=calls,
            redo_budget=policy.redo_budget,
            final_rejection=final_rejection,
            failure=failure,
            actions=actions,
            at=at,
            host=socket.gethostname(),
            pid=os.getpid(),
        )
    )
    return GameResult(
        game_id=game_id,
        directory=directory,
        manifest_path=manifest_path,
        sidecar_path=sidecar.path,
        decisions=decisions,
        actions=actions,
        completed=False,
        abandonment=Abandonment(
            request_id=request_id,
            seat=seat,
            model=spec.model,
            provider=spec.provider_id,
            failure=failure,
            attempts=attempts,
            calls=calls,
            redo_budget=policy.redo_budget,
            final_rejection=final_rejection,
        ),
        model_seats=model_seats,
    )


def _turn_attempt_outcome(attempt: Attempt, action: object) -> dict[str, JsonValue]:
    """What one recorded call produced, in the decision record's declared outcome shape."""
    if attempt.outcome is not AttemptOutcome.ACTION:
        return {"kind": attempt.outcome.value}
    if not isinstance(action, ToolCall) or not isinstance(action.arguments, Mapping):
        raise GameError("an accepted attempt carries no usable action")
    return {
        "kind": "action",
        "action": {"type": action.name, "params": dict(action.arguments)},
    }


def _rejection_of(attempt: Attempt, config: RunConfig) -> dict[str, JsonValue] | None:
    """The refusal this record carries: its own when refused, the prompting one when retried.

    The tier is the run's, not the engine's: the record stores which tier the player was shown, so
    an L0 redo and an L2 redo are distinguishable even though the engine's refusal is the same
    (FR-7.4).
    """
    number: int | None
    if attempt.outcome is AttemptOutcome.REJECTION:
        code, number = attempt.rejection, attempt.attempt
    else:
        code, number = attempt.prompted_by, attempt.prompted_by_attempt
    if code is None or number is None:
        return None
    return {"code": code, "detail": config.rejection_detail.value, "attempt": number}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


__all__: list[str] = [
    "DEFAULT_GAME_TIMEOUT_S",
    "Abandonment",
    "GameAbortedError",
    "GameError",
    "GameResult",
    "ManifestError",
    "run_game",
]
