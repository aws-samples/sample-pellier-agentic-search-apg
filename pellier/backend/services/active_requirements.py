"""The shopper's active requirements, kept server-side across a conversation.

Anna asks for a gift "in stock, under $100, no candles". Her follow-up,
"which of those would you pick for a small kitchen?", states none of that,
and a reading of the follow-up alone drops the limits she still means. This
module keeps the limits the last search plan applied, per session, and lays
them under the next turn's reading: a follow-up overrides only what it
states, an explicit reset ("ignore my budget", "show me anything") clears a
limit, and a new conversation starts clean.

Both catalog tools on the in-process rail read the same turn requirements,
so the fallback from ``search_products`` to ``browse_department`` cannot lose
them either. The managed rail has no server-side reading; its agent passes
the limits as tool arguments.

The per-turn scope is a ``ContextVar`` holding one object the chat stream
creates before the agent runs. ``asyncio.to_thread`` copies the context into
the Strands worker, so every tool call in the turn shares that object and
the first reading of the shopper's words serves them all.
"""

from __future__ import annotations

import contextvars
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services.catalog_vocabulary import KNOWN_MATERIALS, KNOWN_TAGS

# The kinds of limit a shopper can carry, reset or override.
KIND_BUDGET = "budget"
KIND_STOCK = "stock"
KIND_EXCLUSIONS = "exclusions"
KIND_DEPARTMENT = "department"
KIND_ALL = "all"
KINDS = (KIND_BUDGET, KIND_STOCK, KIND_EXCLUSIONS, KIND_DEPARTMENT)

_SESSIONS_MAX = 256

# The resets the brief names, read deterministically from the shopper's own
# words. The structured extractor reports other releases in ``lifted``; this
# table is the floor that holds without a model.
_RESET_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    (KIND_ALL, re.compile(r"\b(show me anything|anything goes|no limits|ignore (?:my|the|all) limits)\b", re.I)),
    (KIND_BUDGET, re.compile(r"\b((?:ignore|forget|drop|skip) (?:my|the) budget|no budget|any price|no price limit)\b", re.I)),
    (KIND_STOCK, re.compile(r"\b(in stock or not|(?:does not|doesn'?t|need not|needn'?t) (?:have to |need to )?be in stock)\b", re.I)),
)
# "Candles are fine now" releases one excluded value.
_ALLOW_AGAIN = re.compile(r"\b([a-z][a-z -]{1,30}?) (?:are|is) (?:fine|ok|okay|allowed)(?: now| again)?\b", re.I)
_VOCABULARY = frozenset(KNOWN_TAGS) | frozenset(KNOWN_MATERIALS)


@dataclass(frozen=True)
class ActiveRequirements:
    """The limits in force for a conversation, as the last plan applied them."""

    price_max_usd: Optional[float] = None
    in_stock_only: bool = False
    exclusions: Tuple[str, ...] = ()
    categories: Tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return (
            self.price_max_usd is None
            and not self.in_stock_only
            and not self.exclusions
            and not self.categories
        )


@dataclass
class TurnScope:
    """One turn's binding: which session it belongs to and what it read.

    ``reading`` caches the structured extraction of the shopper's words so
    the second catalog tool in a turn reuses the first tool's reading.
    """

    session_id: Optional[str]
    message: str
    reading: Optional[Dict[str, Any]] = None
    carried: List[str] = field(default_factory=list)


_turn: contextvars.ContextVar[Optional[TurnScope]] = contextvars.ContextVar(
    "pellier_active_requirements_turn", default=None
)
_by_session: "OrderedDict[str, ActiveRequirements]" = OrderedDict()


def bind_turn(
    *,
    session_id: Optional[str],
    message: str,
    conversation_history: Optional[Sequence[Dict[str, Any]]],
) -> contextvars.Token:
    """Open the turn's scope. A conversation with no earlier shopper turn starts clean."""
    earlier = any(
        isinstance(item, dict) and item.get("role") == "user"
        for item in (conversation_history or [])
    )
    if session_id and not earlier:
        _by_session.pop(session_id, None)
    return _turn.set(TurnScope(session_id=session_id, message=message))


def reset_turn(token: contextvars.Token) -> None:
    _turn.reset(token)


def current_turn() -> Optional[TurnScope]:
    return _turn.get()


def active(session_id: Optional[str]) -> ActiveRequirements:
    """The requirements in force for ``session_id``; empty for an unknown or missing one."""
    if not session_id:
        return ActiveRequirements()
    return _by_session.get(session_id, ActiveRequirements())


