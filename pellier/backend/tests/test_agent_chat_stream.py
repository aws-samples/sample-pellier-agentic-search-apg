"""Unit tests for ``routes.agent`` — the ``/api/agent/*`` surface (Task 3.5).

Validates Requirements 3.4.1–3.4.4 and the Design "Error Handling" row
"JWT expires mid-SSE stream" / Sequence Diagram #2 note. No live
Cognito, Bedrock, or AgentCore SDK traffic: the orchestrator call is
stubbed via ``run_agent``, ``CognitoAuthService.extract_user`` uses a
synthetic RSA signer (same pattern as ``test_preferences_api.py`` /
``test_auth_routes.py``), and the in-memory fallback store is the only
backend for ``AgentCoreMemory``.

Covered assertions (from tasks.md Task 3.5 "Test verification"):

  * mid-stream token expiry does not abort the stream
  * session continuity works with ``session_id`` passed in subsequent
    calls
  * anonymous requests fall to ``anon:{session_id}`` namespace

Additional coverage keeps the route contract honest:

  * first SSE event is ``event: session`` with the resolved id
    (Req 3.4.3)
  * authenticated requests route the orchestrator under the verified
    ``user_id`` and memory writes land in
    ``user:{user_id}-session-{session_id}`` (Req 3.4.2)
  * ``GET /api/agent/session/{id}`` returns the turn history the
    stream just wrote (Req 3.4.4)
  * a foreign user cannot read another user's session history through
    the same ``session_id`` (Req 4.3.2)

Runnable from the repo root per ``pytest.ini``:
    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_agent_chat_stream.py -v
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from config import settings
import services.agentcore_memory as memory_module
import services.agentcore_runtime as runtime_module
from services.agentcore_identity import (
    AgentCoreIdentityService,
    SESSION_ID_HEADER,
    get_agentcore_identity_service,
)
from services.agentcore_memory import AgentCoreMemory
from services.cognito_auth import (
    ACCESS_TOKEN_COOKIE,
    CognitoAuthService,
    get_cognito_auth_service,
)
from routes.agent import router as agent_router
from routes.user import get_agentcore_memory


# ---------------------------------------------------------------------------
# Test pool identity — matches test_auth_routes.py / test_preferences_api.py
# ---------------------------------------------------------------------------

POOL_ID = "us-west-2_TESTPOOL"
REGION = "us-west-2"
CLIENT_ID = "test-client-id"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}"


# ---------------------------------------------------------------------------
# Synthetic RSA signer + JWKS (same pattern as test_cognito_auth.py)
# ---------------------------------------------------------------------------


class _Signer:
    """Mint Cognito-shaped access tokens signed by a local RSA key.

    Kept identical to the signer in ``test_preferences_api.py`` so both
    test files exercise ``CognitoAuthService`` the same way.
    """

    def __init__(self, kid: Optional[str] = None) -> None:
        self.kid = kid or f"kid-{uuid.uuid4().hex[:8]}"
        self._private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._pem = self._private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def public_jwk(self) -> Dict[str, Any]:
        public_pem = self._private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        public_key = serialization.load_pem_public_key(public_pem)
        jwk: Dict[str, Any] = json.loads(RSAAlgorithm.to_jwk(public_key))
        jwk["kid"] = self.kid
        jwk["use"] = "sig"
        jwk["alg"] = "RS256"
        return jwk

    def sign(self, claims: Dict[str, Any]) -> str:
        return jwt.encode(
            claims,
            self._pem,
            algorithm="RS256",
            headers={"kid": self.kid},
        )


def _access_claims(
    *,
    sub: str = "cognito-sub-chat",
    email: str = "shopper@example.com",
    given_name: str = "Avery",
    exp_offset: int = 3600,
) -> Dict[str, Any]:
    """Return a claims dict for a Cognito *access* token.

    ``exp_offset`` is additive so tests that need an already-expired
    token can pass a negative value (``exp_offset=-60`` = expired 60
    seconds ago).
    """
    now = int(time.time())
    return {
        "sub": sub,
        "email": email,
        "given_name": given_name,
        "iss": ISSUER,
        "client_id": CLIENT_ID,
        "token_use": "access",
        "iat": now,
        "exp": now + exp_offset,
        "auth_time": now,
    }


# ---------------------------------------------------------------------------
# SSE parsing helper
# ---------------------------------------------------------------------------


def _parse_sse(stream_body: str) -> List[Dict[str, Any]]:
    """Parse an SSE response body into ``[{event, data}, ...]``.

    Each event is a blank-line-delimited block of ``event:`` / ``data:``
    lines. We only need the ``event`` name and the JSON-decoded ``data``
    payload for the assertions below.
    """
    events: List[Dict[str, Any]] = []
    for block in re.split(r"\n\n+", stream_body.strip()):
        if not block.strip():
            continue
        event_name: Optional[str] = None
        data_lines: List[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        if event_name and data_lines:
            payload = json.loads("".join(data_lines))
            events.append({"event": event_name, "data": payload})
    return events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _wire_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the router at our synthetic Cognito pool for the test run."""
    monkeypatch.setattr(settings, "COGNITO_POOL_ID", POOL_ID, raising=False)
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", POOL_ID, raising=False)
    monkeypatch.setattr(settings, "COGNITO_REGION", REGION, raising=False)
    monkeypatch.setattr(settings, "COGNITO_CLIENT_ID", CLIENT_ID, raising=False)
    # Force the in-process (C4) path so no runtime SDK is ever invoked.
    monkeypatch.setattr(settings, "USE_AGENTCORE_RUNTIME", False, raising=False)


