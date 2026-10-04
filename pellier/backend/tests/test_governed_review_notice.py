"""A shopper's store credit request: no amount, not approvable, and said plainly.

The measured defect
-------------------

On the shopper rail a store credit is never written: ``ask_a_person`` opens a
credit request on the customer's case, and the credit itself is
``give_store_credit``, staff only, for the review the Operator's Planner
proposes. The Support agent is told to say that a person reviews the credit and
that nothing has changed yet. On 2026-08-27, against the live stack, a model
said it had "prepared the request" and dropped the second sentence, and a
shopper reading that reasonably concluded the action was done.

So the handoff payload carries the request id and the chat surface emits the
notice as its own ``review_pending`` event with the backend's sentence. The
request names no amount anywhere: not in the tool's arguments, the Gateway
schema, the Lambda, the row it writes, or the sentence the shopper hears.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from pellier_copy import CREDIT_REQUEST_PENDING
from services import chat as CHAT
from services import store_tools

REPO = Path(__file__).resolve().parents[3]


def test_the_sentence_says_what_did_and_did_not_happen_and_names_no_amount() -> None:
    """The refusal taxonomy in VOICE.md: what happened, what did not, who acts next."""
    text = CREDIT_REQUEST_PENDING
    assert "a person at pellier will review" in text.lower()
    assert "nothing on your account has changed yet" in text.lower()
    assert "—" not in text and "$" not in text and not any(ch.isdigit() for ch in text)
    for internal in ("managed_rail", "gateway", "Cedar", "policy", "rail", "tool", "approve"):
        assert internal.lower() not in text.lower(), internal


def test_no_agent_can_reach_a_credit_write_in_process() -> None:
    """The boundary is structural: the wrapper does not exist, so no agent binds it."""
    from agents import shopping_agent, stock_agent, support_agent
    from services import agent_tools

    assert not hasattr(agent_tools, "give_store_credit")
    for module in (shopping_agent, stock_agent, support_agent):
        assert "give_store_credit" not in inspect.getsource(module), module.__name__


# ---------------------------------------------------------------------------
# The request is opened by the handoff, only for a known customer, with no amount
# ---------------------------------------------------------------------------


class _Run:
    """The INSERT answers a request id, or nothing when an open request stands."""

    def __init__(self, request_id: int | None = 44) -> None:
        self.request_id = request_id
        self.calls: List[tuple[str, tuple[Any, ...]]] = []

    def __call__(self, sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        self.calls.append((sql, tuple(params)))
        if "INSERT INTO pellier.approvals" in sql:
            return [{"id": self.request_id}] if self.request_id else []
        if "FROM pellier.approvals" in sql:
            return [{"id": 45}]
        return []


def test_a_credit_request_opens_one_request_with_no_amount_and_no_hash() -> None:
    run = _Run()
    payload = store_tools.ask_a_person(
        run, reason="Two items went back.", customer_id="CUST-JESSICA", credit_request=True,
        source_turn_id="turn-" + "a" * 32, requested_by_sub="sub-j", requester_kind="shopper",
    )
    assert payload["credit_request_status"] == "request_opened" and payload["request_id"] == 44
    sql, params = run.calls[0]
    assert "'store_credit_request', '{}'::jsonb, 'pending'" in sql
    assert "action_hash" not in sql and "amount" not in sql
    assert params == ("CUST-JESSICA", "turn-" + "a" * 32, "Two items went back.", "sub-j",
                      "shopper", "CUST-JESSICA")


def test_a_repeated_ask_resolves_to_the_open_request() -> None:
    run = _Run(request_id=None)
    payload = store_tools.ask_a_person(
        run, reason="Two items went back.", customer_id="CUST-JESSICA", credit_request=True,
    )
    assert payload["credit_request_status"] == "already_requested" and payload["request_id"] == 45
    assert len(run.calls) == 2
    assert "recommendation->>'investigationTurnId' IS NULL" in run.calls[1][0]


def test_a_credit_request_without_a_known_customer_opens_nothing() -> None:
    run = _Run()
    payload = store_tools.ask_a_person(run, reason="Credit please.", customer_id=None, credit_request=True)
    assert payload["credit_request_status"] == "sign_in_required"
    assert run.calls == []


def test_a_plain_handoff_is_not_a_credit_request() -> None:
    run = _Run()
    payload = store_tools.ask_a_person(run, reason="I want a person.", customer_id="CUST-THEO")
    assert "credit_request_status" not in payload and payload["status"] == "handed_off"
    assert run.calls == []


def _deploy_module(name: str, file: str) -> Any:
    import importlib.util
    import sys

    deploy = REPO / "scripts" / "deploy"
    if str(deploy) not in sys.path:
        sys.path.insert(0, str(deploy))
    spec = importlib.util.spec_from_file_location(name, deploy / file)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_shopper_request_carries_no_amount_in_process() -> None:
    from agents import support_agent
    from services import agent_tools

    assert set(inspect.signature(store_tools.ask_a_person).parameters) == {
        "run", "reason", "customer_id", "credit_request", "source_turn_id",
        "requested_by_sub", "requester_kind",
    }
    wrapper = agent_tools.ask_a_person.tool_spec["inputSchema"]["json"]["properties"]
    assert set(wrapper) == {"reason", "credit_request", "customer_id"}
    prompt = support_agent._SUPPORT_SYSTEM_PROMPT
    assert "store_credit_cents" not in prompt and "credit_request" in prompt
    assert "never name or suggest an amount" in prompt
    care_card = (REPO / "skills" / "the-care-card" / "SKILL.md").read_text()
    assert "passes its amount" not in care_card and "names no amount" in care_card


def test_the_gateway_publishes_no_amount_and_the_lambda_reads_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schemas = _deploy_module("gateway_tool_schemas_amount_check", "gateway_tool_schemas.py")
    tools = {tool["name"]: tool for tool in schemas.TOOL_SCHEMAS["store"]["tools"]}
    properties = tools["ask_a_person"]["inputSchema"]["properties"]
    assert set(properties) == {"reason", "customer_id", "credit_request", "turn_id"}
    assert properties["credit_request"] == {"type": "boolean"}

    server = _deploy_module("store_tools_lambda_amount_check", "pellier_store_tools.py")
    import common.dataapi as dataapi

    calls: List[tuple[str, list]] = []

    def execute(sql: str, parameters: list | None = None) -> List[Dict[str, Any]]:
        calls.append((sql, parameters or []))
        return [{"id": 7}] if "INSERT INTO pellier.approvals" in sql else []

    monkeypatch.setattr(dataapi, "execute_sql", execute)
    # A caller that sends an amount anyway: it reaches no statement.
    result = server.TOOLS["ask_a_person"](
        {"reason": "Credit please.", "customer_id": "CUST-JESSICA", "credit_request": True,
         "store_credit_cents": 9999, "amount_cents": 9999},
        "turn-" + "b" * 32,
    )
    assert result["credit_request_status"] == "request_opened" and result["request_id"] == 7
    (sql, parameters), = calls
    assert "'store_credit_request'" in sql
    values = [next(iter(p["value"].values())) for p in parameters]
    assert 9999 not in values and "9999" not in values


# ---------------------------------------------------------------------------
# The chat surface emits the sentence from the payload, not from the prose
# ---------------------------------------------------------------------------


def test_the_scanner_finds_the_handoff_payload() -> None:
    found = CHAT._scan_for_escalation(json.dumps({"type": "escalation", "request_id": 44}))
    assert found is not None and found["request_id"] == 44


def test_the_scanner_ignores_everything_else() -> None:
    for other in (
        "",
        "plain prose with no payload",
        json.dumps({"status": "success", "credit_id": 37}),
        json.dumps({"error": "managed_rail_required", "tool": "give_store_credit"}),
    ):
        assert CHAT._scan_for_escalation(other) is None


@pytest.mark.parametrize("status", ["request_opened", "already_requested"])
def test_an_open_request_earns_the_notice(status: str) -> None:
    notice = CHAT.credit_request_notice({
        "type": "escalation", "credit_request_status": status, "request_id": 44,
        "customer_id": "CUST-JESSICA",
    })
    assert notice == {
        "type": "review_pending",
        "reviewPending": {
            "tool": "store_credit_request", "requestId": 44, "customerId": "CUST-JESSICA",
            "message": CREDIT_REQUEST_PENDING,
        },
    }


@pytest.mark.parametrize(
    "escalation",
    [
        {"type": "escalation", "status": "handed_off"},
        {"type": "escalation", "credit_request_status": "sign_in_required"},
        {"type": "escalation", "credit_request_status": "not_recorded"},
        # The state cut 3 could produce: a shopper must never hear "a person will
        # review" for a credit someone already approved.
        {"type": "escalation", "credit_request_status": "already_approved", "review_id": 41,
         "request_id": 41, "customer_id": "CUST-JESSICA"},
        {"type": "escalation", "credit_request_status": "request_opened", "customer_id": "CUST-A"},
        {"type": "escalation", "credit_request_status": "request_opened", "request_id": 4},
    ],
)
def test_no_notice_without_an_open_request(escalation: Dict[str, Any]) -> None:
    assert CHAT.credit_request_notice(escalation) is None


def test_the_support_prompt_still_asks_for_the_sentence() -> None:
    """Belt and braces. The notice does not license removing the instruction."""
    from agents import support_agent

    prompt = support_agent._SUPPORT_SYSTEM_PROMPT
    assert "say a person at Pellier will review the store credit" in prompt
    assert "nothing has changed yet" in prompt
    assert "Do not name an amount" in prompt
    assert "never say a refund, return or credit was made unless a tool result says so" in prompt
