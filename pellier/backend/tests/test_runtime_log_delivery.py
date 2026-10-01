"""Precreated encrypted Runtime groups must receive real ADOT telemetry."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest


ARN = "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/pellier_orchestrator-abc123"
GROUP = "/aws/bedrock-agentcore/runtimes/pellier_orchestrator-abc123-DEFAULT"
GROUP_ARN = "arn:aws:logs:us-east-1:123456789012:log-group:" + GROUP


@pytest.fixture
def delivery():
    path = Path(__file__).resolve().parents[3] / "scripts/deploy/runtime_log_delivery.py"
    spec = importlib.util.spec_from_file_location("runtime_delivery_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Logs:
    class exceptions:
        class ResourceAlreadyExistsException(Exception):
            pass

    def __init__(self, policy=None):
        self.policy = policy
        self.streams = set()
        self.events = []
        self.writes = []

    def get_paginator(self, operation):
        assert operation == "describe_resource_policies"
        return self

    def paginate(self, **request):
        assert request == {"resourceArn": GROUP_ARN, "policyScope": "RESOURCE"}
        return [{"resourcePolicies": [self.policy] if self.policy else []}]

    def create_log_stream(self, **request):
        assert request["logGroupName"] == GROUP
        name = request["logStreamName"]
        self.events.append("stream:" + name)
        if name in self.streams:
            raise self.exceptions.ResourceAlreadyExistsException()
        self.streams.add(name)

    def put_resource_policy(self, **request):
        self.events.append("policy")
        self.writes.append(copy.deepcopy(request))
        self.policy = {
            "policyName": self.policy["policyName"] if self.policy else "resourceArn=" + GROUP_ARN,
            "policyDocument": request["policyDocument"],
            "revisionId": "revision-2",
        }
        return {"revisionId": "revision-2", "resourcePolicy": self.policy}


def test_fresh_group_initializes_both_streams_and_scoped_xray_delivery(delivery):
    logs = Logs()
    checkpoints = []

    def checkpoint(receipt):
        checkpoints.append(copy.deepcopy(receipt))
        logs.events.append("checkpoint")

    proof = delivery.ensure_runtime_log_delivery(logs, ARN, on_checkpoint=checkpoint)

    assert logs.streams == {"runtime-logs", "spans"}
    assert logs.events == ["checkpoint", "stream:runtime-logs", "stream:spans", "policy", "checkpoint"]
    request = logs.writes[0]
    assert request["resourceArn"] == GROUP_ARN
    assert "policyName" not in request
    assert "expectedRevisionId" not in request
    statement = json.loads(request["policyDocument"])["Statement"][0]
    assert statement["Resource"] == GROUP_ARN + ":log-stream:spans"
    assert statement["Principal"] == {"Service": "xray.amazonaws.com"}
    assert statement["Action"] == "logs:PutLogEvents"
    assert statement["Condition"]["StringEquals"] == {"aws:SourceAccount": "123456789012"}
    assert checkpoints[0]["cleanup"]["policy_created"] is True
    assert proof["revision_id"] == "revision-2"


def test_repeated_setup_preserves_an_existing_delivery_policy(delivery):
    logs = Logs()
    delivery.ensure_runtime_log_delivery(logs, ARN)
    proof = delivery.ensure_runtime_log_delivery(logs, ARN)
    assert len(logs.writes) == 1
    assert proof["cleanup"]["policy_changed"] is False
    assert proof["cleanup"]["policy_created"] is False


def test_existing_service_policy_is_preserved_and_update_uses_its_revision(delivery):
    existing = {"Sid": "OtherService", "Effect": "Allow", "Principal": {"Service": "delivery.logs.amazonaws.com"}}
    original = json.dumps({"Version": "2012-10-17", "Statement": [existing]})
    logs = Logs({"policyName": "ExistingPolicy", "policyDocument": original, "revisionId": "revision-1"})
    proof = delivery.ensure_runtime_log_delivery(logs, ARN)
    request = logs.writes[0]
    assert "policyName" not in request
    assert request["expectedRevisionId"] == "revision-1"
    assert json.loads(request["policyDocument"])["Statement"][0] == existing
    assert proof["cleanup"]["previous_policy_document"] == original
    assert proof["cleanup"]["policy_created"] is False


def test_changed_workshop_statement_is_not_overwritten(delivery):
    logs = Logs()
    delivery.ensure_runtime_log_delivery(logs, ARN)
    document = json.loads(logs.policy["policyDocument"])
    document["Statement"][0]["Resource"] = "external-change"
    logs.policy["policyDocument"] = json.dumps(document)
    with pytest.raises(RuntimeError, match="changed externally"):
        delivery.ensure_runtime_log_delivery(logs, ARN)
    assert len(logs.writes) == 1


@pytest.mark.parametrize("arn", [ARN + "\n", ARN.replace("runtime/", "memory/"), "fixture"])
def test_invalid_resource_is_rejected_before_any_api_call(delivery, arn):
    with pytest.raises(ValueError, match="Runtime ARN"):
        delivery.ensure_runtime_log_delivery(None, arn)
