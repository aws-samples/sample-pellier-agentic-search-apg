"""Tests for the guarded AgentCore observability cleanup."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "teardown_agentcore_observability.py"
WORKSHOP_KMS_KEY = "arn:aws:kms:us-east-1:123456789012:key/workshop"
WORKSHOP_POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [{"Sid": "TransactionSearchXRayAccess"}],
    },
    separators=(",", ":"),
)


def _load_script() -> Any:
    spec = importlib.util.spec_from_file_location(
        "teardown_agentcore_observability",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _receipt() -> dict[str, Any]:
    return {
        "region": "us-east-1",
        "runtime": {
            "runtime_arn": (
                "arn:aws:bedrock-agentcore:us-east-1:123456789012:"
                "runtime/pellier_orchestrator-abc123"
            ),
        },
        "observability": {
            "transaction_search": {
                "cleanup": {
                    "destination_changed": True,
                    "previous_destination": "XRay",
                    "resource_policy_created": True,
                    "previous_resource_policy_document": None,
                },
                "resource_policy_document": WORKSHOP_POLICY,
            },
            "trace_log_groups": {
                "groups": [
                    {
                        "name": "aws/spans",
                        "kms_key_arn": WORKSHOP_KMS_KEY,
                        "retention_days": 30,
                        "cleanup": {"created_by_workshop": True},
                    },
                    {
                        "name": "/aws/application-signals/data",
                        "kms_key_arn": WORKSHOP_KMS_KEY,
                        "retention_days": 30,
                        "cleanup": {"created_by_workshop": True},
                    },
                ]
            },
            "runtime_log_group": {
                "name": (
                    "/aws/bedrock-agentcore/runtimes/"
                    "pellier_orchestrator-abc123-DEFAULT"
                ),
                "kms_key_arn": WORKSHOP_KMS_KEY,
                "retention_days": 30,
                "cleanup": {"created_by_workshop": True},
            }
        }
    }


def test_cleanup_plan_is_bounded_to_workshop_observability() -> None:
    module = _load_script()

    plan = module.cleanup_plan(_receipt())

    assert plan == [
        {
            "service": "xray",
            "operation": "restore_trace_segment_destination",
            "destination": "XRay",
        },
        {
            "service": "logs",
            "operation": "delete_resource_policy",
            "policy_name": "TransactionSearchXRayAccess",
            "expected_policy_document": WORKSHOP_POLICY,
        },
        {
            "service": "logs",
            "operation": "delete_log_group",
            "log_group_name": "aws/spans",
            "expected_kms_key_arn": WORKSHOP_KMS_KEY,
            "expected_retention_days": 30,
        },
        {
            "service": "logs",
            "operation": "delete_log_group",
            "log_group_name": "/aws/application-signals/data",
            "expected_kms_key_arn": WORKSHOP_KMS_KEY,
            "expected_retention_days": 30,
        },
        {
            "service": "logs",
            "operation": "delete_log_group",
            "log_group_name": (
                "/aws/bedrock-agentcore/runtimes/"
                "pellier_orchestrator-abc123-DEFAULT"
            ),
            "expected_kms_key_arn": WORKSHOP_KMS_KEY,
            "expected_retention_days": 30,
        },
    ]


def test_cleanup_rejects_an_arbitrary_runtime_log_group() -> None:
    module = _load_script()

    with pytest.raises(ValueError, match="Pellier AgentCore Runtime"):
        module.cleanup_plan(
            {},
            runtime_log_group="/aws/lambda/unrelated-production-function",
        )


@pytest.mark.parametrize("runtime_id", [
    "pellier_pellier_orchestrator-abc123",
    "pellierrc_pellier_rc_orchestrator-abc123",
])
def test_cleanup_accepts_the_exact_captured_cli_runtime(runtime_id: str) -> None:
    module = _load_script()
    receipt = _receipt()
    receipt["runtime"]["runtime_arn"] = (
        f"arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/{runtime_id}"
    )
    name = f"/aws/bedrock-agentcore/runtimes/{runtime_id}-DEFAULT"
    receipt["observability"]["runtime_log_group"]["name"] = name
    assert module.cleanup_plan(receipt)[-1]["log_group_name"] == name


def test_cleanup_includes_the_separate_operator_runtime() -> None:
    module = _load_script()
    receipt = _receipt()
    runtime_id = "pellierrc_pellier_rc_operator-abc123"
    receipt["operator_runtime"] = {
        "runtime_arn": f"arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/{runtime_id}",
    }
    name = f"/aws/bedrock-agentcore/runtimes/{runtime_id}-DEFAULT"
    receipt["observability"]["operator_runtime_log_group"] = {
        "name": name, "kms_key_arn": WORKSHOP_KMS_KEY, "retention_days": 30,
        "cleanup": {"created_by_workshop": True},
    }
    assert module.cleanup_plan(receipt)[-1]["log_group_name"] == name


def test_cleanup_rejects_a_different_pellier_runtime_than_the_receipt() -> None:
    module = _load_script()
    receipt = _receipt()
    receipt["observability"]["runtime_log_group"]["name"] = (
        "/aws/bedrock-agentcore/runtimes/pellierrc_pellier_rc_orchestrator-other-DEFAULT"
    )
    with pytest.raises(ValueError, match="must match the captured"):
        module.cleanup_plan(receipt)


def test_cleanup_requires_captured_runtime_identity() -> None:
    module = _load_script()
    receipt = _receipt()
    del receipt["runtime"]
    with pytest.raises(ValueError, match="must match the captured"):
        module.cleanup_plan(receipt)


def test_cleanup_cannot_smuggle_an_unrelated_group_into_trace_destinations() -> None:
    module = _load_script()
    receipt = _receipt()
    receipt["observability"]["trace_log_groups"]["groups"][0]["name"] = "/aws/lambda/unrelated"
    with pytest.raises(ValueError, match="unexpected trace log group"):
        module.cleanup_plan(receipt)


def test_cleanup_rejects_duplicate_log_groups() -> None:
    module = _load_script()
    receipt = _receipt()
    groups = receipt["observability"]["trace_log_groups"]["groups"]
    groups.append(dict(groups[0]))
    with pytest.raises(ValueError, match="repeats a log group"):
        module.cleanup_plan(receipt)


def test_dry_run_does_not_create_aws_clients(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(_receipt()), encoding="utf-8")
    receipt.chmod(0o600)
    monkeypatch.setattr(
        module.boto3,
        "client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("dry-run created an AWS client")
        ),
    )

    assert module.main([
        "--receipt", str(receipt), "--region", "us-east-1", "--dry-run",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["plan"]) == 5


@pytest.mark.parametrize("unsafe_kind", [
    "symlink", "hardlink", "readable", "writable", "fifo", "oversized",
])
def test_untrusted_receipts_fail_before_any_aws_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, unsafe_kind: str,
) -> None:
    module = _load_script()
    target = tmp_path / "captured.json"
    target.write_text(json.dumps(_receipt()), encoding="utf-8")
    target.chmod(0o600)
    receipt = tmp_path / "receipt.json"
    if unsafe_kind == "symlink":
        receipt.symlink_to(target)
    elif unsafe_kind == "hardlink":
        os.link(target, receipt)
    elif unsafe_kind == "fifo":
        os.mkfifo(receipt, 0o600)
    else:
        receipt.write_bytes(target.read_bytes())
        receipt.chmod(0o644 if unsafe_kind == "readable" else 0o666)
        if unsafe_kind == "oversized":
            receipt.chmod(0o600)
            with receipt.open("a", encoding="utf-8") as stream:
                stream.write(" " * (4 * 1024 * 1024))
    before = target.read_bytes()
    monkeypatch.setattr(
        module.boto3, "client",
        lambda *_a, **_k: pytest.fail("untrusted receipt created an AWS client"),
    )
    assert module.main([
        "--receipt", str(receipt), "--region", "us-east-1",
        "--confirm-workshop-cleanup",
    ]) == 1
    assert target.read_bytes() == before


def test_receipt_from_another_user_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    module = _load_script()
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(_receipt()), encoding="utf-8")
    receipt.chmod(0o600)
    owner = receipt.stat().st_uid
    monkeypatch.setattr(module.os, "geteuid", lambda: owner + 1)
    with pytest.raises(ValueError, match="owned private regular"):
        module._load_receipt(receipt)


def test_receipt_changed_during_read_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    module = _load_script()
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(_receipt()), encoding="utf-8")
    receipt.chmod(0o600)
    original_load = json.load

    def read_then_change(stream):
        payload = original_load(stream)
        with receipt.open("a", encoding="utf-8") as writer:
            writer.write(" ")
        return payload

    monkeypatch.setattr(module.json, "load", read_then_change)
    with pytest.raises(ValueError, match="changed while being read"):
        module._load_receipt(receipt)


@pytest.mark.parametrize("change", [
    "missing-region", "wrong-region", "wrong-resource-region",
    "mixed-account", "missing-account", "empty",
])
def test_cleanup_scope_fails_before_any_aws_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, change: str,
) -> None:
    module = _load_script()
    payload = _receipt()
    if change == "missing-region":
        payload.pop("region")
    elif change == "wrong-region":
        payload["region"] = "us-west-2"
    elif change == "wrong-resource-region":
        payload["runtime"]["runtime_arn"] = payload["runtime"]["runtime_arn"].replace(
            ":us-east-1:", ":us-west-2:",
        )
    elif change == "mixed-account":
        payload["account_id"] = "999999999999"
    elif change == "missing-account":
        payload = {"region": "us-east-1", "observability": payload["observability"]}
    else:
        payload = {}
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    receipt.chmod(0o600)
    monkeypatch.setattr(
        module.boto3, "client",
        lambda *_a, **_k: pytest.fail("invalid scope created an AWS client"),
    )
    assert module.main([
        "--receipt", str(receipt), "--region", "us-east-1",
        "--confirm-workshop-cleanup",
    ]) == 1


@pytest.mark.parametrize("active_account, expected_status", [
    ("999999999999", 1), ("123456789012", 0),
])
def test_cleanup_checks_active_account_before_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    active_account: str, expected_status: int,
) -> None:
    module = _load_script()
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(_receipt()), encoding="utf-8")
    receipt.chmod(0o600)
    clients = []
    executed = []

    class Identity:
        def get_caller_identity(self):
            return {"Account": active_account}

    def client(service, **kwargs):
        clients.append(service)
        assert service == "sts"
        assert kwargs["region_name"] == "us-east-1"
        return Identity()

    def execute(**kwargs):
        executed.append(kwargs)
        return []

    monkeypatch.setattr(module.boto3, "client", client)
    monkeypatch.setattr(module, "execute_cleanup", execute)
    assert module.main([
        "--receipt", str(receipt), "--region", "us-east-1",
        "--confirm-workshop-cleanup",
    ]) == expected_status
    assert clients == ["sts"]
    assert bool(executed) is (expected_status == 0)
    if executed:
        assert executed[0]["region"] == "us-east-1"
        assert executed[0]["plan"] == module.cleanup_plan(_receipt())


def test_partial_provisioning_receipt_can_bind_account_wide_cleanup() -> None:
    module = _load_script()
    receipt = {
        "region": "us-east-1",
        "account_id": "123456789012",
        "observability": _receipt()["observability"],
    }
    assert module._receipt_account(receipt, "us-east-1") == "123456789012"


def test_execute_cleanup_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()

    class _NotFound(Exception):
        pass

    class _Logs:
        class exceptions:
            ResourceNotFoundException = _NotFound

        def __init__(self) -> None:
            self.policy_calls: list[str] = []
            self.group_calls: list[str] = []
            self.groups = {
                name: {
                    "logGroupName": name,
                    "kmsKeyId": WORKSHOP_KMS_KEY,
                    "retentionInDays": 30,
                }
                for name in (
                    "aws/spans",
                    "/aws/application-signals/data",
                    (
                        "/aws/bedrock-agentcore/runtimes/"
                        "pellier_orchestrator-abc123-DEFAULT"
                    ),
                )
            }

        def get_paginator(self, operation: str):
            logs = self

            class _Paginator:
                def paginate(self, **kwargs):
                    if operation == "describe_resource_policies":
                        return [
                            {
                                "resourcePolicies": [
                                    {
                                        "policyName": (
                                            "TransactionSearchXRayAccess"
                                        ),
                                        "policyDocument": WORKSHOP_POLICY,
                                    }
                                ]
                            }
                        ]
                    name = kwargs["logGroupNamePrefix"]
                    group = logs.groups.get(name)
                    return [{"logGroups": [group] if group else []}]

            return _Paginator()

        def delete_resource_policy(self, *, policyName: str) -> None:
            self.policy_calls.append(policyName)
            raise _NotFound()

        def delete_log_group(self, *, logGroupName: str) -> None:
            self.group_calls.append(logGroupName)

    class _XRay:
        def __init__(self) -> None:
            self.destinations: list[str] = []

        def get_trace_segment_destination(self) -> dict[str, str]:
            return {"Destination": "CloudWatchLogs"}

        def update_trace_segment_destination(self, *, Destination: str) -> None:
            self.destinations.append(Destination)

    logs = _Logs()
    xray = _XRay()
    monkeypatch.setattr(
        module.boto3,
        "client",
        lambda service, **_kwargs: logs if service == "logs" else xray,
    )

    results = module.execute_cleanup(
        region="us-east-1",
        plan=module.cleanup_plan(_receipt()),
    )

    assert xray.destinations == ["XRay"]
    assert logs.policy_calls == ["TransactionSearchXRayAccess"]
    assert len(logs.group_calls) == 3
    assert results[1]["status"] == "already_absent"
    assert all(
        result["status"] in {"restored", "removed", "already_absent"}
        for result in results
    )


def test_cleanup_restores_preexisting_policy_and_log_group_state() -> None:
    module = _load_script()
    receipt = {
        "runtime": _receipt()["runtime"],
        "observability": {
            "transaction_search": {
                "cleanup": {
                    "destination_changed": False,
                    "previous_destination": "CloudWatchLogs",
                    "resource_policy_created": False,
                    "previous_resource_policy_document": '{"Version":"2012-10-17"}',
                },
                "resource_policy_document": WORKSHOP_POLICY,
            },
            "trace_log_groups": {
                "groups": [
                    {
                        "name": "aws/spans",
                        "kms_key_arn": WORKSHOP_KMS_KEY,
                        "retention_days": 30,
                        "cleanup": {
                            "created_by_workshop": False,
                            "previous_kms_key_arn": "arn:aws:kms:us-east-1:123:key/old",
                            "previous_retention_days": 14,
                        },
                    }
                ]
            },
            "runtime_log_group": {
                "name": (
                    "/aws/bedrock-agentcore/runtimes/"
                    "pellier_orchestrator-abc123-DEFAULT"
                ),
                "kms_key_arn": WORKSHOP_KMS_KEY,
                "retention_days": 30,
                "cleanup": {
                    "created_by_workshop": False,
                    "previous_kms_key_arn": None,
                    "previous_retention_days": None,
                },
            },
        }
    }

    assert module.cleanup_plan(receipt) == [
        {
            "service": "logs",
            "operation": "restore_resource_policy",
            "policy_name": "TransactionSearchXRayAccess",
            "policy_document": '{"Version":"2012-10-17"}',
            "expected_policy_document": WORKSHOP_POLICY,
        },
        {
            "service": "logs",
            "operation": "restore_log_group_kms",
            "log_group_name": "aws/spans",
            "kms_key_arn": "arn:aws:kms:us-east-1:123:key/old",
            "expected_kms_key_arn": WORKSHOP_KMS_KEY,
        },
        {
            "service": "logs",
            "operation": "restore_log_group_retention",
            "log_group_name": "aws/spans",
            "retention_days": 14,
            "expected_retention_days": 30,
        },
        {
            "service": "logs",
            "operation": "restore_log_group_kms",
            "log_group_name": (
                "/aws/bedrock-agentcore/runtimes/"
                "pellier_orchestrator-abc123-DEFAULT"
            ),
            "kms_key_arn": None,
            "expected_kms_key_arn": WORKSHOP_KMS_KEY,
        },
        {
            "service": "logs",
            "operation": "restore_log_group_retention",
            "log_group_name": (
                "/aws/bedrock-agentcore/runtimes/"
                "pellier_orchestrator-abc123-DEFAULT"
            ),
            "retention_days": None,
            "expected_retention_days": 30,
        },
    ]


def test_execute_cleanup_preserves_externally_changed_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()

    class _NotFound(Exception):
        pass

    class _Logs:
        class exceptions:
            ResourceNotFoundException = _NotFound

        def __init__(self) -> None:
            self.deleted_policies: list[str] = []
            self.deleted_groups: list[str] = []

        def get_paginator(self, operation: str):
            class _Paginator:
                def paginate(self, **kwargs):
                    if operation == "describe_resource_policies":
                        return [
                            {
                                "resourcePolicies": [
                                    {
                                        "policyName": (
                                            "TransactionSearchXRayAccess"
                                        ),
                                        "policyDocument": json.dumps(
                                            {"Version": "2012-10-17", "Statement": []}
                                        ),
                                    }
                                ]
                            }
                        ]
                    return [
                        {
                            "logGroups": [
                                {
                                    "logGroupName": kwargs[
                                        "logGroupNamePrefix"
                                    ],
                                    "kmsKeyId": "arn:aws:kms:us-east-1:123:key/external",
                                    "retentionInDays": 90,
                                }
                            ]
                        }
                    ]

            return _Paginator()

        def delete_resource_policy(self, *, policyName: str) -> None:
            self.deleted_policies.append(policyName)

        def delete_log_group(self, *, logGroupName: str) -> None:
            self.deleted_groups.append(logGroupName)

    class _XRay:
        def get_trace_segment_destination(self) -> dict[str, str]:
            return {"Destination": "XRay"}

    logs = _Logs()
    monkeypatch.setattr(
        module.boto3,
        "client",
        lambda service, **_kwargs: logs if service == "logs" else _XRay(),
    )

    results = module.execute_cleanup(
        region="us-east-1",
        plan=module.cleanup_plan(_receipt()),
    )

    assert logs.deleted_policies == []
    assert logs.deleted_groups == []
    assert all(
        result["status"] == "skipped_external_change"
        for result in results
    )
