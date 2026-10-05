"""Three identities per turn, kept deliberately distinct.

A workshop needs persona switching: an attendee clicks "Marco" and the
storefront tunes its copy, recommendations, and memory. That affordance is
useful and should stay. What must not happen is the demo persona becoming
the *authorization* principal, because then a UI dropdown decides what a
request is allowed to do.

Three fields, three jobs:

``principal_sub``
    The verified security identity — the Cognito ``sub`` from a validated
    token. This is the only field policy and ownership checks may use. It
    is ``None`` for an anonymous shopper, and ``None`` means "no verified
    identity", never "trust the persona instead".

``shopper_customer_id``
    The authorized domain identity — which customer's orders, returns, and
    preferences this turn may touch. Derived from the verified principal
    when one exists; only a demo persona in demo mode.

``demo_persona_id``
    Pure UI simulation context. Drives copy, curation, and which fixture
    story renders. Never an input to an authorization decision.

The distinction has a concrete failure mode behind it. AgentCore Memory
namespaces durable records by actor; if the namespace is keyed on the
persona while the token says someone else, one attendee's persona switch
reads another's memory, and the audit row names a principal that never
made the request.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# The verified principal for the turn currently executing.
#
# Deterministic tools run through `asyncio.to_thread` with the caller's
# context captured, the same way `db_query_log_var` reaches them, so a tool
# can read the acting identity without it being threaded through every
# signature. `services/chat.py` sets this once per turn.
#
# It holds `principal_sub` and nothing else. A persona id must never travel
# here: this value decides which database rows are writable, and a UI
# selection is not an authorization claim.
#
# Default `None` means anonymous, which the governed write path treats as
# "no scope" rather than "unrestricted".
principal_sub_var: ContextVar[Optional[str]] = ContextVar(
    "principal_sub_var", default=None
)


def current_principal_sub() -> Optional[str]:
    """Return the verified principal for the executing turn, if any."""
    return principal_sub_var.get()


# The verified Cognito username for the turn currently executing. A customer's
# own reads bind it for row-level security (``DatabaseService.principal_session``),
# so it is set beside ``principal_sub`` and, like it, never from a persona.
principal_username_var: ContextVar[Optional[str]] = ContextVar(
    "principal_username_var", default=None
)


def current_principal_username() -> Optional[str]:
    """Return the verified username for the executing turn, if any."""
    return principal_username_var.get()


# The verified customer scope for the turn currently executing.
#
# This is deliberately separate from the display persona and is populated only
# when a verified principal resolves to a customer mapping. It lets read-only
# deterministic tools refuse model-supplied customer identifiers before they
# reach Aurora.
authorized_customer_id_var: ContextVar[Optional[str]] = ContextVar(
    "authorized_customer_id_var", default=None
)


def current_authorized_customer_id() -> Optional[str]:
    """Return this turn's verified self-service customer scope, if any."""
    return authorized_customer_id_var.get()


# The correlation key for the turn currently executing.
#
# Travels the same way as the principal, and for the same reason: a
# deterministic tool that writes evidence needs the turn's id so a span query
# and a SQL query resolve the same turn. Threading it through every tool
# signature would mean touching every tool for a property none of them act on.
turn_id_var: ContextVar[Optional[str]] = ContextVar("turn_id_var", default=None)

# What the shopper actually typed this turn, and nothing earlier. The search
# tools plan from these words, never from the agent's rewritten query, so an
# agent cannot drop "no candles" by shortening its search. The limits stated
# in earlier turns are carried by ``services.active_requirements``.
shopper_words_var: ContextVar[Optional[str]] = ContextVar("shopper_words_var", default=None)


def current_turn_id() -> Optional[str]:
    """Return the correlation id for the executing turn, if any."""
    return turn_id_var.get()

# Which customer each sign-in name belongs to, read from
# ``pellier.customers.cognito_username`` when the app starts
# (:func:`load_customer_usernames_until_ready`). Until it is loaded, no username
# maps to a customer, so a verified shopper gets no customer scope: the read is
# refused, not widened.
_customer_by_username: Dict[str, str] = {}

