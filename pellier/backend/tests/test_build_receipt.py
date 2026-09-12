"""The build receipt must never blur "did not happen" with "did not look".

A receipt that reports an unreachable database as NOT YET tells a participant
they failed a lab they may well have passed, and tells a table lead to debug the
wrong thing. These tests pin that separation, and the related one in Lab 4:
a DENY receipt and the absence of an execution row are two facts, and
non-execution is only claimed when the row was actually searched for.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "build_receipt.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("pellier_build_receipt", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pellier_build_receipt"] = module
    spec.loader.exec_module(module)
    return module


receipt_module = _load()
PROVED = receipt_module.PROVED
NOT_YET = receipt_module.NOT_YET
UNCHECKED = receipt_module.UNCHECKED


class TestUncheckedIsNotFailure:
    def test_unreachable_database_reports_unchecked_not_not_yet(self) -> None:
        built = receipt_module.assemble(
            {"available": False, "reason": "connection refused"}
        )
        labs = built["labs"]
        assert labs["02_measure_hybrid_retrieval"]["hybrid_receipt"] == UNCHECKED
        assert labs["03_operate_the_managed_path"]["managed_rail"] == UNCHECKED
        assert labs["04_govern_and_prove"]["decisions"] == UNCHECKED
        # The reason travels with the receipt, so a reader can act on it.
        assert "connection refused" in built["evidence_source"]

    def test_reachable_database_with_no_rows_reports_not_yet(self) -> None:
        """The same absence, but now it is evidence."""
        built = receipt_module.assemble(
            {
                "available": True,
                "principal_sub": "sub-1",
                "lab1": None,
                "lab2": None,
                "lab3": None,
                "lab3_memory": None,
                "lab4": [],
            }
        )
        labs = built["labs"]
        assert labs["02_measure_hybrid_retrieval"]["hybrid_receipt"] == NOT_YET
        assert labs["03_operate_the_managed_path"]["managed_rail"] == NOT_YET
        assert labs["04_govern_and_prove"]["decisions"] == NOT_YET

    def test_rows_present_report_proved(self) -> None:
        built = receipt_module.assemble(
            {
                "available": True,
                "principal_sub": "sub-1",
                "lab1": {"audit_id": 4099, "turn_id": "turn-abc"},
                "lab2": {"receipt_id": 12, "reranked": True},
                "lab3": {"turn_id": "turn-abc", "rail": "gateway-mcp"},
                "lab3_memory": {"receipt_id": 12, "records": 3},
                "lab4": [],
            }
        )
        labs = built["labs"]
        assert labs["01_ground_the_answer"]["execution_row"] == PROVED
        assert labs["02_measure_hybrid_retrieval"]["hybrid_receipt"] == PROVED
        assert labs["03_operate_the_managed_path"]["managed_rail"] == PROVED
        assert labs["03_operate_the_managed_path"]["memory_informed_a_turn"] == PROVED


class TestGovernanceChain:
    """ALLOW, execution, durable effect and non-execution stay four claims."""

    @staticmethod
    def _findings(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return receipt_module._lab4_findings(rows)

    def test_allow_without_an_execution_row_is_not_a_durable_effect(self) -> None:
        found = self._findings(
            [
                {
                    "decision": "ALLOW",
                    "audit_id": None,
                    "completed_at": None,
                    "policy_name": "p",
                    "idempotency_key": None,
                }
            ]
        )
        assert found["allow_seen"] == PROVED
        assert found["allow_executed"] == NOT_YET
        assert found["durable_effect"] == NOT_YET

    def test_executed_allow_without_a_write_row_is_not_committed(self) -> None:
        """Reaching the tool is not the same as changing the system of record."""
        found = self._findings(
            [
                {
                    "decision": "ALLOW",
                    "audit_id": 4127,
                    "completed_at": None,
                    "policy_name": "p",
                    "idempotency_key": "k",
                }
            ]
        )
        assert found["allow_executed"] == PROVED
        assert found["durable_effect"] == NOT_YET

    @staticmethod
    def _deny(key: str | None, absence: dict[str, int] | None) -> dict[str, Any]:
        return {
            "decision": "DENY",
            "audit_id": None,
            "completed_at": None,
            "policy_name": "p",
            "idempotency_key": None,
            "declared_key": key,
            "absence": absence,
            "receipt_id": 1,
        }

    _CLEAN = {
        "execution_rows": 0,
        "write_rows": 0,
        "completed_writes": 0,
        "ledger_rows": 0,
    }

    def test_a_searched_key_found_nowhere_proves_non_execution(self) -> None:
        found = self._findings([self._deny("key-1", dict(self._CLEAN))])
        assert found["deny_seen"] == PROVED
        assert found["deny_did_not_execute"] == PROVED
        assert found["deny_absence_search"]["searched_key"] == "key-1"

    def test_a_deny_that_named_no_key_cannot_claim_absence(self) -> None:
        """A null audit_id is not a search. Nothing was looked for."""
        found = self._findings([self._deny(None, None)])
        assert found["deny_seen"] == PROVED
        assert found["deny_did_not_execute"] == UNCHECKED

    @pytest.mark.parametrize(
        "trace",
        ["execution_rows", "write_rows", "completed_writes", "ledger_rows"],
    )
    def test_any_trace_of_the_denied_key_contradicts_the_claim(
        self, trace: str
    ) -> None:
        """The audit's finding: a DENY whose own key completed scored PROVED.

        Each of the four tables an execution would touch has to be able to
        refute the claim on its own, because an execution that got far enough
        to write any one of them is an execution.
        """
        absence = dict(self._CLEAN)
        absence[trace] = 1
        found = self._findings([self._deny("key-1", absence)])
        assert found["deny_did_not_execute"] == receipt_module.CONTRADICTED
        assert found["deny_absence_search"][trace] == 1

    def test_a_contradiction_keeps_the_receipt_incomplete(self) -> None:
        built = receipt_module.assemble(
            {
                "available": True,
                "lab4": [self._deny("key-1", {**self._CLEAN, "completed_writes": 1})],
            }
        )
        assert built["complete"] is False
        assert any(
            "deny_did_not_execute: CONTRADICTED" in item
            for item in built["unproven"]
        )

    def test_no_rows_at_all_is_unchecked_when_the_database_was_unreachable(
        self,
    ) -> None:
        assert receipt_module._lab4_findings(None)["decisions"] == UNCHECKED


class TestSourceState:
    def test_a_fresh_checkout_reports_all_eight_builds_as_unwritten(self) -> None:
        """Two builds per lab, eight in all, every one shipping as a starter."""
        state = receipt_module.collect_source_state()
        assert len(state) == 8
        assert {entry["lab"] for entry in state.values()} == {
            "01_ground_the_answer",
            "02_measure_hybrid_retrieval",
            "03_operate_the_managed_path",
            "04_govern_and_prove",
        }
        for name, entry in state.items():
            assert entry["state"] == NOT_YET, f"{name} does not read as a starter"

    def test_every_build_flips_when_its_solution_is_the_source(self) -> None:
        """A detector that never says PROVED would pass the test above too."""
        solutions = {
            "1a_inventory_agent_defined":
                "solutions/waking-the-stock-keeper/agents/inventory_agent_solution.py",
            "1b_inventory_tool_written":
                "solutions/closing-marcos-gap/services/"
                "agent_tools_check_inventory_solution.py",
            "2a_rrf_expression_authored":
                "solutions/the-quiet-search/sql/lab-2-rrf-solution.sql",
            "2b_candidate_budget_authored":
                "solutions/the-quiet-search/retrieval/planned_hybrid_retrieval_solution.py",
            "3a_gateway_tool_published":
                "solutions/the-ledger/gateway/gateway_tool_schemas_solution.py",
            "3b_runtime_catalogue_reconciled":
                "solutions/the-ledger/services/agentcore_gateway.py",
            "4a_identity_rule_authored":
                "solutions/the-concierge/policies/identity_match_forbid.cedar",
            "4b_absence_query_authored":
                "solutions/the-ledger/observability/lab-4-absence-solution.sql",
        }
        for _lab, name, _path, region, markers in receipt_module._BUILDS:
            solution = receipt_module.REPO / solutions[name]
            assert solution.exists(), f"{name}: no solution at {solutions[name]}"
            stub = (
                receipt_module._region_reads_as_stub(solution, region, markers)
                if region
                else receipt_module._reads_as_stub(solution, markers)
            )
            assert receipt_module._source_state(stub) == PROVED, name

    def test_an_unreadable_file_is_unchecked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(receipt_module, "BACKEND", Path("/nonexistent"))
        monkeypatch.setattr(receipt_module, "REPO", Path("/nonexistent"))
        monkeypatch.setattr(
            receipt_module,
            "_BUILDS",
            tuple(
                (lab, name, Path("/nonexistent") / path.name, region, markers)
                for lab, name, path, region, markers in receipt_module._BUILDS
            ),
        )
        state = receipt_module.collect_source_state()
        assert all(entry["state"] == UNCHECKED for entry in state.values())


class TestReporting:
    def test_unproven_list_names_every_incomplete_claim(self) -> None:
        built = receipt_module.assemble({"available": False, "reason": "no db"})
        assert built["unproven"]
        assert built["complete"] is False
        # Every entry carries its state, so NOT YET and UNCHECKED stay legible
        # in the summary a participant actually reads.
        assert all(
            item.endswith(NOT_YET) or item.endswith(UNCHECKED)
            for item in built["unproven"]
        )

    def test_markdown_renders_and_explains_unchecked(self) -> None:
        built = receipt_module.assemble({"available": False, "reason": "no db"})
        markdown = receipt_module.render_markdown(built)
        assert "# Pellier build receipt" in markdown
        assert "Not yet proven" in markdown
        assert "not that the step failed" in markdown

    def test_markdown_reports_a_complete_run_without_a_scold(self) -> None:
        built = receipt_module.assemble(
            {
                "available": True,
                "principal_sub": "sub-1",
                "lab1": {"audit_id": 1},
                "lab2": {"receipt_id": 1},
                "lab3": {"turn_id": "t"},
                "lab3_memory": {"receipt_id": 1},
                "lab4": [
                    {
                        "decision": "ALLOW",
                        "audit_id": 2,
                        "completed_at": "now",
                        "policy_name": "p",
                        "idempotency_key": "k",
                    },
                    {
                        "decision": "DENY",
                        "audit_id": None,
                        "completed_at": None,
                        "policy_name": "p",
                        "idempotency_key": None,
                    },
                ],
            }
        )
        # Source state is still stubbed in this checkout, so the run is not
        # complete; assert the governance half instead, which is fully proved.
        lab4 = built["labs"]["04_govern_and_prove"]
        assert lab4["allow_executed"] == PROVED
        assert lab4["durable_effect"] == PROVED
        # This fixture's DENY names no idempotency key, so there is nothing to
        # search for and non-execution stays UNCHECKED rather than assumed.
        assert lab4["deny_did_not_execute"] == UNCHECKED


# ---------------------------------------------------------------------------
# Run scoping and the strict contract
# ---------------------------------------------------------------------------

RUN_ID = "run-0123456789ab"


class FakeCursor:
    def __init__(self, conn: "FakeConn") -> None:
        self.conn = conn
        self._rows: list = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self.conn.queries.append((sql, params))
        for fragment, rows in self.conn.rows.items():
            if fragment in sql:
                self._rows = list(rows)
                return
        self._rows = []

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> Any:
        return list(self._rows)


class FakeConn:
    def __init__(self, rows: dict[str, list]) -> None:
        self.rows = rows
        self.queries: list = []

    def __enter__(self) -> "FakeConn":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


def _env_file(tmp_path: Path) -> Path:
    env = tmp_path / ".env"
    env.write_text(
        "DB_HOST=db\nDB_NAME=pellier\nDB_USER=u\nDB_PASSWORD=p\n", encoding="utf-8"
    )
    return env


class TestRunScope:
    def test_a_run_id_scopes_every_lab_query(self, tmp_path: Path) -> None:
        conn = FakeConn({"to_regclass": [{"installed": "pellier.workshop_runs"}]})
        evidence = receipt_module.read_evidence(
            _env_file(tmp_path), "sub-1", run_id=RUN_ID, connect=lambda dsn: conn
        )
        assert evidence["available"] is True
        assert evidence["run_id"] == RUN_ID
        assert evidence["run_scope"] == "run_id"
        lab_queries = [(sql, params) for sql, params in conn.queries if "%(sub)s" in sql]
        assert len(lab_queries) == 5, [q[0][:40] for q in conn.queries]
        for sql, params in lab_queries:
            assert "%(run)s" in sql, sql
            assert params["run"] == RUN_ID
        # Policy receipts are stamped by the CLI; timestamps cannot claim
        # another participant's unattributed proof.
        lab4 = [sql for sql, _ in lab_queries if "governed_receipts gr" in sql][0]
        assert "gr.run_id = %(run)s" in lab4
        assert "gr.run_id IS NULL" not in lab4

    def test_the_default_connector_is_the_public_one(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Sibling scripts reach psycopg through a supported name, not a private one."""
        conn = FakeConn({})
        used: list = []

        def _connector() -> Any:
            used.append(True)
            return lambda dsn: conn

        monkeypatch.setattr(receipt_module, "psycopg_connector", _connector)
        evidence = receipt_module.read_evidence(_env_file(tmp_path), "sub-1")
        assert used == [True]
        assert evidence["available"] is True

    def test_without_a_run_id_nothing_is_scoped(self, tmp_path: Path) -> None:
        conn = FakeConn({})
        evidence = receipt_module.read_evidence(
            _env_file(tmp_path), "sub-1", connect=lambda dsn: conn
        )
        assert evidence["run_scope"] == "none"
        assert all("run_id" not in sql for sql, _ in conn.queries)

    def test_missing_migration_049_is_reported_and_left_unscoped(
        self, tmp_path: Path
    ) -> None:
        conn = FakeConn({"to_regclass": [{"installed": None}]})
        evidence = receipt_module.read_evidence(
            _env_file(tmp_path), "sub-1", run_id=RUN_ID, connect=lambda dsn: conn
        )
        assert evidence["run_id"] == RUN_ID
        assert evidence["run_scope"].startswith("unavailable")
        assert "049" in evidence["run_scope"]
        assert all("%(run)s" not in sql for sql, _ in conn.queries if "%(sub)s" in sql)

    def test_the_newest_principal_is_looked_up_inside_the_run(self, tmp_path: Path) -> None:
        conn = FakeConn(
            {
                "to_regclass": [{"installed": "pellier.workshop_runs"}],
                "MAX(created_at)": [{"principal_sub": "sub-9", "last_seen": "t"}],
            }
        )
        evidence = receipt_module.read_evidence(
            _env_file(tmp_path), None, run_id=RUN_ID, connect=lambda dsn: conn
        )
        # Named in the header, never bound into a lab filter. Marco's and
        # Anna's turns are anonymous, so filtering on the newest signed-in
        # identity discarded Labs 1 and 2 from a correctly finished run.
        assert evidence["principals"] == ["sub-9"]
        assert evidence["principal_sub"] == ""
        assert evidence["principal_filtered"] is False
        principal_sql = [sql for sql, _ in conn.queries if "MAX(created_at)" in sql][0]
        assert "run_id = %(run)s" in principal_sql

    def test_an_explicit_principal_is_the_only_thing_that_filters(
        self, tmp_path: Path
    ) -> None:
        conn = FakeConn({"to_regclass": [{"installed": "pellier.workshop_runs"}]})
        evidence = receipt_module.read_evidence(
            _env_file(tmp_path), "sub-diagnostic", run_id=RUN_ID,
            connect=lambda dsn: conn,
        )
        assert evidence["principal_filtered"] is True
        assert evidence["principal_sub"] == "sub-diagnostic"
        lab_params = [params for sql, params in conn.queries if "tool_audit" in sql]
        assert lab_params and all(p["sub"] == "sub-diagnostic" for p in lab_params)

    def test_the_receipt_carries_the_run(self) -> None:
        built = receipt_module.assemble(
            {"available": True, "run_id": RUN_ID, "run_scope": "run_id", "lab4": []}
        )
        assert built["run_id"] == RUN_ID
        assert built["run_scope"] == "run_id"
        assert f"`{RUN_ID}`" in receipt_module.render_markdown(built)


