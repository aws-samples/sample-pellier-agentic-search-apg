"""What the shopper requires, kept across chat turns as application state.

The agent chooses search words; this module keeps the shopper's requirements;
PostgreSQL checks products against them. Each storefront turn reads the
shopper's own message, never the agent's rewritten query, into a proposed
update. Deterministic code applies it and writes a new revision of
``pellier.shopping_requirements``. The search tools read the turn's snapshot
from :data:`active_requirements_var`, so an agent cannot drop "no candles" by
shortening its query, and "show me more" keeps everything.

Rules for an update:
  * Fields the message does not mention stay as they were.
  * A change applies only with a quote from the shopper's message that supports
    it. An unsupported change is ignored, recorded, and the turn is marked
    ``unclear`` so the answer asks instead of guessing.
  * A new shopping request starts empty, also only with a supporting quote.
  * A failed read keeps the previous requirements and marks the turn.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

STATUS_PARSED = "parsed"
STATUS_UNCLEAR = "unclear"
STATUS_FAILED = "extraction_failed"

_MIN_QUOTE_CHARS = 3
_MAX_UNENFORCED = 5
_MAX_UNENFORCED_CHARS = 40


@dataclass(frozen=True)
class Requirements:
    """One revision of a shopper's requirements for the active shopping request.

    Attributes:
        session_id: The chat session these requirements belong to, or None
            when the turn has no session and nothing is stored.
        request_id: Increments when the shopper starts a new shopping request.
        revision: Increments on every turn; 0 means nothing recorded yet.
        turn_id: The turn that wrote this revision.
        status: ``parsed``, ``unclear`` or ``extraction_failed``.
        price_max_usd: The budget the shopper stated, or None.
        in_stock_only: True when the shopper asked for items in stock.
        exclusions: Tags or materials the shopper refused; enforced in SQL.
        unenforced_exclusions: Refusals no catalog field records; admitted.
        required_categories: Departments the shopper limited the request to.
        preferences: Tags the shopper prefers; relaxed before anything else.
        inferred_categories: Departments the model guessed this turn; recorded.
        ignored_changes: Fields a proposed update named without support.
    """

    session_id: Optional[str]
    request_id: int = 1
    revision: int = 0
    turn_id: Optional[str] = None
    status: str = STATUS_PARSED
    price_max_usd: Optional[float] = None
    in_stock_only: bool = False
    exclusions: Tuple[str, ...] = ()
    unenforced_exclusions: Tuple[str, ...] = ()
    required_categories: Tuple[str, ...] = ()
    preferences: Tuple[str, ...] = ()
    inferred_categories: Tuple[str, ...] = ()
    ignored_changes: Tuple[str, ...] = field(default=())

    def to_payload(self) -> Dict[str, Any]:
        """The stored requirement fields, as the planner prompt and the table see them."""
        return {
            "price_max_usd": self.price_max_usd,
            "in_stock_only": self.in_stock_only,
            "exclusions": list(self.exclusions),
            "unenforced_exclusions": list(self.unenforced_exclusions),
            "required_categories": list(self.required_categories),
            "preferences": list(self.preferences),
            "inferred_categories": list(self.inferred_categories),
        }

    def as_extraction(self, *, search_words: str) -> Dict[str, Any]:
        """The snapshot in the shape ``search_plan.build_plan`` validates.

        The agent's search words become the soft signal for ranking; every
        requirement comes from this snapshot, never from the agent.
        """
        return {
            "price_max_usd": self.price_max_usd,
            "in_stock_only": self.in_stock_only,
            "required_categories": list(self.required_categories),
            "categories": list(self.inferred_categories),
            "tags": list(self.preferences),
            "exclusions": list(self.exclusions),
            "unsupported_exclusions": list(self.unenforced_exclusions),
            "soft_signal": search_words,
            "extraction_status": self.status,
        }

    def to_record(self) -> Dict[str, Any]:
        """Which revision a receipt enforced."""
        return {
            "session_id": self.session_id,
            "request_id": self.request_id,
            "revision": self.revision,
            "turn_id": self.turn_id,
            "status": self.status,
        }


active_requirements_var: ContextVar[Optional[Requirements]] = ContextVar(
    "active_requirements", default=None
)


def _normalize(text: str) -> str:
    return " ".join(str(text).replace("’", "'").lower().split())


def _supported(quotes: Dict[str, Any], name: str, message: str) -> bool:
    quote = quotes.get(name)
    if not isinstance(quote, str):
        return False
    quote = _normalize(quote)
    return len(quote) >= _MIN_QUOTE_CHARS and quote in _normalize(message)


def _price(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return float(value)


def _merge(
    current: Tuple[str, ...], added: List[str], limit: Optional[int] = None
) -> Tuple[str, ...]:
    merged = list(current)
    for value in added:
        if value not in merged:
            merged.append(value)
    return tuple(merged[:limit] if limit else merged)


def _clean(values: Any, allowed: List[str]) -> Optional[Tuple[str, ...]]:
    """Known values in canonical spelling, or None when the field was not a list."""
    if not isinstance(values, list):
        return None
    canonical = {str(value).lower(): str(value) for value in allowed}
    cleaned: List[str] = []
    for value in values:
        match = canonical.get(str(value).strip().lower()) if isinstance(value, str) else None
        if match and match not in cleaned:
            cleaned.append(match)
    return tuple(cleaned)


def _split(values: Any) -> Tuple[List[str], List[str]]:
    from services.structured_extract import _split_exclusions

    checkable, unsupported = _split_exclusions(values if isinstance(values, list) else [])
    return checkable, [phrase[:_MAX_UNENFORCED_CHARS] for phrase in unsupported]


def _apply_fields(base: Requirements, update: Dict[str, Any], quotes: Dict[str, Any],
                  message: str) -> Tuple[Requirements, List[str]]:
    from services.structured_extract import KNOWN_CATEGORIES, KNOWN_TAGS

    changes: Dict[str, Any] = {}
    ignored: List[str] = []

    def take(name: str, value: Any) -> None:
        if _supported(quotes, name, message):
            changes.update(value)
        else:
            ignored.append(name)

    price = _price(update.get("price_max_usd"))
    if price is not None:
        take("price_max_usd", {"price_max_usd": price})
    if update.get("remove_budget") is True:
        take("remove_budget", {"price_max_usd": None})
    if isinstance(update.get("in_stock_only"), bool):
        take("in_stock_only", {"in_stock_only": update["in_stock_only"]})
    departments = _clean(update.get("required_categories"), KNOWN_CATEGORIES)
    if departments is not None:
        take("required_categories", {"required_categories": departments})
    preferences = _clean(update.get("preferences"), KNOWN_TAGS)
    if preferences is not None:
        take("preferences", {"preferences": preferences})
    added, unsupported = _split([*(update.get("add_exclusions") or []),
                                 *(update.get("unsupported_exclusions") or [])])
    if added or unsupported:
        take("add_exclusions", {
            "exclusions": _merge(base.exclusions, added),
            "unenforced_exclusions": _merge(
                base.unenforced_exclusions, unsupported, _MAX_UNENFORCED
            ),
        })
    removed = {_normalize(v) for v in update.get("remove_exclusions") or [] if isinstance(v, str)}
    if removed:
        kept = changes.get("exclusions", base.exclusions)
        kept_unenforced = changes.get("unenforced_exclusions", base.unenforced_exclusions)
        take("remove_exclusions", {
            "exclusions": tuple(v for v in kept if v not in removed),
            "unenforced_exclusions": tuple(v for v in kept_unenforced if v not in removed),
        })
    return replace(base, **changes), ignored


def apply_update(current: Requirements, update: Dict[str, Any], message: str, *,
                 turn_id: Optional[str]) -> Requirements:
    """Apply a proposed update to the current requirements, by the module's rules.

    Args:
        current: The latest stored revision (revision 0 when nothing is stored).
        update: The planner's proposal for this message.
        message: The shopper's own message; every change must quote it.
        turn_id: The turn writing the new revision.

    Returns:
        The next revision. Unsupported changes are left out and named in
        ``ignored_changes``, which also marks the revision ``unclear``.
    """
    from services.structured_extract import KNOWN_CATEGORIES

    quotes = update.get("quotes") if isinstance(update.get("quotes"), dict) else {}
    base, ignored = current, []
    if update.get("change") == "new_request":
        if _supported(quotes, "new_request", message):
            base = Requirements(session_id=current.session_id, request_id=current.request_id + 1)
        else:
            ignored.append("new_request")
    if update.get("change") in ("update", "new_request"):
        base, field_ignored = _apply_fields(base, update, quotes, message)
        ignored.extend(field_ignored)
    inferred = _clean(update.get("categories"), KNOWN_CATEGORIES) or ()
    return replace(
        base,
        revision=current.revision + 1,
        turn_id=turn_id,
        status=STATUS_UNCLEAR if ignored else STATUS_PARSED,
        inferred_categories=inferred,
        ignored_changes=tuple(ignored),
    )


def failed_turn(current: Requirements, *, turn_id: Optional[str]) -> Requirements:
    """A turn whose message could not be read keeps every earlier requirement."""
    return replace(
        current, revision=current.revision + 1, turn_id=turn_id,
        status=STATUS_FAILED, inferred_categories=(), ignored_changes=(),
    )


_SELECT_LATEST = """
    SELECT revision, request_id, turn_id, status, requirements
      FROM pellier.shopping_requirements
     WHERE session_id = %s
     ORDER BY revision DESC
     LIMIT 1
