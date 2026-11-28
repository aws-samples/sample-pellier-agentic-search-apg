"""Lab 1B's verdict judges what the shopper asked for against what the answering search kept.

Pure over a receipt and catalog rows, so every edge runs offline here;
``tests/test_lab1_starter_failure.py`` runs it on the real schema against the
starter and the solution.
"""
from __future__ import annotations

import importlib
import json
import os
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
    assert finding.state == "PASSED"
    assert finding.observed == "all 2 keep $100 or less, in stock, no candles after the retry"
    assert "the shopper asked: $100 or less, in stock, no candles" in finding.evidence


@pytest.mark.parametrize("price", [100, 100.0, 99.99, 99.5, 49.99, 250, 1, 0.99])
def test_a_price_ceiling_is_worded_as_ask_pellier_words_it(price: float) -> None:
    """The check and the app say which prices a ceiling admits in the same words.

    Check scripts read rows without importing the backend, so the rule is written twice.
    """
    from services.turn_steps import budget_phrase

    assert lab1.budget_words(price) == budget_phrase(price)


def test_a_ceiling_of_whole_dollars_admits_that_price() -> None:
    limits = lab1.limits_of({"price_max_usd": 100, "in_stock_only": False, "categories": []}, [])
    assert lab1.phrases(limits) == ["$100 or less"]
    limits = lab1.limits_of({"price_max_usd": 99.99, "in_stock_only": False, "categories": []}, [])
    assert lab1.phrases(limits) == ["under $100"]


def test_a_dropped_limit_is_named_and_blames_the_fallback() -> None:
    lost = {"price_max_usd": None, "in_stock_only": False, "categories": []}
    finding = _judge(_receipt(kept=lost, exclusions=[]))
    assert finding.state == "FAILED"
    assert finding.observed.endswith("dropped $100 or less, in stock, no candles")
    assert "_next_attempt" in finding.next_step


@pytest.mark.parametrize("requested, observed", [
    ({"hard_constraints": {"price_max_usd": None, "in_stock_only": False, "categories": []},
      "exclusions": []}, "the request stated no requirement, so there was nothing to keep"),
    (None, "the receipt does not record what the shopper asked"),
])
def test_a_request_with_nothing_to_keep_asks_for_the_guides_request(requested, observed) -> None:
    """Anna's chip used to state no limit; a fix must not read FAILED for it."""
    finding = _judge(_receipt(requested=requested, kept={}, exclusions=[]))
    assert finding.state == "NOT YET PASSED"
    assert finding.observed == observed
    assert "uv run scripts/lab_run.py send --lab 1" in finding.next_step


@pytest.mark.parametrize("ids, observed", [
    (["22"], "No retry ran for this request."),
    ([], "Anna's latest search returned no products"),
])
def test_a_search_without_a_retry_reports_what_the_receipt_shows(ids, observed) -> None:
    receipt = _receipt(relaxations=[])
    finding = lab1._judge(receipt, lab1.requested_limits(receipt), ids, [])
    assert finding.state == "NOT YET PASSED"
    assert finding.observed == observed
    assert lab1.SEND in finding.next_step
    assert "_next_attempt" not in finding.next_step


def test_a_different_request_cannot_prove_annas_required_scenario() -> None:
    """A request with only an exclusion is not failed for a budget nobody stated."""
    wool = {"hard_constraints": {"price_max_usd": None, "in_stock_only": False,
                                 "categories": []}, "exclusions": ["wool"]}
    limits = lab1.requested_limits(_receipt(requested=wool))
    pricey = {"price": 240, "quantity": 0, "category": "Home", "tags": ["warm"],
              "materials": ["wool"]}
    assert lab1.product_breaks(pricey, limits) == ["excluded wool"]
    finding = _judge(_receipt(requested=wool, kept={}, exclusions=["wool"]))
    assert finding.state != "PASSED", finding


@pytest.mark.parametrize("omitted", ["price_max_usd", "in_stock_only", "exclusions"])
def test_matching_initial_and_final_plans_cannot_hide_an_omitted_requirement(omitted):
    import copy
    requested = copy.deepcopy(ASKED)
    if omitted == "exclusions":
        requested[omitted] = []
    else:
        requested["hard_constraints"][omitted] = None
    finding = _judge(_receipt(requested=requested, kept=requested["hard_constraints"],
                               exclusions=requested["exclusions"]))
    assert finding.state != "PASSED"


