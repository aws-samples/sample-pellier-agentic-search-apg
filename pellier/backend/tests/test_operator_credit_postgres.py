"""Jessica's credit on real PostgreSQL: one approval is one key is one credit, on both rails.

Her own chat request opens a credit request with no amount, which nobody can
approve; the Planner's records-built review is the only approvable credit, and
a live review keeps the returned orders it covers.

Fakes cannot prove the parts the database decides: that migration 020's
partial unique index keeps one live review per exact credit, that the
``ON CONFLICT`` target infers it, that ``apply_store_credit`` replays a key,
and that the receipt CHECKs admit what the service writes. This module runs
the real migrations on a throwaway cluster (``tests/fresh_cluster.py``) and
drives the real code against them.

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
        return list(field["arrayValue"].get("stringValues") or [])
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
    """``rds_client.execute_statement`` with named ``:params``, run on the cluster."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

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
    """Every review, credit, claim and audit row gone; the seeded case stays."""
    with conn.cursor() as cur:
        cur.execute(
            "TRUNCATE pellier.approvals, pellier.store_credits, pellier.write_operations, "
            "pellier.tool_audit CASCADE"
        )


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
        run=_sync_run(conn), customer_id=JESSICA, customer_name="Jessica Nakamura",
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
    return _rows_of(conn, "SELECT id, args, action_hash, status, recommendation "
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
                "INSERT INTO pellier.returns (customer_id, product_id, reason, status) "
                "VALUES (%s, '31', 'changed_mind', 'pending')", JESSICA,
            )
            claimed = await OP.get_client(JESSICA, db=db)
        pour_over = next(o for o in claimed["orders"] if o["productId"] == "31")
        assert pour_over["returnStatus"] == "pending" and pour_over["returned"] is False
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

            receipts = _count(conn, "SELECT count(*) FROM pellier.execution_receipts "
                                    "WHERE review_id = %s", review_id)
            assert receipts == 3, "one receipt per attempt"


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
        assert request["status"] == "pending" and _reviews(conn) == 0

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
            assert answered["recommendation"]["answeredByReviewId"] == review_id
            assert answered["status"] == "pending", "a request is answered, never decided"

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


@pytest.mark.asyncio
async def test_a_request_forced_to_approved_still_admits_no_credit(fresh_db, monkeypatch) -> None:
    """Even approved by hand in the table, a request fingerprints nothing and pays nothing."""
    from services import store_tools

    with psycopg.connect(**_conninfo(fresh_db)) as conn:
        _clean_case(conn)
        module = _lambda(monkeypatch, conn)
        _set_rail(monkeypatch, "in-process", module)
        request_id = int(_ask_for_credit(conn, "in-process", module)["request_id"])
        with conn.cursor() as cur:
            cur.execute("UPDATE pellier.approvals SET status = 'approved', decided_at = now(), "
                        "decided_by = 'forced' WHERE id = %s", (request_id,))
        refused = store_tools.give_store_credit(
            _sync_run(conn), customer_id=JESSICA, amount_cents=10000,
            reason="Store credit for the returns.", idempotency_key=f"operator-review:{request_id}:x",
        )
        assert refused["status"] == "approval_required", refused
        async with await psycopg.AsyncConnection.connect(**_conninfo(fresh_db)) as aconn:
            db = _PgDb(aconn)
            with pytest.raises(Exception):
                await _execute(db, request_id)
        assert _credits(conn) == 0


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
                cur.execute("INSERT INTO pellier.returns (customer_id, product_id, reason, status) "
                            "VALUES (%s, '31', 'changed_mind', 'approved') RETURNING id", (JESSICA,))
                return_id = cur.fetchone()["id"]
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
                    cur.execute("DELETE FROM pellier.returns WHERE id = %s", (return_id,))

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


def test_reapplying_020_converges_a_pending_only_index(fresh_db) -> None:
    """The reset re-applies 020; a cluster built before approvals joined the index converges."""
    migration = DEPLOY.parent / "migrations" / "020_operator_review.sql"
    with psycopg.connect(**_conninfo(fresh_db)) as conn:
        _clean_case(conn)
    fresh_db.psql(
        "DROP INDEX pellier.approvals_open_per_action_idx; "
        "CREATE UNIQUE INDEX approvals_open_per_action_idx ON pellier.approvals "
        "(customer_id, tool, action_hash) WHERE status = 'pending';"
    )
    fresh_db.psql(migration.read_text())
    definition = fresh_db.psql(
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'approvals_open_per_action_idx'"
    )
    assert "'pending'::text" in definition and "'approved'::text" in definition, definition


# ---------------------------------------------------------------------------
# Receipts the table used to refuse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_refused_execution_and_an_unknown_outcome_are_both_stored(
    fresh_db, monkeypatch,
) -> None:
    """The refused rail and OUTCOME_UNKNOWN are values the effective CHECKs admit."""
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

            with pytest.raises(ge.GovernedRailUnavailable) as refused:
                await _execute(db, review_id)
            assert refused.value.receipt_id is not None

            unknown = ge.ExecutionOutcome(
                rail=ge.RAIL_GATEWAY, execution_turn_id=new_turn_id(),
                idempotency_key="operator-review:0:unknown", operator_sub=NADIA_SUB,
                customer_subject=None, policy=ge.POLICY_EVALUATION_INCOMPLETE,
                aurora=ge.AURORA_OUTCOME_UNKNOWN, evidence=ge.EVIDENCE_ATTEMPT_RECEIPT,
                tool="give_store_credit",
            )
            assert await ge.record_receipt(db, unknown, review_id=review_id) is not None

        stored = _rows_of(conn, "SELECT rail, policy_outcome, aurora_outcome "
                                "FROM pellier.execution_receipts WHERE review_id = %s "
                                "ORDER BY receipt_id", review_id)
    assert stored == [
        {"rail": "refused", "policy_outcome": "EVALUATION_INCOMPLETE",
         "aurora_outcome": "NOT_REACHED"},
        {"rail": "gateway-mcp", "policy_outcome": "EVALUATION_INCOMPLETE",
         "aurora_outcome": "OUTCOME_UNKNOWN"},
    ]
    assert _credits_any(fresh_db) == 0, "a refused execution writes no credit"


def _rows_of(conn: psycopg.Connection, sql: str, *params: Any) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return _rows(cur)


def _credits_any(cluster: Any) -> int:
    with psycopg.connect(**_conninfo(cluster)) as conn:
        return _credits(conn)
