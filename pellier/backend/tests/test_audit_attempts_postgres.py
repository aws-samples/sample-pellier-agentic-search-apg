"""Lab 4's absence check and the Wrap-up reconstruction when a credit call failed before it applied.

Both rails write one audit row per attempt, so a transient failure and its successful retry leave
two rows for one write key, and the audit is append-only. The proofs count the row that applied the
credit and list the other attempt on its own line (review, 2026-10-22). This is a module of its own:
the neighbouring modules share one cluster per module and leave rows behind on purpose.
"""
from __future__ import annotations

import json

import psycopg
from psycopg.rows import dict_row

from tests.fresh_cluster import Cluster, fresh_db  # noqa: F401  (fixture import)
from tests.test_dba_worksheets_postgres import RECONSTRUCT, _jessica_chain, _worksheet
from tests.test_lab4_starter_failure import ABSENCE, _psql, lab4

FAILED = json.dumps({"error": "The requested action could not be completed."})


def test_a_failed_attempt_beside_the_applied_credit_keeps_both_proofs_passing(
        fresh_db: Cluster) -> None:  # noqa: F811
    chain = _jessica_chain(fresh_db, handoff_row=True)
    with psycopg.connect(host=str(fresh_db.socket), port=5432, user="postgres",
                         dbname="postgres", row_factory=dict_row) as conn:
        probe = lab4.ensure_probe_review(conn, staff_sub="sub-nadia")
        denial = lab4.attempt_for({"outcome": "deny", "cedar_denial": True},
                                  probe["idempotency_key"], {})
        lab4.record_probe_attempt(conn, probe["id"], denial)
        conn.execute("INSERT INTO pellier.tool_audit "
                     "(session_id, tool, caller, args, result, latency_ms) "
                     "VALUES ('gateway-CUST-JESSICA', 'give_store_credit', 'gateway', %s::jsonb, "
                     "%s::jsonb, 9)",
                     (json.dumps({"customer_id": "CUST-JESSICA", "idempotency_key": chain["key"]}),
                      FAILED))

    absence = _psql(fresh_db, ABSENCE)
    assert absence.returncode == 0, absence.stdout + absence.stderr
    assert "1 other attempt for this key did not apply; the audit keeps it." in absence.stdout
    assert "Lab 4 absence check passed" in absence.stdout

    story = _worksheet(fresh_db, RECONSTRUCT)
    assert story.returncode == 0, story.stdout + story.stderr
    assert "1 credit for this key, 1 audit row that applied it" in story.stdout
    assert "1 other attempt with the key did not apply; the audit keeps it." in story.stdout
    assert story.stdout.rstrip().endswith("Wrap-up reconstruction passed")
