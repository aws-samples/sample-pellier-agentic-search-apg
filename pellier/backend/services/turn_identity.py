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

USERNAME_TO_CUSTOMER_ID = {
    "marco": "CUST-MARCO",
    "anna": "CUST-ANNA",
    "theo": "CUST-THEO",
    "jessica": "CUST-JESSICA",
}


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
    """Map a verified Cognito username to its seeded Aurora customer."""
    normalized = str(username or "").strip().casefold()
    return USERNAME_TO_CUSTOMER_ID.get(normalized)


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
    """

    principal_sub: Optional[str] = None
    shopper_customer_id: Optional[str] = None
    demo_persona_id: Optional[str] = None
    authenticated: bool = False
    persona_is_simulated: bool = False

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

    # The customer scope follows the verified principal when we have one.
    # Without a principal, a persona selection is the only scope available
    # and the turn is explicitly marked as simulated.
    if principal_sub:
        shopper_customer_id = customer_id_for_verified_username(
            user.get("username")
        )
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
    )
