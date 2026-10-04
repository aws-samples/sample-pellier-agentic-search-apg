"""Safety and parity checks for the local golden-journey helper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "seed_local_golden_journeys.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("seed_local_golden_journeys", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


seed = _load_script()


def test_hash_matches_the_store_write_path() -> None:
    """The seeded review's action hash is the one `store_tools` computes.

    The operation name is read from the seed script's own call so the check
    follows the script rather than restating its vocabulary.
    """
    import re

    from services.store_tools import write_request_hash

    match = re.search(
        r'write_request_hash\("(\w+)", THEO_ARGS\)', SCRIPT.read_text(encoding="utf-8")
    )
    assert match, "the seed script no longer hashes THEO_ARGS under a named operation"
    operation = match.group(1)

    assert seed.write_request_hash(operation, seed.THEO_ARGS) == (
        write_request_hash(operation, **seed.THEO_ARGS)
    )


@pytest.mark.parametrize("host", ["db.example.com", "10.0.1.25", "aurora.cluster"])
def test_remote_database_hosts_are_refused(host: str) -> None:
    with pytest.raises(SystemExit, match="non-loopback"):
        seed.require_local_target(host, "pellier_dev")


@pytest.mark.parametrize("database", ["pellier", "production", "postgres"])
def test_non_development_database_names_are_refused(database: str) -> None:
    with pytest.raises(SystemExit, match="must end in _dev"):
        seed.require_local_target("127.0.0.1", database)


def test_seed_writes_workflow_state_only() -> None:
    sql = seed.seed_sql().lower()
    assert "insert into pellier.approvals" in sql
    assert "insert into pellier.governed_turn_receipts" in sql
    assert "on conflict (customer_id, tool, action_hash)" in sql
    assert "do nothing" in sql
    assert "update pellier.approvals" not in sql
    assert "delete from pellier.approvals" not in sql
    for forbidden in (
        "insert into pellier.returns",
        "insert into pellier.store_credits",
        "insert into pellier.tool_audit",
        "insert into pellier.execution_receipts",
        "insert into pellier.governed_receipts",
    ):
        assert forbidden not in sql


def test_handoff_is_bound_to_the_review_and_explicitly_local() -> None:
    sql = seed.seed_sql()
    assert "UNTRUSTED_SHOPPER_CONTEXT" in sql
    assert "WAITING_FOR_HUMAN" in sql
    assert "'reviewId', v_review.id" in sql
    assert "'actionHash', v_review.action_hash" in sql
    assert '"managed":false' in sql
    assert "Existing immutable turn receipt has no handoff" in sql


def test_the_theo_review_is_seeded_once_across_its_whole_lifecycle() -> None:
    """Re-seeding must not stack a second copy once the first is decided.

    `approvals_open_per_action_idx` is a PARTIAL unique index scoped to live
    reviews, pending or approved (migration 020), so the statement's ON CONFLICT
    stops a duplicate only while the seeded review is live. Once it is declined
    the row leaves the index and the next seed run would insert another one. A
    box that had been reseeded twice showed two identical decided Theo returns
    in the Action Queue's history, which is why the guard cannot be the index
    alone.

    The source turn is the row's identity: the block immediately after the
    insert reads it back by exactly this value and calls it the canonical
    review.
    """
    sql = SCRIPT.read_text(encoding="utf-8")
    insert_at = sql.index("INSERT INTO pellier.approvals")
    statement = sql[insert_at : sql.index(";", insert_at)]

    assert "NOT EXISTS" in statement, (
        "the Theo review insert no longer guards on the canonical source turn, "
        "so a reseed after a decision will add a second copy"
    )
    assert "a.source_turn_id = '{SOURCE_TURN_ID}'" in statement or (
        f"a.source_turn_id = '{seed.SOURCE_TURN_ID}'" in statement
    )
    # The partial index still belongs there: it protects the running
    # application from two live reviews for one action, and the predicate must
    # name the index's own so PostgreSQL infers it.
    live = "WHERE status IN ('pending', 'approved')"
    assert f"ON CONFLICT (customer_id, tool, action_hash) {live}" in statement

