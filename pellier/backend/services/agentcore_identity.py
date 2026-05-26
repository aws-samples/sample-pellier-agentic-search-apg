"""
AgentCoreIdentityService — verified user context for the orchestrator.

Challenge 9.2 (Requirements 4.3.1–4.3.3). Builds a ``UserContext`` that
pairs the verified Cognito ``user_id`` (when present) with a stable
``session_id`` and the exact namespace string ``agentcore_memory`` keys
on. Callers hand the context straight into
``AgentCoreMemory.append_session_turn`` /
``AgentCoreMemory.get_session_history`` so a single definition of the
namespace format lives in one place.

This is the backend half of Challenge 9's four-file capstone:

    9.1  services/cognito_auth.py
    9.2  services/agentcore_identity.py         ← this file
    9.3  frontend/src/utils/auth.ts
    9.4  frontend/src/components/{AuthModal,PreferencesModal}.tsx

Key design choices (Req 4.3):

  * Authenticated namespace:  ``user-{user_id}-session-{session_id}``
  * Anonymous namespace:      ``anon-{session_id}``
  * Dashes (not colons) because AgentCore session IDs must match
    ``[a-zA-Z0-9][a-zA-Z0-9-_]*`` — colons are rejected at the API.
  * These MUST match ``services/agentcore_memory.py`` byte-for-byte —
    ``AgentCoreMemory`` keys on the raw string, so any drift silently
    fragments session history.
  * ``user_id`` is only ever populated from ``request.state.user``
    (set by ``require_user``) or from a successful
    ``CognitoAuthService.extract_user`` call. It is never inferred
    from a header the client controls. This is the Req 4.3.2
    "no cross-user bleed" guarantee.
  * Anonymous ``session_id`` is read from an ``X-Session-Id`` request
    header or a ``session_id`` cookie before falling back to a freshly
    minted uuid4. The route layer is responsible for echoing the
    resolved id back to the client (Req 3.4.3 first-SSE-event contract)
    so subsequent turns land in the same namespace.
  * Per Req 4.3.3 there is deliberately no ``anon:`` → ``user:`` merge
    at sign-in. The anon namespace is left orphaned and reclaimed by
    AgentCore Memory's TTL sweep.

The workshop ``solutions/the-ledger/services/agentcore_identity.py`` file
mirrors the CHALLENGE 9.2 block below byte-for-byte (enforced by Task
7.4).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import Request

from models import VerifiedUser
from services.cognito_auth import (
    CognitoAuthService,
    get_cognito_auth_service,
)

logger = logging.getLogger(__name__)


# === CHALLENGE 9.2: AgentCore Identity — START ===
# Requirements 4.3.1–4.3.3 and Design "services/agentcore_identity.py".
#
# Participants delete this block and reimplement ``AgentCoreIdentityService``
# so the orchestrator can scope ``agentcore_memory`` calls by verified
# user. The tests at ``tests/test_agentcore_identity.py`` build synthetic
# FastAPI ``Request`` objects with and without ``request.state.user`` to
# exercise the authenticated + anonymous branches.
#
# Namespace scheme (must match services/agentcore_memory.py byte-for-byte):
#
#     user-{user_id}-session-{session_id}   authenticated sessions
#     anon-{session_id}                     anonymous sessions
#
# (Dashes, not colons — AgentCore session IDs must match
# [a-zA-Z0-9][a-zA-Z0-9-_]*.)
#
# ⏩ SHORT ON TIME? Run:
#    cp solutions/the-ledger/services/agentcore_identity.py pellier/backend/services/agentcore_identity.py

SESSION_ID_HEADER = "X-Session-Id"
SESSION_ID_COOKIE = "session_id"


@dataclass(frozen=True)
class UserContext:
    """Verified identity + session namespace handed to the orchestrator.

    ``user_id`` is ``None`` for anonymous requests (Req 4.3.3). ``namespace``
    is the exact string ``AgentCoreMemory`` keys on — never rebuild it at
    the call site; pass this context through.
    """

    user_id: Optional[str]
    session_id: str
    namespace: str


class AgentCoreIdentityService:
    """Resolve a verified ``UserContext`` from an incoming FastAPI request.

    The service is stateless. It delegates JWT validation to
    ``CognitoAuthService`` (Challenge 9.1) and only owns the namespace
    computation so the scheme lives in exactly one place.
    """

    def __init__(
        self,
        cognito_auth: Optional[CognitoAuthService] = None,
    ) -> None:
        self._cognito_auth = cognito_auth

    def _auth_service(self) -> CognitoAuthService:
        """Lazily resolve the shared ``CognitoAuthService``.

        Holding a lazy reference (rather than constructing at import
        time) keeps tests that build isolated ``AgentCoreIdentityService``
        instances free of module-global side effects while production
        code keeps sharing the JWKS cache.
        """
        if self._cognito_auth is not None:
            return self._cognito_auth
        return get_cognito_auth_service()

    # ------------------------------------------------------------------
    # Namespace helpers
    # ------------------------------------------------------------------

    @staticmethod
    def build_namespace(user_id: Optional[str], session_id: str) -> str:
        """Return the ``agentcore_memory`` namespace for the given pair.

        Kept static + public so ``/api/agent/session/{id}`` and any
        future tooling can recompute the exact string without going
        through a full ``UserContext`` resolution.

        Uses dashes (not colons) as separators because AgentCore
        session IDs must match ``[a-zA-Z0-9][a-zA-Z0-9-_]*``.
        """
        if user_id:
            return f"user-{user_id}-session-{session_id}"
        return f"anon-{session_id}"

    @staticmethod
    def _resolve_session_id(request: Request) -> str:
        """Return a stable session id for ``request``.

        Priority:
          1. ``X-Session-Id`` request header (set by the frontend on
             subsequent turns)
          2. ``session_id`` cookie (set by the route layer for anon
             shoppers so page reloads keep the same thread)
          3. Freshly generated uuid4 (first-ever turn)
        """
        header_value = request.headers.get(SESSION_ID_HEADER) or request.headers.get(
            SESSION_ID_HEADER.lower()
        )
        if header_value:
            return header_value.strip()

        cookie_value = request.cookies.get(SESSION_ID_COOKIE)
        if cookie_value:
            return cookie_value.strip()

        return uuid.uuid4().hex

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_verified_user_context(self, request: Request) -> UserContext:
        """Return the ``UserContext`` for ``request``.

        Resolution order for ``user_id``:
          1. ``request.state.user`` — populated by ``require_user`` on
             protected routes. The common fast path: JWT validation
             already happened once per request, no second network hit.
          2. ``CognitoAuthService.extract_user`` — falls through on
             public routes (``/api/products``, ``/api/search``) so an
             authenticated shopper gets personalised results without
             every handler re-declaring ``Depends(require_user)``.
          3. ``None`` — treated as anonymous (Req 4.3.3).
        """
        user: Optional[VerifiedUser] = getattr(request.state, "user", None)

        if user is None:
            try:
                user = await self._auth_service().extract_user(request)
            except Exception as exc:  # pragma: no cover - defensive
                # extract_user already swallows HTTPException. Any other
                # exception (e.g., Cognito not configured) should still
                # let the caller proceed anonymously rather than 500.
                logger.warning(
                    "AgentCoreIdentity anonymous fallback after extract_user "
                    "failure: %s",
                    exc.__class__.__name__,
                )
                user = None

        session_id = self._resolve_session_id(request)
        user_id = user.user_id if user is not None else None
        namespace = self.build_namespace(user_id, session_id)

        return UserContext(
            user_id=user_id,
            session_id=session_id,
            namespace=namespace,
        )


# Process-wide service instance. Kept module-level so callers (route
# handlers, the orchestrator) share the same ``CognitoAuthService``
# JWKS cache by default. Tests construct their own instance to stay
# isolated from module state.
_default_service: Optional[AgentCoreIdentityService] = None


def get_agentcore_identity_service() -> AgentCoreIdentityService:
    """FastAPI-friendly accessor for the shared ``AgentCoreIdentityService``."""
    global _default_service
    if _default_service is None:
        _default_service = AgentCoreIdentityService()
    return _default_service
# === CHALLENGE 9.2: AgentCore Identity — END ===
