"""Lab 3's contract: the starter fails the way the guide's See it fail shows, the solution does not.

Task 3A. In the starter the Gateway withholds ``get_tickets``, the Support agent
asks only for ``get_return_policy`` and ``ask_a_person``, and the server binds no
read to the caller. The starter is still a working agent: a returns question is
answered from the return policy, and Theo's ticket question gets an agent with
no ticket read to invent from. The check names, before any deploy, the reads
Theo's household request needs and that ``get_tickets`` is unpublished. In the
solution the reads are published, asked for and bound, and a request naming
Jessica is bound to Theo before it leaves the process.

The managed Router runs for real; only the MCP client and the model are
replaced, by fakes that list the variant's published tools and call one tool.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List

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
TICKET_QUESTION = "My Wabi-Sabi Bowl arrived chipped. What is happening with my ticket?"
RETURNS_QUESTION = "What is your return policy for home goods?"


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
        text = '{"status": "success", "tickets": []}'
        result = {"status": "success", "content": [{"text": text}]}
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
    from services import model_fallback

    monkeypatch.setattr(model_fallback, "specialist_bedrock_model", lambda *_args: object())
    monkeypatch.setattr(agentcore_gateway, "_model_gateway_tools", lambda tools: list(tools))
    _FakeAgent.built.clear()

    def run(variant: str, message: str = TICKET_QUESTION) -> tuple:
        managed, bound = lab_variants.support_contract(variant)
        monkeypatch.setitem(agentcore_gateway.MANAGED_SPECIALIST_TOOLS, "support", managed)
        monkeypatch.setattr(agentcore_gateway, "SUPPORT_CALLER_BOUND_TOOLS", bound)
        monkeypatch.setattr(agentcore_gateway, "_CUSTOMER_SCOPED_TOOL_NAMES", bound)
        _FakeMcpClient.published = _published(variant)
        dispatcher = agentcore_gateway.ManagedGatewayDispatcher(
            access_token="theo-token", customer_id=THEO, routing_query=message,
        )
        answer = dispatcher(message)
        return dispatcher, _FakeAgent.built[-1], answer

    return run


def _route_note(unpublished: List[str]) -> Any:
    import app as app_module
    from services.agentcore_runtime import ManagedRuntimeResult

    result = ManagedRuntimeResult(response="ok", intent="support", specialist="support",
                                  skills=[{"name": "care-and-returns"}],
                                  unpublished_tools=unpublished)
    return app_module._managed_route_note(result, "fixed", "Support agent")


# ---------------------------------------------------------------------------
# The starter: an unpublished read, told plainly, never raised
# ---------------------------------------------------------------------------


def test_the_starter_withholds_get_tickets_and_asks_for_neither_read() -> None:
    assert "get_tickets" not in _published(lab_variants.STARTER)
    managed, bound = lab_variants.support_contract(lab_variants.STARTER)
    assert managed == ("get_return_policy", "ask_a_person") and bound == frozenset()


def test_the_starter_is_a_working_agent_for_a_returns_question(managed_support) -> None:
    dispatcher, agent, answer = managed_support(lab_variants.STARTER, RETURNS_QUESTION)

    assert dispatcher.last_intent == "support"
    assert set(agent.tool_names) == {"get_return_policy", "ask_a_person"}
    assert dispatcher.last_unpublished_tools == ()
    assert answer


def test_the_starter_ticket_turn_has_no_ticket_read_to_invent_from(managed_support) -> None:
    dispatcher, agent, answer = managed_support(lab_variants.STARTER)

    assert dispatcher.last_intent == "support"
    assert "get_tickets" not in agent.tool_names and "get_orders" not in agent.tool_names
    assert "Treat tool output as the only source of" in agent.system_prompt
    assert "customer" in agent.system_prompt.split("only source of", 1)[1][:80]
    assert dispatcher.last_tool_events == []
    assert "support tickets" in answer


def test_the_starter_builder_view_names_the_tool_as_not_published() -> None:
    assert _route_note(["get_tickets"]) == (
        "get_tickets is not in the Gateway's tool list for this caller, so the Support agent "
        "ran without it")
    assert _route_note([]) is None, "a published read leaves no note"


def _rules(variant: str, probes=None):
    managed, bound = lab_variants.support_contract(variant)
    return lab3.judge_catalog(_published(variant), managed, bound, probes)


def test_the_starter_check_names_the_reads_and_the_unpublished_tool() -> None:
    published, reads, bound, staff = _rules(lab_variants.STARTER)
    assert published.state == lab3.check.NOT_YET
    assert published.observed == ("get_tickets is not published: "
                                  "scripts/deploy/gateway_tool_schemas.py withholds it")
    assert reads.state == lab3.check.NOT_YET
    assert reads.observed == ("the Support agent asks for get_return_policy and ask_a_person; "
                              "Theo's household request needs get_orders and get_tickets")
    assert reads.next_step.startswith("which of the nine tools take a customer_id?")
    assert bound.state == lab3.check.NOT_YET
    assert bound.next_step.startswith("which of the nine tools take a customer_id?")
    assert staff.state == lab3.check.PROVED
    assert "published is not permitted" in staff.observed


def test_the_solution_meets_all_four_rules() -> None:
    findings = _rules(lab_variants.SOLUTION)
    assert [f.state for f in findings] == [lab3.check.PROVED] * 4
    verdict = lab3.catalog_verdict(findings)
    assert verdict.state == lab3.check.PROVED
    assert verdict.observed.startswith("9 of the nine tools published, get_tickets among them")


def test_a_staff_only_tool_on_the_support_agent_is_refused() -> None:
    managed, bound = lab_variants.support_contract(lab_variants.SOLUTION)
    findings = lab3.judge_catalog(_published(lab_variants.SOLUTION),
                                    managed + ("give_store_credit",), bound)
    assert findings[3].state == lab3.check.CONTRADICTED
    assert "published is not permitted" in findings[3].observed
    assert lab3.catalog_verdict(findings) is findings[3]


# ---------------------------------------------------------------------------
# The solution: published, granted, and bound to Theo
# ---------------------------------------------------------------------------


def test_the_solution_publishes_the_read_and_the_agent_gets_it(managed_support) -> None:
    dispatcher, agent, _answer = managed_support(lab_variants.SOLUTION)

    assert dispatcher.last_unpublished_tools == ()
    assert "get_tickets" in agent.tool_names
    assert "does not list these tools" not in agent.system_prompt


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


# ---------------------------------------------------------------------------
# The check's forged call: what the server's binding does, every time
# ---------------------------------------------------------------------------


def _probe(variant: str, monkeypatch, tool: str = "get_tickets") -> dict:
    """A forged read through the server binding, under one variant's region."""
    _managed, bound = lab_variants.support_contract(variant)
    monkeypatch.setattr(agentcore_gateway, "_CUSTOMER_SCOPED_TOOL_NAMES", bound)
    return lab3.probe_binding(agentcore_gateway._bind_server_tool_context, tool)


