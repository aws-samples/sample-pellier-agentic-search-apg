"""The staff graph cannot change its actor, case or permitted tool set."""
import json

import pytest

from services.operator_gateway import BoundOperatorTools
from services.runtime_identity import RuntimeIdentity


class Client:
    def __init__(self):
        self.calls = []
        self.result = {"status": "success", "customer_id": "CUST-JESSICA"}

    def call_tool_sync(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": "success", "content": [{"text": json.dumps(self.result)}]}


def bound(client):
    return BoundOperatorTools(client, RuntimeIdentity("staff-sub", "CUST-JESSICA"),
                              "turn-staff-test", "a" * 64)


def test_tool_context_overwrites_model_supplied_identity():
    client = Client()
    bound(client)("get_orders", {"customer_id": "CUST-THEO", "operator_sub": "forged",
                                  "turn_id": "wrong", "build_fingerprint": "wrong", "limit": 2})
    assert client.calls[0]["name"] == "pellier-operator-tools___operator_get_orders"
    assert client.calls[0]["arguments"] == {
        "customer_id": "CUST-JESSICA", "operator_sub": "staff-sub", "turn_id": "turn-staff-test",
        "build_fingerprint": "a" * 64, "limit": 2,
    }


@pytest.mark.parametrize("tool", ["give_store_credit", "approve", "search_products", "execute_sql"])
def test_ungranted_tool_never_reaches_gateway(tool):
    client = Client()
    with pytest.raises(ValueError, match="operator_tool_not_granted"):
        bound(client)(tool, {})
    assert client.calls == []


def test_wrong_customer_result_is_rejected():
    client = Client()
    client.result["customer_id"] = "CUST-THEO"
    with pytest.raises(ValueError, match="operator_case_mismatch"):
        bound(client)("get_orders", {})


def test_gateway_error_is_not_an_empty_case():
    class Denied(Client):
        def call_tool_sync(self, **kwargs):
            return {"status": "error", "content": [{"text": "denied"}]}
    with pytest.raises(RuntimeError, match="operator_gateway_rejected"):
        bound(Denied())("get_orders", {})


def test_cedar_staff_scope_and_actor_binding_for_every_operator_tool():
    import sys
    from pathlib import Path
    scripts = Path(__file__).resolve().parents[3] / "scripts"
    sys.path.insert(0, str(scripts))
    import lab4_policy as policy
    from gateway_tool_schemas import OPERATOR_SCHEMA

    schema, policies = policy.gateway_cedar_schema(), policy.baseline_set()
    assert policy.validation_errors(policies, schema) == []
    for tool in OPERATOR_SCHEMA["tools"]:
        action = f"pellier-operator-tools___{tool['name']}"
        inputs = {"customer_id": "CUST-JESSICA", "operator_sub": policy.NADIA.principal_id,
                  "turn_id": "turn-policy-test", "build_fingerprint": "a" * 64,
                  "limit": 5, "order_ids": [20, 21], "reason": "Received return", "review_id": 0}
        fields = tool["inputSchema"]["properties"]
        inputs = {key: value for key, value in inputs.items() if key in fields}
        assert policy.decide(policies, schema, policy.NADIA, action, inputs).decision == policy.ALLOW
        assert policy.decide(policies, schema, policy.SHOPPER, action, inputs).decision == policy.DENY
        assert policy.decide(policies, schema, policy.OTHER_STAFF, action, inputs).decision == policy.DENY
