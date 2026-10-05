"""The build receipt must never blur "did not happen" with "did not look".

A receipt that reports an unreachable database as NOT YET tells a participant
they failed a lab they may well have passed, and tells a table lead to debug the
wrong thing. These tests pin that separation, and run every evidence query on
the real schema (``tests/fresh_cluster.py``), because a query no real row can
satisfy is the failure a fake connection cannot show.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

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
CONTRADICTED = receipt_module.CONTRADICTED

BUILD = "b" * 64
CREDIT = {
    "credit_id": 1, "approval_id": 3, "customer_id": "CUST-JESSICA",
    "amount_cents": 10000, "approved_cents": 10000,
    "idempotency_key": "operator-review:3:" + "a" * 32,
    "credit_rows": 1, "audit_rows": 1,
}


def _evidence(**overrides: Any) -> dict[str, Any]:
    evidence = {
        "available": True,
        "lab1": {"receipt_id": 12},
        "lab2": {"audit_id": 4},
        "lab3": {"turn_id": "turn-abc", "deployed_fingerprint": BUILD},
        "lab4": dict(CREDIT),
    }
    evidence.update(overrides)
    return evidence


@pytest.fixture()
def local_build(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin this checkout's digest, so a comparison with BUILD is decidable."""
    monkeypatch.setattr(
        receipt_module, "collect_provenance", lambda: {"runtime_build_fingerprint": BUILD}
    )


class TestUncheckedIsNotFailure:
    def test_unreachable_database_reports_unchecked_not_not_yet(self) -> None:
        built = receipt_module.assemble({"available": False, "reason": "connection refused"})
        labs = built["labs"]
        assert labs["01_measure_hybrid_retrieval"]["hybrid_receipt"] == UNCHECKED
        assert labs["03_operate_the_managed_path"]["managed_rail"] == UNCHECKED
        assert labs["03_operate_the_managed_path"]["runtime_revision_is_yours"] == UNCHECKED
        assert labs["04_govern_and_prove"]["credit_recorded_once"] == UNCHECKED
        # The reason travels with the receipt, so a reader can act on it.
        assert "connection refused" in built["evidence_source"]

    def test_reachable_database_with_no_rows_reports_not_yet(self) -> None:
        built = receipt_module.assemble(
            {"available": True, "lab1": None, "lab2": None, "lab3": None, "lab4": None}
        )
        labs = built["labs"]
        assert labs["01_measure_hybrid_retrieval"]["hybrid_receipt"] == NOT_YET
        assert labs["02_ground_the_answer"]["execution_row"] == NOT_YET
        assert labs["03_operate_the_managed_path"]["managed_rail"] == NOT_YET
        assert labs["04_govern_and_prove"]["credit_recorded_once"] == NOT_YET

    def test_rows_present_report_proved(self, local_build: None) -> None:
        labs = receipt_module.assemble(_evidence())["labs"]
        assert labs["01_measure_hybrid_retrieval"]["hybrid_receipt"] == PROVED
        assert labs["02_ground_the_answer"]["execution_row"] == PROVED
        assert labs["03_operate_the_managed_path"]["managed_rail"] == PROVED
        assert labs["03_operate_the_managed_path"]["runtime_revision_is_yours"] == PROVED
        assert labs["04_govern_and_prove"]["credit_recorded_once"] == PROVED
        assert labs["04_govern_and_prove"]["approved_amount_recorded"] == PROVED


class TestTheExecutedBuild:
    def test_another_build_contradicts_the_claim(self, local_build: None) -> None:
        lab3 = receipt_module.assemble(
            _evidence(lab3={"turn_id": "turn-abc", "deployed_fingerprint": "c" * 64})
        )["labs"]["03_operate_the_managed_path"]
        assert lab3["managed_rail"] == PROVED
        assert lab3["runtime_revision_is_yours"] == CONTRADICTED

    def test_a_row_without_a_build_cannot_be_compared(self, local_build: None) -> None:
        lab3 = receipt_module.assemble(
            _evidence(lab3={"turn_id": "turn-abc", "deployed_fingerprint": None})
        )["labs"]["03_operate_the_managed_path"]
        assert lab3["runtime_revision_is_yours"] == UNCHECKED