def test_a_department_the_answer_widened_is_dropped() -> None:
    home = {"hard_constraints": {"price_max_usd": None, "in_stock_only": False,
                                 "categories": ["Home"]}, "exclusions": []}
    requested = lab1.requested_limits(_receipt(requested=home))
    assert lab1.dropped(requested, lab1.limits_of({"categories": []}, [])) == ["home only"]
    assert lab1.dropped(requested, lab1.limits_of({"categories": ["Home"]}, [])) == []
    away = {"price": 10, "quantity": 1, "category": "Bath and body", "tags": [], "materials": []}
    assert lab1.product_breaks(away, requested) == ["in Bath and body"]


def test_the_guides_1b_request_is_annas_first_sentence_with_her_limits() -> None:
    prompts = json.loads((REPO / "data" / "scenarios.json").read_text(encoding="utf-8"))
    anna = sorted((p for p in prompts if p["persona"] == "anna"), key=lambda p: p["ordinal"])
    assert anna[1]["prompt"] == lab1.ANNA_REQUEST
    assert lab1.ANNA_REQUEST.startswith(anna[0]["prompt"])
    assert [p["journey_role"] for p in anna[:2]] == ["required", "required"]


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
    assert finding.state == "NOT YET PASSED"
    assert finding.observed == ("Anna's newest search ran at 14:45:43 UTC, before your last "
                                "change to search_plan.py at 14:46:10 UTC, so the code before "
                                "your edit made it")
    assert finding.next_step == ("send Anna's request again (uv run scripts/lab_run.py send "
                                 "--lab 1 --task 1B), then rerun this check.")
    assert "pellier last started: 14:46:19 UTC" in finding.evidence
    assert rows == [] and conn.queries == 1, "the stale search's products are not judged"


def test_a_backend_started_before_the_edit_asks_for_a_restart() -> None:
    finding, rows = lab1.evaluate(_Conn(_dropped_at(RAN), [CANDLE]),
                                  lab1.Timeline(RESTARTED, EDITED))
    assert finding.state == "NOT YET PASSED"
    assert finding.observed.startswith("pellier last started at 14:46:10 UTC, before your last "
                                       "change to search_plan.py at 14:46:19 UTC")
    assert finding.next_step.startswith("send Anna's request again")
    assert "restart" not in finding.next_step.split(";")[0], "the send restarts Pellier itself"
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
    assert finding.state == "PASSED"


def test_without_systemd_the_edit_alone_dates_the_search() -> None:
    finding, _rows = lab1.evaluate(_Conn(_dropped_at(RAN), [CANDLE]), lab1.Timeline(EDITED, None))
    assert finding.state == "NOT YET PASSED"
    assert "before your last change to search_plan.py at 14:46:10 UTC" in finding.observed


def test_a_search_after_the_restart_is_judged_as_before() -> None:
    """A wrong edit still reads FAILED once Anna has been sent again."""
    later = datetime(2026, 10, 14, 14, 47, 6, tzinfo=timezone.utc)
    finding, rows = lab1.evaluate(_Conn(_dropped_at(later), [CANDLE]),
                                  lab1.Timeline(EDITED, RESTARTED))
    assert finding.state == "FAILED"
    assert rows and rows[0][-1] == "breaks: excluded candle"


def test_no_timeline_keeps_the_rows_only_reading() -> None:
    """The Wrap-up summary has no timeline; it judges the newest search as it is."""
    finding, _rows = lab1.evaluate(_Conn(_dropped_at(RAN), [CANDLE]))
    assert finding.state == "FAILED"


