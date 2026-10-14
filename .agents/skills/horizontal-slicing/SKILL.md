---
name: horizontal-slicing
description: Use when creating or reviewing a kanban board, work breakdown, or task plan for a system built from multiple components or layers. Decomposes work into horizontal slices that each cut through every layer end to end and deliver a coherent, testable improvement, instead of completing one service or layer at a time.
---

# Horizontal Slicing Through Integrated Increments

## The principle

> Break work down into small, incremental tasks that evolve **multiple components together** rather
> than completing one service or layer at a time. Each task should deliver a coherent, testable
> improvement to the overall system, integrating and validating interactions between components
> early and frequently. Build a minimal working end-to-end flow first, then progressively extend and
> refine it through short feedback loops. Prioritize continuous integration, early validation, and
> adaptation over isolated component completion.

Apply this whenever you turn a PRD, design document, or feature request into a task board.

## When to use it

- Creating a kanban board or work breakdown for anything with more than one component.
- Reviewing an existing board for sequencing risk.
- Planning a milestone, release, or migration.

It matters most when the system has layers that must agree on interfaces: an API and its clients, a
storage layer and its readers, a rules engine and its UI. Those interfaces are the risky part, and
vertical plans defer discovering whether they work.

## Vertical versus horizontal

A **vertical** decomposition completes one layer at a time:

```text
parse module -> rules module -> storage module -> API -> UI -> wire together
```

Its failure mode is *late discovery*. Nobody learns whether the storage format survives a real
rules workload until the final step, when correcting it is most expensive and most of the code that
depends on it already exists.

A **horizontal** slice cuts through every layer at once and stops at the first thing that
demonstrably works end to end:

```text
slice 1: parse -> rules -> storage -> API -> UI   (thinnest path that runs)
slice 2: + one real rule, end to end
slice 3: + persistence, end to end
```

Each slice is describable in one sentence of *user-visible capability*, and every interface is
exercised on the first slice where both of its sides exist.

## How to build the slices

1. **Write the end state as a single sentence.** The thinnest path that touches every layer and
   produces something observable.
2. **Identify the layer you cannot avoid.** There is usually one component every path must cross
   (a serialisation format, a schema, a protocol). It gets exercised first, not last.
3. **Cut slice 1 as thin as possible.** It is acceptable to substitute a toy or fixture stand-in for
   the real domain logic here, provided the stand-in exercises the real interfaces. This isolates
   infrastructure defects from domain defects.
4. **Order the remaining slices by user-visible capability, not by component.** Each slice should
   end with a sentence a stakeholder would recognise as progress.
5. **Pull forward whatever a slice needs to be demonstrably complete.** Dependencies exist to serve
   slices; slice boundaries are not sacred. If a capability is reachable only by including one item
   from a later area, move that item earlier.
6. **Add a regression net that grows with the board.** Each slice commits a fixture that exercises
   what it added, and later slices must keep every earlier fixture passing.

## Rules each slice must satisfy

| Rule | Test |
|---|---|
| Every slice ends in a runnable demo | Can you name the command a person runs to see it? |
| No slice completes a layer | If the whole output is "finish module X", it is mis-sliced |
| Every task integrates components | If a task touches one component only, merge it with its neighbour |
| Interfaces are validated early | The riskiest interface appears in an early slice, not a late one |
| Tests arrive with the slice | A slice is done when the feature is asserted, not when it works |
| The observable surface grows every slice | If there is a CLI, UI, or report, each slice extends it |

## When horizontal slicing is genuinely blocked

There are two legitimate reasons a slice cannot be cut thinner. Both should be documented on the
card rather than silently ignored:

1. **Correctness constraints.** Some subsystems cannot be partially implemented without producing an
   invalid intermediate state. Shipping the partial version means shipping something knowingly
   wrong. Group the inseparable parts into one slice and say so.
2. **Reachability constraints.** Some outcomes are unreachable until a specific capability exists,
   even though that capability looks like a separate area. Pull it forward instead of shipping a
   slice that cannot demonstrate its own goal.

A slice that is neither correct nor demonstrable is not a slice. If you cannot state what it
demonstrates, you have a task list, not a slice.

## Writing the cards

Record each slice in the board format the project uses. With the Markdown Kanban format, a board is
one level-1 heading, level-2 headings for status columns, and level-3 headings for tasks:

````markdown
# Board title

## Todo

### TASK-001 · Short action-oriented title

  - tags: [slice-1, core, FR-1]
  - priority: high
  - workload: Normal
  - steps:
      - [ ] First verifiable acceptance condition
      - [ ] Second verifiable acceptance condition
    ```md
    - **Cuts through:** component A, component B, component C
    - **Depends on:** TASK-000
    - **Why:** The reason this card exists and why it is cut this way.
    ```

````

Map the slicing information onto the format like this:

| Slicing concept | Where it goes |
|---|---|
| Which slice the task belongs to | a `tags` entry, for example `slice-3` |
| Which components it integrates | the `Cuts through` line of the description |
| Its acceptance criteria | the `steps` checkboxes |
| Its relative size | `workload` |
| Its scheduling urgency | `priority` |
| Requirements it satisfies | `tags` plus a `PRD` line in the description |
| Its prerequisites | a `Depends on` line in the description |

Do not add prose sections to the board. Slice grouping, ordering rationale, and dependency notes
belong in tags and card descriptions, so the file stays a list of tasks that a tool can parse.

## Anti-patterns

- **The layer card.** "Implement the storage module." One component, no integration, no demo.
- **The framework-first card.** "Design the plugin interface." Interfaces are discovered from a
  working path, not designed in advance. Cut a slice that forces the interface to exist.
- **The big-bang integration.** Every slice is internal until a final wiring slice. This is vertical
  decomposition wearing slice labels.
- **The empty slice.** It advances a component but demonstrates nothing a stakeholder would
  recognise.
- **The deferred regression net.** Fixtures and tests are treated as a later phase. Then no slice
  actually validates the previous one.
- **The sacred boundary.** Work that a slice obviously needs is left for later because it "belongs"
  to another area.

## Review checklist

Before accepting a board, confirm:

- [ ] Slice 1 is a thin end-to-end path, and its exit test is a command.
- [ ] Every slice has a one-sentence demoable outcome.
- [ ] No card's entire output is "finish component X".
- [ ] The riskiest interface is exercised in an early slice.
- [ ] Each slice's acceptance criteria are written as checkboxes.
- [ ] Each slice commits a regression fixture, and earlier fixtures keep passing.
- [ ] Any deviation from thin slicing is documented on the card with its reason.
- [ ] The board contains only a title, status columns, and tasks.
