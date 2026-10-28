"""The run config file: what an operator declares before a line is played (PRD-v2 FR-14.2).

The file is the operator's interface to the runner, and it is deliberately the same shape the PRD
declares (section 11.2): a game, a run configuration, a table of seats, an experiment design and
the policy values. This module reads it, refuses a declaration that cannot be carried out, and
builds the agents the runner takes. It names no game: the game arrives as a registered name and
its own options travel opaquely in 'config'.

**Two providers exist, and only one is a model.** 'openrouter' is the real gateway, reached with
the key in the environment and priced from the gateway's own listing. 'mock' is the provider the
suite drives: its behaviour is a declared word and its correct-play script is the actions it is
given. A mock run costs nothing, which is why a campaign can be fifty games in CI (SC-12), and its
prices are recorded like any other run's.

**A run file cannot lie about its table.** Every seat of the configuration has exactly one agent,
the provider is the same for every seat, and every model has a price before the run starts. A
missing price would otherwise surface in the middle of a game as an accounting failure, which is
exactly the kind of thing an unattended run must decide in advance.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx

from lgbg.agents.context import ContextError, ContextPolicy, ContextStrategy
from lgbg.agents.loop import TurnPolicy
from lgbg.agents.pricing import PRICE_UNIT, ModelPrice, PriceTable
from lgbg.agents.prompting import PromptError, PromptSet
from lgbg.agents.providers import mock, openrouter
from lgbg.agents.providers.base import Sampling, ToolCall
from lgbg.agents.providers.mock import Behaviour, MockProvider
from lgbg.agents.providers.openrouter import OpenRouterProvider
from lgbg.core.config import ConfigError, RunConfig
from lgbg.core.types import JsonValue
from lgbg.runner.agents import Agent, LlmAgent
from lgbg.runner.design import ExperimentDesign
from lgbg.runner.experiment import ExperimentResult, run_experiment

MOCK_PROVIDER: Final[str] = mock.NAME
OPENROUTER_PROVIDER: Final[str] = openrouter.NAME
PROVIDERS: Final[tuple[str, ...]] = (MOCK_PROVIDER, OPENROUTER_PROVIDER)
"""The provider identities a run file may name. A new adapter adds itself here, once."""

OPENROUTER_KEY_VARIABLE: Final[str] = "OPENROUTER_API_KEY"
OPENROUTER_BASE_VARIABLE: Final[str] = "OPENROUTER_BASE_URL"
"""Where the real provider's credential and optional base URL come from. Never recorded."""

_SEAT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "seat",
        "agent",
        "model",
        "provider",
        "temperature",
        "top_p",
        "seed",
        "behaviour",
        "actions",
    }
)
_DESIGN_KEYS: Final[frozenset[str]] = frozenset(
    {"seating", "initial_configuration", "configuration_scope", "replicates"}
)
_POLICY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "context",
        "context_refresh_every",
        "context_window",
        "redo_budget",
        "on_exhausted",
        "step_budget",
        "decision_timeout_s",
    }
)
_FILE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "game",
        "config",
        "seats",
        "design",
        "policies",
        "prompts",
        "prices",
        "run_id",
        "out",
        "concurrency",
    }
)


@dataclass(frozen=True, slots=True)
class SeatSpec:
    """One declared seat: a model, its provider and the sampling it is played with."""

    seat: int
    model: str
    provider: str
    behaviour: str | None
    actions: tuple[ToolCall, ...]
    sampling: Sampling


@dataclass(frozen=True, slots=True)
class RunFile:
    """One parsed run declaration: everything the runner needs before it starts."""

    path: Path
    game: str
    config: RunConfig
    seats: tuple[SeatSpec, ...]
    design: ExperimentDesign | None
    policy: TurnPolicy
    context: ContextPolicy
    game_prompt: Path | None
    prices: tuple[ModelPrice, ...]
    run_id: str | None
    out: Path | None
    concurrency: int


