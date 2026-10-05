"""``POST /api/operator/clients/{id}/investigate`` streams the graph's steps.

The graph is a stand-in that emits two steps and returns a proposal, so the
test covers the route's contract: SSE framing, the order of events, the
operator's subject reaching the graph, and the clean close on failure.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import operator as operator_module
from services import operator_graph as GRAPH

OPERATOR = {"sub": "sub-nadia", "username": "nadia", "groups": ("pellier-operators",)}


class _Db:
    async def fetch_one(self, query: str, *params: Any):
        if "FROM pellier.customers c" in query:
            return {"customer_id": params[0], "name": "Jessica Nakamura"} if params[0] == "CUST-JESSICA" else None
        return None

    async def fetch_all(self, query: str, *params: Any):
        return []


def _client(db: Any = None) -> TestClient:
    app = FastAPI()
    app.include_router(operator_module.router)
    app.dependency_overrides[operator_module.get_db_service] = lambda: db or _Db()
    app.dependency_overrides[operator_module.require_operator] = lambda: OPERATOR
    return TestClient(app)


def _frames(text: str) -> List[tuple[str, Dict[str, Any]]]:
    import json

    frames = []
    for frame in text.strip().split("\n\n"):
        kind, data = "", ""
        for line in frame.split("\n"):
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: "):
                data += line[6:]
        frames.append((kind, json.loads(data)))
    return frames


def _fake_graph(monkeypatch: pytest.MonkeyPatch, *, fail: bool = False) -> Dict[str, Any]:
    seen: Dict[str, Any] = {}

    def run_investigation(**kwargs: Any) -> GRAPH.InvestigationResult:
        seen.update(kwargs)
        emit = kwargs["emit"]
        emit(GRAPH.step_event(GRAPH.INVESTIGATOR_NODE, label="Investigator reads the case", status="running"))
        if fail:
            raise RuntimeError("boom")
        emit(GRAPH.step_event(GRAPH.INVESTIGATOR_NODE, label="Investigator reads the case",
                              status="done", finding="2 things the records show, 1 missing"))
        proposal = GRAPH.Proposal(
            review_id=41, amount_cents=10000, reason="Two items went back.", order_ids=[301, 302],
            action_hash="h" * 64, idempotency_key="operator-review:41:" + "h" * 32,
            customer_id="CUST-JESSICA",
        )
        return GRAPH.InvestigationResult(
            turn_id=kwargs["turn_id"], customer_id=kwargs["customer_id"], status="complete",
            facts=["Both went back."], missing=["No credit recorded."], planner="Approve it.",
            proposal=proposal, model_id="model-test",
        )

    monkeypatch.setattr(GRAPH, "run_investigation", run_investigation)
    return seen


def test_the_stream_sends_status_steps_answer_then_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _fake_graph(monkeypatch)
    response = _client().post("/api/operator/clients/CUST-JESSICA/investigate")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = _frames(response.text)
    assert [kind for kind, _ in frames] == ["status", "step", "step", "answer", "complete"]
    answer = frames[3][1]
    assert answer["proposal"]["reviewId"] == 41 and answer["proposal"]["amount"] == "100.00"
    assert answer["proposal"]["idempotencyKey"].startswith("operator-review:41:")
    assert answer["investigation"] == {"facts": ["Both went back."], "missing": ["No credit recorded."]}
    assert answer["turnId"].startswith("turn-")
    assert frames[4][1]["type"] == "complete"
    # The graph ran as the verified staff member, for the client in the path.
    assert seen["operator_sub"] == "sub-nadia"
    assert seen["customer_id"] == "CUST-JESSICA"
    assert seen["customer_name"] == "Jessica Nakamura"


@pytest.mark.parametrize("fail", [False, True])
def test_the_steps_keep_their_place_when_the_graph_finishes_before_it_is_awaited(
    monkeypatch: pytest.MonkeyPatch, fail: bool
) -> None:
    """A graph that is already done when the route looks must not lose its steps.

    The stand-in ``to_thread`` returns only after the graph has run, which is
    what Python 3.14 produced for a fast graph about four runs in five: the
    route resumed without yielding to the loop, and its answer and end of
    stream overtook the steps still waiting to be delivered.
    """
    import asyncio

    async def already_finished(func: Any, /, *args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    _fake_graph(monkeypatch, fail=fail)
    monkeypatch.setattr(asyncio, "to_thread", already_finished)
    response = _client().post("/api/operator/clients/CUST-JESSICA/investigate")

    expected = ["status", "step", "error"] if fail else ["status", "step", "step", "answer", "complete"]
    assert [kind for kind, _ in _frames(response.text)] == expected


def test_an_unknown_client_is_a_404_before_any_model_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _fake_graph(monkeypatch)
    response = _client().post("/api/operator/clients/CUST-NOBODY/investigate")
    assert response.status_code == 404
    assert seen == {}


def test_a_failed_graph_closes_the_stream_with_an_error_event(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_graph(monkeypatch, fail=True)
    response = _client().post("/api/operator/clients/CUST-JESSICA/investigate")
    frames = _frames(response.text)
    assert [kind for kind, _ in frames] == ["status", "step", "error"]
    assert frames[-1][1]["detail"] == "investigation_failed"


def test_the_investigate_route_is_gated_like_every_desk_route() -> None:
    from services.auth import require_operator

    route = next(r for r in operator_module.router.routes if r.path.endswith("/investigate"))
    assert any(dep.call is require_operator for dep in route.dependant.dependencies)


def test_the_investigators_customer_reads_are_bound_to_the_clients_username(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The route hands the graph a customer runner that reads as pellier_agent.

    The runner must go through ``fetch_all_as`` with the client's own sign-in
    name, so row-level security holds the Investigator's get_orders and
    get_tickets to the case customer. A runner on plain ``fetch_all`` would
    read as the owner and contain nothing.
    """
    calls: List[tuple] = []

    class _BindingDb(_Db):
        async def fetch_one(self, query: str, *params: Any):
            if "FROM pellier.customers c" in query and params[0] == "CUST-THEO":
                return {"customer_id": "CUST-THEO", "name": "Theo Okafor", "cognito_username": "theo"}
            return None

        async def fetch_all(self, query: str, *params: Any):
            calls.append(("owner", None, query, params))
            return []

        async def fetch_all_as(self, username: Any, query: str, *params: Any):
            calls.append(("pellier_agent", username, query, params))
            return [{"order_id": 13}]

    orders_sql = "SELECT id FROM pellier.orders WHERE customer_id = %s"

    def run_investigation(**kwargs: Any) -> GRAPH.InvestigationResult:
        rows = kwargs["run_customer"](orders_sql, ("CUST-THEO",))
        assert rows == [{"order_id": 13}]
        return GRAPH.InvestigationResult(
            turn_id=kwargs["turn_id"], customer_id=kwargs["customer_id"], status="complete",
            facts=[], missing=[], planner="", proposal=None, model_id="model-test",
        )

    monkeypatch.setattr(GRAPH, "run_investigation", run_investigation)
    response = _client(_BindingDb()).post("/api/operator/clients/CUST-THEO/investigate")

    assert response.status_code == 200
    assert [kind for kind, _ in _frames(response.text)][-1] == "complete"
    assert calls == [("pellier_agent", "theo", orders_sql, ("CUST-THEO",))]