@pytest.fixture(autouse=True)
def _reset_memory_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the module-level fallback dicts between tests and force the
    SDK-unavailable path so ``AgentCoreMemory`` uses its in-memory
    store. Mirrors ``test_agentcore_memory.py`` / ``test_preferences_api.py``.
    """
    monkeypatch.setattr(memory_module, "_SESSION_STORE", {})
    monkeypatch.setattr(memory_module, "_PREFS_STORE", {})
    monkeypatch.setattr(memory_module.settings, "AGENTCORE_MEMORY_ID", None)


@pytest.fixture
def signer() -> _Signer:
    return _Signer(kid="agent-chat-kid")


@pytest.fixture
def auth_service(signer: _Signer) -> CognitoAuthService:
    """JWKS-backed service wired to the synthetic signer."""
    svc = CognitoAuthService(pool_id=POOL_ID, region=REGION, client_id=CLIENT_ID)
    svc._fetch_jwks = lambda: {"keys": [signer.public_jwk()]}  # type: ignore[assignment]
    return svc


@pytest.fixture
def identity_service(auth_service: CognitoAuthService) -> AgentCoreIdentityService:
    """Identity service wired to the synthetic JWKS-backed auth svc."""
    return AgentCoreIdentityService(cognito_auth=auth_service)


@pytest.fixture
def memory() -> AgentCoreMemory:
    """Fresh ``AgentCoreMemory`` shared across the test's request cycle."""
    return AgentCoreMemory()


@pytest.fixture
def agent_calls(monkeypatch: pytest.MonkeyPatch) -> List[Dict[str, Any]]:
    """Stub ``services.agentcore_runtime.run_agent`` so no Bedrock /
    Strands agent is actually constructed.

    Records each invocation's kwargs so tests can assert what the route
    forwarded to the orchestrator. Returns a canned response tagged
    with the session id so mid-stream assertions can verify the stream
    drained fully.
    """
    calls: List[Dict[str, Any]] = []

    async def _fake_run_agent(
        message: str,
        session_id: str,
        user_id: Optional[str] = None,
    ) -> str:
        calls.append(
            {"message": message, "session_id": session_id, "user_id": user_id}
        )
        return f"stubbed response for '{message}' in {session_id}"

    # Patch the symbol the route module bound at import time, not just
    # the one on the ``runtime_module`` namespace, so the route-level
    # reference picks up the stub.
    monkeypatch.setattr(runtime_module, "run_agent", _fake_run_agent)
    import routes.agent as agent_module

    monkeypatch.setattr(agent_module, "run_agent", _fake_run_agent)
    return calls