def load_run_file(path: Path) -> RunFile:
    """Read and validate one run file, naming the field that is wrong."""
    raw = _read_json(path)
    _only(raw, _FILE_KEYS, "the run file")

    game = _string(raw, "game", "the run file")
    seats = _seats(_list(raw, "seats", "the run file"))
    if not seats:
        raise ConfigError("the run file declares no seats")
    _same_provider(seats)
    _provider_declarations(seats, raw)
    config = _config(raw.get("config", {}), seats)
    design = _design(raw.get("design"))
    policy, context = _policies(raw.get("policies", {}))
    prices = _prices(raw.get("prices"), seats)
    game_prompt = _game_prompt(path, raw.get("prompts"))
    run_id = _optional_string(raw, "run_id", "the run file")
    out = _optional_string(raw, "out", "the run file")
    concurrency = raw.get("concurrency", 1)
    if not isinstance(concurrency, int) or isinstance(concurrency, bool) or concurrency < 1:
        raise ConfigError(f"concurrency must be a positive integer, got {concurrency!r}")
    return RunFile(
        path=path,
        game=game,
        config=config,
        seats=seats,
        design=design,
        policy=policy,
        context=context,
        game_prompt=game_prompt,
        prices=prices,
        run_id=run_id,
        out=None if out is None else Path(out),
        concurrency=concurrency,
    )


def run_from_file(
    path: Path,
    *,
    out: Path | None = None,
    run_id: str | None = None,
    concurrency: int | None = None,
) -> ExperimentResult:
    """Play the declared run and write its directory. The command line's whole job."""
    parsed = load_run_file(path)
    root = out if out is not None else parsed.out
    if root is None:
        raise ConfigError("the run file declares no 'out' directory and --out was not given")
    identity = run_id if run_id is not None else (parsed.run_id or path.stem)
    limit = parsed.concurrency if concurrency is None else concurrency
    if limit < 1:
        raise ConfigError("--concurrency must be at least 1")
    return asyncio.run(_execute(parsed, root=root, run_id=identity, concurrency=limit))


async def _execute(
    parsed: RunFile, *, root: Path, run_id: str, concurrency: int
) -> ExperimentResult:
    """Build the provider, play the experiment and hand back what it wrote."""
    prompts = _prompts(parsed)
    if parsed.seats[0].provider == MOCK_PROVIDER:
        agents: tuple[Agent, ...] = tuple(_mock_agent(spec) for spec in parsed.seats)
        return await _play(parsed, root, run_id, concurrency, prompts, agents, _price_table(parsed))
    if parsed.seats[0].provider != OPENROUTER_PROVIDER:
        raise ConfigError(f"provider {parsed.seats[0].provider!r} is not one of {list(PROVIDERS)}")
    key = os.environ.get(OPENROUTER_KEY_VARIABLE, "")
    if not key:
        raise ConfigError(f"{OPENROUTER_KEY_VARIABLE} is not set, so the gateway cannot be asked")
    base_url = os.environ.get(OPENROUTER_BASE_VARIABLE, openrouter.DEFAULT_BASE_URL)
    async with httpx.AsyncClient(timeout=120) as client:
        provider = OpenRouterProvider(client, api_key=key, base_url=base_url)
        models = tuple(dict.fromkeys(spec.model for spec in parsed.seats))
        prices = await provider.read_pricing(models)
        real: tuple[Agent, ...] = tuple(
            LlmAgent(
                provider=provider,
                model=spec.model,
                provider_id=openrouter.NAME,
                provider_version=openrouter.VERSION,
                sampling=spec.sampling,
            )
            for spec in parsed.seats
        )
        return await _play(parsed, root, run_id, concurrency, prompts, real, prices)


async def _play(
    parsed: RunFile,
    root: Path,
    run_id: str,
    concurrency: int,
    prompts: PromptSet,
    agents: tuple[Agent, ...],
    price_table: PriceTable,
) -> ExperimentResult:
    return await run_experiment(
        game=parsed.game,
        config=parsed.config,
        root=root,
        run_id=run_id,
        seats=agents,
        prompts=prompts,
        price_table=price_table,
        design=parsed.design,
        policy=parsed.policy,
        context=parsed.context,
        max_concurrent_games=concurrency,
    )


