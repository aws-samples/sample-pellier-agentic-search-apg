#!/usr/bin/env python3
"""Provision and prove Pellier's managed AgentCore path.

AgentCore CLI is the only control-plane deployment path for Runtime, Memory,
Gateway, Gateway target registrations, AgentCore-managed service roles, Policy
engine, and Cedar policies. ``deploy_lambda.py`` owns the external Lambda
functions and their Lambda execution roles. The remaining Python/AWS SDK code
is limited to Aurora preflight, Memory data seeding, authentication, and
post-deploy proof.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


DEPLOY_DIR = Path(__file__).resolve().parent / "deploy"
if str(DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(DEPLOY_DIR))

from gateway_tool_schemas import (  # noqa: E402
    STAFF_ONLY_GATEWAY_TOOLS,
    TOOL_SCHEMAS,
    discoverable_tools_for_claims,
    schema_for,
)
from render_agentcore_project import (  # noqa: E402
    DEPLOYMENT_SUFFIX,
    AGENTCORE_CLI,
    FINGERPRINT_ENV_VAR,
    GATEWAY_NAME,
    MEMORY_NAME,
    POLICY_ENGINE_NAME,
    INITIATE_RETURN_ACTION,
    PROJECT_NAME,
    RUNTIME_NAME,
    OPERATOR_RUNTIME_NAME,
    project_root,
    render_project,
)


# Lambda names carry the deployment suffix so a release candidate's functions
# sit beside a live set; target names inside the Gateway do not, because the
# Cedar action ids the workshop teaches embed them and a Gateway scopes them.
_SERVER_PREFIX = f"pellier-{DEPLOYMENT_SUFFIX}" if DEPLOYMENT_SUFFIX else "pellier"
EXPECTED_TARGETS = {
    "search": {
        "handler": "pellier_search_server.lambda_handler",
        "server_name": f"{_SERVER_PREFIX}-search-server",
        "entrypoint": "scripts/deploy/pellier_search_server.py",
    },
    "pricing": {
        "handler": "pellier_pricing_server.lambda_handler",
        "server_name": f"{_SERVER_PREFIX}-pricing-server",
        "entrypoint": "scripts/deploy/pellier_pricing_server.py",
    },
    "recommendation": {
        "handler": "pellier_recommend_server.lambda_handler",
        "server_name": f"{_SERVER_PREFIX}-recommend-server",
        "entrypoint": "scripts/deploy/pellier_recommend_server.py",
    },
    "experience": {
        "handler": "pellier_experience_server.lambda_handler",
        "server_name": f"{_SERVER_PREFIX}-experience-server",
        "entrypoint": "scripts/deploy/pellier_experience_server.py",
    },
}

AWS_CONFIG = Config(
    retries={"total_max_attempts": 5, "mode": "adaptive"},
    connect_timeout=10,
    read_timeout=60,
)
TRANSACTION_SEARCH_POLICY = "TransactionSearchXRayAccess"
# AWS documents up to ten minutes for first-time Transaction Search activation.
# Allow a propagation margin; PENDING must never count as managed readiness.
TRANSACTION_SEARCH_ACTIVATION_TIMEOUT_SECONDS = 900
TRANSACTION_SEARCH_POLL_SECONDS = 5
TRANSACTION_SEARCH_PROGRESS_SECONDS = 30
# Unified traces reach CloudWatch minutes after the invoke: on 2026-09-10 a smoke
# session's trace was listed only after the first 4-minute wait had expired,
# although it did arrive. The bound is generous because a false "no trace"
# here fails a deploy whose every other proof passed; the list window is wider
# than the wait so a late trace is still inside it.
TRACE_DELIVERY_TIMEOUT_SECONDS = 900
TRACE_LIST_WINDOW = "30m"
CLOUDTRAIL_AUDIT_TIMEOUT_SECONDS = 300
CLOUDTRAIL_AUDIT_LOOKBACK_SECONDS = 60
CLOUDTRAIL_AGENTCORE_EVENT_SOURCE = "bedrock-agentcore.amazonaws.com"
_RUNTIME_LOG_RETENTION_DAYS = frozenset(
    {
        1,
        3,
        5,
        7,
        14,
        30,
        60,
        90,
        120,
        150,
        180,
        365,
        400,
        545,
        731,
        1827,
        2192,
        2557,
        2922,
        3288,
        3653,
    }
)
_TRACE_LOG_GROUP_NAMES = (
    "aws/spans",
    "/aws/application-signals/data",
)
_AGENT_INPUT_ATTRIBUTE_KEYS = (
    "gen_ai.input.messages",
    "gen_ai.request.input",
    "gen_ai.prompt",
)
_AGENT_OUTPUT_ATTRIBUTE_KEYS = (
    "gen_ai.output.messages",
    "gen_ai.response.output",
    "gen_ai.completion",
)
_TOOL_INPUT_ATTRIBUTE_KEYS = (
    "gen_ai.tool.call.arguments",
    "gen_ai.tool.input",
    "gen_ai.tool.parameters",
)
_TOOL_OUTPUT_ATTRIBUTE_KEYS = (
    "gen_ai.tool.call.result",
    "gen_ai.tool.output",
    "gen_ai.tool.result",
)
_SENSITIVE_TRACE_VALUE = re.compile(
    r"(authorization|bearer\s|access[_-]?token|id[_-]?token|refresh[_-]?token|"
    r"api[_-]?key|client[_-]?secret|password|secret[_-]?key)",
    re.IGNORECASE,
)


def _run(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env or os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        redacted = list(cmd)
        for index, value in enumerate(redacted[:-1]):
            if value in {"--bearer-token", "--token", "--password", "--client-secret"}:
                redacted[index + 1] = "<redacted>"
        raise RuntimeError(
            f"Command failed: {' '.join(redacted)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def _load_env_fallback(repo: Path) -> None:
    """Fill missing variables from the backend `.env`, never overriding the real ones.

    This provisioner is invoked through `sudo -u <participant> bash -c "..."`, and sudo
    strips the parent environment: only the variables that block explicitly re-exports
    survive. That list was one short. `check_model_access.py` resolves the model ids at
    bootstrap time and writes them into `pellier/backend/.env` (they are not static: an
    account without Opus access gets a documented fallback), but nothing carried
    `AGENT_MODEL_ID` from that file into this process, so `_require_env` raised and the
    entire managed path died. Runtime, Memory, Gateway and Policy all failed on one
    missing string, and the nine readiness failures that followed all had the same cause.

    Reading the file here removes the whole class rather than one variable, and matches
    what `gateway_initiate_return.py` and `reset_memory_runtime.py` already do. The real
    environment still wins, so an explicit export always overrides the file.
    """
    for candidate in (repo / "pellier" / "backend" / ".env", repo / ".env"):
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            # setdefault, not assignment: a variable the caller exported is the caller's
            # decision and a stale file must never quietly win over it.
            if key and value and not os.environ.get(key, "").strip():
                os.environ[key] = value


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _region_from_arn(arn: str, fallback: str) -> str:
    match = re.match(r"^arn:[^:]+:[^:]+:([^:]+):", arn or "")
    return match.group(1) if match else fallback


def _runtime_log_group_name(runtime_arn: str) -> str:
    """Return the one AgentCore Runtime log group this provisioner owns."""
    runtime_id = runtime_arn.rsplit("/", 1)[-1].strip()
    if not runtime_id:
        raise RuntimeError("AgentCore Runtime ARN did not include a runtime id")
    return f"/aws/bedrock-agentcore/runtimes/{runtime_id}-DEFAULT"


# Values that mean "leave retention exactly as deployed".
#
# A deployed installation may legitimately have no retention policy at all, and
# a tool that cannot express that cannot reproduce it. This is deliberately NOT
# the same as `"0"`, which stays rejected below: `0` is not a CloudWatch value,
# and accepting it as a synonym for unbounded would quietly weaken the bounded
# retention contract for anyone who typed it by mistake.
_RETENTION_UNMANAGED = frozenset({"", "never", "never-expire", "unset", "none"})


def _runtime_log_retention_days(value: str) -> int | None:
    """Validate the CloudWatch retention contract, or return None if unmanaged.

    ``None`` means "this deployment does not manage retention": no policy is
    written and none is asserted. Every relevant Pellier log group in the live
    test account is in exactly that state, so refusing to represent it made the
    provisioner unable to describe its own installation.
    """
    if str(value or "").strip().lower() in _RETENTION_UNMANAGED:
        return None
    try:
        days = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "AGENTCORE_RUNTIME_LOG_RETENTION_DAYS must be a supported "
            "CloudWatch Logs retention value, or one of "
            f"{sorted(_RETENTION_UNMANAGED - {''})} to leave it unmanaged"
        ) from exc
    if days not in _RUNTIME_LOG_RETENTION_DAYS:
        supported = ", ".join(str(item) for item in sorted(_RUNTIME_LOG_RETENTION_DAYS))
        raise RuntimeError(
            "AGENTCORE_RUNTIME_LOG_RETENTION_DAYS must be one of: "
            f"{supported}"
        )
    return days


def _find_runtime_log_group(logs: Any, log_group_name: str) -> dict[str, Any] | None:
    """Find one exact log group without relying on a truncated list response."""
    paginator = logs.get_paginator("describe_log_groups")
    for page in paginator.paginate(logGroupNamePrefix=log_group_name):
        for group in page.get("logGroups", []):
            if group.get("logGroupName") == log_group_name:
                return group
    return None


def _write_result(path: Path, result: dict[str, Any]) -> None:
    """Atomically checkpoint a private receipt without following a temp symlink."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, indent=2) + "\n"
    fd, filename = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp",
    )
    temporary = Path(filename)
    try:
        # mkstemp creates the file exclusively with mode 0600 before any data
        # is written. Replacing the destination replaces a symlink itself.
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_log_kms_key_arn(kms_key_arn: str) -> None:
    """Validate a supplied key ARN. An empty value means "no key", not "invalid".

    The live installation has no customer key on any Pellier log group, so
    treating absence as a validation failure made the deployed encryption posture
    impossible to express. A value that IS supplied is still held to the
    customer-managed-key contract: an alias is still rejected.
    """
    if not str(kms_key_arn or "").strip():
        return
    if not re.match(
        r"^arn:[^:]+:kms:[^:]+:\d{12}:key/(?:mrk-)?[0-9a-f-]{36}$",
        kms_key_arn,
    ):
        raise RuntimeError(
            "AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN must be a customer-managed KMS key ARN"
        )


