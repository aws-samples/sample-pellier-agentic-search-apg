"""The claim probe requires a successful owner read and a policy denial for other customers."""
import json
import sys
from pathlib import Path

import pytest
from mcp.types import CallToolResult, TextContent

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import prove_customer_claim as probe
import gateway_policy_probe

CUSTOMER = "CUST-THEO"
ORDERS = {"status": "success", "customer_id": CUSTOMER, "orders": [], "count": 0}


def result(payload, *, error=False):
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload))], isError=error)


@pytest.mark.parametrize("answer,passes", [
    (TimeoutError(), False),
    (RuntimeError("401 Unauthorized"), False),
    (result({"status": "error"}, error=True), False),
    (result({"status": "error"}), False),
    (CallToolResult(content=[]), False),
    (result(dict(ORDERS, customer_id="CUST-OTHER")), False),
    (result(ORDERS), True),
    (result({"content": [{"type": "text", "text": json.dumps(ORDERS)}]}), True),
])
def test_owner_must_read_orders_while_other_requests_must_be_denied(monkeypatch, answer, passes):
    async def catalog(*args):
        return ["store___get_orders"]

    async def call(_url, token, _tool, args):
        if token != "owner" or args["customer_id"] != CUSTOMER:
            raise RuntimeError("Tool call not allowed due to policy enforcement [Policy evaluation denied]")
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(probe, "_gateway_catalog", catalog)
    monkeypatch.setattr(gateway_policy_probe, "_call_tool", call)
    checks = probe.gateway_probes("local", {"theo": "owner"}, {"theo": CUSTOMER}, "unmapped")
    assert [(item["case"], item["passed"]) for item in checks] == [
        ("owner", passes), ("mismatched", True), ("unmapped", True)]


def test_gateway_proof_without_a_mapped_owner_fails():
    checks = probe.gateway_probes("local", {}, {}, "")
    assert checks and not checks[0].get("passed")
