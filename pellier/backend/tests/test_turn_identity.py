"""Tests for the three-way identity split and managed trace correlation.

Audit finding B7: Pellier preferred a request ``customer_id`` persona
over Cognito identity for memory scoping. Persona switching is a useful
workshop affordance, but a demo persona must never become the
authorization principal or the memory namespace key — otherwise a UI
dropdown decides which durable records a turn reads, and the audit row
names a principal that never made the request.

Audit finding B9: the managed receipt summarized instead of correlating.
It now carries the trace and request IDs plus the query that reaches the
authoritative CloudWatch record, while still refusing to synthesize spans
it did not observe.
"""

from __future__ import annotations

import pytest

from services.turn_identity import (
    TurnIdentity,
    authorized_customer_id_var,
    current_authorized_customer_id,
    resolve_turn_identity,
)


# ---------------------------------------------------------------------------
# The verified principal always wins
# ---------------------------------------------------------------------------
def test_verified_principal_is_the_memory_actor_not_the_persona() -> None:
    """The regression guard for B7.

    A persona selection must not redirect memory to another actor's
    namespace when a real token is present.
    """
    identity = resolve_turn_identity(
        user={"sub": "cognito-sub-real", "username": "marco"},
        requested_customer_id="CUST-ANNA",
    )

    assert identity.memory_actor() == "cognito-sub-real"
    assert identity.principal_sub == "cognito-sub-real"


def test_only_the_verified_sub_is_an_authorization_principal() -> None:
    identity = resolve_turn_identity(
        user={"sub": "cognito-sub-real"}, requested_customer_id="CUST-ANNA"
    )

    assert identity.authorization_principal() == "cognito-sub-real"


def test_anonymous_turn_has_no_authorization_principal() -> None:
    """``None`` means unauthenticated, never "use the persona instead"."""
    identity = resolve_turn_identity(requested_customer_id="CUST-MARCO")

    assert identity.authorization_principal() is None
    assert identity.authenticated is False


def test_persona_only_turn_is_flagged_as_simulated() -> None:
    identity = resolve_turn_identity(requested_customer_id="CUST-MARCO")

    assert identity.persona_is_simulated is True
    assert identity.demo_persona_id == "CUST-MARCO"
    assert identity.shopper_customer_id == "CUST-MARCO"


def test_authenticated_turn_is_not_simulated() -> None:
    identity = resolve_turn_identity(
        user={"sub": "sub-1", "username": "marco"}
    )

    assert identity.persona_is_simulated is False


def test_persona_namespace_is_prefixed_so_it_cannot_collide_with_a_sub() -> None:
    """A persona actor id must be structurally distinct from a real sub."""
    identity = resolve_turn_identity(requested_customer_id="CUST-MARCO")

    assert identity.memory_actor() == "persona-CUST-MARCO"


def test_fully_anonymous_turn_falls_back_to_anonymous() -> None:
    identity = resolve_turn_identity()

    assert identity.memory_actor() == "anonymous"
    assert identity.demo_persona_id is None


def test_blank_sub_is_treated_as_absent() -> None:
    identity = resolve_turn_identity(user={"sub": "   "})

    assert identity.principal_sub is None
    assert identity.authenticated is False


def test_identity_serializes_all_three_fields_distinctly() -> None:
    payload = resolve_turn_identity(
        user={"sub": "sub-1", "username": "marco"},
        requested_customer_id="CUST-ANNA",
    ).to_dict()

    assert payload["principalSub"] == "sub-1"
    assert payload["shopperCustomerId"] == "CUST-MARCO"
    assert payload["demoPersonaId"] == "CUST-ANNA"
    assert payload["memoryActor"] == "sub-1"
    assert payload["authenticated"] is True


def test_authenticated_customer_scope_comes_only_from_verified_username() -> None:
    identity = resolve_turn_identity(
        user={"sub": "sub-1", "username": "marco"},
        requested_customer_id="CUST-ANNA",
    )

    assert identity.shopper_customer_id == "CUST-MARCO"
    assert identity.demo_persona_id == "CUST-ANNA"


def test_jessica_has_a_verified_customer_scope_without_becoming_a_persona() -> None:
    identity = resolve_turn_identity(
        user={"sub": "sub-jessica", "username": "Jessica"},
        requested_customer_id="CUST-MARCO",
    )

    assert identity.shopper_customer_id == "CUST-JESSICA"
    assert identity.principal_sub == "sub-jessica"
    assert identity.demo_persona_id == "CUST-MARCO"
    assert identity.authenticated is True
    assert identity.persona_is_simulated is False


def test_unknown_verified_username_does_not_fall_back_to_persona() -> None:
    identity = resolve_turn_identity(
        user={"sub": "sub-1", "username": "participant-99"},
        requested_customer_id="CUST-THEO",
    )

    assert identity.shopper_customer_id is None