def _require_release_log_protection(kms_key_arn: str, retention_days: int | None) -> None:
    """Require the declared workshop contract before provisioning resources."""
    _validate_log_kms_key_arn(kms_key_arn)
    if not kms_key_arn:
        raise RuntimeError(
            "Managed readiness requires AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN. "
            "Use the governed workshop's Code Editor log key; an existing "
            "deployment without an approved key is not release-ready."
        )
    if type(retention_days) is not int or retention_days not in _RUNTIME_LOG_RETENTION_DAYS:
        raise RuntimeError(
            "Managed readiness requires AGENTCORE_RUNTIME_LOG_RETENTION_DAYS "
            "with a supported positive retention period."
        )


def _log_protection_checks(
    groups: list[dict[str, Any]], *, kms_key_arn: str, retention_days: int | None,
) -> tuple[bool, bool]:
    """Derive verification from read-back settings, never requested values."""
    observed = [group.get("observed") for group in groups]
    encrypted = bool(groups) and bool(kms_key_arn) and all(
        isinstance(group, dict) and group.get("kms_key_arn") == kms_key_arn
        for group in observed
    )
    bounded = (
        bool(groups)
        and type(retention_days) is int
        and retention_days in _RUNTIME_LOG_RETENTION_DAYS
        and all(
            isinstance(group, dict)
            and type(group.get("retention_days")) is int
            and group.get("retention_days") == retention_days
            for group in observed
        )
    )
    return encrypted, bounded


def _ensure_protected_log_group(
    *,
    logs: Any,
    log_group_name: str,
    kms_key_arn: str,
    retention_days: int | None,
    on_cleanup_state: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Create or repair one CloudWatch Logs destination."""
    observed_previous = _find_runtime_log_group(logs, log_group_name)
    previous = dict(observed_previous) if observed_previous is not None else None
    creation_pending = previous is None
    created_by_workshop = False

    def receipt() -> dict[str, Any]:
        return {
            "name": log_group_name,
            "kms_key_arn": kms_key_arn,
            "retention_days": retention_days,
            "requested": {
                "kms_key_arn": kms_key_arn or None,
                "retention_days": retention_days,
            },
            "cleanup": {
                "created_by_workshop": created_by_workshop,
                "creation_pending": creation_pending,
                "previous_kms_key_arn": (
                    previous.get("kmsKeyId")
                    if isinstance(previous, dict)
                    else None
                ),
                "previous_retention_days": (
                    previous.get("retentionInDays")
                    if isinstance(previous, dict)
                    else None
                ),
            },
        }

    if on_cleanup_state is not None:
        on_cleanup_state(receipt())

    if creation_pending:
        try:
            create_args: dict[str, Any] = {"logGroupName": log_group_name}
            if kms_key_arn:
                create_args["kmsKeyId"] = kms_key_arn
            logs.create_log_group(**create_args)
        except logs.exceptions.ResourceAlreadyExistsException:
            raced = _find_runtime_log_group(logs, log_group_name)
            if raced is None:
                raise RuntimeError(
                    "CloudWatch reported an existing log group that could not "
                    f"be read: {log_group_name}"
                )
            previous = dict(raced)
            creation_pending = False
            if on_cleanup_state is not None:
                on_cleanup_state(receipt())
        else:
            created_by_workshop = True
            creation_pending = False
            if on_cleanup_state is not None:
                on_cleanup_state(receipt())

    observed = _find_runtime_log_group(logs, log_group_name)
    if observed is None:
        raise RuntimeError(f"CloudWatch log group was not created: {log_group_name}")

    # Only manage what this deployment declares. An unset key or retention means
    # "leave it as deployed", so the provisioner neither writes nor asserts it.
    # Changing encryption posture as a side effect of an unrelated migration is
    # exactly the churn a vocabulary change must not cause.
    if kms_key_arn and observed.get("kmsKeyId") != kms_key_arn:
        logs.associate_kms_key(logGroupName=log_group_name, kmsKeyId=kms_key_arn)
    if retention_days is not None and observed.get("retentionInDays") != retention_days:
        logs.put_retention_policy(
            logGroupName=log_group_name,
            retentionInDays=retention_days,
        )

    verified = _find_runtime_log_group(logs, log_group_name)
    if verified is None:
        raise RuntimeError(f"CloudWatch log group disappeared: {log_group_name}")
    if kms_key_arn and verified.get("kmsKeyId") != kms_key_arn:
        raise RuntimeError(
            f"CloudWatch log group KMS key is incorrect: {log_group_name}"
        )
    if retention_days is not None and verified.get("retentionInDays") != retention_days:
        raise RuntimeError(
            f"CloudWatch log group retention is incorrect: {log_group_name}"
        )

    result = receipt()
    result["observed"] = {
        "kms_key_arn": verified.get("kmsKeyId"),
        "retention_days": verified.get("retentionInDays"),
    }
    result.update(result["observed"])
    return result


def _deploy_claim_trigger(
    *,
    region: str,
    user_pool_id: str,
    db_cluster_arn: str,
    db_secret_arn: str,
) -> dict[str, Any]:
    """Attach the customer-claim trigger to the workshop pool. Idempotent."""
    deploy_path = str(Path(__file__).resolve().parent / "deploy")
    if deploy_path not in sys.path:
        sys.path.insert(0, deploy_path)
    import deploy_customer_claim_trigger as trigger

    mapping = trigger.mapping_from_database(
        region,
        cluster_arn=db_cluster_arn,
        secret_arn=db_secret_arn,
        allow_empty=True,
    )
    if not mapping:
        raise RuntimeError(
            "pellier.principal_customers is empty; run scripts/seed_principal_mappings.py "
            "before managed provisioning so shopper tokens carry their customer claim"
        )
    return trigger.deploy_trigger(region=region, pool_id=user_pool_id, mapping=mapping)


def _enable_gateway_observability(
    *,
    region: str,
    account_id: str,
    gateway_arn: str,
    gateway_id: str,
) -> dict[str, Any]:
    """Deliver the Gateway's application logs and traces to CloudWatch.

    Vended-log deliveries, as the AgentCore observability guide configures them:
    a delivery source per log type on the Gateway ARN, a CloudWatch Logs
    destination for application logs, an X-Ray destination for traces, and one
    delivery joining each pair. Every call is an upsert or tolerates an existing
    delivery, so a re-run leaves the configuration as it is.
    """
    logs = boto3.client("logs", region_name=region, config=AWS_CONFIG)
    log_group = f"/aws/vendedlogs/bedrock-agentcore/{gateway_id}"
    try:
        logs.create_log_group(logGroupName=log_group)
    except logs.exceptions.ResourceAlreadyExistsException:
        pass
    log_group_arn = f"arn:aws:logs:{region}:{account_id}:log-group:{log_group}"

    logs_source = logs.put_delivery_source(
        name=f"{gateway_id}-logs-source", logType="APPLICATION_LOGS", resourceArn=gateway_arn
    )["deliverySource"]["name"]
    traces_source = logs.put_delivery_source(
        name=f"{gateway_id}-traces-source", logType="TRACES", resourceArn=gateway_arn
    )["deliverySource"]["name"]
    logs_destination = logs.put_delivery_destination(
        name=f"{gateway_id}-logs-destination",
        deliveryDestinationType="CWL",
        deliveryDestinationConfiguration={"destinationResourceArn": log_group_arn},
    )["deliveryDestination"]["arn"]
    traces_destination = logs.put_delivery_destination(
        name=f"{gateway_id}-traces-destination", deliveryDestinationType="XRAY"
    )["deliveryDestination"]["arn"]

    def _deliver(source: str, destination: str) -> str:
        try:
            return str(logs.create_delivery(
                deliverySourceName=source, deliveryDestinationArn=destination
            )["delivery"]["id"])
        except logs.exceptions.ConflictException:
            for delivery in logs.describe_deliveries().get("deliveries", []):
                if (
                    delivery.get("deliverySourceName") == source
                    and delivery.get("deliveryDestinationArn") == destination
                ):
                    return str(delivery["id"])
            raise

    return {
        "log_group": log_group,
        "logs_delivery_id": _deliver(logs_source, logs_destination),
        "traces_delivery_id": _deliver(traces_source, traces_destination),
    }


def _ensure_runtime_log_group(
    *,
    region: str,
    runtime_arn: str,
    kms_key_arn: str,
    retention_days: int | None,
    on_cleanup_state: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Create or repair the Runtime log group before it receives a smoke turn.

    AgentCore emits Runtime payloads to this group. A deployment receipt is
    useful only when the payload-bearing destination has a customer key and
    bounded retention, so this check happens before Runtime invocation.
    """
    _validate_log_kms_key_arn(kms_key_arn)
    logs = boto3.client("logs", region_name=region, config=AWS_CONFIG)
    return _ensure_protected_log_group(
        logs=logs,
        log_group_name=_runtime_log_group_name(runtime_arn),
        kms_key_arn=kms_key_arn,
        retention_days=retention_days,
        on_cleanup_state=on_cleanup_state,
    )


def _ensure_trace_log_groups(
    *,
    region: str,
    kms_key_arn: str,
    retention_days: int | None,
    on_cleanup_state: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Protect both Transaction Search destinations before X-Ray writes spans."""
    _validate_log_kms_key_arn(kms_key_arn)
    logs = boto3.client("logs", region_name=region, config=AWS_CONFIG)
    groups: list[dict[str, Any]] = []
    for name in _TRACE_LOG_GROUP_NAMES:
        groups.append(
            _ensure_protected_log_group(
                logs=logs,
                log_group_name=name,
                kms_key_arn=kms_key_arn,
                retention_days=retention_days,
                on_cleanup_state=on_cleanup_state,
            )
        )
    return {
        "groups": groups,
        "kms_key_arn": kms_key_arn,
        "retention_days": retention_days,
    }


def _configure_transaction_search(
    *,
    region: str,
    account_id: str,
    partition: str,
    on_cleanup_state: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Install the scoped X-Ray delivery policy and require an active destination."""
    logs = boto3.client("logs", region_name=region, config=AWS_CONFIG)
    xray = boto3.client("xray", region_name=region, config=AWS_CONFIG)
    previous_policy: dict[str, Any] | None = None
    next_token: str | None = None
    while True:
        request = {"nextToken": next_token} if next_token else {}
        response = logs.describe_resource_policies(**request)
        previous_policy = next(
            (
                item
                for item in response.get("resourcePolicies", [])
                if item.get("policyName") == TRANSACTION_SEARCH_POLICY
            ),
            None,
        )
        if previous_policy is not None:
            break
        next_token = response.get("nextToken")
        if not next_token:
            break

    destination = xray.get_trace_segment_destination()
    previous_destination = str(destination.get("Destination") or "")
    if previous_destination not in {"XRay", "CloudWatchLogs"}:
        raise RuntimeError(
            "Transaction Search returned an unsupported prior trace destination"
        )
    cleanup = {
        "destination_changed": previous_destination != "CloudWatchLogs",
        "previous_destination": previous_destination,
        "resource_policy_created": previous_policy is None,
        "previous_resource_policy_document": (
            previous_policy.get("policyDocument") if previous_policy else None
        ),
    }
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "TransactionSearchXRayAccess",
                "Effect": "Allow",
                "Principal": {"Service": "xray.amazonaws.com"},
                "Action": "logs:PutLogEvents",
                "Resource": [
                    (
                        f"arn:{partition}:logs:{region}:{account_id}:"
                        "log-group:aws/spans:*"
                    ),
                    (
                        f"arn:{partition}:logs:{region}:{account_id}:"
                        "log-group:/aws/application-signals/data:*"
                    ),
                ],
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": account_id},
                    "ArnLike": {
                        "aws:SourceArn": (
                            f"arn:{partition}:xray:{region}:{account_id}:*"
                        )
                    },
                },
            }
        ],
    }
    policy_document = json.dumps(policy, separators=(",", ":"))
    configuring_receipt = {
        "destination": "CloudWatchLogs",
        "status": "CONFIGURING",
        "resource_policy": TRANSACTION_SEARCH_POLICY,
        "resource_policy_document": policy_document,
        "span_log_group": "aws/spans",
        "cleanup": cleanup,
    }
    if on_cleanup_state is not None:
        on_cleanup_state(configuring_receipt)

    logs.put_resource_policy(
        policyName=TRANSACTION_SEARCH_POLICY,
        policyDocument=policy_document,
    )

    if previous_destination != "CloudWatchLogs":
        xray.update_trace_segment_destination(Destination="CloudWatchLogs")

    started = time.monotonic()
    deadline = started + TRANSACTION_SEARCH_ACTIVATION_TIMEOUT_SECONDS
    next_progress = started
    last_observed: tuple[str, str] | None = None
    while True:
        destination = xray.get_trace_segment_destination()
        observed = (
            str(destination.get("Destination") or "UNKNOWN"),
            str(destination.get("Status") or "UNKNOWN"),
        )
        now = time.monotonic()
        elapsed = int(now - started)
        if observed == ("CloudWatchLogs", "ACTIVE"):
            print(
                f"Transaction Search ACTIVE after {elapsed}s "
                "(destination=CloudWatchLogs)",
                flush=True,
            )
            return {
                "destination": "CloudWatchLogs",
                "status": "ACTIVE",
                "resource_policy": TRANSACTION_SEARCH_POLICY,
                "resource_policy_document": policy_document,
                "span_log_group": "aws/spans",
                "cleanup": cleanup,
            }
        if observed != last_observed or now >= next_progress or now >= deadline:
            waiting_receipt = {
                **configuring_receipt,
                "status": (
                    "PENDING"
                    if observed == ("CloudWatchLogs", "PENDING")
                    else "CONFIGURING"
                ),
                "observed_destination": observed[0],
                "observed_status": observed[1],
                "elapsed_seconds": elapsed,
                "timeout_seconds": TRANSACTION_SEARCH_ACTIVATION_TIMEOUT_SECONDS,
            }
            if on_cleanup_state is not None:
                on_cleanup_state(waiting_receipt)
            print(
                f"Waiting for Transaction Search: destination={observed[0]}, "
                f"status={observed[1]}, elapsed={elapsed}s, "
                f"timeout={TRANSACTION_SEARCH_ACTIVATION_TIMEOUT_SECONDS}s",
                flush=True,
            )
            last_observed = observed
            next_progress = now + TRANSACTION_SEARCH_PROGRESS_SECONDS
        if now >= deadline:
            message = (
                "Transaction Search trace destination did not become "
                f"CloudWatchLogs/ACTIVE within "
                f"{TRANSACTION_SEARCH_ACTIVATION_TIMEOUT_SECONDS}s; "
                f"last observed destination={observed[0]}, status={observed[1]}"
            )
            print(message, file=sys.stderr, flush=True)
            raise RuntimeError(message)
        time.sleep(min(TRANSACTION_SEARCH_POLL_SECONDS, deadline - now))