@pytest.fixture
def client(
    identity_service: AgentCoreIdentityService,
    auth_service: CognitoAuthService,
    memory: AgentCoreMemory,
) -> TestClient:
    """FastAPI test app with only the agent router mounted.

    Keeps the test isolated from ``app.py`` so no lifespan
    (database, embeddings) runs. Dependency overrides substitute the
    synthetic JWKS-backed services and the in-memory ``AgentCoreMemory``.
    """
    app = FastAPI()
    app.include_router(agent_router)
    app.dependency_overrides[get_agentcore_identity_service] = (
        lambda: identity_service
    )
    app.dependency_overrides[get_cognito_auth_service] = lambda: auth_service
    app.dependency_overrides[get_agentcore_memory] = lambda: memory
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /api/agent/chat — session/chunk/done envelope (Req 3.4.1, 3.4.3)
# ---------------------------------------------------------------------------


def test_chat_emits_session_then_chunk_then_done_events(
    client: TestClient, signer: _Signer, agent_calls: List[Dict[str, Any]]
) -> None:
    """Req 3.4.1 + 3.4.3: the stream emits a ``session`` event first
    (so the client can persist the id), then ``chunk``(s), then
    ``done``. ``session_id`` is auto-generated when the body omits it.
    """
    token = signer.sign(_access_claims(sub="user-one"))

    with client.stream(
        "POST",
        "/api/agent/chat",
        json={"message": "show me linen"},
        cookies={ACCESS_TOKEN_COOKIE: token},
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        body = resp.read().decode("utf-8")

    events = _parse_sse(body)
    assert [e["event"] for e in events] == ["session", "chunk", "done"]

    session_event = events[0]
    assert session_event["data"]["authenticated"] is True
    # Auto-generated session_id is a non-empty string (uuid4 hex in practice).
    auto_session_id = session_event["data"]["session_id"]
    assert isinstance(auto_session_id, str) and len(auto_session_id) > 0
    assert session_event["data"]["namespace"] == (
        f"user-user-one-session-{auto_session_id}"
    )

    assert "stubbed response" in events[1]["data"]["content"]
    assert events[2]["data"]["session_id"] == auto_session_id

    # The orchestrator was called exactly once with the verified user id.
    assert agent_calls == [
        {
            "message": "show me linen",
            "session_id": auto_session_id,
            "user_id": "user-one",
        }
    ]


def test_chat_anonymous_request_uses_anon_namespace(
    client: TestClient, agent_calls: List[Dict[str, Any]], memory: AgentCoreMemory
) -> None:
    """Test-verification bullet: anonymous requests fall to
    ``anon:{session_id}`` (Req 4.3.3). No JWT means no user id and no
    ``user:`` prefix.
    """
    with client.stream(
        "POST",
        "/api/agent/chat",
        json={"message": "hi there"},
    ) as resp:
        assert resp.status_code == 200
        body = resp.read().decode("utf-8")

    events = _parse_sse(body)
    session_event = next(e for e in events if e["event"] == "session")
    assert session_event["data"]["authenticated"] is False

    session_id = session_event["data"]["session_id"]
    assert session_event["data"]["namespace"] == f"anon-{session_id}"

    # Orchestrator was called with ``user_id=None`` so ``run_agent_on_runtime``
    # can fall back to the "anonymous" tag itself (C5 contract).
    assert agent_calls[0]["user_id"] is None

    # The turn pair was written under the anon namespace, not any
    # ``user:`` namespace.
    import asyncio

    history = asyncio.run(memory.get_session_history(f"anon-{session_id}"))
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_chat_session_continuity_across_turns(
    client: TestClient, signer: _Signer, agent_calls: List[Dict[str, Any]]
) -> None:
    """Test-verification bullet: session continuity works with
    ``session_id`` passed in subsequent calls. Turn 2 sees turn 1's
    history under the same namespace.
    """
    token = signer.sign(_access_claims(sub="user-cont"))

    # Turn 1 — no session_id, auto-generated.
    with client.stream(
        "POST",
        "/api/agent/chat",
        json={"message": "show me linen"},
        cookies={ACCESS_TOKEN_COOKIE: token},
    ) as resp:
        events1 = _parse_sse(resp.read().decode("utf-8"))
    session_id = events1[0]["data"]["session_id"]

    # Turn 2 — caller echoes session_id back.
    with client.stream(
        "POST",
        "/api/agent/chat",
        json={"message": "only under $100", "session_id": session_id},
        cookies={ACCESS_TOKEN_COOKIE: token},
    ) as resp:
        events2 = _parse_sse(resp.read().decode("utf-8"))

    # Both turns landed on the same session id and namespace.
    session_event_2 = next(e for e in events2 if e["event"] == "session")
    assert session_event_2["data"]["session_id"] == session_id
    assert session_event_2["data"]["namespace"] == (
        f"user-user-cont-session-{session_id}"
    )

    # The orchestrator saw both messages on the same session.
    assert [c["session_id"] for c in agent_calls] == [session_id, session_id]
    assert [c["message"] for c in agent_calls] == [
        "show me linen",
        "only under $100",
    ]


def test_chat_session_id_via_header_is_honoured(
    client: TestClient, signer: _Signer, agent_calls: List[Dict[str, Any]]
) -> None:
    """The identity service picks ``X-Session-Id`` when the body omits
    ``session_id``. Keeps older clients that rely purely on headers
    working alongside the body field contract.
    """
    token = signer.sign(_access_claims(sub="user-hdr"))
    with client.stream(
        "POST",
        "/api/agent/chat",
        json={"message": "first turn"},
        cookies={ACCESS_TOKEN_COOKIE: token},
        headers={SESSION_ID_HEADER: "header-session-abc"},
    ) as resp:
        events = _parse_sse(resp.read().decode("utf-8"))

    session_event = events[0]
    assert session_event["data"]["session_id"] == "header-session-abc"
    assert session_event["data"]["namespace"] == (
        "user-user-hdr-session-header-session-abc"
    )
    assert agent_calls[0]["session_id"] == "header-session-abc"


# ---------------------------------------------------------------------------
# One-shot JWT validation (Design "Error Handling" row + Sequence #2)
# ---------------------------------------------------------------------------


def test_mid_stream_token_expiry_does_not_abort_the_stream(
    client: TestClient,
    signer: _Signer,
    agent_calls: List[Dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test-verification bullet: the JWT is validated once at stream
    start; if it expires mid-stream the response still completes.

    Simulated here by patching ``run_agent`` to advance time past the
    token's ``exp`` mid-call. A second JWT check would now reject the
    token; the route must NOT re-check, so the stream still reaches
    ``done`` intact.
    """
    # Token valid for exactly 2 seconds. The stub below advances the
    # clock by 10 seconds so a re-check would fail; the route must not
    # perform one.
    token = signer.sign(_access_claims(sub="user-expire", exp_offset=2))

    original_time = time.time

    async def _expiring_run_agent(
        message: str,
        session_id: str,
        user_id: Optional[str] = None,
    ) -> str:
        agent_calls.append(
            {"message": message, "session_id": session_id, "user_id": user_id}
        )
        # Advance the clock past the token's exp. Any JWT re-check
        # after this point would raise ``ExpiredSignatureError``.
        monkeypatch.setattr(
            time, "time", lambda: original_time() + 3600, raising=False
        )
        return f"response after clock skip for {session_id}"

    import routes.agent as agent_module

    monkeypatch.setattr(agent_module, "run_agent", _expiring_run_agent)
    monkeypatch.setattr(runtime_module, "run_agent", _expiring_run_agent)

    with client.stream(
        "POST",
        "/api/agent/chat",
        json={"message": "long-running turn"},
        cookies={ACCESS_TOKEN_COOKIE: token},
    ) as resp:
        assert resp.status_code == 200
        body = resp.read().decode("utf-8")

    events = _parse_sse(body)
    # All three events arrived — no ``error`` frame, no truncated stream.
    assert [e["event"] for e in events] == ["session", "chunk", "done"]
    assert "response after clock skip" in events[1]["data"]["content"]

    # The agent saw the verified ``user_id`` despite the clock skip —
    # authentication happened exactly once at stream start.
    assert agent_calls[0]["user_id"] == "user-expire"


def test_chat_requires_non_empty_message(client: TestClient) -> None:
    """FastAPI's pydantic validator SHALL 422 on a missing / empty
    message body so the route never reaches the JWT step with no
    content to stream.
    """
    resp = client.post("/api/agent/chat", json={"message": ""})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/agent/session/{id} — history retrieval (Req 3.4.4)
# ---------------------------------------------------------------------------


def test_get_session_returns_turns_after_chat_writes_them(
    client: TestClient, signer: _Signer, agent_calls: List[Dict[str, Any]]
) -> None:
    """Req 3.4.4: the history endpoint returns the turns the chat
    stream just appended under the same JWT.
    """
    token = signer.sign(_access_claims(sub="user-hist"))

    with client.stream(
        "POST",
        "/api/agent/chat",
        json={"message": "first"},
        cookies={ACCESS_TOKEN_COOKIE: token},
    ) as resp:
        events = _parse_sse(resp.read().decode("utf-8"))
    session_id = events[0]["data"]["session_id"]

    resp = client.get(
        f"/api/agent/session/{session_id}",
        cookies={ACCESS_TOKEN_COOKIE: token},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["session_id"] == session_id
    assert payload["namespace"] == f"user-user-hist-session-{session_id}"
    assert payload["authenticated"] is True

    turns = payload["turns"]
    assert len(turns) == 2
    assert turns[0] == {"role": "user", "content": "first"}
    assert turns[1]["role"] == "assistant"
    assert "stubbed response" in turns[1]["content"]


def test_get_session_scoped_per_user(
    client: TestClient, signer: _Signer, agent_calls: List[Dict[str, Any]]
) -> None:
    """Req 4.3.2: user B cannot read user A's session history even
    when both callers hit the endpoint with the same ``session_id``.

    The namespace is keyed per-user, so B's GET sees an empty list —
    the ``user:B-session-{sid}`` key has no entries.
    """
    alice_token = signer.sign(_access_claims(sub="alice"))
    bob_token = signer.sign(_access_claims(sub="bob"))

    # Alice streams one turn under a known session_id.
    with client.stream(
        "POST",
        "/api/agent/chat",
        json={"message": "alice turn", "session_id": "shared-sid"},
        cookies={ACCESS_TOKEN_COOKIE: alice_token},
    ):
        pass

    # Alice sees her turns.
    alice_resp = client.get(
        "/api/agent/session/shared-sid",
        cookies={ACCESS_TOKEN_COOKIE: alice_token},
    )
    assert alice_resp.status_code == 200
    assert len(alice_resp.json()["turns"]) == 2

    # Bob's token + same session_id → empty history, his own namespace.
    bob_resp = client.get(
        "/api/agent/session/shared-sid",
        cookies={ACCESS_TOKEN_COOKIE: bob_token},
    )
    assert bob_resp.status_code == 200
    assert bob_resp.json()["namespace"] == "user-bob-session-shared-sid"
    assert bob_resp.json()["turns"] == []


def test_get_session_anonymous_reads_anon_namespace(
    client: TestClient, agent_calls: List[Dict[str, Any]]
) -> None:
    """An anonymous GET resolves to ``anon:{session_id}`` — the same
    namespace the anonymous POST wrote to. This keeps anon shoppers'
    multi-turn threads working without any sign-in.
    """
    # Anonymous POST populates anon:{sid}.
    with client.stream(
        "POST",
        "/api/agent/chat",
        json={"message": "anon turn", "session_id": "anon-sid"},
    ):
        pass

    resp = client.get("/api/agent/session/anon-sid")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["namespace"] == "anon-anon-sid"
    assert payload["authenticated"] is False
    assert len(payload["turns"]) == 2
