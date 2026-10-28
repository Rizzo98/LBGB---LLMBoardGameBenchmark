"""Outcome aggregates over played games (PRD-v2 FR-7.5, FR-11.8).

This is the arithmetic behind results.json. `run_experiment` writes the whole artefact at the
run root: the experiment's axes and caveats, one line per game with its per-seat split, and the
per-model and per-seat totals. The one rule that matters most is that an abandoned game is not an
outcome. It is counted in its own column, per model, and it never enters a win or a loss. Folding it
in would reward a model that plays badly but legally over one that fails decisively, which is the
opposite of what the benchmark is for (PRD-v2 section 10.2).

v2 reports facts, not inferences: these are counts over games that happened, not a rating.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from lgbg.agents.sidecar import DecisionSidecar
from lgbg.core.contracts import RESULTS_SCHEMA_NAME
from lgbg.core.game import BenchmarkProfile
from lgbg.core.log import ActionRecord, GameLog, GameLogReader, god_log_path
from lgbg.core.types import JsonValue
from lgbg.runner.design import ExperimentDesign
from lgbg.runner.game import GameResult

RESULTS_FILENAME: Final[str] = "results.json"
"""What the experiment writes at its root: the design axes and the caveats they carry."""


class ResultsError(RuntimeError):
    """The results this run would write do not fit the declared shape."""


@dataclass(frozen=True, slots=True)
class ModelTally:
    """One model's games: finished outcomes and abandonments, kept apart on purpose."""

    model: str
    completed: int = 0
    wins: int = 0
    losses: int = 0
    abandoned: int = 0

    @property
    def games(self) -> int:
        return self.completed + self.abandoned

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "model": self.model,
            "games": self.games,
            "completed": self.completed,
            "wins": self.wins,
            "losses": self.losses,
            "abandoned": self.abandoned,
        }


@dataclass(frozen=True, slots=True)
class OutcomeSummary:
    """The run's outcomes: completed games only, with abandonments in their own row."""

    completed: int
    abandoned: int
    per_model: tuple[ModelTally, ...]

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "completed": self.completed,
            "abandoned": self.abandoned,
            "per_model": [row.to_mapping() for row in self.per_model],
        }


def summarise(results: Sequence[GameResult]) -> OutcomeSummary:
    """Count finished games and abandonments, per model, without mixing them.

    A completed game counts once for every model that held a seat in it, and a win is the model
    whose seat the game's winner names. An abandoned game counts once, for the model responsible,
    and not as a loss for anyone (FR-7.5, FR-11.8).
    """
    completed = 0
    abandoned = 0
    rows: dict[str, dict[str, int]] = {}

    def row(model: str) -> dict[str, int]:
        return rows.setdefault(model, {"completed": 0, "wins": 0, "losses": 0, "abandoned": 0})

    for result in results:
        if result.completed:
            completed += 1
            for seat, model in result.model_seats.items():
                counts = row(model)
                counts["completed"] += 1
                if result.winner == seat:
                    counts["wins"] += 1
                else:
                    counts["losses"] += 1
            continue
        abandoned += 1
        if result.abandonment is not None:
            row(result.abandonment.model)["abandoned"] += 1

    per_model = tuple(ModelTally(model=model, **counts) for model, counts in sorted(rows.items()))
    return OutcomeSummary(completed=completed, abandoned=abandoned, per_model=per_model)


def experiment_record(
    *,
    run_id: str,
    design: ExperimentDesign,
    profile: BenchmarkProfile,
    seats: int,
    derivation: Mapping[str, JsonValue],
    planned: int,
    completed: int,
    abandoned: int,
) -> dict[str, JsonValue]:
    """The experiment block of `results.json`, with every uncontrolled axis named (FR-11.12).

    The caveat is computed from the same declaration the matrix used, so it cannot drift from the
    games the run actually played: the axes are re-derived here from the plugin's profile rather
    than copied from whatever the caller remembered to pass.
    """
    return {
        "schema": RESULTS_SCHEMA_NAME,
        "run_id": run_id,
        "design": {
            "seating": design.seating,
            "initial_configuration": design.initial_configuration,
            "configuration_scope": design.configuration_scope,
            "replicates": design.replicates,
            "uncontrolled": list(design.uncontrolled(profile, seats)),
            "derivation": dict(derivation),
        },
        "summary": {
            "games": planned,
            "completed": completed,
            "abandoned": abandoned,
        },
    }