def _ensure_data_api_enabled(region: str, db_cluster_arn: str) -> None:
    rds = boto3.client("rds", region_name=region, config=AWS_CONFIG)
    cluster_id = db_cluster_arn.rsplit(":", 1)[-1]

    def enabled() -> bool:
        response = rds.describe_db_clusters(DBClusterIdentifier=cluster_id)
        return bool(response["DBClusters"][0].get("HttpEndpointEnabled"))

    if enabled():
        return

    print(f"Enabling Aurora Data API on {cluster_id}...")
    rds.enable_http_endpoint(ResourceArn=db_cluster_arn)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        time.sleep(5)
        if enabled():
            time.sleep(10)
            return
    raise RuntimeError(f"Aurora Data API did not become ready on {cluster_id}")


def _compute_secret_hash(username: str, client_id: str, client_secret: str) -> str:
    digest = hmac.new(
        client_secret.encode("utf-8"),
        msg=f"{username}{client_id}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _cognito_access_token(
    *,
    region: str,
    user_pool_id: str,
    client_id: str,
    credentials_secret_arn: str,
    client_secret_arn: str | None,
) -> tuple[str, str]:
    secrets = boto3.client("secretsmanager", region_name=region, config=AWS_CONFIG)
    cognito = boto3.client("cognito-idp", region_name=region, config=AWS_CONFIG)
    credentials_raw = secrets.get_secret_value(
        SecretId=credentials_secret_arn
    ).get("SecretString", "")
    credentials = json.loads(credentials_raw) if credentials_raw else {}
    users = credentials.get("users", [])
    if not users:
        raise RuntimeError("Cognito test credentials secret has no users")

    username = str(users[0].get("username", ""))
    password = str(users[0].get("password", ""))
    if not username or not password:
        raise RuntimeError("Cognito test credentials are missing username/password")

    auth_parameters = {"USERNAME": username, "PASSWORD": password}
    if client_secret_arn:
        client_secret_raw = secrets.get_secret_value(
            SecretId=client_secret_arn
        ).get("SecretString", "")
        client_secret_payload = json.loads(client_secret_raw) if client_secret_raw else {}
        client_secret = str(client_secret_payload.get("client_secret", ""))
        if client_secret:
            auth_parameters["SECRET_HASH"] = _compute_secret_hash(
                username, client_id, client_secret
            )

    response = cognito.admin_initiate_auth(
        UserPoolId=user_pool_id,
        ClientId=client_id,
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters=auth_parameters,
    )
    access_token = response.get("AuthenticationResult", {}).get("AccessToken")
    if not access_token:
        raise RuntimeError("Cognito did not return an access token")
    verified_user = cognito.get_user(AccessToken=str(access_token))
    verified_username = str(verified_user.get("Username", "")).strip()
    if not verified_username:
        raise RuntimeError("Cognito GetUser did not return a username")
    if verified_username.casefold() != username.casefold():
        raise RuntimeError(
            "Cognito authenticated username did not match the seeded user"
        )
    if verified_username != verified_username.casefold():
        raise RuntimeError(
            "Cognito username is not lowercase; identity-bound workshop policy "
            "would not match lowercase customer_id arguments"
        )
    return str(access_token), verified_username


def _scaffold_cli_project(
    *,
    repo: Path,
    env: dict[str, str],
) -> Path:
    root = project_root(repo)
    config_path = root / "agentcore" / "agentcore.json"
    output_dir = root.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    legacy_root = repo / "pellier" / "backend" / ".agentcore-project"
    if legacy_root.exists():
        shutil.rmtree(legacy_root, ignore_errors=True)

    if not config_path.is_file():
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        _run(
            [
                "npx",
                "-y",
                AGENTCORE_CLI,
                "create",
                "--project-name",
                PROJECT_NAME,
                "--no-agent",
                "--skip-git",
                "--skip-python-setup",
                "--output-dir",
                str(output_dir),
                "--json",
            ],
            cwd=output_dir,
            env=env,
        )
    return root


