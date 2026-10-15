"""The two read-only worksheets that show the agent from the database's side.

``workshop/lab-3-agent-workload.sql`` reads pg_stat_statements role by role after
Lab 3, and ``workshop/wrap-up-reconstruct.sql`` rebuilds Jessica's credit from her
request to the row at the Wrap-up. Both are supplied, so nothing here has a region:
these tests hold their shape (laptop width, read-only, one token) and the two
things each one depends on staying true in the source.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from services import store_tools

REPO = Path(__file__).resolve().parents[3]
WORKLOAD = REPO / "workshop" / "lab-3-agent-workload.sql"
RECONSTRUCT = REPO / "workshop" / "wrap-up-reconstruct.sql"
WORKSHEETS = (WORKLOAD, RECONSTRUCT)

WRITES = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|GRANT|REVOKE|TRUNCATE|COMMENT|COPY"
    r"|COMMIT|VACUUM|ANALYZE|REINDEX|CLUSTER|SELECT\s+pg_stat_statements_reset)\b",
    re.IGNORECASE)


def _statements(path: Path) -> list[str]:
    """The worksheet's lines with SQL comments and psql meta-commands removed."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        code = line.split("--", 1)[0]
        if code.strip() and not code.lstrip().startswith("\\"):
            lines.append(code)
    return lines


def _collapsed(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


@pytest.mark.parametrize("path", WORKSHEETS, ids=lambda p: p.name)
def test_every_line_fits_a_laptop_terminal(path: Path) -> None:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        assert len(line) < 120, f"{path.name}:{number} is {len(line)} columns"


@pytest.mark.parametrize("path", WORKSHEETS, ids=lambda p: p.name)
def test_the_worksheet_writes_nothing(path: Path) -> None:
    writes = [line for line in _statements(path) if WRITES.search(line)]
    assert writes == [], f"{path.name} writes: {writes}"


def test_the_workload_worksheet_reads_inside_one_rolled_back_transaction() -> None:
    """It switches role with SET LOCAL, which needs a transaction; the transaction
    is rolled back, so the switch and the bound name leave nothing behind."""
    code = [line.strip().upper() for line in _statements(WORKLOAD)]
    assert code.count("BEGIN;") == 1 and code.count("ROLLBACK;") == 1
    assert code.index("BEGIN;") < code.index("ROLLBACK;")
    assert "COMMIT;" not in code


def test_the_reconstruction_opens_no_transaction() -> None:
    code = [line.strip().upper() for line in _statements(RECONSTRUCT)]
    assert not any(line.startswith(("BEGIN", "SET LOCAL", "SET ROLE")) for line in code)


@pytest.mark.parametrize(("path", "prefix"), [
    (WORKLOAD, "Lab 3 workload check"),
    (RECONSTRUCT, "Wrap-up reconstruction"),
], ids=["workload", "reconstruct"])
def test_each_worksheet_ends_on_one_token(path: Path, prefix: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert f"\\echo '{prefix} passed'" in text
    assert f"\\echo '{prefix} failed'" in text


def test_the_workload_worksheet_says_unchecked_without_the_library() -> None:
    text = WORKLOAD.read_text(encoding="utf-8")
    assert "\\echo 'Lab 3 workload check unchecked'" in text
    assert "object_not_in_prerequisite_state" in text


@pytest.mark.parametrize(("marker", "sql"), [
    (r"FROM pellier\.orders o JOIN pellier\.product_catalog p", store_tools._ORDERS_SQL),
    (r"SELECT ticket_id, subject, status, channel, last_note", store_tools._TICKETS_SQL),
], ids=["get_orders", "get_tickets"])
def test_the_token_counts_the_tools_own_statements(marker: str, sql: str) -> None:
    """The pass token counts get_orders and get_tickets by their SQL, so the
    worksheet's markers must keep matching the statements the tools run. The
    row-ownership worksheet's own probes (also run as pellier_agent) must not."""
    assert f"'{marker}'" in WORKLOAD.read_text(encoding="utf-8")
    assert re.search(marker, _collapsed(sql))
    probes = (REPO / "workshop" / "lab-3-row-ownership.sql").read_text(encoding="utf-8")
    assert not re.search(marker, _collapsed(probes))


def test_the_bootstrap_installs_pg_stat_statements_in_public() -> None:
    schema = (REPO / "scripts" / "migrations" / "001_schema.sql").read_text(encoding="utf-8")
    assert "CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA public;" in schema
    assert schema.index("pg_stat_statements") < schema.index("CREATE SCHEMA pellier;")


def test_the_reconstruction_derives_the_key_the_operator_uses() -> None:
    """A key derived differently would find no audit row and no credit."""
    text = _collapsed(RECONSTRUCT.read_text(encoding="utf-8"))
    assert "'operator-review:' || a.id || ':' || left(a.action_hash, 32)" in text
    action_hash = "ab" * 32
    assert store_tools.execution_idempotency_key(41, action_hash) == (
        "operator-review:41:" + action_hash[:32])
