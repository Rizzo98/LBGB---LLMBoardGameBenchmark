"""What a player is shown, at the level of help the run was configured for (ARCHITECTURE.md 9).

The assist level is the benchmark's most important knob: an engine that enumerates every legal
move every turn turns a planning task into a classification task, and that is a different
benchmark rather than a harder one. So the level is a parameter of *this* module and of nothing
else. It is not passed to apply, it is not read by a rule, and it is not written into a record:
the same actions produce the same states, events and hashes at every level (FR-17.1, FR-17.2),
and one recorded game can be re-rendered at another level without the game changing underneath.

Two things are rendered, and the level governs both.

* **The decision.** L0 shows the observation and nothing else, because the model is expected to
  build the action from the rules and what it can see. L1 adds the action *types* with their
  costs and the permitted values of each parameter - the domains of the plugin interface, which
  are deliberately not the cross product - and L2 adds every legal action, one to a line.
* **The refusal.** A rejected attempt is told to the player at the tier the run configured
  (FR-17.3; ARCHITECTURE.md 9.4). The record keeps the refusal in full whatever the tier is,
  which is what makes the levels comparable: only what the *player* is told changes.

The tier rule is structural rather than a list of forbidden keys. A refusal's details are either
**facts** about it - a count the player held, the count that was required, a ratio, a phase - or
**enumeration**, which in JSON means a sequence: the neighbours it could have chosen, the targets
that would have worked, the action types that exist. The minimal tier carries neither; the
standard tier carries the facts and the sentence the rule wrote, because what was required versus
what was held is exactly a fact; the full tier carries everything, alternatives included. A rule
that starts leaking a new list tomorrow leaks it only at the full tier, which is the direction to
fail in - a key-by-key deny list would have failed the other way round, and quietly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from lgbg.core.canonical import to_canonical_json
from lgbg.core.config import AssistLevel, RejectionDetail
from lgbg.core.errors import Rejection
from lgbg.core.game import Game
from lgbg.core.types import (
    Action,
    ActionDomain,
    DecisionRequest,
    JsonValue,
    ParamDomain,
    PlayerId,
    State,
)

ASKING: Final[str] = "asking"
"""The label the open decisions are listed under, so a player knows what they are answering."""


def render_decision(game: Game, state: State, player: PlayerId, *, assist: AssistLevel) -> str:
    """The decision in front of one player, at this level of assistance (FR-17.4, FR-17.5).

    L0 is the game's own rendering of that player's observation, byte for byte: the level adds
    nothing, so observation-only is a subtraction that can be asserted rather than described.
    The two higher levels append what the player may do - the domains at L1, the enumeration at
    L2 - under the decisions that are open, so one helper serves a prompt, a CLI and a tool.
    """
    observation = game.render(game.observe(state, player))
    if assist is AssistLevel.L0:
        return observation
    lines = [observation, "", _asking_line(game.pending_decisions(state), player)]
    if assist is AssistLevel.L1:
        lines.extend(f"  {_domain_line(domain)}" for domain in game.action_domains(state, player))
    else:
        lines.extend(f"  {_action_line(action)}" for action in game.legal_actions(state, player))
    return "\n".join(lines)


def rejection_view(rejection: Rejection, *, detail: RejectionDetail) -> dict[str, JsonValue]:
    """What a player is told about a refused attempt, at this tier (FR-17.3; ARCHITECTURE 9).

    The three tiers are a ladder and not three shapes: each is the one below it plus a fact.
    MINIMAL is the code alone - ok and error, exactly as ARCHITECTURE.md 9.2 writes it - because
    a refusal at the hardest level is a category and nothing more. STANDARD adds the sentence the
    rule wrote and the facts it recorded. FULL adds the rest of the details, which is where the
    alternatives live.

    Nothing here is written to the record: the record keeps the refusal in full at every tier, so
    that the tier stays a property of the interface rather than of the corpus (FR-17.2).
    """
    view: dict[str, JsonValue] = {"ok": False, "error": rejection.code.code}
    if detail is RejectionDetail.MINIMAL:
        return view
    view["message"] = rejection.message
    facts = {name: value for name, value in rejection.details.items() if _is_fact(value)}
    if facts:
        view["details"] = facts
    if detail is RejectionDetail.FULL:
        view["details"] = dict(rejection.details)
    return view


def render_rejection(rejection: Rejection, *, detail: RejectionDetail) -> str:
    """The same view as one line, which is what a driver hands to a player."""
    view = rejection_view(rejection, detail=detail)
    line = str(view["error"])
    if "message" in view:
        line = f"{line}: {view['message']}"
    if "details" in view:
        line = f"{line} {to_canonical_json(view['details'])}"
    return line


def _is_fact(value: JsonValue) -> bool:
    """Whether a detail is a fact about the refusal rather than a list of alternatives.

    A fact is a scalar - a count, a name, a ratio - or a mapping of them, which is the shape of
    what was required against what was held. Everything else is a collection of things that were
    possible: a sequence (a target set, the types that exist, the requests that are open), or a
    structure too deep to be a count. Collections are what a lower tier withholds, so a new one
    is withheld by construction rather than by somebody remembering to add its key to a list.
    """
    if isinstance(value, Mapping):
        return all(_is_scalar(item) for item in value.values())
    return _is_scalar(value)


def _is_scalar(value: JsonValue) -> bool:
    if isinstance(value, (bool, int, float, str)):
        return True
    return value is None


def _asking_line(requests: Sequence[DecisionRequest], player: PlayerId) -> str:
    mine = [request for request in requests if request.player == player]
    if not mine:
        return f"{ASKING}: nobody"
    asked = " | ".join(f"{r.request_id} {r.kind} ({r.phase})" for r in mine)
    return f"{ASKING}: {asked}"


def _domain_line(domain: ActionDomain) -> str:
    """One action type as L1 describes it: what it costs, and what each parameter may be."""
    cost = "free" if domain.cost is None else _counts(domain.cost)
    told = " ".join(f"{name}={_permitted(param)}" for name, param in domain.params.items())
    return f"{domain.type} cost={cost} {told}".rstrip()


def _action_line(action: Action) -> str:
    """One legal action as L2 gives it: the type, and every parameter it was given."""
    given = " ".join(
        f"{name}={to_canonical_json(value)}" for name, value in sorted(action.params.items())
    )
    return f"{action.type} {given}".rstrip()


def _permitted(param: ParamDomain) -> str:
    if param.kind == "int_range":
        return f"{param.lo}..{param.hi}"
    values = " ".join(to_canonical_json(value) for value in param.values or ())
    return f"one of {values}" if values else "one of none"


def _counts(cost: Mapping[str, int]) -> str:
    return " ".join(f"{name} {count}" for name, count in sorted(cost.items()) if count) or "free"
