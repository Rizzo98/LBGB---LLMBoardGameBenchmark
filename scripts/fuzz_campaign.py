"""The fuzz campaign: many games, many seeds, and a summary of what they found (K-067).

The harness of K-064 drives one game and objects when a plugin breaks a declaration. A campaign is
that, repeated across seeds and policies, far enough that a rare path is reached - and it is the
evidence SC-2 asks for: no uncaught exception, every declared invariant holding, and lengths that
say which games wander rather than finish.

    uv run python scripts/fuzz_campaign.py --games 10000 --seeds 1000 --out fuzz_campaign.json

It prints the summary and, when given --out, writes it as JSON. Nothing here is a test: the CI
smoke run is tests/core/test_fuzzing.py, and this is the campaign an operator runs and records.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Final

import lgbg.games  # noqa: F401 - importing the package registers the in-repo plugins
from lgbg.core.config import GameConfig, RunConfig
from lgbg.core.fuzzing import POLICIES, run_fuzz
from lgbg.core.game import get_game

PLAYERS: Final[int] = 4
BOARD: Final[str] = "fixed:standard_a"
BOUND: Final[int] = 4000


def one_game(game: Any, seed: int, policy: str) -> tuple[dict[str, Any] | None, str | None]:
    """One game, as a summary, or the exception that stopped it."""
    config = RunConfig(
        seed=seed,
        players=PLAYERS,
        interaction_protocol="decline_only",
        game_config=GameConfig({"board": BOARD}),
    )
    try:
        report = run_fuzz(game, config, policy=POLICIES[policy], max_actions=BOUND)
    except Exception as error:
        return None, f"seed {seed} policy {policy}: {type(error).__name__}: {error}"
    return {
        "seed": seed,
        "policy": policy,
        "actions": report.actions,
        "rejected": report.rejected,
        "livelock": report.livelock,
        "offenders": list(report.offenders),
    }, None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=10000)
    parser.add_argument("--seeds", type=int, default=1000)
    parser.add_argument("--first-seed", type=int, default=20270101)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    game = get_game("catan")
    names = sorted(POLICIES)
    failures: list[str] = []
    offenders: list[str] = []
    actions: list[int] = []
    livelocks = 0
    started = time.perf_counter()
    for index in range(args.games):
        seed = args.first_seed + index % args.seeds
        summary, failure = one_game(game, seed, names[index % len(names)])
        if failure is not None:
            failures.append(failure)
            continue
        if summary is None:  # unreachable: a failure came back as one
            continue
        actions.append(int(summary["actions"]))
        livelocks += int(bool(summary["livelock"]))
        offenders.extend(str(offender) for offender in summary["offenders"])

    seconds = time.perf_counter() - started
    played = len(actions)
    summary_record: dict[str, Any] = {
        "games": args.games,
        "seeds": args.seeds,
        "games_played": played,
        "failures": failures[:20],
        "failure_count": len(failures),
        "offenders": sorted(set(offenders))[:20],
        "offender_count": len(offenders),
        "livelocks": livelocks,
        "median_actions": int(statistics.median(actions)) if actions else 0,
        "max_actions": max(actions) if actions else 0,
        "seconds": round(seconds, 1),
        "ms_per_game": round(1000 * seconds / played, 2) if played else 0.0,
    }

    print(json.dumps(summary_record, indent=2, sort_keys=True))
    if args.out is not None:
        Path(args.out).write_text(
            json.dumps(summary_record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"wrote {args.out}")
    return 1 if (failures or offenders) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
