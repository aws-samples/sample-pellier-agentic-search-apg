"""Execute the distributed takeaway SQL against a private local PostgreSQL cluster.

Run with the backend Python environment (psycopg) and PostgreSQL binaries on
PATH, or set PG_BIN. No application configuration or AWS credentials are read.
The stopped cluster goes to Trash when available; otherwise its path is printed.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

import psycopg

PACKAGE = Path(__file__).resolve().parents[1] / "takeaway" / "governed-postgres-agent"
QUERIES = dict(re.findall(
    r"-- query: (\w+)\n(.*?)\n-- end", (PACKAGE / "references/proof-queries.sql").read_text(), re.DOTALL
))
CALL = "SELECT review_example.apply_credit(%s, %s, %s, %s)"


class TakeawaySQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg = os.environ.get("PG_BIN")
        found = shutil.which("initdb")
        candidates = [Path(pg)] if pg else ([Path(found).resolve().parent] if found else [])
        if not pg:
            candidates.append(Path("/opt/homebrew/opt/postgresql@18/bin"))
        cls.bin = next((path for path in candidates if all(
            (path / name).is_file() for name in ("initdb", "postgres", "pg_ctl", "psql")
        )), None)
        if cls.bin is None:
            raise unittest.SkipTest("local PostgreSQL binaries required; set PG_BIN")
        cls.root = Path(tempfile.mkdtemp(prefix="dat416-takeaway-", dir="/tmp"))
        cls.socket = cls.root / "socket"
        cls.socket.mkdir(mode=0o700)
        cls.started = False
        cls.addClassCleanup(cls.cleanup_cluster)
        cls.env = {"PATH": str(cls.bin) + ":/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
        cls.command("initdb", "-D", cls.root / "data", "-U", "takeaway_admin",
                    "--auth=trust", "--no-locale", "--encoding=UTF8")
        cls.command("pg_ctl", "-D", cls.root / "data", "-l", cls.root / "server.log",
                    "-o", f"-c listen_addresses='' -k {cls.socket}", "-w", "start")
        cls.started = True
        cls.counter = 0
        with cls.connect("postgres") as conn:
            conn.execute("CREATE DATABASE takeaway_fixture")
        setup = (PACKAGE / "examples/setup.sql").read_text()
        setup = "\n".join(line for line in setup.splitlines() if not line.startswith("\\"))
        with cls.connect("takeaway_fixture") as conn:
            conn.execute(setup)

    @classmethod
    def command(cls, executable, *args):
        result = subprocess.run([str(cls.bin / executable), *map(str, args)],
                                env=cls.env, text=True, capture_output=True, timeout=30,
                                check=False)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return result

    @classmethod
    def connect(cls, database):
        return psycopg.connect(host=str(cls.socket), port=5432, user="takeaway_admin",
                               dbname=database, autocommit=True)

    @classmethod
    def cleanup_cluster(cls):
        if cls.started:
            cls.command("pg_ctl", "-D", cls.root / "data", "-m", "fast", "-w", "stop")
        trash = shutil.which("trash")
        if trash:
            subprocess.run([trash, str(cls.root)], check=True, capture_output=True)
        else:
            print(f"Stopped test cluster retained at {cls.root}")

    def setUp(self):
        type(self).counter += 1
        self.database = f"takeaway_case_{self.counter}"
        with self.connect("postgres") as conn:
            conn.execute(f"CREATE DATABASE {self.database} TEMPLATE takeaway_fixture")
        self.conn = self.connect(self.database)

    def tearDown(self):
        self.conn.close()
        with self.connect("postgres") as conn:
            conn.execute(f"DROP DATABASE {self.database}")

    def query(self, name, **variables):
        # psql substitutes variables in stdin, not in a -c SQL string.
        args = [str(self.bin / "psql"), "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                "-h", str(self.socket), "-U", "takeaway_admin", "-d", self.database]
        for key, value in variables.items():
            args.extend(["-v", f"{key}={value}"])
        result = subprocess.run(args, input=QUERIES[name], env=self.env, text=True,
                                capture_output=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip().splitlines()[-1]

    def call(self, key="approval:1", customer="customer-a", cents=2500, reason="travel", conn=None):
        connection = conn or self.conn
        connection.execute("SET ROLE review_writer")
        try:
            return connection.execute(CALL, (key, customer, cents, reason)).fetchone()[0]
        finally:
            connection.execute("RESET ROLE")

    def test_function_runs_as_writer_and_replay_has_one_credit_and_audit(self):
        first = self.call()
        second = self.call()
        self.assertEqual(first["status"], "success")
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(first["credit_id"], second["credit_id"])
        self.assertEqual(self.query("approval", write_key="approval:1"), "passed|1|0")
        self.assertEqual(self.query("committed_write", write_key="approval:1"), "passed|1|1")

    def test_worked_review_reproduces_defect_then_keeps_corrected_terms(self):
        self.command("psql", "-X", "-v", "ON_ERROR_STOP=1", "-h", self.socket,
                     "-U", "takeaway_admin", "-d", self.database,
                     "-f", PACKAGE / "examples/expense-review.sql")
        self.assertEqual(self.conn.execute("SELECT amount_cents FROM review_example.credits").fetchall(), [(2500,)])
        self.assertEqual(self.query("privileges"), "passed|0")
        self.assertEqual(self.query("approval", write_key="approval:1"), "passed|1|0")
        self.assertEqual(self.query("committed_write", write_key="approval:1"), "passed|1|1")

    def test_changed_retry_terms_conflict_without_another_write(self):
        self.call()
        for change in ({"cents": 5000}, {"reason": "other"}, {"customer": "customer-b"}):
            with self.subTest(change=change):
                self.assertEqual(self.call(**change)["status"], "idempotency_conflict")
        self.assertEqual(self.query("committed_write", write_key="approval:1"), "passed|1|1")

    def test_pending_and_missing_approval_cannot_write(self):
        for key in ("approval:3", "approval:404"):
            self.assertEqual(self.call(key=key)["status"], "approval_required")
        self.assertEqual(self.query("committed_write", write_key="approval:3"), "not tested|0|0")

    def test_missing_approved_amount_or_reason_is_refused(self):
        for args in ({"customer_id": "customer-a", "reason": "travel"},
                     {"customer_id": "customer-a", "amount_cents": 2500},
                     {"customer_id": "customer-a", "amount_cents": None, "reason": "travel"}):
            self.conn.execute("UPDATE review_example.approvals SET args = %s::jsonb WHERE id = 1", (json.dumps(args),))
            self.assertEqual(self.call()["status"], "approval_required")

    def test_database_ceiling_and_inclusive_boundary(self):
        self.conn.execute("UPDATE review_example.approvals SET args = jsonb_set(args, '{amount_cents}', '50001') WHERE id = 1")
        self.assertEqual(self.call(cents=50001)["status"], "invalid_terms")
        self.conn.execute("UPDATE review_example.approvals SET args = jsonb_set(args, '{amount_cents}', '50000') WHERE id = 1")
        self.assertEqual(self.call(cents=50000)["status"], "success")

    def test_second_approval_cannot_pay_same_expense_again(self):
        self.call()
        self.assertEqual(self.call(key="approval:2")["status"], "already_paid")

    def test_direct_table_update_is_denied(self):
        self.call()
        self.conn.execute("SET ROLE review_writer")
        try:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                self.conn.execute("UPDATE review_example.credits SET amount_cents = 50000")
        finally:
            self.conn.execute("RESET ROLE")

    def test_privilege_query_detects_public_access_and_repair(self):
        self.assertEqual(self.query("privileges"), "passed|0")
        self.conn.execute("GRANT UPDATE ON review_example.credits TO PUBLIC")
        self.assertEqual(self.query("privileges"), "failed|1")
        self.conn.execute("REVOKE UPDATE ON review_example.credits FROM PUBLIC")
        self.assertEqual(self.query("privileges"), "passed|0")

    def test_privilege_query_detects_inherited_access(self):
        self.conn.execute("GRANT SELECT ON review_example.credits TO review_support")
        self.conn.execute("GRANT review_support TO review_writer")
        try:
            self.assertTrue(self.conn.execute("SELECT has_table_privilege('review_writer', 'review_example.credits', 'SELECT')").fetchone()[0])
            self.assertTrue(self.query("privileges").startswith("failed|"))
        finally:
            self.conn.execute("REVOKE review_support FROM review_writer")

    def test_approval_proof_detects_missing_field_and_changed_reason(self):
        self.call()
        self.conn.execute("UPDATE review_example.approvals SET args = args - 'amount_cents' WHERE id = 1")
        self.assertEqual(self.query("approval", write_key="approval:1"), "failed|1|1")
        self.conn.execute("UPDATE review_example.approvals SET args = jsonb_set(args, '{amount_cents}', '2500') WHERE id = 1")
        self.conn.execute("UPDATE review_example.credits SET reason = 'changed'")
        self.assertEqual(self.query("approval", write_key="approval:1"), "failed|1|1")

    def test_approval_proof_reports_no_credit_as_untested(self):
        self.assertEqual(self.query("approval", write_key="approval:404"), "not tested|0|0")

    def test_existing_credit_without_audit_is_a_failure(self):
        self.call()
        self.conn.execute("DELETE FROM review_example.write_audit")
        self.assertEqual(self.query("committed_write", write_key="approval:1"), "failed|1|0")

    def test_retrieval_positive_and_dropped_constraints(self):
        self.assertEqual(self.query("retrieval", request_id="search-1"), "passed|1|0")
        self.conn.execute("UPDATE review_example.retrieval_receipts SET final_plan = '{}', returned_product_ids = ARRAY['candle']")
        self.assertEqual(self.query("retrieval", request_id="search-1"), "failed|1|1")

    def test_dropped_constraints_fail_even_with_a_lucky_eligible_result(self):
        self.conn.execute("UPDATE review_example.retrieval_receipts SET final_plan = '{}'")
        self.assertEqual(self.query("retrieval", request_id="search-1"), "failed|1|0")

    def test_retrieval_missing_product_fails_and_empty_evidence_cannot_pass(self):
        self.conn.execute("UPDATE review_example.retrieval_receipts SET returned_product_ids = ARRAY['missing']")
        self.assertEqual(self.query("retrieval", request_id="search-1"), "failed|1|1")
        self.conn.execute("UPDATE review_example.retrieval_receipts SET returned_product_ids = ARRAY[]::text[]")
        self.assertEqual(self.query("retrieval", request_id="search-1"), "not tested|0|0")
        self.conn.execute("DELETE FROM review_example.retrieval_receipts")
        self.assertEqual(self.query("retrieval", request_id="search-1"), "not tested|0|0")

    def test_stock_missing_warehouse_wrong_status_and_missing_evidence(self):
        self.assertEqual(self.query("stock", case_id="stock-1"), "passed|1")
        self.conn.execute("UPDATE review_example.stock_receipts SET result = jsonb_set(result, '{warehouses}', '[{\"name\":\"Austin\",\"quantity\":6}]') WHERE case_id = 'stock-1'")
        self.assertEqual(self.query("stock", case_id="stock-1"), "failed|1")
        self.assertEqual(self.query("stock", case_id="missing-1"), "passed|1")
        self.conn.execute("UPDATE review_example.stock_receipts SET result = '{\"status\":\"success\",\"quantity\":0}' WHERE case_id = 'missing-1'")
        self.assertEqual(self.query("stock", case_id="missing-1"), "failed|1")
        self.assertEqual(self.query("stock", case_id="absent"), "not tested|0")

    def test_ownership_positive_foreign_unbound_and_deny_everyone(self):
        self.assertEqual(self.query("ownership"), "passed")
        self.assertEqual(self.query("unbound"), "passed")
        self.conn.execute("ALTER POLICY ticket_owner ON review_example.tickets USING (false)")
        self.assertEqual(self.query("ownership"), "failed")

    def test_rls_write_has_a_positive_control_and_context_does_not_leak(self):
        self.conn.execute("BEGIN")
        self.conn.execute("SET LOCAL ROLE review_support")
        self.conn.execute("SELECT set_config('review_example.customer_id', 'customer-a', true)")
        self.conn.execute("INSERT INTO review_example.tickets VALUES ('own', 'customer-a', 'ok')")
        self.conn.execute("SAVEPOINT foreign_write")
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            self.conn.execute("INSERT INTO review_example.tickets VALUES ('foreign', 'customer-b', 'not ok')")
        self.conn.execute("ROLLBACK TO SAVEPOINT foreign_write")
        self.conn.execute("ROLLBACK")
        self.conn.execute("BEGIN")
        self.conn.execute("SET LOCAL ROLE review_support")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM review_example.tickets").fetchone()[0], 0)
        self.conn.execute("SELECT set_config('review_example.customer_id', 'customer-b', true)")
        self.assertEqual(self.conn.execute("SELECT ticket_id FROM review_example.tickets").fetchone()[0], "ticket-b")
        self.conn.execute("ROLLBACK")

    def race(self, second_key):
        outcome = {}
        with self.connect(self.database) as a, self.connect(self.database) as b:
            a.execute("BEGIN ISOLATION LEVEL READ COMMITTED")
            first = self.call(conn=a)
            def second():
                try:
                    b.execute("BEGIN ISOLATION LEVEL READ COMMITTED")
                    b.execute("SET LOCAL statement_timeout = '8s'")
                    outcome["result"] = self.call(key=second_key, conn=b)
                    b.execute("COMMIT")
                except Exception as exc:  # noqa: BLE001 - the thread reports any failure
                    outcome["error"] = repr(exc)
                    b.execute("ROLLBACK")
            thread = threading.Thread(target=second)
            thread.start()
            waited = False
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    waited = self.conn.execute("SELECT cardinality(pg_blocking_pids(%s)) > 0", (b.info.backend_pid,)).fetchone()[0]
                    if waited or "error" in outcome:
                        break
                    time.sleep(0.02)
            finally:
                a.execute("COMMIT")
                thread.join(10)
            self.assertTrue(waited, outcome)
            self.assertFalse(thread.is_alive())
            self.assertNotIn("error", outcome)
            self.assertEqual(self.conn.execute("SELECT count(*) FROM review_example.credits").fetchone()[0], 1)
            return first, outcome["result"]

    def test_concurrent_same_key_waits_and_replays(self):
        first, second = self.race("approval:1")
        self.assertTrue(second["replayed"])
        self.assertEqual(first["credit_id"], second["credit_id"])

    def test_concurrent_different_approvals_cannot_pay_same_expense_twice(self):
        _, second = self.race("approval:2")
        self.assertEqual(second["status"], "already_paid")


if __name__ == "__main__":
    unittest.main(verbosity=2)
