#!/usr/bin/env python3
"""Remove the account-level observability state created for the workshop."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


TRANSACTION_SEARCH_POLICY = "TransactionSearchXRayAccess"
RUNTIME_LOG_PREFIX = "/aws/bedrock-agentcore/runtimes/pellier_orchestrator-"
AWS_CONFIG = Config(
    retries={"total_max_attempts": 5, "mode": "adaptive"},
    connect_timeout=10,
    read_timeout=30,
)


def _load_receipt(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("managed receipt root must be a JSON object")
    return payload


def _runtime_log_group(
    receipt: dict[str, Any],
    override: str | None,
) -> str | None:
    observability = receipt.get("observability")
    runtime = (
        observability.get("runtime_log_group")
        if isinstance(observability, dict)
        else None
    )
    captured = runtime.get("name") if isinstance(runtime, dict) else None
    if override and captured and override != captured:
        raise ValueError(
            "runtime log group override does not match the captured receipt"
        )
    value = override or captured
    if not value:
        return None
    value = str(value).strip()
    if not value.startswith(RUNTIME_LOG_PREFIX) or not value.endswith("-DEFAULT"):
        raise ValueError(
            "runtime log group must be the Pellier AgentCore Runtime DEFAULT group"
        )
    return value


def _policy_document(value: Any) -> dict[str, Any] | None:
    """Normalize a CloudWatch Logs resource policy for safe comparison."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _find_resource_policy(logs: Any, policy_name: str) -> dict[str, Any] | None:
    paginator = logs.get_paginator("describe_resource_policies")
    for page in paginator.paginate():
        for policy in page.get("resourcePolicies", []):
            if policy.get("policyName") == policy_name:
                return policy
    return None


def _find_log_group(logs: Any, log_group_name: str) -> dict[str, Any] | None:
    paginator = logs.get_paginator("describe_log_groups")
    for page in paginator.paginate(logGroupNamePrefix=log_group_name):
        for group in page.get("logGroups", []):
            if group.get("logGroupName") == log_group_name:
                return group
    return None


def cleanup_plan(
    receipt: dict[str, Any],
    *,
    runtime_log_group: str | None = None,
) -> list[dict[str, Any]]:
    """Return operations that restore state captured before provisioning."""
    runtime_group = _runtime_log_group(receipt, runtime_log_group)
    observability = receipt.get("observability")
    observability = observability if isinstance(observability, dict) else {}
    transaction_search = observability.get("transaction_search")
    transaction_search = (
        transaction_search if isinstance(transaction_search, dict) else {}
    )
    transaction_cleanup = transaction_search.get("cleanup")
    transaction_cleanup = (
        transaction_cleanup if isinstance(transaction_cleanup, dict) else {}
    )
    expected_policy_document = transaction_search.get(
        "resource_policy_document"
    )
    if (
        transaction_cleanup.get("resource_policy_created") is True
        or transaction_cleanup.get("previous_resource_policy_document")
    ) and _policy_document(expected_policy_document) is None:
        raise ValueError(
            "receipt has no valid workshop resource policy document"
        )

    plan: list[dict[str, Any]] = []
    if transaction_cleanup.get("destination_changed") is True:
        previous_destination = transaction_cleanup.get("previous_destination")
        if previous_destination not in {"XRay", "CloudWatchLogs"}:
            raise ValueError("receipt has no valid previous X-Ray destination")
        plan.append(
            {
                "service": "xray",
                "operation": "restore_trace_segment_destination",
                "destination": previous_destination,
            }
        )

    if transaction_cleanup.get("resource_policy_created") is True:
        plan.append(
            {
                "service": "logs",
                "operation": "delete_resource_policy",
                "policy_name": TRANSACTION_SEARCH_POLICY,
                "expected_policy_document": expected_policy_document,
            }
        )
    elif transaction_cleanup.get("previous_resource_policy_document"):
        plan.append(
            {
                "service": "logs",
                "operation": "restore_resource_policy",
                "policy_name": TRANSACTION_SEARCH_POLICY,
                "policy_document": transaction_cleanup[
                    "previous_resource_policy_document"
                ],
                "expected_policy_document": expected_policy_document,
            }
        )

    groups: list[dict[str, Any]] = []
    operator_runtime = observability.get("operator_runtime_log_group")
    if isinstance(operator_runtime, dict):
        groups.append(operator_runtime)
    trace_log_groups = observability.get("trace_log_groups")
    if isinstance(trace_log_groups, dict):
        groups.extend(
            group
            for group in trace_log_groups.get("groups", [])
            if isinstance(group, dict)
        )
    runtime = observability.get("runtime_log_group")
    if isinstance(runtime, dict):
        groups.append(runtime)
    elif runtime_group:
        raise ValueError(
            "runtime log group override requires a receipt with captured "
            "ownership and configuration"
        )

    for group in groups:
        name = str(group.get("name") or "")
        cleanup = group.get("cleanup")
        if not name or not isinstance(cleanup, dict):
            raise ValueError(
                "receipt log groups must include captured cleanup ownership"
            )
        if cleanup.get("creation_pending") is True:
            continue
        expected_kms_key_arn = group.get("kms_key_arn")
        expected_retention_days = group.get("retention_days")
        if (
            not isinstance(expected_kms_key_arn, str)
            or not expected_kms_key_arn
            or type(expected_retention_days) is not int
            or expected_retention_days <= 0
        ):
            raise ValueError(
                f"receipt has no valid workshop configuration for {name}"
            )
        if cleanup.get("created_by_workshop") is True:
            plan.append(
                {
                    "service": "logs",
                    "operation": "delete_log_group",
                    "log_group_name": name,
                    "expected_kms_key_arn": expected_kms_key_arn,
                    "expected_retention_days": expected_retention_days,
                }
            )
            continue
        plan.extend(
            [
                {
                    "service": "logs",
                    "operation": "restore_log_group_kms",
                    "log_group_name": name,
                    "kms_key_arn": cleanup.get("previous_kms_key_arn"),
                    "expected_kms_key_arn": expected_kms_key_arn,
                },
                {
                    "service": "logs",
                    "operation": "restore_log_group_retention",
                    "log_group_name": name,
                    "retention_days": cleanup.get("previous_retention_days"),
                    "expected_retention_days": expected_retention_days,
                },
            ]
        )
    return plan