class TestTheCredit:
    @pytest.mark.parametrize("change", [{"credit_rows": 2}, {"audit_rows": 0}, {"audit_rows": 2}])
    def test_anything_but_one_of_each_contradicts(self, change: dict) -> None:
        findings = receipt_module._lab4_findings({**CREDIT, **change}, True)
        assert findings["credit_recorded_once"] == CONTRADICTED

    def test_a_credit_for_another_amount_contradicts(self) -> None:
        findings = receipt_module._lab4_findings({**CREDIT, "amount_cents": 10001}, True)
        assert findings["approved_amount_recorded"] == CONTRADICTED


class TestSourceState:
    def test_a_fresh_checkout_reports_all_source_regions_as_unwritten(self) -> None:
        """Four labs, eight participant tasks, nine independently inspected source regions."""
        state = receipt_module.collect_source_state()
        assert len(state) == 9
        assert {entry["lab"] for entry in state.values()} == {
            "02_ground_the_answer",
            "01_measure_hybrid_retrieval",
            "03_operate_the_managed_path",
            "04_govern_and_prove",
        }
        for name, entry in state.items():
            assert entry["state"] == NOT_YET, f"{name} does not read as a starter"

    def test_each_region_detector_distinguishes_changed_missing_and_starter(self, tmp_path) -> None:
        """Source state is deliberately narrower than runtime verification."""
        for _, name, _, region, markers in receipt_module._BUILDS:
            source = tmp_path / (name + ".txt")
            header = f"# === WORKSHOP - {region}: START ===\n" if region else ""
            footer = f"# === WORKSHOP - {region}: END ===\n" if region else ""
            source.write_text(header + markers[0] + "\n" + footer)
            inspect = lambda: (receipt_module._region_reads_as_stub(source, region, markers)
                               if region else receipt_module._reads_as_stub(source, markers))
            assert inspect() is True
            source.write_text(header + "changed participant source\n" + footer)
            assert inspect() is False
            source.unlink()
            assert inspect() is None

    def test_an_unreadable_file_is_unchecked(self, monkeypatch: pytest.MonkeyPatch) -> None:
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
        assert all(
            item.endswith(NOT_YET) or item.endswith(UNCHECKED) for item in built["unproven"]
        )

    def test_markdown_renders_and_explains_unchecked(self) -> None:
        markdown = receipt_module.render_markdown(
            receipt_module.assemble({"available": False, "reason": "no db"})
        )
        assert "# Pellier build receipt" in markdown
        assert "Not yet proven" in markdown
        assert "not that the step failed" in markdown

    def test_markdown_names_the_executed_build_and_the_credit_key(self, local_build: None) -> None:
        markdown = receipt_module.render_markdown(receipt_module.assemble(_evidence()))
        assert f"Runtime build (executed): `{BUILD[:12]}` -- PROVED" in markdown
        assert f"`idempotency_key={CREDIT['idempotency_key']}`" in markdown