@dataclass(frozen=True, slots=True)
class SeatFacts:
    """One seat's line in one game: its outcome and everything the record knows it spent."""

    seat: int
    agent: str
    model: str | None
    player: str | None
    outcome: str | None
    place: int | None
    abandoned: bool
    actions: int
    rejections: Mapping[str, int]
    failures: Mapping[str, int]
    prompt_tokens: int
    completion_tokens: int
    cost_micro_usd: int
    latency_ms: int
    partial: bool

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "seat": self.seat,
            "agent": self.agent,
            "model": self.model,
            "player": self.player,
            "outcome": self.outcome,
            "place": self.place,
            "abandoned": self.abandoned,
            "actions": self.actions,
            "rejections_by_code": dict(self.rejections),
            "failures_by_kind": dict(self.failures),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "cost_micro_usd": self.cost_micro_usd,
            "latency_ms": self.latency_ms,
            "partial": self.partial,
        }


@dataclass(frozen=True, slots=True)
class GameFacts:
    """One game's line in results.json: the design point, the outcome and the per-seat split."""

    game_id: str
    design: Mapping[str, JsonValue]
    completed: bool
    outcome: Mapping[str, JsonValue] | None
    seats: tuple[SeatFacts, ...]
    actions: int
    rejections: Mapping[str, int]
    failures: Mapping[str, int]
    prompt_tokens: int
    completion_tokens: int
    cost_micro_usd: int
    latency_ms: int
    partial: bool
    abandonment: Mapping[str, JsonValue] | None

    def abandoned_seat(self) -> int | None:
        for seat in self.seats:
            if seat.abandoned:
                return seat.seat
        return None

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "game_id": self.game_id,
            "design": dict(self.design),
            "completed": self.completed,
            "outcome": None if self.outcome is None else dict(self.outcome),
            "actions": self.actions,
            "rejections_by_code": dict(self.rejections),
            "failures_by_kind": dict(self.failures),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "cost_micro_usd": self.cost_micro_usd,
            "latency_ms": self.latency_ms,
            "partial": self.partial,
            "abandonment": None if self.abandonment is None else dict(self.abandonment),
            "seats": [seat.to_mapping() for seat in self.seats],
        }


@dataclass(slots=True)
class _Tally:
    """The running totals behind one aggregate row. Not part of the artefact."""

    games: int = 0
    completed: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    abandoned: int = 0
    actions: int = 0
    rejections: dict[str, int] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_micro_usd: int = 0
    latency_ms: int = 0
    partial: bool = False
    place_counts: dict[int, int] = field(default_factory=dict)
    seat_counts: dict[int, int] = field(default_factory=dict)
    agents: set[str] = field(default_factory=set)
    models: set[str] = field(default_factory=set)


