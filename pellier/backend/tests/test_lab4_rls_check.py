"""Lab 4B, live: the shipped policies stop a wrong query on both database paths.

``scripts/lab4_rls_check.py`` binds Theo through each path's own code, the
in-process ``DatabaseService.principal_session`` and the store-tools Lambda's
``bind_runtime_principal`` over the Data API, then asks for Jessica's rows and
writes in her name. The cluster is a fresh one with the real migrations, so
the policies probed are the ones Pellier ships; the Data API is answered by the
cluster, as in the Operator credit tests.
"""

from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)
from tests.test_operator_credit_postgres import _conninfo, _DataApiOnPostgres

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "deploy"))
sys.path.insert(0, str(REPO / "scripts"))
lab4 = importlib.import_module("lab4_rls_check")

POLICIES = ("orders_owner ON pellier.orders", "support_tickets_owner ON pellier.support_tickets")


@pytest.fixture(scope="module")
def conn(fresh_db: Any) -> Iterator[psycopg.Connection]:  # noqa: F811 - the imported fixture
    with psycopg.connect(**_conninfo(fresh_db)) as connection:
        yield connection


def _theo_tickets(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(lab4.READS[0][1])
        return int(cur.fetchone()["n"])


async def _in_process(cluster: Any) -> dict:
    from services.database import DatabaseService

    info = _conninfo(cluster)
    conninfo = " ".join(f"{key}={info[key]}" for key in ("host", "port", "user", "dbname"))
    db = DatabaseService()
    db._pool = AsyncConnectionPool(conninfo, kwargs={"row_factory": dict_row}, open=False)
    await db._pool.open()
    db._is_connected = True
    try:
        return await lab4.probe_in_process(db)
    finally:
        await db._pool.close()


def _gateway(monkeypatch: pytest.MonkeyPatch, conn: psycopg.Connection) -> dict:
    import common.dataapi as dataapi

    monkeypatch.setattr(dataapi, "rds_client", _DataApiOnPostgres(conn))
    return lab4.probe_gateway(dataapi)


@contextmanager
def _policies(conn: psycopg.Connection, predicate: str) -> Iterator[None]:
    """Replace both live predicates for the duration, then put the shipped ones back."""
    with conn.cursor() as cur:
        cur.execute("SELECT policyname, qual, with_check FROM pg_policies "
                    "WHERE schemaname = 'pellier' AND policyname IN "
                    "('orders_owner', 'support_tickets_owner')")
        shipped = {row["policyname"]: row for row in cur.fetchall()}
    try:
        for policy in POLICIES:
            conn.execute(f"ALTER POLICY {policy} USING ({predicate}) WITH CHECK ({predicate})")
        yield
    finally:
        for policy in POLICIES:
            row = shipped[policy.split()[0]]
            conn.execute(f"ALTER POLICY {policy} USING ({row['qual']}) "
                         f"WITH CHECK ({row['with_check']})")


@pytest.mark.asyncio
async def test_the_shipped_policies_pass_on_both_paths_and_keep_nothing(
    fresh_db: Any, conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
) -> None:
    own = _theo_tickets(conn)
    assert own > 0, "the seed gives Theo tickets, or the own-rows probe proves nothing"

    in_process = lab4.judge_path("in process", await _in_process(fresh_db), own)
    gateway = lab4.judge_path("Gateway", _gateway(monkeypatch, conn), own)

    assert in_process.state == lab4.check.PROVED, in_process
    assert gateway.state == lab4.check.PROVED, gateway
    assert in_process.observed == gateway.observed == "4 of 4 probes match"
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM pellier.support_tickets "
                    "WHERE ticket_id = 'TKT-LAB4-LIVE'")
        assert cur.fetchone()["n"] == 0


@pytest.mark.asyncio
async def test_a_policy_that_lets_everyone_through_is_contradicted_on_both_paths(
    fresh_db: Any, conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
) -> None:
    own = _theo_tickets(conn)
    with _policies(conn, "true"):
        in_process = lab4.judge_path("in process", await _in_process(fresh_db), own)
        gateway = lab4.judge_path("Gateway", _gateway(monkeypatch, conn), own)

    for finding in (in_process, gateway):
        assert finding.state == lab4.check.CONTRADICTED, finding
        assert "Jessica's orders came back" in finding.observed
        assert "a new ticket in Jessica's name came back 00000" in finding.observed
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM pellier.support_tickets "
                    "WHERE ticket_id = 'TKT-LAB4-LIVE'")
        assert cur.fetchone()["n"] == 0, "a write the policy let through is still rolled back"


def test_a_path_that_could_not_read_is_named() -> None:
    finding = lab4.judge_path("Gateway", {}, 2)
    assert finding.state == lab4.check.CONTRADICTED
    assert "Theo's own tickets came back not read" in finding.observed
    assert "pg_policies" in finding.next_step


def test_a_write_that_failed_for_another_reason_is_unchecked_not_wrong() -> None:
    observed = {label: 0 for label, _sql in lab4.READS}
    observed[lab4.READS[0][0]] = 2
    observed[lab4.WRITE_LABEL] = f"{lab4.ERROR} 23503"
    finding = lab4.judge_path("in process", observed, 2)
    assert finding.state == lab4.check.UNCHECKED
    assert "a reason other than the policy" in finding.observed


