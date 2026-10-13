"""Lab 4B's live check: the stamp it reads, and the money role on both paths.

``scripts/lab4_credit_check.py`` first matches the live function's comment with
the statements in the participant's worksheet, then probes the role through the
in-process session and through the Lambda's ``run_as_credit_writer``. These
tests drive it against a fresh cluster after the solution worksheet commits; the
Gateway path runs over the same Data API stand-in the Operator tests use.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)
from tests.test_operator_credit_postgres import _conninfo, _DataApiOnPostgres, _PgDb

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
credit_check = importlib.import_module("lab4_credit_check")
SOLUTION = REPO / "solutions" / "the-concierge" / "sql" / "lab-4-credit-writer-solution.sql"
CLEAN = {"rights": credit_check.LIVE_RIGHTS, "execute": credit_check.LIVE_EXECUTE,
         "table_grants": 0, "policies": 0}


def test_the_stamp_is_the_sha256_of_the_statements_psql_hashes() -> None:
    stamp = credit_check.file_stamp(SOLUTION.read_bytes())
    assert stamp and stamp.startswith(credit_check.STAMP_PREFIX)
    assert credit_check.file_stamp(b"no quotes here") is None


@pytest.mark.parametrize(("is_starter", "live", "state", "observed"), [
    (True, {}, "NOT YET", "the worksheet still holds the starter's grants"),
    (False, {**CLEAN, "stamp": ""}, "NOT YET",
     "the live function still carries the privileges the database shipped with"),
    (False, {**CLEAN, "stamp": credit_check.STAMP_PREFIX + "0" * 64}, "NOT YET",
     "the live function carries different statements from the ones in your file"),
    (False, {**CLEAN, "table_grants": 3, "stamp": "MATCH"}, "CONTRADICTED",
     "the live state changed after your run: the role holds 3 table grants"),
    (False, {**CLEAN, "stamp": "MATCH"}, "PROVED", "the live function carries your statements"),
])
def test_the_deployed_verdict(is_starter: bool, live: dict, state: str, observed: str) -> None:
    stamp = credit_check.file_stamp(SOLUTION.read_bytes())
    live = {**live, "stamp": stamp} if live.get("stamp") == "MATCH" else live
    finding = credit_check.judge_deployed(stamp, is_starter, live)
    assert finding.state == state, finding
    assert finding.observed.startswith(observed), finding.observed


@pytest.fixture(scope="module")
def deployed(fresh_db: Any) -> Any:  # noqa: F811 - the imported fixture
    done = subprocess.run(
        [str(fresh_db.bin / "psql"), "-X", "-h", str(fresh_db.socket), "-U", "postgres",
         "-d", "postgres", "-P", "pager=off", "-f", str(SOLUTION)],
        capture_output=True, text=True, timeout=60,
    )
    assert "Lab 4B privileges check passed" in done.stdout, done.stdout + done.stderr
    return fresh_db


def test_the_live_function_carries_the_solutions_stamp(deployed: Any) -> None:
    def connect() -> Any:
        return psycopg.connect(**{**_conninfo(deployed), "row_factory": dict_row})

    finding = credit_check.deployed_finding(connect, worksheet=SOLUTION)
    assert finding.state == "PROVED", finding
    starter = credit_check.deployed_finding(connect)
    assert starter.state == "NOT YET" and "starter" in starter.observed


@pytest.mark.asyncio
async def test_the_in_process_path_holds_the_role_to_the_function(deployed: Any) -> None:
    async with await psycopg.AsyncConnection.connect(**_conninfo(deployed)) as aconn:
        observed = await credit_check.probe_in_process(_PgDb(aconn))
    assert observed == credit_check.WANT, observed
    assert credit_check.judge_path("in process", observed).state == "PROVED"


def test_the_gateway_path_holds_the_role_to_the_function(deployed: Any, monkeypatch) -> None:
    sys.path.insert(0, str(REPO / "scripts" / "deploy"))
    import common.dataapi as dataapi

    with psycopg.connect(**_conninfo(deployed)) as conn:
        monkeypatch.setattr(dataapi, "rds_client", _DataApiOnPostgres(conn))
        observed = credit_check.probe_gateway(dataapi)
    assert observed == credit_check.WANT, observed
    assert credit_check.judge_path("Gateway", observed).state == "PROVED"


@pytest.mark.asyncio
async def test_a_table_privilege_on_credits_is_caught_on_the_path(deployed: Any) -> None:
    """A role that may UPDATE credits answers 00000 to the direct write: contradicted."""
    with psycopg.connect(**_conninfo(deployed)) as conn:
        conn.execute("GRANT UPDATE ON pellier.store_credits TO pellier_credit_writer")
        try:
            async with await psycopg.AsyncConnection.connect(**_conninfo(deployed)) as aconn:
                observed = await credit_check.probe_in_process(_PgDb(aconn))
        finally:
            conn.execute("REVOKE UPDATE ON pellier.store_credits FROM pellier_credit_writer")
    finding = credit_check.judge_path("in process", observed)
    assert observed[credit_check.UPDATE] == "00000"
    assert finding.state == "CONTRADICTED" and "raise a credit's amount directly" in finding.observed
