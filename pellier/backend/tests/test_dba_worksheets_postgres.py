"""The DBA worksheets on real PostgreSQL, built by the real setup scripts.

The workload worksheet runs on a cluster that preloads pg_stat_statements, as the
workshop's Aurora parameter group does: it fails NOT YET before any tool call,
passes once get_orders and get_tickets have run as pellier_agent, and says
unchecked on a cluster without the library. The reconstruction worksheet runs on
Jessica's chain written by the app's own functions: it fails NOT YET while a link
is missing and passes once every link finds its row. Neither changes a table.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List

import psycopg
import pytest
from psycopg.rows import dict_row

from services import store_tools
from services.turn_identity import new_turn_id
from tests.fresh_cluster import Cluster, fresh_db, run_setup, start_cluster  # noqa: F401

REPO = Path(__file__).resolve().parents[3]
WORKLOAD = REPO / "workshop" / "lab-3-agent-workload.sql"
RECONSTRUCT = REPO / "workshop" / "wrap-up-reconstruct.sql"
TABLES = ("approvals", "store_credits", "tool_audit", "orders", "support_tickets")


def _worksheet(cluster: Cluster, path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(cluster.bin / "psql"), "-X", "-h", str(cluster.socket), "-U", "postgres",
         "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-P", "pager=off", "-f", str(path)],
        capture_output=True, text=True, timeout=60,
    )


def _connect(cluster: Cluster) -> psycopg.Connection:
    return psycopg.connect(host=str(cluster.socket), port=5432, user="postgres",
                           dbname="postgres", autocommit=True, row_factory=dict_row)


def _run(conn: psycopg.Connection) -> Callable[..., List[Dict[str, Any]]]:
    def run(sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()] if cur.description else []
    return run


def _counts(cluster: Cluster) -> str:
    return cluster.psql(" UNION ALL ".join(
        f"SELECT '{name}=' || count(*) FROM pellier.{name}" for name in TABLES))


@pytest.fixture(scope="module")
def statements_db() -> Iterator[Cluster]:
    """A fresh cluster that preloads pg_stat_statements, as the workshop's Aurora does."""
    tmp = tempfile.TemporaryDirectory(prefix="pellier-pgss-")
    try:
        cluster = start_cluster(Path(tmp.name),
                                server_options="-c shared_preload_libraries=pg_stat_statements")
        try:
            run_setup(cluster)
            yield cluster
        finally:
            cluster.stop()
    finally:
        tmp.cleanup()


def _agent_reads(cluster: Cluster, persona: str, customer: str) -> None:
    """get_orders and get_tickets as the tools run them: the role, the bound name, the SQL."""
    with _connect(cluster) as conn, conn.transaction():
        run = _run(conn)
        run("SET LOCAL ROLE pellier_agent")
        run("SELECT set_config('pellier.principal_username', %s, true)", (persona,))
        run(store_tools._ORDERS_SQL, (customer, 10))
        run(store_tools._TICKETS_SQL, (customer, 10))


# ---------------------------------------------------------------------------
# Lab 3: what the agent did to your database
# ---------------------------------------------------------------------------


def test_the_workload_needs_the_library_loaded(fresh_db: Cluster) -> None:  # noqa: F811
    """The harness cluster does not preload it: the worksheet says so and stops."""
    done = _worksheet(fresh_db, WORKLOAD)
    assert done.returncode != 0
    assert "installed but not loaded (shared_preload_libraries)" in done.stdout
    assert done.stdout.rstrip().endswith("Lab 3 workload check unchecked")


def test_the_workload_waits_for_the_agent_then_shows_it_by_role(statements_db: Cluster) -> None:
    before = _counts(statements_db)
    statements_db.psql("SELECT pg_stat_statements_reset()")

    # The row-ownership worksheet's probes run as pellier_agent too; they are not the agent.
    statements_db.psql("BEGIN; SET LOCAL ROLE pellier_agent; "
                       "SELECT set_config('pellier.principal_username', 'theo', true); "
                       "SELECT count(*) FROM pellier.orders WHERE customer_id = 'CUST-THEO'; "
                       "ROLLBACK;")
    waiting = _worksheet(statements_db, WORKLOAD)
    assert waiting.returncode != 0
    assert "Observed  none yet: no get_orders or get_tickets statement under pellier_agent" \
        in waiting.stdout
    assert waiting.stdout.rstrip().endswith("Lab 3 workload check failed")

    _agent_reads(statements_db, "theo", "CUST-THEO")
    _agent_reads(statements_db, "theo", "CUST-THEO")
    done = _worksheet(statements_db, WORKLOAD)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.rstrip().endswith("Lab 3 workload check passed")
    assert "Observed  2 tool statement(s)" in done.stdout
    assert "One-Time Filter" in done.stdout and "current_setting('pellier.principal_username'" \
        in done.stdout
    assert "Observed  0 rows: the row policy runs inside the plan" in done.stdout
    assert max(len(line) for line in done.stdout.splitlines()) < 120
    assert _counts(statements_db) == before


def test_the_workload_fails_when_the_row_policy_shows_theo_another_customer(
    statements_db: Cluster,
) -> None:
    """The plan's 0 rows is part of the verdict, not a remark beside it."""
    _agent_reads(statements_db, "theo", "CUST-THEO")
    statements_db.psql("ALTER POLICY orders_owner ON pellier.orders USING (true)")
    try:
        done = _worksheet(statements_db, WORKLOAD)
    finally:
        statements_db.psql(
            "ALTER POLICY orders_owner ON pellier.orders USING (customer_id = (SELECT id "
            "FROM pellier.customers WHERE cognito_username = "
            "current_setting('pellier.principal_username', true)))")
    assert done.returncode != 0
    assert "of Jessica's orders were visible to Theo's session" in done.stdout
    assert done.stdout.rstrip().endswith("Lab 3 workload check failed")


