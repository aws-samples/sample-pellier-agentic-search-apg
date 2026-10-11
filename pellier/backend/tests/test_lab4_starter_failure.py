"""Lab 4's contract: the starters fail the way the guide's Spot step shows, the solutions do not.

Task 4A. Provisioning deploys the starter forbid, ``unless { false }``. Nadia
approves Jessica's in-limit credit (10000 cents, the seeded case) and the
starter still blocks it; with the solution it passes while 10001 cents is
denied. Decided by the real Cedar engine over the rendered baseline.

Task 4B. The RLS worksheet's starter expression is ``false``: Theo sees none of
his own rows and the Investigator none of Jessica's, so the check fails and the
transaction rolls back. The solution passes every probe, so it commits: the
solution's predicate becomes the live policy on both tables, stamped with its
sha256, and the probe writes are undone. A failing run never replaces what an
earlier passing run deployed. The keyed absence check is supplied: it reads the over-limit
review the Lab 4A check sent and Jessica's credit, and passes only on 0, 0, 1.

The worksheets run through ``psql`` on the real schema and seed.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List

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
FORENSIC = REPO / "solutions" / "the-ledger" / "sql" / "forensic_incident.sql"
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
    return lab4.decide(policies, lab4.gateway_cedar_schema(), lab4.NADIA,
                       lab4.GIVE_STORE_CREDIT_ACTION, lab4.credit_input(cents)).decision


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
    assert [row[-1] for row in result.table] == ["matches"] * 12


@pytest.mark.asyncio
@pytest.mark.parametrize(("rule_path", "label", "credits"), [
    (STARTER_RULE, "The Gateway answered: denied", 0),
    (SOLUTION_RULE, "The Gateway answered: allowed", 1),
], ids=["starter", "solution"])
async def test_nadias_execute_in_the_operator_shows_what_cedar_decided(
    fresh_db: Any, monkeypatch: pytest.MonkeyPatch, rule_path: Path, label: str,  # noqa: F811
    credits: int,
) -> None:
    """The Spot step at test level: the failure is visible in the Operator.

    Nadia executes Jessica's approved $100.00 credit through the Operator's
    execute route on the managed rail. The Gateway is a stand-in whose Cedar is
    the real engine over the rendered baseline and the rule; an allowed call
    runs the store-tools Lambda on this cluster. With the starter deployed the
    reloaded review reads "The Gateway answered: denied" and nothing is
    written; with the solution it reads "allowed" and one credit is written.
    """
    from config import settings
    from routes import operator as OP
    from services import governed_execution as ge
    from services import operator_review as rv
    from tests.test_operator_credit_postgres import (
        NADIA_SUB, _call_lambda, _clean_case, _conninfo, _investigate, _lambda, _order_id, _PgDb,
    )

    policies = lab4.baseline_set() + [
        (lab4.CREDIT_LIMIT_POLICY, lab4.render_rule(rule_path.read_text()))]
    schema = lab4.gateway_cedar_schema()
    with psycopg.connect(**_conninfo(fresh_db)) as sync:
        _clean_case(sync)
        module = _lambda(monkeypatch, sync)

        async def gateway_with_cedar(*, tool: str, args: Any, idempotency_key: str,
                                     access_token: str):
            tool_input = {**dict(args), "idempotency_key": idempotency_key}
            decided = lab4.decide(policies, schema, lab4.NADIA, ge.gateway_action_id(tool),
                                  tool_input)
            if decided.decision == lab4.DENY:
                said = ("Tool call not allowed due to policy enforcement "
                        f"[{', '.join(decided.decided_by)}]")
                return ge.POLICY_DENY, {"status": "policy_denied", "gateway_message": said}, said
            return ge.POLICY_ALLOW, _call_lambda(module, tool_input), "Cedar permitted it."

        async def enforcing(_row: Any) -> Any:
            return ge.PolicyEngineState(gateway_mode="ENFORCE")

        monkeypatch.setattr(settings, "WORKSHOP_FORMAT", "governed", raising=False)
        monkeypatch.setattr(settings, "AGENTCORE_GATEWAY_URL", "https://gw.example", raising=False)
        monkeypatch.setattr(settings, "AGENTCORE_POLICY_ENGINE_ID", "engine-1", raising=False)
        monkeypatch.setattr(ge, "_execute_through_gateway", gateway_with_cedar)
        monkeypatch.setattr(OP, "_policy_engine_state", enforcing)
        cases = [_order_id(sync, "42"), _order_id(sync, "25")]
        async with await psycopg.AsyncConnection.connect(**_conninfo(fresh_db)) as aconn:
            db = _PgDb(aconn)
            proposal = _investigate(sync, cases, "Both returns were received.")
            assert proposal["amount_cents"] == lab4.LIMIT_CENTS
            review_id = int(proposal["review_id"])
            row = await rv.get_review(db, review_id)
            await rv.decide_review(db, review_id=review_id, decision=rv.STATUS_CONFIRMED,
                                   decided_by=NADIA_SUB, action_hash=row["action_hash"],
                                   decided_by_name="nadia")
            nadia = {"sub": NADIA_SUB, "username": "nadia", "access_token": "jwt-nadia"}
            await OP.execute_review(OP.ReviewExecuteRequest(), review_id=review_id,
                                    operator=nadia, db=db)
            reloaded = (await OP.get_review(review_id, db=db))["review"]

        assert reloaded["execution"]["lastAttempt"]["label"] == label
        assert reloaded["assurance"]["policy"] == ("DENY" if credits == 0 else "ALLOW")
        assert reloaded["policyCheckProbe"] is False
        written = sync.execute("SELECT count(*) AS n FROM pellier.store_credits "
                               "WHERE approval_id = %s", (review_id,)).fetchone()
        assert written["n"] == credits
        _clean_case(sync)


# ---------------------------------------------------------------------------
# Task 4B: the RLS worksheet
# ---------------------------------------------------------------------------


STAMPS = """
SELECT pol.polname AS policy, coalesce(obj_description(pol.oid, 'pg_policy'), '') AS stamp
  FROM pg_policy pol
  JOIN pg_class c ON c.oid = pol.polrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'pellier' ORDER BY pol.polname
