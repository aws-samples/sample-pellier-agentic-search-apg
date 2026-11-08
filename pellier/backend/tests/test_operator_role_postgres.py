"""Real PostgreSQL grants keep proposing separate from approving and paying."""
import psycopg
import pytest
from psycopg.rows import dict_row

from services import operator_graph
from tests.fresh_cluster import fresh_db  # noqa: F401


def test_operator_login_can_read_and_propose_but_cannot_approve_or_pay(fresh_db):
    with psycopg.connect(host=str(fresh_db.socket), user="postgres", dbname="postgres",
                         autocommit=True, row_factory=dict_row) as conn:
        conn.execute("SET SESSION AUTHORIZATION pellier_operator_tools")
        role = conn.execute("SELECT rolsuper, rolbypassrls, rolinherit FROM pg_roles "
                            "WHERE rolname = current_user").fetchone()
        assert role == {"rolsuper": False, "rolbypassrls": False, "rolinherit": False}
        audit = conn.execute(
            "SELECT has_table_privilege(current_user, 'pellier.tool_audit', 'INSERT') AS whole, "
            "has_column_privilege(current_user, 'pellier.tool_audit', 'session_id', 'INSERT') AS receipt, "
            "has_column_privilege(current_user, 'pellier.tool_audit', 'audit_id', 'INSERT') AS id"
        ).fetchone()
        assert audit == {"whole": False, "receipt": True, "id": False}
        owners = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'pellier' "
                              "AND tableowner = current_user").fetchall()
        assert owners == []
        # Missing transaction identity must not inherit a previous case.
        assert conn.execute("SELECT count(*) AS n FROM pellier.orders").fetchone()["n"] == 0
        with conn.transaction():
            conn.execute("SELECT set_config('pellier.principal_username', 'jessica', true)")
            rows = conn.execute("SELECT customer_id FROM pellier.orders").fetchall()
            assert rows and {r["customer_id"] for r in rows} == {"CUST-JESSICA"}
            assert conn.execute("SELECT id FROM pellier.orders WHERE customer_id = 'CUST-THEO'").fetchall() == []
            tickets = conn.execute("SELECT customer_id FROM pellier.support_tickets").fetchall()
            assert tickets and {r["customer_id"] for r in tickets} == {"CUST-JESSICA"}

            def run(sql, params=()):
                return conn.execute(sql, params).fetchall()

            orders = run(operator_graph._RETURNED_ORDERS_SQL, ("CUST-JESSICA", "received"))
            case = operator_graph._Case(run, run, "CUST-JESSICA", "Jessica", "staff-test",
                                        "turn-staff-proof", lambda _event: None)
            proposal = operator_graph.propose_credit(
                case, order_ids=[r["order_id"] for r in orders], reason="Received return")
            assert proposal["amount_cents"] == 10000
            assert case.proposal.status == "pending"
            again = operator_graph._Case(run, run, "CUST-JESSICA", "Jessica", "staff-test",
                                         "turn-staff-retry", lambda _event: None)
            assert operator_graph.propose_credit(
                again, order_ids=[r["order_id"] for r in orders], reason="Retry"
            )["review_id"] == proposal["review_id"]

        assert conn.execute("SELECT count(*) AS n FROM pellier.orders").fetchone()["n"] == 0
        for sql, error in (
            ("UPDATE pellier.approvals SET decided_by = 'staff-test', decided_at = now(), status = 'approved'", psycopg.errors.InsufficientPrivilege),
            ("UPDATE pellier.approvals SET args = '{}'::jsonb", psycopg.errors.InsufficientPrivilege),
            ("UPDATE pellier.approvals SET status = 'approved' WHERE tool = 'give_store_credit'", psycopg.errors.CheckViolation),
            ("INSERT INTO pellier.store_credits (customer_id) VALUES ('CUST-JESSICA')", psycopg.errors.InsufficientPrivilege),
            ("SELECT pellier.give_store_credit('CUST-JESSICA', 'retry', 10000, 'Return', 'staff-test')", psycopg.errors.InsufficientPrivilege),
            ("SET ROLE pellier_credit_writer", psycopg.errors.InsufficientPrivilege),
            ("SET ROLE pellier_credit_owner", psycopg.errors.InsufficientPrivilege),
        ):
            with pytest.raises(error):
                conn.execute(sql)
        with conn.transaction():
            conn.execute("SELECT set_config('pellier.principal_username', 'theo', true)")
            rows = conn.execute("SELECT customer_id FROM pellier.orders").fetchall()
            assert rows and {r["customer_id"] for r in rows} == {"CUST-THEO"}
        assert conn.execute("SELECT count(*) AS n FROM pellier.orders").fetchone()["n"] == 0
        conn.execute("RESET SESSION AUTHORIZATION")
        assert conn.execute("SELECT count(*) AS n FROM pellier.store_credits").fetchone()["n"] == 0
        reviews = conn.execute("SELECT status, decided_by FROM pellier.approvals "
                               "WHERE source_turn_id = 'turn-staff-proof'").fetchall()
        assert reviews == [{"status": "pending", "decided_by": None}]
        conn.execute("DELETE FROM pellier.approvals WHERE source_turn_id = 'turn-staff-proof'")


