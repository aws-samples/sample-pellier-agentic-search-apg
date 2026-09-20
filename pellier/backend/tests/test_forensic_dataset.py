"""The forensic dataset must be readable from evidence alone.

Three turns, one business question, three enforcement outcomes. The
answer-key invariant is what these tests defend: every answer has to be
derivable from artifacts, with no instructor knowledge, no hidden logs, and no
assumption about what should have happened.

Two properties are easy to break and would quietly ruin the exercise:

  1. **The denied turn must have no execution row.** Its absence *is* the
     evidence that the tool never ran. Seeding one "for completeness" would
     make the ENFORCE case indistinguishable from the LOG_ONLY case.
  2. **Every `source` must name a place the evidence exists.** Claiming
     `governed_receipts` on a turn that has no row there sends a participant
     hunting for an artifact that was never written, which is the same failure
     as inventing one.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest


def _load_seeder():
    module_name = "seed_forensic_dataset_for_tests"
    if module_name in sys.modules:
        return sys.modules[module_name]
    script_path = (
        Path(__file__).resolve().parents[3] / "scripts" / "seed_forensic_dataset.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _turn_block(sql: str, turn_id: str) -> str:
    """Return the SQL between this turn's id and the next turn marker."""
    start = sql.index(turn_id)
    remainder = sql[start:]
    next_marker = re.search(r"-{10,} turn [A-C]", remainder[1:])
    return remainder[: next_marker.start()] if next_marker else remainder


# ---------------------------------------------------------------------------
# The three cases are distinct
# ---------------------------------------------------------------------------


def test_three_turns_cover_the_three_enforcement_outcomes():
    seeder = _load_seeder()
    sql = seeder.seed_sql()

    assert seeder.TURN_ALLOWED in sql
    assert seeder.TURN_ENFORCE_DENIED in sql
    assert seeder.TURN_LOG_ONLY in sql
    for verdict in ("'ALLOW'", "ALLOW", "DENY", "WOULD_DENY"):
        assert verdict in sql


def test_the_business_question_is_identical_across_turns():
    """Enforcement varies; the question must not."""
    seeder = _load_seeder()

    assert seeder.seed_sql().count("initiate_return") >= 3
    # One order, so "was this return allowed?" means the same thing each time.
    assert seeder.seed_sql().count("INSERT INTO pellier.orders") == 1


# ---------------------------------------------------------------------------
# The absence is the evidence
# ---------------------------------------------------------------------------


def test_the_denied_turn_writes_no_execution_row():
    """If the tool never ran, there must be no tool_audit row to find.

    Seeding one would make the ENFORCE denial indistinguishable from the
    LOG_ONLY case, where the tool *did* run.
    """
    seeder = _load_seeder()
    block = _turn_block(seeder.seed_sql(), seeder.TURN_ENFORCE_DENIED)

    assert "tool_audit" not in block, "the denied turn must leave no execution row"


def test_the_allowed_and_monitor_turns_do_write_execution_rows():
    """The contrast only works if the other two have one."""
    seeder = _load_seeder()
    sql = seeder.seed_sql()

    for turn in (seeder.TURN_ALLOWED, seeder.TURN_LOG_ONLY):
        assert "tool_audit" in _turn_block(sql, turn), turn


def test_the_denied_turn_uses_the_schema_state_for_denial_before_execution():
    """`denied-before-execution` states *when* the denial happened."""
    seeder = _load_seeder()
    block = _turn_block(seeder.seed_sql(), seeder.TURN_ENFORCE_DENIED)

    assert "denied-before-execution" in block


# ---------------------------------------------------------------------------
# Every source must be findable
# ---------------------------------------------------------------------------


