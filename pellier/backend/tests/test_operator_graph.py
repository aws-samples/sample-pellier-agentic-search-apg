"""The Operator's two-node Strands graph: Investigator, then Planner.

The graph is built with the real ``GraphBuilder`` API but a fake builder and
fake agents stand in for Strands and Bedrock, so no model is called. The tools
are the real closures over a recording ``run`` stand-in, so the amount the
Planner proposes is computed from real order rows and the review it opens is
the real INSERT. The stand-in honours the two things the database decides
here: which orders have a received return, and that one live review (pending
or approved) exists per exact credit.
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
     "category": "Home", "quantity": 1, "amount_paid_cents": 6400, "placed_at": None,
     "return_status": "received", "store_credit_id": None},
    {"order_id": 302, "product_id": "25", "name": "Reed Diffuser", "brand": "Pellier",
     "category": "Home", "quantity": 1, "amount_paid_cents": 3600, "placed_at": None,
     "return_status": "received", "store_credit_id": None},
    {"order_id": 303, "product_id": "31", "name": "Stoneware Pour-Over Set", "brand": "Pellier",
     "category": "Home", "quantity": 1, "amount_paid_cents": 5800, "placed_at": None,
     "return_status": None, "store_credit_id": None},
]

JESSICA_REASON = (
    "Store credit for 2 returned items: Waffle Bath Robe, Sage (order 301); "
    "Reed Diffuser (order 302)."
)


class _Run:
    """Jessica's records, the live reviews, and every statement the graph issued."""

    def __init__(
        self,
        orders: List[Dict[str, Any]] | None = None,
        credits: List[Dict[str, Any]] | None = None,
    ) -> None:
        self.orders = [dict(o) for o in (orders if orders is not None else JESSICA_ORDERS)]
        self.credits = [dict(c) for c in (credits or [])]
        self.calls: List[tuple[str, tuple[Any, ...]]] = []
        # Statements that ran as pellier_agent with the customer named.
        self.scoped_calls: List[tuple[str, tuple[Any, ...]]] = []
        self.reviews: List[Dict[str, Any]] = []
        # (customer, action_hash) -> the review row: the partial unique index.
        self.live: Dict[tuple[str, str], Dict[str, Any]] = {}
        # The parameters of each UPDATE that answered the open credit requests.
        self.answered: List[tuple[Any, ...]] = []

    def _decide(self, review_id: int, status: str) -> None:
        for review in self.live.values():
            if review["id"] == review_id:
                review["status"] = status

    def approve(self, review_id: int) -> None:
        self._decide(review_id, "approved")

    def decline(self, review_id: int) -> None:
        self._decide(review_id, "rejected")

    def __call__(self, sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        self.calls.append((sql, tuple(params)))
        if "FROM pellier.orders o" in sql and "o.return_status = %s" in sql:
            return [dict(o) for o in self.orders if o["return_status"] == params[1]]
        if "FROM pellier.orders o" in sql:
            return [dict(o) for o in self.orders]
        if "FROM pellier.support_tickets" in sql:
            return [{"ticket_id": "TKT-2026-3015", "subject": "Two items went back, no credit yet",
                     "status": "open", "channel": "chat", "last_note": "Both were received.",
                     "opened_at": None, "resolved_at": None}]
        if "FROM pellier.return_policies" in sql:
            return [{"category_name": "Home", "return_window_days": 30,
                     "conditions": "Unused", "refund_method": "original payment"}]
        if "FROM pellier.store_credits" in sql:
            return [dict(c) for c in self.credits][: params[1]]
        if "INSERT INTO pellier.approvals" in sql:
            assert "WHERE status IN ('pending', 'approved')" in sql
            key = (params[0], params[6])
            if key in self.live and self.live[key]["status"] in ("pending", "approved"):
                return []
            self.live[key] = {
                "id": 41 + len(self.reviews), "status": "pending", "customer_id": params[0],
                "args": params[1], "action_hash": params[6], "order_ids": list(params[3]),
                "recommendation": params[5],
            }
            self.reviews.append({"params": params})
            return [{"id": self.live[key]["id"], "status": "pending"}]
        if "UPDATE pellier.approvals" in sql:
            assert "tool = 'store_credit_request'" in sql
            self.answered.append(tuple(params))
            return []
        if "FROM pellier.approvals" in sql and "action_hash = %s" in sql:
            review = self.live.get((params[0], params[1]))
            live = review and review["status"] in ("pending", "approved")
            return [{"id": review["id"], "status": review["status"]}] if live else []
        if "FROM pellier.approvals" in sql:
            assert "status IN ('pending', 'approved')" in sql
            rows = [dict(r) for r in self.live.values()
                    if r["customer_id"] == params[0] and r["status"] in ("pending", "approved")]
            return sorted(rows, key=lambda r: -r["id"])
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
        GRAPH.INVESTIGATOR_NODE: [
            ("get_tickets", {}), ("get_orders", {}), ("get_store_credits", {}),
            ("get_return_policy", {"department": "Home"}),
        ],
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
    def run_customer(sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        run.scoped_calls.append((sql, tuple(params)))
        return run(sql, params)

    return GRAPH.run_investigation(
        run=run, run_customer=run_customer, customer_id="CUST-JESSICA",
        customer_name="Jessica Nakamura",
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
    assert sorted(investigator.tools) == [
        "get_orders", "get_return_policy", "get_store_credits", "get_tickets",
    ]
    assert sorted(planner.tools) == ["propose_store_credit"]
    assert investigator.kwargs["model"].kwargs["max_tokens"] == GRAPH._INVESTIGATOR_MAX_TOKENS
    assert "give_store_credit" not in investigator.tools and "give_store_credit" not in planner.tools


def test_the_investigator_reads_are_bound_to_the_case_customer(graph_runtime) -> None:
    run = _Run()
    _investigate(run, [])
    reads = ("FROM pellier.orders o", "FROM pellier.support_tickets", "FROM pellier.store_credits")
    seen = set()
    for sql, params in run.calls:
        for table in reads:
            if table in sql:
                seen.add(table)
                assert params[0] == "CUST-JESSICA", (sql, params)
    assert seen == set(reads)


def test_the_investigators_order_and_ticket_reads_run_under_row_level_security(
    graph_runtime,
) -> None:
    """get_orders and get_tickets read through the customer-scoped runner."""
    run = _Run()
    _investigate(run, [])
    scoped = [sql for sql, _params in run.scoped_calls]
    assert any("FROM pellier.support_tickets" in sql for sql in scoped)
    assert any("FROM pellier.orders o" in sql and "LIMIT %s" in sql for sql in scoped)
    # The Planner's own read of the returns is a staff read, not the customer's.
    assert not any("o.return_status = %s" in sql for sql in scoped)


def test_the_investigator_reads_the_recorded_credits_bounded(graph_runtime) -> None:
    """After payment, a re-investigation's own read says the credit is recorded."""
    _FakeAgent.scripts[GRAPH.INVESTIGATOR_NODE] = [("get_store_credits", {"limit": 500})]
    _FakeAgent.scripts[GRAPH.PLANNER_NODE] = []
    credit = {"amount_cents": 10000, "reason": JESSICA_REASON, "created_at": "2026-10-04T18:00:00"}
    run = _Run(credits=[credit])
    events: List[Dict[str, Any]] = []
    _investigate(run, events)
    (sql, params), = [(s, p) for s, p in run.calls if "FROM pellier.store_credits" in s]
    assert params == ("CUST-JESSICA", GRAPH._MAX_CREDITS), "the model's limit is bounded"
    done = [e for e in events if e["id"] == "get_store_credits" and e["status"] == "done"]
    assert done[0]["finding"] == "1 store credit recorded, $100.00"
    assert done[0]["label"] == "Reading Jessica's store credits"
    assert "get_store_credits" in GRAPH._INVESTIGATOR_PROMPT
    assert GRAPH.read_store_credits(_Run(), customer_id="CUST-JESSICA")["count"] == 0


def test_the_planner_proposes_the_received_returns_with_a_reason_from_the_records(
    graph_runtime,
) -> None:
    run = _Run()
    result = _investigate(run, [])

    assert result.status == "complete"
    assert result.proposal is not None
    assert result.proposal.amount_cents == 10000
    assert result.proposal.order_ids == [301, 302]
    assert result.proposal.review_id == 41
    assert result.proposal.reason == JESSICA_REASON
    key = f"operator-review:41:{result.proposal.action_hash[:32]}"
    assert result.proposal.idempotency_key == key
    assert result.proposal.action_hash == write_request_hash(
        "give_store_credit", customer_id="CUST-JESSICA", amount_cents=10000, reason=JESSICA_REASON,
    )
    insert = run.reviews[0]["params"]
    assert insert[0] == "CUST-JESSICA"
    assert json.loads(insert[1]) == {"amount_cents": 10000, "customer_id": "CUST-JESSICA",
                                     "reason": JESSICA_REASON}
    assert insert[2] == "turn-" + "a" * 32          # the investigation is the source turn
    assert insert[3] == [301, 302]                   # the orders the credit covers
    planner_sentence = "Two items went back, no credit recorded."
    assert insert[4] == planner_sentence             # the Planner's words are the rationale
    recommendation = json.loads(insert[5])
    assert "orderIds" not in recommendation, "order_ids is a column, not desk data"
    assert recommendation["rationale"] == planner_sentence
    assert insert[7] == "sub-nadia" and insert[8] == "operator"


@pytest.mark.parametrize(
    "named",
    [[301], [302], [301, 302, 303], [302, 303, 9999], ["301", 302], [301, 301]],
    ids=["subset", "other-subset", "extra-unreturned", "extra-foreign", "strings", "repeated"],
)
def test_the_amount_is_10000_whatever_orders_the_planner_names(graph_runtime, named) -> None:
    """The records decide the credit; the model only has to point at one returned order."""
    _FakeAgent.scripts[GRAPH.PLANNER_NODE] = [
        ("propose_store_credit", {"order_ids": named, "reason": "Items went back."}),
    ]
    run = _Run()
    result = _investigate(run, [])
    assert result.proposal is not None, named
    assert result.proposal.amount_cents == 10000 and result.proposal.order_ids == [301, 302]
    assert result.proposal.reason == JESSICA_REASON


@pytest.mark.parametrize("named", [[303], [9999], [303, 9999], []])
def test_naming_no_returned_order_proposes_nothing(graph_runtime, named) -> None:
    _FakeAgent.scripts[GRAPH.PLANNER_NODE] = [
        ("propose_store_credit", {"order_ids": named, "reason": "Credit these."}),
    ]
    run = _Run()
    result = _investigate(run, [])
    assert run.reviews == [] and result.proposal is None, named


@pytest.mark.parametrize("status", ["requested", "refunded", None])
def test_a_return_request_is_not_evidence_of_receipt(graph_runtime, status) -> None:
    """Only a received return is credited: a request is a claim, and a refund was paid back."""
    orders = [dict(o) for o in JESSICA_ORDERS]
    orders[2]["return_status"] = status
    run = _Run(orders)
    result = _investigate(run, [])
    assert result.proposal is not None and result.proposal.amount_cents == 10000
    assert result.proposal.order_ids == [301, 302]


def test_no_received_return_means_no_proposal(graph_runtime) -> None:
    orders = [{**o, "return_status": None} for o in JESSICA_ORDERS]
    run = _Run(orders)
    result = _investigate(run, [])
    assert run.reviews == [] and result.proposal is None


def test_two_investigations_in_different_words_resolve_to_one_review(graph_runtime) -> None:
    """The fingerprint is the case's, not the model's, so a rerun cannot open a twin."""
    run = _Run()
    first = _investigate(run, [])
    _FakeAgent.scripts[GRAPH.PLANNER_NODE] = [
        ("propose_store_credit",
         {"order_ids": [302, 303], "reason": "The robe and diffuser came back."}),
    ]
    second = _investigate(run, [])
    assert first.proposal is not None and second.proposal is not None
    assert len(run.reviews) == 1, "a second investigation opened a second review"
    assert second.proposal.review_id == first.proposal.review_id
    assert second.proposal.action_hash == first.proposal.action_hash
    assert second.proposal.idempotency_key == first.proposal.idempotency_key


def test_an_approved_case_investigated_again_opens_no_second_review(graph_runtime) -> None:
    """Re-investigating a case a person approved resolves to that review and its one key."""
    run = _Run()
    first = _investigate(run, [])
    assert first.proposal is not None
    run.approve(first.proposal.review_id)

    events: List[Dict[str, Any]] = []
    second = _investigate(run, events)

    assert len(run.reviews) == 1, "an approved case opened a second review"
    assert second.proposal is not None
    assert second.proposal.review_id == first.proposal.review_id
    assert second.proposal.status == "approved"
    assert second.as_payload()["proposal"]["status"] == "approved"
    assert second.proposal.idempotency_key == first.proposal.idempotency_key
    planner = [e for e in events if e["id"] == GRAPH.PLANNER_NODE and e["status"] == "done"][-1]
    assert planner["finding"] == (
        "$100.00 credit already approved in review 41; no second review opened"
    )


def test_a_later_returned_item_gets_a_review_of_its_own(graph_runtime) -> None:
    """Credited items stay covered; a genuinely new return is proposed alone."""
    run = _Run()
    first = _investigate(run, [])
    assert first.proposal is not None
    run.approve(first.proposal.review_id)
    run.orders[2]["return_status"] = "received"

    _FakeAgent.scripts[GRAPH.PLANNER_NODE] = [
        ("propose_store_credit", {"order_ids": [301, 302, 303], "reason": "A third item came back."}),
    ]
    second = _investigate(run, [])
    assert second.proposal is not None
    assert second.proposal.review_id != first.proposal.review_id and len(run.reviews) == 2
    assert second.proposal.order_ids == [303] and second.proposal.amount_cents == 5800
    assert second.proposal.reason == (
        "Store credit for 1 returned item: Stoneware Pour-Over Set (order 303)."
    )


def test_a_declined_review_releases_its_items(graph_runtime) -> None:
    run = _Run()
    first = _investigate(run, [])
    assert first.proposal is not None
    run.decline(first.proposal.review_id)
    second = _investigate(run, [])
    assert second.proposal is not None and second.proposal.review_id != first.proposal.review_id
    assert second.proposal.order_ids == [301, 302] and second.proposal.amount_cents == 10000


def test_an_investigation_answers_the_open_credit_requests(graph_runtime) -> None:
    run = _Run()
    result = _investigate(run, [])
    assert result.proposal is not None
    assert run.answered == [("turn-" + "a" * 32, result.proposal.review_id, "CUST-JESSICA")]


def test_an_investigation_with_no_proposal_answers_them_with_no_review(graph_runtime) -> None:
    run = _Run([{**o, "return_status": None} for o in JESSICA_ORDERS])
    result = _investigate(run, [])
    assert result.proposal is None
    assert run.answered == [("turn-" + "a" * 32, None, "CUST-JESSICA")]


def test_a_planner_that_reads_the_brief_and_proposes_nothing_answers_them(graph_runtime) -> None:
    """A deliberate no-credit outcome is a finding: "call nothing and say why"."""
    _FakeAgent.scripts[GRAPH.PLANNER_NODE] = []
    run = _Run()
    result = _investigate(run, [])
    assert result.proposal is None
    assert run.answered == [("turn-" + "a" * 32, None, "CUST-JESSICA")]


@pytest.mark.parametrize("order_ids", [[9999], [399]], ids=["refused", "over-ceiling"])
def test_a_failed_proposal_leaves_the_requests_open(graph_runtime, order_ids) -> None:
    orders = JESSICA_ORDERS + [{
        "order_id": 399, "product_id": "5", "name": "Watch", "brand": "Pellier",
        "category": "Accessories", "quantity": 400, "amount_paid_cents": 14900,
        "placed_at": None, "return_status": "received", "store_credit_id": None,
    }]
    _FakeAgent.scripts[GRAPH.PLANNER_NODE] = [
        ("propose_store_credit", {"order_ids": order_ids, "reason": "Credit these."}),
    ]
    run = _Run(orders if order_ids == [399] else None)
    result = _investigate(run, [])
    assert result.status == "complete" and result.proposal is None
    assert run.answered == [], "no proposal and no finding: the request stays open"


def test_an_investigation_with_no_brief_leaves_the_requests_open(graph_runtime) -> None:
    _FakeAgent.outputs[GRAPH.INVESTIGATOR_NODE] = "I could not read the records."
    _FakeAgent.scripts[GRAPH.PLANNER_NODE] = []
    run = _Run()
    result = _investigate(run, [])
    assert result.facts == [] and result.proposal is None
    assert run.answered == []


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
    assert by_id["get_orders"]["finding"] == "3 orders on file, $158.00 paid, 2 returned"
    assert by_id["get_return_policy"]["finding"] == "30-day returns for Home"
    assert by_id["get_store_credits"]["finding"] == "No store credit recorded"
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
    orders = JESSICA_ORDERS + [{
        "order_id": 399, "product_id": "5", "name": "Watch", "brand": "Pellier",
        "category": "Accessories", "quantity": 400, "amount_paid_cents": 14900,
        "placed_at": None, "return_status": "received", "store_credit_id": None,
    }]
    _FakeAgent.scripts[GRAPH.PLANNER_NODE] = [
        ("propose_store_credit", {"order_ids": [399], "reason": "Over."}),
    ]
    run = _Run(orders)
    result = _investigate(run, [])
    assert run.reviews == []
    assert result.proposal is None


def test_an_order_from_another_client_cannot_be_credited(graph_runtime) -> None:
    _FakeAgent.scripts[GRAPH.PLANNER_NODE] = [("propose_store_credit", {"order_ids": [9999], "reason": "Not hers."})]
    run = _Run()
    result = _investigate(run, [])
    assert run.reviews == [] and result.proposal is None


def test_a_graph_failure_is_a_failed_turn_with_no_proposal(graph_runtime) -> None:
    _FakeBuilder.fail = True
    events: List[Dict[str, Any]] = []
    run = _Run()
    result = _investigate(run, events)
    assert result.status == "failed" and result.error == "RuntimeError"
    assert result.proposal is None
    assert run.answered == [], "a failed investigation answers no request"
    assert [e["status"] for e in events[-2:]] == ["failed", "failed"]
