"""Lab 3's contract: the starter fails the way the guide's Spot step shows, the solution does not.

Task 3A. In the starter the Gateway withholds ``get_tickets`` and the server
binds no support read to the caller. Theo asks about his ticket on the managed
rail: the Support agent is built without the read instead of raising, its
prompt tells it to say plainly that it can't look up support tickets here, and
the Builder view names ``get_tickets`` as not published. In the solution the
read is published, the agent gets it, and a request naming Jessica is bound to
Theo before it leaves the process.

The managed Router runs for real; only the MCP client and the model are
replaced, by fakes that list the variant's published tools and call one tool.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from services import agentcore_gateway
from tests import lab_variants

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "deploy"))
sys.path.insert(0, str(REPO / "scripts"))
gateway_tool_schemas = importlib.import_module("gateway_tool_schemas")
lab3 = importlib.import_module("lab3_check")

THEO, JESSICA = "CUST-THEO", "CUST-JESSICA"
TARGET = "pellier-store-tools"


def _published(variant: str) -> frozenset:
    return gateway_tool_schemas.canonical_tool_names() - lab_variants.deferred_tools(variant)


class _FakeMcpClient:
    """Lists the variant's published tools under their Gateway names."""

    published: frozenset = frozenset()

    def __init__(self, _transport: Any) -> None:
        self.stopped = False

    def start(self) -> None:
        return None

    def list_tools_sync(self) -> List[Any]:
        return [
            SimpleNamespace(tool_name=f"{TARGET}___{name}",
                            mcp_tool=SimpleNamespace(name=f"{TARGET}___{name}"))
            for name in sorted(self.published)
        ]

    def stop(self, *_args: Any) -> None:
        self.stopped = True


class _FakeAgent:
    """Records what it was built with; asks for Jessica's tickets when it can."""

    built: List["_FakeAgent"] = []

    def __init__(self, *, name: str, model: Any, system_prompt: str, tools: List[Any]) -> None:
        self.name, self.system_prompt = name, system_prompt
        self.tool_names = [agentcore_gateway._logical_gateway_tool_name(t.tool_name) for t in tools]
        self.hooks: List[Any] = []
        _FakeAgent.built.append(self)

    def add_hook(self, hook: Any) -> None:
        self.hooks.append(hook)

    def __call__(self, prompt: str) -> str:
        if "get_tickets" not in self.tool_names:
            return "I can't look up support tickets here. I can hand this to a person."
        tool_use = {"toolUseId": "call-1", "name": f"{TARGET}___get_tickets",
                    "input": {"customer_id": JESSICA}}
        before = SimpleNamespace(tool_use=tool_use, cancel_tool=None)
        self.hooks[0](before)
        assert before.cancel_tool is None
        result = {"status": "success", "content": [{"text": '{"status": "success", "tickets": []}'}]}
        self.hooks[1](SimpleNamespace(tool_use=tool_use, result=result, exception=None))
        self.last_bound_input = dict(tool_use["input"])
        return "I can only look up the signed-in account."


@pytest.fixture()
def managed_support(monkeypatch: pytest.MonkeyPatch):
    """Run the real managed Router for Theo's support turn under one variant."""
    import strands
    import strands.models
    import strands.tools.mcp.mcp_client as mcp_client_module

    monkeypatch.setenv("AGENTCORE_GATEWAY_URL", "https://gateway.example.test/mcp")
    monkeypatch.setattr(mcp_client_module, "MCPClient", _FakeMcpClient)
    monkeypatch.setattr(strands, "Agent", _FakeAgent)
    monkeypatch.setattr(strands.models, "BedrockModel", lambda **_kwargs: object())
    monkeypatch.setattr(agentcore_gateway, "_model_gateway_tools", lambda tools: list(tools))
    _FakeAgent.built.clear()

    def run(variant: str) -> tuple:
        managed, bound = lab_variants.support_contract(variant)
        monkeypatch.setitem(agentcore_gateway.MANAGED_SPECIALIST_TOOLS, "support", managed)
        monkeypatch.setattr(agentcore_gateway, "SUPPORT_CALLER_BOUND_TOOLS", bound)
        monkeypatch.setattr(agentcore_gateway, "_CUSTOMER_SCOPED_TOOL_NAMES",
                            frozenset({"get_orders"}) | bound)
        _FakeMcpClient.published = _published(variant)
        dispatcher = agentcore_gateway.ManagedGatewayDispatcher(
            access_token="theo-token", customer_id=THEO,
            routing_query="My Wabi-Sabi Bowl arrived chipped. What is happening with my ticket?",
        )
        answer = dispatcher("My Wabi-Sabi Bowl arrived chipped. What is happening with my ticket?")
        return dispatcher, _FakeAgent.built[-1], answer

    return run