"""

_INSERT = """
    INSERT INTO pellier.shopping_requirements
        (session_id, revision, request_id, turn_id, status, requirements, ignored_changes)
    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
"""


async def load_latest(db: Any, session_id: str) -> Requirements:
    """The session's latest revision, or an empty one when none is stored."""
    row = await db.fetch_one(_SELECT_LATEST, session_id)
    if not row:
        return Requirements(session_id=session_id)
    stored = row["requirements"]
    stored = json.loads(stored) if isinstance(stored, str) else dict(stored or {})
    return Requirements(
        session_id=session_id,
        request_id=int(row["request_id"]),
        revision=int(row["revision"]),
        turn_id=row.get("turn_id"),
        status=str(row["status"]),
        price_max_usd=_price(stored.get("price_max_usd")),
        in_stock_only=bool(stored.get("in_stock_only")),
        exclusions=tuple(stored.get("exclusions") or ()),
        unenforced_exclusions=tuple(stored.get("unenforced_exclusions") or ()),
        required_categories=tuple(stored.get("required_categories") or ()),
        preferences=tuple(stored.get("preferences") or ()),
    )


async def save(db: Any, requirements: Requirements) -> None:
    """Append one revision. Raises if the write fails; the caller decides."""
    await db.execute_query(
        _INSERT,
        requirements.session_id,
        requirements.revision,
        requirements.request_id,
        requirements.turn_id,
        requirements.status,
        json.dumps(requirements.to_payload()),
        json.dumps(list(requirements.ignored_changes)),
    )


ExtractUpdate = Callable[[str, Dict[str, Any]], Dict[str, Any]]


async def resolve_for_turn(db: Any, *, session_id: Optional[str], message: str,
                           turn_id: Optional[str], extract_update: ExtractUpdate) -> Requirements:
    """Read this turn's message into the next revision and store it.

    A turn without a session starts from nothing and is not stored. A storage
    failure is logged and the turn still enforces the revision it computed.
    """
    stored = bool(db is not None and session_id)
    current = await load_latest(db, session_id) if stored else Requirements(session_id=session_id)
    try:
        update = await asyncio.to_thread(extract_update, message, current.to_payload())
    except Exception as exc:
        logger.warning("requirements extraction failed: %s", exc)
        update = {"extraction_status": STATUS_FAILED}
    if update.get("extraction_status") == STATUS_FAILED:
        nxt = failed_turn(current, turn_id=turn_id)
    else:
        nxt = apply_update(current, update, message, turn_id=turn_id)
    if stored:
        try:
            await save(db, nxt)
        except Exception as exc:
            logger.warning("requirements revision %s not stored: %s", nxt.revision, exc)
    return nxt
