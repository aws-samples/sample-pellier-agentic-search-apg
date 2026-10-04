"""The shopper's active requirements, kept server-side across a conversation.

Anna asks for a gift "in stock, under $100, no candles". Her follow-up,
"which of those would you pick for a small kitchen?", states none of that,
and a reading of the follow-up alone drops the limits she still means. This
module keeps the limits the shopper stated, per verified principal and
session, and lays them under the next turn's reading: a follow-up overrides
only what it states, a release clears a limit, and a new conversation starts
clean.

Only the shopper's words reach the active set. What is remembered is the
turn's merged extractor reading, never the plan the tool ran: a ``max_price``
the agent chose as a tool argument applies to that one search and is never
carried as "your limit from earlier". Each remembered value records its
source, and the only source is the shopper.

Releases come from two places. The structured extractor reports what the
latest message lifts (``lifted``). A deterministic floor reads only explicit
phrases tied to a named limit ("ignore my budget", "drop the price limit",
"in stock or not", "include sold out"), so those hold without a model. It
never reads a generic phrase such as "show me anything else" or "any price
range you would suggest?": those are ordinary follow-ups.

The store is process-local: one worker's memory, bounded, keyed by the
verified principal and the session id together. A session whose principal
changes starts clean. A multi-worker deployment would need a shared store
to carry limits consistently.

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

# The one source a remembered value can have.
SOURCE_SHOPPER = "shopper"

_SESSIONS_MAX = 256

# The floor of releases read deterministically from the shopper's own words:
# an explicit verb or negation tied to a named limit, nothing generic. The
# structured extractor reports every other release in ``lifted``.
_RESET_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    (
        KIND_BUDGET,
        re.compile(
            r"\b(?:(?:ignore|forget|drop|skip|remove|lift) (?:my|the) "
            r"(?:budget|price (?:limit|cap|ceiling))|no price limit)\b",
            re.I,
        ),
    ),
    (
        KIND_STOCK,
        re.compile(
            r"\b(?:in stock or not|include (?:the )?sold[ -]out"
            r"|(?:does not|doesn'?t|need not|needn'?t) (?:have to |need to )?be in stock)\b",
            re.I,
        ),
    ),
)
# "Candles are fine now" releases one excluded value.
_ALLOW_AGAIN = re.compile(r"\b([a-z][a-z -]{1,30}?) (?:are|is) (?:fine|ok|okay|allowed)(?: now| again)?\b", re.I)
_VOCABULARY = frozenset(KNOWN_TAGS) | frozenset(KNOWN_MATERIALS)


@dataclass(frozen=True)
class ActiveRequirements:
    """The limits in force for a conversation, as the shopper stated them.

    ``sources`` names where each kept value came from, by kind. Only the
    shopper's reading reaches this set, so every entry is ``shopper``; the
    record is what makes that checkable.
    """

    price_max_usd: Optional[float] = None
    in_stock_only: bool = False
    exclusions: Tuple[str, ...] = ()
    categories: Tuple[str, ...] = ()
    sources: Dict[str, str] = field(default_factory=dict)

    def kinds(self) -> Tuple[str, ...]:
        """The kinds of limit this set holds, in the findings' order."""
        present = {
            KIND_BUDGET: self.price_max_usd is not None,
            KIND_STOCK: self.in_stock_only,
            KIND_EXCLUSIONS: bool(self.exclusions),
            KIND_DEPARTMENT: bool(self.categories),
        }
        return tuple(kind for kind in KINDS if present[kind])

    def is_empty(self) -> bool:
        return not self.kinds()


@dataclass
class TurnScope:
    """One turn's binding: whose session it belongs to and what it read.

    ``reading`` caches the structured extraction of the shopper's words so
    the second catalog tool in a turn reuses the first tool's reading.
    """

    session_id: Optional[str]
    message: str
    principal: Optional[str] = None
    reading: Optional[Dict[str, Any]] = None
    carried: List[str] = field(default_factory=list)


_turn: contextvars.ContextVar[Optional[TurnScope]] = contextvars.ContextVar(
    "pellier_active_requirements_turn", default=None
)
# Keyed by (verified principal, session id). Process-local; see the module docstring.
_by_session: "OrderedDict[Tuple[str, str], ActiveRequirements]" = OrderedDict()


def _key(principal: Optional[str], session_id: str) -> Tuple[str, str]:
    return (str(principal or ""), str(session_id))


