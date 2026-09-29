"""Regression coverage for customer boundaries and durable workshop evidence."""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import observatory, workshop
from services.auth import get_current_user
from services.agentcore_identity import AgentCoreIdentityService
from services.governed_turn_receipt import _trace_metadata
from services.operator_review import MANAGED_RAIL_REFUSAL


@pytest.mark.parametrize("principal,status", [
    (None, 401),
    ({"sub": "verified-marco", "username": "marco"}, 403),
    ({"sub": "unmapped", "username": "unmapped"}, 403),
])
def test_customer_memory_and_resume_reject_before_reading(principal, status, monkeypatch):
    api = FastAPI()
    api.include_router(observatory.router)
    api.include_router(workshop.router)
    api.dependency_overrides[get_current_user] = lambda: principal

    async def no_database():
        pytest.fail("an unauthorized request reached the database")

    monkeypatch.setattr(observatory, "_live_db", no_database)
    client = TestClient(api)
    assert client.get("/api/observatory/memory/theo").status_code == status
    assert client.post("/api/observatory/resume", json={"customer_id": "CUST-THEO"}).status_code == status
    assert client.post("/api/observatory/query", json={
        "customer_id": "CUST-THEO", "query": "Read this customer's history",
    }).status_code == status


def test_memory_dashboard_uses_authenticated_writer_namespace(monkeypatch):
    class DB:
        async def fetch_one(self, sql, *params):
            assert params == ("verified-theo", "verified-theo")
            return {"session_id": "persona-theo-abc"}

    namespace = asyncio.run(AgentCoreIdentityService.latest_shopper_namespace(DB(), "verified-theo"))
    assert namespace == AgentCoreIdentityService.build_namespace("verified-theo", "persona-theo-abc")
    captured = []
    from services.agentcore_memory import AgentCoreMemory

    async def preferences(self, actor_id):
        captured.append(actor_id)
        return ["Prefers blue linen"]

    monkeypatch.setattr(AgentCoreMemory, "get_semantic_memories", preferences)
    rows = asyncio.run(observatory._load_live_semantic("theo", namespace=namespace))
    assert rows[0]["content"] == "Prefers blue linen"
    assert captured == [namespace]
    assert asyncio.run(observatory._load_live_semantic("theo")) == []


@pytest.mark.parametrize("result,expected", [
    ({"error": "timeout"}, "failed"),
    ({"success": False}, "failed"),
    ({"status": "denied"}, "denied"),
    ({"success": True}, "succeeded"),
    # A structured result without a stated outcome proves the tool ran and
    # returned data, not that it succeeded; "unavailable" read as the tool
    # having been unreachable.
    ({"rows": []}, "recorded"),
    ({"category": "Home Decor", "return_window_days": 30}, "recorded"),
    # The governed boundary declining a shopper-rail mutation is a refusal
    # before execution, not a failure of the turn.
    ({"tool": "initiate_return", "error": "managed_rail_required"}, "denied"),
    (None, "unavailable"),
    ("not json", "unavailable"),
])
def test_audit_outcome_never_invents_success(result, expected):
    assert observatory._audit_result_status(result) == expected


def test_replay_captions_a_boundary_refusal_as_refused_before_execution():
    """A Denied step captioned "invocation recorded in Aurora" read as a Cedar
    DENY that left an execution row, which Lab 4 teaches cannot happen."""
    refused = observatory._audit_step_description({
        "caller": "agent",
        "result": {"tool": "initiate_return", "error": MANAGED_RAIL_REFUSAL},
    })
    assert refused.startswith("Refused before execution")
    assert "invocation" not in refused
    ran = observatory._audit_step_description({
        "caller": "agent", "result": {"count": 5, "status": "success"},
    })
    assert ran == "agent invocation recorded in Aurora."


def test_configured_models_report_settings_including_env_overrides(monkeypatch):
    """The Evidence tab's model card reads this, so an .env override shows."""
    from config import settings

    monkeypatch.setattr(settings, "BEDROCK_OPUS_MODEL", "global.anthropic.override-for-test")
    monkeypatch.setattr(settings, "BEDROCK_RERANK_MODEL", "")
    app = FastAPI()
    app.include_router(observatory.router)
    response = TestClient(app).get("/api/observatory/models")
    assert response.status_code == 200
    models = {row["setting"]: row for row in response.json()["models"]}
    assert models["BEDROCK_OPUS_MODEL"]["modelId"] == "global.anthropic.override-for-test"
    assert models["BEDROCK_OPUS_MODEL"]["label"] == "Editorial specialists"
    # An empty setting is reported as absent, never as a stale default.
    assert models["BEDROCK_RERANK_MODEL"]["modelId"] is None
    assert set(models) == {
        "BEDROCK_OPUS_MODEL", "BEDROCK_REPORTING_MODEL", "BEDROCK_SONNET_MODEL",
        "BEDROCK_ROUTER_MODEL", "BEDROCK_FAST_MODEL", "BEDROCK_EMBEDDING_MODEL",
        "BEDROCK_RERANK_MODEL",
    }


