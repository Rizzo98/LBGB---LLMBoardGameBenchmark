"""One game driven through the facade, the loop and the sidecar (K-022).

This is the smallest complete path from a model to a verifiable record: a game, a set of seats, the
generated surface, and one decision turn at a time. It is deliberately not the runner (K-027): there
is no experiment design, no concurrency and no results.json. What it does have is the property the
rest of the release depends on - every model decision is in the sidecar, with the exact messages it
was sent, and the god log remains the v1 record.

A seat is either a model or a script. A model seat owns a Provider and goes through the loop; a
scripted seat submits the next recorded action directly through the facade, through no model at all.
The manifest records which is which, so a scripted seat can never be mistaken for a scored one.

The sidecar is written after an action is accepted. The record's 'seq' is the number of accepted
actions before this one; in a clean game with no rejections that is the god-log seq, and the test
asserts it. Rejections and abandonment are K-023 and K-024's business, not a shape this driver
invents here.
"""

from __future__ import annotations

import os
import socket
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from lgbg import __version__
from lgbg.agents.accounting import RunAccounting
from lgbg.agents.loop import (
    Attempt,
    AttemptOutcome,
    DecisionTurn,
    TurnPolicy,
    TurnResult,
)
from lgbg.agents.pricing import PriceTable
from lgbg.agents.prompting import PromptSet
from lgbg.agents.providers.base import CompletionConfig, Provider, Sampling, ToolCall
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
from lgbg.core.contracts import MANIFEST_SCHEMA_NAME, validate_manifest
from lgbg.core.game import Applied, Game, get_game
from lgbg.core.types import Action, GameId, JsonValue, PlayerId
from lgbg.host.facade import SessionFacade

DEFAULT_GAME_TIMEOUT_S: Final[int] = 7200


class GameError(RuntimeError):
    """The game could not be driven to a completed verdict."""


class GameAbortedError(GameError):
    """The driver could not continue for a reason that is not the model's failure."""


class ManifestError(GameError):
    """The manifest this driver would write does not fit the frozen shape."""


@dataclass(frozen=True, slots=True)
class ModelSeat:
    """One seat played by a provider, with the identity the manifest records."""

    provider: Provider
    model: str
    provider_id: str
    provider_version: str
    sampling: Sampling = field(default_factory=Sampling)

    def __post_init__(self) -> None:
        if not self.model:
            raise ValueError("a model seat needs a model")
        if not self.provider_id or not self.provider_version:
            raise ValueError("a model seat needs a provider identity and version")


@dataclass(frozen=True, slots=True)
class ScriptedSeat:
    """One seat played from a recorded action list, never through a provider."""

    actions: Sequence[Action]

    def __post_init__(self) -> None:
        if not self.actions:
            raise ValueError("a scripted seat needs at least one action")


type Seat = ModelSeat | ScriptedSeat


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


async def play_game(
    *,
    game: str,
    config: RunConfig,
    directory: Path,
    run_id: str,
    seats: Mapping[PlayerId, Seat],
    prompts: PromptSet,
    price_table: PriceTable,
    policy: TurnPolicy | None = None,
    render_detail: str = "full",
    clock: Callable[[], str] | None = None,
) -> GameResult:
    """Play one game to completion, one decision at a time, and write its run directory."""
    prompts.verify()
    plugin = get_game(game)
    budgets = policy or TurnPolicy()
    manifest = build_manifest(
        game=plugin,
        config=config,
        run_id=run_id,
        seats=seats,
        prompts=prompts,
        price_table=price_table,
        policy=budgets,
    )
    problems = validate_manifest(manifest)
    if problems:
        raise ManifestError("; ".join(problems))
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "run.json"
    manifest_path.write_text(to_canonical_json(manifest) + "\n", encoding="utf-8")

    facade = SessionFacade()
    game_id = facade.create_session(game, config, directory=directory)
    sidecar = DecisionSidecar(decision_path(directory, game_id))
    accounting = RunAccounting(price_table)
    model_seats = {seat: spec.model for seat, spec in seats.items() if isinstance(spec, ModelSeat)}
    scripts = {
        seat: deque(spec.actions) for seat, spec in seats.items() if isinstance(spec, ScriptedSeat)
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
        if isinstance(spec, ModelSeat)
    }
    turns = {
        seat: DecisionTurn(
            spec.provider,
            surfaces[seat],
            policy=budgets,
            redo=prompts.redo_text,
        )
        for seat, spec in seats.items()
        if isinstance(spec, ModelSeat)
    }
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
            if isinstance(spec, ScriptedSeat):
                action = scripts[seat].popleft()
                result = facade.submit_action(game_id, action, request_id=decision.request_id)
                if not isinstance(result, Applied):
                    raise GameAbortedError(
                        f"scripted seat {seat} was refused: {result.rejection.code.code}"
                    )
                actions += 1
                attempted += 1
                continue
            state = facade.decision_surface(game_id, seat)
            messages = prompts.initial_messages(state)
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