_CUSTOMER_USERNAMES_SQL = "SELECT cognito_username, id FROM pellier.customers"

# How long the loader waits between reads while the customers cannot be read.
CUSTOMER_USERNAMES_RETRY_SECONDS = 10.0


def normalize_username(username: Optional[str]) -> Optional[str]:
    """The one form of a sign-in name: trimmed and lowercased, or ``None``.

    ``pellier.customers`` stores names in this form (a CHECK holds it), so the
    customer lookup and the row-level security binding compare like with like.
    """
    return str(username or "").strip().lower() or None


async def load_customer_usernames(db: Any) -> int:
    """Read the username-to-customer map from Aurora. Returns how many were read."""
    rows = await db.fetch_all(_CUSTOMER_USERNAMES_SQL)
    set_customer_usernames({str(row["cognito_username"]): str(row["id"]) for row in rows or []})
    return len(_customer_by_username)


async def load_customer_usernames_until_ready(
    db: Any, *, retry_seconds: float = CUSTOMER_USERNAMES_RETRY_SECONDS
) -> int:
    """Read the map, retrying until it holds at least one name.

    A database that cannot be read when the app starts (setup still running,
    or a schema from before the customers table) would otherwise leave every
    signed-in shopper with no customer scope until a restart. The first
    failure is logged as an error; the retries after it are quiet.
    """
    failures = 0
    while True:
        try:
            loaded = await load_customer_usernames(db)
            problem = "pellier.customers holds no sign-in names yet"
        except Exception as exc:  # noqa: BLE001 - retried, and the first one is logged
            loaded, problem = 0, f"{exc.__class__.__name__}: {exc}"
        if loaded:
            logger.info("✅ %d customer sign-in names loaded", loaded)
            return loaded
        log = logger.error if failures == 0 else logger.debug
        log(
            "Customer sign-in names could not be read (%s). Signed-in shoppers have "
            "no customer scope until they load; retrying every %.0f s.",
            problem,
            retry_seconds,
        )
        failures += 1
        await asyncio.sleep(retry_seconds)


def set_customer_usernames(mapping: Dict[str, str]) -> None:
    """Replace the username-to-customer map (the loader above, and tests)."""
    _customer_by_username.clear()
    _customer_by_username.update(
        {normalize_username(name): str(customer) for name, customer in mapping.items()
         if normalize_username(name)}
    )


def new_turn_id() -> str:
    """Mint a stable identifier for one shopper turn.

    Every turn gets one, minted server-side. This is what makes a receipt deep
    link reproducible: Pellier can hand the id to Observatory, and a reload
    resolves the same turn rather than whatever happens to be newest.

    Deliberately not derived from message position or display order — a
    positional id silently points at a different turn after any reordering,
    which is worse than having no link at all.

    Format is ``turn-<32 hex>``: uuid4 hex, prefixed so the value is
    self-describing in a URL, a log line, and a JSONB column.

    Lives here rather than in ``app.py`` because two paths now need it: the
    streamed route mints it before the stream opens, and the non-streaming
    ``chat()`` mints one when no turn is in scope. A second copy of the format
    would let the two drift.
    """
    return f"turn-{uuid.uuid4().hex}"


def customer_id_for_verified_username(username: Optional[str]) -> Optional[str]:
    """Map a verified Cognito username to its Aurora customer."""
    normalized = normalize_username(username)
    return _customer_by_username.get(normalized) if normalized else None


