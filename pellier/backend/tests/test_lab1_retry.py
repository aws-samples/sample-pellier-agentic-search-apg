"""Lab 1B's verdict judges what the shopper asked for against what the answering search kept.

Pure over a receipt and catalog rows, so every edge runs offline here;
``tests/test_lab1_starter_failure.py`` runs it on the real schema against the
starter and the solution.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
lab1 = importlib.import_module("lab1_retry")

ASKED = {"hard_constraints": {"price_max_usd": 100, "in_stock_only": True, "categories": []},
         "exclusions": ["candle"]}
KEPT = {"price_max_usd": 100, "in_stock_only": True, "categories": []}
FELL_BACK = [{"step": "drop_tags", "dropped": ["slow"]}]


def _receipt(*, requested: Optional[Dict[str, Any]] = ASKED, kept: Optional[Dict] = None,
             exclusions: Optional[List[str]] = None,
             relaxations: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    config = {"requested": requested} if requested is not None else {}
    return {"receipt_id": 7, "session_id": "persona-anna-x", "created_at": "now",
            "query_preview": "gift", "retrieval_config": json.dumps(config),
            "hard_constraints": kept if kept is not None else KEPT,
            "exclusions": ["candle"] if exclusions is None else exclusions,
            "relaxations": FELL_BACK if relaxations is None else relaxations}


def _judge(receipt: Dict[str, Any], broken: Optional[List[str]] = None):
    return lab1._judge(receipt, lab1.requested_limits(receipt), ["22", "28"], broken or [])


def test_kept_limits_after_the_fallback_prove_it() -> None:
    finding = _judge(_receipt())
    assert finding.state == "PROVED"
    assert finding.observed == "all 2 keep under $100, in stock, no candles after the fallback"
    assert "the shopper asked: under $100, in stock, no candles" in finding.evidence


def test_a_dropped_limit_is_named_and_blames_the_fallback() -> None:
    lost = {"price_max_usd": None, "in_stock_only": False, "categories": []}
    finding = _judge(_receipt(kept=lost, exclusions=[]))
    assert finding.state == "CONTRADICTED"
    assert finding.observed.endswith("dropped under $100, in stock, no candles")
    assert "_next_attempt" in finding.next_step


@pytest.mark.parametrize("requested, observed", [
    ({"hard_constraints": {"price_max_usd": None, "in_stock_only": False, "categories": []},
      "exclusions": []}, "the request stated no limit, so there was nothing to keep"),
    (None, "the receipt does not record what the shopper asked"),
])
def test_a_request_with_nothing_to_keep_asks_for_the_guides_request(requested, observed) -> None:
    """Anna's chip used to state no limit; a fix must not read CONTRADICTED for it."""
    finding = _judge(_receipt(requested=requested, kept={}, exclusions=[]))
    assert finding.state == "NOT YET"
    assert finding.observed == observed
    assert "python3 scripts/lab_run.py send --lab 1" in finding.next_step


def test_a_first_pass_answer_is_not_yet_and_does_not_blame_the_fallback() -> None:
    finding = _judge(_receipt(relaxations=[]), ["80 Sunday Morning Candle is excluded candle"])
    assert finding.state == "NOT YET"
    assert finding.observed.startswith("the first search answered, so the fallback never ran")
    assert "_next_attempt" not in finding.next_step


def test_only_the_limits_asked_for_are_judged() -> None:
    """A request with only an exclusion is not failed for a budget nobody stated."""
    wool = {"hard_constraints": {"price_max_usd": None, "in_stock_only": False,
                                 "categories": []}, "exclusions": ["wool"]}
    limits = lab1.requested_limits(_receipt(requested=wool))
    pricey = {"price": 240, "quantity": 0, "category": "Home", "tags": ["warm"],
              "materials": ["wool"]}
    assert lab1.product_breaks(pricey, limits) == ["excluded wool"]
    finding = _judge(_receipt(requested=wool, kept={}, exclusions=["wool"]))
    assert finding.state == "PROVED", finding


def test_a_department_the_answer_widened_is_dropped() -> None:
    home = {"hard_constraints": {"price_max_usd": None, "in_stock_only": False,
                                 "categories": ["Home"]}, "exclusions": []}
    requested = lab1.requested_limits(_receipt(requested=home))
    assert lab1.dropped(requested, lab1.limits_of({"categories": []}, [])) == ["home only"]
    assert lab1.dropped(requested, lab1.limits_of({"categories": ["Home"]}, [])) == []
    away = {"price": 10, "quantity": 1, "category": "Bath and body", "tags": [], "materials": []}
    assert lab1.product_breaks(away, requested) == ["in Bath and body"]


def test_the_guides_request_is_annas_first_suggestion() -> None:
    prompts = json.loads((REPO / "data" / "scenarios.json").read_text(encoding="utf-8"))
    anna = sorted((p for p in prompts if p["persona"] == "anna"), key=lambda p: p["ordinal"])
    assert anna[0]["prompt"] == lab1.ANNA_REQUEST
    assert anna[0]["journey_role"] == "required"


# --- A search older than the edit or the restart is never judged ---------------------------

from datetime import datetime, timezone  # noqa: E402

RAN = datetime(2026, 10, 14, 14, 45, 43, tzinfo=timezone.utc)
EDITED = datetime(2026, 10, 14, 14, 46, 10, tzinfo=timezone.utc)
RESTARTED = datetime(2026, 10, 14, 14, 46, 19, tzinfo=timezone.utc)
CANDLE = {"product_id": "80", "name": "Sunday Morning Candle", "price": 28, "quantity": 24,
          "category": "Home", "tags": ["candle"], "materials": []}