def _abandoned(
    *,
    game_id: GameId,
    directory: Path,
    manifest_path: Path,
    sidecar: DecisionSidecar,
    seat: PlayerId,
    request_id: str,
    spec: ModelSeat,
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
    attempts = turn.redo_attempts if turn.redo_attempts else 1
    failure = turn.failure or turn.outcome.value
    sidecar.append_abandonment(
        build_abandonment_record(
            game_id=game_id,
            request_id=request_id,
            seat=seat,
            model=spec.model,
            provider=spec.provider_id,
            attempts=attempts,
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


def build_manifest(
    *,
    game: Game,
    config: RunConfig,
    run_id: str,
    seats: Mapping[PlayerId, Seat],
    prompts: PromptSet,
    price_table: PriceTable,
    policy: TurnPolicy,
) -> dict[str, JsonValue]:
    """The run.json this single-game driver writes, checked against K-002's shape."""
    game_config = dict(config.to_mapping().items())
    game_config.pop("prompt_hashes", None)
    initial = config.game_config.options.get("board")
    initial_configuration = initial if isinstance(initial, str) else "fixed:default"
    timeout = int(policy.decision_timeout_s)
    if timeout != policy.decision_timeout_s or timeout < 1:
        raise ManifestError("the manifest records decision_timeout_s as whole seconds, at least 1")
    seat_rows: list[JsonValue] = []
    for seat in range(config.players):
        spec = seats.get(seat)
        if spec is None:
            raise ManifestError(f"seat {seat} has no agent")
        if isinstance(spec, ModelSeat):
            seat_rows.append(
                {
                    "seat": seat,
                    "agent": "llm",
                    "player": None,
                    "model": spec.model,
                    "provider": spec.provider_id,
                    "sampling": spec.sampling.to_mapping(),
                }
            )
        else:
            seat_rows.append(
                {
                    "seat": seat,
                    "agent": "scripted",
                    "player": "scripted",
                    "model": None,
                    "provider": None,
                    "sampling": None,
                }
            )
    providers: list[JsonValue] = []
    seen: set[tuple[str, str]] = set()
    for spec in seats.values():
        if isinstance(spec, ModelSeat) and (spec.provider_id, spec.provider_version) not in seen:
            seen.add((spec.provider_id, spec.provider_version))
            providers.append({"id": spec.provider_id, "version": spec.provider_version})
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
        "design": {
            "seating": "fixed",
            "initial_configuration": initial_configuration,
            "configuration_scope": "per_experiment",
            "replicates": 1,
            "uncontrolled": [],
            "derivation": {
                "rule": "games = replicates x seatings",
                "replicates": 1,
                "seatings": 1,
                "games": 1,
            },
        },
        "policies": {
            "context": "full",
            "redo_budget": policy.redo_budget,
            "on_exhausted": "abandon_game",
            "step_budget": policy.step_budget,
            "decision_timeout_s": timeout,
            "game_timeout_s": DEFAULT_GAME_TIMEOUT_S,
            "budget_micro_usd": None,
        },
        "prompts": prompts.hashes(),
        "providers": providers,
        "price_table": price_table.to_mapping(),
    }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


__all__: list[str] = [
    "DEFAULT_GAME_TIMEOUT_S",
    "GameAbortedError",
    "GameError",
    "GameResult",
    "ManifestError",
    "ModelSeat",
    "ScriptedSeat",
    "Seat",
    "build_manifest",
    "play_game",
]