def _merge(target: dict[str, int], source: Mapping[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + value


def _add_seats(tally: _Tally, seats: Sequence[SeatFacts]) -> None:
    for seat in seats:
        tally.actions += seat.actions
        _merge(tally.rejections, seat.rejections)
        _merge(tally.failures, seat.failures)
        tally.prompt_tokens += seat.prompt_tokens
        tally.completion_tokens += seat.completion_tokens
        tally.cost_micro_usd += seat.cost_micro_usd
        tally.latency_ms += seat.latency_ms
        tally.partial = tally.partial or seat.partial
        tally.agents.add(seat.agent)
        if seat.model is not None:
            tally.models.add(seat.model)


def _tally_row(tally: _Tally) -> dict[str, JsonValue]:
    return {
        "games": tally.games,
        "completed": tally.completed,
        "wins": tally.wins,
        "losses": tally.losses,
        "draws": tally.draws,
        "abandoned": tally.abandoned,
        "actions": tally.actions,
        "rejections": sum(tally.rejections.values()),
        "rejections_by_code": dict(sorted(tally.rejections.items())),
        "failures": sum(tally.failures.values()),
        "failures_by_kind": dict(sorted(tally.failures.items())),
        "prompt_tokens": tally.prompt_tokens,
        "completion_tokens": tally.completion_tokens,
        "total_tokens": tally.prompt_tokens + tally.completion_tokens,
        "cost_micro_usd": tally.cost_micro_usd,
        "latency_ms": tally.latency_ms,
        "partial": tally.partial,
        "place_counts": [
            {"place": place, "games": count} for place, count in sorted(tally.place_counts.items())
        ],
        "seat_counts": [
            {"seat": seat, "games": count} for seat, count in sorted(tally.seat_counts.items())
        ],
    }


def _rejections(records: Sequence[ActionRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        if record.result.get("ok") is True:
            continue
        code = record.result.get("error")
        key = str(code) if code is not None else "UNKNOWN"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _failures(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        failure = record.get("failure")
        if isinstance(failure, str) and failure:
            counts[failure] = counts.get(failure, 0) + 1
    return dict(sorted(counts.items()))


def _usage(records: Sequence[Mapping[str, Any]]) -> tuple[int, int, int, int, bool]:
    prompt = 0
    completion = 0
    cost = 0
    latency = 0
    partial = False
    for record in records:
        usage = record.get("usage")
        if isinstance(usage, Mapping):
            prompt += int(usage.get("prompt_tokens", 0))
            completion += int(usage.get("completion_tokens", 0))
        else:
            partial = True
        micro = record.get("cost_micro_usd")
        if isinstance(micro, int) and not isinstance(micro, bool):
            cost += micro
        else:
            partial = True
        milliseconds = record.get("latency_ms")
        if isinstance(milliseconds, int) and not isinstance(milliseconds, bool):
            latency += milliseconds
    return prompt, completion, cost, latency, partial


def _outcome(log: GameLog, game: GameResult) -> dict[str, JsonValue] | None:
    if not game.completed:
        return None
    terminal = log.terminal
    if terminal is not None:
        return {
            "winner": terminal.winner,
            "scores": dict(terminal.final_scores),
            "rounds": terminal.rounds,
        }
    return {"winner": game.winner, "scores": dict(game.scores), "rounds": None}


def _places(outcome: Mapping[str, JsonValue] | None, players: int) -> dict[int, int | None]:
    places: dict[int, int | None] = dict.fromkeys(range(players))
    if outcome is None:
        return places
    scores = outcome.get("scores")
    numeric: dict[int, int] = {}
    if isinstance(scores, Mapping):
        for key, value in scores.items():
            try:
                seat = int(key)
            except (TypeError, ValueError):
                continue
            if isinstance(value, int) and not isinstance(value, bool):
                numeric[seat] = value
    if numeric:
        for seat, score in numeric.items():
            places[seat] = 1 + sum(1 for other in numeric.values() if other > score)
        return places
    winner = outcome.get("winner")
    if isinstance(winner, int) and not isinstance(winner, bool):
        places[winner] = 1
    return places


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _abandonment_of(game: GameResult) -> dict[str, JsonValue] | None:
    abandonment = game.abandonment
    if abandonment is None:
        return None
    return {
        "seat": abandonment.seat,
        "model": abandonment.model,
        "provider": abandonment.provider,
        "request_id": abandonment.request_id,
        "failure": abandonment.failure,
        "attempts": abandonment.attempts,
        "calls": abandonment.calls,
        "redo_budget": abandonment.redo_budget,
        "final_rejection": (
            None if abandonment.final_rejection is None else dict(abandonment.final_rejection)
        ),
        "actions": game.actions,
    }


def _game_facts(game: GameResult) -> GameFacts:
    """Read one game's artefacts and turn them into the line results.json records."""
    log = GameLogReader(god_log_path(game.directory, game.game_id)).read()
    sidecar = DecisionSidecar(game.sidecar_path).records()
    manifest: dict[str, Any] = json.loads(game.manifest_path.read_text(encoding="utf-8"))
    decisions = [record for record in sidecar if record.get("t") == "decision"]
    seat_rows = manifest.get("seats")
    specs: dict[int, dict[str, Any]] = {}
    if isinstance(seat_rows, list):
        for row in seat_rows:
            if isinstance(row, dict):
                seat = _int_or_none(row.get("seat"))
                if seat is not None:
                    specs[seat] = row
    config = manifest.get("config")
    players = 0
    if isinstance(config, Mapping):
        value = _int_or_none(config.get("players"))
        players = 0 if value is None else value
    if players <= 0:
        players = max(specs, default=-1) + 1
    outcome = _outcome(log, game)
    places = _places(outcome, players)
    winner = None if outcome is None else _int_or_none(outcome.get("winner"))
    abandonment = _abandonment_of(game)
    abandoned_seat = None if abandonment is None else _int_or_none(abandonment.get("seat"))
    seats: list[SeatFacts] = []
    for seat in range(players):
        spec = specs.get(seat, {})
        mine = [record for record in decisions if _int_or_none(record.get("seat")) == seat]
        seat_actions = [record for record in log.actions if record.player == seat]
        prompt, completion, cost, latency, partial = _usage(mine)
        if not game.completed:
            seat_outcome = None
        elif winner is None:
            seat_outcome = "draw"
        else:
            seat_outcome = "win" if winner == seat else "loss"
        agent = spec.get("agent")
        if not isinstance(agent, str):
            agent = "llm" if seat in game.model_seats else "unknown"
        model = spec.get("model")
        if not isinstance(model, str):
            model = game.model_seats.get(seat)
        player = spec.get("player")
        seats.append(
            SeatFacts(
                seat=seat,
                agent=agent,
                model=model,
                player=player if isinstance(player, str) else None,
                outcome=seat_outcome,
                place=places.get(seat),
                abandoned=abandoned_seat == seat,
                actions=sum(1 for record in seat_actions if record.result.get("ok") is True),
                rejections=_rejections(seat_actions),
                failures=_failures(mine),
                prompt_tokens=prompt,
                completion_tokens=completion,
                cost_micro_usd=cost,
                latency_ms=latency,
                partial=partial,
            )
        )
    prompt, completion, cost, latency, partial = _usage(decisions)
    design = manifest.get("design")
    return GameFacts(
        game_id=game.game_id,
        design=dict(design) if isinstance(design, Mapping) else {},
        completed=game.completed,
        outcome=outcome,
        seats=tuple(seats),
        actions=sum(1 for record in log.actions if record.result.get("ok") is True),
        rejections=_rejections(log.actions),
        failures=_failures(decisions),
        prompt_tokens=prompt,
        completion_tokens=completion,
        cost_micro_usd=cost,
        latency_ms=latency,
        partial=partial,
        abandonment=abandonment,
    )


def _summary(games: Sequence[GameFacts]) -> dict[str, JsonValue]:
    rejections: dict[str, int] = {}
    failures: dict[str, int] = {}
    prompt = 0
    completion = 0
    cost = 0
    latency = 0
    partial = False
    for game in games:
        _merge(rejections, game.rejections)
        _merge(failures, game.failures)
        prompt += game.prompt_tokens
        completion += game.completion_tokens
        cost += game.cost_micro_usd
        latency += game.latency_ms
        partial = partial or game.partial
    return {
        "games": len(games),
        "completed": sum(1 for game in games if game.completed),
        "abandoned": sum(1 for game in games if not game.completed),
        "actions": sum(game.actions for game in games),
        "rejections": sum(rejections.values()),
        "rejections_by_code": dict(sorted(rejections.items())),
        "failures": sum(failures.values()),
        "failures_by_kind": dict(sorted(failures.items())),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "cost_micro_usd": cost,
        "latency_ms": latency,
        "partial": partial,
    }


def _model_rows(games: Sequence[GameFacts]) -> list[dict[str, JsonValue]]:
    tallies: dict[str, _Tally] = {}
    for game in games:
        if game.completed:
            by_model: dict[str, list[SeatFacts]] = {}
            for seat in game.seats:
                if seat.agent == "llm" and seat.model is not None:
                    by_model.setdefault(seat.model, []).append(seat)
            winner = None if game.outcome is None else _int_or_none(game.outcome.get("winner"))
            winner_model = None
            if winner is not None and 0 <= winner < len(game.seats):
                winning = game.seats[winner]
                if winning.agent == "llm":
                    winner_model = winning.model
            for model, seats in sorted(by_model.items()):
                tally = tallies.setdefault(model, _Tally())
                tally.games += 1
                tally.completed += 1
                if winner is None:
                    tally.draws += 1
                elif winner_model == model:
                    tally.wins += 1
                else:
                    tally.losses += 1
                _add_seats(tally, seats)
                best = min(
                    (seat.place for seat in seats if seat.place is not None),
                    default=None,
                )
                if best is not None:
                    tally.place_counts[best] = tally.place_counts.get(best, 0) + 1
                for seat in seats:
                    tally.seat_counts[seat.seat] = tally.seat_counts.get(seat.seat, 0) + 1
            continue
        abandoned = game.abandoned_seat()
        if abandoned is None or abandoned >= len(game.seats):
            continue
        seat = game.seats[abandoned]
        if seat.agent != "llm" or seat.model is None:
            continue
        tally = tallies.setdefault(seat.model, _Tally())
        tally.games += 1
        tally.abandoned += 1
        _add_seats(tally, [seat])
        tally.seat_counts[seat.seat] = tally.seat_counts.get(seat.seat, 0) + 1
    rows: list[dict[str, JsonValue]] = []
    for model, tally in sorted(tallies.items()):
        row: dict[str, JsonValue] = {"model": model, **_tally_row(tally)}
        rows.append(row)
    return rows


def _seat_rows(games: Sequence[GameFacts]) -> list[dict[str, JsonValue]]:
    tallies: dict[int, _Tally] = {}
    for game in games:
        if game.completed:
            seats = game.seats
        else:
            abandoned = game.abandoned_seat()
            seats = () if abandoned is None else (game.seats[abandoned],)
        for seat in seats:
            tally = tallies.setdefault(seat.seat, _Tally())
            tally.games += 1
            if game.completed:
                tally.completed += 1
                if seat.outcome == "win":
                    tally.wins += 1
                elif seat.outcome == "loss":
                    tally.losses += 1
                elif seat.outcome == "draw":
                    tally.draws += 1
                if seat.place is not None:
                    tally.place_counts[seat.place] = tally.place_counts.get(seat.place, 0) + 1
            else:
                tally.abandoned += 1
            _add_seats(tally, [seat])
    rows: list[dict[str, JsonValue]] = []
    for seat_index, tally in sorted(tallies.items()):
        if "llm" not in tally.agents:
            # Reference and scripted seats are test infrastructure, never a scored row
            # (FR-11.1). Their per-game detail remains in the game line above.
            continue
        row: dict[str, JsonValue] = {
            "seat": seat_index,
            "agents": sorted(tally.agents),
            "models": sorted(tally.models),
            **_tally_row(tally),
        }
        rows.append(row)
    return rows


def experiment_results(
    *,
    run_id: str,
    design: ExperimentDesign,
    profile: BenchmarkProfile,
    seats: int,
    derivation: Mapping[str, JsonValue],
    games: Sequence[GameResult],
) -> dict[str, JsonValue]:
    """The whole results.json: the design caveat, every game, and the per-model/per-seat totals."""
    facts = tuple(_game_facts(game) for game in games)
    payload = experiment_record(
        run_id=run_id,
        design=design,
        profile=profile,
        seats=seats,
        derivation=derivation,
        planned=len(facts),
        completed=sum(1 for game in facts if game.completed),
        abandoned=sum(1 for game in facts if not game.completed),
    )
    payload["summary"] = _summary(facts)
    payload["games"] = [game.to_mapping() for game in facts]
    payload["per_model"] = _model_rows(facts)
    payload["per_seat"] = _seat_rows(facts)
    return payload


__all__: Final[list[str]] = [
    "RESULTS_FILENAME",
    "RESULTS_SCHEMA_NAME",
    "GameFacts",
    "ModelTally",
    "OutcomeSummary",
    "ResultsError",
    "SeatFacts",
    "experiment_record",
    "experiment_results",
    "summarise",
]