def test_a_persons_decision_cannot_be_reversed_by_any_login(fresh_db):
    """The staff login may answer requests; it must not turn a rejection into an approval."""
    terms = '{"customer_id": "CUST-JESSICA", "amount_cents": 10000, "reason": "Return"}'
    with _connect(fresh_db) as conn:
        rejected, approved = (conn.execute(
            "INSERT INTO pellier.approvals (customer_id, tool, status, args, action_hash, "
            "decided_by, decided_at) VALUES ('CUST-JESSICA', 'give_store_credit', %s, %s, %s, "
            "'nadia-sub', now()) RETURNING id", (status, terms, f"decision-final-{status}"),
        ).fetchone()["id"] for status in ("rejected", "approved"))
        for login in ("pellier_operator_tools", "postgres"):
            conn.execute(f"SET SESSION AUTHORIZATION {login}")
            for sql, review in (
                ("UPDATE pellier.approvals SET status = 'approved' WHERE id = %s", rejected),
                ("UPDATE pellier.approvals SET status = 'rejected' WHERE id = %s", approved),
            ):
                with pytest.raises(psycopg.errors.CheckViolation, match="already decided"):
                    conn.execute(sql, (review,))
            conn.execute("RESET SESSION AUTHORIZATION")
        rows = conn.execute("SELECT id, status, decided_by FROM pellier.approvals "
                            "WHERE id IN (%s, %s) ORDER BY id", (rejected, approved)).fetchall()
        assert rows == [{"id": rejected, "status": "rejected", "decided_by": "nadia-sub"},
                        {"id": approved, "status": "approved", "decided_by": "nadia-sub"}]
        # Executing an approved review still records its turn; only the decision is final.
        conn.execute("UPDATE pellier.approvals SET execution_turn_id = 'turn-execute-proof' "
                     "WHERE id = %s", (approved,))
        conn.execute("DELETE FROM pellier.approvals WHERE id IN (%s, %s)", (rejected, approved))


def _connect(cluster):
    return psycopg.connect(host=str(cluster.socket), user="postgres", dbname="postgres",
                           autocommit=True, row_factory=dict_row)


def _staff_lambda(monkeypatch, conn):
    from tests.test_operator_credit_postgres import _DataApiOnPostgres
    import common.dataapi as dataapi
    import pellier_operator_tools
    conn.execute("SET SESSION AUTHORIZATION pellier_operator_tools")
    monkeypatch.setattr(dataapi, "rds_client", _DataApiOnPostgres(conn))
    return pellier_operator_tools


def _invoke(module, tool, turn="turn-proposal-proof", **extra):
    import json
    result = module.lambda_handler({"name": "operator_" + tool, "arguments": {
        "customer_id": "CUST-JESSICA", "operator_sub": "staff-test", "turn_id": turn,
        "build_fingerprint": "a" * 64, **extra,
    }}, None)
    return result if result.get("isError") else json.loads(result["content"][0]["text"])


