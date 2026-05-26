"""Unit tests for ``services.agentcore_identity.AgentCoreIdentityService``
(Task 3.2).

Validates Requirement 4.3 (AgentCore Identity integration) without any
live Cognito call. Tests build synthetic ``fastapi.Request`` objects
with and without ``request.state.user`` and assert the returned
``UserContext`` carries the right namespace.

Covered assertions (from tasks.md Task 3.2 "Test verification"):

  * authenticated request yields ``user-{user_id}-session-{session_id}``
    namespace
  * unauthenticated request yields ``anon-{session_id}`` namespace
  * ``user_id`` in ``UserContext`` equals ``request.state.user.user_id``

Plus the "Done when" assertion: session_id is stable across a request
(so the orchestrator and ``agentcore_memory`` key on the same string).

Async methods are dispatched via ``asyncio.run`` per the repo convention
in ``test_cognito_auth.py`` (no pytest-asyncio plugin is installed in
the backend venv).

Runnable from the repo root:
    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_agentcore_identity.py -v
"""

from __future__ import annotations

import asyncio
from typing import Any, Coroutine, Dict, List, Optional, TypeVar

import pytest
from fastapi import Request

from models import VerifiedUser
from services.agentcore_identity import (
    SESSION_ID_COOKIE,
    SESSION_ID_HEADER,
    AgentCoreIdentityService,
    UserContext,
)
from services.cognito_auth import CognitoAuthService


T = TypeVar("T")


