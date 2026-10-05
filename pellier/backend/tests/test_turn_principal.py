"""The verified principal on every turn: from the signed token, never the shopper choice.

Choosing a shopper on the home page signs in with that shopper's demo account.
The Builder view then shows, on every turn, who the server verified: the
``principal`` on ``turn_start``. It is read from the token and the server's own
sign-in cookie. The customer id the storefront sends with the turn is the
shopper's edit and is never the principal.
"""

from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

import app as app_module
from routes.auth import SIGN_IN_METHOD_WORKSHOP
from services.auth import session_cookie_names

SIGN_IN_METHOD_COOKIE = session_cookie_names("shopper").sign_in_method


def _turn_start(body: str) -> Dict[str, Any]:
    events = [json.loads(m) for m in re.findall(r"^data: (.*)$", body, re.M)]
    return next(e for e in events if e.get("type") == "turn_start")


@pytest.fixture
def chat(monkeypatch: pytest.MonkeyPatch):
    """POST one turn as ``user``, with or without the workshop sign-in cookie."""

    async def _stream(**_kwargs: Any) -> AsyncIterator[Dict[str, Any]]:
        yield {"type": "complete", "response": {"response": "hello", "products": [], "suggestions": []}}

    class _Svc:
        chat_stream = staticmethod(_stream)

    monkeypatch.setattr(app_module.settings, "USE_AGENTCORE_RUNTIME", False, raising=False)
    monkeypatch.setattr(app_module, "chat_service", _Svc())

    def post(
        user: Optional[Dict[str, Any]], *, workshop: bool = False, customer_id: str | None = None,
    ) -> Dict[str, Any]:
        app_module.app.dependency_overrides[app_module.get_current_user] = lambda: user
        client = TestClient(app_module.app)
        if workshop:
            client.cookies.set(SIGN_IN_METHOD_COOKIE, SIGN_IN_METHOD_WORKSHOP)
        try:
            response = client.post("/api/chat/stream", json={
                "message": "my ticket", "conversation_history": [], "session_id": "sess-p",
                "customer_id": customer_id,
            })
        finally:
            app_module.app.dependency_overrides.pop(app_module.get_current_user, None)
        assert response.status_code == 200
        return _turn_start(response.text)["principal"]

    return post


def _shopper(username: str) -> Dict[str, Any]:
    return {"sub": f"sub-{username}", "username": username, "access_token": f"jwt-{username}"}


def test_choosing_a_shopper_yields_their_verified_identity_on_the_next_turn(chat) -> None:
    assert chat(_shopper("theo"), workshop=True, customer_id="CUST-THEO") == {
        "authenticated": True, "customerId": "CUST-THEO", "signInMethod": "workshop",
    }


def test_switching_shopper_changes_the_principal(chat) -> None:
    first = chat(_shopper("theo"), workshop=True, customer_id="CUST-THEO")
    second = chat(_shopper("anna"), workshop=True, customer_id="CUST-ANNA")
    assert (first["customerId"], second["customerId"]) == ("CUST-THEO", "CUST-ANNA")


def test_the_principal_follows_the_token_not_the_edit_on_screen(chat) -> None:
    """A token for Theo with Jessica's edit selected is still Theo."""
    assert chat(_shopper("theo"), workshop=True, customer_id="CUST-JESSICA")["customerId"] == "CUST-THEO"


def test_the_signed_out_state_has_no_principal(chat) -> None:
    for customer_id in (None, "CUST-THEO"):
        assert chat(None, customer_id=customer_id) == {
            "authenticated": False, "customerId": None, "signInMethod": None,
        }
    # The cookie alone proves nothing: without a verified token there is no one.
    assert chat(None, workshop=True)["authenticated"] is False


def test_a_typed_password_sign_in_is_not_labelled_workshop(chat) -> None:
    """Nadia signs in with her password and is no shopper: no customer, not workshop."""
    assert chat(_shopper("nadia")) == {
        "authenticated": True, "customerId": None, "signInMethod": "cognito",
    }