def _mock_agent(spec: SeatSpec) -> LlmAgent:
    """One seat played by the mock, with the behaviour its declaration names."""
    try:
        behaviour = Behaviour(spec.behaviour or Behaviour.CORRECT_PLAY.value)
        provider = MockProvider(behaviour, actions=spec.actions)
    except ValueError as error:
        raise ConfigError(f"seat {spec.seat}: {error}") from None
    return LlmAgent(
        provider=provider,
        model=spec.model,
        provider_id=mock.NAME,
        provider_version=mock.VERSION,
        sampling=spec.sampling,
    )


def _prompts(parsed: RunFile) -> PromptSet:
    try:
        return PromptSet.load(parsed.game, game_prompt=parsed.game_prompt)
    except PromptError as error:
        raise ConfigError(str(error)) from None


def _price_table(parsed: RunFile) -> PriceTable:
    """The run's price table, with a mock model free only because it has no gateway to pay."""
    declared = {price.model: price for price in parsed.prices}
    models: list[ModelPrice] = []
    seen: set[str] = set()
    for spec in parsed.seats:
        if spec.model in seen:
            continue
        seen.add(spec.model)
        price = declared.get(spec.model)
        models.append(
            ModelPrice(model=spec.model, prompt=0, completion=0) if price is None else price
        )
    return PriceTable(
        source="run file" if parsed.prices else "mock: no gateway, so no price",
        read_at=_utc_now(),
        unit=PRICE_UNIT,
        models=tuple(models),
    )


# --- parsing -------------------------------------------------------------------------------


def _read_json(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"{path} does not exist") from None
    except OSError as error:
        raise ConfigError(f"{path} cannot be read: {error}") from None
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(f"{path} is not JSON: {error}") from None
    if not isinstance(payload, Mapping):
        raise ConfigError(f"{path} must hold a JSON object")
    return {str(key): value for key, value in payload.items()}


def _only(raw: Mapping[str, Any], allowed: frozenset[str], where: str) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ConfigError(f"{where} has unknown key(s) {unknown}; accepted are {sorted(allowed)}")


