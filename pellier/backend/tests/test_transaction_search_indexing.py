"""Managed trace indexing is verified and cleanup preserves account ownership."""

import copy
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import boto3
from botocore.exceptions import ClientError
from botocore.stub import Stubber
import pytest


ROOT = Path(__file__).resolve().parents[3]
UPDATED = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rule(percentage, modified=UPDATED):
    return {
        "Name": "Default", "ModifiedAt": modified,
        "Rule": {"Probabilistic": {"DesiredSamplingPercentage": percentage}},
    }


@pytest.fixture
def clients(monkeypatch):
    provisioner = load_script("provision_agentcore_end_to_end")
    cleanup = load_script("teardown_agentcore_observability")
    xray = boto3.client("xray", region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing")
    logs = Mock()
    logs.describe_resource_policies.return_value = {"resourcePolicies": []}
    monkeypatch.setattr(provisioner.boto3, "client", lambda service, **kwargs: {"logs": logs, "xray": xray}[service])
    with Stubber(xray) as stub:
        yield provisioner, cleanup, logs, stub
        stub.assert_no_pending_responses()


def preflight(stub, percentage):
    stub.add_response("get_trace_segment_destination", {"Destination": "CloudWatchLogs", "Status": "ACTIVE"}, {})
    stub.add_response("get_indexing_rules", {"IndexingRules": [rule(percentage)]}, {})
    stub.add_response("get_trace_segment_destination", {"Destination": "CloudWatchLogs", "Status": "ACTIVE"}, {})


def configure(provisioner, checkpoints):
    return provisioner._configure_transaction_search(
        region="us-east-1", account_id="123456789012", partition="aws",
        on_cleanup_state=lambda receipt: checkpoints.append(copy.deepcopy(receipt)),
    )


def indexing_plan(cleanup, receipt):
    plan = cleanup.cleanup_plan({"observability": {"transaction_search": receipt}})
    return [step for step in plan if step["operation"] == "restore_indexing_rule"]


@pytest.mark.parametrize("previous", [0, 1, 10, 100])
def test_configures_and_restores_observed_default_without_writing_a_prior_100(clients, previous):
    provisioner, cleanup, logs, stub = clients
    preflight(stub, previous)
    requested = {"Name": "Default", "Rule": {"Probabilistic": {"DesiredSamplingPercentage": 100}}}
    if previous != 100:
        stub.add_response("update_indexing_rule", {"IndexingRule": rule(100)}, requested)
    stub.add_response("get_indexing_rules", {"IndexingRules": [rule(100)]}, {})
    checkpoints = []
    receipt = configure(provisioner, checkpoints)

    assert receipt["status"] == "ACTIVE"
    assert receipt["indexing_rule"]["desired_sampling_percentage"] == 100
    assert receipt["cleanup"]["previous_indexing_rule"]["desired_sampling_percentage"] == previous
    assert receipt["cleanup"]["indexing_rule_update_started"] is (previous != 100)
    assert checkpoints[0]["cleanup"]["indexing_rule_update_started"] is False
    plan = indexing_plan(cleanup, receipt)
    if previous == 100:
        assert plan == []
    else:
        assert any(item["cleanup"]["indexing_rule_update_started"] for item in checkpoints)
        stub.add_response("get_indexing_rules", {"IndexingRules": [rule(100)]}, {})
        stub.add_response("update_indexing_rule", {"IndexingRule": rule(previous)}, {
            "Name": "Default", "Rule": {"Probabilistic": {"DesiredSamplingPercentage": previous}},
        })
        assert cleanup.execute_cleanup(region="us-east-1", plan=plan)[0]["status"] == "restored"
    logs.put_resource_policy.assert_called_once()


@pytest.mark.parametrize("current", [rule(25), rule(100, datetime(2026, 9, 21, tzinfo=timezone.utc))])
def test_cleanup_skips_external_sampling_or_same_value_rewrite(clients, current):
    provisioner, cleanup, _logs, stub = clients
    preflight(stub, 1)
    stub.add_response("update_indexing_rule", {"IndexingRule": rule(100)}, {
        "Name": "Default", "Rule": {"Probabilistic": {"DesiredSamplingPercentage": 100}},
    })
    stub.add_response("get_indexing_rules", {"IndexingRules": [rule(100)]}, {})
    receipt = configure(provisioner, [])
    stub.add_response("get_indexing_rules", {"IndexingRules": [current]}, {})
    result = cleanup.execute_cleanup(region="us-east-1", plan=indexing_plan(cleanup, receipt))
    assert result[0]["status"] == "skipped_external_change"


def test_update_response_loss_preserves_restoration_checkpoint(clients):
    provisioner, cleanup, _logs, stub = clients
    preflight(stub, 1)
    stub.add_client_error("update_indexing_rule", service_error_code="ThrottledException", expected_params={
        "Name": "Default", "Rule": {"Probabilistic": {"DesiredSamplingPercentage": 100}},
    })
    checkpoints = []
    with pytest.raises(ClientError):
        configure(provisioner, checkpoints)
    plan = indexing_plan(cleanup, checkpoints[-1])
    assert plan[0]["desired_sampling_percentage"] == 1
    assert plan[0]["expected_modified_at"] is None


def test_unverified_sampling_cannot_return_ready(clients):
    provisioner, _cleanup, _logs, stub = clients
    preflight(stub, 1)
    stub.add_response("update_indexing_rule", {"IndexingRule": rule(100)}, {
        "Name": "Default", "Rule": {"Probabilistic": {"DesiredSamplingPercentage": 100}},
    })
    stub.add_response("get_indexing_rules", {"IndexingRules": [rule(1)]}, {})
    with pytest.raises(RuntimeError, match="did not retain 100 percent"):
        configure(provisioner, [])


def test_missing_default_fails_before_account_observability_mutation(monkeypatch):
    provisioner = load_script("provision_agentcore_end_to_end")
    logs, xray = Mock(), Mock()
    logs.describe_resource_policies.return_value = {"resourcePolicies": []}
    xray.get_trace_segment_destination.return_value = {"Destination": "XRay", "Status": "ACTIVE"}
    xray.get_indexing_rules.return_value = {"IndexingRules": []}
    monkeypatch.setattr(provisioner.boto3, "client", lambda service, **kwargs: {"logs": logs, "xray": xray}[service])
    with pytest.raises(RuntimeError, match="did not return the Default indexing rule"):
        configure(provisioner, [])
    logs.put_resource_policy.assert_not_called()
    xray.update_trace_segment_destination.assert_not_called()
    xray.update_indexing_rule.assert_not_called()


def test_default_indexing_rule_paginates(clients):
    provisioner, _cleanup, _logs, stub = clients
    stub.add_response("get_indexing_rules", {"IndexingRules": [{**rule(25), "Name": "Other"}], "NextToken": "next"}, {})
    stub.add_response("get_indexing_rules", {"IndexingRules": [rule(1)]}, {"NextToken": "next"})
    xray = provisioner.boto3.client("xray")
    assert provisioner._default_indexing_rule(xray)["desired_sampling_percentage"] == 1
