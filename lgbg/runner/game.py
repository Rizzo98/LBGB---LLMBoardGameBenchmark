"""One game played by the runner: every seat an agent, every action through the facade (K-027).

This is the smallest complete path from a table of agents to a verifiable record. The runner owns
the seat-to-agent mapping (FR-11.1) and the run manifest (FR-10.1); it owns no game fact. It asks
the plugin registry for the game by name, drives the facade, and writes down what happened.

The three kinds of seat play differently and are recorded the same way:

- an **LLM agent** goes through the provider-agnostic loop. Every provider call becomes a decision
  record in the sidecar, with the exact messages it was sent, and the run's price table accounts
  for it (FR-10.3, FR-13.1).
- a **reference player** is test infrastructure, asked for one of the game's own legal actions. It
  costs a decision, not a call, so it is counted in the god log and nowhere in the sidecar. It is
  never scored and never part of a comparison (FR-11.1).
- a **scripted agent** submits its recorded actions directly. It is how a fixture plays a seat with
  no agent at all, and the manifest says so.

**That the game runs entirely through the facade** is the property this slice adds. Reading the
position for a reference player is the facade's `snapshot` and submitting an action is its
`submit_action`; the runner never applies a rule itself and never keeps a second copy of the game.

**A game ends one of two ways, and the record says which.** A completed game has a terminal record
in the god log and a verdict. An abandoned game has no terminal record and one `abandonment` line
in the sidecar naming the decision, the seat and the model that failed (FR-7.5, FR-11.6). No
synthetic winner is ever written, so an abandoned game stays distinguishable from a loss.

**Concurrent decisions are dispatched together and applied in order.** The batch is the set
of requests the game has open at one moment. Every model call starts before the first answer is
applied, and each action waits on a gate that opens only when every earlier request in the game's
declared resolution order has been recorded. A decision's reads are frozen at the batch boundary, so
it sees the position it was opened in rather than the effects of the seat before it (FR-11.2,
NFR-2).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import socket
from collections import deque
from collections.abc import Callable, Mapping, Sequence
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
from lgbg.agents.providers.base import CompletionConfig, Message, ToolCall
from lgbg.agents.sidecar import (
    DecisionSidecar,
    build_abandonment_record,
    build_decision_record,
    decision_path,
)
from lgbg.agents.surface import FacadeSurface, SurfaceView, decisions_payload
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


@dataclass(slots=True)
class _PreparedDecision:
    """One open decision, ready to answer: its gate, its model turn, or its script.

    The gate is what separates dispatch from application. The model call may start as soon as the
    batch is prepared; the action it produces waits here until every earlier decision in the game's
    resolution order has been applied (FR-11.2).
    """

    decision: DecisionRequest
    seat: PlayerId
    spec: Agent
    gate: asyncio.Event = field(default_factory=asyncio.Event)
    started: asyncio.Event = field(default_factory=asyncio.Event)
    turn: DecisionTurn | None = None
    messages: tuple[Message, ...] = ()
    completion: CompletionConfig | None = None
    script: deque[Action] | None = None


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
    concurrent: bool = True,
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
    context_builder = ContextBuilder(context_policy, game=plugin)
    seat_decisions: dict[PlayerId, int] = {}
    reference_decisions: dict[PlayerId, int] = {}
    now = _utc_now if clock is None else clock
    actions = 0
    decisions = 0
    attempted = 0

    def prepare(decision: DecisionRequest, pending: Sequence[DecisionRequest]) -> _PreparedDecision:
        """Ready one open decision for dispatch, without applying anything yet.

        An LLM decision gets the reads it may make frozen at this boundary and a surface whose
        action path waits on the decision's gate. A reference player gets its snapshot here too,
        before any of the batch has moved. A scripted seat only needs its list.
        """
        seat = decision.player
        spec = seats.get(seat)
        if spec is None:
            raise GameAbortedError(f"seat {seat} has no agent")
        prepared = _PreparedDecision(decision=decision, seat=seat, spec=spec)
        if isinstance(spec, ScriptedAgent):
            prepared.script = scripts[seat]
            return prepared
        if isinstance(spec, ReferenceAgent):
            return prepared
        if not isinstance(spec, LlmAgent):
            raise GameAbortedError(f"seat {seat} has an agent the runner cannot drive")
        observation = facade.projection(game_id, seat)
        decision_surface = facade.decision_surface(game_id, seat)
        view = SurfaceView(
            observation=observation,
            decision_surface=decision_surface,
            decisions=decisions_payload(pending, seat),
        )
        messages = context_builder.messages(
            prompts,
            seat=seat,
            decision=seat_decisions.get(seat, 0),
            decision_surface=decision_surface,
            observation=observation,
        )
        seat_decisions[seat] = seat_decisions.get(seat, 0) + 1
        surface = FacadeSurface(
            facade,
            game,
            game_id,
            seat,
            refusal_view=lambda rejection: rejection_view(
                rejection, detail=config.rejection_detail
            ),
            request_id=decision.request_id,
            act_gate=prepared.gate.wait,
            view=view,
        )
        prepared.turn = DecisionTurn(
            spec.provider,
            surface,
            policy=budgets,
            redo=prompts.redo_text,
        )
        prepared.messages = tuple(messages)
        prepared.completion = CompletionConfig(model=spec.model, sampling=spec.sampling)
        return prepared

    async def run(prepared: _PreparedDecision) -> TurnResult | None:
        """Ask the decision's agent, and submit only when its gate opens.

        The agent call runs before the gate: that is the whole point of the batch. The submission
        waits, so the engine sees the batch in its declared resolution order rather than in the
        order the models happened to answer (FR-11.2).
        """
        prepared.started.set()
        if prepared.script is not None:
            if not prepared.script:
                raise GameAbortedError(f"scripted seat {prepared.seat} ran out of actions")
            action = prepared.script.popleft()
            await prepared.gate.wait()
            result = facade.submit_action(game_id, action, request_id=prepared.decision.request_id)
            if not isinstance(result, Applied):
                raise GameAbortedError(
                    f"scripted seat {prepared.seat} was refused: {result.rejection.code.code}"
                )
            return None
        if prepared.turn is not None:
            if prepared.completion is None:
                raise GameError("an LLM decision was prepared without a completion config")
            return await prepared.turn.run(prepared.messages, prepared.completion)
        spec = prepared.spec
        if not isinstance(spec, ReferenceAgent):
            raise GameAbortedError(f"seat {prepared.seat} has an agent the runner cannot drive")
        action = _reference_action(
            facade,
            game_id,
            prepared.seat,
            prepared.decision,
            spec,
            reference_decisions,
            config.seed,
        )
        await prepared.gate.wait()
        result = facade.submit_action(game_id, action, request_id=prepared.decision.request_id)
        if not isinstance(result, Applied):
            raise GameAbortedError(
                f"reference seat {prepared.seat} ({spec.name}) chose an action the engine "
                f"refused: {result.rejection.code.code}"
            )
        return None

    def record(
        prepared: _PreparedDecision, turn: TurnResult | None
    ) -> tuple[LlmAgent, TurnResult, str] | None:
        """Write what one decision produced, in resolution order, and count it.

        Returns the failing turn when the model could not produce an action, so the caller can
        stop the game after everything this decision wrote is on disk. Scripted and reference
        decisions have no sidecar records: their action is already in the god log.
        """
        nonlocal actions, decisions, attempted
        if turn is None:
            actions += 1
            attempted += 1
            return None
        spec = prepared.spec
        if not isinstance(spec, LlmAgent):
            raise GameError("a model turn belongs to a seat that is not an LLM agent")
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
                    seat=prepared.seat,
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
            return spec, turn, request_id
        if turn.action is None or not isinstance(turn.action.arguments, Mapping):
            raise GameAbortedError(f"seat {prepared.seat} accepted no usable action")
        actions += 1
        return None

    try:
        while True:
            pending = facade.pending_decisions(game_id)
            if not pending:
                break
            if concurrent and len(pending) > 1:
                prepared = [prepare(decision, pending) for decision in pending]
                tasks = [asyncio.create_task(run(item)) for item in prepared]
                await asyncio.gather(*(item.started.wait() for item in prepared))
                try:
                    for index, item in enumerate(prepared):
                        still_open = {
                            request.request_id for request in facade.pending_decisions(game_id)
                        }
                        if item.decision.request_id not in still_open:
                            # An earlier decision in this batch closed this request. A serial
                            # runner would never have asked it, so the speculative answer is
                            # discarded rather than submitted into a decision that is gone.
                            await _cancel([tasks[index]])
                            continue
                        item.gate.set()
                        try:
                            turn = await tasks[index]
                        except BaseException:
                            await _cancel(tasks[index + 1 :])
                            raise
                        abandoned = record(item, turn)
                        if abandoned is None:
                            continue
                        await _cancel(tasks[index + 1 :])
                        spec, failed_turn, request_id = abandoned
                        return _abandoned(
                            game_id=game_id,
                            directory=directory,
                            manifest_path=manifest_path,
                            sidecar=sidecar,
                            seat=item.seat,
                            request_id=request_id,
                            spec=spec,
                            turn=failed_turn,
                            config=config,
                            policy=budgets,
                            actions=actions,
                            decisions=decisions,
                            model_seats=model_seats,
                            at=now(),
                        )
                finally:
                    await _cancel(tasks)
                continue
            item = prepare(pending[0], pending)
            item.gate.set()
            task = asyncio.create_task(run(item))
            try:
                turn = await task
            except BaseException:
                task.cancel()
                raise
            abandoned = record(item, turn)
            if abandoned is None:
                continue
            spec, failed_turn, request_id = abandoned
            return _abandoned(
                game_id=game_id,
                directory=directory,
                manifest_path=manifest_path,
                sidecar=sidecar,
                seat=item.seat,
                request_id=request_id,
                spec=spec,
                turn=failed_turn,
                config=config,
                policy=budgets,
                actions=actions,
                decisions=decisions,
                model_seats=model_seats,
                at=now(),
            )
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


def _reference_action(
    facade: SessionFacade,
    game_id: GameId,
    seat: PlayerId,
    decision: DecisionRequest,
    spec: ReferenceAgent,
    seen: dict[PlayerId, int],
    seed: int,
) -> Action:
    """Ask a reference player for one of the game's own legal actions, without submitting it.

    The chooser is derived from the run's seed, the seat and the decision's ordinal, so a policy
    that draws is reproducible without the policy having to know anything about the run. Choosing
    here, before the decision's gate opens, is what makes a concurrent reference seat see the
    batch boundary rather than the answers of the seats before it.
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
    return spec.player.choose(view)


async def _cancel(tasks: list[asyncio.Task[TurnResult | None]]) -> None:
    """Stop decisions that were dispatched but whose turn never came, and reap their errors."""
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


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
