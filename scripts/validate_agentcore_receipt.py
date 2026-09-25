#!/usr/bin/env python3
"""Validate the managed AgentCore readiness receipt emitted by the provisioner."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


DEPLOY_DIR = Path(__file__).resolve().parent / "deploy"
if str(DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(DEPLOY_DIR))

from gateway_tool_schemas import (  # noqa: E402
    discoverable_tools_for_claims,
    workshop_target_tools,
)


EXPECTED_CLI = "@aws/agentcore@0.29.0"
TRACE_ATTRIBUTE_ALLOWLISTS = {
    "agent_input": {
        "gen_ai.input.messages",
        "gen_ai.request.input",
        "gen_ai.prompt",
    },
    "agent_output": {
        "gen_ai.output.messages",
        "gen_ai.response.output",
        "gen_ai.completion",
    },
    "tool_input": {
        "gen_ai.tool.call.arguments",
        "gen_ai.tool.input",
        "gen_ai.tool.parameters",
    },
    "tool_output": {
        "gen_ai.tool.call.result",
        "gen_ai.tool.output",
        "gen_ai.tool.result",
    },
}


def _value(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _expected_policy_mode() -> str:
    """Return the gateway policy mode this receipt is expected to report.

    Enforcement mode is a deliberate state transition, not a constant: the
    workshop has a monitor window in which Cedar reports WOULD_DENY and the
    database is the enforcer. Hard-coding ENFORCE made a receipt captured
    during that window look like a provisioning failure.

    Set `PELLIER_EXPECTED_POLICY_MODE=LOG_ONLY` while the monitor window is
    open. The default stays ENFORCE, which is the shipped state reset restores.
    """
    expected = os.environ.get("PELLIER_EXPECTED_POLICY_MODE", "ENFORCE").strip()
    if expected not in {"ENFORCE", "LOG_ONLY"}:
        raise SystemExit(
            f"PELLIER_EXPECTED_POLICY_MODE must be ENFORCE or LOG_ONLY, got {expected!r}"
        )
    return expected


def _validate_participant_receipt(
    payload: dict[str, Any], participant: dict[str, Any]
) -> list[str]:
    """Bind a later catalogue/build proof to the original provisioned resources."""
    errors: list[str] = []
    expected = {
        "status": "ready",
        "mode": "participant",
        "cli.package": EXPECTED_CLI,
        "policy.mode": _expected_policy_mode(),
        "verification.gateway_control_plane.policy_mode": _expected_policy_mode(),
        "verification.runtime_invoke_smoke.rail": "gateway-mcp",
        "verification.targets_attached": True,
        "verification.gateway_tools_discovered": True,
        "verification.authenticated_runtime_invoke_smoke": True,
        "verification.runtime_build_fingerprint_match": True,
        "verification.runtime_invoke_smoke.build_fingerprint_match": True,
    }
    for path, value in expected.items():
        actual = _value(participant, path)
        if actual != value or (isinstance(value, bool) and actual is not value):
            errors.append(f"participant.{path} must be {value!r}")
    for path in (
        "runtime.runtime_arn", "operator_runtime.runtime_arn",
        "gateway.gateway_id", "gateway.gateway_arn", "gateway.gateway_url",
        "policy.policy_engine_id",
    ):
        if not _value(participant, path) or _value(participant, path) != _value(payload, path):
            errors.append(f"participant.{path} must match the full provisioning receipt")
    for path in (
        "verification.runtime_invoke_smoke.session_id",
        "verification.runtime_invoke_smoke.response_preview",
        "verification.runtime_invoke_smoke.build_fingerprint",
        "verification.runtime_invoke_smoke.build_fingerprint_expected",
    ):
        value = _value(participant, path)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"participant.{path} must be a non-empty string")
    if _value(participant, "verification.runtime_invoke_smoke.build_fingerprint") != _value(
        participant, "verification.runtime_invoke_smoke.build_fingerprint_expected"
    ):
        errors.append("participant Runtime smoke must match the updated package fingerprint")
    return errors


def validate_receipt(
    payload: dict[str, Any], participant: dict[str, Any] | None = None
) -> list[str]:
    """Return human-readable contract violations; an empty list means ready."""
    errors: list[str] = []
    if participant is not None:
        errors.extend(_validate_participant_receipt(payload, participant))
    content_redacted = _value(
        payload, "observability.unified_trace.content_redacted"
    ) is True

    expected_values = {
        "status": "ready",
        "cli.package": EXPECTED_CLI,
        "policy.mode": _expected_policy_mode(),
        "verification.gateway_control_plane.policy_mode": _expected_policy_mode(),
        "memory.seed.status": "ready",
        "observability.transaction_search.destination": "CloudWatchLogs",
        "observability.transaction_search.status": "ACTIVE",
        "observability.control_plane_audit.source": "CloudTrail Event History",
        "observability.control_plane_audit.event_source": (
            "bedrock-agentcore.amazonaws.com"
        ),
        "observability.unified_trace.provenance": "agentcore-unified-telemetry",
        "verification.runtime_invoke_smoke.rail": "gateway-mcp",
        "operator_runtime.authentication": "AWS_IAM",
        "verification.operator_runtime_invoke_smoke.fixture": True,
        "verification.operator_runtime_invoke_smoke.build_fingerprint_match": True,
        "verification.runtime_invoke_smoke.build_fingerprint_match": True,
    }
    for path, expected in expected_values.items():
        actual = _value(payload, path)
        if actual != expected:
            errors.append(f"{path}={actual!r}, expected {expected!r}")

    for path in (
        "runtime.runtime_arn",
        "operator_runtime.runtime_arn",
        "memory.memory_id",
        "gateway.gateway_id",
        "gateway.gateway_arn",
        "gateway.gateway_url",
        "policy.policy_engine_id",
        "observability.transaction_search.resource_policy",
        "observability.transaction_search.resource_policy_document",
        "observability.control_plane_audit.event_name",
        "observability.control_plane_audit.event_time",
        "observability.control_plane_audit.resource_type",
        "observability.runtime_log_group.name",
        "observability.runtime_log_group.kms_key_arn",
        "observability.operator_runtime_log_group.name",
        "observability.operator_runtime_log_group.kms_key_arn",
        "observability.trace_log_groups.kms_key_arn",
        "observability.unified_trace.trace_id",
        "observability.unified_trace.session_id",
        "observability.unified_trace.runtime_arn",
        "observability.unified_trace.runtime_log_group",
        "verification.runtime_invoke_smoke.session_id",
        "verification.runtime_invoke_smoke.response_preview",
        "verification.runtime_invoke_smoke.build_fingerprint",
        "verification.runtime_invoke_smoke.build_fingerprint_expected",
        "verification.operator_runtime_invoke_smoke.runtime_arn",
        "verification.operator_runtime_invoke_smoke.session_id",
        "verification.operator_runtime_invoke_smoke.build_fingerprint",
    ):
        actual = _value(payload, path)
        if not isinstance(actual, str) or not actual.strip():
            errors.append(f"{path} must be a non-empty string")

    required_checks = (
        "verification.targets_attached",
        "verification.gateway_tools_discovered",
        "verification.memory_seeded",
        "verification.live_policy_allow",
        "verification.live_policy_deny",
        "verification.authenticated_runtime_invoke_smoke",
        "verification.runtime_build_fingerprint_match",
        "verification.operator_runtime_build_fingerprint_match",
        "verification.transaction_search_ready",
        "verification.trace_log_groups_encrypted",
        "verification.trace_log_groups_retention_bounded",
        "verification.control_plane_audit_verified",
        "verification.runtime_log_group_encrypted",
        "verification.runtime_log_group_retention_bounded",
        "verification.unified_trace_delivered",
        "verification.unified_trace_agent_span",
        "verification.unified_trace_model_span",
        "verification.unified_trace_tool_span",
        "verification.unified_trace_tool_io_sanitized",
        "verification.unified_trace_step_latency",
    )
    if content_redacted:
        required_checks += ("verification.unified_trace_content_redacted",)
        for path, expected in {
            "verification.unified_trace_agent_input": False,
            "verification.unified_trace_agent_output": False,
            "verification.unified_trace_tool_io_structured": None,
            "observability.unified_trace.agent_input_observed": False,
            "observability.unified_trace.agent_output_observed": False,
            "observability.unified_trace.tool_input_output_observed": False,
            "observability.unified_trace.tool_input_output_structured": None,
        }.items():
            if _value(payload, path) is not expected:
                errors.append(f"{path} must be {expected!r} under content redaction")
    else:
        required_checks += (
            "verification.unified_trace_agent_input",
            "verification.unified_trace_agent_output",
            "verification.unified_trace_tool_io_structured",
        )
        if _value(payload, "verification.unified_trace_content_redacted") is True:
            errors.append("Content redaction verification must match the observed trace")
    for path in required_checks:
        if _value(payload, path) is not True:
            errors.append(f"{path} must be true")

    expected_build = _value(
        payload, "verification.runtime_invoke_smoke.build_fingerprint_expected"
    )
    for runtime in ("runtime", "operator_runtime"):
        if _value(payload, f"verification.{runtime}_invoke_smoke.build_fingerprint") != expected_build:
            errors.append(f"{runtime} smoke must match the expected package fingerprint")
    operator_arn = _value(payload, "operator_runtime.runtime_arn")
    if operator_arn == _value(payload, "runtime.runtime_arn"):
        errors.append("Operator must use a separate Runtime endpoint")
    if _value(payload, "verification.operator_runtime_invoke_smoke.runtime_arn") != operator_arn:
        errors.append("Operator smoke must match operator_runtime.runtime_arn")
    if _value(payload, "verification.operator_runtime_invoke_smoke.executed_nodes") != [
        "case-investigator", "resolution-planner"
    ]:
        errors.append("Operator smoke must prove both graph nodes in order")

    # Provisioning publishes the catalogue but proves discovery with a seeded
    # shopper token. Staff-only tools must remain absent from that listing.
    # A participant deploy changes the catalogue, not the historical bootstrap
    # trace/Memory proof. Validate that current catalogue against the separate,
    # resource-bound update receipt while retaining every full-provision gate.
    catalogue_receipt = participant if participant is not None else payload
    target_tools = workshop_target_tools()
    published_tools = {name for names in target_tools.values() for name in names}
    shopper_tools = discoverable_tools_for_claims(
        has_staff_scope=False, has_customer_claim=True
    )
    prefixed_tools = {
        f"{target}___{name}"
        for target, names in target_tools.items()
        for name in names
        if name in shopper_tools
    }
    expected_counts = {
        "verification.local_tool_schema.count": len(published_tools),
        "verification.gateway_control_plane.target_count": len(target_tools),
        "verification.gateway_tool_count": len(shopper_tools),
    }
    for path, expected in expected_counts.items():
        actual = _value(catalogue_receipt, path)
        if type(actual) is not int or actual != expected:
            errors.append(f"{path}={actual!r}, expected {expected}")

    expected_lists = {
        "verification.local_tool_schema.canonical_names": published_tools,
        "verification.gateway_control_plane.target_names": set(target_tools),
        "verification.gateway_tool_names": shopper_tools,
        "verification.gateway_prefixed_tool_names": prefixed_tools,
    }
    for path, expected in expected_lists.items():
        actual = _value(catalogue_receipt, path)
        if (
            not isinstance(actual, list)
            or not all(isinstance(name, str) for name in actual)
            or len(actual) != len(expected)
            or set(actual) != expected
        ):
            errors.append(
                f"{path} must match the source catalogue: {sorted(expected)}"
            )

    span_count = _value(payload, "observability.unified_trace.span_count")
    if type(span_count) is not int or span_count < 3:
        errors.append(
            "observability.unified_trace.span_count must include agent, model, and tool spans"
        )
    trace_checks = (
        "observability.unified_trace.agent_span",
        "observability.unified_trace.model_span",
        "observability.unified_trace.tool_span",
        "observability.unified_trace.tool_input_output_sanitized",
        "observability.unified_trace.step_latency_observed",
    )
    if not content_redacted:
        trace_checks += (
            "observability.unified_trace.agent_input_observed",
            "observability.unified_trace.agent_output_observed",
            "observability.unified_trace.tool_input_output_observed",
            "observability.unified_trace.tool_input_output_structured",
        )
    for path in trace_checks:
        if _value(payload, path) is not True:
            errors.append(f"{path} must be true")

    attribute_contract = _value(
        payload, "observability.unified_trace.attribute_contract"
    )
    if not isinstance(attribute_contract, dict):
        errors.append(
            "observability.unified_trace.attribute_contract must be an object"
        )
    else:
        for role, allowed in TRACE_ATTRIBUTE_ALLOWLISTS.items():
            observed = attribute_contract.get(role)
            if content_redacted and observed is not None:
                errors.append(
                    f"observability.unified_trace.attribute_contract.{role} "
                    "must be null under content redaction"
                )
            elif not content_redacted and observed not in allowed:
                errors.append(
                    "observability.unified_trace.attribute_contract."
                    f"{role}={observed!r} is not allowlisted"
                )

    for runtime in ("runtime", "operator_runtime"):
        log_path = f"observability.{runtime}_log_group"
        retention_days = _value(payload, f"{log_path}.retention_days")
        if type(retention_days) is not int or retention_days <= 0:
            errors.append(f"{log_path}.retention_days must be a positive integer")
        runtime_cleanup = _value(payload, f"{log_path}.cleanup")
        if (
            not isinstance(runtime_cleanup, dict)
            or type(runtime_cleanup.get("created_by_workshop")) is not bool
            or runtime_cleanup.get("creation_pending") is True
        ):
            errors.append(f"{log_path}.cleanup must capture ownership")

    trace_groups = _value(payload, "observability.trace_log_groups.groups")
    expected_trace_groups = {"aws/spans", "/aws/application-signals/data"}
    if not isinstance(trace_groups, list) or len(trace_groups) != 2:
        errors.append(
            "observability.trace_log_groups.groups must contain both trace destinations"
        )
    else:
        names = {
            group.get("name")
            for group in trace_groups
            if isinstance(group, dict)
        }
        if names != expected_trace_groups:
            errors.append(
                "observability.trace_log_groups.groups must contain "
                "aws/spans and /aws/application-signals/data"
            )
        expected_kms = _value(
            payload, "observability.trace_log_groups.kms_key_arn"
        )
        expected_retention = _value(
            payload, "observability.trace_log_groups.retention_days"
        )
        for group in trace_groups:
            if not isinstance(group, dict):
                continue
            if group.get("kms_key_arn") != expected_kms:
                errors.append(
                    f"trace log group {group.get('name')!r} must use the receipt KMS key"
                )
            if (
                type(group.get("retention_days")) is not int
                or group.get("retention_days") != expected_retention
                or group["retention_days"] <= 0
            ):
                errors.append(
                    f"trace log group {group.get('name')!r} must use bounded retention"
                )
            cleanup = group.get("cleanup")
            if (
                not isinstance(cleanup, dict)
                or type(cleanup.get("created_by_workshop")) is not bool
                or cleanup.get("creation_pending") is True
            ):
                errors.append(
                    f"trace log group {group.get('name')!r} must capture cleanup ownership"
                )

    observed_groups = [
        _value(payload, "observability.runtime_log_group"),
        _value(payload, "observability.operator_runtime_log_group"),
        *(trace_groups if isinstance(trace_groups, list) else []),
    ]
    for group in observed_groups:
        if not isinstance(group, dict):
            continue
        for evidence_type in ("requested", "observed"):
            evidence = group.get(evidence_type)
            if not isinstance(evidence, dict) or any(
                evidence.get(setting) != group.get(setting)
                for setting in ("kms_key_arn", "retention_days")
            ):
                errors.append(
                    f"log group {group.get('name')!r} must record matching "
                    f"{evidence_type} encryption and retention settings"
                )

    transaction_cleanup = _value(
        payload, "observability.transaction_search.cleanup"
    )
    transaction_policy_document = _value(
        payload, "observability.transaction_search.resource_policy_document"
    )
    if isinstance(transaction_policy_document, str):
        try:
            parsed_policy = json.loads(transaction_policy_document)
        except json.JSONDecodeError:
            parsed_policy = None
        if not isinstance(parsed_policy, dict):
            errors.append(
                "observability.transaction_search.resource_policy_document "
                "must be a JSON object"
            )
    if not isinstance(transaction_cleanup, dict):
        errors.append(
            "observability.transaction_search.cleanup must capture prior state"
        )
    else:
        if type(transaction_cleanup.get("destination_changed")) is not bool:
            errors.append(
                "observability.transaction_search.cleanup.destination_changed "
                "must be boolean"
            )
        if transaction_cleanup.get("previous_destination") not in {
            "XRay",
            "CloudWatchLogs",
        }:
            errors.append(
                "observability.transaction_search.cleanup.previous_destination "
                "must be XRay or CloudWatchLogs"
            )
        if type(transaction_cleanup.get("resource_policy_created")) is not bool:
            errors.append(
                "observability.transaction_search.cleanup.resource_policy_created "
                "must be boolean"
            )

    step_latencies = _value(payload, "observability.unified_trace.step_latency_ms")
    if not isinstance(step_latencies, dict):
        errors.append(
            "observability.unified_trace.step_latency_ms must contain agent, model, and tool"
        )
    else:
        for kind in ("agent", "model", "tool"):
            latency = step_latencies.get(kind)
            if type(latency) is not int or latency < 0:
                errors.append(
                    "observability.unified_trace.step_latency_ms."
                    f"{kind} must be a non-negative integer"
                )

    for path in (
        "observability.unified_trace.span_names",
        "observability.unified_trace.model_ids",
        "observability.unified_trace.tool_names",
    ):
        values = _value(payload, path)
        if (
            not isinstance(values, list)
            or not values
            or not all(isinstance(value, str) and value for value in values)
        ):
            errors.append(f"{path} must contain observed non-empty strings")

    trace_session = _value(payload, "observability.unified_trace.session_id")
    smoke_session = _value(payload, "verification.runtime_invoke_smoke.session_id")
    if trace_session != smoke_session:
        errors.append(
            "observability.unified_trace.session_id must match "
            "verification.runtime_invoke_smoke.session_id"
        )
    trace_runtime = _value(payload, "observability.unified_trace.runtime_arn")
    runtime_arn = _value(payload, "runtime.runtime_arn")
    if trace_runtime != runtime_arn:
        errors.append(
            "observability.unified_trace.runtime_arn must match runtime.runtime_arn"
        )

    allow = _value(payload, "verification.live_policy_proof.allow")
    if not isinstance(allow, dict) or allow.get("outcome") != "allow":
        errors.append("verification.live_policy_proof.allow must prove ALLOW")
    elif allow.get("tool_audit_row_after_call") is None:
        errors.append("Policy ALLOW must include an execution audit row")

    deny = _value(payload, "verification.live_policy_proof.deny")
    if not isinstance(deny, dict) or deny.get("outcome") != "deny":
        errors.append("verification.live_policy_proof.deny must prove DENY")
    elif (
        deny.get("cedar_denial") is not True
        or "tool_audit_row_after_call" not in deny
        or deny["tool_audit_row_after_call"] is not None
    ):
        errors.append("Policy DENY must be Cedar-specific and pre-execution")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--participant", type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.receipt.read_text(encoding="utf-8"))
        participant = (
            json.loads(args.participant.read_text(encoding="utf-8"))
            if args.participant else None
        )
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read receipt: {exc}", file=sys.stderr)
        return 1
    if not isinstance(payload, dict) or (
        args.participant and not isinstance(participant, dict)
    ):
        print("each receipt root must be a JSON object", file=sys.stderr)
        return 1

    errors = validate_receipt(payload, participant)
    if errors:
        print("; ".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