def test_chat_uses_one_identity_service_namespace_for_shopper_stm() -> None:
    """The STM writer and the Observatory replay must use the same key.

    The only working-memory write in the chat service is the explicit facade
    call, keyed by the identity service's namespace builder. The Strands
    session manager that used to be attached beside it never took effect and
    is gone, so a second namespace derivation in this file would be a
    regression, not a redundancy.
    """
    from pathlib import Path

    chat_source = (
        Path(__file__).resolve().parents[1] / "services" / "chat.py"
    ).read_text()

    assert "resolve_turn_identity" in chat_source
    assert chat_source.count("AgentCoreIdentityService.build_namespace(") == 1
    assert "session_manager" not in chat_source
    assert "create_agentcore_session_manager" not in chat_source
    assert "memory_user_id = turn_identity.memory_actor()" not in chat_source


def test_default_identity_is_anonymous() -> None:
    assert TurnIdentity().memory_actor() == "anonymous"
    assert TurnIdentity().authorization_principal() is None


def test_verified_customer_scope_is_turn_local() -> None:
    assert current_authorized_customer_id() is None
    token = authorized_customer_id_var.set("CUST-MARCO")
    try:
        assert current_authorized_customer_id() == "CUST-MARCO"
    finally:
        authorized_customer_id_var.reset(token)
    assert current_authorized_customer_id() is None


def test_chat_binds_the_verified_customer_scope_on_the_streamed_turn() -> None:
    """``chat()`` delegates to ``chat_stream``, so one binding covers both."""
    from pathlib import Path

    chat_source = (
        Path(__file__).resolve().parents[1] / "services" / "chat.py"
    ).read_text()
    assert chat_source.count("authorized_customer_id_var.set(") == 1
    assert (
        "turn_identity.shopper_customer_id if turn_identity.authenticated else None"
        in chat_source
    )


# ---------------------------------------------------------------------------
# Managed trace correlation (audit finding B9)
# ---------------------------------------------------------------------------
def test_xray_root_trace_id_is_parsed() -> None:
    from services.agentcore_runtime import _trace_id_from

    trace_id = _trace_id_from(
        {"x-amzn-trace-id": "Root=1-65f0a1b2-abcdef0123456789abcdef01;Sampled=1"}
    )

    assert trace_id == "1-65f0a1b2-abcdef0123456789abcdef01"


def test_w3c_traceparent_is_parsed() -> None:
    from services.agentcore_runtime import _trace_id_from

    trace_id = _trace_id_from(
        {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}
    )

    assert trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"


def test_absent_trace_headers_yield_none() -> None:
    """No trace id is honest evidence, not a value to invent."""
    from services.agentcore_runtime import _trace_id_from

    assert _trace_id_from({}) is None


def test_managed_receipt_carries_correlation_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.agentcore_runtime as rt

    rt._store_managed_runtime_receipt(
        "sess-b9",
        principal_sub="principal-b9",
        rail="gateway-mcp",
        auth_token_present=True,
        trace_id="1-65f0a1b2-abcdef0123456789abcdef01",
        request_id="req-abc-123",
    )

    receipt = rt.get_latest_trace("sess-b9", principal_sub="principal-b9")

    assert receipt["traceId"] == "1-65f0a1b2-abcdef0123456789abcdef01"
    assert receipt["runtimeRequestId"] == "req-abc-123"
    assert receipt["sessionId"] == "sess-b9"
    assert receipt["rail"] == "gateway-mcp"
    assert receipt["managedTrace"]["xrayConsoleUrl"] is not None
    assert "sess-b9" in receipt["managedTrace"]["logsInsightsQuery"]


def test_managed_receipt_never_synthesizes_spans() -> None:
    """Reconstructed data must not be presented as observed telemetry."""
    import services.agentcore_runtime as rt

    rt._store_managed_runtime_receipt(
        "sess-b9-empty",
        principal_sub="principal-b9",
        rail="gateway-mcp",
        auth_token_present=True,
    )

    receipt = rt.get_latest_trace(
        "sess-b9-empty", principal_sub="principal-b9"
    )

    assert receipt["spans"] == []
    assert receipt["otel_enabled"] is False
    assert receipt["evidenceProvenance"] == "agentcore-service-telemetry"
    # No trace id reported means no console link is fabricated.
    assert receipt["managedTrace"]["xrayConsoleUrl"] is None


def test_managed_receipts_do_not_fall_back_across_principals() -> None:
    import services.agentcore_runtime as rt

    rt._store_managed_runtime_receipt(
        "shared-session",
        principal_sub="principal-a",
        rail="gateway-mcp",
        auth_token_present=True,
        trace_id="trace-a",
    )

    own_receipt = rt.get_latest_trace(
        "shared-session", principal_sub="principal-a"
    )
    foreign_receipt = rt.get_latest_trace(
        "shared-session", principal_sub="principal-b"
    )

    assert own_receipt["traceId"] == "trace-a"
    assert foreign_receipt == {
        "spans": [],
        "totalMs": 0,
        "specialistRoute": "",
    }