def test_the_data_api_module_is_pointed_at_the_box_cluster_even_if_already_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import common.dataapi as dataapi

    # Recorded first, so teardown restores what _dataapi overwrites in the module and env.
    monkeypatch.setattr(dataapi, "DB_CLUSTER_ARN", "arn:aws:rds:us-west-2:111111111111:cluster:old")
    monkeypatch.setattr(dataapi, "SECRET_ARN", "old-secret")
    monkeypatch.setattr(dataapi, "DATABASE", "old")
    monkeypatch.setattr(dataapi, "rds_client", dataapi.rds_client)
    for key in ("DB_CLUSTER_ARN", "SECRET_ARN", "DATABASE", "DB_REGION", "REGION"):
        monkeypatch.setenv(key, "old")
    cluster = "arn:aws:rds:eu-west-1:222222222222:cluster:pellier"
    module = lab4._dataapi({"DB_CLUSTER_ARN": cluster, "DB_SECRET_ARN": "box-secret",
                            "DB_NAME": "pellier"})
    assert (module.DB_CLUSTER_ARN, module.SECRET_ARN, module.DATABASE) == (
        cluster, "box-secret", "pellier")
    assert module.rds_client.meta.region_name == "eu-west-1"


# ---------------------------------------------------------------------------
# Deployed: the live policies carry the predicate in the participant's file
# ---------------------------------------------------------------------------

SOLUTION = REPO / "solutions" / "the-concierge" / "sql" / "lab-4-rls-solution.sql"


def _stamp(worksheet: Path) -> str:
    stamp = lab4.file_stamp(worksheet.read_bytes())
    assert stamp and stamp.startswith("Lab 4B predicate sha256 ")
    return stamp


def test_a_starter_worksheet_is_not_yet_deployed() -> None:
    finding = lab4.judge_deployed(_stamp(SOLUTION), is_starter=True, deployed={})
    assert finding.state == lab4.check.NOT_YET
    assert "starter" in finding.observed
    assert "workshop/lab-4-rls.sql" in finding.next_step


def test_unstamped_policies_are_the_shipped_ones_not_yours() -> None:
    finding = lab4.judge_deployed(_stamp(SOLUTION), is_starter=False,
                                  deployed={"orders_owner": "", "support_tickets_owner": ""})
    assert finding.state == lab4.check.NOT_YET
    assert "shipped" in finding.observed
    assert "psql" in finding.next_step and "workshop/lab-4-rls.sql" in finding.next_step


def test_a_file_edited_after_it_was_deployed_is_named() -> None:
    old = "Lab 4B predicate sha256 " + "0" * 64
    finding = lab4.judge_deployed(_stamp(SOLUTION), is_starter=False,
                                  deployed={"orders_owner": old, "support_tickets_owner": old})
    assert finding.state == lab4.check.NOT_YET
    assert "different predicate" in finding.observed
    assert "again" in finding.next_step


def test_both_policies_carrying_the_file_stamp_is_proved() -> None:
    stamp = _stamp(SOLUTION)
    finding = lab4.judge_deployed(stamp, is_starter=False,
                                  deployed={"orders_owner": stamp, "support_tickets_owner": stamp})
    assert finding.state == lab4.check.PROVED
    assert stamp.rsplit(" ", 1)[1][:12] in finding.observed


def test_the_file_stamp_is_the_predicate_between_the_dollar_quotes_byte_for_byte() -> None:
    crlf = SOLUTION.read_bytes().replace(b"\n", b"\r\n")
    assert lab4.file_stamp(crlf) != _stamp(SOLUTION), "psql hashes the bytes it reads"
    assert lab4.file_stamp(b"no predicate region here") is None


def test_the_solution_worksheet_deploys_a_predicate_the_check_recognises(
    fresh_db: Any, conn: psycopg.Connection,  # noqa: F811
) -> None:
    import subprocess

    def deployed() -> dict:
        return lab4.deployed_policies(lambda: psycopg.connect(**_conninfo(fresh_db)))

    before = deployed()
    try:
        assert lab4.judge_deployed(_stamp(SOLUTION), False, {k: v["stamp"] for k, v in
                                                             before.items()}).state == lab4.check.NOT_YET
        done = subprocess.run(
            [str(fresh_db.bin / "psql"), "-X", "-h", str(fresh_db.socket), "-U", "postgres",
             "-d", "postgres", "-P", "pager=off", "-f", str(SOLUTION)],
            capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, done.stdout + done.stderr
        after = deployed()
        finding = lab4.judge_deployed(_stamp(SOLUTION), False,
                                      {k: v["stamp"] for k, v in after.items()})
        assert finding.state == lab4.check.PROVED, finding
        assert "cognito_username" in after["orders_owner"]["qual"]
    finally:
        for policy in POLICIES:
            row = before[policy.split()[0]]
            conn.execute(f"ALTER POLICY {policy} USING ({row['qual']}) "
                         f"WITH CHECK ({row['with_check']})")
            conn.execute(f"COMMENT ON POLICY {policy} IS NULL")
