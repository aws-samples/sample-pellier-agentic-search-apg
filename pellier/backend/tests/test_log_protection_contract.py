"""Readiness depends on observed log settings, including the operator Runtime."""

import copy
import importlib.util
from pathlib import Path

import pytest


KEY = "arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-1234567890ab"
MRK_KEY = "arn:aws:kms:us-east-1:123456789012:key/mrk-1234abcd12ab34cd56ef1234567890ab"
TRACE_GROUPS = ("aws/spans", "/aws/application-signals/data")


@pytest.fixture
def provisioner():
    path = Path(__file__).resolve().parents[3] / "scripts/provision_agentcore_end_to_end.py"
    spec = importlib.util.spec_from_file_location("log_contract_provisioner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("key,days", [("", 30), (KEY, None), (KEY, 0), (KEY, True)])
def test_full_readiness_rejects_unmanaged_settings(provisioner, key, days):
    with pytest.raises(RuntimeError, match="Managed readiness requires"):
        provisioner._require_release_log_protection(key, days)


def test_requested_settings_alone_are_not_verified(provisioner):
    groups = [{"kms_key_arn": KEY, "retention_days": 30}]
    assert provisioner._log_protection_checks(
        groups, kms_key_arn=KEY, retention_days=30,
    ) == (False, False)


def test_one_unprotected_runtime_prevents_a_group_wide_pass(provisioner):
    groups = [
        {"observed": {"kms_key_arn": KEY, "retention_days": 30}},
        {"observed": {"kms_key_arn": None, "retention_days": 30}},
    ]
    assert provisioner._log_protection_checks(
        groups, kms_key_arn=KEY, retention_days=30,
    ) == (False, True)


def test_actual_matching_configuration_passes(provisioner):
    provisioner._require_release_log_protection(KEY, 30)
    groups = [{"observed": {"kms_key_arn": KEY, "retention_days": 30}}]
    assert provisioner._log_protection_checks(
        groups, kms_key_arn=KEY, retention_days=30,
    ) == (True, True)


def test_inspection_keeps_unmanaged_request_separate_from_observed_state(provisioner):
    class Logs:
        def get_paginator(self, operation):
            assert operation == "describe_log_groups"
            return self

        def paginate(self, **kwargs):
            return [{"logGroups": [{
                "logGroupName": "aws/spans",
                "retentionInDays": 30,
            }]}]

    group = provisioner._ensure_protected_log_group(
        logs=Logs(), log_group_name="aws/spans", kms_key_arn="", retention_days=None,
    )
    assert group["requested"] == {"kms_key_arn": None, "retention_days": None}
    assert group["observed"] == {"kms_key_arn": None, "retention_days": 30}
    assert group["retention_days"] == 30
    assert group["cleanup"]["created_by_workshop"] is False


@pytest.mark.parametrize("key", [KEY, MRK_KEY])
def test_single_and_multi_region_key_arns_are_valid(provisioner, key):
    provisioner._require_release_log_protection(key, 30)


@pytest.mark.parametrize("key", [
    KEY.replace("key/", "alias/"),
    KEY.replace("123456789012", "12345678901"),
    KEY.replace("12345678-1234-1234-1234-1234567890ab", "-" * 36),
    MRK_KEY + "abcd",
    MRK_KEY[:-1],
    MRK_KEY.replace("mrk-", "mrk--"),
    KEY + "\n",
])
def test_malformed_or_alias_key_arns_are_rejected(provisioner, key):
    with pytest.raises(RuntimeError, match="customer-managed KMS key ARN"):
        provisioner._validate_log_kms_key_arn(key)


@pytest.mark.parametrize("key", [KEY, MRK_KEY])
@pytest.mark.parametrize("override", [
    {}, {"KeyState": "Disabled", "Enabled": False},
    {"KeyState": "PendingDeletion"}, {"KeyManager": "AWS"},
    {"KeySpec": "RSA_2048"}, {"KeyUsage": "SIGN_VERIFY"},
    {"AWSAccountId": "999999999999"}, {"Arn": KEY.replace("us-east-1", "us-west-2")},
])
def test_key_preflight_checks_provider_metadata(provisioner, monkeypatch, key, override):
    import boto3
    from botocore.stub import Stubber

    kms = boto3.client("kms", region_name="us-east-1", aws_access_key_id="fixture", aws_secret_access_key="fixture")
    metadata = {
        "KeyId": key.split("/")[-1], "Arn": key, "AWSAccountId": "123456789012",
        "KeyState": "Enabled", "Enabled": True, "KeyManager": "CUSTOMER",
        "KeySpec": "SYMMETRIC_DEFAULT", "KeyUsage": "ENCRYPT_DECRYPT",
    } | override
    monkeypatch.setattr(provisioner.boto3, "client", lambda *_args, **_kwargs: kms)
    with Stubber(kms) as stub:
        stub.add_response("describe_key", {"KeyMetadata": metadata}, {"KeyId": key})
        if override:
            with pytest.raises(RuntimeError, match="enabled customer-managed symmetric"):
                provisioner._verify_log_kms_key(key, region="us-east-1", account_id="123456789012", partition="aws")
        else:
            provisioner._verify_log_kms_key(key, region="us-east-1", account_id="123456789012", partition="aws")
        stub.assert_no_pending_responses()


@pytest.mark.parametrize("kwargs", [
    {"region": "us-west-2", "account_id": "123456789012", "partition": "aws"},
    {"region": "us-east-1", "account_id": "999999999999", "partition": "aws"},
    {"region": "us-east-1", "account_id": "123456789012", "partition": "aws-cn"},
])
def test_wrong_key_location_is_rejected_before_provider_access(provisioner, monkeypatch, kwargs):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("wrong-location key must not reach a provider")
    monkeypatch.setattr(provisioner.boto3, "client", unexpected)
    with pytest.raises(RuntimeError, match="deployment account and region"):
        provisioner._verify_log_kms_key(KEY, **kwargs)


def test_key_verification_precedes_first_provisioning_mutation(provisioner):
    import inspect

    source = inspect.getsource(provisioner.main)
    assert source.index("_verify_log_kms_key(") < source.index("_ensure_data_api_enabled(")
    assert source.index("_verify_log_kms_key(") < source.index("_deploy_lambdas(")


class SharedLogs:
    class exceptions:
        class ResourceAlreadyExistsException(Exception):
            pass

    def __init__(self, groups, *, raced_group=None):
        self.groups = copy.deepcopy(groups)
        self.raced_group = raced_group
        self.events = []

    def get_paginator(self, operation):
        assert operation == "describe_log_groups"
        return self

    def paginate(self, *, logGroupNamePrefix):
        self.events.append(("read", logGroupNamePrefix))
        group = self.groups.get(logGroupNamePrefix)
        return [{"logGroups": [copy.deepcopy(group)] if group else []}]

    def create_log_group(self, *, logGroupName, kmsKeyId):
        self.events.append(("create", logGroupName))
        if self.raced_group:
            self.groups[logGroupName] = copy.deepcopy(self.raced_group)
            raise self.exceptions.ResourceAlreadyExistsException()
        self.groups[logGroupName] = {
            "logGroupName": logGroupName,
            "kmsKeyId": kmsKeyId,
        }

    def associate_kms_key(self, *, logGroupName, kmsKeyId):
        self.events.append(("associate", logGroupName))
        self.groups[logGroupName]["kmsKeyId"] = kmsKeyId

    def put_retention_policy(self, *, logGroupName, retentionInDays):
        self.events.append(("retention", logGroupName))
        self.groups[logGroupName]["retentionInDays"] = retentionInDays


def shared_group(name, *, key=KEY, days=30):
    return {"logGroupName": name, "kmsKeyId": key, "retentionInDays": days}


@pytest.mark.parametrize("first", [None, {"key": KEY}, {"key": None}])
@pytest.mark.parametrize("second", [{"key": None}, {"days": 7}])
def test_both_shared_groups_are_preflighted_before_any_mutation(
    provisioner, monkeypatch, first, second,
):
    groups = {TRACE_GROUPS[1]: shared_group(TRACE_GROUPS[1], **second)}
    if first is not None:
        groups[TRACE_GROUPS[0]] = shared_group(TRACE_GROUPS[0], **first)
    logs = SharedLogs(groups)
    monkeypatch.setattr(provisioner.boto3, "client", lambda *_args, **_kwargs: logs)

    with pytest.raises(RuntimeError, match="AGENTCORE_ALLOW_SHARED_TRACE_LOG_CHANGES=true"):
        provisioner._ensure_trace_log_groups(
            region="us-east-1", kms_key_arn=KEY, retention_days=30,
        )

    assert logs.events == [("read", name) for name in TRACE_GROUPS]
    assert logs.groups == groups


def test_matching_shared_groups_need_no_change_authorization(provisioner, monkeypatch):
    logs = SharedLogs({name: shared_group(name) for name in TRACE_GROUPS})
    monkeypatch.setattr(provisioner.boto3, "client", lambda *_args, **_kwargs: logs)

    receipt = provisioner._ensure_trace_log_groups(
        region="us-east-1", kms_key_arn=KEY, retention_days=30,
    )

    assert all(event[0] == "read" for event in logs.events)
    assert all(group["cleanup"]["created_by_workshop"] is False for group in receipt["groups"])
    assert provisioner._log_protection_checks(
        receipt["groups"], kms_key_arn=KEY, retention_days=30,
    ) == (True, True)


def test_authorized_shared_changes_preserve_previous_settings(provisioner, monkeypatch):
    logs = SharedLogs({name: shared_group(name, key=None, days=7) for name in TRACE_GROUPS})
    monkeypatch.setattr(provisioner.boto3, "client", lambda *_args, **_kwargs: logs)

    receipt = provisioner._ensure_trace_log_groups(
        region="us-east-1", kms_key_arn=KEY, retention_days=30,
        allow_existing_changes=True,
    )

    assert logs.events[:2] == [("read", name) for name in TRACE_GROUPS]
    assert logs.groups == {name: shared_group(name) for name in TRACE_GROUPS}
    assert all(group["cleanup"] == {
        "created_by_workshop": False,
        "creation_pending": False,
        "previous_kms_key_arn": None,
        "previous_retention_days": 7,
    } for group in receipt["groups"])


def test_shared_group_create_race_cannot_authorize_rekeying(provisioner):
    name = TRACE_GROUPS[0]
    existing = shared_group(name, key=None, days=7)
    logs = SharedLogs({}, raced_group=existing)
    checkpoints = []

    with pytest.raises(RuntimeError, match="Existing shared trace log groups"):
        provisioner._ensure_protected_log_group(
            logs=logs, log_group_name=name, kms_key_arn=KEY, retention_days=30,
            allow_existing_changes=False, on_cleanup_state=checkpoints.append,
        )

    assert logs.groups[name] == existing
    assert not any(event[0] in {"associate", "retention"} for event in logs.events)
    assert checkpoints[-1]["cleanup"] == {
        "created_by_workshop": False,
        "creation_pending": False,
        "previous_kms_key_arn": None,
        "previous_retention_days": 7,
    }