def test_statements_after_set_local_role_are_recorded_under_that_role(
        statements_db: Cluster) -> None:
    """What the worksheet relies on: pg_stat_statements keys a statement by the
    role in force when it ran, so SET LOCAL ROLE attributes it to the agent's role."""
    statements_db.psql("SELECT pg_stat_statements_reset()")
    _agent_reads(statements_db, "jessica", "CUST-JESSICA")
    roles = statements_db.psql(
        "SELECT string_agg(DISTINCT userid::regrole::text, ',') FROM pg_stat_statements "
        "WHERE query LIKE '%FROM pellier.orders o%'")
    assert roles == "pellier_agent"


# ---------------------------------------------------------------------------
# Wrap-up: Jessica's credit, from her request to the row
# ---------------------------------------------------------------------------


def _jessica_chain(cluster: Cluster, *, handoff_row: bool) -> Dict[str, Any]:
    """Write Lab 4 as the app does: her request, the review, Nadia's approval, the
    credit through apply_store_credit as the money role, and the Gateway's receipts."""
    with _connect(cluster) as conn:
        run = _run(conn)
        asked, investigated = new_turn_id(), new_turn_id()
        request = store_tools.open_credit_request(
            run, customer_id="CUST-JESSICA", reason="Please ask a person about a store credit",
            source_turn_id=asked, requested_by_sub="sub-jessica", requester_kind="shopper")
        if handoff_row:
            run("INSERT INTO pellier.tool_audit (session_id, tool, caller, args, result, latency_ms)"
                " VALUES (%s, 'ask_a_person', 'gateway', %s::jsonb, '{}'::jsonb, 40)",
                (asked, json.dumps({"customer_id": "CUST-JESSICA", "turn_id": asked})))
        reason = "Returned: Waffle Bath Robe, Sage and Reed Diffuser"
        review = store_tools.open_credit_review(
            run, customer_id="CUST-JESSICA", amount_cents=10000, reason=reason,
            source_turn_id=investigated, requested_by_sub="sub-nadia",
            requester_kind="operator", order_ids=[20, 21])
        store_tools.answer_credit_requests(run, customer_id="CUST-JESSICA",
                                           investigation_turn_id=investigated,
                                           review_id=review.id)
        run("UPDATE pellier.approvals SET status = 'approved', decided_by = 'sub-nadia', "
            "decided_by_name = 'nadia', decided_at = now() WHERE id = %s", (review.id,))
        action_hash = run("SELECT action_hash FROM pellier.approvals WHERE id = %s",
                          (review.id,))[0]["action_hash"]
        key = store_tools.execution_idempotency_key(review.id, action_hash)
        with conn.transaction():
            run("SET LOCAL ROLE pellier_credit_writer")
            result = run("SELECT pellier.apply_store_credit(%s, 'CUST-JESSICA', 10000, %s, "
                         "'nadia') AS r", (key, reason))[0]["r"]
        run("INSERT INTO pellier.tool_audit (session_id, tool, caller, args, result, latency_ms)"
            " VALUES ('gateway-CUST-JESSICA', 'give_store_credit', 'gateway', %s::jsonb, "
            "%s::jsonb, 300)",
            (json.dumps({"customer_id": "CUST-JESSICA", "amount_cents": 10000,
                         "reason": reason, "idempotency_key": key}), json.dumps(result)))
        assert result["status"] == "success", result
        return {"request": request.id, "review": review.id, "asked": asked, "key": key,
                "credit": result["credit_id"]}


def test_the_reconstruction_names_the_first_missing_link_then_tells_the_story(
        fresh_db: Cluster) -> None:  # noqa: F811
    nothing = _worksheet(fresh_db, RECONSTRUCT)
    assert nothing.returncode != 0
    assert "Observed  NOT YET: Jessica has no store credit" in nothing.stdout

    chain = _jessica_chain(fresh_db, handoff_row=False)
    gap = _worksheet(fresh_db, RECONSTRUCT)
    assert gap.returncode != 0
    assert "NOT YET: her request's turn left no ask_a_person row in tool_audit" in gap.stdout
    assert gap.stdout.rstrip().endswith("Wrap-up reconstruction failed")

    with _connect(fresh_db) as conn:
        _run(conn)("INSERT INTO pellier.tool_audit (session_id, tool, caller, args) "
                   "VALUES (%s, 'ask_a_person', 'gateway', '{}'::jsonb)", (chain["asked"],))
    before = _counts(fresh_db)
    done = _worksheet(fresh_db, RECONSTRUCT)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.rstrip().endswith("Wrap-up reconstruction passed")
    story = [line for line in done.stdout.splitlines() if " \u2502 " in line][1:8]
    assert [line.split(" \u2502 ")[1].strip() for line in story] == [
        "Jessica asked for a person about a store credit",
        "ask_a_person ran in her turn (gateway)",
        "The investigation proposed $100.00 for orders 20, 21",
        "nadia approved the review",
        "give_store_credit ran with the review's key (gateway)",
        f"Aurora wrote credit {chain['credit']}, $100.00",
        f"Orders 20, 21 now carry credit {chain['credit']}",
    ]
    assert f"Key       {chain['key']}" in done.stdout
    assert max(len(line) for line in done.stdout.splitlines()) < 120
    assert _counts(fresh_db) == before