def test_session_list_does_not_mark_a_boundary_refusal_as_failure(monkeypatch):
    """Lab 3 turn 3 ends in the intended managed-rail refusal. The session list
    must not report that correct outcome as "Failure recorded"."""
    captured = []

    class DB:
        async def fetch_all(self, sql, *params):
            captured.append(sql)
            return []

    async def live_db():
        return DB()

    monkeypatch.setattr(observatory, "_live_db", live_db)
    app = FastAPI()
    app.include_router(observatory.router)
    app.dependency_overrides[get_current_user] = lambda: None
    response = TestClient(app).get("/api/observatory/sessions")
    assert response.status_code == 200
    failure_predicate = captured[0].split("THEN 'failed'")[0].rsplit("CASE WHEN bool_or(", 1)[1]
    assert f"<> '{MANAGED_RAIL_REFUSAL}'" in failure_predicate


def test_memory_receipt_survives_projection_without_content():
    memory = {
        "source": "agentcore-memory", "turns_loaded": 2, "turns_persisted": 2,
        "read_status": "succeeded", "write_status": "succeeded",
        "namespace_scope": "verified-principal", "conversation": "private content",
    }
    projected = _trace_metadata({"memory": memory})["memory"]
    assert projected["turns_loaded"] == 2
    assert projected["write_status"] == "succeeded"
    assert "conversation" not in projected
    assert "memory" not in _trace_metadata({"memory": None})


def test_publishing_ticket_history_also_installs_ownership(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts/deploy"))
    import render_agentcore_project as renderer

    published = renderer.workshop_target_tools()
    published[renderer.EXPERIENCE_TARGET] = [
        *published[renderer.EXPERIENCE_TARGET], "get_ticket_history", "issue_credit", "future_tool",
    ]
    monkeypatch.setattr(renderer, "workshop_target_tools", lambda: published)
    arn = "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/test-gw"
    policies = {
        item["name"]: item["statement"]
        for item in renderer.baseline_policies(gateway_arn=arn)
    }
    permit = policies["baseline_permit_workshop_tools"]
    assert "___get_ticket_history" not in permit
    assert "___issue_credit" not in permit
    assert "___future_tool" not in permit
    # Published in the same deployment as its owner-only permit: the read is
    # reachable only by the customer the token names, never by a caller who
    # merely supplies a customer_id.
    owned = policies["get_ticket_history_owner_only"]
    assert owned.startswith("permit (principal is AgentCore::OAuthUser")
    assert "___get_ticket_history" in owned
    assert 'principal.hasTag("custom:customer_id")' in owned
    assert "context.input has customer_id" in owned
    assert 'principal.getTag("custom:customer_id") == context.input.customer_id' in owned
    assert "CUST-THEO" not in owned and "username" not in owned
    assert "get_ticket_history_identity_scope" not in policies


def test_no_statement_rewrites_the_material_a_person_confirmed() -> None:
    """approvals.customer_id, tool, args and action_hash are write-once.

    A confirmation echoes the fingerprint and an execution recomputes it from
    the stored args. That proves the row still says what the person was shown
    only if nothing can rewrite those columns after the insert, so every UPDATE
    the application issues against the table is inspected for them.
    """
    import re

    backend = Path(__file__).resolve().parents[1]
    updates = re.compile(r"UPDATE\s+pellier\.approvals\s+SET(.*?)\bWHERE\b", re.S | re.I)
    material = re.compile(r"\b(customer_id|tool|args|action_hash)\s*=")
    seen, offenders = 0, []
    for folder in ("services", "routes"):
        for path in sorted((backend / folder).rglob("*.py")):
            for match in updates.finditer(path.read_text()):
                seen += 1
                if material.search(match.group(1)):
                    offenders.append(f"{path.relative_to(backend)}: {match.group(0)[:100]}")
    assert seen >= 2, "the decision and execution-turn updates were not found"
    assert not offenders, offenders