def test_policy_event_sources_name_places_the_evidence_exists():
    """A source that names an absent table sends the reader nowhere."""
    seeder = _load_seeder()
    sql = seeder.seed_sql()

    allowed_block = _turn_block(sql, seeder.TURN_ALLOWED)
    denied_block = _turn_block(sql, seeder.TURN_ENFORCE_DENIED)
    monitor_block = _turn_block(sql, seeder.TURN_LOG_ONLY)

    # The allowed turn does write a governed_receipts row, so it may cite it.
    assert '"source": "governed_receipts"' in allowed_block
    assert "INSERT INTO pellier.governed_receipts" in allowed_block

    # The other two do not, so they must not cite it.
    assert '"source": "governed_receipts"' not in denied_block
    assert '"source": "governed_receipts"' not in monitor_block


def test_would_deny_is_not_written_to_governed_receipts():
    """`governed_receipts.decision` is constrained to ALLOW or DENY.

    A would-deny enforced neither, so it belongs in policy_events. Writing it
    to the receipts table fails the check constraint at seed time.
    """
    seeder = _load_seeder()
    monitor_block = _turn_block(seeder.seed_sql(), seeder.TURN_LOG_ONLY)

    assert "INSERT INTO pellier.governed_receipts" not in monitor_block
    assert "WOULD_DENY" in monitor_block


def test_governed_receipt_caller_is_the_managed_rail():
    """`governed_receipts.caller` is constrained to gateway or runtime."""
    seeder = _load_seeder()
    allowed_block = _turn_block(seeder.seed_sql(), seeder.TURN_ALLOWED)

    assert "'gateway', 'ALLOW'" in allowed_block
    assert "'agent', 'ALLOW'" not in allowed_block


def test_policy_events_is_valid_json():
    seeder = _load_seeder()

    payload = json.loads(seeder._policy_events("DENY", "monitor_mode", "p"))

    assert payload == [
        {"decision": "DENY", "source": "monitor_mode", "policy_name": "p"}
    ]


# ---------------------------------------------------------------------------
# Re-seeding must not make the exercise ambiguous
# ---------------------------------------------------------------------------


def test_turn_receipts_are_inserted_idempotently():
    """Append-only means the insert cannot delete-then-replace."""
    seeder = _load_seeder()

    assert seeder.seed_sql().count("ON CONFLICT (turn_id) DO NOTHING") == 3


def test_clear_does_not_attempt_to_delete_append_only_receipts():
    """Triggers reject DELETE on all three evidence tables (migrations 014,
    047); attempting one aborts the whole clear, so clear_sql() must not try.
    """
    seeder = _load_seeder()
    clear = seeder.clear_sql()

    for table in ("governed_turn_receipts", "governed_receipts", "tool_audit"):
        assert f"DELETE FROM pellier.{table}" not in clear
    # Theo has ordinary orders too. Clearing by customer would destroy them.
    assert "DELETE FROM" not in clear
    assert "RAISE EXCEPTION" in clear


def test_clear_is_scoped_to_the_seeded_customer():
    """A clear that removed unrelated orders would destroy real evidence."""
    seeder = _load_seeder()
    clear = seeder.clear_sql()

    assert seeder.PREFIX in clear
    assert "DELETE FROM pellier.orders;" not in clear


def test_seed_sql_guards_every_write_against_reseeding():
    """`governed_receipts` and `tool_audit` became append-only/fill-once in
    migration 047, so `clear_sql()` can no longer delete-then-reinsert them.
    Every write in `seed_sql()` must instead be conditioned on one up-front
    snapshot of whether the dataset already exists, or a rerun would double
    the orders/returns/tool_audit/governed_receipts rows.
    """
    seeder = _load_seeder()
    sql = seeder.seed_sql()

    assert "CREATE TEMP TABLE _forensic_already_seeded" in sql
    guard = "NOT EXISTS (SELECT 1 FROM _forensic_already_seeded WHERE v)"
    # Orders and both executions are gated; returns use only the exact new order.
    assert sql.count(guard) == 3
    assert 'FROM _forensic_order' in sql
    assert 'RETURNING id' in sql
    assert 'ORDER BY' not in sql
    assert "pg_advisory_xact_lock" in sql


