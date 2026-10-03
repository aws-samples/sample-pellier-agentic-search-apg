"""The retired span object, and readiness that can see the evidence substrate.

Two things shipped invisibly
---------------------------

1. `pellier.agent_trace_spans` survived on the live cluster for weeks. The repository
   contract retires that name for every database object and
   `tests/test_surface_naming.py` scans the repository for it — but a scan of files
   cannot see a table, and readiness did not look.

2. Migration 026's outcome index was absent, so every governed execution raised a
   duplicate-key error on 024's index, the best-effort handler swallowed it, and three
   executions recorded no memories at all. Nothing failed and nothing reported it.

So readiness now checks the substrate an evidence reconstruction depends on, and this
file proves both the fresh chain and the stale-cluster convergence.
"""

from __future__ import annotations

import pathlib
import re

import pytest

MIGRATIONS = pathlib.Path("../../scripts/migrations")
DATABASE_SETUP = pathlib.Path("../../scripts/setup/database-setup.sh")
RETIRE = MIGRATIONS / "027_canonical_span_table.sql"


def _sql(path: pathlib.Path) -> str:
    """Statements only, so a comment explaining the retired name cannot satisfy a scan."""
    return "\n".join(
        line.split("--", 1)[0] for line in path.read_text().splitlines()
    )


# ---------------------------------------------------------------------------
# Migration 027: stale-cluster convergence
# ---------------------------------------------------------------------------


def test_the_migration_is_registered_after_the_others() -> None:
    body = DATABASE_SETUP.read_text()
    assert "027_canonical_span_table.sql" in body
    assert body.index("026_episode_outcome_lineage.sql") < body.index(
        "027_canonical_span_table.sql"
    )


def test_it_renames_when_the_canonical_target_is_absent() -> None:
    """Migration 002's intent was a rename, and 027 performs it without re-running 002."""
    sql = _sql(RETIRE)
    assert "ALTER TABLE pellier.agent_trace_spans RENAME TO observatory_spans" in sql
    # Including the indexes, so a converged cluster and a fresh one agree on every
    # identifier rather than differing by three index names.
    for index in ("session_idx", "created_idx", "pkey"):
        assert f"agent_trace_spans_{index}" in sql, index


def test_it_refuses_to_drop_span_rows() -> None:
    """Both tables present is a partial convergence, not a licence to discard data."""
    sql = _sql(RETIRE)
    assert "Refusing to drop span data" in RETIRE.read_text()
    assert "IF v_rows > 0 THEN" in sql
    assert "RAISE EXCEPTION" in sql


def test_it_is_a_no_op_on_a_converged_cluster() -> None:
    sql = _sql(RETIRE)
    assert "IF NOT v_retired THEN" in sql
    assert "RETURN;" in sql


def test_it_asserts_its_own_post_condition() -> None:
    body = RETIRE.read_text()
    assert "still exists after convergence" in body
    assert "is absent after convergence" in body
    assert "an index still carries the retired table name" in body


def test_it_does_not_rerun_migration_002() -> None:
    """A narrow forward migration, not a replay of a large telemetry one."""
    sql = _sql(RETIRE)
    assert "public" not in sql
    assert "SET SCHEMA" not in sql
    assert "pg_cron" not in sql


# ---------------------------------------------------------------------------
# Item 18: a fresh chain must never end with the retired name
# ---------------------------------------------------------------------------


def test_the_fresh_chain_creates_the_canonical_table() -> None:
    """002 creates `observatory_spans` outright, so a fresh stack is never wrong.

    This cluster was stale for a different reason: it ran 002 before the rename block
    existed and never ran it again.
    """
    sql = _sql(MIGRATIONS / "002_workshop_telemetry.sql")
    assert "CREATE TABLE IF NOT EXISTS pellier.observatory_spans" in sql


def test_no_migration_creates_the_retired_table() -> None:
    """The one thing that would make a fresh stack end up wrong."""
    for path in sorted(MIGRATIONS.glob("*.sql")):
        sql = _sql(path)
        assert not re.search(
            r"CREATE TABLE (IF NOT EXISTS )?pellier\.agent_trace_spans", sql
        ), path.name
        assert not re.search(
            r"RENAME TO agent_trace_spans", sql
        ), path.name


def test_only_the_two_sanctioned_migrations_name_the_retired_table() -> None:
    """002 relocates and renames it; 027 converges a stale cluster. Nothing else.

    The repository contract permits exactly the one-time convergence, so a third file
    reaching for that name is drift.
    """
    naming = [
        path.name for path in sorted(MIGRATIONS.glob("*.sql"))
        if "agent_trace_spans" in _sql(path)
    ]
    assert naming == [
        "002_workshop_telemetry.sql",
        "027_canonical_span_table.sql",
    ], naming