def _agentcore(
    root: Path,
    *args: str,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    # Pellier stores the Runtime ARN in this application variable. The pinned
    # CLI instead reads it as an endpoint alias, including when deriving the
    # CloudWatch log-group name. Keep the CLI's DEFAULT alias in its child
    # process without replacing the application's ARN.
    cli_env = {**env, "AGENTCORE_RUNTIME_ENDPOINT": "DEFAULT"}
    return _run(
        ["npx", "-y", AGENTCORE_CLI, *args],
        cwd=root,
        env=cli_env,
    )


def _deploy_cli_project(
    *,
    repo: Path,
    account_id: str,
    region: str,
    cognito_pool: str,
    cognito_client: str,
    lambda_arns: dict[str, str],
    model_id: str,
    workshop_id: str,
    env: dict[str, str],
    opus_model_id: str | None = None,
    sonnet_model_id: str | None = None,
    fast_model_id: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Deploy infrastructure first, then add Gateway-scoped Cedar policies."""
    root = _scaffold_cli_project(repo=repo, env=env)
    common = {
        "repo": repo,
        "account_id": account_id,
        "region": region,
        "cognito_pool": cognito_pool,
        "cognito_client": cognito_client,
        "lambda_arns": lambda_arns,
        "model_id": model_id,
        "opus_model_id": opus_model_id or model_id,
        "sonnet_model_id": sonnet_model_id or model_id,
        "fast_model_id": fast_model_id or model_id,
        "workshop_id": workshop_id,
    }

    render_project(**common, include_policies=False)
    _agentcore(root, "validate", env=env)
    _agentcore(root, "deploy", "--yes", "--json", env=env)

    state = _read_deployed_state(root)
    gateway_state = _require_gateway_state(state, GATEWAY_NAME)
    _require_state_resource(state, "policyEngines", POLICY_ENGINE_NAME)

    # Tool-specific Cedar policies must name the Gateway by ARN, which exists
    # only after the first deploy; that is the reason for the second render.
    render_project(
        **common,
        include_policies=True,
        action_token=INITIATE_RETURN_ACTION,
        gateway_arn=str(gateway_state["gatewayArn"]),
    )
    _agentcore(root, "validate", env=env)
    _agentcore(root, "deploy", "--yes", "--json", env=env)
    return root, _read_deployed_state(root)


def _read_deployed_state(root: Path) -> dict[str, Any]:
    path = root / "agentcore" / ".cli" / "deployed-state.json"
    if not path.is_file():
        raise RuntimeError(f"AgentCore CLI deployed state not found: {path}")
    try:
        state = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"AgentCore CLI deployed state is invalid JSON: {path}") from exc
    if not isinstance(state.get("targets"), dict):
        raise RuntimeError("AgentCore CLI deployed state has no targets map")
    return state


def _state_resources(state: dict[str, Any]) -> dict[str, Any]:
    target = state.get("targets", {}).get("default")
    if not isinstance(target, dict):
        target = next(iter(state.get("targets", {}).values()), {})
    resources = target.get("resources", {}) if isinstance(target, dict) else {}
    if not isinstance(resources, dict):
        raise RuntimeError("AgentCore CLI deployed state has no resources")
    return resources


def _require_state_resource(
    state: dict[str, Any],
    category: str,
    name: str,
) -> dict[str, Any]:
    value = _state_resources(state).get(category, {}).get(name)
    if not isinstance(value, dict):
        raise RuntimeError(
            f"AgentCore CLI deployed state is missing {category}.{name}"
        )
    return value


def _require_gateway_state(
    state: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    mcp = _state_resources(state).get("mcp", {})
    value = mcp.get("gateways", {}).get(name) if isinstance(mcp, dict) else None
    if not isinstance(value, dict):
        raise RuntimeError(
            f"AgentCore CLI deployed state is missing mcp.gateways.{name}"
        )
    return value


def _deploy_lambdas(
    *,
    repo: Path,
    deploy_dir: Path,
    region: str,
    db_region: str,
    db_cluster_arn: str,
    db_secret_arn: str,
    db_name: str,
) -> dict[str, str]:
    lambda_client = boto3.client("lambda", region_name=region, config=AWS_CONFIG)
    arns: dict[str, str] = {}
    for surface, config in EXPECTED_TARGETS.items():
        _run(
            [
                sys.executable,
                str(deploy_dir / "deploy_lambda.py"),
                "--region",
                region,
                "--server-name",
                config["server_name"],
                "--db-cluster-arn",
                db_cluster_arn,
                "--db-region",
                db_region,
                "--secret-arn",
                db_secret_arn,
                "--database",
                db_name,
                "--mcp-server-path",
                str(repo / config["entrypoint"]),
                "--handler",
                config["handler"],
            ],
            cwd=repo,
        )
        function_name = f"{config['server_name']}-function"
        response = lambda_client.get_function(FunctionName=function_name)
        arns[surface] = response["Configuration"]["FunctionArn"]
    return arns


def _verify_local_schema() -> dict[str, Any]:
    """Assert the canonical schema is internally consistent, not a fixed count.

    The count was hardcoded to 15 and silently became wrong the moment
    `issue_credit` and `get_ticket_history` were published, so a full provision
    run would have failed its own precondition against a correct schema. What
    actually matters is that every published name is unique and that each one
    resolves to exactly one target, which is what Cedar action ids depend on.
    """
    names: list[str] = []
    target_for: dict[str, str] = {}
    for surface, config in TOOL_SCHEMAS.items():
        for tool in schema_for(surface, workshop=True):
            names.append(tool["name"])
            target_for.setdefault(tool["name"], config["target_name"])

    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise RuntimeError(
            "Canonical Gateway schema publishes duplicate tool names, so a Cedar "
            f"action id would be ambiguous: {duplicates}"
        )
    if not names:
        raise RuntimeError("Canonical Gateway schema publishes no tools")

    return {
        "count": len(names),
        "canonical_names": sorted(names),
        "target_for": target_for,
    }


def _verify_gateway_control_plane(
    *,
    region: str,
    gateway_id: str,
) -> dict[str, Any]:
    control = boto3.client(
        "bedrock-agentcore-control",
        region_name=region,
        config=AWS_CONFIG,
    )
    expected = {schema["target_name"] for schema in TOOL_SCHEMAS.values()}
    observed: set[str] = set()
    paginator = control.get_paginator("list_gateway_targets")
    for page in paginator.paginate(gatewayIdentifier=gateway_id):
        observed.update(
            str(item["name"])
            for item in page.get("items", [])
            if item.get("name")
        )
    if observed != expected:
        raise RuntimeError(
            "Gateway target mismatch: "
            f"expected {sorted(expected)}, observed {sorted(observed)}"
        )
    gateway = control.get_gateway(gatewayIdentifier=gateway_id)
    policy_config = gateway.get("policyEngineConfiguration", {})
    if policy_config.get("mode") != "ENFORCE":
        raise RuntimeError("Gateway Policy mode is not ENFORCE")
    return {
        "target_count": len(observed),
        "target_names": sorted(observed),
        "status": gateway.get("status", "UNKNOWN"),
        "policy_mode": policy_config.get("mode"),
    }


def _as_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _cloudtrail_resource_type(
    event: dict[str, Any],
    *,
    expected_resources: dict[str, str],
) -> str | None:
    """Correlate an Event History entry without retaining its request payload."""
    cloudtrail_event = event.get("CloudTrailEvent")
    try:
        payload = json.loads(cloudtrail_event) if isinstance(cloudtrail_event, str) else {}
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    resource_data = {
        "resources": event.get("Resources", []),
        "requestParameters": payload.get("requestParameters"),
        "responseElements": payload.get("responseElements"),
    }
    searchable = json.dumps(resource_data, sort_keys=True, default=str)
    for resource_type, identifier in expected_resources.items():
        if identifier and identifier in searchable:
            return resource_type
    return None


def _verify_agentcore_control_plane_audit(
    *,
    region: str,
    deployment_started_at: datetime,
    runtime_arn: str,
    gateway_arn: str,
    memory_id: str,
    policy_engine_id: str,
) -> dict[str, str]:
    """Require a recent, correlated AgentCore management event in Event History.

    CloudTrail Event History keeps management events for 90 days without a
    separately configured trail. The receipt retains only safe proof metadata:
    never the CloudTrail user identity, source address, or request contents.
    """
    cloudtrail = boto3.client("cloudtrail", region_name=region, config=AWS_CONFIG)
    started_at = _as_utc(deployment_started_at)
    if started_at is None:
        raise RuntimeError("AgentCore deployment start time must be timezone-aware")
    search_start = started_at - timedelta(seconds=CLOUDTRAIL_AUDIT_LOOKBACK_SECONDS)
    expected_resources = {
        "runtime": runtime_arn,
        "gateway": gateway_arn,
        "memory": memory_id,
        "policy_engine": policy_engine_id,
    }
    deadline = time.monotonic() + CLOUDTRAIL_AUDIT_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        paginator = cloudtrail.get_paginator("lookup_events")
        for page in paginator.paginate(
            LookupAttributes=[
                {
                    "AttributeKey": "EventSource",
                    "AttributeValue": CLOUDTRAIL_AGENTCORE_EVENT_SOURCE,
                }
            ],
            StartTime=search_start,
            PaginationConfig={"PageSize": 50},
        ):
            for event in page.get("Events", []):
                if not isinstance(event, dict):
                    continue
                event_time = _as_utc(event.get("EventTime"))
                if event_time is None or event_time < search_start:
                    continue
                if event.get("EventSource") != CLOUDTRAIL_AGENTCORE_EVENT_SOURCE:
                    continue
                resource_type = _cloudtrail_resource_type(
                    event,
                    expected_resources=expected_resources,
                )
                if resource_type is None:
                    continue
                event_name = str(event.get("EventName", "")).strip()
                if not event_name:
                    continue
                return {
                    "source": "CloudTrail Event History",
                    "event_source": CLOUDTRAIL_AGENTCORE_EVENT_SOURCE,
                    "event_name": event_name,
                    "event_time": event_time.isoformat().replace("+00:00", "Z"),
                    "resource_type": resource_type,
                }
        time.sleep(10)

    raise RuntimeError(
        "CloudTrail Event History did not contain a recent AgentCore management "
        "event correlated to this deployment"
    )


def _unverified_token_claims(access_token: str) -> dict[str, Any]:
    """Read a token's payload without verifying it.

    The Gateway verifies this token; here it is only being asked what claims it
    carries, so the expected discovery set can be shaped like the policy that
    filters it. Nothing security-relevant is decided from this.
    """
    try:
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
    except Exception:  # pragma: no cover - a malformed token fails the call below
        return {}


def _discover_live_gateway_tools(
    *,
    deploy_dir: Path,
    gateway_url: str,
    access_token: str,
) -> dict[str, Any]:
    """Assert the Gateway publishes what this caller is allowed to discover.

    Gateway evaluates Cedar on MCP discovery, so the listing is per identity, not
    per deployment. Comparing it against the whole published catalogue reported a
    working staff-only boundary as a failed deploy (live, 2026-09-10): a shopper
    token cannot see `issue_credit` and never will.

    A shopper's listing therefore carries a second assertion worth more than the
    count: the staff-only tool is absent, proved against the live Gateway rather
    than against the policy text that is supposed to cause it.
    """
    deploy_path = str(deploy_dir)
    if deploy_path not in sys.path:
        sys.path.insert(0, deploy_path)
    from test_gateway_tools import discover_gateway_tools

    tools = discover_gateway_tools(gateway_url, access_token)
    full_names = sorted(str(tool.name) for tool in tools)
    canonical_names = {name.rsplit("__", 1)[-1] for name in full_names}

    claims = _unverified_token_claims(access_token)
    has_staff_scope = bool(str(claims.get("custom:staff_scope") or "").strip())
    has_customer_claim = bool(str(claims.get("custom:customer_id") or "").strip())
    expected = set(
        discoverable_tools_for_claims(
            has_staff_scope=has_staff_scope,
            has_customer_claim=has_customer_claim,
        )
    )
    published = {
        tool["name"]
        for surface in TOOL_SCHEMAS
        for tool in schema_for(surface, workshop=True)
    }
    if len(tools) != len(expected) or canonical_names != expected:
        raise RuntimeError(
            "Live Gateway discovery mismatch for a caller with "
            f"staff_scope={has_staff_scope} customer_claim={has_customer_claim}: "
            f"expected {sorted(expected)}, observed {sorted(canonical_names)} "
            f"(published catalogue is {sorted(published)})"
        )
    leaked = sorted(canonical_names & STAFF_ONLY_GATEWAY_TOOLS) if not has_staff_scope else []
    if leaked:
        raise RuntimeError(
            f"Staff-only tools are discoverable by a non-staff token: {leaked}"
        )
    return {
        "count": len(tools),
        "canonical_names": sorted(canonical_names),
        "prefixed_names": full_names,
        "published_count": len(published),
        "caller_claims": {
            "staff_scope": has_staff_scope,
            "customer_id": has_customer_claim,
        },
        "staff_only_hidden_from_caller": sorted(
            STAFF_ONLY_GATEWAY_TOOLS - canonical_names
        ),
    }


def _seed_memory(
    *,
    repo: Path,
    memory_id: str,
    region: str,
    env: dict[str, str],
) -> dict[str, Any]:
    proc = _run(
        [
            sys.executable,
            str(repo / "scripts" / "deploy" / "seed_agentcore_memory.py"),
            "--memory-id",
            memory_id,
            "--region",
            region,
        ],
        cwd=repo,
        env=env,
    )
    return json.loads(proc.stdout)


def _rendered_build_fingerprint(root: Path) -> str:
    """The build digest the renderer injected into the project's Runtime.

    Read back from the rendered project rather than recomputed, so the smoke
    compares against exactly the value the deployed container was given.
    Empty when the project carries none.
    """
    path = root / "agentcore" / "agentcore.json"
    if not path.is_file():
        return ""
    stack: list[Any] = [json.loads(path.read_text())]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("name") == FINGERPRINT_ENV_VAR and isinstance(node.get("value"), str):
                return node["value"].strip()
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return ""


def _decode_runtime_invoke(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """The Runtime's own JSON envelope from one CLI invoke, or a RuntimeError."""
    try:
        cli_payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AgentCore CLI invoke did not return JSON") from exc
    if cli_payload.get("success") is not True:
        raise RuntimeError("AgentCore CLI invoke did not report success")

    raw_response = cli_payload.get("response")
    if isinstance(raw_response, str):
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "AgentCore CLI Runtime response was not a JSON object"
            ) from exc
    if isinstance(raw_response, dict):
        return raw_response
    raise RuntimeError("AgentCore CLI Runtime response was missing")


def _operator_runtime_smoke(
    *, runtime_arn: str, region: str, expected_fingerprint: str,
) -> dict[str, Any]:
    """Require the IAM endpoint to execute both graph nodes from this package."""
    from services.operator_graph import GRAPH_ID

    session_id = f"operator-smoke-{int(time.time())}-0000000000000000000001"
    payload = {
        "request": "Summarize the supplied deployment fixture.",
        "evidence_text": "[FACT] This is a synthetic deployment fixture, not a customer case.",
        "memory_text": "",
        "contract": 'Return JSON with one key, "summary". State that this is a deployment fixture.',
    }
    client = boto3.client(
        "bedrock-agentcore", region_name=region,
        config=Config(connect_timeout=10, read_timeout=210, retries={"total_max_attempts": 1}),
    )
    response = client.invoke_agent_runtime(
        agentRuntimeArn=runtime_arn, runtimeSessionId=session_id,
        qualifier="DEFAULT", contentType="application/json", accept="application/json",
        payload=json.dumps(payload).encode(),
    )
    stream = response["response"]
    try:
        decoded = json.loads(stream.read(1024 * 1024))
    finally:
        stream.close()
    if not isinstance(decoded, dict) or not isinstance(decoded.get("metadata"), dict):
        raise RuntimeError("Operator Runtime smoke returned an invalid result")
    metadata = decoded["metadata"]
    nodes = metadata.get("executedNodes")
    if not isinstance(nodes, list) or not all(isinstance(node, dict) for node in nodes):
        raise RuntimeError("Operator Runtime smoke returned invalid graph evidence")
    node_ids = [node.get("nodeId") for node in nodes]
    if (
        not expected_fingerprint
        or decoded.get("build_fingerprint") != expected_fingerprint
        or decoded.get("error")
        or metadata.get("graphId") != GRAPH_ID
        or metadata.get("execution") != "agentcore-runtime"
        or metadata.get("status") != "complete"
        or node_ids != ["case-investigator", "resolution-planner"]
        or any(node.get("status") != "completed" for node in nodes)
        or not isinstance(decoded.get("raw"), str)
        or not decoded["raw"].strip()
    ):
        raise RuntimeError("Operator Runtime smoke did not prove this package and both graph nodes")
    return {
        "runtime_arn": runtime_arn,
        "session_id": session_id,
        "build_fingerprint": expected_fingerprint,
        "build_fingerprint_match": True,
        "executed_nodes": node_ids,
        "fixture": True,
    }


def _authenticated_runtime_smoke(
    *,
    root: Path,
    access_token: str,
    username: str,
    env: dict[str, str],
    expected_fingerprint: str = "",
    attempts: int = 12,
    wait_seconds: float = 20.0,
) -> dict[str, Any]:
    """Invoke the deployed Runtime and require the answer to come from THIS build.

    A runtime endpoint reports the new version as live before every warm
    container of the previous version has been retired, so the first invoke
    after a deploy can be answered by yesterday's package. The entrypoint
    echoes the build digest it was started with; the smoke keeps invoking,
    bounded, until that digest is the one the renderer injected, and fails
    with a distinct message when it never is. Without the comparison a smoke
    passing against the old container would certify a package that never ran.

    The budget is sized from a measured swap, not a guess. On 2026-09-10 a Lab 3
    style package change kept answering from the previous container through
    eight attempts spread over about four and a half minutes, then served the
    new build roughly a minute later. Twelve attempts at twenty seconds covers
    that with margin, and costs nothing on the common path where the first
    invoke already carries the expected digest.
    """
    decoded: dict[str, Any] = {}
    answered_by = ""
    for attempt in range(1, max(1, attempts) + 1):
        # A prior session may remain attached to an older Runtime sandbox.
        runtime_session_id = f"builders-smoke-{uuid.uuid4().hex}"
        proc = _agentcore(
            root,
            "invoke",
            "--runtime",
            RUNTIME_NAME,
            "--session-id",
            runtime_session_id,
            "--bearer-token",
            access_token,
            "--prompt",
            "Smoke test: find one linen item under 150. Do not mutate data.",
            "--json",
            env=env,
        )
        decoded = _decode_runtime_invoke(proc)
        answered_by = str(decoded.get("build_fingerprint") or "").strip()
        if not expected_fingerprint or answered_by == expected_fingerprint:
            break
        if attempt < attempts:
            print(
                f"Runtime answered with build {answered_by[:12] or 'unknown'}, "
                f"expected {expected_fingerprint[:12]}; the endpoint is still serving "
                f"the previous version, retrying in {wait_seconds:g}s "
                f"({attempt}/{attempts})",
                flush=True,
            )
            time.sleep(wait_seconds)
    else:
        raise RuntimeError(
            f"Runtime answered with build {answered_by or 'unknown'} after {attempts} "
            f"attempts; expected {expected_fingerprint}. The endpoint is still serving "
            "the previous version, so this package has not been proved to run."
        )

    if not str(decoded.get("response", "")).strip():
        raise RuntimeError("Runtime smoke returned an empty response")
    if decoded.get("rail") != "gateway-mcp":
        raise RuntimeError(
            "Runtime smoke did not use Gateway MCP "
            f"(rail={decoded.get('rail') or 'missing'})"
        )
    return {
        "username": username,
        "session_id": runtime_session_id,
        "rail": decoded["rail"],
        "intent": decoded.get("intent"),
        "specialist": decoded.get("specialist"),
        "gateway_tools": decoded.get("gateway_tools", []),
        "response_preview": str(decoded["response"])[:200],
        "build_fingerprint": answered_by,
        "build_fingerprint_expected": expected_fingerprint,
        "build_fingerprint_match": bool(expected_fingerprint) and answered_by == expected_fingerprint,
        "attempts": attempt,
    }


_REDACTED_CONTENT_MARKER = "[REDACTED]"
_CONTENT_ATTRIBUTE_KEYS = (
    _AGENT_INPUT_ATTRIBUTE_KEYS
    + _AGENT_OUTPUT_ATTRIBUTE_KEYS
    + _TOOL_INPUT_ATTRIBUTE_KEYS
    + _TOOL_OUTPUT_ATTRIBUTE_KEYS
)


def _runtime_redacts_content() -> bool:
    """Whether the deployed entrypoint withholds model and tool content from spans.

    Mirrors ``_env_flag("OTEL_REDACT_MODEL_CONTENT", default=True)`` in
    ``agentcore_runtime.py``: redaction is on unless the variable says otherwise,
    and the trace proof has to expect what the container was told to do.
    """
    raw = os.environ.get("OTEL_REDACT_MODEL_CONTENT", "").strip().lower()
    if not raw:
        return True
    return raw not in {"0", "false", "no", "off"}


def _clear_text_content_keys(spans: list[dict[str, Any]]) -> list[str]:
    """Content attributes that reached the trace as anything but the redaction marker."""
    leaked: set[str] = set()
    for span in spans:
        attributes = span.get("attributes") or {}
        for key in _CONTENT_ATTRIBUTE_KEYS:
            value = attributes.get(key)
            if value is None or value == "":
                continue
            if str(value).strip() == _REDACTED_CONTENT_MARKER:
                continue
            leaked.add(key)
    return sorted(leaked)


def _summarize_trace_records(
    records: Any,
    *,
    trace_id: str,
    session_id: str,
    runtime_arn: str,
    content_redacted: bool = False,
) -> dict[str, Any]:
    """Validate the downloaded unified trace and return bounded proof metadata.

    ``content_redacted`` states what the deployed entrypoint was told to do. When
    the Runtime redacts model content, Strands emits no prompt, completion, or
    tool input/output attributes at all, so the proof is that none reached the
    trace in clear text while the agent, model, tool and session structure
    still did. When redaction is off, the trace must carry sanitized,
    structured tool input and output as before.
    """
    if not isinstance(records, list):
        raise RuntimeError("AgentCore trace download must be a JSON array")

    spans: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        message = record.get("@message")
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except json.JSONDecodeError:
                continue
        if isinstance(message, dict) and message.get("traceId") == trace_id:
            spans.append(message)

    if not spans:
        raise RuntimeError(f"Unified trace {trace_id} contained no span records")

    def attribute_value(value: Any) -> Any:
        """Unwrap both JSON-log and OTLP typed attribute value shapes."""
        if not isinstance(value, dict):
            return value
        for key in (
            "stringValue",
            "boolValue",
            "intValue",
            "doubleValue",
            "arrayValue",
            "kvlistValue",
        ):
            if key in value:
                return value[key]
        if "value" in value:
            return attribute_value(value["value"])
        return value

    def attribute_map(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return {str(key): attribute_value(item) for key, item in value.items()}
        if not isinstance(value, list):
            return {}
        mapped: dict[str, Any] = {}
        for item in value:
            if not isinstance(item, dict) or not item.get("key"):
                continue
            mapped[str(item["key"])] = attribute_value(item.get("value"))
        return mapped

    def attributes(span: dict[str, Any]) -> dict[str, Any]:
        return attribute_map(span.get("attributes"))

    def resource_attributes(span: dict[str, Any]) -> dict[str, Any]:
        resource = span.get("resource")
        value = resource.get("attributes") if isinstance(resource, dict) else None
        return attribute_map(value)

    def first_attribute(
        span_list: list[dict[str, Any]], keys: tuple[str, ...]
    ) -> tuple[str | None, Any]:
        for span in span_list:
            span_attributes = attributes(span)
            for key in keys:
                value = span_attributes.get(key)
                if value not in (None, "", [], {}):
                    return key, value
        return None, None

    def structured_value(value: Any) -> Any:
        """Decode JSON-bearing OTEL values without evaluating free-form text."""
        current = attribute_value(value)
        if isinstance(current, str):
            try:
                current = json.loads(current)
            except json.JSONDecodeError:
                return None
        return current if isinstance(current, (dict, list)) else None

    def numeric_value(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)) and value >= 0:
            return int(value)
        if isinstance(value, str) and re.fullmatch(r"\d+(?:\.\d+)?", value):
            return int(float(value))
        return None

    def duration_ms(span: dict[str, Any]) -> int | None:
        for key in ("durationMs", "duration_ms"):
            value = numeric_value(span.get(key))
            if value is not None:
                return value
        for key in ("durationNanos", "duration_nanos"):
            value = numeric_value(span.get(key))
            if value is not None:
                return int(value / 1_000_000)
        for start_key, end_key in (
            ("startTimeUnixNano", "endTimeUnixNano"),
            ("start_time_unix_nano", "end_time_unix_nano"),
        ):
            start = numeric_value(span.get(start_key))
            end = numeric_value(span.get(end_key))
            if start is not None and end is not None:
                if end >= start:
                    return int((end - start) / 1_000_000)
        return None

    def contains_sensitive_value(value: Any) -> bool:
        if isinstance(value, dict):
            return any(
                _SENSITIVE_TRACE_VALUE.search(str(key))
                or contains_sensitive_value(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return any(contains_sensitive_value(item) for item in value)
        return bool(_SENSITIVE_TRACE_VALUE.search(str(value or "")))

    if not all(
        runtime_arn in str(resource_attributes(span).get("cloud.resource_id", ""))
        for span in spans
    ):
        raise RuntimeError("Unified trace includes a span from another Runtime")

    observed_sessions = {
        str(attributes(span).get("session.id"))
        for span in spans
        if attributes(span).get("session.id")
    }
    if session_id not in observed_sessions:
        raise RuntimeError(
            "Unified trace did not preserve the authenticated Runtime session id"
        )

    agent_spans = [
        span for span in spans if str(span.get("name", "")).startswith("invoke_agent")
    ]
    model_spans = [
        span
        for span in spans
        if span.get("name") == "chat"
        and attributes(span).get("gen_ai.request.model")
    ]
    tool_spans = [
        span
        for span in spans
        if str(span.get("name", "")).startswith("execute_tool")
        and attributes(span).get("gen_ai.tool.name")
    ]
    missing = [
        label
        for label, values in (
            ("agent", agent_spans),
            ("model", model_spans),
            ("tool", tool_spans),
        )
        if not values
    ]
    if missing:
        raise RuntimeError(
            "Unified trace is missing required span classes: " + ", ".join(missing)
        )

    if content_redacted:
        leaked = _clear_text_content_keys(spans)
        if leaked:
            raise RuntimeError(
                "Unified trace exported model or tool content in clear text although "
                "the Runtime redacts it: " + ", ".join(leaked)
            )
        step_latencies = {
            "agent": duration_ms(agent_spans[0]),
            "model": duration_ms(model_spans[0]),
            "tool": duration_ms(tool_spans[0]),
        }
        if any(value is None for value in step_latencies.values()):
            raise RuntimeError(
                "Unified trace is missing per-step latency for agent, model, or tool"
            )
        return {
            "trace_id": trace_id,
            "session_id": session_id,
            "runtime_arn": runtime_arn,
            "span_count": len(spans),
            "span_names": sorted({str(span.get("name", "")) for span in spans}),
            "agent_span": True,
            "model_span": True,
            "tool_span": True,
            "content_redacted": True,
            "agent_input_observed": False,
            "agent_output_observed": False,
            "tool_input_output_observed": False,
            "tool_input_output_structured": None,
            "tool_input_output_sanitized": True,
            "attribute_contract": {
                "agent_input": None,
                "agent_output": None,
                "tool_input": None,
                "tool_output": None,
            },
            "step_latency_observed": True,
            "step_latency_ms": step_latencies,
            "model_ids": sorted(
                {str(attributes(span)["gen_ai.request.model"]) for span in model_spans}
            ),
            "tool_names": sorted(
                {str(attributes(span)["gen_ai.tool.name"]) for span in tool_spans}
            ),
        }

    agent_input_key, agent_input = first_attribute(
        spans, _AGENT_INPUT_ATTRIBUTE_KEYS
    )
    agent_output_key, agent_output = first_attribute(
        spans, _AGENT_OUTPUT_ATTRIBUTE_KEYS
    )
    tool_input_key, tool_input = first_attribute(
        tool_spans, _TOOL_INPUT_ATTRIBUTE_KEYS
    )
    tool_output_key, tool_output = first_attribute(
        tool_spans, _TOOL_OUTPUT_ATTRIBUTE_KEYS
    )
    if agent_input is None or agent_output is None:
        raise RuntimeError(
            "Unified trace is missing required Agent input/output attributes"
        )
    if tool_input is None or tool_output is None:
        raise RuntimeError(
            "Unified trace is missing required sanitized tool input/output attributes"
        )
    structured_tool_input = structured_value(tool_input)
    structured_tool_output = structured_value(tool_output)
    if structured_tool_input is None or structured_tool_output is None:
        raise RuntimeError(
            "Unified trace tool input/output must be structured JSON values"
        )
    if contains_sensitive_value(
        structured_tool_input
    ) or contains_sensitive_value(structured_tool_output):
        raise RuntimeError(
            "Unified trace tool input/output contains a secret or credential marker"
        )

    step_latencies = {
        "agent": duration_ms(agent_spans[0]),
        "model": duration_ms(model_spans[0]),
        "tool": duration_ms(tool_spans[0]),
    }
    if any(value is None for value in step_latencies.values()):
        raise RuntimeError(
            "Unified trace is missing per-step latency for agent, model, or tool"
        )

    return {
        "trace_id": trace_id,
        "session_id": session_id,
        "runtime_arn": runtime_arn,
        "span_count": len(spans),
        "span_names": sorted({str(span.get("name", "")) for span in spans}),
        "agent_span": True,
        "model_span": True,
        "tool_span": True,
        "content_redacted": False,
        "agent_input_observed": True,
        "agent_output_observed": True,
        "tool_input_output_observed": True,
        "tool_input_output_structured": True,
        "tool_input_output_sanitized": True,
        "attribute_contract": {
            "agent_input": agent_input_key,
            "agent_output": agent_output_key,
            "tool_input": tool_input_key,
            "tool_output": tool_output_key,
        },
        "step_latency_observed": True,
        "step_latency_ms": step_latencies,
        "model_ids": sorted(
            {
                str(attributes(span)["gen_ai.request.model"])
                for span in model_spans
            }
        ),
        "tool_names": sorted(
            {
                str(attributes(span)["gen_ai.tool.name"])
                for span in tool_spans
            }
        ),
        "provenance": "agentcore-unified-telemetry",
    }


def _wait_for_unified_trace(
    *,
    root: Path,
    session_id: str,
    runtime_arn: str,
    env: dict[str, str],
) -> dict[str, Any]:
    """Poll the pinned CLI until the smoke invocation has a complete trace."""
    deadline = time.monotonic() + TRACE_DELIVERY_TIMEOUT_SECONDS
    last_error = "trace not listed yet"

    while time.monotonic() < deadline:
        try:
            listed = _agentcore(
                root,
                "traces",
                "list",
                "--runtime",
                RUNTIME_NAME,
                "--since",
                TRACE_LIST_WINDOW,
                "--limit",
                "20",
                "--json",
                env=env,
            )
            payload = json.loads(listed.stdout)
            if payload.get("success") is not True:
                raise RuntimeError("AgentCore CLI trace listing did not report success")
            traces = payload.get("traces")
            if not isinstance(traces, list):
                raise RuntimeError("AgentCore CLI trace listing has no traces array")
            match = next(
                (
                    trace
                    for trace in traces
                    if isinstance(trace, dict)
                    and trace.get("sessionId") == session_id
                    and trace.get("traceId")
                ),
                None,
            )
            if match is None:
                last_error = f"no trace listed for session {session_id}"
                time.sleep(10)
                continue

            trace_id = str(match["traceId"])
            # The CLI writes model/tool trace data. A randomized 0700 directory
            # protects both creation and reading from shared-/tmp path races.
            with tempfile.TemporaryDirectory(prefix="pellier-agentcore-trace-") as directory:
                trace_path = Path(directory) / "trace.json"
                downloaded = _agentcore(
                    root,
                    "traces",
                    "get",
                    trace_id,
                    "--runtime",
                    RUNTIME_NAME,
                    "--since",
                    TRACE_LIST_WINDOW,
                    "--output",
                    str(trace_path),
                    "--json",
                    env=env,
                )
                download_payload = json.loads(downloaded.stdout)
                if download_payload.get("success") is not True:
                    raise RuntimeError(
                        "AgentCore CLI trace download did not report success"
                    )
                records = json.loads(trace_path.read_text(encoding="utf-8"))
            proof = _summarize_trace_records(
                records,
                trace_id=trace_id,
                session_id=session_id,
                runtime_arn=runtime_arn,
                content_redacted=_runtime_redacts_content(),
            )
            proof["listed_span_count"] = int(match.get("spanCount") or 0)
            proof["runtime_log_group"] = _runtime_log_group_name(runtime_arn)
            return proof
        except (OSError, ValueError, RuntimeError) as exc:
            last_error = str(exc)
            time.sleep(10)

    raise RuntimeError(
        "Unified AgentCore trace did not become complete within "
        f"{TRACE_DELIVERY_TIMEOUT_SECONDS}s: {last_error}"
    )


def _live_policy_proof(
    *,
    repo: Path,
    deploy_dir: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    helper = deploy_dir / "gateway_initiate_return.py"
    proofs: dict[str, Any] = {}
    for expected, reason, session_id in (
        ("allow", "damaged", "provision-policy-allow"),
        ("deny", "changed_mind", "provision-policy-deny"),
    ):
        proc = _run(
            [
                sys.executable,
                str(helper),
                "--product-id",
                "31",
                "--reason",
                reason,
                "--expect",
                expected,
                "--record-receipt",
                "--session-id",
                session_id,
            ],
            cwd=repo,
            env=env,
        )
        payload = json.loads(proc.stdout)
        if payload.get("outcome") != expected:
            raise RuntimeError(
                f"Policy {expected.upper()} proof returned {payload.get('outcome')}"
            )
        if expected == "allow" and payload.get("tool_audit_row_after_call") is None:
            raise RuntimeError("Policy ALLOW produced no execution audit row")
        if expected == "deny" and (
            payload.get("tool_audit_row_after_call") is not None
            or payload.get("cedar_denial") is not True
        ):
            raise RuntimeError("Policy DENY did not prove pre-execution blocking")
        proofs[expected] = payload
    return proofs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-path", default=os.environ.get("REPO_PATH", "."))
    parser.add_argument("--output-json", default="/tmp/pellier-agentcore-managed.json")
    args = parser.parse_args()

    repo = Path(args.repo_path).resolve()
    deploy_dir = repo / "scripts" / "deploy"
    output_path = Path(args.output_json)
    # Before the first _require_env, or the fallback cannot help.
    _load_env_fallback(repo)
    region = _require_env("AWS_REGION")
    required = {
        "db_cluster_arn": _require_env("DB_CLUSTER_ARN"),
        "db_secret_arn": _require_env("DB_SECRET_ARN"),
        "cognito_pool": _require_env("COGNITO_POOL"),
        "cognito_client": _require_env("COGNITO_CLIENT"),
        "credentials_secret": _require_env(
            "COGNITO_TEST_CREDENTIALS_SECRET_ARN"
        ),
        # Canonical for a FRESH deployment. Deliberately not used to discover or
        # adopt existing resources: the live test account carries three different
        # values across resources provisioned in separate runs
        # (`dat416-readiness-sweep`, `local-screenshot-20260817`, `unknown`), and
        # picking one of those to match on would silently adopt the wrong set.
        # Existing resources are adopted by ARN; this tag only labels new ones.
        "workshop_id": os.environ.get("WORKSHOP_ID", "").strip() or "dat416",
        "model_id": _require_env("AGENT_MODEL_ID"),
        # Helpers can inspect unmanaged groups. Full managed readiness requires
        # the workshop's declared key and retention before provisioning starts.
        "runtime_log_kms_key_arn": os.environ.get(
            "AGENTCORE_RUNTIME_LOG_KMS_KEY_ARN", ""
        ).strip(),
    }
    runtime_log_retention_days = _runtime_log_retention_days(
        os.environ.get("AGENTCORE_RUNTIME_LOG_RETENTION_DAYS", "")
    )
    opus_model_id = (
        os.environ.get("BEDROCK_OPUS_MODEL", "").strip()
        or required["model_id"]
    )
    sonnet_model_id = (
        os.environ.get("BEDROCK_SONNET_MODEL", "").strip()
        or required["model_id"]
    )
    fast_model_id = _require_env("BEDROCK_FAST_MODEL")
    client_secret_arn = (
        os.environ.get("COGNITO_CLIENT_SECRET_ARN", "").strip() or None
    )
    db_region = os.environ.get("DB_REGION", "").strip() or _region_from_arn(
        required["db_cluster_arn"], region
    )
    db_name = os.environ.get("DB_NAME", "pellier")
    deploy_env = os.environ.copy()
    deploy_env.update({"AWS_REGION": region, "AWS_DEFAULT_REGION": region})

    result: dict[str, Any] = {
        "status": "failed",
        "region": region,
        "cli": {"package": AGENTCORE_CLI},
        "lambdas": {},
        "gateway": {},
        "memory": {},
        "observability": {},
        "policy": {},
        "runtime": {},
        "verification": {},
    }

    def checkpoint() -> None:
        _write_result(output_path, result)

    def checkpoint_trace_log_group(group: dict[str, Any]) -> None:
        trace_log_groups = result["observability"].setdefault(
            "trace_log_groups",
            {
                "groups": [],
                "kms_key_arn": required["runtime_log_kms_key_arn"],
                "retention_days": runtime_log_retention_days,
            },
        )
        groups = trace_log_groups.setdefault("groups", [])
        groups[:] = [
            existing
            for existing in groups
            if existing.get("name") != group.get("name")
        ]
        groups.append(group)
        checkpoint()

    def checkpoint_transaction_search(receipt: dict[str, Any]) -> None:
        result["observability"]["transaction_search"] = receipt
        checkpoint()

    def checkpoint_runtime_log_group(group: dict[str, Any]) -> None:
        result["observability"]["runtime_log_group"] = group
        checkpoint()

    try:
        _require_release_log_protection(
            required["runtime_log_kms_key_arn"], runtime_log_retention_days,
        )
        _ensure_data_api_enabled(db_region, required["db_cluster_arn"])
        local_schema = _verify_local_schema()
        result["verification"]["local_tool_schema"] = local_schema

        lambda_arns = _deploy_lambdas(
            repo=repo,
            deploy_dir=deploy_dir,
            region=region,
            db_region=db_region,
            db_cluster_arn=required["db_cluster_arn"],
            db_secret_arn=required["db_secret_arn"],
            db_name=db_name,
        )
        result["lambdas"] = {
            surface: {"function_arn": arn}
            for surface, arn in lambda_arns.items()
        }

        sts = boto3.client("sts", region_name=region, config=AWS_CONFIG)
        caller = sts.get_caller_identity()
        account_id = caller["Account"]
        result["account_id"] = account_id
        partition = str(caller.get("Arn", "arn:aws:")).split(":", 2)[1]
        trace_log_groups = _ensure_trace_log_groups(
            region=region,
            kms_key_arn=required["runtime_log_kms_key_arn"],
            retention_days=runtime_log_retention_days,
            on_cleanup_state=checkpoint_trace_log_group,
        )
        result["observability"]["trace_log_groups"] = trace_log_groups
        checkpoint()
        encrypted, bounded = _log_protection_checks(
            trace_log_groups["groups"],
            kms_key_arn=required["runtime_log_kms_key_arn"],
            retention_days=runtime_log_retention_days,
        )
        result["verification"]["trace_log_groups_encrypted"] = encrypted
        result["verification"]["trace_log_groups_retention_bounded"] = bounded
        transaction_search = _configure_transaction_search(
            region=region,
            account_id=account_id,
            partition=partition,
            on_cleanup_state=checkpoint_transaction_search,
        )
        result["observability"]["transaction_search"] = transaction_search
        checkpoint()
        result["verification"]["transaction_search_ready"] = True
        agentcore_deployment_started_at = datetime.now(timezone.utc)
        root, state = _deploy_cli_project(
            repo=repo,
            account_id=account_id,
            region=region,
            cognito_pool=required["cognito_pool"],
            cognito_client=required["cognito_client"],
            lambda_arns=lambda_arns,
            model_id=required["model_id"],
            opus_model_id=opus_model_id,
            sonnet_model_id=sonnet_model_id,
            fast_model_id=fast_model_id,
            workshop_id=required["workshop_id"],
            env=deploy_env,
        )
        result["cli"]["project_root"] = str(root)

        runtime_state = _require_state_resource(state, "runtimes", RUNTIME_NAME)
        operator_state = _require_state_resource(state, "runtimes", OPERATOR_RUNTIME_NAME)
        memory_state = _require_state_resource(state, "memories", MEMORY_NAME)
        gateway_state = _require_gateway_state(state, GATEWAY_NAME)
        policy_state = _require_state_resource(
            state, "policyEngines", POLICY_ENGINE_NAME
        )
        runtime_arn = str(runtime_state["runtimeArn"])
        operator_runtime_arn = str(operator_state["runtimeArn"])
        memory_id = str(memory_state["memoryId"])
        gateway_id = str(gateway_state["gatewayId"])
        gateway_arn = str(gateway_state["gatewayArn"])
        gateway_url = str(gateway_state.get("gatewayUrl", ""))
        from output_guardrail import ensure_permission
        result["verification"]["output_guardrail_configuration"] = ensure_permission(
            boto3.client("bedrock-agentcore-control", region_name=region, config=AWS_CONFIG),
            boto3.client("iam", region_name=region, config=AWS_CONFIG),
            gateway_id=gateway_id, region=region,
        )
        policy_engine_id = str(policy_state["policyEngineId"])
        if not gateway_url:
            raise RuntimeError("AgentCore CLI state did not include Gateway URL")

        control_plane_audit = _verify_agentcore_control_plane_audit(
            region=region,
            deployment_started_at=agentcore_deployment_started_at,
            runtime_arn=runtime_arn,
            gateway_arn=gateway_arn,
            memory_id=memory_id,
            policy_engine_id=policy_engine_id,
        )
        result["observability"]["control_plane_audit"] = control_plane_audit
        result["verification"]["control_plane_audit_verified"] = True

        result["runtime"] = {
            "runtime_arn": runtime_arn,
            "agent_model_id": required["model_id"],
            "opus_model_id": opus_model_id,
            "sonnet_model_id": sonnet_model_id,
        }
        result["operator_runtime"] = {
            "runtime_arn": operator_runtime_arn,
            "authentication": "AWS_IAM",
            "agent_model_id": sonnet_model_id,
        }
        def checkpoint_operator_log_group(group: dict[str, Any]) -> None:
            result["observability"]["operator_runtime_log_group"] = group
            checkpoint()

        operator_log_group = _ensure_runtime_log_group(
            region=region,
            runtime_arn=operator_runtime_arn,
            kms_key_arn=required["runtime_log_kms_key_arn"],
            retention_days=runtime_log_retention_days,
            on_cleanup_state=checkpoint_operator_log_group,
        )
        result["observability"]["operator_runtime_log_group"] = operator_log_group
        checkpoint()
        runtime_log_group = _ensure_runtime_log_group(
            region=region,
            runtime_arn=runtime_arn,
            kms_key_arn=required["runtime_log_kms_key_arn"],
            retention_days=runtime_log_retention_days,
            on_cleanup_state=checkpoint_runtime_log_group,
        )
        result["observability"]["runtime_log_group"] = runtime_log_group
        checkpoint()
        encrypted, bounded = _log_protection_checks(
            [runtime_log_group, operator_log_group],
            kms_key_arn=required["runtime_log_kms_key_arn"],
            retention_days=runtime_log_retention_days,
        )
        result["verification"]["runtime_log_group_encrypted"] = encrypted
        result["verification"]["runtime_log_group_retention_bounded"] = bounded
        result["memory"] = {
            "memory_id": memory_id,
            "memory_arn": memory_state.get("memoryArn"),
        }
        result["gateway"] = {
            "gateway_id": gateway_id,
            "gateway_arn": gateway_arn,
            "gateway_url": gateway_url,
        }
        result["policy"] = {
            "policy_engine_id": policy_engine_id,
            "policy_engine_arn": policy_state.get("policyEngineArn"),
            "mode": "ENFORCE",
            "gated_tool": "initiate_return",
        }

        control_proof = _verify_gateway_control_plane(
            region=region,
            gateway_id=gateway_id,
        )
        result["verification"]["gateway_control_plane"] = control_proof
        result["verification"]["targets_attached"] = (
            control_proof["target_count"] == 4
        )

        # Identity reaches Cedar as a claim, so the pool's pre-token trigger is
        # part of the authorization boundary and deploys before any token is
        # minted for a proof. The map is read from the same table RLS keys off;
        # bootstrap seeds the mapping before this deployment. An empty map is
        # a provisioning failure because no shopper would carry a customer claim.
        claim_trigger = _deploy_claim_trigger(
            region=region,
            user_pool_id=required["cognito_pool"],
            db_cluster_arn=required["db_cluster_arn"],
            db_secret_arn=required["db_secret_arn"],
        )
        result["identity"] = {"claim_trigger": claim_trigger}
        result["verification"]["claim_trigger_attached"] = (
            claim_trigger["lambdaConfig"].get("PreTokenGenerationConfig", {}).get("LambdaVersion")
            == "V2_0"
        )
        result["verification"]["claim_trigger_mapped_subjects"] = claim_trigger["mappedSubjects"]
        checkpoint()

        # Gateway spans, including the policy engine's own decision attributes,
        # reach aws/spans only once trace delivery is configured on the Gateway.
        gateway_observability = _enable_gateway_observability(
            region=region,
            account_id=account_id,
            gateway_arn=gateway_arn,
            gateway_id=gateway_id,
        )
        result["observability"]["gateway"] = gateway_observability
        result["verification"]["gateway_tracing_enabled"] = bool(
            gateway_observability.get("traces_delivery_id")
        )
        checkpoint()

        access_token, smoke_username = _cognito_access_token(
            region=region,
            user_pool_id=required["cognito_pool"],
            client_id=required["cognito_client"],
            credentials_secret_arn=required["credentials_secret"],
            client_secret_arn=client_secret_arn,
        )
        live_gateway = _discover_live_gateway_tools(
            deploy_dir=deploy_dir,
            gateway_url=gateway_url,
            access_token=access_token,
        )
        result["verification"]["gateway_tools_discovered"] = True
        result["verification"]["gateway_tool_count"] = live_gateway["count"]
        result["verification"]["gateway_tool_names"] = live_gateway[
            "canonical_names"
        ]
        result["verification"]["gateway_prefixed_tool_names"] = live_gateway[
            "prefixed_names"
        ]

        memory_seed = _seed_memory(
            repo=repo,
            memory_id=memory_id,
            region=region,
            env=deploy_env,
        )
        result["memory"]["seed"] = memory_seed
        result["verification"]["memory_seeded"] = (
            memory_seed.get("status") == "ready"
        )

        proof_env = deploy_env.copy()
        proof_env.update(
            {
                "AGENTCORE_GATEWAY_URL": gateway_url,
                "AGENTCORE_GATEWAY_ARN": gateway_arn,
                "AGENTCORE_POLICY_ENGINE_ID": policy_engine_id,
                "PELLIER_TOKEN": access_token,
            }
        )
        policy_proof = _live_policy_proof(
            repo=repo,
            deploy_dir=deploy_dir,
            env=proof_env,
        )
        result["verification"]["live_policy_allow"] = True
        result["verification"]["live_policy_deny"] = True
        result["verification"]["live_policy_proof"] = policy_proof

        runtime_smoke = _authenticated_runtime_smoke(
            root=root,
            access_token=access_token,
            username=smoke_username,
            env=deploy_env,
            expected_fingerprint=_rendered_build_fingerprint(root),
        )
        result["verification"]["authenticated_runtime_invoke_smoke"] = True
        result["verification"]["runtime_invoke_smoke"] = runtime_smoke
        result["verification"]["runtime_build_fingerprint_match"] = runtime_smoke[
            "build_fingerprint_match"
        ]
        operator_smoke = _operator_runtime_smoke(
            runtime_arn=operator_runtime_arn, region=region,
            expected_fingerprint=_rendered_build_fingerprint(root),
        )
        result["verification"]["operator_runtime_invoke_smoke"] = operator_smoke
        result["verification"]["operator_runtime_build_fingerprint_match"] = True
        trace_proof = _wait_for_unified_trace(
            root=root,
            session_id=runtime_smoke["session_id"],
            runtime_arn=runtime_arn,
            env=deploy_env,
        )
        result["observability"]["unified_trace"] = trace_proof
        result["verification"]["unified_trace_delivered"] = True
        result["verification"]["unified_trace_agent_span"] = trace_proof["agent_span"]
        result["verification"]["unified_trace_model_span"] = trace_proof["model_span"]
        result["verification"]["unified_trace_tool_span"] = trace_proof["tool_span"]
        result["verification"]["unified_trace_agent_input"] = trace_proof[
            "agent_input_observed"
        ]
        result["verification"]["unified_trace_agent_output"] = trace_proof[
            "agent_output_observed"
        ]
        result["verification"]["unified_trace_tool_io_sanitized"] = trace_proof[
            "tool_input_output_sanitized"
        ]
        result["verification"]["unified_trace_tool_io_structured"] = trace_proof[
            "tool_input_output_structured"
        ]
        result["verification"]["unified_trace_step_latency"] = trace_proof[
            "step_latency_observed"
        ]
        result["verification"]["unified_trace_content_redacted"] = bool(
            trace_proof.get("content_redacted")
        )

        required_checks = (
            "targets_attached",
            "gateway_tools_discovered",
            "memory_seeded",
            "live_policy_allow",
            "live_policy_deny",
            "authenticated_runtime_invoke_smoke",
            "operator_runtime_build_fingerprint_match",
            "transaction_search_ready",
            "trace_log_groups_encrypted",
            "trace_log_groups_retention_bounded",
            "control_plane_audit_verified",
            "runtime_log_group_encrypted",
            "runtime_log_group_retention_bounded",
            "unified_trace_delivered",
            "unified_trace_agent_span",
            "unified_trace_model_span",
            "unified_trace_tool_span",
            "unified_trace_tool_io_sanitized",
            "unified_trace_step_latency",
        )
        # What a complete trace contains depends on whether the Runtime was told
        # to redact model content, which it is by default. Under redaction the
        # trace carries no prompt, completion, or tool payload at all, and
        # `_summarize_trace_records` has already refused any that leaked. Asking
        # for the content anyway failed a correct deployment for doing the
        # private thing (live, 2026-09-10).
        if result["verification"]["unified_trace_content_redacted"]:
            required_checks += ("unified_trace_content_redacted",)
        else:
            required_checks += (
                "unified_trace_agent_input",
                "unified_trace_agent_output",
                "unified_trace_tool_io_structured",
            )
        missing = [
            check
            for check in required_checks
            if result["verification"].get(check) is not True
        ]
        if missing:
            raise RuntimeError(
                "Managed readiness checks did not pass: " + ", ".join(missing)
            )
        result["status"] = "ready"
        checkpoint()
        print(json.dumps({"status": "ready", "output_json": str(output_path)}))
        return 0
    except (ClientError, RuntimeError, OSError, ValueError) as exc:
        result["error"] = str(exc)
        checkpoint()
        print(
            json.dumps(
                {"status": "failed", "output_json": str(output_path)}
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
