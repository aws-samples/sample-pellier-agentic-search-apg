"""Security contract for the public trace HTTP boundary."""

from fastapi.testclient import TestClient

import app as app_module
from models import VerifiedUser
from services import otel_trace_extractor
from services.cognito_auth import require_user


def _authenticated_client() -> TestClient:
    app_module.app.dependency_overrides[require_user] = lambda: VerifiedUser(
        user_id="cognito-owner",
        email="owner@example.com",
        given_name="Marco",
    )
    return TestClient(app_module.app)


def test_waterfall_requires_authentication() -> None:
    client = TestClient(app_module.app)

    response = client.get(
        "/api/traces/waterfall",
        params={"session_id": "session-owned-by-a-shopper"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "auth_failed"}


def test_waterfall_filters_with_authenticated_owner(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_waterfall(*, session_id: str, user_id: str) -> dict:
        captured.update(session_id=session_id, user_id=user_id)
        return {
            "spans": [],
            "totalMs": 0,
            "specialistRoute": "",
            "waterfall": [],
            "span_count": 0,
            "otel_enabled": True,
        }

    monkeypatch.setattr(otel_trace_extractor, "get_waterfall_data", fake_waterfall)
    client = _authenticated_client()
    try:
        response = client.get(
            "/api/traces/waterfall",
            params={"session_id": "owned-session"},
        )
    finally:
        app_module.app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert captured == {
        "session_id": "owned-session",
        "user_id": "cognito-owner",
    }


def test_waterfall_does_not_echo_internal_exception(monkeypatch) -> None:
    def fail_waterfall(*, session_id: str, user_id: str) -> dict:
        raise RuntimeError("private prompt and shopper context")

    monkeypatch.setattr(otel_trace_extractor, "get_waterfall_data", fail_waterfall)
    client = _authenticated_client()
    try:
        response = client.get(
            "/api/traces/waterfall",
            params={"session_id": "owned-session"},
        )
    finally:
        app_module.app.dependency_overrides.pop(require_user, None)

    payload = response.json()
    assert response.status_code == 200
    assert payload["otel_enabled"] is False
    assert payload["reason"] == (
        "Telemetry unavailable. See docs/troubleshooting-otel.md."
    )
    assert "private prompt" not in response.text