def _run(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine from a sync test without needing a plugin."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Request builders
# ---------------------------------------------------------------------------


def _make_request(
    headers: Optional[Dict[str, str]] = None,
    cookies: Optional[Dict[str, str]] = None,
    state_user: Optional[VerifiedUser] = None,
) -> Request:
    """Construct a minimal ASGI ``Request`` for the service to inspect.

    ``state_user`` stands in for what ``require_user`` would have set on
    a protected route. Leaving it ``None`` exercises the anonymous path.
    """
    raw_headers: List[tuple[bytes, bytes]] = []
    for k, v in (headers or {}).items():
        raw_headers.append((k.lower().encode(), v.encode()))
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        raw_headers.append((b"cookie", cookie_header.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/agent/chat",
        "headers": raw_headers,
        "query_string": b"",
        "client": ("test", 0),
    }
    req = Request(scope)
    if state_user is not None:
        req.state.user = state_user
    return req


def _verified_user(
    user_id: str = "cognito-sub-123",
    email: str = "shopper@example.com",
    given_name: str = "Avery",
) -> VerifiedUser:
    return VerifiedUser(user_id=user_id, email=email, given_name=given_name)


class _StubAuth(CognitoAuthService):
    """``CognitoAuthService`` stand-in that short-circuits extract_user.

    ``AgentCoreIdentityService`` only reaches ``extract_user`` when
    ``request.state.user`` is missing. The stub lets a test pretend the
    request carried a JWT cookie without minting real tokens (that path
    is covered exhaustively in ``test_cognito_auth.py``).
    """

    def __init__(self, user: Optional[VerifiedUser]) -> None:
        # Deliberately skip the base class __init__: no JWKS plumbing
        # is needed because we override extract_user wholesale.
        self._user = user

    async def extract_user(self, request: Request) -> Optional[VerifiedUser]:  # type: ignore[override]
        return self._user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def identity_service_anon() -> AgentCoreIdentityService:
    """Identity service whose Cognito layer never produces a user."""
    return AgentCoreIdentityService(cognito_auth=_StubAuth(user=None))


@pytest.fixture
def identity_service_with_cookie_user() -> AgentCoreIdentityService:
    """Identity service whose Cognito layer returns a user from cookies.

    Used to prove the fall-through path: on a public route that does
    NOT use ``Depends(require_user)``, the service still resolves the
    authenticated namespace when an ``access_token`` cookie is present.
    """
    return AgentCoreIdentityService(
        cognito_auth=_StubAuth(user=_verified_user(user_id="cookie-auth-user"))
    )


# ---------------------------------------------------------------------------
# Authenticated path — Req 4.3.1, 4.3.2
# ---------------------------------------------------------------------------


def test_authenticated_request_yields_user_namespace(
    identity_service_anon: AgentCoreIdentityService,
) -> None:
    """``request.state.user`` set → ``user:{uid}-session-{sid}`` namespace."""
    user = _verified_user(user_id="verified-abc")
    req = _make_request(
        headers={SESSION_ID_HEADER: "session-xyz"},
        state_user=user,
    )

    ctx = _run(identity_service_anon.get_verified_user_context(req))

    assert ctx.user_id == "verified-abc"
    assert ctx.session_id == "session-xyz"
    assert ctx.namespace == "user-verified-abc-session-session-xyz"


def test_user_id_equals_request_state_user_user_id(
    identity_service_anon: AgentCoreIdentityService,
) -> None:
    """Spec check: ``UserContext.user_id == request.state.user.user_id``."""
    user = _verified_user(user_id="eq-check-uid")
    req = _make_request(
        cookies={SESSION_ID_COOKIE: "sess-from-cookie"},
        state_user=user,
    )

    ctx = _run(identity_service_anon.get_verified_user_context(req))

    assert ctx.user_id == req.state.user.user_id == "eq-check-uid"


def test_authenticated_request_prefers_state_user_over_extract(
    identity_service_with_cookie_user: AgentCoreIdentityService,
) -> None:
    """When both are available, ``request.state.user`` wins.

    This avoids a second JWT decode on protected routes where
    ``require_user`` already ran; it is also the Req 4.3.2
    "no cross-user bleed" guarantee: the id used to scope memory is
    the one already validated by the middleware, not one re-derived
    from raw request headers.
    """
    state_user = _verified_user(user_id="state-user")
    req = _make_request(
        headers={SESSION_ID_HEADER: "s1"},
        state_user=state_user,
    )

    ctx = _run(identity_service_with_cookie_user.get_verified_user_context(req))

    assert ctx.user_id == "state-user"
    assert ctx.namespace == "user-state-user-session-s1"


def test_cookie_token_falls_through_on_unprotected_route(
    identity_service_with_cookie_user: AgentCoreIdentityService,
) -> None:
    """Public route (no ``require_user``) still lights up personalisation.

    ``state.user`` is missing, so the service calls ``extract_user``
    and lands on the authenticated namespace when the cookie is valid.
    """
    req = _make_request(headers={SESSION_ID_HEADER: "sess-pub"})

    ctx = _run(identity_service_with_cookie_user.get_verified_user_context(req))

    assert ctx.user_id == "cookie-auth-user"
    assert ctx.namespace == "user-cookie-auth-user-session-sess-pub"


# ---------------------------------------------------------------------------
# Anonymous path — Req 4.3.3
# ---------------------------------------------------------------------------


def test_unauthenticated_request_yields_anon_namespace(
    identity_service_anon: AgentCoreIdentityService,
) -> None:
    """No state user + no token → ``anon-{session_id}`` namespace."""
    req = _make_request(headers={SESSION_ID_HEADER: "anon-sess-1"})

    ctx = _run(identity_service_anon.get_verified_user_context(req))

    assert ctx.user_id is None
    assert ctx.session_id == "anon-sess-1"
    assert ctx.namespace == "anon-anon-sess-1"


def test_unauthenticated_request_generates_session_id_when_absent(
    identity_service_anon: AgentCoreIdentityService,
) -> None:
    """Truly first-ever turn: no header, no cookie → uuid4 hex."""
    req = _make_request()

    ctx = _run(identity_service_anon.get_verified_user_context(req))

    assert ctx.user_id is None
    assert ctx.session_id
    assert len(ctx.session_id) == 32  # uuid4().hex
    assert ctx.namespace == f"anon-{ctx.session_id}"


def test_unauthenticated_request_reuses_session_cookie(
    identity_service_anon: AgentCoreIdentityService,
) -> None:
    """Cookie-carried session id survives page reloads for anon shoppers."""
    req = _make_request(cookies={SESSION_ID_COOKIE: "anon-cookie-sess"})

    ctx = _run(identity_service_anon.get_verified_user_context(req))

    assert ctx.user_id is None
    assert ctx.session_id == "anon-cookie-sess"
    assert ctx.namespace == "anon-anon-cookie-sess"


def test_header_session_id_wins_over_cookie(
    identity_service_anon: AgentCoreIdentityService,
) -> None:
    """Header is the explicit signal from the frontend and takes priority."""
    req = _make_request(
        headers={SESSION_ID_HEADER: "from-header"},
        cookies={SESSION_ID_COOKIE: "from-cookie"},
    )

    ctx = _run(identity_service_anon.get_verified_user_context(req))

    assert ctx.session_id == "from-header"


# ---------------------------------------------------------------------------
# Namespace format — guards against drift from agentcore_memory.py
# ---------------------------------------------------------------------------


def test_build_namespace_matches_agentcore_memory_scheme() -> None:
    """Exact-format check — must track ``agentcore_memory.py`` by hand.

    ``AgentCoreMemory`` keys on the literal string; if this format drifts,
    session history silently fragments across the two modules.
    """
    assert (
        AgentCoreIdentityService.build_namespace("u1", "s1")
        == "user-u1-session-s1"
    )
    assert AgentCoreIdentityService.build_namespace(None, "s1") == "anon-s1"
    assert AgentCoreIdentityService.build_namespace("", "s1") == "anon-s1"


def test_user_context_is_immutable() -> None:
    """Frozen dataclass — prevents downstream handlers from mutating
    the scoping tuple and accidentally reading from a different
    namespace than they wrote to."""
    ctx = UserContext(user_id="u", session_id="s", namespace="user-u-session-s")
    with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
        ctx.user_id = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Defensive: malformed request.state.user shouldn't 500
# ---------------------------------------------------------------------------


def test_missing_state_user_triggers_extract(
    identity_service_with_cookie_user: AgentCoreIdentityService,
) -> None:
    """``request.state.user`` unset → fall through to ``extract_user``.

    Regression guard: an earlier draft raised ``AttributeError`` when
    ``state.user`` was missing instead of falling through to the
    Cognito extractor. ``getattr(request.state, 'user', None)`` fixes it.
    """
    req = _make_request(headers={SESSION_ID_HEADER: "sess-fallthrough"})

    ctx = _run(identity_service_with_cookie_user.get_verified_user_context(req))

    assert ctx.user_id == "cookie-auth-user"
    assert ctx.namespace == "user-cookie-auth-user-session-sess-fallthrough"