def _complete_evidence() -> dict[str, Any]:
    return {
        "available": True,
        "principal_sub": "sub-1",
        "run_id": RUN_ID,
        "run_scope": "run_id",
        "lab1": {"audit_id": 1},
        "lab2": {"receipt_id": 1},
        # A complete run's managed turn carries the fingerprint comparison,
        # so "the Runtime executed MY package" is answerable rather than
        # assumed from a successful invocation.
        "lab3": {
            "turn_id": "t",
            "rail": "gateway-mcp",
            "build_state": "current",
            "deployed_fingerprint": "abc123",
            "local_fingerprint": "abc123",
        },
        "lab3_memory": {"receipt_id": 1},
        "lab4": [
            {
                "decision": "ALLOW",
                "audit_id": 2,
                "completed_at": "now",
                "policy_name": "p",
                "idempotency_key": "k",
                "declared_key": "k",
            },
            {
                "decision": "DENY",
                "audit_id": None,
                "completed_at": None,
                "policy_name": "p",
                "idempotency_key": None,
                "declared_key": "k-denied",
                "receipt_id": 9,
                # The denied key, searched and found nowhere.
                "absence": {
                    "execution_rows": 0,
                    "write_rows": 0,
                    "completed_writes": 0,
                    "ledger_rows": 0,
                },
            },
        ],
    }


