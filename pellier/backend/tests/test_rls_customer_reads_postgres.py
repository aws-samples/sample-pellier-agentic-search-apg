"""Row-level security guards the agent's own customer reads, on real PostgreSQL.

``get_orders`` and ``get_tickets`` read as ``pellier_agent`` with one customer
named. In process, that customer comes from the signed token. On the Gateway,
it is the customer Cedar's owner-only permit admitted. Either way Aurora returns
only that customer's rows, even if the tool's own SQL asks for someone else's.
The two binding places:

* in process, through ``DatabaseService.principal_session`` (the one place
  ``services/database.py`` binds it), reached by ``agent_tools``' customer runner;
* on the Gateway, through ``common.dataapi.run_as_customer`` (the one place the
  Lambda binds it), here with the RDS Data API answered by the same cluster.

The proof the brief asks for: with the application's own owner check switched
off, a read for Theo's orders while Jessica is the signed-in person returns no
rows. The counterfactual is in the suite too: switch the role binding to the
owner and the same read returns Theo's orders, so it is the binding that holds.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
from typing import Any, Dict, List

import psycopg
import pytest
import pytest_asyncio
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from services import agent_tools, store_tools
from services import database as database_module
from services.database import DatabaseService
from services.turn_identity import (
    authorized_customer_id_var,
    principal_sub_var,
    principal_username_var,
)
from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)
from tests.test_operator_credit_postgres import DEPLOY, _DataApiOnPostgres, _conninfo


@pytest_asyncio.fixture
async def live_db(fresh_db):
    """A real DatabaseService pool on the throwaway cluster, wired into the agent tools."""
    db = DatabaseService()
    db._pool = AsyncConnectionPool(
        conninfo=f"host={fresh_db.socket} port=5432 user=postgres dbname=postgres",
        kwargs={"row_factory": dict_row, "autocommit": False},
        min_size=1, max_size=2, open=False,
    )
    await db._pool.open()
    db._is_connected = True
    previous = (agent_tools._db_service, agent_tools._main_loop)
    agent_tools.set_db_service(db)
    agent_tools.set_main_loop(asyncio.get_running_loop())
    try:
        yield db
    finally:
        agent_tools._db_service, agent_tools._main_loop = previous
        await db._pool.close()


def _orders(payload: str) -> List[Dict[str, Any]]:
    return json.loads(payload)["orders"]


async def _get_orders_as(username: str, customer: str, requested: str) -> List[Dict[str, Any]]:
    """Run the agent's get_orders tool as a turn would: verified person bound, worker thread."""
    tokens = (
        principal_sub_var.set(f"sub-{username}"),
        principal_username_var.set(username),
        authorized_customer_id_var.set(customer),
    )
    try:
        fn = getattr(agent_tools.get_orders, "__wrapped__", agent_tools.get_orders)
        return _orders(await asyncio.to_thread(fn, customer_id=requested))
    finally:
        principal_sub_var.reset(tokens[0])
        principal_username_var.reset(tokens[1])
        authorized_customer_id_var.reset(tokens[2])


def _trust_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch off the application's owner check: whatever customer the model names is read."""
    def no_owner_check(customer_id: str = "", persona: str = "", *, tool: str = ""):
        return agent_tools._infer_customer_id(customer_id), None

    monkeypatch.setattr(agent_tools, "_verified_read_customer_scope", no_owner_check)


# ---------------------------------------------------------------------------
# In process
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signed_in_as_jessica_a_read_for_theo_returns_nothing(live_db, monkeypatch):
    _trust_the_model(monkeypatch)
    assert await _get_orders_as("jessica", "CUST-JESSICA", "CUST-THEO") == []
    # The positive control: her own orders, all five.
    own = await _get_orders_as("jessica", "CUST-JESSICA", "CUST-JESSICA")
    assert len(own) == 5 and {o["product_id"] for o in own} >= {"42", "25"}


@pytest.mark.asyncio
async def test_with_the_owner_check_on_the_mismatch_never_reaches_the_database(live_db):
    tokens = (principal_username_var.set("jessica"), authorized_customer_id_var.set("CUST-JESSICA"))
    try:
        fn = getattr(agent_tools.get_orders, "__wrapped__", agent_tools.get_orders)
        refused = json.loads(await asyncio.to_thread(fn, customer_id="CUST-THEO"))
    finally:
        principal_username_var.reset(tokens[0])
        authorized_customer_id_var.reset(tokens[1])
    assert refused["status"] == "customer_scope_mismatch"


