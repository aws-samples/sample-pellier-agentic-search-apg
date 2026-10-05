"""Lab 4's contract: the starters fail the way the guide's Spot step shows, the solutions do not.

Task 4A. Provisioning deploys the starter forbid, ``unless { false }``. Nadia
approves Jessica's in-limit credit (10000 cents, the seeded case) and the
starter still blocks it; with the solution it passes while 10001 cents is
denied. Decided by the real Cedar engine over the rendered baseline.

Task 4B. The RLS worksheet's starter expression is ``false``: Theo sees none of
his own rows and the Investigator none of Jessica's, so the check fails. The
solution passes every probe, and both leave the live policies and the tables
as they were. The keyed absence check is supplied: it reads the over-limit
review the Lab 4A check sent and Jessica's credit, and passes only on 0, 0, 1.

The worksheets run through ``psql`` on the real schema and seed.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import psycopg
import pytest
from psycopg.rows import dict_row

from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
lab4 = importlib.import_module("lab4_policy_check")

STARTER_RULE = REPO / "workshop" / "starters" / "workshop_credit_limit.cedar"
SOLUTION_RULE = REPO / "solutions" / "the-concierge" / "policies" / "workshop_credit_limit.cedar"
RLS_STARTER = REPO / "workshop" / "starters" / "lab-4-rls.sql"
RLS_SOLUTION = REPO / "solutions" / "the-concierge" / "sql" / "lab-4-rls-solution.sql"
ABSENCE = REPO / "workshop" / "lab-4-absence.sql"
JESSICA = "CUST-JESSICA"


@pytest.fixture(scope="module")
def conn(fresh_db: Any) -> Any:  # noqa: F811 - the imported fixture
    connection = psycopg.connect(host=str(fresh_db.socket), port=5432, user="postgres",
                                 dbname="postgres", autocommit=True, row_factory=dict_row)
    try:
        yield connection
    finally:
        connection.close()


def _psql(cluster: Any, path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(cluster.bin / "psql"), "-X", "-h", str(cluster.socket), "-U", "postgres",
         "-d", "postgres", "-P", "pager=off", "-f", str(path)],
        capture_output=True, text=True, timeout=60,
    )


def _run(conn: Any):
    def run(sql: str, params: Any = ()) -> List[Dict[str, Any]]:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall()) if cur.description else []
    return run


# ---------------------------------------------------------------------------
# Task 4A: the starter blocks Nadia's in-limit credit; the solution does not
# ---------------------------------------------------------------------------


def _nadia(rule_path: Path, cents: int) -> str:
    rule = lab4.render_rule(rule_path.read_text())
    policies = lab4.baseline_set() + [(lab4.CREDIT_LIMIT_POLICY, rule)]
    return lab4.decide(policies, lab4.gateway_cedar_schema(), lab4.NADIA, cents).decision


def test_jessicas_seeded_case_is_exactly_the_limit(conn: Any) -> None:
    row = conn.execute("SELECT sum(amount_paid_cents) AS cents FROM pellier.orders "
                       "WHERE customer_id = %s AND return_status = 'received'",
                       (JESSICA,)).fetchone()
    assert row["cents"] == lab4.LIMIT_CENTS == 10000


def test_the_starter_blocks_nadias_approved_in_limit_credit() -> None:
    assert _nadia(STARTER_RULE, 10000) == lab4.DENY
    assert _nadia(STARTER_RULE, 9999) == lab4.DENY
    starter = STARTER_RULE.read_text()
    assert lab4.local_check(starter, starter).finding.state == lab4.check.NOT_YET


def test_the_solution_lets_it_through_and_denies_one_cent_more() -> None:
    assert _nadia(SOLUTION_RULE, 10000) == lab4.ALLOW
    assert _nadia(SOLUTION_RULE, 10001) == lab4.DENY
    result = lab4.local_check(SOLUTION_RULE.read_text(), STARTER_RULE.read_text())
    assert result.finding.state == lab4.check.PROVED
    assert [row[-1] for row in result.table] == ["matches"] * 7


# ---------------------------------------------------------------------------
# Task 4B: the RLS worksheet
# ---------------------------------------------------------------------------


def _live_state(conn: Any) -> Dict[str, Any]:
    policies = conn.execute("SELECT policyname, qual, with_check FROM pg_policies "
                            "WHERE schemaname = 'pellier' ORDER BY policyname").fetchall()
    probes = conn.execute("SELECT count(*) AS n FROM pellier.support_tickets "
                          "WHERE ticket_id LIKE 'TKT-LAB4-%'").fetchone()["n"]
    return {"policies": policies, "probe_tickets": probes}


def test_the_starter_predicate_hides_every_customers_own_rows(fresh_db: Any, conn: Any) -> None:  # noqa: F811
    before = _live_state(conn)
    done = _psql(fresh_db, RLS_STARTER)
    assert done.returncode != 0
    assert "Lab 4B check failed" in done.stdout
    for line in ("Theo reads his own orders", "Theo writes a ticket in his own name",
                 "The Investigator reads Jessica's orders"):
        assert next(row for row in done.stdout.splitlines() if line in row).rstrip().endswith(
            "differs"), line
    assert "rolled back" in done.stdout
    assert _live_state(conn) == before


def test_the_solution_passes_every_probe_and_keeps_nothing(fresh_db: Any, conn: Any) -> None:  # noqa: F811
    before = _live_state(conn)
    done = _psql(fresh_db, RLS_SOLUTION)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Lab 4B check passed" in done.stdout
    assert "10 of 10 probes match" in done.stdout
    assert "42501" in done.stdout
    assert _live_state(conn) == before


def test_an_everyone_predicate_fails_too(fresh_db: Any, tmp_path: Path) -> None:  # noqa: F811
    everyone = tmp_path / "lab-4-rls-true.sql"
    everyone.write_text(RLS_STARTER.read_text().replace(
        "SELECT $predicate$\n  false\n$predicate$", "SELECT $predicate$\n  true\n$predicate$"))
    done = _psql(fresh_db, everyone)
    assert done.returncode != 0
    assert "Theo reads Jessica's orders" in done.stdout and "Lab 4B check failed" in done.stdout


# ---------------------------------------------------------------------------
# The supplied absence check
# ---------------------------------------------------------------------------


def _jessicas_credit(conn: Any) -> str:
    """Nadia's approval of Jessica's real case, executed once, as the desk writes it."""
    from services import store_tools

    reason = "Two returned items, received"
    review = store_tools.open_credit_review(
        _run(conn), customer_id=JESSICA, amount_cents=10000, reason=reason,
        source_turn_id=None, requested_by_sub="sub-nadia", requester_kind="operator",
        order_ids=[20, 21])
    conn.execute("UPDATE pellier.approvals SET status = 'approved', decided_by = 'sub-nadia', "
                 "decided_at = now() WHERE id = %s", (review.id,))
    hash_ = conn.execute("SELECT action_hash FROM pellier.approvals WHERE id = %s",
                         (review.id,)).fetchone()["action_hash"]
    key = store_tools.execution_idempotency_key(review.id, hash_)
    result = store_tools.give_store_credit(_run(conn), customer_id=JESSICA, amount_cents=10000,
                                           reason=reason, idempotency_key=key,
                                           issued_by="sub-nadia")
    assert result["status"] == "success", result
    conn.execute("INSERT INTO pellier.tool_audit "
                 "(session_id, tool, caller, args, result, latency_ms) "
                 "VALUES ('turn-desk', 'give_store_credit', 'sub-nadia', %s::jsonb, "
                 "'{\"status\": \"success\"}', 7)", (json.dumps({"idempotency_key": key}),))
    return key


def test_the_absence_check_waits_for_the_probe_then_passes_on_0_0_1(fresh_db: Any,  # noqa: F811
                                                                      conn: Any) -> None:
    waiting = _psql(fresh_db, ABSENCE)
    assert waiting.returncode != 0
    assert "none yet: no approved review is named Lab 4 over-limit probe" in waiting.stdout

    with psycopg.connect(host=str(fresh_db.socket), port=5432, user="postgres",
                         dbname="postgres", row_factory=dict_row) as probe_conn:
        review = lab4.ensure_probe_review(probe_conn, staff_sub="sub-nadia", staff_name="nadia")
        again = lab4.ensure_probe_review(probe_conn, staff_sub="sub-nadia", staff_name="nadia")
    assert again["id"] == review["id"], "a second run reuses the same review and key"
    assert (review["status"], review["order_ids"], review["args"]["amount_cents"]) == (
        "approved", [], 10001)

    no_credit = _psql(fresh_db, ABSENCE)
    assert "none yet: Jessica has no store credit" in no_credit.stdout

    allowed_key = _jessicas_credit(conn)
    done = _psql(fresh_db, ABSENCE)
    assert done.returncode == 0, done.stdout + done.stderr
    assert f"denied key   {review['idempotency_key']}" in done.stdout
    assert f"allowed key  {allowed_key}" in done.stdout
    assert "Observed  0, 0 and 1" in done.stdout
    assert "Lab 4 absence check passed" in done.stdout

    conn.execute("INSERT INTO pellier.tool_audit "
                 "(session_id, tool, caller, args, result, latency_ms) "
                 "VALUES ('turn-x', 'give_store_credit', 'gateway', %s::jsonb, "
                 "'{\"status\": \"not_creditable\"}', 5)",
                 (json.dumps({"idempotency_key": review["idempotency_key"]}),))
    leaked = _psql(fresh_db, ABSENCE)
    assert leaked.returncode != 0
    assert "the denied key left rows behind" in leaked.stdout
