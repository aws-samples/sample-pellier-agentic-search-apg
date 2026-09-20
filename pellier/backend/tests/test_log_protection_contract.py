"""Readiness depends on observed log settings, including the operator Runtime."""

import importlib.util
from pathlib import Path

import pytest


KEY = "arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-1234567890ab"


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