class TestStrict:
    @pytest.fixture(autouse=True)
    def _wired_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            receipt_module,
            "collect_source_state",
            lambda: {
                name: {"lab": lab, "state": PROVED}
                for lab, name, _p, _r, _m in receipt_module._BUILDS
            },
        )
        monkeypatch.setattr(receipt_module, "collect_provenance", lambda: {})

    def test_strict_exits_zero_only_when_every_claim_is_proved(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            receipt_module, "read_evidence", lambda env, sub, run_id=None: _complete_evidence()
        )
        assert receipt_module.main(["--strict", "--run-id", RUN_ID]) == 0
        assert "STRICT" not in capsys.readouterr().err

    def test_strict_prints_the_missing_keys_and_exits_one(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        evidence = _complete_evidence()
        evidence["lab3"] = None
        evidence["lab4"] = []
        monkeypatch.setattr(
            receipt_module, "read_evidence", lambda env, sub, run_id=None: evidence
        )
        assert receipt_module.main(["--strict", "--run-id", RUN_ID]) == 1
        err = capsys.readouterr().err
        assert RUN_ID in err
        assert "03_operate_the_managed_path.managed_rail: NOT YET" in err
        assert "04_govern_and_prove.deny_did_not_execute: NOT YET" in err

    def test_strict_refuses_a_receipt_that_could_not_be_scoped_to_the_run(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Every claim is PROVED, but off rows nobody can attribute to this run."""
        evidence = _complete_evidence()
        evidence["run_scope"] = receipt_module.RUN_SCOPE_UNAVAILABLE
        monkeypatch.setattr(
            receipt_module, "read_evidence", lambda env, sub, run_id=None: evidence
        )
        assert receipt_module.main(["--strict", "--run-id", RUN_ID]) == 1
        err = capsys.readouterr().err
        assert "049" in err
        assert RUN_ID in err

    def test_default_mode_still_exits_zero_when_the_run_scope_is_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        evidence = _complete_evidence()
        evidence["run_scope"] = receipt_module.RUN_SCOPE_UNAVAILABLE
        monkeypatch.setattr(
            receipt_module, "read_evidence", lambda env, sub, run_id=None: evidence
        )
        assert receipt_module.main(["--run-id", RUN_ID]) == 0
        assert "# Pellier build receipt" in capsys.readouterr().out

    def test_strict_without_a_run_id_refuses(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(receipt_module, "_resolve_run_id", lambda explicit: None)
        monkeypatch.setattr(
            receipt_module, "read_evidence", lambda env, sub, run_id=None: _complete_evidence()
        )
        assert receipt_module.main(["--strict"]) == 1
        assert "workshop-start" in capsys.readouterr().err

    def test_default_mode_still_exits_zero_on_an_incomplete_run(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        evidence = _complete_evidence()
        evidence["lab3"] = None
        monkeypatch.setattr(
            receipt_module, "read_evidence", lambda env, sub, run_id=None: evidence
        )
        assert receipt_module.main(["--run-id", RUN_ID]) == 0
        assert "# Pellier build receipt" in capsys.readouterr().out

    def test_a_malformed_run_id_is_refused_before_any_query(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert receipt_module.main(["--run-id", "run-nope"]) == 2
        assert "run-<12 hex>" in capsys.readouterr().err

    def test_the_current_run_is_the_default_scope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, Any] = {}

        def _read(env: Any, sub: Any, run_id: Any = None) -> dict[str, Any]:
            seen["run_id"] = run_id
            return _complete_evidence()

        monkeypatch.setattr(receipt_module, "read_evidence", _read)
        monkeypatch.setenv("PELLIER_RUN_ID", RUN_ID)
        assert receipt_module.main(["--json", "/dev/null"]) == 0
        assert seen["run_id"] == RUN_ID


# ---------------------------------------------------------------------------
# Lab 3: what the managed rail actually leaves behind
# ---------------------------------------------------------------------------

SUB = "sub-theo"

# ---------------------------------------------------------------------------
# The real engine, or none at all
# ---------------------------------------------------------------------------
# This used to be a SQLite harness. Its instinct was right -- ``FakeConn``
# answers by SQL fragment and cannot catch a predicate no real row satisfies --
# but SQLite is not the engine this SQL runs on, and the substitution hid a
# total failure: every lab query carried ``%(sub)s IS NULL OR col = %(sub)s``,
# which SQLite accepts and PostgreSQL rejects outright with
# ``could not determine data type of parameter $1``. The receipt could not read
# Aurora at all, and a green suite said otherwise.
#
# So: PostgreSQL or skip. A skipped test is honest about what it did not check;
# a passing test on the wrong engine is not.

_PG_DSN = os.environ.get("PELLIER_TEST_DSN") or os.environ.get("DATABASE_URL")


def _pg_connection() -> Any:
    """Open a scratch schema on a real PostgreSQL, or skip the test."""
    psycopg = pytest.importorskip("psycopg", reason="psycopg is required")
    if not _PG_DSN:
        pytest.skip("set PELLIER_TEST_DSN to run the receipt's SQL on PostgreSQL")
    try:
        conn = psycopg.connect(_PG_DSN, row_factory=psycopg.rows.dict_row)
    except Exception as exc:  # noqa: BLE001 - unreachable server is a skip
        pytest.skip(f"no PostgreSQL at PELLIER_TEST_DSN: {type(exc).__name__}: {exc}")
    return conn


@pytest.fixture()
def pg() -> Any:
    """A disposable ``pellier`` schema carrying only what these queries read."""
    conn = _pg_connection()
    schema = f"pellier_receipt_test_{uuid.uuid4().hex[:8]}"
    with conn.cursor() as cur:
        cur.execute(f'CREATE SCHEMA "{schema}"')
        cur.execute(f'SET search_path TO "{schema}"')
        cur.execute(
            "CREATE TABLE tool_audit (audit_id bigserial PRIMARY KEY, session_id text,"
            " tool text, caller text, args jsonb, result jsonb, latency_ms int,"
            " created_at timestamptz DEFAULT now(), run_id text)"
        )
        cur.execute(
            "CREATE TABLE governed_turn_receipts (turn_id text PRIMARY KEY,"
            " session_id text, principal_sub text,"
            " principal_verified boolean NOT NULL DEFAULT false,"
            " rail text, terminal_status text,"
            " trace jsonb DEFAULT '{}'::jsonb, created_at timestamptz DEFAULT now(),"
            " run_id text)"
        )
        cur.execute(
            "CREATE TABLE retrieval_receipts (receipt_id bigserial PRIMARY KEY,"
            " principal_sub text, turn_id text, query_preview text,"
            " embedding_model text, rerank_model text,"
            " retrieval_config jsonb DEFAULT '{}'::jsonb,"
            " latency_breakdown jsonb DEFAULT '{}'::jsonb, modeled_cost_usd numeric,"
            " citation_ids jsonb DEFAULT '[]'::jsonb,"
            " rerank_scores jsonb DEFAULT '{}'::jsonb,"
            " vector_ranks jsonb DEFAULT '{}'::jsonb,"
            " lexical_ranks jsonb DEFAULT '{}'::jsonb,"
            " rrf_scores jsonb DEFAULT '{}'::jsonb,"
            " memory_record_ids_used jsonb DEFAULT '[]'::jsonb,"
            " created_at timestamptz DEFAULT now(), run_id text)"
        )
        cur.execute(
            "CREATE TABLE governed_receipts (receipt_id bigserial PRIMARY KEY,"
            " audit_id bigint, principal_id text, tool text, caller text,"
            " decision text, args jsonb DEFAULT '{}'::jsonb, policy_engine_id text,"
            " policy_name text, verified_subject text, identity_source text,"
            " principal_label text,"
            " created_at timestamptz DEFAULT now(), run_id text)"
        )
        cur.execute(
            "CREATE TABLE write_operations (idempotency_key text PRIMARY KEY,"
            " operation text, completed_at timestamptz)"
        )
        cur.execute(
            "CREATE TABLE inventory_ledger (id bigserial PRIMARY KEY,"
            " idempotency_key text)"
        )
        cur.execute(
            "CREATE TABLE workshop_runs (run_id text PRIMARY KEY,"
            " started_at timestamptz DEFAULT now())"
        )
        cur.execute("INSERT INTO workshop_runs (run_id) VALUES (%s)", (RUN_ID,))
    conn.commit()
    conn.schema = schema  # type: ignore[attr-defined]
    try:
        yield conn
    finally:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(f'DROP SCHEMA "{schema}" CASCADE')
        conn.commit()
        conn.close()


def _run_lab_sql(conn: Any, sql: str, label: str, *, sub: Any, scoped: bool) -> Any:
    """Execute one of the receipt's real queries, unmodified, on PostgreSQL."""
    schema = conn.schema  # type: ignore[attr-defined]
    text = receipt_module._scoped(sql, label, scoped).replace("pellier.", f'"{schema}".')
    with conn.cursor() as cur:
        cur.execute(text, {"sub": sub, "run": RUN_ID})
        return cur.fetchall()


class TestEveryQueryParsesOnPostgres:
    """The regression the SQLite harness could not express.

    Each query is executed against a real server with both parameter shapes the
    tool actually uses: ``None`` (no ``--principal``, the default) and a subject
    string (the explicit diagnostic).
    """

    @pytest.mark.parametrize("sub", [None, SUB])
    @pytest.mark.parametrize("scoped", [True, False])
    def test_every_receipt_query_executes(self, pg: Any, sub: Any, scoped: bool) -> None:
        queries = (
            ("principals", receipt_module._RUN_PRINCIPALS),
            ("lab1", receipt_module._LAB1),
            ("lab2", receipt_module._LAB2),
            ("lab3", receipt_module._LAB3),
            ("lab3_memory", receipt_module._LAB3_MEMORY),
            ("lab4", receipt_module._LAB4),
        )
        for label, sql in queries:
            _run_lab_sql(pg, sql, label, sub=sub, scoped=scoped)

    def test_the_absence_probe_executes(self, pg: Any) -> None:
        schema = pg.schema
        with pg.cursor() as cur:
            cur.execute(
                receipt_module._DENY_ABSENCE.replace("pellier.", f'"{schema}".'),
                {"key": "k"},
            )
            row = cur.fetchone()
        assert row["execution_rows"] == 0
        assert row["completed_writes"] == 0


class TestAnonymousLabsSurviveTheDefaultScope:
    """Marco and Anna never sign in. Their evidence must still be found."""

    def test_a_four_persona_run_reports_every_lab(self, pg: Any) -> None:
        schema = pg.schema
        with pg.cursor() as cur:
            cur.execute(f'SET search_path TO "{schema}"')
            # Lab 1: anonymous.
            cur.execute(
                "INSERT INTO tool_audit (session_id, tool, caller, args, result, run_id)"
                " VALUES ('s1','check_inventory','inprocess',"
                " '{\"turn_id\":\"t1\"}'::jsonb,'{}'::jsonb,%s)", (RUN_ID,))
            cur.execute(
                "INSERT INTO governed_turn_receipts"
                " (turn_id, principal_sub, rail, terminal_status, run_id)"
                " VALUES ('t1', NULL, 'inprocess', 'complete', %s)", (RUN_ID,))
            # Lab 2: anonymous.
            cur.execute(
                "INSERT INTO retrieval_receipts (principal_sub, turn_id, vector_ranks,"
                " lexical_ranks, rrf_scores, run_id) VALUES (NULL,'t2',"
                " '{\"1\":1}'::jsonb,'{\"1\":2}'::jsonb,'{\"1\":0.9}'::jsonb,%s)",
                (RUN_ID,))
            # Lab 3: signed in, and newer.
            cur.execute(
                "INSERT INTO governed_turn_receipts"
                " (turn_id, principal_sub, rail, terminal_status, trace, run_id)"
                " VALUES ('t3',%s,'gateway-mcp','complete',"
                " '{\"buildState\":\"current\"}'::jsonb,%s)", (SUB, RUN_ID))
        pg.commit()

        lab1 = _run_lab_sql(pg, receipt_module._LAB1, "lab1", sub=None, scoped=True)
        lab2 = _run_lab_sql(pg, receipt_module._LAB2, "lab2", sub=None, scoped=True)
        assert lab1, "Marco's anonymous execution row was dropped"
        assert lab2, "Anna's anonymous retrieval receipt was dropped"

        # And the old behaviour, reproduced: filtering on the signed-in
        # identity discards both.
        assert not _run_lab_sql(pg, receipt_module._LAB1, "lab1", sub=SUB, scoped=True)
        assert not _run_lab_sql(pg, receipt_module._LAB2, "lab2", sub=SUB, scoped=True)


class _Lab3Rows:
    """Writes the rows the real writers produce, then runs the real Lab 3 SQL."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self._schema = conn.schema  # type: ignore[attr-defined]

    def turn(
        self,
        *,
        turn_id: str,
        run_id: str | None,
        rail: str = "gateway-mcp",
        trace: str = "{}",
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(f'SET search_path TO "{self._schema}"')
            cur.execute(
                "INSERT INTO governed_turn_receipts (turn_id, session_id,"
                " principal_sub, rail, terminal_status, trace, run_id)"
                " VALUES (%s,'lab3-start-1',%s,%s,'complete',%s::jsonb,%s)",
                (turn_id, SUB, rail, trace, run_id),
            )
        self._conn.commit()

    def gateway_mutation(self, *, audit_id: int, turn_id: str) -> None:
        """The row the MCP Lambda writes for a mutation. ``run_id`` is NULL."""
        with self._conn.cursor() as cur:
            cur.execute(f'SET search_path TO "{self._schema}"')
            cur.execute(
                "INSERT INTO tool_audit (audit_id, session_id, tool, caller, args,"
                " result, latency_ms, run_id) VALUES (%s,'gateway-CUST-THEO',"
                "'initiate_return','gateway',%s::jsonb,'{}'::jsonb,412,NULL)",
                (audit_id, json.dumps({"turn_id": turn_id})),
            )
        self._conn.commit()

    def lab3(self) -> Any:
        rows = _run_lab_sql(
            self._conn, receipt_module._LAB3, "lab3", sub=None, scoped=True
        )
        return rows[0] if rows else None


@contextlib.contextmanager
def _lab3_fixture(conn: Any) -> Any:
    yield _Lab3Rows(conn)


class TestLab3ManagedRailProof:
    """Lab 3 must be provable by completing Lab 3.

    Theo's journey ends at a pending review (``tests/golden/journeys.json``:
    ``endsAt: proposal``), so a correct Lab 3 run performs no mutation. Only the
    three mutation tools leave a ``caller = 'gateway'`` row, and Gateway reads
    leave no ``tool_audit`` row at all, so the rail proof has to be the turn
    receipt: written through the application pool, run-stamped by migration 049,
    and carrying the rail that served the turn.
    """

    def test_lab3_as_designed_yields_a_row_with_no_gateway_mutation(self, pg: Any) -> None:
        with _lab3_fixture(pg) as db:
            db.turn(turn_id="turn-theo-ceramics", run_id=RUN_ID)
            row = db.lab3()
        assert row is not None, "a managed turn with no mutation must still prove Lab 3"
        assert row["rail"] == "gateway-mcp"
        assert row["turn_id"] == "turn-theo-ceramics"
        assert row["gateway_mutation_audit_id"] is None

    def test_that_row_proves_the_managed_rail_in_the_receipt(self, pg: Any) -> None:
        with _lab3_fixture(pg) as db:
            db.turn(turn_id="turn-theo-ceramics", run_id=RUN_ID)
            row = db.lab3()
        built = receipt_module.assemble(
            {"available": True, "lab3": row, "lab3_memory": {"receipt_id": 1}, "lab4": []}
        )
        assert built["labs"]["03_operate_the_managed_path"]["managed_rail"] == PROVED

    def test_an_in_process_only_run_leaves_lab3_unproved(self, pg: Any) -> None:
        """The check cannot pass vacuously: an unswitched run still fails."""
        with _lab3_fixture(pg) as db:
            db.turn(turn_id="turn-in-process", run_id=RUN_ID, rail="in-process")
            row = db.lab3()
        assert row is None
        built = receipt_module.assemble(
            {"available": True, "lab3": row, "lab3_memory": None, "lab4": []}
        )
        assert built["labs"]["03_operate_the_managed_path"]["managed_rail"] == NOT_YET

    def test_another_runs_managed_turn_does_not_count(self, pg: Any) -> None:
        with _lab3_fixture(pg) as db:
            db.turn(turn_id="turn-someone-else", run_id="run-ffffffffffff")
            assert db.lab3() is None

    def test_a_gateway_mutation_is_reported_as_labelled_detail(self, pg: Any) -> None:
        """Present it as the optional mutation evidence it is, not as the proof."""
        with _lab3_fixture(pg) as db:
            db.turn(turn_id="turn-theo-return", run_id=RUN_ID)
            db.gateway_mutation(audit_id=4127, turn_id="turn-theo-return")
            row = db.lab3()
        assert row["gateway_mutation_audit_id"] == 4127
        built = receipt_module.assemble(
            {"available": True, "lab3": row, "lab3_memory": {"receipt_id": 1}, "lab4": []}
        )
        markdown = receipt_module.render_markdown(built)
        assert "gateway_mutation_audit_id=4127" in markdown

    def test_strict_counts_lab3_satisfied_without_any_gateway_row(
        self, pg: Any, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]
    ) -> None:
        with _lab3_fixture(pg) as db:
            db.turn(
                turn_id="turn-theo-ceramics", run_id=RUN_ID,
                trace='{"buildState":"current"}',
            )
            row = db.lab3()
        evidence = _complete_evidence()
        evidence["lab3"] = row
        monkeypatch.setattr(
            receipt_module,
            "collect_source_state",
            lambda: {
                name: {"lab": lab, "state": PROVED}
                for lab, name, _p, _r, _m in receipt_module._BUILDS
            },
        )
        monkeypatch.setattr(receipt_module, "collect_provenance", lambda: {})
        monkeypatch.setattr(
            receipt_module, "read_evidence", lambda env, sub, run_id=None: evidence
        )
        assert receipt_module.main(["--strict", "--run-id", RUN_ID]) == 0
        assert "STRICT" not in capsys.readouterr().err
