"""The Operator's two-node Strands graph: Investigator, then Planner.

The graph is built with the real ``GraphBuilder`` API but a fake builder and
fake agents stand in for Strands and Bedrock, so no model is called. The tools
are the real closures over a recording ``run`` stand-in, so the amount the
Planner proposes is computed from real order rows and the review it opens is
the real INSERT.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from services import operator_graph as GRAPH
from services.store_tools import write_request_hash

JESSICA_ORDERS = [
    {"order_id": 301, "product_id": "42", "name": "Waffle Bath Robe, Sage", "brand": "NestWell",
     "category": "Home", "quantity": 1, "amount_paid_cents": 6400, "placed_at": None},
    {"order_id": 302, "product_id": "25", "name": "Reed Diffuser", "brand": "Pellier",
     "category": "Home", "quantity": 1, "amount_paid_cents": 3600, "placed_at": None},
    {"order_id": 303, "product_id": "31", "name": "Stoneware Pour-Over Set", "brand": "Pellier",
     "category": "Home", "quantity": 1, "amount_paid_cents": 5800, "placed_at": None},
]


class _Run:
    """Jessica's records, and every statement the graph issued."""

    def __init__(self) -> None:
        self.calls: List[tuple[str, tuple[Any, ...]]] = []
        self.reviews: List[Dict[str, Any]] = []

    def __call__(self, sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        self.calls.append((sql, tuple(params)))
        if "FROM pellier.orders o" in sql and "o.id = ANY" in sql:
            wanted = set(int(v) for v in params[1])
            return [dict(o) for o in JESSICA_ORDERS if o["order_id"] in wanted]
        if "FROM pellier.orders o" in sql:
            return [dict(o) for o in JESSICA_ORDERS]
        if "FROM pellier.support_tickets" in sql:
            return [{"ticket_id": "TKT-2026-3015", "subject": "Two items went back, no credit yet",
                     "status": "open", "channel": "chat", "last_note": "Both were received.",
                     "opened_at": None, "resolved_at": None}]
        if "FROM pellier.return_policies" in sql:
            return [{"category_name": "Home", "return_window_days": 30,
                     "conditions": "Unused", "refund_method": "original payment"}]
        if "FROM pellier.store_credits" in sql:
            return []
        if "INSERT INTO pellier.approvals" in sql:
            self.reviews.append({"params": params})
            return [{"id": 41}]
        return []


@dataclass
class _NodeResult:
    output: str
    execution_time: int
    status: Any = field(default_factory=lambda: SimpleNamespace(value="completed"))

    def get_agent_results(self) -> list[str]:
        return [self.output]


class _FakeAgent:
    """Runs the tools a scripted node would run, through the real hooks."""

    scripts: Dict[str, List[tuple[str, Dict[str, Any]]]] = {}
    outputs: Dict[str, str] = {}

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.name = kwargs["name"]
        self.tools = {tool.tool_name: tool for tool in kwargs["tools"]}
        self.hooks: List[Any] = list(kwargs.get("hooks") or [])
        self.callbacks: Dict[Any, List[Any]] = {}
        for provider in self.hooks:
            provider.register_hooks(self)

    def add_callback(self, event_type: Any, callback: Any) -> None:
        self.callbacks.setdefault(event_type.__name__, []).append(callback)

    def _fire(self, name: str, **fields: Any) -> None:
        for callback in self.callbacks.get(name, []):
            callback(SimpleNamespace(agent=self, **fields))

    def run(self) -> _NodeResult:
        self._fire("BeforeInvocationEvent")
        for index, (tool_name, tool_input) in enumerate(self.scripts.get(self.name, [])):
            tool_use = {"name": tool_name, "input": tool_input, "toolUseId": f"{self.name}-{index}"}
            self._fire("BeforeToolCallEvent", tool_use=tool_use, selected_tool=self.tools[tool_name])
            text = self.tools[tool_name](**tool_input)
            self._fire("AfterToolCallEvent", tool_use=tool_use, selected_tool=self.tools[tool_name],
                       result={"toolUseId": tool_use["toolUseId"], "status": "success",
                               "content": [{"text": text}]}, exception=None)
        self._fire("AfterInvocationEvent", result=None)
        return _NodeResult(self.outputs.get(self.name, ""), 7)


class _FakeGraph:
    def __init__(self, nodes: List[tuple[Any, str]], *, fail: bool = False) -> None:
        self.nodes = nodes
        self.fail = fail
        self.trace_attributes: Dict[str, str] = {}

    def __call__(self, task: str, invocation_state: Any = None) -> Any:
        self.task = task
        if self.fail:
            raise RuntimeError("graph unavailable")
        results = {}
        order = []
        for agent, node_id in self.nodes:
            results[node_id] = agent.run()
            order.append(SimpleNamespace(node_id=node_id))
        return SimpleNamespace(results=results, execution_order=order)


class _FakeBuilder:
    latest: "_FakeBuilder | None" = None
    fail = False

    def __init__(self) -> None:
        type(self).latest = self
        self.nodes: list[tuple[Any, str]] = []
        self.edges: list[tuple[str, str]] = []
        self.entry = ""
        self.max_executions = 0

    def set_max_node_executions(self, value: int) -> "_FakeBuilder":
        self.max_executions = value
        return self

    def set_execution_timeout(self, value: float) -> "_FakeBuilder":
        return self

    def set_node_timeout(self, value: float) -> "_FakeBuilder":
        return self

    def add_node(self, executor: Any, node_id: str) -> Any:
        self.nodes.append((executor, node_id))
        return SimpleNamespace(node_id=node_id)

    def add_edge(self, source: str, target: str) -> Any:
        self.edges.append((source, target))
        return SimpleNamespace()

    def set_entry_point(self, node_id: str) -> "_FakeBuilder":
        self.entry = node_id
        return self

    def build(self) -> _FakeGraph:
        self.graph = _FakeGraph(self.nodes, fail=type(self).fail)
        return self.graph


class _FakeModel:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


INVESTIGATOR_BRIEF = json.dumps({
    "facts": [
        "Jessica ordered the Waffle Bath Robe, Sage for $64.00 and the Reed Diffuser for $36.00.",
        "Her open ticket says both went back and were received.",
        "Home returns have a 30-day window.",
    ],
    "missing": ["No store credit is recorded for the two returned items."],
})


@pytest.fixture
def graph_runtime(monkeypatch: pytest.MonkeyPatch):
    import strands
    import strands.models
    import strands.multiagent
    from services import specialist_models

    _FakeBuilder.fail = False
    _FakeBuilder.latest = None
    _FakeAgent.scripts = {
        GRAPH.INVESTIGATOR_NODE: [("get_tickets", {}), ("get_orders", {}), ("get_return_policy", {"department": "Home"})],
        GRAPH.PLANNER_NODE: [("propose_store_credit", {"order_ids": [301, 302], "reason": "Two items went back, no credit recorded."})],
    }
    _FakeAgent.outputs = {
        GRAPH.INVESTIGATOR_NODE: INVESTIGATOR_BRIEF,
        GRAPH.PLANNER_NODE: "A $100.00 store credit is proposed for the robe and the diffuser; a person must approve it.",
    }
    monkeypatch.setattr(strands, "Agent", _FakeAgent)
    monkeypatch.setattr(strands.models, "BedrockModel", _FakeModel)
    monkeypatch.setattr(strands.multiagent, "GraphBuilder", _FakeBuilder)
    monkeypatch.setattr(specialist_models, "specialist_model", lambda _tier: ("model-test", 9999))
    yield


def _investigate(run: _Run, events: List[Dict[str, Any]]) -> GRAPH.InvestigationResult:
    return GRAPH.run_investigation(
        run=run, customer_id="CUST-JESSICA", customer_name="Jessica Nakamura",
        operator_sub="sub-nadia", turn_id="turn-" + "a" * 32, emit=events.append,
    )


def test_the_graph_has_two_ordered_nodes_and_bounded_tools(graph_runtime) -> None:
    events: List[Dict[str, Any]] = []
    _investigate(_Run(), events)

    builder = _FakeBuilder.latest
    assert builder is not None
    assert [node_id for _agent, node_id in builder.nodes] == [GRAPH.INVESTIGATOR_NODE, GRAPH.PLANNER_NODE]
    assert builder.edges == [(GRAPH.INVESTIGATOR_NODE, GRAPH.PLANNER_NODE)]
    assert builder.entry == GRAPH.INVESTIGATOR_NODE
    assert builder.max_executions == 2
    investigator, planner = (agent for agent, _ in builder.nodes)
    assert sorted(investigator.tools) == ["get_orders", "get_return_policy", "get_tickets"]
    assert sorted(planner.tools) == ["propose_store_credit"]
    assert investigator.kwargs["model"].kwargs["max_tokens"] == GRAPH._INVESTIGATOR_MAX_TOKENS
    assert "give_store_credit" not in investigator.tools and "give_store_credit" not in planner.tools


def test_the_investigator_reads_are_bound_to_the_case_customer(graph_runtime) -> None:
    run = _Run()
    _investigate(run, [])
    for sql, params in run.calls:
        if "FROM pellier.orders o" in sql or "FROM pellier.support_tickets" in sql:
            assert params[0] == "CUST-JESSICA", (sql, params)


def test_the_planner_proposes_the_paid_total_of_the_named_orders(graph_runtime) -> None:
    run = _Run()
    result = _investigate(run, [])

    assert result.status == "complete"
    assert result.proposal is not None
    assert result.proposal.amount_cents == 10000
    assert result.proposal.order_ids == [301, 302]
    assert result.proposal.review_id == 41
    assert result.proposal.idempotency_key.startswith("operator-review:41:")
    assert result.proposal.action_hash == write_request_hash(
        "give_store_credit", customer_id="CUST-JESSICA", amount_cents=10000,
        reason="Two items went back, no credit recorded.",
    )
    insert = run.reviews[0]["params"]
    assert insert[0] == "CUST-JESSICA"
    assert json.loads(insert[1]) == {"amount_cents": 10000, "customer_id": "CUST-JESSICA",
                                     "reason": "Two items went back, no credit recorded."}
    assert insert[2] == "turn-" + "a" * 32          # the investigation is the source turn
    assert insert[3] == 301                          # the order it refers to
    recommendation = json.loads(insert[5])
    assert recommendation["orderIds"] == [301, 302]
    assert insert[7] == "sub-nadia" and insert[8] == "operator"


def test_the_graph_stops_after_one_proposal(graph_runtime) -> None:
    _FakeAgent.scripts[GRAPH.PLANNER_NODE] = [
        ("propose_store_credit", {"order_ids": [301, 302], "reason": "Two items went back."}),
        ("propose_store_credit", {"order_ids": [303], "reason": "Second try."}),
    ]
    run = _Run()
    result = _investigate(run, [])
    assert len(run.reviews) == 1
    assert result.proposal is not None and result.proposal.amount_cents == 10000


def test_the_steps_stream_in_order_with_template_findings(graph_runtime) -> None:
    events: List[Dict[str, Any]] = []
    _investigate(_Run(), events)

    ids = [(e["id"], e["status"]) for e in events]
    assert ids[0] == (GRAPH.INVESTIGATOR_NODE, "running")
    assert ("get_tickets", "running") in ids and ("get_tickets", "done") in ids
    assert ids.index(("get_tickets", "done")) < ids.index(("get_orders", "running"))
    assert ids[-2:] == [(GRAPH.INVESTIGATOR_NODE, "done"), (GRAPH.PLANNER_NODE, "done")]
    by_id = {e["id"]: e for e in events if e["status"] == "done"}
    assert by_id["get_tickets"]["finding"] == "1 open ticket: Two items went back, no credit yet"
    assert by_id["get_orders"]["finding"] == "3 orders on file, $158.00 paid"
    assert by_id["get_return_policy"]["finding"] == "30-day returns for Home"
    assert by_id[GRAPH.INVESTIGATOR_NODE]["finding"] == "3 things the records show, 1 missing"
    assert by_id[GRAPH.PLANNER_NODE]["finding"] == "$100.00 credit proposed for 2 returned items, waiting for approval"
    assert by_id["get_orders"]["label"] == "Reading Jessica's orders"
    assert by_id[GRAPH.PLANNER_NODE]["tags"] == ["Planner", "Approval"]
    assert all(e["type"] == "step" for e in events)


def test_the_answer_carries_the_brief_and_the_proposal(graph_runtime) -> None:
    result = _investigate(_Run(), [])
    payload = result.as_payload()
    assert payload["investigation"]["facts"][0].startswith("Jessica ordered")
    assert payload["investigation"]["missing"] == ["No store credit is recorded for the two returned items."]
    assert payload["proposal"]["amount"] == "100.00" and payload["proposal"]["status"] == "pending"
    assert payload["graph"]["nodes"][0]["nodeId"] == GRAPH.INVESTIGATOR_NODE
    assert payload["graph"]["execution"] == "in-process"
    assert "approve" in payload["planner"]


def test_a_proposal_above_the_safety_ceiling_opens_no_review(graph_runtime) -> None:
    JESSICA_ORDERS.append({"order_id": 399, "product_id": "5", "name": "Watch", "brand": "Pellier",
                           "category": "Accessories", "quantity": 400, "amount_paid_cents": 14900, "placed_at": None})
    try:
        _FakeAgent.scripts[GRAPH.PLANNER_NODE] = [("propose_store_credit", {"order_ids": [399], "reason": "Over."})]
        run = _Run()
        result = _investigate(run, [])
        assert run.reviews == []
        assert result.proposal is None
    finally:
        JESSICA_ORDERS.pop()


def test_an_order_from_another_client_cannot_be_credited(graph_runtime) -> None:
    _FakeAgent.scripts[GRAPH.PLANNER_NODE] = [("propose_store_credit", {"order_ids": [9999], "reason": "Not hers."})]
    run = _Run()
    result = _investigate(run, [])
    assert run.reviews == [] and result.proposal is None


def test_a_graph_failure_is_a_failed_turn_with_no_proposal(graph_runtime) -> None:
    _FakeBuilder.fail = True
    events: List[Dict[str, Any]] = []
    result = _investigate(_Run(), events)
    assert result.status == "failed" and result.error == "RuntimeError"
    assert result.proposal is None
    assert [e["status"] for e in events[-2:]] == ["failed", "failed"]