def bind_turn(
    *,
    session_id: Optional[str],
    message: str,
    conversation_history: Optional[Sequence[Dict[str, Any]]],
    principal: Optional[str] = None,
) -> contextvars.Token:
    """Open the turn's scope.

    A conversation with no earlier shopper turn starts clean, and so does a
    session whose verified principal is not the one that stated the limits.
    """
    earlier = any(
        isinstance(item, dict) and item.get("role") == "user"
        for item in (conversation_history or [])
    )
    if session_id:
        own = _key(principal, session_id)
        for key in [key for key in _by_session if key[1] == own[1] and key != own]:
            _by_session.pop(key, None)
        if not earlier:
            _by_session.pop(own, None)
    return _turn.set(TurnScope(session_id=session_id, message=message, principal=principal))


def reset_turn(token: contextvars.Token) -> None:
    _turn.reset(token)


def current_turn() -> Optional[TurnScope]:
    return _turn.get()


def active(session_id: Optional[str], principal: Optional[str] = None) -> ActiveRequirements:
    """The requirements in force for this principal's session; empty for an unknown one."""
    if not session_id:
        return ActiveRequirements()
    return _by_session.get(_key(principal, session_id), ActiveRequirements())


def forget_session(session_id: Optional[str]) -> None:
    """Drop the session's limits under every principal."""
    if not session_id:
        return
    for key in [key for key in _by_session if key[1] == str(session_id)]:
        _by_session.pop(key, None)


def explicit_resets(message: str) -> set[str]:
    """The limits the shopper's words release: named kinds, or excluded values."""
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

    The reading wins wherever it states a limit; a release clears one;
    everything else carries over. Returns the merged reading and the kinds
    that were in force before this message, were not restated by it, and
    still apply: a restated value reads as stated, not carried.

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

    stated_price = merged.get("price_max_usd")
    if stated_price is None and KIND_BUDGET not in lifted:
        merged["price_max_usd"] = before.price_max_usd
    stated_stock = bool(merged.get("in_stock_only"))
    if not stated_stock and KIND_STOCK not in lifted:
        merged["in_stock_only"] = before.in_stock_only
    stated_exclusions = [
        str(value).lower() for value in (merged.get("exclusions") or []) if isinstance(value, str)
    ]
    exclusions = list(stated_exclusions)
    for value in before.exclusions:
        if value not in exclusions and value not in lifted:
            exclusions.append(value)
    merged["exclusions"] = exclusions
    stated_categories = list(merged.get("required_categories") or [])
    if not stated_categories and KIND_DEPARTMENT not in lifted:
        merged["required_categories"] = list(before.categories)
    merged.pop("lifted", None)

    carried: List[str] = []
    if (
        before.price_max_usd is not None
        and stated_price is None
        and merged.get("price_max_usd") == before.price_max_usd
    ):
        carried.append(KIND_BUDGET)
    if before.in_stock_only and not stated_stock and merged.get("in_stock_only"):
        carried.append(KIND_STOCK)
    if any(value in exclusions and value not in stated_exclusions for value in before.exclusions):
        carried.append(KIND_EXCLUSIONS)
    if (
        before.categories
        and not stated_categories
        and tuple(merged.get("required_categories") or ()) == before.categories
    ):
        carried.append(KIND_DEPARTMENT)
    return merged, carried


def remember(
    session_id: Optional[str],
    reading: Dict[str, Any],
    *,
    principal: Optional[str] = None,
) -> ActiveRequirements:
    """Keep the shopper's limits from one turn's merged reading, for the next turn.

    The reading is the shopper's words, merged with what they stated earlier.
    A plan's resolved values are never read here: an agent's ``max_price``
    argument applied to one search and is not the shopper's limit.
    """
    price = reading.get("price_max_usd")
    stated = ActiveRequirements(
        price_max_usd=float(price) if price is not None else None,
        in_stock_only=bool(reading.get("in_stock_only")),
        exclusions=tuple(str(value) for value in (reading.get("exclusions") or [])),
        categories=tuple(str(value) for value in (reading.get("required_categories") or [])),
    )
    requirements = ActiveRequirements(
        price_max_usd=stated.price_max_usd,
        in_stock_only=stated.in_stock_only,
        exclusions=stated.exclusions,
        categories=stated.categories,
        sources={kind: SOURCE_SHOPPER for kind in stated.kinds()},
    )
    if session_id:
        key = _key(principal, session_id)
        _by_session[key] = requirements
        _by_session.move_to_end(key)
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
            before=active(scope.session_id, scope.principal),
            message=scope.message,
        )
        scope.reading = merged
        scope.carried = carried
    return dict(scope.reading), list(scope.carried)


def remember_turn() -> None:
    """Keep the bound turn's merged reading for the session's next turn."""
    scope = _turn.get()
    if scope is None or scope.reading is None:
        return
    remember(scope.session_id, scope.reading, principal=scope.principal)