@dataclass(frozen=True)
class TurnIdentity:
    """The resolved identities for one turn.

    Attributes:
        principal_sub: Verified Cognito ``sub``, or ``None`` when
            anonymous. The only field valid for policy decisions.
        shopper_customer_id: Customer whose domain data this turn may
            read, or ``None``.
        demo_persona_id: UI persona label, or ``None``. Never
            authoritative.
        authenticated: True when a verified principal is present.
        persona_is_simulated: True when a persona is active without a
            verified principal backing it — i.e. the customer scope comes
            from a UI selection, not from a token.
        principal_username: Verified Cognito username, or ``None``. A
            customer's own reads name it for row-level security.
    """

    principal_sub: Optional[str] = None
    shopper_customer_id: Optional[str] = None
    demo_persona_id: Optional[str] = None
    authenticated: bool = False
    persona_is_simulated: bool = False
    principal_username: Optional[str] = None

    def memory_actor(self) -> str:
        """Return the actor id AgentCore Memory should namespace under.

        Prefers the verified principal. A demo persona never overrides a
        real identity: doing so would let a UI dropdown read another
        attendee's durable records. Falls back to the persona only when
        there is no verified principal at all — which is the demo case,
        and is reported as ``persona_is_simulated``.
        """
        if self.principal_sub:
            return self.principal_sub
        if self.demo_persona_id:
            return f"persona-{self.demo_persona_id}"
        return "anonymous"

    def authorization_principal(self) -> Optional[str]:
        """Return the only identity a policy check may use.

        ``None`` means unauthenticated. Callers must treat that as "deny
        or require login", never as "fall back to the persona".
        """
        return self.principal_sub

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for the turn payload and evidence surfaces."""
        return {
            "principalSub": self.principal_sub,
            "shopperCustomerId": self.shopper_customer_id,
            "demoPersonaId": self.demo_persona_id,
            "authenticated": self.authenticated,
            "personaIsSimulated": self.persona_is_simulated,
            "memoryActor": self.memory_actor(),
        }


def turn_principal(identity: TurnIdentity, *, workshop_session: bool) -> Dict[str, Any]:
    """The verified principal one turn runs as, for the Builder view.

    Read from the turn's resolved identity, never from the storefront's
    shopper choice: an anonymous turn has no customer here even when a
    shopper's edit is on screen.

    Args:
        identity: The turn's resolved identities.
        workshop_session: True when the server's own cookie says the
            one-click shopper sign-in established this session.
    """
    if not identity.authenticated:
        return {"authenticated": False, "customerId": None, "signInMethod": None}
    return {
        "authenticated": True,
        "customerId": identity.shopper_customer_id,
        "signInMethod": "workshop" if workshop_session else "cognito",
    }


def resolve_turn_identity(
    *,
    user: Optional[Dict[str, Any]] = None,
    requested_customer_id: Optional[str] = None,
) -> TurnIdentity:
    """Split one request's identities into their three distinct roles.

    Args:
        user: The verified-user dict from ``services.auth``
            (``{sub, email, given_name, access_token}``), or ``None`` for
            an anonymous caller. May also carry a ``customer_id`` that the
            storefront merged in from the active persona.
        requested_customer_id: A customer id supplied by the request body.
            Treated as a *demo persona* selection, not as an identity
            claim — the caller does not get to assert who they are.

    Returns:
        A :class:`TurnIdentity`. When a verified principal exists it always
        wins for authorization and memory namespacing; the persona only
        colours the experience.
    """
    user = user or {}
    principal_sub = (user.get("sub") or "").strip() or None
    persona_id = str(requested_customer_id or "").strip() or None
    # Normalized once, here: the customer lookup and the row-level security
    # binding must name the same person in the same form.
    principal_username = normalize_username(user.get("username")) if principal_sub else None

    # The customer scope follows the verified principal when we have one.
    # Without a principal, a persona selection is the only scope available
    # and the turn is explicitly marked as simulated.
    if principal_sub:
        shopper_customer_id = customer_id_for_verified_username(principal_username)
        persona_is_simulated = False
    else:
        shopper_customer_id = persona_id
        persona_is_simulated = persona_id is not None

    if persona_is_simulated and persona_id:
        logger.debug(
            "Turn scoped to simulated persona %s (no verified principal); "
            "this scope is not valid for authorization",
            persona_id,
        )

    return TurnIdentity(
        principal_sub=principal_sub,
        shopper_customer_id=shopper_customer_id,
        demo_persona_id=persona_id,
        authenticated=principal_sub is not None,
        persona_is_simulated=persona_is_simulated,
        principal_username=principal_username,
    )