@pytest.mark.asyncio
async def test_the_role_binding_is_what_contains_it(live_db, monkeypatch):
    """Counterfactual: run the same read as the owner, and Theo's orders come back."""
    _trust_the_model(monkeypatch)
    monkeypatch.setattr(database_module, "CUSTOMER_ROLE", "postgres")
    leaked = await _get_orders_as("jessica", "CUST-JESSICA", "CUST-THEO")
    assert len(leaked) == 4, "without the role, nothing stops the read"


@pytest.mark.asyncio
async def test_the_tickets_read_is_held_the_same_way(live_db, monkeypatch):
    _trust_the_model(monkeypatch)
    tokens = (principal_username_var.set("jessica"), authorized_customer_id_var.set("CUST-JESSICA"))
    try:
        fn = getattr(agent_tools.get_tickets, "__wrapped__", agent_tools.get_tickets)
        theos = json.loads(await asyncio.to_thread(fn, customer_id="CUST-THEO"))
        own = json.loads(await asyncio.to_thread(fn, customer_id="CUST-JESSICA"))
    finally:
        principal_username_var.reset(tokens[0])
        authorized_customer_id_var.reset(tokens[1])
    assert theos["tickets"] == []
    assert [t["ticket_id"] for t in own["tickets"]] == ["TKT-2026-3015"]


@pytest.mark.asyncio
async def test_the_investigators_reads_are_held_to_the_case_customer(live_db):
    """The Operator route reads a case's orders through the same binding."""
    rows = await live_db.fetch_all_as(
        "jessica", "SELECT DISTINCT customer_id FROM pellier.orders WHERE customer_id <> %s", ""
    )
    assert [r["customer_id"] for r in rows] == ["CUST-JESSICA"]


# ---------------------------------------------------------------------------
# On the Gateway, through the Lambda's one binding
# ---------------------------------------------------------------------------


@pytest.fixture
def dataapi_on_cluster(fresh_db, monkeypatch):
    import common.dataapi as dataapi

    conn = psycopg.connect(**_conninfo(fresh_db))
    monkeypatch.setattr(dataapi, "rds_client", _DataApiOnPostgres(conn))
    try:
        yield dataapi
    finally:
        conn.close()


def test_on_the_gateway_a_read_for_theo_bound_as_jessica_returns_nothing(dataapi_on_cluster):
    theos = dataapi_on_cluster.run_as_customer(
        "CUST-JESSICA", lambda run: store_tools.get_orders(run, customer_id="CUST-THEO")
    )
    assert theos["orders"] == []
    own = dataapi_on_cluster.run_as_customer(
        "CUST-THEO", lambda run: store_tools.get_orders(run, customer_id="CUST-THEO")
    )
    assert own["count"] == 4


def test_the_lambdas_ticket_read_binds_the_customer_it_carries(dataapi_on_cluster):
    spec = importlib.util.spec_from_file_location(
        "store_tools_lambda_rls", DEPLOY / "pellier_store_tools.py"
    )
    assert spec and spec.loader
    lambda_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lambda_module)

    def call(arguments: Dict[str, Any]) -> Dict[str, Any]:
        envelope = lambda_module.lambda_handler({"name": "get_tickets", "arguments": arguments}, None)
        return json.loads(envelope["text"])

    assert [t["ticket_id"] for t in call({"customer_id": "CUST-THEO"})["tickets"]] == [
        "TKT-2026-5021", "TKT-2026-1874",
    ]
    assert call({})["tickets"] == [], "no customer named, no rows"


def test_on_the_gateway_the_owner_would_have_read_theos_orders(dataapi_on_cluster, monkeypatch):
    """Counterfactual for the Lambda's binding: as the owner, the mismatched read leaks."""
    monkeypatch.setattr(dataapi_on_cluster, "CUSTOMER_ROLE", "postgres")
    leaked = dataapi_on_cluster.run_as_customer(
        "CUST-JESSICA", lambda run: store_tools.get_orders(run, customer_id="CUST-THEO")
    )
    assert leaked["count"] == 4


# ---------------------------------------------------------------------------
# Ask Pellier's opening read, through the real route
# ---------------------------------------------------------------------------

THEOS_ANSWER = "Last time you bought the Wabi-Sabi Bowl."