class TestStrict:
    @pytest.fixture(autouse=True)
    def _wired_source(self, monkeypatch: pytest.MonkeyPatch, local_build: None) -> None:
        monkeypatch.setattr(
            receipt_module,
            "collect_source_state",
            lambda: {
                name: {"lab": lab, "state": PROVED}
                for lab, name, _p, _r, _m in receipt_module._BUILDS
            },
        )

    def test_strict_exits_zero_only_when_every_claim_is_proved(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(receipt_module, "read_evidence", lambda env: _evidence())
        assert receipt_module.main(["--strict"]) == 0
        assert "STRICT" not in capsys.readouterr().err

    def test_strict_prints_the_missing_claims_and_exits_one(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            receipt_module, "read_evidence", lambda env: _evidence(lab3=None, lab4=None)
        )
        assert receipt_module.main(["--strict"]) == 1
        err = capsys.readouterr().err
        assert "03_operate_the_managed_path.managed_rail: NOT YET" in err
        assert "04_govern_and_prove.credit_recorded_once: NOT YET" in err

    def test_default_mode_still_exits_zero_on_an_incomplete_run(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(receipt_module, "read_evidence", lambda env: _evidence(lab3=None))
        assert receipt_module.main([]) == 0
        assert "# Pellier build receipt" in capsys.readouterr().out

    def test_an_unreadable_database_exits_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            receipt_module, "read_evidence", lambda env: {"available": False, "reason": "x"}
        )
        assert receipt_module.main(["--json", "/dev/null"]) == 1


# ---------------------------------------------------------------------------
# The real schema
# ---------------------------------------------------------------------------


class _Held:
    """One connection the receipt borrows without committing or closing it."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def __enter__(self) -> Any:
        return self.conn

    def __exit__(self, *exc: Any) -> bool:
        return False


@pytest.fixture()
def pg(fresh_db: Any, tmp_path: Path) -> Any:  # noqa: F811 - the imported fixture
    """A connection to the freshly built schema, rolled back after each test."""
    psycopg = pytest.importorskip("psycopg")
    from psycopg.rows import dict_row

    conn = psycopg.connect(
        host=str(fresh_db.socket), port=5432, user="postgres", dbname="postgres",
        row_factory=dict_row,
    )
    env = tmp_path / ".env"
    env.write_text("DB_HOST=h\nDB_NAME=n\nDB_USER=u\nDB_PASSWORD=p\n", encoding="utf-8")
    try:
        yield conn, env
    finally:
        conn.rollback()
        conn.close()


def _read(pg: Any) -> dict[str, Any]:
    conn, env = pg
    return receipt_module.read_evidence(env, connect=lambda dsn: _Held(conn))


def _execute(conn: Any, sql: str, *params: Any) -> Any:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone() if cur.description else None


class TestOnTheRealSchema:
    def test_a_fresh_database_has_no_lab_evidence(self, pg: Any) -> None:
        evidence = _read(pg)
        assert evidence["available"] is True, evidence
        assert all(evidence[lab] is None for lab in ("lab1", "lab2", "lab3", "lab4"))

    def test_the_rows_each_lab_leaves_are_found(self, pg: Any) -> None:
        conn, _ = pg
        _execute(conn, """
            INSERT INTO pellier.retrieval_receipts
                   (turn_id, query_hash, search_plan, vector_ranks, lexical_ranks, rrf_scores)
            VALUES ('turn-anna', 'h', '{}', '{"22": 1}', '{"22": 2}', '{"22": 0.03}')""")
        _execute(conn, """
            INSERT INTO pellier.tool_audit (session_id, tool, caller, args, result, latency_ms)
            VALUES ('s-marco', 'check_stock', 'stock', '{}', '{"status": "success"}', 40)""")
        _execute(conn, """
            INSERT INTO pellier.tool_audit
                   (session_id, tool, caller, args, result, latency_ms, build_fingerprint)
            VALUES ('turn-theo', 'get_tickets', 'gateway', '{"turn_id": "turn-theo"}',
                    '{"status": "success"}', 80, %s)""", BUILD)
        evidence = _read(pg)
        assert evidence["lab1"]["turn_id"] == "turn-anna"
        assert evidence["lab2"]["session_id"] == "s-marco"
        assert evidence["lab3"]["turn_id"] == "turn-theo"
        assert evidence["lab3"]["deployed_fingerprint"] == BUILD

    def test_an_executed_credit_is_found_by_its_own_key(self, pg: Any) -> None:
        conn, _ = pg
        args = {"customer_id": "CUST-JESSICA", "amount_cents": 10000,
                "reason": "Store credit for 2 returned items."}
        review = _execute(conn, """
            INSERT INTO pellier.approvals
                   (customer_id, tool, status, args, action_hash, order_ids,
                    decided_by, decided_at)
            VALUES ('CUST-JESSICA', 'give_store_credit', 'approved', %s::jsonb, %s,
                    ARRAY[20, 21]::bigint[], 'sub-nadia', now())
            RETURNING id""", json.dumps(args), "a" * 64)["id"]
        key = f"operator-review:{review}:{'a' * 32}"
        result = _execute(conn, "SELECT pellier.apply_store_credit(%s, %s, %s, %s) AS r",
                          key, "CUST-JESSICA", 10000, args["reason"])["r"]
        assert result["status"] == "success", result
        _execute(conn, """
            INSERT INTO pellier.tool_audit (session_id, tool, caller, args, result, latency_ms)
            VALUES ('operator-CUST-JESSICA', 'give_store_credit', 'sub-nadia', %s::jsonb,
                    %s::jsonb, 30)""", json.dumps({**args, "idempotency_key": key}),
                 json.dumps(result))
        evidence = _read(pg)
        assert evidence["lab4"]["idempotency_key"] == key
        findings = receipt_module._lab4_findings(evidence["lab4"], True)
        assert findings == {"credit_recorded_once": PROVED, "approved_amount_recorded": PROVED}