class _Conn:
    """The two queries evaluate() runs: Anna's newest receipt, then its products."""

    def __init__(self, receipt: Dict[str, Any], catalog: List[Dict[str, Any]]) -> None:
        self.receipt, self.catalog, self.queries = receipt, catalog, 0

    def cursor(self) -> "_Conn":
        return self

    def __enter__(self) -> "_Conn":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self.queries += 1

    def fetchone(self) -> Dict[str, Any]:
        return self.receipt

    def fetchall(self) -> List[Dict[str, Any]]:
        return self.catalog


def _dropped_at(created: datetime) -> Dict[str, Any]:
    """The receipt the code as shipped writes: every limit dropped, a candle returned."""
    receipt = _receipt(kept={"price_max_usd": None, "in_stock_only": False, "categories": []},
                       exclusions=[])
    receipt.update(created_at=created, citation_ids=["80"])
    return receipt


def test_a_search_older_than_the_edit_is_not_judged() -> None:
    """The tester's sequence: the solution installed and restarted, Anna not sent again."""
    conn = _Conn(_dropped_at(RAN), [CANDLE])
    finding, rows = lab1.evaluate(conn, lab1.Timeline(EDITED, RESTARTED))
    assert finding.state == "NOT YET"
    assert finding.observed == ("Anna's newest search ran at 14:45:43 UTC, before your last "
                                "change to search_plan.py at 14:46:10 UTC, so the code before "
                                "your edit made it")
    assert finding.next_step == ("send Anna's request again (python3 scripts/lab_run.py send "
                                 "--lab 1), then rerun this check.")
    assert "pellier last started: 14:46:19 UTC" in finding.evidence
    assert rows == [] and conn.queries == 1, "the stale search's products are not judged"


def test_a_backend_started_before_the_edit_asks_for_a_restart() -> None:
    finding, rows = lab1.evaluate(_Conn(_dropped_at(RAN), [CANDLE]),
                                  lab1.Timeline(RESTARTED, EDITED))
    assert finding.state == "NOT YET"
    assert finding.observed.startswith("pellier last started at 14:46:10 UTC, before your last "
                                       "change to search_plan.py at 14:46:19 UTC")
    assert finding.next_step.startswith("restart the backend (sudo systemctl restart pellier)")
    assert rows == []


def test_a_later_restart_for_another_lab_does_not_date_the_search() -> None:
    """Lab 2 restarts pellier; Anna's passing search from after her edit still proves 1B."""
    sent = datetime(2026, 10, 14, 14, 47, 6, tzinfo=timezone.utc)
    lab2 = datetime(2026, 10, 14, 14, 48, 30, tzinfo=timezone.utc)
    receipt = _receipt()
    receipt.update(created_at=sent, citation_ids=["65"])
    mugs = {"product_id": "65", "name": "Stoneware Mugs, Set of 2", "price": 38, "quantity": 24,
            "category": "Kitchen", "tags": ["stoneware"], "materials": []}
    finding, _rows = lab1.evaluate(_Conn(receipt, [mugs]), lab1.Timeline(EDITED, lab2))
    assert finding.state == "PROVED"


def test_without_systemd_the_edit_alone_dates_the_search() -> None:
    finding, _rows = lab1.evaluate(_Conn(_dropped_at(RAN), [CANDLE]), lab1.Timeline(EDITED, None))
    assert finding.state == "NOT YET"
    assert "before your last change to search_plan.py at 14:46:10 UTC" in finding.observed


def test_a_search_after_the_restart_is_judged_as_before() -> None:
    """A wrong edit still reads CONTRADICTED once Anna has been sent again."""
    later = datetime(2026, 10, 14, 14, 47, 6, tzinfo=timezone.utc)
    finding, rows = lab1.evaluate(_Conn(_dropped_at(later), [CANDLE]),
                                  lab1.Timeline(EDITED, RESTARTED))
    assert finding.state == "CONTRADICTED"
    assert rows and rows[0][-1] == "breaks: excluded candle"


def test_no_timeline_keeps_the_rows_only_reading() -> None:
    """The Wrap-up summary has no timeline; it judges the newest search as it is."""
    finding, _rows = lab1.evaluate(_Conn(_dropped_at(RAN), [CANDLE]))
    assert finding.state == "CONTRADICTED"


@pytest.mark.parametrize("value, expected", [
    ("Wed 2026-10-14 14:46:19 UTC", RESTARTED),
    ("", None),
    ("n/a", None),
    ("Wed 2026-10-14 16:46:19 CEST", None),
])
def test_systemds_start_time_is_read_only_in_utc(value: str, expected: Optional[datetime]) -> None:
    assert lab1.service_started(value) == expected


def test_the_timeline_reads_the_file_and_systemd(monkeypatch: pytest.MonkeyPatch,
                                                 tmp_path: Path) -> None:
    plan = tmp_path / "search_plan.py"
    plan.write_text("# edited\n")
    monkeypatch.setattr(lab1, "SEARCH_PLAN", plan)

    class _Shown:
        stdout = "Wed 2026-10-14 14:46:19 UTC\n"

    monkeypatch.setattr(lab1.subprocess, "run", lambda *args, **kwargs: _Shown())
    when = lab1.timeline()
    assert when.started_at == RESTARTED
    assert when.edited_at == datetime.fromtimestamp(plan.stat().st_mtime, tz=timezone.utc)


def test_no_systemctl_leaves_the_start_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def _missing(*args: Any, **kwargs: Any) -> None:
        raise FileNotFoundError("systemctl")

    monkeypatch.setattr(lab1.subprocess, "run", _missing)
    assert lab1.timeline().started_at is None
