"""Concurrent decisions: dispatched together, applied in the game's resolution order (K-031).

Discards after a seven and trade responses are concurrent by rule. Answering them serially
multiplies a model-driven game's wall clock for no gain, and answering them out of order changes the
record. The test asset is a game with one open decision per seat and no interaction between the
answers, so the only thing that can distinguish the two dispatch modes is the order the runner
writes them down.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import tests.games.concurrent_game  # noqa: F401 - importing registers the game
from lgbg.agents.pricing import PRICE_UNIT, ModelPrice, PriceTable
from lgbg.agents.prompting import PromptSet
from lgbg.agents.providers.base import (
    Completion,
    CompletionConfig,
    Message,
    Provider,
    ToolCall,
    ToolSpec,
)
from lgbg.agents.providers.mock import Behaviour, MockProvider
from lgbg.agents.sidecar import DecisionSidecar
from lgbg.core.config import RunConfig
from lgbg.core.log import GameLogReader, god_log_path
from lgbg.runner import GameResult, LlmAgent, run_game

PLAYERS: Final[int] = 4
MODEL: Final[str] = "mock-model"
RUN_ID: Final[str] = "r-k031"
AT: Final[str] = "2026-02-11T09:30:00+00:00"


class RendezvousProvider:
    """Hold every completion until all of them have started, then answer them all.

    A serial dispatcher can never release the barrier, so this proves the calls overlapped rather
    than merely that they all happened. The inner mock supplies the recorded wire exchange and
    usage every completion must carry.
    """

    def __init__(self, expected: int, action: ToolCall) -> None:
        self._expected = expected
        self._inner = MockProvider(Behaviour.ALWAYS_ILLEGAL, action=action)
        self._arrived = 0
        self._in_flight = 0
        self.max_in_flight = 0
        self._release = asyncio.Event()

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        config: CompletionConfig,
    ) -> Completion:
        self._arrived += 1
        self._in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self._in_flight)
        if self._arrived == self._expected:
            self._release.set()
        try:
            await asyncio.wait_for(self._release.wait(), timeout=2.0)
        finally:
            self._in_flight -= 1
        return await self._inner.complete(messages, tools, config)


class DelayedProvider:
    """A provider that answers after a fixed delay, so completion order is predictable."""

    def __init__(self, delay_s: float, action: ToolCall) -> None:
        self._delay_s = delay_s
        self._inner = MockProvider(Behaviour.ALWAYS_ILLEGAL, action=action)

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        config: CompletionConfig,
    ) -> Completion:
        await asyncio.sleep(self._delay_s)
        return await self._inner.complete(messages, tools, config)


def prompts(directory: Path) -> PromptSet:
    directory.mkdir(parents=True, exist_ok=True)
    game_prompt = directory / "game.md"
    game_prompt.write_text("The concurrent game: every seat marks once.\n", encoding="utf-8")
    return PromptSet.load("concurrent", game_prompt=game_prompt)


def price_table() -> PriceTable:
    return PriceTable(
        source="test",
        read_at=AT,
        unit=PRICE_UNIT,
        models=(ModelPrice(model=MODEL, prompt=0, completion=0),),
    )


def agents(providers: Sequence[Provider]) -> dict[int, LlmAgent]:
    return {
        seat: LlmAgent(
            provider=provider,
            model=MODEL,
            provider_id="mock",
            provider_version="1",
        )
        for seat, provider in enumerate(providers)
    }


def play(
    tmp_path: Path,
    *,
    providers: Sequence[Provider],
    concurrent: bool,
    directory: str = "run",
) -> GameResult:
    return asyncio.run(
        run_game(
            game="concurrent",
            config=RunConfig(seed=7, players=PLAYERS, interaction_protocol="concurrent"),
            directory=tmp_path / directory,
            run_id=RUN_ID,
            requested_id="g-0001",
            seats=agents(providers),
            prompts=prompts(tmp_path / "prompts"),
            price_table=price_table(),
            concurrent=concurrent,
            clock=lambda: AT,
        )
    )


def test_concurrent_decisions_are_dispatched_together(tmp_path: Path) -> None:
    """The model calls overlap: a serial dispatcher cannot get past the rendezvous."""
    action = ToolCall(id="mark", name="mark", arguments={})
    provider = RendezvousProvider(PLAYERS, action)

    result = play(tmp_path, providers=[provider] * PLAYERS, concurrent=True)

    assert result.completed is True
    assert result.actions == PLAYERS
    assert provider.max_in_flight == PLAYERS, "the four completions were in flight together"


def test_decisions_are_applied_in_the_games_resolution_order(tmp_path: Path) -> None:
    """Seat 3 answers first but seat 0 is applied first: the gate, not arrival, fixes the record."""
    delays = (0.03, 0.02, 0.01, 0.0)
    providers = [
        DelayedProvider(delay, ToolCall(id=f"mark-{seat}", name="mark", arguments={}))
        for seat, delay in enumerate(delays)
    ]

    result = play(tmp_path, providers=providers, concurrent=True)
    recorded = GameLogReader(god_log_path(result.directory, result.game_id)).read()

    assert result.completed is True
    assert [action.player for action in recorded.actions] == list(range(PLAYERS))


def test_a_decision_closed_by_an_earlier_answer_is_not_submitted(tmp_path: Path) -> None:
    """A speculative answer for a request the batch has closed is discarded, not forced in."""
    providers = [
        MockProvider(
            Behaviour.ALWAYS_ILLEGAL,
            action=ToolCall(id="close", name="close", arguments={}),
        ),
        *[
            MockProvider(
                Behaviour.ALWAYS_ILLEGAL,
                action=ToolCall(id=f"mark-{seat}", name="mark", arguments={}),
            )
            for seat in range(1, PLAYERS)
        ],
    ]

    result = play(tmp_path, providers=providers, concurrent=True)

    assert result.completed is True
    assert result.actions == 1, "only the closing answer was applied"
    recorded = GameLogReader(god_log_path(result.directory, result.game_id)).read()
    assert [action.player for action in recorded.actions] == [0]
    side = DecisionSidecar(result.sidecar_path).records()
    assert sum(1 for record in side if record.get("t") == "decision") == 1


def test_the_record_is_identical_whether_answered_serially_or_in_parallel(tmp_path: Path) -> None:
    """The reference net: dispatch mode changes when the answers happen, never what is written."""

    def once(concurrent: bool, directory: str) -> tuple[bytes, list[dict[str, Any]]]:
        providers = [
            MockProvider(
                Behaviour.ALWAYS_ILLEGAL,
                action=ToolCall(id=f"mark-{seat}", name="mark", arguments={}),
            )
            for seat in range(PLAYERS)
        ]
        result = play(
            tmp_path,
            providers=providers,
            concurrent=concurrent,
            directory=directory,
        )
        log = god_log_path(result.directory, result.game_id)
        side = DecisionSidecar(result.sidecar_path).records()
        stable: list[dict[str, Any]] = [
            {key: value for key, value in record.items() if key not in {"at", "latency_ms"}}
            for record in side
        ]
        return log.read_bytes(), stable

    serial_log, serial_side = once(False, "serial")
    parallel_log, parallel_side = once(True, "parallel")

    assert serial_log == parallel_log, "the god log is the deterministic record"
    assert serial_side == parallel_side, "the sidecar tells the same story once timing is removed"
    assert sum(1 for record in serial_side if record.get("t") == "decision") == PLAYERS