def _string(raw: Mapping[str, Any], name: str, where: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{where}: {name} must be a non-empty string, got {value!r}")
    return value


def _optional_string(raw: Mapping[str, Any], name: str, where: str) -> str | None:
    if name not in raw:
        return None
    return _string(raw, name, where)


def _list(raw: Mapping[str, Any], name: str, where: str) -> list[Any]:
    value = raw.get(name)
    if not isinstance(value, list):
        raise ConfigError(f"{where}: {name} must be an array, got {value!r}")
    return value


def _config(raw: object, seats: tuple[SeatSpec, ...]) -> RunConfig:
    if not isinstance(raw, Mapping):
        raise ConfigError(f"config must be an object, got {raw!r}")
    values: dict[str, JsonValue] = {str(key): item for key, item in raw.items()}
    values.setdefault("players", len(seats))
    values.setdefault("interaction_protocol", "decline_only")
    if values["players"] != len(seats):
        raise ConfigError(
            f"config.players is {values['players']} but the run file declares {len(seats)} seats"
        )
    return RunConfig.from_mapping(values, game_option_keys=None)


def _seats(raw: list[Any]) -> tuple[SeatSpec, ...]:
    seats: list[SeatSpec] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ConfigError(f"seats[{index}] must be an object")
        fields = {str(key): value for key, value in item.items()}
        _only(fields, _SEAT_KEYS, f"seats[{index}]")
        seat = fields.get("seat", index)
        if not isinstance(seat, int) or isinstance(seat, bool) or seat < 0:
            raise ConfigError(f"seats[{index}].seat must be a non-negative integer")
        agent = fields.get("agent", "llm")
        if agent != "llm":
            raise ConfigError(
                f"seats[{index}].agent is {agent!r}; a run file declares model seats only"
            )
        model = _string(fields, "model", f"seats[{index}]")
        provider = _string(fields, "provider", f"seats[{index}]")
        behaviour = _optional_string(fields, "behaviour", f"seats[{index}]")
        if behaviour is not None and behaviour not in {member.value for member in Behaviour}:
            accepted = [member.value for member in Behaviour]
            raise ConfigError(f"seats[{index}].behaviour {behaviour!r} is not one of {accepted}")
        seats.append(
            SeatSpec(
                seat=seat,
                model=model,
                provider=provider,
                behaviour=behaviour,
                actions=_actions(fields.get("actions", []), index),
                sampling=_sampling(fields, index),
            )
        )
    ordered = sorted(seats, key=lambda spec: spec.seat)
    indices = [spec.seat for spec in ordered]
    if indices != list(range(len(ordered))):
        raise ConfigError(f"the seats must be numbered 0 to {len(ordered) - 1}, got {indices}")
    return tuple(ordered)


def _actions(raw: object, index: int) -> tuple[ToolCall, ...]:
    if not isinstance(raw, list):
        raise ConfigError(f"seats[{index}].actions must be an array")
    calls: list[ToolCall] = []
    for position, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ConfigError(f"seats[{index}].actions[{position}] must be an object")
        fields = {str(key): value for key, value in item.items()}
        _only(fields, frozenset({"type", "params"}), f"seats[{index}].actions[{position}]")
        name = _string(fields, "type", f"seats[{index}].actions[{position}]")
        params = fields.get("params", {})
        if not isinstance(params, Mapping):
            raise ConfigError(f"seats[{index}].actions[{position}].params must be an object")
        calls.append(
            ToolCall(
                id=f"script-{index}-{position}",
                name=name,
                arguments={str(key): value for key, value in params.items()},
            )
        )
    return tuple(calls)


def _sampling(fields: Mapping[str, Any], index: int) -> Sampling:
    temperature = fields.get("temperature", 0.0)
    top_p = fields.get("top_p", 1.0)
    for name, value in (("temperature", temperature), ("top_p", top_p)):
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise ConfigError(f"seats[{index}].{name} must be a number, got {value!r}")
        if not 0 <= value <= 1:
            raise ConfigError(f"seats[{index}].{name} must be between 0 and 1, got {value!r}")
    seed = fields.get("seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        raise ConfigError(f"seats[{index}].seed must be an integer")
    return Sampling(
        temperature_milli=round(float(temperature) * 1000),
        top_p_milli=round(float(top_p) * 1000),
        seed=seed,
    )


def _same_provider(seats: tuple[SeatSpec, ...]) -> None:
    providers = {spec.provider for spec in seats}
    if len(providers) != 1:
        raise ConfigError(
            f"the seats name several providers {sorted(providers)}; one run uses one provider"
        )
    provider = next(iter(providers))
    if provider not in PROVIDERS:
        raise ConfigError(f"provider {provider!r} is not one of {list(PROVIDERS)}")


def _provider_declarations(seats: tuple[SeatSpec, ...], raw: Mapping[str, Any]) -> None:
    """The mock's declarations belong to the mock; the gateway supplies its own facts (FR-5.9).

    A behaviour or an action script is a mock concept, and a price table is the gateway's, read
    at run time. Accepting either silently for a real run would let an operator believe they had
    configured something that was never consulted.
    """
    if seats[0].provider != OPENROUTER_PROVIDER:
        return
    declared = sorted(
        str(spec.seat) for spec in seats if spec.behaviour is not None or spec.actions
    )
    if declared:
        raise ConfigError(
            f"seats {declared} declare a mock behaviour or script; openrouter plays the model"
        )
    if raw.get("prices") is not None:
        raise ConfigError(
            "prices are read from the gateway for openrouter; remove the prices block"
        )


def _design(raw: object) -> ExperimentDesign | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ConfigError(f"design must be an object, got {raw!r}")
    fields = {str(key): value for key, value in raw.items()}
    _only(fields, _DESIGN_KEYS, "design")
    return ExperimentDesign(
        seating=_string(fields, "seating", "design"),
        initial_configuration=_string(fields, "initial_configuration", "design"),
        configuration_scope=_string(fields, "configuration_scope", "design")
        if "configuration_scope" in fields
        else "per_experiment",
        replicates=_integer(fields, "replicates", "design", default=1),
    )


def _policies(raw: object) -> tuple[TurnPolicy, ContextPolicy]:
    if not isinstance(raw, Mapping):
        raise ConfigError(f"policies must be an object, got {raw!r}")
    fields = {str(key): value for key, value in raw.items()}
    _only(fields, _POLICY_KEYS, "policies")
    on_exhausted = fields.get("on_exhausted", "abandon_game")
    if on_exhausted != "abandon_game":
        raise ConfigError(f"policies.on_exhausted {on_exhausted!r} is not 'abandon_game'")
    try:
        policy = TurnPolicy(
            step_budget=_integer(
                fields, "step_budget", "policies", default=TurnPolicy().step_budget
            ),
            redo_budget=_integer(
                fields, "redo_budget", "policies", default=TurnPolicy().redo_budget
            ),
            decision_timeout_s=_positive_number(
                fields, "decision_timeout_s", "policies", default=TurnPolicy().decision_timeout_s
            ),
        )
    except ValueError as error:
        raise ConfigError(f"policies: {error}") from None
    strategy = fields.get("context", ContextStrategy.DELTA_WITH_REFRESH.value)
    if not isinstance(strategy, str):
        raise ConfigError("policies.context must be a string")
    try:
        context = ContextPolicy(
            strategy=ContextStrategy(strategy),
            refresh_every=_integer(
                fields, "context_refresh_every", "policies", default=ContextPolicy().refresh_every
            ),
            window=_integer(fields, "context_window", "policies", default=ContextPolicy().window),
        )
    except (ContextError, ValueError) as error:
        raise ConfigError(f"policies: {error}") from None
    return policy, context


def _integer(raw: Mapping[str, Any], name: str, where: str, *, default: int) -> int:
    value = raw.get(name, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ConfigError(f"{where}.{name} must be a positive integer, got {value!r}")
    return value


def _positive_number(raw: Mapping[str, Any], name: str, where: str, *, default: float) -> float:
    value = raw.get(name, default)
    if not isinstance(value, int | float) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{where}.{name} must be a positive number, got {value!r}")
    return float(value)


def _prices(raw: object, seats: tuple[SeatSpec, ...]) -> tuple[ModelPrice, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ConfigError(f"prices must be an array, got {raw!r}")
    prices: list[ModelPrice] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ConfigError(f"prices[{index}] must be an object")
        fields = {str(key): value for key, value in item.items()}
        _only(fields, frozenset({"model", "prompt", "completion"}), f"prices[{index}]")
        model = _string(fields, "model", f"prices[{index}]")
        prices.append(
            ModelPrice(
                model=model,
                prompt=_non_negative(fields, "prompt", f"prices[{index}]"),
                completion=_non_negative(fields, "completion", f"prices[{index}]"),
            )
        )
    known = {price.model for price in prices}
    missing = sorted({spec.model for spec in seats} - known)
    if missing:
        raise ConfigError(f"prices are declared for every model; no price for {missing}")
    return tuple(prices)


def _non_negative(raw: Mapping[str, Any], name: str, where: str) -> int:
    value = raw.get(name, 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ConfigError(f"{where}.{name} must be a non-negative integer, got {value!r}")
    return value


def _game_prompt(path: Path, raw: object) -> Path | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ConfigError(f"prompts must be an object, got {raw!r}")
    fields = {str(key): value for key, value in raw.items()}
    _only(fields, frozenset({"game"}), "prompts")
    if "game" not in fields:
        return None
    value = _string(fields, "game", "prompts")
    prompt = Path(value)
    return prompt if prompt.is_absolute() else path.parent / prompt


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


__all__: Final[list[str]] = [
    "MOCK_PROVIDER",
    "OPENROUTER_KEY_VARIABLE",
    "OPENROUTER_PROVIDER",
    "PROVIDERS",
    "RunFile",
    "SeatSpec",
    "load_run_file",
    "run_from_file",
]
