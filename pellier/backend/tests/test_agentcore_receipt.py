"""Contract tests for the managed AgentCore provisioning receipt."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_agentcore_receipt.py"


def _load_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "pellier_agentcore_receipt_validator", VALIDATOR_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _valid_receipt() -> dict[str, Any]:
    validator = _load_validator()
    targets = validator.workshop_target_tools()
    names = sorted({name for tools in targets.values() for name in tools})
    shopper_names = sorted(validator.discoverable_tools_for_claims(
        has_staff_scope=False, has_customer_claim=True
    ))
    receipt = {
        "status": "ready",
        "cli": {"package": "@aws/agentcore@0.29.0"},
        "runtime": {"runtime_arn": "arn:aws:bedrock-agentcore:runtime/example"},
        "operator_runtime": {
            "runtime_arn": "arn:aws:bedrock-agentcore:runtime/operator-fixture",
            "authentication": "AWS_IAM",
        },
        "memory": {"memory_id": "memory-1", "seed": {"status": "ready"}},
        "gateway": {
            "gateway_id": "gateway-1",
            "gateway_arn": "arn:aws:bedrock-agentcore:gateway/example",
            "gateway_url": "https://gateway.example/mcp",
        },
        "policy": {"policy_engine_id": "policy-1", "mode": "ENFORCE"},
        "observability": {
            "transaction_search": {
                "destination": "CloudWatchLogs",
                "status": "ACTIVE",
                "resource_policy": "TransactionSearchXRayAccess",
                "resource_policy_document": (
                    '{"Version":"2012-10-17","Statement":'
                    '[{"Sid":"TransactionSearchXRayAccess"}]}'
                ),
                "cleanup": {
                    "destination_changed": True,
                    "previous_destination": "XRay",
                    "resource_policy_created": True,
                    "previous_resource_policy_document": None,
                },
            },
            "control_plane_audit": {
                "source": "CloudTrail Event History",
                "event_source": "bedrock-agentcore.amazonaws.com",
                "event_name": "CreateAgentRuntime",
                "event_time": "2026-08-13T12:00:00Z",
                "resource_type": "runtime",
            },
            "runtime_log_group": {
                "name": "/aws/bedrock-agentcore/runtimes/pellier_orchestrator-abc123-DEFAULT",
                "kms_key_arn": (
                    "arn:aws:kms:us-east-1:123456789012:"
                    "key/12345678-1234-1234-1234-1234567890ab"
                ),
                "retention_days": 30,
                "cleanup": {
                    "created_by_workshop": True,
                    "previous_kms_key_arn": None,
                    "previous_retention_days": None,
                },
            },
            "operator_runtime_log_group": {
                "name": "/aws/bedrock-agentcore/runtimes/pellier_operator-fixture-DEFAULT",
                "kms_key_arn": "arn:aws:kms:us-east-1:123456789012:key/fixture",
                "retention_days": 30,
                "cleanup": {"created_by_workshop": True},
            },
            "trace_log_groups": {
                "groups": [
                    {
                        "name": "aws/spans",
                        "kms_key_arn": (
                            "arn:aws:kms:us-east-1:123456789012:"
                            "key/12345678-1234-1234-1234-1234567890ab"
                        ),
                        "retention_days": 30,
                        "cleanup": {
                            "created_by_workshop": True,
                            "previous_kms_key_arn": None,
                            "previous_retention_days": None,
                        },
                    },
                    {
                        "name": "/aws/application-signals/data",
                        "kms_key_arn": (
                            "arn:aws:kms:us-east-1:123456789012:"
                            "key/12345678-1234-1234-1234-1234567890ab"
                        ),
                        "retention_days": 30,
                        "cleanup": {
                            "created_by_workshop": True,
                            "previous_kms_key_arn": None,
                            "previous_retention_days": None,
                        },
                    },
                ],
                "kms_key_arn": (
                    "arn:aws:kms:us-east-1:123456789012:"
                    "key/12345678-1234-1234-1234-1234567890ab"
                ),
                "retention_days": 30,
            },
            "unified_trace": {
                "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
                "session_id": "runtime-proof-000000000000000000001",
                "runtime_arn": "arn:aws:bedrock-agentcore:runtime/example",
                "runtime_log_group": (
                    "/aws/bedrock-agentcore/runtimes/"
                    "pellier_orchestrator-abc123-DEFAULT"
                ),
                "span_count": 3,
                "span_names": [
                    "chat",
                    "execute_tool search_products_hybrid",
                    "invoke_agent pellier_orchestrator",
                ],
                "agent_span": True,
                "model_span": True,
                "tool_span": True,
                "agent_input_observed": True,
                "agent_output_observed": True,
                "tool_input_output_observed": True,
                "tool_input_output_structured": True,
                "tool_input_output_sanitized": True,
                "attribute_contract": {
                    "agent_input": "gen_ai.input.messages",
                    "agent_output": "gen_ai.output.messages",
                    "tool_input": "gen_ai.tool.call.arguments",
                    "tool_output": "gen_ai.tool.call.result",
                },
                "step_latency_observed": True,
                "step_latency_ms": {"agent": 125, "model": 80, "tool": 30},
                "model_ids": ["global.anthropic.claude-sonnet-4-6"],
                "tool_names": ["search_products_hybrid"],
                "provenance": "agentcore-unified-telemetry",
            },
        },
        "verification": {
            "local_tool_schema": {"count": len(names), "canonical_names": names},
            "gateway_control_plane": {
                "target_count": len(targets),
                "target_names": sorted(targets),
                "policy_mode": "ENFORCE",
            },
            "gateway_tool_count": len(shopper_names),
            "gateway_tool_names": shopper_names,
            "gateway_prefixed_tool_names": [
                f"{target}___{name}"
                for target, tools in targets.items()
                for name in tools
                if name in shopper_names
            ],
            "runtime_invoke_smoke": {
                "rail": "gateway-mcp",
                "session_id": "runtime-proof-000000000000000000001",
                "response_preview": "A linen shirt is available.",
                "build_fingerprint": "fixture-package",
                "build_fingerprint_expected": "fixture-package",
                "build_fingerprint_match": True,
            },
            "operator_runtime_invoke_smoke": {
                "runtime_arn": "arn:aws:bedrock-agentcore:runtime/operator-fixture",
                "session_id": "operator-proof-000000000000000000001",
                "build_fingerprint": "fixture-package",
                "build_fingerprint_match": True,
                "executed_nodes": ["case-investigator", "resolution-planner"],
                "fixture": True,
            },
            "runtime_build_fingerprint_match": True,
            "operator_runtime_build_fingerprint_match": True,
            "targets_attached": True,
            "gateway_tools_discovered": True,
            "memory_seeded": True,
            "live_policy_allow": True,
            "live_policy_deny": True,
            "authenticated_runtime_invoke_smoke": True,
            "transaction_search_ready": True,
            "trace_log_groups_encrypted": True,
            "trace_log_groups_retention_bounded": True,
            "control_plane_audit_verified": True,
            "runtime_log_group_encrypted": True,
            "runtime_log_group_retention_bounded": True,
            "unified_trace_delivered": True,
            "unified_trace_agent_span": True,
            "unified_trace_model_span": True,
            "unified_trace_tool_span": True,
            "unified_trace_agent_input": True,
            "unified_trace_agent_output": True,
            "unified_trace_tool_io_structured": True,
            "unified_trace_tool_io_sanitized": True,
            "unified_trace_step_latency": True,
            "live_policy_proof": {
                "allow": {
                    "outcome": "allow",
                    "tool_audit_row_after_call": {"audit_id": 101},
                },
                "deny": {
                    "outcome": "deny",
                    "cedar_denial": True,
                    "tool_audit_row_after_call": None,
                },
            },
        },
    }
    observability = receipt["observability"]
    for group in [
        observability["runtime_log_group"],
        observability["operator_runtime_log_group"],
        *observability["trace_log_groups"]["groups"],
    ]:
        settings = {
            "kms_key_arn": group["kms_key_arn"],
            "retention_days": group["retention_days"],
        }
        group["requested"] = dict(settings)
        group["observed"] = dict(settings)
    return receipt


def test_ready_receipt_requires_managed_observability_proof() -> None:
    validator = _load_validator()

    assert validator.validate_receipt(_valid_receipt()) == []


@pytest.mark.parametrize("evidence_type", ["requested", "observed"])
def test_log_protection_flags_do_not_substitute_for_readback(evidence_type: str) -> None:
    validator = _load_validator()
    receipt = _valid_receipt()
    group = receipt["observability"]["runtime_log_group"]
    del group[evidence_type]
    assert any(evidence_type in error for error in validator.validate_receipt(receipt))


def test_observed_log_settings_must_match_the_claimed_configuration() -> None:
    validator = _load_validator()
    receipt = _valid_receipt()
    receipt["observability"]["operator_runtime_log_group"]["observed"]["kms_key_arn"] = None
    assert any("observed" in error for error in validator.validate_receipt(receipt))


def test_receipt_matches_the_real_provisioner_catalogue() -> None:
    spec = importlib.util.spec_from_file_location(
        "receipt_provisioner_contract",
        REPO_ROOT / "scripts/provision_agentcore_end_to_end.py",
    )
    assert spec and spec.loader
    provisioner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(provisioner)
    receipt = _valid_receipt()
    receipt["verification"]["local_tool_schema"] = provisioner._verify_local_schema()
    assert provisioner.INITIATE_RETURN_ACTION in (
        receipt["verification"]["gateway_prefixed_tool_names"]
    )
    assert _load_validator().validate_receipt(receipt) == []
    assert receipt["verification"]["gateway_tool_count"] < (
        receipt["verification"]["local_tool_schema"]["count"]
    )


@pytest.mark.parametrize(
    "path",
    [
        ("local_tool_schema", "canonical_names"),
        ("gateway_control_plane", "target_names"),
        ("gateway_tool_names",),
        ("gateway_prefixed_tool_names",),
    ],
)
@pytest.mark.parametrize("replacement", ["unexpected_tool", {}, None])
def test_matching_counts_cannot_hide_a_wrong_tool_contract(path, replacement) -> None:
    receipt = _valid_receipt()
    values = receipt["verification"]
    for key in path:
        values = values[key]
    values[0] = replacement
    assert _load_validator().validate_receipt(receipt)


def test_staff_tool_cannot_replace_a_shopper_tool_at_the_same_count() -> None:
    receipt = _valid_receipt()
    receipt["verification"]["gateway_tool_names"][0] = "issue_credit"
    assert _load_validator().validate_receipt(receipt)


def test_validator_follows_source_catalogue_changes(monkeypatch) -> None:
    _load_validator()
    import gateway_tool_schemas as schemas

    config = schemas.TOOL_SCHEMAS["search"]
    monkeypatch.setitem(
        config, "tools", [*config["tools"], {"name": "future_catalogue_read"}]
    )
    assert _load_validator().validate_receipt(_valid_receipt()) == []


def _participant_receipt(full: dict[str, Any]) -> dict[str, Any]:
    receipt = copy.deepcopy(full)
    receipt["mode"] = "participant"
    receipt.pop("memory")
    receipt.pop("observability")
    smoke = receipt["verification"]["runtime_invoke_smoke"]
    smoke["build_fingerprint"] = "updated-package"
    smoke["build_fingerprint_expected"] = "updated-package"
    smoke["session_id"] = "participant-new-session"
    return receipt


def test_participant_catalogue_change_keeps_full_bootstrap_proof(monkeypatch, tmp_path) -> None:
    validator = _load_validator()
    full = _valid_receipt()
    import gateway_tool_schemas as schemas

    config = schemas.TOOL_SCHEMAS["search"]
    monkeypatch.setitem(config, "tools", [*config["tools"], {"name": "future_catalogue_read"}])
    participant = _participant_receipt(_valid_receipt())
    assert validator.validate_receipt(full), "the historical catalogue is stale"
    original = copy.deepcopy(full)
    assert validator.validate_receipt(full, participant) == []
    assert full == original, "historical evidence must not be rewritten"

    full_path, update_path = tmp_path / "full.json", tmp_path / "update.json"
    full_path.write_text(json.dumps(full))
    update_path.write_text(json.dumps(participant))
    monkeypatch.setattr(validator.sys, "argv", ["validator", str(full_path), "--participant", str(update_path)])
    assert validator.main() == 0
    full["verification"]["unified_trace_tool_span"] = False
    assert validator.validate_receipt(full, participant), "update cannot replace missing bootstrap proof"


@pytest.mark.parametrize("failure", ["resource", "failed", "fingerprint", "discovery", "catalogue", "policy"])
def test_participant_receipt_cannot_bypass_current_deployment_proof(failure: str) -> None:
    full = _valid_receipt()
    participant = _participant_receipt(full)
    if failure == "resource":
        participant["gateway"]["gateway_id"] = "another-environment"
    elif failure == "failed":
        participant["status"] = "failed"
    elif failure == "fingerprint":
        participant["verification"]["runtime_invoke_smoke"]["build_fingerprint"] = "stale-package"
    elif failure == "discovery":
        participant["verification"]["gateway_tools_discovered"] = False
    elif failure == "catalogue":
        participant["verification"]["gateway_tool_names"][0] = "issue_credit"
    else:
        participant["verification"]["gateway_control_plane"]["policy_mode"] = "LOG_ONLY"
    assert _load_validator().validate_receipt(full, participant)


@pytest.mark.parametrize("failure", ["missing", "stale", "partial", "endpoint", "log"])
def test_ready_receipt_requires_the_matching_operator_package(failure: str) -> None:
    receipt = _valid_receipt()
    smoke = receipt["verification"]["operator_runtime_invoke_smoke"]
    if failure == "missing":
        receipt.pop("operator_runtime")
    elif failure == "stale":
        smoke["build_fingerprint"] = "old-package"
    elif failure == "partial":
        smoke["executed_nodes"].pop()
    elif failure == "endpoint":
        smoke["runtime_arn"] = receipt["runtime"]["runtime_arn"]
    else:
        receipt["observability"]["operator_runtime_log_group"]["retention_days"] = 0
    assert _load_validator().validate_receipt(receipt)


def _redacted_receipt() -> dict[str, Any]:
    receipt = _valid_receipt()
    trace = receipt["observability"]["unified_trace"]
    verification = receipt["verification"]
    trace["content_redacted"] = True
    verification["unified_trace_content_redacted"] = True
    for key in ("agent_input_observed", "agent_output_observed", "tool_input_output_observed"):
        trace[key] = False
    trace["tool_input_output_structured"] = None
    trace["attribute_contract"] = dict.fromkeys(trace["attribute_contract"])
    verification["unified_trace_agent_input"] = False
    verification["unified_trace_agent_output"] = False
    verification["unified_trace_tool_io_structured"] = None
    return receipt


def test_ready_receipt_accepts_verified_redaction_without_requiring_content() -> None:
    assert _load_validator().validate_receipt(_redacted_receipt()) == []


@pytest.mark.parametrize("redacted", [False, True])
def test_produced_trace_with_unnamed_transport_spans_passes_readiness(redacted: bool) -> None:
    """Exercise the producer and consumer together, including live transport metadata."""
    from tests.test_agentcore_deploy_templates import (
        _load_provisioner,
        _strip_content_attributes,
        _unified_trace_records,
    )

    receipt = _redacted_receipt() if redacted else _valid_receipt()
    prior_trace = receipt["observability"]["unified_trace"]
    identifiers = {
        key: prior_trace[key] for key in ("trace_id", "session_id", "runtime_arn")
    }
    records = _unified_trace_records(**identifiers)
    for name in (None, "", "   ", 42):
        records.append({"@message": {
            "traceId": identifiers["trace_id"],
            "name": name,
            "resource": {"attributes": {"cloud.resource_id": identifiers["runtime_arn"]}},
        }})
    if redacted:
        records = _strip_content_attributes(records)
    trace = _load_provisioner()._summarize_trace_records(
        records, **identifiers, content_redacted=redacted,
    )
    trace["runtime_log_group"] = prior_trace["runtime_log_group"]
    receipt["observability"]["unified_trace"] = trace

    assert trace["span_count"] == 7
    assert trace["span_names"] == [
        "chat", "execute_tool search_products_hybrid", "invoke_agent pellier_orchestrator",
    ]
    assert _load_validator().validate_receipt(receipt) == []


@pytest.mark.parametrize("failure", ["content", "attribute", "unverified", "missing_span"])
def test_redaction_does_not_bypass_trace_evidence(failure: str) -> None:
    receipt = _redacted_receipt()
    trace = receipt["observability"]["unified_trace"]
    if failure == "content":
        trace["agent_input_observed"] = True
    elif failure == "attribute":
        trace["attribute_contract"]["agent_input"] = "gen_ai.input.messages"
    elif failure == "unverified":
        receipt["verification"]["unified_trace_content_redacted"] = False
    else:
        trace["tool_span"] = False
    assert _load_validator().validate_receipt(receipt)


def test_ready_receipt_rejects_missing_tool_span_proof() -> None:
    validator = _load_validator()
    receipt = _valid_receipt()
    receipt["observability"]["unified_trace"]["tool_span"] = False
    receipt["verification"]["unified_trace_tool_span"] = False

    errors = validator.validate_receipt(receipt)

    assert "verification.unified_trace_tool_span must be true" in errors
    assert "observability.unified_trace.tool_span must be true" in errors


def test_ready_receipt_rejects_unbounded_runtime_log_retention() -> None:
    validator = _load_validator()
    receipt = _valid_receipt()
    receipt["observability"]["runtime_log_group"]["retention_days"] = 0

    errors = validator.validate_receipt(receipt)

    assert (
        "observability.runtime_log_group.retention_days must be a positive integer"
        in errors
    )


def test_ready_receipt_rejects_missing_cloudtrail_control_plane_proof() -> None:
    validator = _load_validator()
    receipt = _valid_receipt()
    receipt["verification"]["control_plane_audit_verified"] = False

    errors = validator.validate_receipt(receipt)

    assert "verification.control_plane_audit_verified must be true" in errors


def test_ready_receipt_rejects_non_allowlisted_trace_attribute() -> None:
    validator = _load_validator()
    receipt = _valid_receipt()
    receipt["observability"]["unified_trace"]["attribute_contract"][
        "tool_output"
    ] = "custom.raw.tool.output"

    errors = validator.validate_receipt(receipt)

    assert (
        "observability.unified_trace.attribute_contract."
        "tool_output='custom.raw.tool.output' is not allowlisted"
    ) in errors


def test_ready_receipt_rejects_unprotected_trace_log_group() -> None:
    validator = _load_validator()
    receipt = _valid_receipt()
    receipt["observability"]["trace_log_groups"]["groups"][0][
        "kms_key_arn"
    ] = "arn:aws:kms:us-east-1:123456789012:key/other"

    errors = validator.validate_receipt(receipt)

    assert "trace log group 'aws/spans' must use the receipt KMS key" in errors