def test_seed_ids_are_stable_so_an_answer_key_can_name_them():
    seeder = _load_seeder()

    assert seeder.TURN_ALLOWED == "turn-forensic-allowed"
    assert seeder.TURN_ENFORCE_DENIED == "turn-forensic-enforce-denied"
    assert seeder.TURN_LOG_ONLY == "turn-forensic-logonly-dual"


# ---------------------------------------------------------------------------
# Credential handling
# ---------------------------------------------------------------------------


def test_password_never_reaches_a_command_line(monkeypatch):
    seeder = _load_seeder()
    captured = {}

    def _fake_run(args, env=None, capture_output=None, text=None):
        captured["args"] = args
        captured["env"] = env

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr(seeder.subprocess, "run", _fake_run)
    secret = "p@ss|word*with]metachars"

    seeder._psql(
        {"DB_HOST": "h", "DB_NAME": "d", "DB_USER": "u", "DB_PASSWORD": secret},
        "SELECT 1",
    )

    assert secret not in " ".join(captured["args"])
    assert captured["env"]["PGPASSWORD"] == secret
    assert "-X" in captured["args"]


# ---------------------------------------------------------------------------
# main(): an already-seeded dataset cannot be cleared, only reported
# ---------------------------------------------------------------------------


def _stub_env(seeder, monkeypatch):
    monkeypatch.setattr(
        seeder,
        "_load_env",
        lambda: {"DB_HOST": "h", "DB_NAME": "d", "DB_USER": "u", "DB_PASSWORD": "p"},
    )


class _FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_already_seeded_dataset_is_a_pure_noop(monkeypatch):
    """Rerunning after a full seed must not call clear_sql or seed_sql:

    clear_sql() must preserve orders/returns, since deleting them while the
    append-only evidence still exists would strip the business state that
    evidence points at.
    """
    seeder = _load_seeder()
    _stub_env(seeder, monkeypatch)
    queries = []

    def _fake_psql(cfg, sql):
        queries.append(sql)
        return _FakeResult(stdout="1")  # governed_turn_receipts already has it

    monkeypatch.setattr(seeder, "_psql", _fake_psql)

    rc = seeder.main([])

    assert rc == 0
    assert len(queries) == 1, "only the already-seeded check should run"
    assert "governed_turn_receipts" in queries[0]
    assert seeder.PREFIX in queries[0]


def test_clear_refuses_once_the_dataset_is_seeded(monkeypatch):
    """`--clear` must refuse rather than silently strip orders/returns out
    from under evidence it can no longer remove.
    """
    seeder = _load_seeder()
    _stub_env(seeder, monkeypatch)

    monkeypatch.setattr(seeder, "_psql", lambda cfg, sql: _FakeResult(stdout="1"))

    rc = seeder.main(["--clear"])

    assert rc == 1


def test_clear_still_works_before_anything_is_seeded(monkeypatch):
    """On a fresh dataset, clear_sql() matches zero rows and must succeed."""
    seeder = _load_seeder()
    _stub_env(seeder, monkeypatch)
    queries = []

    def _fake_psql(cfg, sql):
        queries.append(sql)
        return _FakeResult(stdout="")  # nothing seeded yet

    monkeypatch.setattr(seeder, "_psql", _fake_psql)

    rc = seeder.main(["--clear"])

    assert rc == 0
    assert all("DELETE FROM" not in q for q in queries)


def test_fresh_run_seeds_without_deleting_existing_orders(monkeypatch):
    """A fresh seed adds its own order without deleting Theo's history."""
    seeder = _load_seeder()
    _stub_env(seeder, monkeypatch)
    queries = []

    def _fake_psql(cfg, sql):
        queries.append(sql)
        return _FakeResult(stdout="")

    monkeypatch.setattr(seeder, "_psql", _fake_psql)

    rc = seeder.main([])

    assert rc == 0
    assert len(queries) == 2  # read-only shortcut, atomic seed
    assert "governed_turn_receipts" in queries[0]
    assert all("DELETE FROM" not in q for q in queries)
    assert "_forensic_already_seeded" in queries[1]