"""
SHIPPED = ("customer_id = (SELECT id FROM pellier.customers "
           "WHERE cognito_username = current_setting('pellier.principal_username', true))")
POLICY_TABLES = (("orders_owner", "orders"), ("support_tickets_owner", "support_tickets"))


def _live_state(conn: Any) -> Dict[str, Any]:
    policies = conn.execute("SELECT policyname, qual, with_check FROM pg_policies "
                            "WHERE schemaname = 'pellier' ORDER BY policyname").fetchall()
    probes = conn.execute("SELECT count(*) AS n FROM pellier.support_tickets "
                          "WHERE ticket_id LIKE 'TKT-LAB4-%'").fetchone()["n"]
    return {"policies": policies, "stamps": conn.execute(STAMPS).fetchall(),
            "probe_tickets": probes}


def _stamp_for(worksheet: Path) -> str:
    """The comment a passing worksheet leaves on both policies: its predicate's sha256."""
    predicate = worksheet.read_bytes().decode("utf-8").split("$predicate$")[1]
    return "Lab 4B predicate sha256 " + hashlib.sha256(predicate.encode("utf-8")).hexdigest()


def _with_predicate(tmp_path: Path, name: str, predicate: str) -> Path:
    path = tmp_path / name
    path.write_text(RLS_STARTER.read_text().replace(
        "SELECT $predicate$\n  false\n$predicate$", f"SELECT $predicate$\n  {predicate}\n$predicate$"))
    return path


@pytest.fixture
def shipped(conn: Any) -> Iterator[None]:
    """Each test starts and ends on the policies the migrations ship, unstamped."""
    def restore() -> None:
        for policy, table in POLICY_TABLES:
            conn.execute(f"ALTER POLICY {policy} ON pellier.{table} "
                         f"USING ({SHIPPED}) WITH CHECK ({SHIPPED})")
            conn.execute(f"COMMENT ON POLICY {policy} ON pellier.{table} IS NULL")
    restore()
    yield
    restore()


def test_the_starter_predicate_hides_every_customers_own_rows(  # noqa: F811
        fresh_db: Any, conn: Any, shipped: None) -> None:
    before = _live_state(conn)
    done = _psql(fresh_db, RLS_STARTER)
    assert done.returncode != 0
    assert "Lab 4B check failed" in done.stdout
    for line in ("Theo reads his own orders", "Theo writes a ticket in his own name",
                 "The Investigator reads Jessica's orders"):
        assert next(row for row in done.stdout.splitlines() if line in row).rstrip().endswith(
            "differs"), line
    assert "rolled back, the live policies are unchanged" in done.stdout
    assert _live_state(conn) == before


def test_the_solution_passes_every_probe_and_becomes_the_live_policy(  # noqa: F811
        fresh_db: Any, conn: Any, shipped: None) -> None:
    done = _psql(fresh_db, RLS_SOLUTION)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "10 of 10 probes match" in done.stdout
    assert "your predicate is now the live policy" in done.stdout
    assert "42501" in done.stdout and "Lab 4B check passed" in done.stdout
    after = _live_state(conn)
    stamp = _stamp_for(RLS_SOLUTION)
    owned = {row["policy"]: row["stamp"] for row in after["stamps"]}
    assert owned["orders_owner"] == owned["support_tickets_owner"] == stamp
    assert f"sha256 {stamp.rsplit(' ', 1)[1][:12]}" in done.stdout
    assert after["probe_tickets"] == 0, "the probe writes must not survive the commit"
    again = _psql(fresh_db, RLS_SOLUTION)
    assert again.returncode == 0 and _live_state(conn) == after