def _route_note(unpublished: List[str]) -> Any:
    import app as app_module
    from services.agentcore_runtime import ManagedRuntimeResult

    result = ManagedRuntimeResult(response="ok", intent="support", specialist="support",
                                  skills=[{"name": "the-care-card"}],
                                  unpublished_tools=unpublished)
    return app_module._managed_route_note(result, "fixed", "Support agent")


# ---------------------------------------------------------------------------
# The starter: an unpublished read, told plainly, never raised
# ---------------------------------------------------------------------------


def test_the_starter_withholds_get_tickets_and_binds_no_support_read() -> None:
    assert "get_tickets" not in _published(lab_variants.STARTER)
    managed, bound = lab_variants.support_contract(lab_variants.STARTER)
    assert "get_tickets" in managed and bound == frozenset()


def test_the_starter_support_turn_runs_without_the_read_and_says_so(managed_support) -> None:
    dispatcher, agent, answer = managed_support(lab_variants.STARTER)

    assert dispatcher.last_intent == "support"
    assert dispatcher.last_unpublished_tools == ("get_tickets",)
    assert "get_tickets" not in agent.tool_names
    assert set(agent.tool_names) == {"get_orders", "get_return_policy", "ask_a_person"}
    assert "can't look up support tickets here" in agent.system_prompt
    assert "Do not guess or invent them" in agent.system_prompt
    assert dispatcher.last_tool_events == []
    assert "support tickets" in answer


def test_the_starter_builder_view_names_the_tool_as_not_published() -> None:
    assert _route_note(["get_tickets"]) == (
        "get_tickets is not published on the Gateway, so the Support agent ran without it")
    assert _route_note([]) is None, "a published read leaves no note"


def test_the_doctor_names_the_starter_gap_and_passes_the_solution() -> None:
    def check(variant: str):
        managed, bound = lab_variants.support_contract(variant)
        return lab3.judge_catalogue(_published(variant), managed, bound)

    starter = check(lab_variants.STARTER)
    assert starter.state == lab3.check.NOT_YET
    assert "get_tickets" in starter.observed and "not published" in starter.observed
    solved = check(lab_variants.SOLUTION)
    assert solved.state == lab3.check.PROVED
    assert solved.observed == "9 tools published, get_tickets bound to the signed-in caller"


# ---------------------------------------------------------------------------
# The solution: published, granted, and bound to Theo
# ---------------------------------------------------------------------------


def test_the_solution_publishes_the_read_and_the_agent_gets_it(managed_support) -> None:
    dispatcher, agent, _answer = managed_support(lab_variants.SOLUTION)

    assert dispatcher.last_unpublished_tools == ()
    assert "get_tickets" in agent.tool_names
    assert "not available to you" not in agent.system_prompt


def test_the_solution_binds_a_request_for_jessica_to_theo(managed_support) -> None:
    """The household challenge: the model asks for CUST-JESSICA; the server binds CUST-THEO."""
    dispatcher, agent, _answer = managed_support(lab_variants.SOLUTION)

    assert agent.last_bound_input["customer_id"] == THEO
    (event,) = dispatcher.last_tool_events
    assert event["tool"] == "get_tickets"
    assert (event["requested_customer"], event["bound_customer"], event["binding"]) == (
        JESSICA, THEO, "overwritten")


def test_published_but_unbound_leaves_the_model_choosing_whose_tickets(managed_support,
                                                                       monkeypatch) -> None:
    """Half of Task 3A is not the task: publishing without binding lets Jessica's id through."""
    starter_bound = lab_variants.support_contract(lab_variants.STARTER)[1]
    real = lab_variants.support_contract

    def half(variant: str) -> tuple:
        managed, _bound = real(lab_variants.SOLUTION)
        return managed, starter_bound

    monkeypatch.setattr(lab_variants, "support_contract", half)
    dispatcher, agent, _answer = managed_support(lab_variants.SOLUTION)

    assert agent.last_bound_input["customer_id"] == JESSICA
    (event,) = dispatcher.last_tool_events
    assert event["binding"] == "unbound" and event["requested_other_customer"] is True
