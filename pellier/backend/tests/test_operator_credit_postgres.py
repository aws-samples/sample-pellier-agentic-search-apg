"""Jessica's credit on real PostgreSQL: one approval is one key is one credit, on both rails.

Her own chat request opens a credit request with no amount, which nobody can
approve; the Planner's records-built review is the only approvable credit, and
a live review keeps the returned orders it covers.

Fakes cannot prove the parts the database decides: that the partial unique
index ``approvals_one_live_review`` keeps one live review per exact credit,
that the ``ON CONFLICT`` target infers it, that ``apply_store_credit`` admits
only the approved review's key, replays it, and never credits an order twice.
This module builds the real schema and seed on a throwaway cluster
(``tests/fresh_cluster.py``) and drives the real code against them.

The two rails:

* in process: ``governed_execution`` on an async psycopg connection, through
  the shared ``store_tools.give_store_credit``;
* the Gateway: the store-tools Lambda's ``lambda_handler``, whose RDS Data API
  client is replaced by a stand-in that executes each statement on the same
  cluster. Cedar is not evaluated here (the call stands in for an ALLOW), so
  what this proves is the tool's own guard, not the policy.

No test reaches AWS or Bedrock: the Investigator's model is not run, the
Planner's tool (``operator_graph.propose_credit``) is called directly.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List

import psycopg
import pytest
from psycopg.rows import dict_row

from routes import operator as OP
from services import governed_execution as ge
from services import operator_graph
from services import operator_review as rv
from services.turn_identity import new_turn_id
from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

DEPLOY = Path(__file__).resolve().parents[3] / "scripts" / "deploy"
if str(DEPLOY) not in sys.path:
    sys.path.insert(0, str(DEPLOY))

NADIA_SUB = "sub-nadia"
ENFORCED = ge.PolicyEngineState(gateway_mode="ENFORCE")
JESSICA = "CUST-JESSICA"


# ---------------------------------------------------------------------------
# Connections to the throwaway cluster
# ---------------------------------------------------------------------------


def _conninfo(cluster: Any) -> Dict[str, Any]:
    return {"host": str(cluster.socket), "port": 5432, "user": "postgres", "dbname": "postgres",
            "autocommit": True, "row_factory": dict_row}


def _rows(cur: Any) -> List[Dict[str, Any]]:
    return [dict(row) for row in cur.fetchall()] if cur.description else []


class _PgDb:
    """The ``DatabaseService`` surface the Operator code uses, on one async connection."""

    def __init__(self, conn: psycopg.AsyncConnection) -> None:
        self.conn = conn

    async def fetch_all(self, sql: str, *params: Any) -> List[Dict[str, Any]]:
        async with self.conn.cursor() as cur:
            await cur.execute(sql, params)
            return [dict(row) for row in await cur.fetchall()] if cur.description else []

    async def fetch_one(self, sql: str, *params: Any) -> Dict[str, Any] | None:
        async with self.conn.cursor() as cur:
            await cur.execute(sql, params)
            row = await cur.fetchone() if cur.description else None
            return dict(row) if row else None

    @asynccontextmanager
    async def get_connection(self):
        yield self.conn


def _sync_run(conn: psycopg.Connection) -> Callable[[str, Any], List[Dict[str, Any]]]:
    def run(sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return _rows(cur)

    return run


def _scalar(conn: psycopg.Connection, sql: str, *params: Any) -> Any:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return next(iter(row.values())) if row else None


# ---------------------------------------------------------------------------
# The RDS Data API, answered by the cluster
# ---------------------------------------------------------------------------

_NAMED = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


def _from_field(field: Dict[str, Any]) -> Any:
    if field.get("isNull"):
        return None
    for kind in ("stringValue", "longValue", "doubleValue", "booleanValue"):
        if kind in field:
            return field[kind]
    if "arrayValue" in field:
        raise AssertionError("ValidationException: Array parameters are not supported")
    raise AssertionError(f"unhandled Data API parameter {field}")


def _to_field(value: Any) -> Dict[str, Any]:
    if value is None:
        return {"isNull": True}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"longValue": value}
    if isinstance(value, (dict, list)):
        return {"stringValue": json.dumps(value, default=str)}
    if isinstance(value, (datetime, date)):
        return {"stringValue": value.isoformat()}
    if isinstance(value, (float, Decimal)):
        return {"stringValue": str(value)}
    return {"stringValue": str(value)}


class _DataApiOnPostgres:
    """``rds_client`` with named ``:params`` and transactions, run on the cluster.

    The connection is autocommit, so a Data API transaction is an explicit
    ``BEGIN`` ... ``COMMIT`` on it: statements carrying the ``transactionId``
    share it, exactly as the service shares one server-side transaction.
    """

    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn
        self.transactions = 0

    def begin_transaction(self, **_kwargs: Any) -> Dict[str, Any]:
        self.transactions += 1
        self.conn.execute("BEGIN")
        return {"transactionId": f"tx-{self.transactions}"}

    def commit_transaction(self, **_kwargs: Any) -> Dict[str, Any]:
        self.conn.execute("COMMIT")
        return {}

    def rollback_transaction(self, **_kwargs: Any) -> Dict[str, Any]:
        self.conn.execute("ROLLBACK")
        return {}

    def execute_statement(self, **kwargs: Any) -> Dict[str, Any]:
        values = {p["name"]: _from_field(p["value"]) for p in kwargs.get("parameters") or []}
        with self.conn.cursor() as cur:
            cur.execute(_NAMED.sub(r"%(\1)s", kwargs["sql"]), values)
            if cur.description is None:
                return {}
            columns = [column.name for column in cur.description]
            records = [[_to_field(row[name]) for name in columns] for row in cur.fetchall()]
        return {"columnMetadata": [{"name": name} for name in columns], "records": records}


def _lambda(monkeypatch: pytest.MonkeyPatch, conn: psycopg.Connection) -> ModuleType:
    import common.dataapi as dataapi

    monkeypatch.setattr(dataapi, "rds_client", _DataApiOnPostgres(conn))
    spec = importlib.util.spec_from_file_location(
        "store_tools_lambda_on_postgres", DEPLOY / "pellier_store_tools.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _call_lambda(
    module: ModuleType, arguments: Dict[str, Any], tool: str = "give_store_credit",
) -> Dict[str, Any]:
    envelope = module.lambda_handler({"name": tool, "arguments": arguments}, None)
    return json.loads(envelope["text"])


# ---------------------------------------------------------------------------
# The case, the decision and the two rails
# ---------------------------------------------------------------------------


def _clean_case(conn: psycopg.Connection) -> None:
    """Every review, credit and audit row gone; the seeded orders and their returns stay.

    ``orders.store_credit_id`` references ``store_credits``, so the credits are
    deleted rather than truncated (a TRUNCATE would have to empty the orders
    too), and ``tool_audit`` is truncated because its trigger refuses DELETE.
    """
    with conn.cursor() as cur:
        cur.execute("UPDATE pellier.orders SET store_credit_id = NULL")
        cur.execute("DELETE FROM pellier.store_credits")
        cur.execute("DELETE FROM pellier.approvals")
        cur.execute("TRUNCATE pellier.tool_audit")
        cur.execute("UPDATE pellier.orders SET return_status = NULL "
                    "WHERE customer_id = %s AND product_id NOT IN ('42', '25')", (JESSICA,))


def _customer_run(
    conn: psycopg.Connection, username: str
) -> Callable[[str, Any], List[Dict[str, Any]]]:
    """A customer's read as the app runs it: pellier_agent, the name bound, one transaction."""
    def run(sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SET LOCAL ROLE pellier_agent")
                cur.execute("SELECT set_config('pellier.principal_username', %s, true)", (username,))
                cur.execute(sql, params)
                return _rows(cur)

    return run


def _order_id(conn: psycopg.Connection, product_id: str) -> int:
    return int(_scalar(
        conn, "SELECT id FROM pellier.orders WHERE customer_id = %s AND product_id = %s",
        JESSICA, product_id,
    ))


def _investigate(conn: psycopg.Connection, order_ids: List[int], sentence: str) -> Dict[str, Any]:
    """The Planner's one tool, as the graph calls it, on a fresh investigation.

    Then what the graph does once it completes: answer the open credit requests.
    """
    case = operator_graph._Case(
        run=_sync_run(conn), run_customer=_customer_run(conn, "jessica"),
        customer_id=JESSICA, customer_name="Jessica Nakamura",
        operator_sub=NADIA_SUB, turn_id=new_turn_id(), emit=lambda _event: None,
    )
    result = operator_graph.propose_credit(case, order_ids=order_ids, reason=sentence)
    operator_graph.answer_open_requests(case)
    return result


def _ask_for_credit(conn: psycopg.Connection, rail: str, module: ModuleType) -> Dict[str, Any]:
    """Jessica asks in chat for a store credit, on the rail under test."""
    sentence = "Jessica sent two items back and asks for a store credit."
    if rail == "in-process":
        from services import store_tools

        return store_tools.ask_a_person(
            _sync_run(conn), reason=sentence, customer_id=JESSICA, credit_request=True,
            source_turn_id=new_turn_id(), requested_by_sub="sub-jessica", requester_kind="shopper",
        )
    return _call_lambda(
        module, {"reason": sentence, "customer_id": JESSICA, "credit_request": True},
        tool="ask_a_person",
    )


def _requests(conn: psycopg.Connection) -> List[Dict[str, Any]]:
    return _rows_of(conn, "SELECT id, args, action_hash, status, answered_turn_id, answered_by_review_id "
                          "FROM pellier.approvals WHERE customer_id = %s "
                          "AND tool = 'store_credit_request' ORDER BY id", JESSICA)


def _count(conn: psycopg.Connection, sql: str, *params: Any) -> int:
    return int(_scalar(conn, sql, *params))


def _reviews(conn: psycopg.Connection) -> int:
    return _count(conn, "SELECT count(*) FROM pellier.approvals "
                        "WHERE customer_id = %s AND tool = 'give_store_credit'", JESSICA)


def _credits(conn: psycopg.Connection, key: str | None = None) -> int:
    if key is None:
        return _count(conn, "SELECT count(*) FROM pellier.store_credits WHERE customer_id = %s",
                      JESSICA)
    return _count(conn, "SELECT count(*) FROM pellier.store_credits WHERE idempotency_key = %s",
                  key)


def _set_rail(monkeypatch: pytest.MonkeyPatch, rail: str, module: ModuleType) -> None:
    from config import settings

    if rail == "in-process":
        monkeypatch.setattr(settings, "WORKSHOP_FORMAT", "builders", raising=False)
        monkeypatch.setattr(settings, "AGENTCORE_GATEWAY_URL", "", raising=False)
        return
    monkeypatch.setattr(settings, "WORKSHOP_FORMAT", "governed", raising=False)
    monkeypatch.setattr(settings, "AGENTCORE_GATEWAY_URL", "https://gw.example", raising=False)
    monkeypatch.setattr(settings, "AGENTCORE_POLICY_ENGINE_ID", "engine-1", raising=False)

    async def through_the_lambda(*, tool: str, args: Any, idempotency_key: str, access_token: str):
        result = _call_lambda(module, {**dict(args), "idempotency_key": idempotency_key})
        note = "Cedar is not evaluated here; the call stands in for an ALLOW."
        return ge.POLICY_ALLOW, result, note

    monkeypatch.setattr(ge, "_execute_through_gateway", through_the_lambda)


async def _execute(db: _PgDb, review_id: int) -> ge.ExecutionOutcome:
    """What ``POST /reviews/{id}/execute`` does once the route has a verified staff member."""
    row = await rv.get_review(db, review_id)
    assert row is not None
    return await ge.execute_confirmed_review(
        db, row, operator_sub=NADIA_SUB, access_token="jwt", engine_state=ENFORCED,
    )


async def _fresh_key_attempt(
    db: _PgDb, rail: str, module: ModuleType, review_id: int, key: str,
) -> Dict[str, Any]:
    """The approved arguments, read off the review, under a key the caller minted."""
    row = await rv.get_review(db, review_id)
    assert row is not None
    args = rv.parse_json(row.get("args"))
    if rail == "in-process":
        return await ge._execute_in_process(
            db, tool="give_store_credit", args=args, idempotency_key=key, operator_sub=NADIA_SUB,
        )
    return _call_lambda(module, {**args, "idempotency_key": key})


# ---------------------------------------------------------------------------
# The read models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_clients_list_shows_open_requests_and_the_last_order(fresh_db) -> None:
    async with await psycopg.AsyncConnection.connect(**_conninfo(fresh_db)) as aconn:
        payload = await OP.list_clients(db=_PgDb(aconn))
    clients = {c["customerId"]: c for c in payload["clients"]}
    jessica = clients[JESSICA]
    assert jessica["openRequests"] == 1
    assert jessica["openRequest"] == "Two items went back, no credit yet"
    assert jessica["lastOrder"]["productName"] in {"Waffle Bath Robe, Sage", "Reed Diffuser"}
    assert jessica["lastOrder"]["placedAt"]
    assert "CUST-FRESH" not in clients
    order = [c["openRequests"] for c in payload["clients"]]
    assert order == sorted(order, reverse=True), "clients with open requests come first"
    assert not re.search(r"membership|tier|silver|gold", json.dumps(payload), re.IGNORECASE)


@pytest.mark.asyncio
async def test_jessicas_record_marks_only_received_returns(fresh_db) -> None:
    """The seeded returns make two orders Returned; a new request does not make a third."""
    with psycopg.connect(**_conninfo(fresh_db)) as conn:
        _clean_case(conn)
    async with await psycopg.AsyncConnection.connect(**_conninfo(fresh_db)) as aconn:
        db = _PgDb(aconn)
        record = await OP.get_client(JESSICA, db=db)
        returned = {o["productName"] for o in record["orders"] if o["returned"]}
        assert returned == {"Waffle Bath Robe, Sage", "Reed Diffuser"}
        assert record["client"]["returnedCount"] == 2 and record["credits"] == []

        async with aconn.transaction(force_rollback=True):
            await db.fetch_all(
                "UPDATE pellier.orders SET return_status = 'requested' "
                "WHERE customer_id = %s AND product_id = '31' RETURNING id", JESSICA,
            )
            claimed = await OP.get_client(JESSICA, db=db)
        pour_over = next(o for o in claimed["orders"] if o["productId"] == "31")
        assert pour_over["returnStatus"] == "requested" and pour_over["returned"] is False
        assert claimed["client"]["returnedCount"] == 2


# ---------------------------------------------------------------------------
# One approval, one key, one credit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("rail", ["in-process", "gateway"])
async def test_one_approval_is_one_credit_on_either_rail(fresh_db, monkeypatch, rail) -> None:
    with psycopg.connect(**_conninfo(fresh_db)) as conn:
        _clean_case(conn)
        module = _lambda(monkeypatch, conn)
        _set_rail(monkeypatch, rail, module)
        robe, diffuser, pour_over = (_order_id(conn, p) for p in ("42", "25", "31"))

        async with await psycopg.AsyncConnection.connect(**_conninfo(fresh_db)) as aconn:
            db = _PgDb(aconn)

            # Two investigations, worded and pointed differently: one review, 10000.
            first = _investigate(conn, [robe], "The robe came back and nothing was credited.")
            second = _investigate(conn, [diffuser, pour_over], "Both returns were received.")
            assert first["status"] == "review_opened" and second["status"] == "already_covered"
            assert first["amount_cents"] == second["amount_cents"] == 10000
            assert sorted(first["order_ids"]) == sorted([robe, diffuser])
            assert second["review_id"] == first["review_id"] and _reviews(conn) == 1
            review_id = int(first["review_id"])

            review = await rv.get_review(db, review_id)
            decided = await rv.decide_review(
                db, review_id=review_id, decision=rv.STATUS_CONFIRMED, decided_by=NADIA_SUB,
                action_hash=review["action_hash"], decided_by_name="nadia",
            )
            assert decided["decided_by_name"] == "nadia"

            executed = await _execute(db, review_id)
            key = executed.idempotency_key
            assert key == f"operator-review:{review_id}:{review['action_hash'][:32]}"
            assert executed.result["status"] == "success"
            assert executed.result["idempotent_replay"] is False
            assert executed.record["creditRows"] == 1 and executed.record["auditRows"] == 1
            assert executed.record["amountCents"] == 10000

            # The approved terms under a key the caller minted: refused, nothing written.
            minted = f"operator-review:{review_id}:minted-by-the-caller"
            refused = await _fresh_key_attempt(db, rail, module, review_id, minted)
            assert refused["status"] == "approval_key_mismatch", refused
            assert _credits(conn, minted) == 0 and _credits(conn) == 1

            # The exact retry replays the first credit.
            retried = await _execute(db, review_id)
            assert retried.result["idempotent_replay"] is True
            assert retried.result["credit_id"] == executed.result["credit_id"]
            assert retried.record["creditRows"] == 1 and retried.record["auditRows"] == 1

            # The paid case, investigated again: the same review, no second one.
            again = _investigate(conn, [robe, diffuser], "Checking the robe and diffuser again.")
            assert again["status"] == "already_approved" and again["review_id"] == review_id
            assert _reviews(conn) == 1
            await _execute(db, review_id)
            assert _credits(conn) == 1
            assert _scalar(conn, "SELECT sum(amount_cents) FROM pellier.store_credits "
                                 "WHERE customer_id = %s", JESSICA) == 10000

            # The credit records the two orders it covers, once each.
            credit_id = executed.result["credit_id"]
            covered = _rows_of(conn, "SELECT id FROM pellier.orders WHERE store_credit_id = %s "
                                     "ORDER BY id", credit_id)
            assert [row["id"] for row in covered] == sorted([robe, diffuser])
            assert executed.result["order_ids"] == sorted([robe, diffuser])


@pytest.mark.asyncio
@pytest.mark.parametrize("rail", ["in-process", "gateway"])
async def test_jessicas_request_and_the_investigation_give_one_review_and_one_credit(
    fresh_db, monkeypatch, rail,
) -> None:
    """Her chat request names no amount and is never approvable; the Planner's review pays once."""
    with psycopg.connect(**_conninfo(fresh_db)) as conn:
        _clean_case(conn)
        module = _lambda(monkeypatch, conn)
        _set_rail(monkeypatch, rail, module)
        robe = _order_id(conn, "42")

        asked = _ask_for_credit(conn, rail, module)
        again = _ask_for_credit(conn, rail, module)
        assert asked["credit_request_status"] == "request_opened"
        assert again["credit_request_status"] == "already_requested"
        assert again["request_id"] == asked["request_id"]
        (request,) = _requests(conn)
        assert request["args"] == {} and request["action_hash"] is None
        assert request["status"] == "open" and _reviews(conn) == 0

        async with await psycopg.AsyncConnection.connect(**_conninfo(fresh_db)) as aconn:
            db = _PgDb(aconn)
            for decision in (rv.STATUS_CONFIRMED, rv.STATUS_DECLINED):
                with pytest.raises(rv.ReviewError) as refused:
                    await rv.decide_review(db, review_id=int(request["id"]), decision=decision,
                                           decided_by=NADIA_SUB, action_hash="a" * 64)
                assert refused.value.code == "request_not_approvable"
            queue = await OP.list_reviews(db=db)
            assert queue["openRequestCount"] == 1 and queue["total"] == 0
            assert not re.search(r"amount", json.dumps(queue["requests"]), re.IGNORECASE)

            proposal = _investigate(conn, [robe], "Her two returns were received.")
            assert proposal["status"] == "review_opened" and proposal["amount_cents"] == 10000
            review_id = int(proposal["review_id"])
            (answered,) = _requests(conn)
            assert answered["answered_by_review_id"] == review_id and answered["answered_turn_id"]
            assert answered["status"] == "answered", "a request is answered, never decided"

            review = await rv.get_review(db, review_id)
            await rv.decide_review(db, review_id=review_id, decision=rv.STATUS_CONFIRMED,
                                   decided_by=NADIA_SUB, action_hash=review["action_hash"])
            executed = await _execute(db, review_id)
            assert executed.result["status"] == "success"

            record = await OP.get_client(JESSICA, db=db)
            assert [r["status"] for r in record["requests"]] == ["answered"]
            assert record["requests"][0]["answeredByReviewId"] == review_id

        assert _reviews(conn) == 1 and _credits(conn) == 1
        assert _count(conn, "SELECT count(*) FROM pellier.tool_audit "
                            "WHERE tool = 'give_store_credit'") == 1
        assert _scalar(conn, "SELECT sum(amount_cents) FROM pellier.store_credits "
                             "WHERE customer_id = %s", JESSICA) == 10000


def test_a_request_can_never_be_approved_in_the_table(fresh_db, monkeypatch) -> None:
    """A request names no amount; the database refuses to give it a decision."""
    with psycopg.connect(**_conninfo(fresh_db)) as conn:
        _clean_case(conn)
        module = _lambda(monkeypatch, conn)
        request_id = int(_ask_for_credit(conn, "in-process", module)["request_id"])
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.cursor() as cur:
                cur.execute("UPDATE pellier.approvals SET status = 'approved', decided_at = now(), "
                            "decided_by = 'forced' WHERE id = %s", (request_id,))
        assert _credits(conn) == 0


def _force_approved_review(conn: psycopg.Connection, order_ids: List[int], amount: int,
                           reason: str) -> str:
    """An approved credit review written straight into the table, and its write key."""
    from services.store_tools import execution_idempotency_key, write_request_hash

    args = {"customer_id": JESSICA, "amount_cents": amount, "reason": reason}
    action_hash = write_request_hash("give_store_credit", **args)
    review_id = int(_scalar(
        conn,
        "INSERT INTO pellier.approvals (customer_id, tool, status, args, action_hash, order_ids, "
        "decided_by, decided_at) VALUES (%s, 'give_store_credit', 'approved', %s::jsonb, %s, "
        "%s::bigint[], 'forced', now()) RETURNING id",
        JESSICA, json.dumps(args), action_hash, order_ids,
    ))
    return execution_idempotency_key(review_id, action_hash)


def test_the_database_never_credits_an_order_twice_whoever_asks(fresh_db) -> None:
    """The backstop for one credit per case: no principal gets around the order rule.

    Jessica's real credit is paid. Then an approved review written straight into
    the table, with different terms, for the same returned orders: the function
    refuses it, and so does the store_credits trigger when the owner inserts the
    credit row directly. An order holds one store_credit_id, so it cannot point
    at two credits.
    """
    with psycopg.connect(**_conninfo(fresh_db)) as conn:
        _clean_case(conn)
        robe, diffuser = _order_id(conn, "42"), _order_id(conn, "25")
        run = _sync_run(conn)
        paid_key = _force_approved_review(conn, [robe, diffuser], 10000, "The two returns.")
        paid = run("SELECT pellier.apply_store_credit(%s, %s, %s, %s) AS result",
                   (paid_key, JESSICA, 10000, "The two returns."))[0]["result"]
        assert paid["status"] == "success" and paid["order_ids"] == sorted([robe, diffuser])

        again_key = _force_approved_review(conn, [robe], 6400, "The robe, again.")
        again = run("SELECT pellier.apply_store_credit(%s, %s, %s, %s) AS result",
                    (again_key, JESSICA, 6400, "The robe, again."))[0]["result"]
        assert again["status"] == "not_creditable" and again["denied_by"] == "order_guard"
        with pytest.raises(psycopg.errors.CheckViolation) as direct:
            _insert_credit(conn, again_key, 6400, "The robe, again.")
        assert direct.value.diag.constraint_name == "store_credits_require_approval"

        # A review that covers no order credits nothing either: the Lab 4 over-limit
        # probe is such a review, so a policy that wrongly allowed it still pays nothing.
        probe_key = _force_approved_review(conn, [], 10001, "Over-limit probe.")
        probe = run("SELECT pellier.apply_store_credit(%s, %s, %s, %s) AS result",
                    (probe_key, JESSICA, 10001, "Over-limit probe."))[0]["result"]
        assert probe["status"] == "not_creditable"

        assert _credits(conn) == 1
        assert _count(conn, "SELECT count(*) FROM pellier.orders WHERE store_credit_id IS NOT NULL") == 2


def test_a_credit_needs_its_approval_and_the_amount_ceiling_is_500(fresh_db) -> None:
    """$100.01 is a valid credit to the database; only Lab 4's policy refuses it."""
    with psycopg.connect(**_conninfo(fresh_db)) as conn:
        _clean_case(conn)
        robe, diffuser = _order_id(conn, "42"), _order_id(conn, "25")
        run = _sync_run(conn)

        def credit(key: str, amount: int, reason: str) -> Dict[str, Any]:
            return run("SELECT pellier.apply_store_credit(%s, %s, %s, %s) AS result",
                       (key, JESSICA, amount, reason))[0]["result"]

        assert credit("operator-review:1:none", 10000, "x")["status"] == "approval_required"
        assert credit("operator-review:1:none", 10001, "Over the limit, valid here.")[
            "status"] == "approval_required"
        assert credit("k", 50001, "x")["status"] == "policy_blocked"
        key = _force_approved_review(conn, [robe, diffuser], 10001, "Over the limit, valid here.")
        assert credit(key, 10000, "Over the limit, valid here.")["status"] == "approval_mismatch"
        minted = key.rsplit(":", 1)[0] + ":minted"
        assert credit(minted, 10001, "Over the limit, valid here.")["status"] == (
            "approval_key_mismatch")
        assert credit(key, 10001, "Over the limit, valid here.")["status"] == "success"

        # The ceiling is a CHECK of its own: an approved review for $500.01 that
        # passes every approval rule still cannot be written.
        pour_over = _order_id(conn, "31")
        with conn.cursor() as cur:
            cur.execute("UPDATE pellier.orders SET return_status = 'received' WHERE id = %s",
                        (pour_over,))
        try:
            over_key = _force_approved_review(conn, [pour_over], 50001, "Over the ceiling.")
            with pytest.raises(psycopg.errors.CheckViolation) as over:
                _insert_credit(conn, over_key, 50001, "Over the ceiling.")
            assert over.value.diag.constraint_name == "store_credits_amount_cents_check"
        finally:
            with conn.cursor() as cur:
                cur.execute("UPDATE pellier.orders SET return_status = NULL WHERE id = %s",
                            (pour_over,))


def _insert_credit(conn: psycopg.Connection, key: str, amount: int, reason: str) -> None:
    """The owner writing a credit row directly, bound to the review its key names."""
    review_id = int(key.split(":")[1])
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pellier.store_credits (approval_id, customer_id, amount_cents, reason, "
            "idempotency_key) VALUES (%s, %s, %s, %s, %s)",
            (review_id, JESSICA, amount, reason, key),
        )


def test_the_owner_cannot_write_a_credit_no_approved_review_names(fresh_db, monkeypatch) -> None:
    """The money rules hold for any insert, the table owner's too, not only the function's callers.

    The ``BEFORE INSERT`` trigger covers how a credit row is written; nothing in
    Pellier updates or deletes one. Each direct insert below names a real
    approvals row, so only the trigger
    stands between it and a paid credit: a shopper's request, a pending
    review, an approved review with other terms, and one under a minted key.
    """
    from services.store_tools import execution_idempotency_key

    with psycopg.connect(**_conninfo(fresh_db)) as conn:
        _clean_case(conn)
        robe, diffuser = _order_id(conn, "42"), _order_id(conn, "25")
        module = _lambda(monkeypatch, conn)
        request_id = int(_ask_for_credit(conn, "in-process", module)["request_id"])
        key = _force_approved_review(conn, [robe, diffuser], 10000, "The two returns.")
        approved_id = int(key.split(":")[1])
        pending_id = int(_scalar(
            conn, "INSERT INTO pellier.approvals (customer_id, tool, status, args, action_hash, "
                  "order_ids) SELECT customer_id, tool, 'pending', args, action_hash || 'p', "
                  "order_ids FROM pellier.approvals WHERE id = %s RETURNING id", approved_id,
        ))

        def refused(approval_id: int, amount: int, write_key: str) -> None:
            with pytest.raises(psycopg.errors.CheckViolation) as caught:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO pellier.store_credits (approval_id, customer_id, amount_cents, "
                        "reason, idempotency_key) VALUES (%s, %s, %s, %s, %s)",
                        (approval_id, JESSICA, amount, "The two returns.", write_key),
                    )
            assert caught.value.diag.constraint_name == "store_credits_require_approval"

        refused(request_id, 10000, execution_idempotency_key(request_id, "x" * 32))
        refused(pending_id, 10000, execution_idempotency_key(pending_id, "x" * 32))
        refused(approved_id, 9999, key)
        refused(approved_id, 10000, key.rsplit(":", 1)[0] + ":minted")
        assert _credits(conn) == 0

        # The positive control: the approved review's own terms and key are written.
        _insert_credit(conn, key, 10000, "The two returns.")
        assert _credits(conn) == 1


@pytest.mark.asyncio
async def test_a_third_returned_order_gets_its_own_credit_for_that_order_only(
    fresh_db, monkeypatch,
) -> None:
    """The paid items stay covered; the new return is proposed and paid alone."""
    with psycopg.connect(**_conninfo(fresh_db)) as conn:
        _clean_case(conn)
        _set_rail(monkeypatch, "in-process", _lambda(monkeypatch, conn))
        robe, pour_over = _order_id(conn, "42"), _order_id(conn, "31")
        async with await psycopg.AsyncConnection.connect(**_conninfo(fresh_db)) as aconn:
            db = _PgDb(aconn)
            first = _investigate(conn, [robe], "Her two returns were received.")
            first_id = int(first["review_id"])
            review = await rv.get_review(db, first_id)
            await rv.decide_review(db, review_id=first_id, decision=rv.STATUS_CONFIRMED,
                                   decided_by=NADIA_SUB, action_hash=review["action_hash"])
            await _execute(db, first_id)

            with conn.cursor() as cur:
                cur.execute("UPDATE pellier.orders SET return_status = 'received' WHERE id = %s",
                            (pour_over,))
            try:
                third = _investigate(conn, [robe, pour_over], "The pour-over set came back too.")
                assert third["status"] == "review_opened" and third["order_ids"] == [pour_over]
                assert third["amount_cents"] == 5800
                third_id = int(third["review_id"])
                review = await rv.get_review(db, third_id)
                await rv.decide_review(db, review_id=third_id, decision=rv.STATUS_CONFIRMED,
                                       decided_by=NADIA_SUB, action_hash=review["action_hash"])
                executed = await _execute(db, third_id)
                assert executed.record["amountCents"] == 5800

                # Investigated once more, everything returned is covered: no third review.
                again = _investigate(conn, [robe, pour_over], "Checking again.")
                assert again["status"] == "already_approved" and _reviews(conn) == 2
            finally:
                with conn.cursor() as cur:
                    cur.execute("UPDATE pellier.orders SET store_credit_id = NULL, "
                                "return_status = NULL WHERE id = %s", (pour_over,))

        amounts = [row["amount_cents"] for row in _rows_of(
            conn, "SELECT amount_cents FROM pellier.store_credits WHERE customer_id = %s "
                  "ORDER BY credit_id", JESSICA)]
        assert amounts == [10000, 5800]


@pytest.mark.asyncio
async def test_a_declined_credit_can_be_proposed_again(fresh_db) -> None:
    """A no leaves the live index, so the case can come back to a person."""
    with psycopg.connect(**_conninfo(fresh_db)) as conn:
        _clean_case(conn)
        robe = _order_id(conn, "42")
        async with await psycopg.AsyncConnection.connect(**_conninfo(fresh_db)) as aconn:
            db = _PgDb(aconn)
            first = _investigate(conn, [robe], "The robe came back.")
            await rv.decide_review(db, review_id=int(first["review_id"]),
                                   decision=rv.STATUS_DECLINED, decided_by=NADIA_SUB)
            second = _investigate(conn, [robe], "The robe came back.")
        assert second["status"] == "review_opened"
        assert second["review_id"] != first["review_id"] and _reviews(conn) == 2


@pytest.mark.asyncio
async def test_a_refused_execution_writes_nothing(fresh_db, monkeypatch) -> None:
    """The governed format without its managed rail refuses before any write."""
    from config import settings

    monkeypatch.setattr(settings, "WORKSHOP_FORMAT", "governed", raising=False)
    monkeypatch.setattr(settings, "AGENTCORE_GATEWAY_URL", "", raising=False)
    with psycopg.connect(**_conninfo(fresh_db)) as conn:
        _clean_case(conn)
        robe = _order_id(conn, "42")
        async with await psycopg.AsyncConnection.connect(**_conninfo(fresh_db)) as aconn:
            db = _PgDb(aconn)
            proposal = _investigate(conn, [robe], "The robe came back.")
            review_id = int(proposal["review_id"])
            review = await rv.get_review(db, review_id)
            await rv.decide_review(db, review_id=review_id, decision=rv.STATUS_CONFIRMED,
                                   decided_by=NADIA_SUB, action_hash=review["action_hash"])
            with pytest.raises(ge.GovernedRailUnavailable):
                await _execute(db, review_id)
        assert _credits(conn) == 0
        assert _count(conn, "SELECT count(*) FROM pellier.tool_audit") == 0
        (stored,) = _rows_of(conn, "SELECT last_attempt FROM pellier.approvals WHERE id = %s",
                             review_id)
        attempt = stored["last_attempt"]
        assert attempt["outcome"] == "refused" and attempt["policy"] == "NOT_EVALUATED"
        assert "AGENTCORE_GATEWAY_URL" in attempt["detail"]


@pytest.mark.asyncio
async def test_a_denied_attempt_is_stored_and_read_back_after_a_reload(fresh_db, monkeypatch) -> None:
    """After a reload the desk shows what the Gateway answered, not a guess from the tables.

    Cedar's DENY is stored on the review with its key, the forbids naming the
    action and the policy digest. Nothing ran, so the tables still hold no
    credit and no audit row, and those stay the execution and data evidence.
    """
    with psycopg.connect(**_conninfo(fresh_db)) as conn:
        _clean_case(conn)
        _set_rail(monkeypatch, "gateway", _lambda(monkeypatch, conn))
        denial = "Tool call not allowed due to policy enforcement [Policy evaluation denied due to x]"

        async def cedar_denies(*, tool: str, args: Any, idempotency_key: str, access_token: str):
            return ge.POLICY_DENY, {"status": "policy_denied", "gateway_message": denial}, "Denied."

        monkeypatch.setattr(ge, "_execute_through_gateway", cedar_denies)
        robe = _order_id(conn, "42")
        async with await psycopg.AsyncConnection.connect(**_conninfo(fresh_db)) as aconn:
            db = _PgDb(aconn)
            review_id = int(_investigate(conn, [robe], "The robe came back.")["review_id"])
            review = await rv.get_review(db, review_id)
            await rv.decide_review(db, review_id=review_id, decision=rv.STATUS_CONFIRMED,
                                   decided_by=NADIA_SUB, action_hash=review["action_hash"])
            engine = ge.PolicyEngineState(
                gateway_mode="ENFORCE", matching_forbids=("credit_limit_forbid",),
                policy_engine_id="engine-1", policy_digest="sha256:" + "d" * 64,
            )
            row = await rv.get_review(db, review_id)
            await ge.execute_confirmed_review(
                db, row, operator_sub=NADIA_SUB, access_token="jwt", engine_state=engine,
            )
            reloaded = await OP.get_review(review_id, db=db)

        key = reloaded["review"]["execution"]["idempotencyKey"]
        assert reloaded["review"]["assurance"]["policy"] == "DENY"
        assert reloaded["review"]["assurance"]["evidence"] == "NO_EXECUTION"
        stored = reloaded["review"]["execution"]["lastAttempt"]
        assert stored["outcome"] == "denied" and stored["idempotencyKey"] == key
        assert stored["matchingForbids"] == ["credit_limit_forbid"]
        assert stored["policyDigest"] == "sha256:" + "d" * 64 and stored["detail"] == denial
        assert stored["label"] == "The Gateway answered: denied"
        assert reloaded["review"]["execution"]["notes"]["policy"].startswith(
            "The Gateway answered: denied")
        assert _credits(conn, key) == 0
        assert _count(conn, "SELECT count(*) FROM pellier.tool_audit") == 0


def _rows_of(conn: psycopg.Connection, sql: str, *params: Any) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return _rows(cur)
