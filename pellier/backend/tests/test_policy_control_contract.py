"""Policy observations must consume the SDK response used by the live service."""
from types import SimpleNamespace

import botocore.session
import pytest

from services import managed_policy, operator_capabilities


@pytest.mark.parametrize("member", ["policy", "cedar"])
def test_definition_reader_supports_live_and_archived_shapes(member):
    statement = 'forbid(principal, action, resource);'
    assert managed_policy.policy_statement({
        "definition": {member: {"statement": statement}}
    }) == statement


def test_current_sdk_uses_policy_for_both_read_and_write():
    service = botocore.session.get_session().get_service_model("bedrock-agentcore-control")
    for operation, direction in (("GetPolicy", "output_shape"), ("UpdatePolicy", "input_shape")):
        shape = getattr(service.operation_model(operation), direction)
        assert "policy" in shape.members["definition"].members


def test_operator_reads_paged_policy_details_instead_of_list_summaries(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "AGENTCORE_GATEWAY_ARN", "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/test")
    monkeypatch.setattr(settings, "AGENTCORE_POLICY_ENGINE_ID", "test-engine")
    read = []

    def policies(**kwargs):
        if kwargs.get("nextToken"):
            return {"policies": [{"policyId": "permit"}]}
        return {"policies": [{"policyId": "monitor"}], "nextToken": "second"}

    def detail(**kwargs):
        read.append(kwargs["policyId"])
        return {
            "enforcementMode": "ACTIVE" if kwargs["policyId"] == "permit" else "LOG_ONLY",
            "definition": {"policy": {
                "statement": 'permit(principal, action == AgentCore::Action::"returns___initiate_return", resource);'
            }},
        }

    client = SimpleNamespace(
        list_gateway_targets=lambda **_: {"items": [{"targetId": "returns"}]},
        get_gateway_target=lambda **_: {
            "name": "returns", "targetConfiguration": {"mcp": {"lambda": {
                "toolSchema": {"inlinePayload": [{"name": "initiate_return"}]}
            }}},
        },
        list_policies=policies,
        get_policy=detail,
    )
    monkeypatch.setattr(managed_policy, "_control_client", lambda: client)
    published, permitted = operator_capabilities._live_gateway_facts()
    assert read == ["monitor", "permit"]
    assert published == ["initiate_return"]
    assert permitted == {"initiate_return": 1}
    client.get_policy = lambda **_: {"enforcementMode": "ACTIVE"}
    with pytest.raises(RuntimeError, match="definition unavailable"):
        operator_capabilities._live_gateway_facts()


def test_repeated_page_token_cannot_silently_truncate_policy_observation():
    client = SimpleNamespace(list_policies=lambda **_: {
        "policies": [{"policyId": "one"}], "nextToken": "repeated"
    })
    with pytest.raises(managed_policy.ControlPlaneUnavailable, match="pagination"):
        list(managed_policy.policy_summaries(client, "test-engine"))