def test_an_everyone_predicate_fails_and_changes_nothing(  # noqa: F811
        fresh_db: Any, conn: Any, shipped: None, tmp_path: Path) -> None:
    before = _live_state(conn)
    done = _psql(fresh_db, _with_predicate(tmp_path, "lab-4-rls-true.sql", "true"))
    assert done.returncode != 0
    assert "Theo reads Jessica's orders" in done.stdout and "Lab 4B check failed" in done.stdout
    assert _live_state(conn) == before


def test_a_predicate_for_theo_and_jessica_only_fails_the_every_customer_probe(  # noqa: F811
        fresh_db: Any, conn: Any, shipped: None, tmp_path: Path) -> None:
    before = _live_state(conn)
    narrow = ("customer_id IN ('CUST-THEO', 'CUST-JESSICA') AND customer_id = (SELECT c.id "
              "FROM pellier.customers c WHERE c.cognito_username = "
              "current_setting('pellier.principal_username', true))")
    done = _psql(fresh_db, _with_predicate(tmp_path, "lab-4-rls-narrow.sql", narrow))
    assert done.returncode != 0, done.stdout
    row = next(r for r in done.stdout.splitlines() if "Customers who see exactly their own" in r)
    assert row.rstrip().endswith("differs")
    for line in ("Theo reads his own orders", "The Investigator reads Jessica's orders"):
        assert next(r for r in done.stdout.splitlines() if line in r).rstrip().endswith("matches")
    assert _live_state(conn) == before


def test_a_failing_run_keeps_the_predicate_an_earlier_run_deployed(  # noqa: F811
        fresh_db: Any, conn: Any, shipped: None, tmp_path: Path) -> None:
    assert _psql(fresh_db, RLS_SOLUTION).returncode == 0
    deployed = _live_state(conn)
    done = _psql(fresh_db, _with_predicate(tmp_path, "lab-4-rls-false.sql", "false"))
    assert done.returncode != 0 and "Lab 4B check failed" in done.stdout
    assert _live_state(conn) == deployed


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
                                                                      conn: Any,
                                                                      tmp_path: Path) -> None:
    waiting = _psql(fresh_db, ABSENCE)
    assert waiting.returncode != 0
    assert "none yet: no approved review is named Lab 4 over-limit probe" in waiting.stdout

    with psycopg.connect(host=str(fresh_db.socket), port=5432, user="postgres",
                         dbname="postgres", row_factory=dict_row) as probe_conn:
        review = lab4.ensure_probe_review(probe_conn, staff_sub="sub-nadia")
        again = lab4.ensure_probe_review(probe_conn, staff_sub="sub-nadia")
    assert again["id"] == review["id"], "a second run reuses the same review and key"
    assert (review["status"], review["order_ids"], review["args"]["amount_cents"]) == (
        "approved", [], 10001)
    # The check confirmed its own probe; no staff member is recorded as approving it.
    decided = conn.execute("SELECT decided_by, decided_by_name, requested_by_sub "
                           "FROM pellier.approvals WHERE id = %s", (review["id"],)).fetchone()
    assert decided == {"decided_by": "lab4-policy-check", "decided_by_name": "lab4-policy-check",
                       "requested_by_sub": "sub-nadia"}

    no_credit = _psql(fresh_db, ABSENCE)
    assert "none yet: Jessica has no store credit" in no_credit.stdout

    allowed_key = _jessicas_credit(conn)
    done = _psql(fresh_db, ABSENCE)
    assert done.returncode == 0, done.stdout + done.stderr
    assert f"denied key   {review['idempotency_key']}" in done.stdout
    assert f"allowed key  {allowed_key}" in done.stdout
    assert "Observed  0, 0 and 1" in done.stdout
    assert "Lab 4 absence check passed" in done.stdout

    # Both keys are derived the same way, so a derivation that drifted from the
    # desk's finds no allowed credit and fails, instead of two vacuous zeros.
    drifted = tmp_path / "lab-4-absence-drifted.sql"
    drifted.write_text(ABSENCE.read_text().replace("left(a.action_hash, 32)",
                                                   "left(a.action_hash, 31)"))
    vacuous = _psql(fresh_db, drifted)
    assert vacuous.returncode != 0
    assert "the allowed key does not find exactly one credit" in vacuous.stdout

    forensic = _psql(fresh_db, FORENSIC)
    assert forensic.returncode == 0, forensic.stderr
    assert "Lab 4 over-limit probe: covers no order" in forensic.stdout
    assert allowed_key in forensic.stdout and review["idempotency_key"] in forensic.stdout

    conn.execute("INSERT INTO pellier.tool_audit "
                 "(session_id, tool, caller, args, result, latency_ms) "
                 "VALUES ('turn-x', 'give_store_credit', 'gateway', %s::jsonb, "
                 "'{\"status\": \"not_creditable\"}', 5)",
                 (json.dumps({"idempotency_key": review["idempotency_key"]}),))
    leaked = _psql(fresh_db, ABSENCE)
    assert leaked.returncode != 0
    assert "the denied key left rows behind" in leaked.stdout
