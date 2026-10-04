"""Policy observations must consume the SDK response used by the live service."""
from types import SimpleNamespace

import botocore.session
import pytest

from services import managed_policy


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


def test_repeated_page_token_cannot_silently_truncate_policy_observation():
    client = SimpleNamespace(list_policies=lambda **_: {
        "policies": [{"policyId": "one"}], "nextToken": "repeated"
    })
    with pytest.raises(managed_policy.ControlPlaneUnavailable, match="pagination"):
        list(managed_policy.policy_summaries(client, "test-engine"))
