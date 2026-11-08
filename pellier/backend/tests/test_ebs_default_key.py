"""The editor instance launches only after the account's aws/ebs key exists and is Enabled.

An account that has never encrypted an EBS volume has no aws/ebs key. AWS creates it when the
first encrypted volume asks for it, and an instance launched in that moment is terminated with
Client.InvalidKMSKey.InvalidState (a brand-new event account, 2026-11-08). A recycled event
account already holds the key, so no test event can reproduce the race: these tests hold the
template's order and run the custom resource's own code against a fake KMS.
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from tests.test_userdata_size import TEMPLATE, _CloudFormation


def _resources() -> dict:
    return yaml.load(TEMPLATE.read_text(encoding="utf-8"), Loader=_CloudFormation)["Resources"]


def test_the_encrypted_root_volume_waits_for_the_key() -> None:
    resources = _resources()
    instance = resources["CodeEditorInstance"]
    (root,) = instance["Properties"]["BlockDeviceMappings"]
    assert root["Ebs"]["Encrypted"] is True and "KmsKeyId" not in root["Ebs"]
    depends = instance.get("DependsOn")
    assert "EbsDefaultKey" in ([depends] if isinstance(depends, str) else depends)
    key = resources["EbsDefaultKey"]
    assert key["Type"] == "Custom::EbsDefaultKey"
    assert key["Properties"]["ServiceToken"] == "EbsDefaultKeyFunction.Arn"


def test_the_function_always_answers_before_its_timeout() -> None:
    function = _resources()["EbsDefaultKeyFunction"]["Properties"]
    module = _load_function({})
    assert function["Timeout"] > module.POLL_SECONDS + module.SETTLE_SECONDS + 10
    assert function["Runtime"] == "python3.13"


class _ClientError(Exception):
    """botocore's ClientError as the code reads it: an error code under ``response``."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class _Kms:
    """KMS answering each describe_key with the next state; the last one repeats.

    A state named after an error code (NotFoundException, AccessDeniedException) raises it.
    """

    def __init__(self, states: list[str], created: datetime) -> None:
        self.states, self.created, self.calls = list(states), created, []

    def describe_key(self, KeyId: str) -> dict:  # noqa: N803 - boto3's name
        self.calls.append(KeyId)
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        if state.endswith("Exception"):
            raise _ClientError(state)
        return {"KeyMetadata": {"KeyId": "k-1", "Arn": "arn:aws:kms:us-east-1:123456789012:key/k-1",
                                "KeyState": state, "CreationDate": self.created}}


def _load_function(sent: dict, kms: _Kms | None = None, sleeps: list | None = None):
    """The inline ZipFile code as Lambda runs it, with boto3 and cfnresponse stood in."""
    code = _resources()["EbsDefaultKeyFunction"]["Properties"]["Code"]["ZipFile"]
    cfnresponse = types.SimpleNamespace(
        SUCCESS="SUCCESS", FAILED="FAILED",
        send=lambda event, context, status, data, **kwargs: sent.update(
            status=status, data=data, **kwargs))
    boto3 = types.SimpleNamespace(client=lambda name: kms)
    module = types.ModuleType("ebs_default_key")
    saved = {name: sys.modules.get(name) for name in ("boto3", "cfnresponse")}
    sys.modules.update(boto3=boto3, cfnresponse=cfnresponse)
    try:
        exec(compile(code, "index.py", "exec"), module.__dict__)  # noqa: S102 - the template's code
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
    if sleeps is not None:
        module.time = types.SimpleNamespace(sleep=sleeps.append, time=lambda: _NOW.timestamp(),
                                            monotonic=lambda: len(sleeps) * 3.0)
    return module


_NOW = datetime(2026, 11, 8, 19, 43, 40, tzinfo=timezone.utc)
CREATE = {"RequestType": "Create", "ResourceProperties": {}}


def test_a_key_kms_creates_now_is_waited_for_until_enabled_and_settled() -> None:
    sent, sleeps = {}, []
    kms = _Kms(["Creating", "Creating", "Enabled"], created=_NOW - timedelta(seconds=4))
    _load_function(sent, kms, sleeps).lambda_handler(CREATE, None)
    assert kms.calls == ["alias/aws/ebs"] * 3
    assert sent["status"] == "SUCCESS" and sent["data"] == {
        "KeyArn": "arn:aws:kms:us-east-1:123456789012:key/k-1"}
    assert sleeps == [3, 3, pytest.approx(26)]


def test_a_key_the_account_already_holds_launches_without_waiting() -> None:
    sent, sleeps = {}, []
    kms = _Kms(["Enabled"], created=_NOW - timedelta(days=400))
    _load_function(sent, kms, sleeps).lambda_handler(CREATE, None)
    assert sent["status"] == "SUCCESS" and sleeps == []


def test_a_key_that_never_enables_fails_the_stack_with_its_state() -> None:
    sent, sleeps = {}, []
    kms = _Kms(["Disabled"], created=_NOW - timedelta(seconds=1))
    _load_function(sent, kms, sleeps).lambda_handler(CREATE, None)
    assert sent["status"] == "FAILED" and "alias/aws/ebs is Disabled" in sent["reason"]


def test_delete_touches_no_key() -> None:
    sent = {}
    kms = _Kms(["Enabled"], created=_NOW)
    _load_function(sent, kms, []).lambda_handler(
        {"RequestType": "Delete", "PhysicalResourceId": "pellier-ebs-default-key"}, None)
    assert sent["status"] == "SUCCESS" and kms.calls == []
    assert sent["physicalResourceId"] == "pellier-ebs-default-key"



def test_an_alias_that_resolves_late_is_waited_for() -> None:
    sent, sleeps = {}, []
    kms = _Kms(["NotFoundException", "Enabled"], created=_NOW - timedelta(seconds=40))
    _load_function(sent, kms, sleeps).lambda_handler(CREATE, None)
    assert sent["status"] == "SUCCESS" and sleeps == [3]


def test_an_alias_that_never_resolves_leaves_the_key_to_ec2_as_before() -> None:
    """Failing here would fail every brand-new account, where the race fails only some."""
    sent, sleeps = {}, []
    kms = _Kms(["NotFoundException"], created=_NOW)
    module = _load_function(sent, kms, sleeps)
    module.lambda_handler(CREATE, None)
    assert sent["status"] == "SUCCESS" and sent["data"] == {"KeyArn": ""}
    assert len(sleeps) * 3 > module.POLL_SECONDS


def test_a_refused_describe_fails_the_stack_with_the_reason() -> None:
    sent = {}
    kms = _Kms(["AccessDeniedException"], created=_NOW)
    _load_function(sent, kms, []).lambda_handler(CREATE, None)
    assert sent["status"] == "FAILED" and "AccessDeniedException" in sent["reason"]


def test_a_key_dated_ahead_of_the_lambdas_clock_waits_no_longer_than_the_settle() -> None:
    sent, sleeps = {}, []
    kms = _Kms(["Enabled"], created=_NOW + timedelta(minutes=5))
    module = _load_function(sent, kms, sleeps)
    module.lambda_handler(CREATE, None)
    assert sent["status"] == "SUCCESS" and sleeps == [module.SETTLE_SECONDS]
