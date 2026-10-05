"""The evidence export: eight task lines, each never blurring "did not happen" with "did not look".

A line that reports an unreachable database as NOT YET tells a participant they
failed a task they may have passed. These tests pin that separation, the
starter rule for the lines whose proof runs the participant's source (a region
still holding its starter is never proved), and the Lab 1 and Lab 2 lines on
the real schema with the solutions in place. The source each test reads is the
starter or the solution twin, never the live checkout, so a box with the
solutions applied runs the same tests.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

import psycopg
import pytest
from psycopg.rows import dict_row

from tests import lab_variants
from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
evidence = importlib.import_module("workshop_evidence")
check = importlib.import_module("workshop_check")

PROVED, NOT_YET, UNCHECKED, CONTRADICTED = (
    check.PROVED, check.NOT_YET, check.UNCHECKED, check.CONTRADICTED)
TASKS = ["1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B"]
BUILD = "b" * 64
CREDIT = {
    "credit_id": 1, "approval_id": 3, "customer_id": "CUST-JESSICA",
    "amount_cents": 10000, "approved_cents": 10000,
    "idempotency_key": "operator-review:3:" + "a" * 32,
    "credit_rows": 1, "audit_rows": 1,
}


def _no_database(_cfg: Dict[str, str]) -> Any:
    raise AssertionError("no connection should be opened without settings")


@pytest.fixture(autouse=True)
def _no_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hermetic DB_* placeholders would read as settings; these tests name their own."""
    for key in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"):
        monkeypatch.delenv(key, raising=False)


# The lines a durable row proves read no source: with no database they cannot look.
ROW_TASKS = {"1B", "2A", "2B", "3B"}


