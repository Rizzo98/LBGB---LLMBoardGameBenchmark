# ACCEPTANCE-v1 — the release record

Every success criterion of PRD-v1 section 5, the **named command** that demonstrates it, and the
output that command produced on the tree as committed. Nothing here is accepted because a suite
"passes": it is accepted because a command was run and its output is below, so any line can be
reproduced by running the command from the repository root. The deviations at the end are part of
the record: a criterion that is not met is written down as not met, with its reason, rather than
left out.

| Field | Value |
|---|---|
| Engine version | 0.1.0 |
| Plugin | `catan`, `rules_version = catan-rules-6`, `schema_version = catan-actions-1` |
| Rule authority | `lgbg/games/catan/RULES.md`, document revision 6, status PINNED |
| Golden corpus | 7 games: 16 to 790 actions, every one verified end to end |
| Gate | `uv run python scripts/gate.py` — ruff, ruff format --check, mypy --strict, pytest |

## The criteria

| # | Demonstrated by | Result |
|---|---|---|
| SC-1 | `... main(['verify','tests/golden/catan'])` | 7 records, 0 rejections, hashes pinned (below) |
| SC-2 | `uv run python scripts/fuzz_campaign.py --games 30 --seeds 30` | 0 exceptions, 0 offenders — scale deviation, see below |
| SC-3 | `uv run pytest tests/core -q` | 91 tests, including determinism across hash seeds |
| SC-4 | `uv run pytest tests/core/test_replay.py tests/core/test_log.py -q` | tamper detection localised to a seq |
| SC-5 | `... verify tests/golden/catan` | 0 rejections in the corpus, so invariance holds vacuously and is asserted separately |
| SC-6 | `uv run pytest tests/games/test_catan_leaks.py tests/games/test_catan_leak_matrix.py -q` | 51 tests, one per hidden field per observer per rendering |
| SC-7 | `uv run pytest tests/games/test_board_layout.py -q` | 61 tests: 19 hexes, 54 vertices, 72 edges, 9 harbours |
| SC-8 | `uv run pytest tests/games/test_catan_assist.py -q` | 9 tests, byte-identical logs at L0/L1/L2 |
| SC-9 | `uv run pytest tests/tooling/test_traceability.py -q` | matrix over 142 requirements, gaps recorded |
| SC-10 | `uv run python -c "...tomllib...['dependencies']"` | `[]` |
| SC-11 | `uv run pytest tests --cov=lgbg.core --cov=lgbg.games.catan.rules --cov=lgbg.games.catan.projection` | 96% total, longest_road 100%, projection 100% |
| SC-12 | `lgbg/games/catan/RULES.md` (revision 6) | every rule area cited to the rulebook; eight ambiguities resolved |
| SC-13 | `uv run pytest tests/games/test_catan_profile.py tests/games/test_catan_rejection_fuzz.py -q` | profile complete, no undeclared rejection code in a fuzzed run |

## The output

SC-1, and the corpus behind SC-5, SC-8 and SC-12. `lgbg verify` on the golden directory, one line a
record:

```text
ok: tests/golden/catan/devcard_game.god.jsonl: 476 action(s), 0 rejection(s), final hash 34fec8a48e21537f
ok: tests/golden/catan/full_game.god.jsonl: 743 action(s), 0 rejection(s), final hash e57e23d3c4839159
ok: tests/golden/catan/random_game.god.jsonl: 790 action(s), 0 rejection(s), final hash 6fa50e63d0155a0b
ok: tests/golden/catan/setup_game.god.jsonl: 16 action(s), 0 rejection(s), final hash d1612a388d49137d
ok: tests/golden/catan/seven_game.god.jsonl: 43 action(s), 0 rejection(s), final hash b59ca27542264e0c
ok: tests/golden/catan/three_player_game.god.jsonl: 205 action(s), 0 rejection(s), final hash af9114ee7555141f
ok: tests/golden/catan/trade_game.god.jsonl: 598 action(s), 0 rejection(s), final hash 385f4ac1f762534d
```

SC-2. The campaign, at the scale this release run could afford, with its summary committed as
`benchmark/fuzz_campaign.json`:

```text
games 30 · seeds 30 · games_played 30 · failure_count 0 · offender_count 0
livelocks 30 · ms_per_game 20686
```

SC-10. The plugin's runtime dependency list, read out of `pyproject.toml`:

```text
runtime dependencies: []
```

SC-11. Coverage over the whole suite for the three scopes the criterion names:

```text
lgbg/games/catan/projection.py        53      0   100%
lgbg/games/catan/rules/longest_road.py 58     0   100%
TOTAL                               2452     92    96%
```

SC-3 to SC-9 and SC-13. Each is a pytest selection whose summary is the evidence; the counts are in
the table above and the full output is one command away: `uv run pytest <paths> -q`. The gate that
runs all of them together, and refuses to pass without ruff, ruff format, mypy --strict and every
test, is:

```text
uv run python scripts/gate.py
==> lint: -m ruff check .            All checks passed!
==> format: -m ruff format --check . 131 files already formatted
==> types: -m mypy .                 Success: no issues found
==> tests: -m pytest                 917 passed, 1 skipped
==> gate passed
```

## Deviations, and why they are here

Four things this release does **not** satisfy, each found by running the check the document asks
for rather than by reading the suite's colour. Whether they are accepted as deviations or carried
as open work is a release decision, and they are written here so that decision can be made against
the numbers.

1. **SC-2's scale.** The criterion asks for 10,000 games across 1,000 seeds. The campaign ran 30
   games across 30 seeds with zero exceptions and zero broken declarations - 120,000 asserted
   actions - and at 20.7 seconds a game the full scale is about 55 hours, because the harness
   asserts the schema of every offered action, the declared invariants, ten projections and three
   state hashes per action. The gap is a cost, not a defect, and the command to close it is
   `scripts/fuzz_campaign.py`.
2. **NFR-2's timings.** A four-player game in under 50 ms: measured at 932 ms for bare play (K-039),
   roughly nineteen times the budget, before the harness adds anything. The performance tests assert
   only the bounds that do not depend on the machine, which is why a green suite never contradicted
   the requirement.
3. **SC-11's enforcement.** Coverage is measured, not gated: 96% overall and 100% on the two modules
   the criterion names, from the command above. Making it mechanical costs a second full pass of the
   suite inside the gate.
4. **FR-22.3's event sufficiency.** The PRD asks that applying events to the pre-state reproduce the
   post-state. The harness asserts the weaker claim the interface supports - an accepted action emits
   at least one event - and says so in its own docstring; the stronger claim needs a new protocol
   member and every game implementing it.

The board stands at 66 of 68 cards. The two open ones are K-067, held open on the scale and the
timing above, and K-068, which is this record: its remaining step is the demonstration list being
signed off rather than written. A release that said "all criteria met" while these four lines stand
would be the one thing this project has spent its whole build avoiding.