def forget_session(session_id: Optional[str]) -> None:
    if session_id:
        _by_session.pop(session_id, None)


def explicit_resets(message: str) -> set[str]:
    """The limits the shopper's words release: kinds, ``all``, or excluded values."""
    text = str(message or "")
    lifted: set[str] = set()
    for kind, pattern in _RESET_PATTERNS:
        if pattern.search(text):
            lifted.add(kind)
    for match in _ALLOW_AGAIN.finditer(text):
        phrase = match.group(1).strip().lower()
        for candidate in (phrase, phrase[:-1] if phrase.endswith("s") else phrase):
            if candidate in _VOCABULARY:
                lifted.add(candidate)
    return lifted


def merge(
    extracted: Dict[str, Any],
    *,
    before: ActiveRequirements,
    message: str,
) -> Tuple[Dict[str, Any], List[str]]:
    """Lay the active requirements under one turn's reading.

    The reading wins wherever it states a limit; a stated reset clears one;
    everything else carries over. Returns the merged reading and the kinds
    that were in force before this message and still are.

    Args:
        extracted: The structured extractor's output for this turn. Its
            ``lifted`` list names what the latest message released.
        before: The requirements in force before this message.
        message: The shopper's words, for the deterministic resets.
    """
    merged = dict(extracted)
    lifted = {str(value).lower() for value in (extracted.get("lifted") or []) if isinstance(value, str)}
    lifted |= explicit_resets(message)
    if KIND_ALL in lifted:
        before = ActiveRequirements()

    if merged.get("price_max_usd") is None and KIND_BUDGET not in lifted:
        merged["price_max_usd"] = before.price_max_usd
    if not merged.get("in_stock_only") and KIND_STOCK not in lifted:
        merged["in_stock_only"] = before.in_stock_only
    stated = [str(value).lower() for value in (merged.get("exclusions") or []) if isinstance(value, str)]
    if KIND_EXCLUSIONS not in lifted:
        for value in before.exclusions:
            if value not in stated and value not in lifted:
                stated.append(value)
    merged["exclusions"] = stated
    if not merged.get("required_categories") and KIND_DEPARTMENT not in lifted:
        merged["required_categories"] = list(before.categories)
    merged.pop("lifted", None)

    carried: List[str] = []
    if before.price_max_usd is not None and merged.get("price_max_usd") == before.price_max_usd:
        carried.append(KIND_BUDGET)
    if before.in_stock_only and merged.get("in_stock_only"):
        carried.append(KIND_STOCK)
    if before.exclusions and any(value in stated for value in before.exclusions):
        carried.append(KIND_EXCLUSIONS)
    if before.categories and tuple(merged.get("required_categories") or ()) == before.categories:
        carried.append(KIND_DEPARTMENT)
    return merged, carried


def remember(session_id: Optional[str], plan: Dict[str, Any]) -> ActiveRequirements:
    """Keep the limits the plan that just ran applied, for the next turn."""
    hard = plan.get("hard_constraints") or {}
    price = hard.get("price_max_usd")
    categories = (
        tuple(str(value) for value in (hard.get("categories") or []))
        if plan.get("category_source") == "shopper"
        else ()
    )
    requirements = ActiveRequirements(
        price_max_usd=float(price) if price is not None else None,
        in_stock_only=bool(hard.get("in_stock_only")),
        exclusions=tuple(str(value) for value in (plan.get("exclusions") or [])),
        categories=categories,
    )
    if session_id:
        _by_session[session_id] = requirements
        _by_session.move_to_end(session_id)
        while len(_by_session) > _SESSIONS_MAX:
            _by_session.popitem(last=False)
    return requirements


def turn_requirements(read: Any) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """The requirements a catalog tool applies this turn, read once and merged.

    ``read`` produces the structured extraction of the shopper's words; it
    runs once per turn and its result is shared by every tool in the turn.
    Outside a bound turn the reading is returned as it is, with nothing
    carried.

    Returns:
        The merged extraction (``None`` when no reading ran) and the carried
        kinds.
    """
    scope = _turn.get()
    if scope is None:
        return read(), []
    if scope.reading is None:
        merged, carried = merge(
            read() or {},
            before=active(scope.session_id),
            message=scope.message,
        )
        scope.reading = merged
        scope.carried = carried
    return dict(scope.reading), list(scope.carried)


def remember_plan(plan: Dict[str, Any]) -> None:
    """Remember the plan that ran for the bound turn's session."""
    scope = _turn.get()
    if scope is not None:
        remember(scope.session_id, plan)