@pytest.mark.parametrize("value, expected", [
    ("Wed 2026-10-14 14:46:19 UTC", RESTARTED),
    ("Wed 2026-10-14 14:46:19.479163 UTC", RESTARTED.replace(microsecond=479163)),
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

    monkeypatch.setattr(lab1.check.subprocess, "run", lambda *args, **kwargs: _Shown())
    when = lab1.timeline()
    assert when.started_at == RESTARTED
    assert when.edited_at == datetime.fromtimestamp(plan.stat().st_mtime, tz=timezone.utc)


def systemd_252(args: List[str], **kwargs: Any) -> Any:
    """systemctl show as Amazon Linux 2023 answers it: whole seconds unless asked for more."""

    class _Shown:
        stdout = ("Sun 2026-10-25 15:42:17.479163 UTC\n" if "--timestamp=us+utc" in args
                  else "Sun 2026-10-25 15:42:17 UTC\n")

    return _Shown()


def test_a_restart_in_the_same_second_as_the_edit_serves_it(monkeypatch: pytest.MonkeyPatch,
                                                            tmp_path: Path) -> None:
    """The solution command writes the file and restarts within one second, as on the 2026-10-25
    event: written at 17.116, started at 17.479. Whole seconds read that start as 17.000."""
    plan = tmp_path / "search_plan.py"
    plan.write_text("# solution\n")
    written = datetime(2026, 10, 25, 15, 42, 17, 116017, tzinfo=timezone.utc).timestamp()
    os.utime(plan, (written, written))
    monkeypatch.setattr(lab1, "SEARCH_PLAN", plan)
    monkeypatch.setattr(lab1.check.subprocess, "run", systemd_252)
    sent = datetime(2026, 10, 25, 15, 42, 25, tzinfo=timezone.utc)
    assert lab1.stale(_dropped_at(sent), lab1.timeline()) is None


def test_no_systemctl_leaves_the_start_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def _missing(*args: Any, **kwargs: Any) -> None:
        raise FileNotFoundError("systemctl")

    monkeypatch.setattr(lab1.check.subprocess, "run", _missing)
    assert lab1.timeline().started_at is None


# ---------------------------------------------------------------------------
# What the participant reads: the pass, the failure, and Lab 1's ending
# ---------------------------------------------------------------------------
REQUESTED = lab1.limits_of({"price_max_usd": 100, "in_stock_only": True}, ["candle"])


def test_a_pass_says_what_the_retry_kept_and_how_many_gifts_met_it() -> None:
    finding = _judge(_receipt())
    text = lab1.check.compact(finding)
    assert text.splitlines() == ["The retry kept   In stock, $100 or less, no candles",
                                 "All 2 gifts met those requirements."]


def test_a_retry_that_lost_every_requirement_is_one_cross_with_one_next() -> None:
    lost = {"price_max_usd": None, "in_stock_only": False, "categories": []}
    text = lab1.check.compact(_judge(_receipt(kept=lost, exclusions=[])))
    assert text.count("\u2717") == 1 and text.count("Next") == 1
    assert "in stock, $100 or less, no candles" in text and "dropped all three" in text
    assert "1B-search-plan.py" in text and lab1.SEND in text


def test_a_retry_that_kept_some_names_what_it_kept_and_what_it_dropped() -> None:
    some = {"price_max_usd": None, "in_stock_only": True, "categories": []}
    text = " ".join(lab1.check.compact(_judge(_receipt(kept=some))).split())
    assert "kept in stock, no candles; dropped $100 or less" in text


def test_after_the_pass_comes_pellier_then_the_lab_1_row_only_when_1a_passes_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(lab1.check.NO_NEXT_ENV, raising=False)
    monkeypatch.setattr(lab1.check, "terminal_width", lambda: 120)
    complete = lab1.after_pass(REQUESTED, True)
    assert complete[:4] == list(lab1.SEE_IT_IN_PELLIER)
    assert complete[5] == "What you’ve proved · 1 of 4 labs"
    assert " ".join(complete[6].split()) == "Lab What you added What you proved"
    assert " ".join(complete[7].split()) == (
        "1 · Retrieve Search by meaning and a retry that keeps Anna’s rules "
        "Anna’s retry kept all three rules.")
    assert len(complete) == 8
    assert lab1.after_pass(REQUESTED, False) == list(lab1.SEE_IT_IN_PELLIER)
    monkeypatch.setenv(lab1.check.NO_NEXT_ENV, "1")
    assert lab1.after_pass(REQUESTED, True)[0].startswith("What you\u2019ve proved")


@pytest.mark.parametrize("width", [60, 80, 100])
def test_the_lab_1_row_keeps_both_columns_readable(width: int) -> None:
    lines = lab1.completion_row(REQUESTED, width=width)
    assert all(len(line) <= width for line in lines)
    added = lines[1].index("What you added")
    proved = lines[1].index("What you proved")
    assert [word for line in lines[2:] for word in line[added:proved].split()] == (
        "Search by meaning and a retry that keeps Anna’s rules".split())
    assert [word for line in lines[2:] for word in line[proved:].split()] == (
        "Anna’s retry kept all three rules.".split())


@pytest.mark.parametrize("state", ["FAILED", "NOT YET PASSED", "COULD NOT CHECK"])
def test_a_check_that_did_not_pass_never_prints_the_lab_1_row(
    state: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    finding = lab1.check.Finding("1B", "t", state, "e", "o", [], "next")
    monkeypatch.setattr(lab1, "run", lambda: (finding, []))
    monkeypatch.setattr(lab1.check, "refuse_missing_lab_file", lambda lab: False)
    monkeypatch.setattr(lab1, "lab_1_complete", lambda: True)
    assert lab1.main([]) == 1
    out = capsys.readouterr().out
    assert "proved" not in out and "See it in Pellier" not in out


def test_the_lab_1_row_heading_is_green_on_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lab1.check, "colour_enabled", lambda stream=None: True)
    assert lab1.completion_row(REQUESTED, width=100)[0].startswith("\033[32mWhat you")


# ---------------------------------------------------------------------------
# The 1B check judges the turn the last 1B send recorded, never an older turn's search
# ---------------------------------------------------------------------------
def _record(turn: Optional[str]) -> None:
    path = lab1.check.lab1_retry_turn_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("" if turn is None else json.dumps({"session": "persona-anna-x",
                                                         "turn": turn}))


def test_a_recorded_request_that_ran_no_search_is_not_a_pass() -> None:
    """Codex's review: the Router answered without a search, and an earlier turn's retry passed."""
    _record("turn-no-search")
    conn = _Conn(None, [])  # nothing in pellier.retrieval_receipts for that turn
    finding, rows = lab1.evaluate(conn)
    assert finding.state == "NOT YET PASSED" and rows == []
    assert finding.observed == "There is no search receipt for Anna's latest request."
    text = lab1.check.compact(finding)
    assert "send --lab 1 --task 1B" in text and "gifts met" not in text


def test_a_send_that_did_not_finish_is_not_judged() -> None:
    _record(None)
    finding, rows = lab1.evaluate(_Conn(_receipt(), [CANDLE]))
    assert finding.state == "NOT YET PASSED" and finding.observed == lab1.UNFINISHED
    assert rows == []


def test_with_no_record_the_check_reads_annas_newest_search_as_before() -> None:
    assert lab1.recorded_turn() == (False, None)
    receipt = _receipt()
    receipt.update(created_at=RAN, citation_ids=["65"])
    mugs = {"product_id": "65", "name": "Stoneware Mugs, Set of 2", "price": 38,
            "quantity": 24, "category": "Kitchen", "tags": [], "materials": []}
    assert lab1.evaluate(_Conn(receipt, [mugs]))[0].state == "PASSED"


def test_a_recorded_turn_with_its_own_retry_is_judged() -> None:
    _record("turn-with-retry")
    receipt = _receipt()
    receipt.update(created_at=RAN, citation_ids=["65"])
    mugs = {"product_id": "65", "name": "Stoneware Mugs, Set of 2", "price": 38,
            "quantity": 24, "category": "Kitchen", "tags": [], "materials": []}
    assert lab1.recorded_turn() == (True, "turn-with-retry")
    assert lab1.evaluate(_Conn(receipt, [mugs]))[0].state == "PASSED"


def test_invalid_marker_bytes_withhold_a_verdict_and_do_not_fall_back() -> None:
    path = lab1.check.lab1_retry_turn_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff")
    assert lab1.recorded_turn() == (True, None)