# ---------------------------------------------------------------------------
# Item 19: readiness sees the substrate
# ---------------------------------------------------------------------------


class FakeDb:
    def __init__(self, tables: set[str], *, index: bool = True,
                 fail: bool = False) -> None:
        self.tables = tables
        self.index = index
        self.fail = fail

    async def fetch_all(self, sql: str, *params):
        if self.fail:
            raise RuntimeError("no cluster")
        if "pg_indexes" in sql:
            return [{"indexname": "operator_episodes_outcome_idx"}] if self.index else []
        return [{"table_name": t} for t in sorted(self.tables)]


_CANONICAL = {
    "execution_receipts",
    "operator_episodes",
    "observatory_spans",
    "model_invocation_receipts",
    "evidence_ledger_event_refs",
}


@pytest.fixture
def substrate(monkeypatch: pytest.MonkeyPatch):
    from routes import observatory

    def _install(db):
        import app as app_module

        monkeypatch.setattr(app_module, "db_service", db, raising=False)
        return observatory._evidence_substrate_state

    return _install


@pytest.mark.asyncio
async def test_a_canonical_cluster_passes(substrate) -> None:
    state = await substrate(FakeDb(_CANONICAL))()
    assert state["state"] == "pass"
    assert "retired trace object is gone" in state["detail"]


@pytest.mark.asyncio
async def test_the_retired_table_is_a_release_blocker(substrate) -> None:
    state = await substrate(FakeDb(_CANONICAL | {"agent_trace_spans"}))()
    assert state["state"] == "fail"
    assert "run migration 027" in state["detail"]


@pytest.mark.asyncio
async def test_a_missing_receipt_table_is_a_release_blocker(substrate) -> None:
    """Without it a Cedar DENY has nowhere durable to live."""
    state = await substrate(FakeDb(_CANONICAL - {"execution_receipts"}))()
    assert state["state"] == "fail"
    assert "execution_receipts is missing" in state["detail"]


@pytest.mark.asyncio
async def test_a_missing_episode_table_is_a_release_blocker(substrate) -> None:
    state = await substrate(FakeDb(_CANONICAL - {"operator_episodes"}))()
    assert state["state"] == "fail"
    assert "operator_episodes is missing" in state["detail"]


@pytest.mark.asyncio
async def test_a_missing_outcome_index_is_a_release_blocker(substrate) -> None:
    """The exact live failure: executions succeed and silently remember nothing."""
    state = await substrate(FakeDb(_CANONICAL, index=False))()
    assert state["state"] == "fail"
    assert "operator_episodes_outcome_idx is missing" in state["detail"]
    assert "fail to record its episode" in state["detail"]


@pytest.mark.asyncio
async def test_a_missing_span_table_is_a_release_blocker(substrate) -> None:
    state = await substrate(FakeDb(_CANONICAL - {"observatory_spans"}))()
    assert state["state"] == "fail"
    assert "observatory_spans is missing" in state["detail"]


@pytest.mark.asyncio
async def test_a_missing_typed_ledger_projection_is_a_release_blocker(substrate) -> None:
    state = await substrate(FakeDb(_CANONICAL - {"evidence_ledger_event_refs"}))()
    assert state["state"] == "fail"
    assert "evidence_ledger_event_refs is missing" in state["detail"]


@pytest.mark.asyncio
async def test_a_missing_model_receipt_table_is_a_release_blocker(substrate) -> None:
    state = await substrate(FakeDb(_CANONICAL - {"model_invocation_receipts"}))()
    assert state["state"] == "fail"
    assert "model_invocation_receipts is missing" in state["detail"]


@pytest.mark.asyncio
async def test_no_cluster_is_a_warning_not_a_blocker(substrate) -> None:
    """A local clone with no database is legitimate.

    Reporting it as a release blocker teaches people to ignore the panel, which is how
    the two real blockers above stayed invisible.
    """
    state = await substrate(FakeDb(set(), fail=True))()
    assert state["state"] == "warn"


def test_the_check_is_wired_into_readiness() -> None:
    source = pathlib.Path("routes/observatory.py").read_text()
    assert 'check_id="evidence_substrate"' in source
    # And the checks that were already there stay there.
    assert 'check_id="managed_rail"' in source
    assert 'check_id="models"' in source
