"""Regression coverage for customer boundaries and durable workshop evidence."""
import sys
from pathlib import Path

from services.governed_turn_receipt import _trace_metadata


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