def _probes(variant: str, monkeypatch) -> dict:
    return {read: _probe(variant, monkeypatch, read) for read in lab3.SHOPPER_READS}


def test_the_forged_call_leaves_the_starter_as_jessica_and_the_solution_as_theo(
    monkeypatch,
) -> None:
    assert _probe(lab_variants.STARTER, monkeypatch) == {"sent": JESSICA, "unsigned": JESSICA}
    assert _probe(lab_variants.SOLUTION, monkeypatch) == {"sent": THEO, "unsigned": "refused"}


def test_published_and_asked_but_unbound_names_the_forged_customer(monkeypatch) -> None:
    """Task 3A two-thirds done: the reads published and asked for, the region binding none."""
    managed, _bound = lab_variants.support_contract(lab_variants.SOLUTION)
    probes = _probes(lab_variants.STARTER, monkeypatch)
    findings = lab3.judge_catalog(_published(lab_variants.SOLUTION), managed, frozenset(),
                                    probes)
    assert [f.state for f in findings[:2]] == [lab3.check.PROVED] * 2
    bound = findings[2]
    assert bound.state == lab3.check.NOT_YET
    assert bound.observed.startswith("get_orders and get_tickets take a customer_id")
    assert f"a forged get_orders or get_tickets call for {JESSICA} would leave as {JESSICA}" \
        in bound.observed
    assert any("the server sends CUST-JESSICA" in line for line in bound.evidence)


def test_the_solution_passes_on_the_forged_calls(monkeypatch) -> None:
    findings = _rules(lab_variants.SOLUTION, _probes(lab_variants.SOLUTION, monkeypatch))
    bound = findings[2]
    assert bound.state == lab3.check.PROVED
    assert bound.observed == f"get_orders and get_tickets bound; a forged call for {JESSICA} " \
                             f"leaves as {THEO}"
    assert "the same get_orders call with no signed-in customer: refused" in bound.evidence


THEO_READS = [{"audit_id": 7, "turn_id": "turn-a", "customer_id": THEO}]


def test_theos_own_reads_do_not_prove_the_binding_without_the_forged_call(monkeypatch) -> None:
    """The model names Theo by itself, so his reads look the same bound or unbound."""
    unbound = lab3.judge_tickets(THEO_READS, _probe(lab_variants.STARTER, monkeypatch))
    assert unbound.state == lab3.check.CONTRADICTED
    assert f"a forged call for {JESSICA} would leave as {JESSICA}" in unbound.observed
    assert "SUPPORT_CALLER_BOUND_TOOLS" in unbound.next_step

    bound = lab3.judge_tickets(THEO_READS, _probe(lab_variants.SOLUTION, monkeypatch))
    assert bound.state == lab3.check.PROVED
    assert bound.observed.endswith(f"a forged call for {JESSICA} leaves as {THEO}")


def test_the_tickets_finding_is_unchecked_when_the_forged_call_cannot_run(monkeypatch) -> None:
    """Without the forged call, Theo's own reads cannot show the binding, so nothing is proved."""
    def broken() -> tuple:
        raise ModuleNotFoundError("strands.vended_plugins")

    monkeypatch.setattr(lab3, "source_catalog", broken)
    finding = lab3.tickets_finding(THEO_READS)
    assert finding.state == lab3.check.UNCHECKED
    assert "ModuleNotFoundError: strands.vended_plugins" in finding.evidence[0]
