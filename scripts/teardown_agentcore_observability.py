#!/usr/bin/env python3
"""Remove the account-level observability state created for the workshop."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


TRANSACTION_SEARCH_POLICY = "TransactionSearchXRayAccess"
RUNTIME_LOG_PREFIX = "/aws/bedrock-agentcore/runtimes/"
TRACE_LOG_GROUP_NAMES = {"aws/spans", "/aws/application-signals/data"}
AWS_CONFIG = Config(
    retries={"total_max_attempts": 5, "mode": "adaptive"},
    connect_timeout=10,
    read_timeout=30,
)


def _load_receipt(path: Path) -> dict[str, Any]:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return {}
    with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
        before = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_mode & 0o077
            or before.st_nlink != 1
            or before.st_size > 4 * 1024 * 1024
        ):
            raise ValueError(
                "managed receipt must be an owned private regular file "
                "with one link and at most 4 MiB"
            )
        payload = json.load(stream)
        after = os.fstat(stream.fileno())
        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or after.st_nlink != 1
        ):
            raise ValueError("managed receipt changed while being read")
    if not isinstance(payload, dict):
        raise ValueError("managed receipt root must be a JSON object")
    return payload


def _receipt_account(receipt: dict[str, Any], region: str) -> str:
    """Bind even account-wide cleanup to the captured deployment identity."""
    if not receipt or receipt.get("region") != region:
        raise ValueError("cleanup region must match the captured managed receipt")
    accounts: set[str] = set()
    captured_account = receipt.get("account_id")
    if captured_account is not None:
        if not re.fullmatch(r"\d{12}", str(captured_account)):
            raise ValueError("managed receipt has an invalid account_id")
        accounts.add(str(captured_account))
    resources = [
        (receipt.get(key) or {}).get(field)
        for key, field in (
            ("runtime", "runtime_arn"),
            ("gateway", "gateway_arn"),
            ("memory", "memory_arn"),
        )
        if isinstance(receipt.get(key) or {}, dict)
    ]
    lambdas = receipt.get("lambdas")
    if isinstance(lambdas, dict):
        resources.extend(
            value.get("function_arn")
            for value in lambdas.values()
            if isinstance(value, dict)
        )
    for arn in resources:
        if not arn:
            continue
        match = re.fullmatch(
            r"arn:[^:]+:(?:bedrock-agentcore|lambda):([a-z0-9-]+):(\d{12}):.+",
            str(arn),
        )
        if not match or match[1] != region:
            raise ValueError("managed receipt resource ARN has a different region")
        accounts.add(match[2])
    if len(accounts) != 1:
        raise ValueError("managed receipt must identify exactly one AWS account")
    return accounts.pop()


def _runtime_log_group(
    receipt: dict[str, Any],
    override: str | None,
    *,
    runtime_key: str = "runtime",
) -> str | None:
    observability = receipt.get("observability")
    runtime = (
        observability.get(f"{runtime_key}_log_group")
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
    identity = receipt.get(runtime_key)
    arn = identity.get("runtime_arn") if isinstance(identity, dict) else None
    match = re.fullmatch(
        r"arn:[^:]+:bedrock-agentcore:[a-z0-9-]+:\d{12}:runtime/"
        r"([A-Za-z0-9_]+-[A-Za-z0-9]+)",
        str(arn or ""),
    )
    pellier_name = (
        r"(?:pellier[a-z0-9]{0,12}_)?pellier(?:_[a-z0-9]{1,12})?"
        r"_(?:orchestrator|operator)-[A-Za-z0-9]+"
    )
    if (
        not match
        or not re.fullmatch(pellier_name, match[1])
        or value != f"{RUNTIME_LOG_PREFIX}{match[1]}-DEFAULT"
    ):
        raise ValueError(
            "runtime log group must match the captured Pellier AgentCore Runtime "
            f"ARN in {runtime_key}.runtime_arn"
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


def _find_resource_policy(
    logs: Any, policy_name: str | None, *, resource_arn: str | None = None,
) -> dict[str, Any] | None:
    paginator = logs.get_paginator("describe_resource_policies")
    request = {"resourceArn": resource_arn, "policyScope": "RESOURCE"} if resource_arn else {}
    for page in paginator.paginate(**request):
        for policy in page.get("resourcePolicies", []):
            if resource_arn or policy.get("policyName") == policy_name:
                return policy
    return None


def _find_log_group(logs: Any, log_group_name: str) -> dict[str, Any] | None:
    paginator = logs.get_paginator("describe_log_groups")
    for page in paginator.paginate(logGroupNamePrefix=log_group_name):
        for group in page.get("logGroups", []):
            if group.get("logGroupName") == log_group_name:
                return group
    return None


def _policy_unchanged(current: dict[str, Any], step: dict[str, Any]) -> bool:
    return (
        _policy_document(current.get("policyDocument"))
        == _policy_document(step.get("expected_policy_document"))
        and (step.get("expected_revision_id") is None
             or current.get("revisionId") == step["expected_revision_id"])
    )


def _policy_request(step: dict[str, Any], current: dict[str, Any]) -> dict[str, str]:
    if not step.get("resource_arn"):
        return {"policyName": step["policy_name"]}
    if not current.get("revisionId"):
        raise ValueError("Runtime delivery cleanup requires the current policy revision")
    return {"resourceArn": step["resource_arn"], "expectedRevisionId": current["revisionId"]}


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
    if transaction_cleanup.get("indexing_rule_update_started") is True:
        previous = transaction_cleanup.get("previous_indexing_rule")
        expected = transaction_search.get("indexing_rule")
        previous_percentage = previous.get("desired_sampling_percentage") if isinstance(previous, dict) else None
        if (
            not isinstance(previous, dict)
            or previous.get("name") != "Default"
            or type(previous_percentage) not in {int, float}
            or not math.isfinite(previous_percentage)
            or not 0 <= previous_percentage <= 100
            or not isinstance(expected, dict)
            or expected.get("name") != "Default"
            or type(expected.get("desired_sampling_percentage")) not in {int, float}
            or expected.get("desired_sampling_percentage") != 100
        ):
            raise ValueError("receipt has no valid captured Default indexing rule")
        plan.append({
            "service": "xray",
            "operation": "restore_indexing_rule",
            "name": "Default",
            "desired_sampling_percentage": previous_percentage,
            "expected_desired_sampling_percentage": 100,
            "expected_modified_at": expected.get("modified_at"),
        })
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

    for runtime_key, name in (("runtime", runtime_group),):
        group = observability.get(f"{runtime_key}_log_group")
        delivery = group.get("delivery") if isinstance(group, dict) else None
        if not isinstance(delivery, dict):
            continue
        cleanup = delivery.get("cleanup") or {}
        if cleanup.get("policy_changed") is not True:
            continue
        arn = receipt[runtime_key]["runtime_arn"].split(":", 5)
        expected_resource = f"arn:{arn[1]}:logs:{arn[3]}:{arn[4]}:log-group:{name}"
        if delivery.get("resource_arn") != expected_resource or not _policy_document(delivery.get("policy_document")):
            raise ValueError("Runtime delivery policy must match its captured log group")
        step = {
            "service": "logs", "resource_arn": expected_resource,
            "expected_policy_document": delivery["policy_document"],
            "expected_revision_id": delivery.get("revision_id"),
        }
        if cleanup.get("policy_created") is True:
            plan.append({**step, "operation": "delete_resource_policy"})
        else:
            previous = cleanup.get("previous_policy_document")
            if not _policy_document(previous):
                raise ValueError("Runtime delivery policy has no valid previous document")
            plan.append({**step, "operation": "restore_resource_policy", "policy_document": previous})

    groups: list[dict[str, Any]] = []
    trace_log_groups = observability.get("trace_log_groups")
    if isinstance(trace_log_groups, dict):
        for group in trace_log_groups.get("groups", []):
            if not isinstance(group, dict) or group.get("name") not in TRACE_LOG_GROUP_NAMES:
                raise ValueError("receipt contains an unexpected trace log group")
            groups.append(group)
    runtime = observability.get("runtime_log_group")
    if isinstance(runtime, dict):
        groups.append(runtime)
    elif runtime_group:
        raise ValueError(
            "runtime log group override requires a receipt with captured "
            "ownership and configuration"
        )
    for kind, field, prefix in (
        ("gateway", "gateway_id", "/aws/vendedlogs/bedrock-agentcore/"),
        ("memory", "memory_id", "/aws/vendedlogs/bedrock-agentcore/memory/APPLICATION_LOGS/"),
    ):
        telemetry = observability.get(kind)
        if not isinstance(telemetry, dict):
            continue
        group = telemetry.get("log_group_protection")
        if group is None:
            continue  # Older receipts do not authorize changes to these groups.
        identity = receipt.get(kind) or {}
        identifier = identity.get(field) if isinstance(identity, dict) else None
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", identifier):
            raise ValueError(f"{kind} log group requires its captured resource ID")
        if not isinstance(group, dict) or group.get("name") != prefix + identifier:
            raise ValueError(f"{kind} log group must match its captured resource ID")
        groups.append(group)

    seen_groups: set[str] = set()
    for group in groups:
        name = str(group.get("name") or "")
        if name in seen_groups:
            raise ValueError(f"receipt repeats a log group: {name}")
        seen_groups.add(name)
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
            if operation == "restore_indexing_rule":
                current = None
                token = None
                while True:
                    response = xray.get_indexing_rules(**({"NextToken": token} if token else {}))
                    current = next((rule for rule in response.get("IndexingRules", []) if rule.get("Name") == step["name"]), None)
                    token = response.get("NextToken")
                    if current is not None or not token:
                        break
                percentage = (current or {}).get("Rule", {}).get("Probabilistic", {}).get("DesiredSamplingPercentage")
                expected_modified_at = step.get("expected_modified_at")
                if (
                    current is None
                    or percentage != step["expected_desired_sampling_percentage"]
                    or (expected_modified_at is not None and str(current.get("ModifiedAt")) != expected_modified_at)
                ):
                    results.append({**step, "status": "skipped_external_change"})
                else:
                    xray.update_indexing_rule(
                        Name=step["name"],
                        Rule={"Probabilistic": {"DesiredSamplingPercentage": step["desired_sampling_percentage"]}},
                    )
                    results.append({**step, "status": "restored"})
            elif operation == "restore_trace_segment_destination":
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
                current = _find_resource_policy(logs, step.get("policy_name"), resource_arn=step.get("resource_arn"))
                if current is None:
                    results.append({**step, "status": "already_absent"})
                elif not _policy_unchanged(current, step):
                    results.append(
                        {**step, "status": "skipped_external_change"}
                    )
                else:
                    logs.delete_resource_policy(**_policy_request(step, current))
                    results.append({**step, "status": "removed"})
            elif operation == "restore_resource_policy":
                current = _find_resource_policy(logs, step.get("policy_name"), resource_arn=step.get("resource_arn"))
                if current is None or not _policy_unchanged(current, step):
                    results.append(
                        {**step, "status": "skipped_external_change"}
                    )
                else:
                    logs.put_resource_policy(
                        **_policy_request(step, current),
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
        help="Pellier Runtime log group, which must match the captured receipt.",
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
        account_id = _receipt_account(receipt, args.region)
        plan = cleanup_plan(
            receipt,
            runtime_log_group=args.runtime_log_group,
        )
        if args.dry_run:
            print(json.dumps(
                {"region": args.region, "account_id": account_id, "plan": plan},
                indent=2,
            ))
            return 0
        if not args.confirm_workshop_cleanup:
            parser.error(
                "destructive cleanup requires --confirm-workshop-cleanup "
                "(use --dry-run to inspect first)"
            )
        caller = boto3.client(
            "sts", region_name=args.region, config=AWS_CONFIG
        ).get_caller_identity()
        if caller.get("Account") != account_id:
            raise ValueError("active AWS account does not match the managed receipt")
        results = execute_cleanup(region=args.region, plan=plan)
        print(json.dumps({"region": args.region, "results": results}, indent=2))
        return 0
    except (ClientError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"AgentCore observability cleanup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
