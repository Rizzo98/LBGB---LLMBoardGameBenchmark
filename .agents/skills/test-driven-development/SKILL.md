---
name: test-driven-development
description: Use when writing, changing, or reviewing code, and especially before adding behaviour to a codebase that already has tests. Drives work through the red-green-refactor loop one small failing test at a time, and pairs it with automated formatting, linting, and type checking (ruff, ruff format, mypy) so that style and correctness are enforced by tooling rather than by review.
---

# Test-Driven Development: Red, Green, Refactor

Write the test first. Watch it fail. Make it pass. Then clean up. Repeat in steps small enough that
you are never more than a minute from knowing whether the last change broke something.

The loop is not a ritual about testing. It is a design technique: writing the test first forces you
to decide what the code is for and how it will be called, before you commit to how it works.

## The loop

```text
RED      -> write a test that fails, and run it to confirm it fails for the right reason
GREEN    -> write the least code that makes it pass
REFACTOR -> improve the design, with the test as a safety net
```

Then repeat. Each pass should take seconds to a few minutes. If a pass is taking longer, the step was
too big: revert and cut it smaller.

### Red

Write the smallest test that expresses the next increment of behaviour, then **run it**.

- Watch it fail. A test you have never seen fail proves nothing. It may be vacuous, misspelled, or
  never executed at all.
- Confirm it fails **for the reason you intended**. If it errored during setup, or failed on a typo
  inside the test itself, you have learned nothing yet. Fix the test until the failure is the real
  one.
- Treat a test that passes on the first run as suspicious. Either the behaviour already exists, the
  assertion is too weak, or you are testing the test double instead of the code.
- Write the test against the interface you wish existed. The discomfort of a clumsy call site is
  design feedback, and it is free at this point.

### Green

Make it pass with the least code that could possibly work.

- Hardcode a return value if that is what the test demands. Duplicate a line. Be inelegant on
  purpose. The next test will force the generalisation.
- **Do not add anything no test requires.** No parameters, no configuration, no extensibility, no
  abstraction. Every unearned abstraction is design you now have to maintain and defend.
- Resist "while I am here". Unrelated improvements belong in their own red-green cycle, or in the
  refactor step once the suite is green.

### Refactor

Now, with the tests green, improve the design.

- **Never refactor while red.** If the suite is failing, the first job is to get back to green.
- Refactor the test code as well as the production code. Tests are code, and duplicated setup is a
  liability that makes the next test harder to write.
- Take small steps and re-run the tests after each. A refactor that breaks several tests at once is
  a rewrite.
- This step is where design actually happens. Skipping it is the most common reason TDD produces a
  working mess instead of a clean design.

## The three laws

The strict form, worth following literally while learning the loop:

1. Do not write production code until you have a failing test.
2. Do not write more of a test than is enough to fail. Not compiling counts as failing.
3. Do not write more production code than is enough to pass the currently failing test.

Before starting a piece of work, write down the list of test cases you expect to need. That list is
your plan, and each entry becomes one red-green-refactor cycle. The list will change as you learn,
and that is the point.

## The tooling gate

Everything mechanical should be decided by a tool, not by a person in review. Tools are faster, more
consistent, and do not get tired. A reviewer's attention should go to design and correctness, not to
quote style and import order.

### Ruff: formatting and linting

Ruff provides both the formatter and the linter, and they share one configuration.

```bash
ruff format .              # apply formatting (Black-compatible, and far faster)
ruff format --check .      # verify without writing - use this in CI
ruff check .               # lint
ruff check --fix .         # apply safe autofixes

ruff rule F401             # explain what a rule means
ruff check --statistics .  # see which rules fire most often
```

Configuration lives in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
# Start from a broad set, then narrow deliberately as the codebase adopts it.
select = [
    "E", "W",   # pycodestyle
    "F",        # pyflakes - real bugs: unused names, undefined names
    "I",        # isort - import ordering
    "N",        # pep8-naming
    "UP",       # pyupgrade - modern syntax for the target version
    "B",        # flake8-bugbear - likely mistakes
    "SIM",      # simplify
    "C4",       # comprehensions
    "PT",       # pytest style
    "S",        # flake8-bandit - security
    "RUF",      # ruff-specific
    "TID",      # tidy imports
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]   # asserts are the point in tests
```

Two capabilities are worth knowing beyond the basics.

**`ruff check --fix --unsafe-fixes`** applies the fixes ruff cannot prove are safe. Read the
resulting diff. The flag name is a warning, not a formality.

**`per-file-ignores`** and **`flake8-tidy-imports.banned-api`** turn architectural rules into
enforced ones. Banning a module everywhere except the one file permitted to use it is far more
reliable than a convention written in a document:

```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"random".msg = "Import the seam instead; ambient randomness makes behaviour unreproducible."

