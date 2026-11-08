"""Staff Runtime identity stays distinct from a shopper's own-customer identity."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from services import runtime_identity as identity

DEPLOY_DIR = Path(__file__).resolve().parents[3] / "scripts" / "deploy"
if str(DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(DEPLOY_DIR))
from tests.test_cognito_auth import _Signer, _valid_access_claims, ISSUER, CLIENT_ID


@pytest.fixture
def staff_identity(monkeypatch):
    signer = _Signer()
    verifier = identity.RuntimeIdentityVerifier(ISSUER, CLIENT_ID)
    monkeypatch.setattr(verifier.jwks, "fetch_data", lambda: {"keys": [signer.public_jwk()]})
    monkeypatch.setattr(identity, "_verifier", lambda: verifier)
    claims = {**_valid_access_claims(), "custom:staff_scope": "returns"}
    claims.pop("custom:customer_id", None)
    return signer, claims


def test_verified_staff_can_investigate_a_selected_customer(staff_identity):
    signer, claims = staff_identity
    resolved = identity.verified_operator_identity(
        signer.sign(claims), {"customer_id": "CUST-JESSICA", "operator_sub": claims["sub"]},
    )
    assert resolved.subject == claims["sub"]
    assert resolved.customer_id == "CUST-JESSICA"


@pytest.mark.parametrize("changes", [
    {"custom:staff_scope": None, "custom:customer_id": "CUST-THEO"},
    {"custom:staff_scope": "catalog"},
    {"custom:staff_scope": ["returns"]},
    {"token_use": "id"},
    {"client_id": "another-client"},
    {"exp": 1},
])
def test_shoppers_and_unverified_staff_cannot_investigate(staff_identity, changes):
    signer, claims = staff_identity
    with pytest.raises(identity.RuntimeIdentityError):
        identity.verified_operator_identity(
            signer.sign({**claims, **changes}), {"customer_id": "CUST-JESSICA"},
        )


@pytest.mark.parametrize("payload", [
    {"customer_id": "CUST-JESSICA", "operator_sub": "another-staff-member"},
    {"customer_id": "CUST-JESSICA", "user_id": "another-staff-member"},
    {"customer_id": ""}, {"customer_id": ["CUST-JESSICA"]}, {},
])
def test_staff_payload_cannot_forge_the_audit_actor_or_an_invalid_case(staff_identity, payload):
    signer, claims = staff_identity
    with pytest.raises(identity.RuntimeIdentityError):
        identity.verified_operator_identity(signer.sign(claims), payload)


def test_a_forged_staff_signature_is_rejected(staff_identity):
    _, claims = staff_identity
    with pytest.raises(identity.RuntimeIdentityError):
        identity.verified_operator_identity(_Signer().sign(claims), {"customer_id": "CUST-JESSICA"})


@pytest.mark.asyncio
async def test_runtime_rejects_missing_identity_before_opening_any_tools(monkeypatch):
    import operator_runtime as runtime
    monkeypatch.setattr(runtime, "operator_tools", lambda **_kw: pytest.fail("tool opened before identity verification"))
    events = [event async for event in runtime.invoke({"customer_id": "CUST-JESSICA"})]
    assert events == [{"event": "error", "data": {"detail": "authentication_required"}}]


@pytest.mark.asyncio
async def test_runtime_streams_graph_with_verified_staff_and_no_local_database(staff_identity, monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    import operator_runtime as runtime
    from services.operator_graph import InvestigationResult

    signer, claims = staff_identity
    monkeypatch.setenv("PELLIER_BUILD_FINGERPRINT", "b" * 64)
    seen = {}

    @contextmanager
    def tools(**kwargs):
        seen.update(kwargs)
        yield lambda name, args: {"customer_id": "CUST-JESSICA", "name": "Jessica"}

    def graph(**kwargs):
        assert kwargs["operator_sub"] == claims["sub"]
        assert kwargs["customer_id"] == "CUST-JESSICA"
        with pytest.raises(RuntimeError, match="no_database"):
            kwargs["run"]("SELECT 1")
        kwargs["emit"]({"type": "step", "id": "investigator", "status": "done"})
        return InvestigationResult(turn_id=kwargs["turn_id"], customer_id=kwargs["customer_id"],
                                   status="complete", execution="gateway-mcp")

    monkeypatch.setattr(runtime, "operator_tools", tools)
    monkeypatch.setattr(runtime, "run_investigation", graph)
    context = SimpleNamespace(request_headers={"Authorization": "Bearer " + signer.sign(claims)})
    events = [event async for event in runtime.invoke({"customer_id": "CUST-JESSICA", "turn_id": "turn-staff-test",
                                                       "preferences": [{"customer_id": "CUST-THEO"}]}, context)]
    assert [event["event"] for event in events] == ["step", "complete"]
    assert events[-1]["data"]["build_fingerprint"] == "b" * 64
    assert seen["identity"].subject == claims["sub"]
    assert seen["identity"].customer_id == "CUST-JESSICA"


def test_staged_runtime_imports_without_database_implementation(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    from render_agentcore_project import _render_runtime_source

    backend = Path(__file__).resolve().parents[1]
    staged, _ = _render_runtime_source(tmp_path, backend)
    code = """
