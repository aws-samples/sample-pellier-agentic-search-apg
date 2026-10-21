"""How a tool call ended, read from the event Strands really builds, never from its text alone.

Strands hands every call that did not answer to the after-tool hook with status
``error`` and prose for text: a tool that raised, input that failed the tool's
schema, a tool the agent does not hold, a call a hook cancelled and, over MCP, a
Gateway refusal. Read as JSON that prose is no records at all, so a failed read
used to show a check and "No orders on file". Each case here runs through a
real Strands agent; only the model is scripted.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from strands import Agent, tool
from strands.hooks.events import AfterToolCallEvent, BeforeToolCallEvent

from services.turn_steps import (
    CANCELLED_FINDING,
    DENIED_FINDING,
    INVALID_FINDING,
    OUTCOME_CANCELLED,
    OUTCOME_DENIED,
    OUTCOME_FAILED,
    OUTCOME_INVALID,
    OUTCOME_NOT_HELD,
    OUTCOME_OK,
    ToolOutcome,
    TurnSteps,
    outcome_finding,
    tool_outcome,
)
from tests.scripted_model import ScriptedModel

# The Gateway's words for a Cedar denial, as AgentCore returns them in an isError result.
GATEWAY_DENIAL = (
    "Tool call not allowed due to policy enforcement [Policy evaluation denied due to "
    "pellier_owner_only_reads-a1b2c3]"
)


@tool
def check_stock(product_name: str) -> str:
    """Units of one piece in each warehouse.

    Args:
        product_name: The piece to look up.
    """
    return json.dumps({"status": "success", "product": product_name,
                       "warehouses": [{"city": "Brooklyn", "quantity": 3}]})


@tool
def get_orders(customer_id: str) -> str:
    """One customer's orders.

    Args:
        customer_id: Whose orders.
    """
    raise RuntimeError("connection to Aurora refused")


@tool
def get_tickets(customer_id: str) -> Dict[str, Any]:
    """One customer's tickets, as the Gateway answers a call Cedar denied.

    Args:
        customer_id: Whose tickets.
    """
    return {"status": "error", "content": [{"text": GATEWAY_DENIAL}]}


def _outcome(name: str, tool_input: Dict[str, Any], *, tools: Optional[list] = None,
             cancel: Optional[str] = None) -> ToolOutcome:
    """Run one scripted call through a real agent; how its after-tool event reads."""
    seen: Dict[str, ToolOutcome] = {}
    agent = Agent(model=ScriptedModel([(name, tool_input)]),
                  tools=tools or [check_stock, get_orders, get_tickets], callback_handler=None)

    def before(event: BeforeToolCallEvent) -> None:
        if cancel:
            event.cancel_tool = cancel

    def after(event: AfterToolCallEvent) -> None:
        seen["outcome"] = tool_outcome(
            event.tool_use["name"], event.result, exception=event.exception,
            cancel_message=event.cancel_message,
        )

    agent.add_hook(before)
    agent.add_hook(after)
    agent("go")
    return seen["outcome"]


def test_a_call_that_answered_is_ok() -> None:
    outcome = _outcome("check_stock", {"product_name": "Waffle Bath Robe"})
    assert outcome.kind == OUTCOME_OK and not outcome.failed
    assert outcome_finding("check_stock", outcome) is None, "an answer keeps its own finding"


def test_a_tool_that_raised_failed_and_says_which_check() -> None:
    outcome = _outcome("get_orders", {"customer_id": "CUST-THEO"})
    assert outcome.kind == OUTCOME_FAILED
    assert outcome.text.startswith("Error: RuntimeError - connection to Aurora refused")
    assert outcome_finding("get_orders", outcome) == "Your orders could not be read"


def test_input_that_failed_the_schema_is_invalid_and_never_ran() -> None:
    outcome = _outcome("check_stock", {})
    assert outcome.kind == OUTCOME_INVALID
    assert outcome_finding("check_stock", outcome) == INVALID_FINDING


def test_a_tool_the_agent_does_not_hold_did_not_run() -> None:
    outcome = _outcome("give_store_credit", {"amount_cents": 10000})
    assert outcome.kind == OUTCOME_NOT_HELD
    assert outcome_finding("give_store_credit", outcome) == (
        "give_store_credit is not one of this agent's tools; it did not run")


def test_a_step_given_only_the_text_still_names_a_tool_the_agent_does_not_hold() -> None:
    step = TurnSteps().finished("give_store_credit", "Unknown tool: give_store_credit")
    assert step["status"] == "failed" and step["builder"]["outcome"] == OUTCOME_NOT_HELD
    assert step["finding"] == "give_store_credit is not one of this agent's tools; it did not run"


def test_a_cedar_denial_at_the_gateway_reads_as_denied() -> None:
    outcome = _outcome("get_tickets", {"customer_id": "CUST-JESSICA"})
    assert outcome.kind == OUTCOME_DENIED
    assert outcome_finding("get_tickets", outcome) == DENIED_FINDING


def test_a_denial_raised_by_the_mcp_client_reads_as_denied() -> None:
    """Strands turns a raised MCP error into "Tool execution failed: <the error>"."""
    result = {"status": "error",
              "content": [{"text": f"Tool execution failed: {GATEWAY_DENIAL}"}]}
    assert tool_outcome("get_tickets", result, exception=RuntimeError(GATEWAY_DENIAL)).kind == (
        OUTCOME_DENIED)


def test_an_access_denied_that_is_not_cedar_stays_a_failure() -> None:
    """A 401, a 403 or an IAM refusal is not a policy decision, and must not read as one."""
    for text in ("AccessDeniedException: User is not authorized to perform: lambda:InvokeFunction",
                 "HTTP 401 Unauthorized", "Forbidden"):
        result = {"status": "error", "content": [{"text": text}]}
        assert tool_outcome("get_tickets", result).kind == OUTCOME_FAILED, text


def test_output_suppressed_by_policy_is_not_a_denial() -> None:
    """Suppression comes after authorization: the tool ran, so it is no DENY proof."""
    result = {"status": "error",
              "content": [{"text": "Tool output suppressed due to policy enforcement"}]}
    assert tool_outcome("get_tickets", result).kind == OUTCOME_FAILED


def test_a_cancelled_call_did_not_run_and_a_missing_sign_in_says_so() -> None:
    outcome = _outcome("get_orders", {"customer_id": "CUST-THEO"},
                       cancel="get_orders requires verified Aurora customer context")
    assert outcome.kind == OUTCOME_CANCELLED
    assert outcome_finding("get_orders", outcome) == "Sign in before account records can be read"
    other = _outcome("check_stock", {"product_name": "Robe"}, cancel="stopped by a test")
    assert outcome_finding("check_stock", other) == CANCELLED_FINDING


def test_an_error_the_tool_reported_in_its_own_json_failed() -> None:
    @tool
    def browse_department(department: str) -> str:
        """One department.

        Args:
            department: Which.
        """
        return json.dumps({"status": "error", "message": "department lookup failed"})

    outcome = _outcome("browse_department", {"department": "Home"}, tools=[browse_department])
    assert outcome.kind == OUTCOME_FAILED
    assert outcome_finding("browse_department", outcome) == "The department could not be read"


def test_a_step_judged_by_its_outcome_fails_where_its_text_looked_empty() -> None:
    """The bug: error prose parsed as no rows, so the step showed done with an empty finding."""
    steps = TurnSteps()
    steps.route(agent="Support agent", intent="support", finding="Sent to the Support agent",
                model_id="global.anthropic.claude-opus-5", skills=[], skill_mode="fixed")
    outcome = _outcome("get_orders", {"customer_id": "CUST-THEO"})
    step = steps.finished("get_orders", outcome.text, call_id="use-0", outcome=outcome)

    assert step["status"] == "failed"
    assert step["finding"] == "Your orders could not be read"
    assert step["builder"]["outcome"] == OUTCOME_FAILED


def test_a_denied_step_carries_the_policy_layer() -> None:
    steps = TurnSteps()
    outcome = _outcome("get_tickets", {"customer_id": "CUST-JESSICA"})
    step = steps.finished("get_tickets", outcome.text, call_id="use-0", outcome=outcome)
    assert step["status"] == "failed" and step["finding"] == DENIED_FINDING
    assert step["tags"] == ["Aurora", "Identity", "Policy"]


# ---------------------------------------------------------------------------
# The managed rail: the Runtime's dispatcher classifies, the app's step shows it
# ---------------------------------------------------------------------------


class _GatewayListing:
    """An MCP client that lists get_tickets under its Gateway name."""

    def __init__(self, _transport: Any) -> None:
        return None

    def start(self) -> None:
        return None

    def list_tools_sync(self) -> list:
        from types import SimpleNamespace

        name = "pellier-store-tools___get_tickets"
        return [SimpleNamespace(tool_name=name, mcp_tool=SimpleNamespace(name=name))]

    def stop(self, *_args: Any) -> None:
        return None


def test_a_cedar_denial_on_the_managed_rail_is_a_failed_policy_step(monkeypatch) -> None:
    """The real dispatcher and a real agent; the Gateway answers the call with a denial."""
    import strands.models
    import strands.tools.mcp.mcp_client as mcp_client_module

    from services import agentcore_gateway

    monkeypatch.setenv("AGENTCORE_GATEWAY_URL", "https://gateway.example.test/mcp")
    monkeypatch.setattr(mcp_client_module, "MCPClient", _GatewayListing)
    monkeypatch.setattr(strands.models, "BedrockModel", lambda **_kwargs: ScriptedModel(
        [("get_tickets", {"customer_id": "CUST-JESSICA"})], "I can't read those tickets."))
    # The MCP adapter is replaced by a tool that answers as the Gateway does for a DENY.
    monkeypatch.setattr(agentcore_gateway, "_model_gateway_tools", lambda _tools: [get_tickets])
    monkeypatch.setitem(agentcore_gateway.MANAGED_SPECIALIST_TOOLS, "support", ("get_tickets",))
    monkeypatch.setattr(agentcore_gateway, "_CUSTOMER_SCOPED_TOOL_NAMES",
                        frozenset({"get_tickets"}))

    dispatcher = agentcore_gateway.ManagedGatewayDispatcher(
        access_token="theo-token", customer_id="CUST-THEO",
        routing_query="What is happening with my support ticket?",
    )
    dispatcher("What is happening with my support ticket?")
    (call,) = dispatcher.last_tool_events
    assert (call["tool"], call["status"], call["outcome"]) == ("get_tickets", "error", "denied")
    assert call["finding"] == DENIED_FINDING

    steps = TurnSteps()
    steps.route(agent="Support agent", intent="support", finding="Sent to the Support agent",
                model_id=dispatcher.last_model_id, skills=[], skill_mode="fixed",
                rail="gateway-mcp")
    step = steps.managed(call)
    assert step["status"] == "failed" and step["finding"] == DENIED_FINDING
    assert step["tags"] == ["Aurora", "Identity", "Policy"]
    assert step["builder"]["outcome"] == OUTCOME_DENIED
    assert step["builder"]["model_id"] == dispatcher.last_model_id


def test_a_managed_call_the_tool_failed_in_its_own_json_is_failed() -> None:
    """The Runtime said success, yet the result was an error: the step must not show a check."""
    step = TurnSteps().managed({"tool": "check_stock", "status": "success", "outcome": "failed",
                                "finding": "The stock check did not complete"})
    assert step["status"] == "failed" and step["builder"]["outcome"] == OUTCOME_FAILED


def test_a_call_from_an_older_runtime_bundle_reads_its_status() -> None:
    """A Runtime deployed before outcomes existed sends status only."""
    old = TurnSteps().managed({"tool": "check_stock", "status": "error"})
    assert old["status"] == "failed" and old["builder"]["outcome"] == OUTCOME_FAILED
    assert TurnSteps().managed({"tool": "check_stock", "status": "success"})["status"] == "done"