@pytest_asyncio.fixture
async def ask_pellier(live_db, monkeypatch):
    """POST /api/chat/stream on the real route and chat service, over the cluster.

    Only the model is replaced: a scripted agent that records the message it
    was given and answers by naming Theo's bowl, as a model using an order
    history in its context would. Returns ``post(user, body) -> (events, prompts)``.
    """
    import sys
    import types

    import httpx

    import app as app_module
    import services.chat as chat_module
    from services.chat import EnhancedChatService
    from tests.test_chat_stream_contract import ScriptedAgent

    prompts: List[str] = []

    class _RecordingAgent(ScriptedAgent):
        def __call__(self, prompt: str):
            prompts.append(prompt)
            return super().__call__(prompt)

    service = EnhancedChatService.__new__(EnhancedChatService)
    service.model_id = "test-model"
    service.strands_available = True
    service.db_service = live_db
    service._agent_stats = {
        "query_count": 0, "products_found": 0, "agent_calls_by_type": {},
        "total_response_time_ms": 0, "avg_response_time_ms": 0,
    }
    monkeypatch.setitem(
        sys.modules,
        "services.otel_trace_extractor",
        types.SimpleNamespace(extract_agent_execution_from_otel=lambda **kwargs: {}),
    )
    monkeypatch.setattr(chat_module, "classify_intent", lambda _m: "shopping")
    monkeypatch.setattr(
        chat_module, "_build_dispatcher_specialist",
        lambda *_a, **_k: _RecordingAgent([], THEOS_ANSWER),
    )
    monkeypatch.setattr(app_module.settings, "USE_AGENTCORE_RUNTIME", False, raising=False)
    monkeypatch.setattr(app_module, "chat_service", service)

    async def post(user: Any, body: Dict[str, Any]):
        prompts.clear()
        app_module.app.dependency_overrides[app_module.get_current_user] = lambda: user
        try:
            transport = httpx.ASGITransport(app=app_module.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://pellier") as client:
                response = await client.post("/api/chat/stream", json={
                    "message": "What did I order last time?",
                    "conversation_history": [],
                    "session_id": "sess-preamble",
                    **body,
                })
        finally:
            app_module.app.dependency_overrides.pop(app_module.get_current_user, None)
        assert response.status_code == 200
        events = [
            json.loads(line[len("data: "):])
            for line in response.text.splitlines() if line.startswith("data: ")
        ]
        return events, list(prompts)

    post.prompts = prompts
    return post


def _owned_cards(events: List[Dict[str, Any]]) -> List[str]:
    return [
        e["product"]["name"] for e in events
        if e.get("type") == "product" and e["product"].get("badge") == "From your orders"
    ]


@pytest.mark.asyncio
async def test_a_signed_out_turn_naming_theo_reads_nothing_about_him(ask_pellier):
    """The request body's customer_id is a persona choice, not an identity.

    Signed out, naming CUST-THEO must not put his preferences or orders in the
    model's context, report his profile, or send his orders back as cards.
    """
    events, prompts = await ask_pellier(None, {"customer_id": "CUST-THEO"})

    start = next(e for e in events if e.get("type") == "turn_start")
    assert start["principal"]["authenticated"] is False
    assert prompts and all("PERSONA CONTEXT" not in p for p in prompts)
    assert all("Wabi-Sabi Bowl" not in p for p in prompts)
    assert [e for e in events if e.get("type") == "aurora_profile_context"] == []
    assert _owned_cards(events) == []


@pytest.mark.asyncio
async def test_a_signed_in_turn_reads_its_own_orders_as_pellier_agent(ask_pellier):
    """The positive control: signed in as theo, the opening read finds his four orders."""
    user = {"sub": "sub-theo", "username": "Theo"}
    events, prompts = await ask_pellier(user, {"customer_id": "CUST-ANNA"})

    profile = next(e for e in events if e.get("type") == "aurora_profile_context")["profile"]
    assert profile["customer_id"] == "CUST-THEO" and profile["orders_available"] == 4
    assert prompts[0].startswith("PERSONA CONTEXT: Theo")
    assert "Wabi-Sabi Bowl" in prompts[0]
    assert _owned_cards(events) == ["Wabi-Sabi Bowl"]


@pytest.mark.asyncio
async def test_agent_chat_in_process_reads_the_signed_in_customers_own_orders(ask_pellier):
    """``/api/agent/chat`` in process binds the token's name, so Theo's own orders are read.

    Before cut 6b the route passed no name, so a signed-in customer's reads
    there returned nothing. Without the name the read still fails closed.
    """
    from services import agentcore_runtime as rt

    async def ask(username: Any) -> str:
        ask_pellier.prompts.clear()
        await rt.run_agent(
            message="What did I order last time?", session_id="sess-agent-chat",
            user_id="sub-theo", customer_id="CUST-THEO", principal_username=username,
        )
        return ask_pellier.prompts[0]

    assert "Wabi-Sabi Bowl" in await ask("theo")
    assert "Wabi-Sabi Bowl" not in await ask(None), "no name, no rows"