@pytest.fixture()
def starters(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every source the export reads holds its starter, whatever the live checkout holds."""
    regions = {}
    for key, (_live, label, starter) in evidence.REGIONS.items():
        text = starter.read_text(encoding="utf-8")
        if check.region_body(text, label) is None:
            marker = f"# === WORKSHOP - {label}: {{}} ==="
            text = f"{marker.format('START')}\n{text}{marker.format('END')}\n"
        copy = tmp_path / f"starter-{key}{starter.suffix}"
        copy.write_text(text, encoding="utf-8")
        regions[key] = (copy, label, starter)
    monkeypatch.setattr(evidence, "REGIONS", regions)
    monkeypatch.setattr(evidence, "CEDAR_POLICY", evidence.CEDAR_STARTER)


class TestTheEightLines:
    def test_starters_are_not_yet_and_row_lines_without_a_database_are_unchecked(
        self, tmp_path: Path, starters: None,
    ) -> None:
        findings = evidence.collect(tmp_path / "absent.env", connect=_no_database)
        assert [finding.task for finding in findings] == TASKS
        for finding in findings:
            expected = UNCHECKED if finding.task in ROW_TASKS else NOT_YET
            assert finding.state == expected, finding

    def test_no_settings_is_unchecked_once_the_regions_are_edited(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(evidence, "source_state", lambda key: check.EDITED)
        findings = {f.task: f for f in evidence.collect(tmp_path / "absent.env",
                                                        connect=_no_database)}
        for task in ("1A", "1B", "2A", "2B"):
            assert findings[task].state == UNCHECKED, findings[task]
            assert "no database settings" in findings[task].evidence[0]

    def test_the_report_prints_three_things_per_line(self, tmp_path: Path, starters: None) -> None:
        report = evidence.render_report(evidence.collect(tmp_path / "absent.env",
                                                         connect=_no_database))
        assert report.count("\nTask ") == 8
        assert report.count("  Expected  ") == 8
        assert report.count("  Observed  ") == 8
        assert report.count("  Evidence  ") == 8
        assert "0 of 8 tasks proved" in report

    def test_save_writes_the_report(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                    capsys: pytest.CaptureFixture[str]) -> None:
        monkeypatch.setattr(evidence, "collect", lambda: [])
        target = tmp_path / "nested" / "evidence.txt"
        assert evidence.main(["--save", str(target)]) == 0
        assert target.read_text(encoding="utf-8").startswith("Pellier workshop evidence")
        assert "Pellier workshop evidence" in capsys.readouterr().out


class TestRegionState:
    def test_starter_edited_and_missing(self, tmp_path: Path) -> None:
        starter = tmp_path / "starter.pyfrag"
        starter.write_text("    return 0\n", encoding="utf-8")
        live = tmp_path / "live.py"
        marker = "# === WORKSHOP - Thing - body: {} ==="
        live.write_text(f"{marker.format('START')}\n    return 0\n{marker.format('END')}\n")
        assert check.region_state(live, "Thing - body", starter) == check.STARTER
        live.write_text(f"{marker.format('START')}\n    return 1\n{marker.format('END')}\n")
        assert check.region_state(live, "Thing - body", starter) == check.EDITED
        live.write_text("no markers\n")
        assert check.region_state(live, "Thing - body", starter) == check.MISSING

    def test_a_whole_file_starter_compares_its_own_region(self) -> None:
        live, label, starter = evidence.REGIONS["1A"]
        assert check.region_state(lab_variants.LAB1_RRF["solution"], label, starter) == check.EDITED
        assert check.region_state(starter, label, starter) == check.STARTER


class TestTheWorksheetVerdict:
    PASSED = ("Lab 1A: recompute\nEvidence  receipt 7 in session persona-anna-x\n"
              "          query: 'gift'\nObserved  9 of 9 scores match\nLab 1A check passed\n")

    def test_passed(self) -> None:
        finding = evidence.read_worksheet(self.PASSED, "")
        assert finding.state == PROVED
        assert finding.observed == "9 of 9 scores match"
        assert finding.evidence == ["receipt 7 in session persona-anna-x", "query: 'gift'"]

    def test_failed(self) -> None:
        out = self.PASSED.replace("9 of 9", "3 of 9").replace("passed", "failed")
        assert evidence.read_worksheet(out, "ERROR: Lab 1A check failed").state == CONTRADICTED

    @pytest.mark.parametrize("observed", [
        "none yet: no pellier.retrieval_receipts row has a session starting persona-anna-",
        "none yet: no product in receipt 7 is in one list only, so it cannot tell a missing "
        "rank apart",
    ])
    def test_a_receipt_that_cannot_decide_is_not_yet(self, observed: str) -> None:
        out = f"Observed  {observed}\nLab 1A check not yet\n"
        finding = evidence.read_worksheet(out, "ERROR:  Lab 1A check not yet")
        assert finding.state == NOT_YET
        assert finding.observed == observed

    def test_a_worksheet_that_did_not_finish_is_unchecked(self) -> None:
        finding = evidence.read_worksheet("", "psql: error: connection refused")
        assert finding.state == UNCHECKED
        assert finding.evidence == ["psql: error: connection refused"]


def _remembered(state: str = PROVED):
    """Stands in for ``lab3_check.memory_finding``, which reads AgentCore Memory."""
    return lambda: check.Finding("3B", "the managed agent is given Theo's remembered taste",
                                 state, "expected", "observed",
                                 ["record mem-theo-1: Prefers hand-thrown ceramics"])


class TestLabsThreeAndFour:
    BUILD_ROW = {"audit_id": 4, "turn_id": "turn-abc", "tool": "get_tickets",
                 "deployed_fingerprint": BUILD}
    THEO_READ = {"audit_id": 4, "turn_id": "turn-abc", "customer_id": "CUST-THEO"}

    def test_the_executed_build_and_reads_decide_3b(self) -> None:
        rows = {"build": self.BUILD_ROW, "tickets": [self.THEO_READ]}
        assert evidence.task_3b(rows, BUILD, _remembered()).state == PROVED
        assert evidence.task_3b(rows, "c" * 64, _remembered()).state == CONTRADICTED
        unstamped = {**rows, "build": {**self.BUILD_ROW, "deployed_fingerprint": None}}
        assert evidence.task_3b(unstamped, BUILD, _remembered()).state == UNCHECKED
        assert evidence.task_3b({"build": None, "tickets": []}, BUILD,
                                _remembered()).state == NOT_YET
        assert evidence.task_3b(None, BUILD, _remembered()).state == UNCHECKED

    def test_3b_needs_the_remembered_record_too(self) -> None:
        """The build and the reads are not enough: Theo's taste must reach the managed agent."""
        rows = {"build": self.BUILD_ROW, "tickets": [self.THEO_READ]}
        proved = evidence.task_3b(rows, BUILD, _remembered())
        assert "record mem-theo-1: Prefers hand-thrown ceramics" in proved.evidence
        assert evidence.task_3b(rows, BUILD, _remembered(NOT_YET)).state == NOT_YET
        assert evidence.task_3b(rows, BUILD, _remembered(UNCHECKED)).state == UNCHECKED
        assert evidence.task_3b(rows, BUILD, _remembered(CONTRADICTED)).state == CONTRADICTED

    def test_a_read_for_another_customer_contradicts_3b(self) -> None:
        rows = {"build": self.BUILD_ROW,
                "tickets": [self.THEO_READ, {**self.THEO_READ, "customer_id": "CUST-JESSICA"}]}
        finding = evidence.task_3b(rows, BUILD, _remembered())
        assert finding.state == CONTRADICTED
        assert "1 for anyone else" in finding.observed

    def test_3a_reads_the_source_and_3b_only_the_rows(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """3B's rows prove it or not on their own: a starter in source does not hide them."""
        monkeypatch.setattr(evidence, "source_state", lambda key: check.STARTER)
        assert evidence.task_3a().state == NOT_YET
        assert evidence.task_3b(None, BUILD).state == UNCHECKED
        rows = {"build": self.BUILD_ROW, "tickets": [self.THEO_READ]}
        assert evidence.task_3b(rows, BUILD, _remembered()).state == PROVED

    def test_3a_reads_the_catalogue_once_the_regions_are_edited(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        lab3 = importlib.import_module("lab3_check")
        monkeypatch.setattr(evidence, "source_state", lambda key: check.EDITED)
        monkeypatch.setattr(lab3, "source_catalogue", lambda: (
            frozenset({"get_orders", "get_tickets"}), ("get_orders", "get_tickets"),
            frozenset({"get_tickets"})))
        assert evidence.task_3a().state == PROVED
        monkeypatch.setattr(lab3, "source_catalogue", lambda: (
            frozenset({"get_orders", "get_tickets"}), ("get_orders", "get_tickets"), frozenset()))
        assert evidence.task_3a().state == NOT_YET

    @pytest.mark.parametrize("change", [{"credit_rows": 2}, {"audit_rows": 0}, {"audit_rows": 2}])
    def test_anything_but_one_of_each_contradicts(self, change: dict) -> None:
        assert evidence.credit_findings({**CREDIT, **change})["once"] == CONTRADICTED

    def test_a_credit_for_another_amount_contradicts(self) -> None:
        assert evidence.credit_findings({**CREDIT, "amount_cents": 10001})["amount"] == CONTRADICTED

    def test_one_credit_for_the_approved_amount_is_proved(self) -> None:
        assert evidence.credit_findings(dict(CREDIT)) == {"once": PROVED, "amount": PROVED}


# ---------------------------------------------------------------------------
# Labs 1 and 2 on the real schema, solutions in place
# ---------------------------------------------------------------------------


@pytest.fixture()
def solved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of the Lab 1A worksheet with the solution's region, run by the export."""
    copies = {"1A": lab_variants.LAB1_RRF["solution"]}
    regions = dict(evidence.REGIONS)
    for task, source in copies.items():
        target = tmp_path / f"{task}{source.suffix}"
        shutil.copyfile(source, target)
        _path, label, starter = regions[task]
        regions[task] = (target, label, starter)
    monkeypatch.setattr(evidence, "REGIONS", regions)
    return tmp_path


def _cfg(cluster: Any) -> Dict[str, str]:
    return {"DB_HOST": str(cluster.socket), "DB_PORT": "5432", "DB_NAME": "postgres",
            "DB_USER": "postgres", "DB_PASSWORD": ""}


def test_lab_one_and_two_lines_read_the_real_schema(
    fresh_db: Any, solved: Path, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
) -> None:
    """Labs 1 and 2 from the rows a solved run leaves; only 1A runs what you wrote."""
    monkeypatch.setenv("PATH", f"{fresh_db.bin}:{os.environ['PATH']}")
    cfg = _cfg(fresh_db)
    for key, value in cfg.items():  # the check sets missing DB_* defaults; undo them after
        monkeypatch.setenv(key, value)
    with psycopg.connect(host=str(fresh_db.socket), port=5432, user="postgres",
                         dbname="postgres", autocommit=True, row_factory=dict_row) as conn:
        conn.execute("""
            INSERT INTO pellier.retrieval_receipts
                   (session_id, query_hash, query_preview, search_plan, hard_constraints,
                    exclusions, relaxations, vector_ranks, lexical_ranks, rrf_scores,
                    citation_ids, retrieval_config)
            VALUES ('persona-anna-export', 'h', 'gift', '{}',
                    '{"price_max_usd": 100, "in_stock_only": true, "categories": []}',
                    '["candle"]', '[{"step": "drop_tags", "dropped": ["gift"]}]',
                    '{"22": 1, "28": 2}', '{"28": 1}',
                    jsonb_build_object('22', 1.0/61, '28', 1.0/62 + 1.0/61), '["22", "28"]',
                    '{"requested": {"hard_constraints": {"price_max_usd": 100,
                      "in_stock_only": true, "categories": []}, "exclusions": ["candle"]}}')""")
        conn.execute("""
            INSERT INTO pellier.tool_audit (session_id, tool, caller, args, result, latency_ms)
            VALUES ('persona-marco-export', 'check_stock', 'agent',
                    '{"product_query": "Velvet Opera Cape", "turn_id": "turn-export",
                      "agent": "stock", "grant": ["check_stock"]}',
                    '{"status": "not_found"}', 9)""")

    findings = {
        "1A": evidence.task_1a(cfg),
        "1B": evidence.task_1b(cfg, check.connect),
        "2A": evidence.task_2a(cfg, check.connect),
        "2B": evidence.task_2b(cfg, check.connect),
    }
    for task, finding in findings.items():
        assert finding.state == PROVED, (task, finding)
    assert "2 of 2 scores match" in findings["1A"].observed


# ---------------------------------------------------------------------------
# Lab 4 on the real schema: the rule, the stored denial, the credit, RLS, absence
# ---------------------------------------------------------------------------

SOLVED_RULE = REPO / "solutions" / "the-concierge" / "policies" / "workshop_credit_limit.cedar"
SOLVED_RLS = REPO / "solutions" / "the-concierge" / "sql" / "lab-4-rls-solution.sql"


def test_lab_4a_needs_the_rule_the_stored_denial_and_one_credit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json as _json

    monkeypatch.setattr(evidence, "CEDAR_POLICY", SOLVED_RULE)
    probe = {"id": 9, "idempotency_key": "operator-review:9:" + "b" * 32, "audit_rows": 0,
             "credit_rows": 0, "last_attempt": _json.dumps({"outcome": "denied", "policy": "DENY"})}
    assert evidence.task_4a({"probe": probe, "credit": dict(CREDIT)}).state == PROVED
    assert evidence.task_4a({"probe": None, "credit": dict(CREDIT)}).state == NOT_YET
    assert evidence.task_4a({"probe": probe, "credit": {**CREDIT, "credit_rows": 2}}).state == (
        CONTRADICTED)
    assert evidence.task_4a(None).state == UNCHECKED


def test_lab_4b_runs_the_rls_worksheet_and_the_absence_check(
    fresh_db: Any, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
) -> None:
    from tests.test_lab4_starter_failure import _jessicas_credit

    lab4 = importlib.import_module("lab4_policy_check")
    regions = dict(evidence.REGIONS)
    regions["4B"] = (SOLVED_RLS, regions["4B"][1], regions["4B"][2])
    monkeypatch.setattr(evidence, "REGIONS", regions)
    monkeypatch.setenv("PATH", f"{fresh_db.bin}:{os.environ['PATH']}")
    cfg = _cfg(fresh_db)

    waiting = evidence.task_4b(cfg)
    assert waiting.state == NOT_YET, waiting
    with psycopg.connect(host=str(fresh_db.socket), port=5432, user="postgres",
                         dbname="postgres", autocommit=True, row_factory=dict_row) as conn:
        review = lab4.ensure_probe_review(conn, staff_sub="sub-nadia")
        lab4.record_probe_attempt(conn, review["id"], lab4.attempt_for(
            {"outcome": "deny", "cedar_denial": True, "error": "not allowed due to policy"},
            review["idempotency_key"], {}))
        _jessicas_credit(conn)
    done = evidence.task_4b(cfg)
    assert done.state == PROVED, done
    assert "9 of 9 probes match" in done.observed and "0, 0 and 1" in done.observed

    monkeypatch.setattr(evidence, "CEDAR_POLICY", SOLVED_RULE)
    rows = evidence._rows(cfg, check.connect)
    assert evidence.task_4a(rows["lab4"]).state == PROVED