[tool.ruff.lint.per-file-ignores]
"src/random_source.py" = ["TID251"]   # the one module permitted to import it
```

Prefer a lint rule over a paragraph of guidance. A rule fails the build; a paragraph is forgotten.

### Type checking

Run a static type checker alongside the linter. Annotations that are never checked drift away from
the truth within weeks.

```bash
mypy --strict src/
```

Adopt strictness incrementally rather than switching it on and giving up. Enable it per package, and
use targeted per-module overrides for code that is not ready. The goal is that a type error fails
the build, not that every file is perfect today.

### Wiring the gate into the loop

Order the gate from cheapest and most mechanical to most judgemental, so that by the time a human or
a model looks at the failures, only decisions remain:

```bash
ruff check --fix . && ruff format . && ruff check . && mypy src/ && pytest -q
```

Run the autofixes before the formatter, so the formatter has the final say on layout. The bare
`ruff check` after the autofix pass surfaces what could not be fixed automatically - those are the
findings that need a decision.

Automate it so nobody has to remember:

- **In the editor**: format on save, with lint findings shown inline.
- **Before commit**: a pre-commit hook running the autofix and format steps.
- **In CI**: the check-only variants, so nothing unformatted or unlinted can merge.

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: <pin-to-a-released-tag>
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

Keep the whole gate fast enough to run on every save. A gate that takes minutes gets deferred to the
end, which is the same as not having one.

## What makes a test worth keeping

- **It tests behaviour through a public seam**, not a private method. Tests coupled to internals
  break on every refactor, which teaches the team to stop refactoring.
- **It has one reason to fail.** If two unrelated changes can break it, the failure message cannot
  tell you which one happened.
- **Its name states the behaviour and the expected outcome.** `test_road_must_connect_to_own_network`
  says something; `test_road_2` does not.
- **Arrange, Act and Assert are visually separated**, so a reader can see what is being exercised.
- **It is deterministic.** No clock, no network, no reliance on file ordering, no `sleep`, no
  unseeded randomness. A flaky test is worse than no test: it teaches everyone to ignore red.
- **It is fast enough to run constantly.** Slow tests get skipped, and a skipped test is decoration.
- **Its failure message identifies what broke** without needing to read the test body.

## Test doubles and seams

Use the real thing wherever it is fast and deterministic. Reach for a double only at a genuine
boundary: the network, the clock, the filesystem, a payment provider, a source of randomness.

Prefer a seam you own - an injected interface - over patching internals. Patching a private function
couples the test to the implementation and silently stops testing anything once the internals are
renamed.

Never mock the thing under test. A test that replaces the logic it claims to verify asserts only
that the mock was called.

## Coverage: what it proves and what it does not

Coverage measures which lines **executed**, not which behaviours were **verified**. A suite with
100% coverage and no assertions proves that the code runs, and nothing else.

- Use coverage to find untested paths. Do not use it as a target, because it will be gamed.
- Hold pure logic, parsers and state transitions to a high bar. Glue code needs less.
- The honest check is mutation-style: **deliberately break the production code and confirm a test
  fails.** If nothing fails, the coverage was an illusion. Do this for a sample of critical paths,
  and automate it for the ones that matter most.

## When TDD feels impossible

Difficulty writing a test is almost always a design signal, not a reason to skip the test. Code is
hard to test when it reaches for global state, performs I/O inline, depends on the clock, or
constructs its own collaborators.

Treat the friction as the finding. Extract the seam, inject the dependency, make the core a pure
function. The code that results is usually better for reasons that have nothing to do with testing.

## Anti-patterns and rationalizations

| Anti-pattern | Why it is wrong |
|---|---|
| Writing code first, tests after | The tests end up shaped to the implementation, so they verify what the code does rather than what it should do |
| The assertion-free test | It exercises the code and checks nothing, so it passes forever |
| The change-detector test | It asserts internal call order, so every refactor breaks it and refactoring stops |
| Mocking the subject under test | It asserts that the mock was called, not that the behaviour is correct |
| "I will add tests once the design settles" | The design settles because of the tests; without them it drifts indefinitely |
| "This code is too simple to test" | Simple code is the cheapest to test. The claim usually means a test was never considered |
| "The test is hard to write, so I will skip it" | The difficulty is the finding. See the section above |
| Leaving a flaky test in place | It destroys the meaning of a red suite for everyone |
| Updating a golden or snapshot file without reading the diff | It converts a regression test into a rubber stamp |
| Coverage as a target | Once it is a target, it stops measuring anything |

## Working with a task board

When a card on the board lists acceptance criteria as checkboxes:

- Each criterion becomes **at least one test**. The criterion is the intent; the test is the proof.
- **Do not tick a checkbox until a test asserts the behaviour.** Completion is evidence-based.
- Run the loop once per criterion, not once per card. A card with four criteria is four or more
  red-green cycles, not one.
- Card-level criteria are usually unit tests. The slice exit condition is the integration test that
  exercises the whole path end to end.

## Checklist

Before calling a piece of work done:

- [ ] Every new behaviour began as a test that was run and seen to fail for the right reason.
- [ ] No production code exists that no test requires.
- [ ] The refactor step actually happened, in both the production code and the tests.
- [ ] `ruff format --check` passes.
- [ ] `ruff check` passes, with no suppressions added merely to silence real findings.
- [ ] The type checker passes at the strictness level the project enforces.
- [ ] The full suite passes, and no test was skipped or quarantined to get there.
- [ ] No test depends on wall-clock time, network access, or execution order.
- [ ] Deliberately breaking the new logic causes a test to fail.
- [ ] Every acceptance criterion on the card is covered by a test.