def test_data_api_role_rls_and_atomic_proposal_receipt(fresh_db, monkeypatch):
    with _connect(fresh_db) as owner, _connect(fresh_db) as conn:
        module = _staff_lambda(monkeypatch, conn)
        case = _invoke(module, "get_case")
        assert case["database_role"] == "pellier_operator_tools"
        assert case["visible_orders"] == case["visible_tickets"] == ["CUST-JESSICA"]
        # The same reused connection must see no case after commit.
        assert conn.execute("SELECT customer_id FROM pellier.orders").fetchall() == []
        theo = _invoke(module, "get_case", customer_id="CUST-THEO")
        assert theo["visible_orders"] == theo["visible_tickets"] == ["CUST-THEO"]
        before = owner.execute("SELECT count(*) AS n FROM pellier.approvals WHERE tool='give_store_credit'").fetchone()["n"]
        real_audit = module.dataapi.write_tool_audit

        def failed_audit(**kwargs):
            raise OSError("audit unavailable")

        monkeypatch.setattr(module.dataapi, "write_tool_audit", failed_audit)
        assert _invoke(module, "propose_store_credit", order_ids=[20, 21], reason="Return")["isError"] is True
        assert owner.execute("SELECT count(*) AS n FROM pellier.approvals WHERE tool='give_store_credit'").fetchone()["n"] == before
        monkeypatch.setattr(module.dataapi, "write_tool_audit", real_audit)
        first = _invoke(module, "propose_store_credit", order_ids=[20, 21], reason="Return")
        second = _invoke(module, "propose_store_credit", "turn-proposal-retry", order_ids=[20, 21], reason="Retry")
        assert first["review_id"] == second["review_id"]
        rows = owner.execute("SELECT status, args->>'amount_cents' AS amount, requested_by_sub "
                             "FROM pellier.approvals WHERE tool='give_store_credit'").fetchall()
        assert rows == [{"status": "pending", "amount": "10000", "requested_by_sub": "staff-test"}]
        assert owner.execute("SELECT count(*) AS n FROM pellier.tool_audit "
                             "WHERE tool='operator_propose_store_credit' AND args->>'turn_id' "
                             "IN ('turn-proposal-proof', 'turn-proposal-retry')").fetchone()["n"] == 2
        assert owner.execute("SELECT count(*) AS n FROM pellier.store_credits").fetchone()["n"] == 0
        owner.execute("DELETE FROM pellier.approvals WHERE id = %s", (first["review_id"],))


def test_concurrent_proposals_create_one_pending_review(fresh_db, monkeypatch):
    import queue
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from tests.test_operator_credit_postgres import _DataApiOnPostgres

    with _connect(fresh_db) as owner, _connect(fresh_db) as one, _connect(fresh_db) as two:
        module = _staff_lambda(monkeypatch, one)
        two.execute("SET SESSION AUTHORIZATION pellier_operator_tools")
        available = queue.Queue()
        for conn in (one, two):
            available.put(conn)
        barrier = threading.Barrier(2, timeout=5)

        class ConcurrentApi(_DataApiOnPostgres):
            def execute_statement(self, **kwargs):
                if "INSERT INTO pellier.approvals" in kwargs["sql"]:
                    barrier.wait()
                return super().execute_statement(**kwargs)

        class PerThreadApi:
            def __init__(self):
                self.local = threading.local()

            def __getattr__(self, name):
                if not hasattr(self.local, "client"):
                    self.local.client = ConcurrentApi(available.get_nowait())
                return getattr(self.local.client, name)

        monkeypatch.setattr(module.dataapi, "rds_client", PerThreadApi())
        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [workers.submit(_invoke, module, "propose_store_credit", f"turn-concurrent-{i}",
                                      order_ids=[20, 21], reason="Return") for i in range(2)]
            results = [future.result(timeout=15) for future in futures]
        assert all(not result.get("isError") for result in results)
        assert results[0]["review_id"] == results[1]["review_id"]
        assert owner.execute("SELECT count(*) AS n FROM pellier.approvals WHERE tool='give_store_credit'").fetchone()["n"] == 1
        assert owner.execute("SELECT count(*) AS n FROM pellier.tool_audit WHERE args->>'turn_id' "
                             "IN ('turn-concurrent-0', 'turn-concurrent-1')").fetchone()["n"] == 2
        assert owner.execute("SELECT count(*) AS n FROM pellier.store_credits").fetchone()["n"] == 0
        owner.execute("DELETE FROM pellier.approvals WHERE id = %s", (results[0]["review_id"],))