import sys
sys.path.insert(0, sys.argv[1])
import operator_runtime
assert 'services.store_tools' not in sys.modules
assert 'services.database' not in sys.modules
assert not (operator_runtime.__file__ is None)
"""
    result = subprocess.run([sys.executable, "-I", "-c", code, str(staged)],
                            capture_output=True, text=True, env={**os.environ, "AWS_EC2_METADATA_DISABLED": "true"})
    assert result.returncode == 0, result.stderr


def test_staged_runtime_graph_tools_reach_only_shipped_modules(tmp_path):
    """Every tool, hook and closing step the staff Runtime runs works from the package alone.

    The package omits store_tools, operator_review and tool_audit_writer. Reaching any of
    them on the managed path would raise ModuleNotFoundError here, as it would in the
    container, where the first investigation would fail.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path
    from render_agentcore_project import _render_runtime_source

    backend = Path(__file__).resolve().parents[1]
    staged, _ = _render_runtime_source(tmp_path, backend)
    code = """
import json, sys
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
from services import operator_graph as graph

calls = []
def call_tool(name, args):
    calls.append(name)
    if name == "propose_store_credit":
        return {"status": "proposed", "review_id": 7, "proposal": None}
    if name == "finish_investigation":
        return {"status": "success", "answered_ids": [3]}
    return {"status": "success", "customer_id": "CUST-JESSICA"}

case = graph._Case(None, None, "CUST-JESSICA", "Jessica", "staff-sub", "turn-staged-proof",
                   lambda _event: None, call_tool=call_tool)
for read in graph._investigator_tools(case):
    json.loads(read())
json.loads(graph._advisor_tools(case)[0](order_ids=[20, 21], reason="Received return"))
assert graph.answer_open_requests(case) == [3]
hooks = graph._NodeHooks(case, graph.INVESTIGATOR_NODE, "model")
use = {"name": "get_orders", "toolUseId": "tool-1", "input": {}}
hooks.before_tool(SimpleNamespace(tool_use=use, agent=None))
hooks.after_tool(SimpleNamespace(tool_use=use, result={"status": "success", "content": [
    {"text": json.dumps({"status": "success", "orders": []})}]}, exception=None, cancel_message=None))
assert calls == ["get_orders", "get_tickets", "get_store_credits", "get_return_policy",
                 "propose_store_credit", "finish_investigation"], calls
unshipped = {"services.store_tools", "services.operator_review", "services.tool_audit_writer"}
assert not unshipped & set(sys.modules), unshipped & set(sys.modules)
"""
    result = subprocess.run([sys.executable, "-I", "-c", code, str(staged)],
                            capture_output=True, text=True, env={**os.environ, "AWS_EC2_METADATA_DISABLED": "true"})
    assert result.returncode == 0, result.stderr