def execute_cleanup(
    *,
    region: str,
    plan: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Execute the allowlisted plan; missing resources count as removed."""
    logs = boto3.client("logs", region_name=region, config=AWS_CONFIG)
    xray = boto3.client("xray", region_name=region, config=AWS_CONFIG)
    results: list[dict[str, Any]] = []

    for step in plan:
        operation = step["operation"]
        try:
            if operation == "restore_trace_segment_destination":
                current = xray.get_trace_segment_destination()
                if current.get("Destination") == "CloudWatchLogs":
                    xray.update_trace_segment_destination(
                        Destination=step["destination"]
                    )
                    results.append({**step, "status": "restored"})
                else:
                    results.append(
                        {**step, "status": "skipped_external_change"}
                    )
            elif operation == "delete_resource_policy":
                current = _find_resource_policy(logs, step["policy_name"])
                if current is None:
                    results.append({**step, "status": "already_absent"})
                elif _policy_document(current.get("policyDocument")) != (
                    _policy_document(step.get("expected_policy_document"))
                ):
                    results.append(
                        {**step, "status": "skipped_external_change"}
                    )
                else:
                    logs.delete_resource_policy(policyName=step["policy_name"])
                    results.append({**step, "status": "removed"})
            elif operation == "restore_resource_policy":
                current = _find_resource_policy(logs, step["policy_name"])
                if current is None or _policy_document(
                    current.get("policyDocument")
                ) != _policy_document(step.get("expected_policy_document")):
                    results.append(
                        {**step, "status": "skipped_external_change"}
                    )
                else:
                    logs.put_resource_policy(
                        policyName=step["policy_name"],
                        policyDocument=step["policy_document"],
                    )
                    results.append({**step, "status": "restored"})
            elif operation == "delete_log_group":
                current = _find_log_group(logs, step["log_group_name"])
                if current is None:
                    results.append({**step, "status": "already_absent"})
                elif (
                    current.get("kmsKeyId")
                    != step["expected_kms_key_arn"]
                    or current.get("retentionInDays")
                    != step["expected_retention_days"]
                ):
                    results.append(
                        {**step, "status": "skipped_external_change"}
                    )
                else:
                    logs.delete_log_group(logGroupName=step["log_group_name"])
                    results.append({**step, "status": "removed"})
            elif operation == "restore_log_group_kms":
                current = _find_log_group(logs, step["log_group_name"])
                if current is None:
                    results.append({**step, "status": "already_absent"})
                elif current.get("kmsKeyId") != step["expected_kms_key_arn"]:
                    results.append(
                        {**step, "status": "skipped_external_change"}
                    )
                else:
                    if step.get("kms_key_arn"):
                        logs.associate_kms_key(
                            logGroupName=step["log_group_name"],
                            kmsKeyId=step["kms_key_arn"],
                        )
                    else:
                        logs.disassociate_kms_key(
                            logGroupName=step["log_group_name"]
                        )
                    results.append({**step, "status": "restored"})
            elif operation == "restore_log_group_retention":
                current = _find_log_group(logs, step["log_group_name"])
                if current is None:
                    results.append({**step, "status": "already_absent"})
                elif (
                    current.get("retentionInDays")
                    != step["expected_retention_days"]
                ):
                    results.append(
                        {**step, "status": "skipped_external_change"}
                    )
                else:
                    if isinstance(step.get("retention_days"), int):
                        logs.put_retention_policy(
                            logGroupName=step["log_group_name"],
                            retentionInDays=step["retention_days"],
                        )
                    else:
                        logs.delete_retention_policy(
                            logGroupName=step["log_group_name"]
                        )
                    results.append({**step, "status": "restored"})
            else:
                raise ValueError(f"unsupported cleanup operation: {operation}")
        except logs.exceptions.ResourceNotFoundException:
            results.append({**step, "status": "already_absent"})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--receipt",
        type=Path,
        default=Path("/tmp/pellier-agentcore-managed.json"),
    )
    parser.add_argument(
        "--runtime-log-group",
        help="Pellier Runtime log group override when no receipt is available.",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-workshop-cleanup", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = _load_receipt(args.receipt)
        plan = cleanup_plan(
            receipt,
            runtime_log_group=args.runtime_log_group,
        )
        if args.dry_run:
            print(json.dumps({"region": args.region, "plan": plan}, indent=2))
            return 0
        if not args.confirm_workshop_cleanup:
            parser.error(
                "destructive cleanup requires --confirm-workshop-cleanup "
                "(use --dry-run to inspect first)"
            )
        results = execute_cleanup(region=args.region, plan=plan)
        print(json.dumps({"region": args.region, "results": results}, indent=2))
        return 0
    except (ClientError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"AgentCore observability cleanup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
