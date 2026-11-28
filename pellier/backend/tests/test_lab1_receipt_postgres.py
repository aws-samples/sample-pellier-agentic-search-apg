"""Task 1B's receipt, ``psql -f workshop/lab-1-receipt.sql``, on a fresh workshop database.

The receipt is how a participant sees the bug: Anna asked for her budget, stock rule and
exclusion, and the retry kept nothing. It reads her newest search. Before any search it says
so; when her newest search recorded no retry it says so and names the
send; after a retry it prints one row per requirement, asked beside kept.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.fresh_cluster import fresh_db  # noqa: F401  (fixture import)

REPO = Path(__file__).resolve().parents[3]
RECEIPT = REPO / "workshop" / "lab-1-receipt.sql"
SEND = "uv run scripts/lab_run.py send --lab 1 --task 1B"
ASKED = '{"price_max_usd": 100, "in_stock_only": true}'
RETRY = '[{"step": "drop_soft_tags", "reason": "too few", "dropped": ["gift", "slow", "home"]}]'


def _receipt(cluster) -> str:
    done = subprocess.run(
        [str(cluster.bin / "psql"), "-X", "-h", str(cluster.socket), "-U", cluster.user,
         "-d", cluster.database, "-f", str(RECEIPT)],
        capture_output=True, text=True, timeout=60, cwd=REPO)
    assert done.returncode == 0, done.stderr
    assert done.stderr == ""
    return done.stdout


def _search(cluster, name: str, kept: str, exclusions: str, relaxations: str,
            requested: str | None = ASKED) -> None:
    config = ({"requested": {"hard_constraints": json.loads(requested), "exclusions": ["candle"]}}
              if requested is not None else {})
    cluster.psql(f"""
        INSERT INTO pellier.retrieval_receipts
          (turn_id, session_id, query_hash, search_plan, hard_constraints, exclusions,
           relaxations, retrieval_config, citation_ids)
        VALUES ('turn-{name}', 'persona-anna-{name}', '{name}', '{{}}', '{kept}', '{exclusions}',
                '{relaxations}', '{json.dumps(config)}', '["65", "36"]')""")


def _rows(text: str) -> list:
    return [[cell.strip() for cell in line.strip("│").split("│")]
            for line in text.splitlines() if line.startswith("│")]


def test_the_receipt_reads_each_of_annas_searches_as_it_stands(fresh_db) -> None:  # noqa: F811
    assert _receipt(fresh_db).splitlines() == [
        "No receipt for Anna yet.",
        "Next: send her full request, then read this receipt.", f"      {SEND}"]

    _search(fresh_db, "dropped", "{}", "[]", RETRY)
    text = _receipt(fresh_db)
    assert _rows(text) == [["Requirement", "Anna asked for", "The retry kept"],
                           ["In stock only", "yes", "no"], ["Price limit", "$100", "none"],
                           ["Excluded", "candle", "nothing"]]
    assert "The retry dropped the words: gift, slow, home" in text

    _search(fresh_db, "first-try", ASKED, '["candle"]', "[]")
    text = _receipt(fresh_db)
    assert text.splitlines() == [
        "No retry ran for this request.",
        "Next: send her full request again, then read this receipt.", f"      {SEND}"]

    _search(fresh_db, "kept", ASKED, '["candle"]', RETRY)
    assert _rows(_receipt(fresh_db))[1:] == [["In stock only", "yes", "yes"],
                                            ["Price limit", "$100", "$100"],
                                            ["Excluded", "candle", "candle"]]


def test_the_receipt_reads_only_the_turn_the_last_1b_send_recorded(
        fresh_db, tmp_path) -> None:  # noqa: F811
    """Codex's review: a later request that ran no search must not show an older retry."""
    _search(fresh_db, "earlier-retry", ASKED, '["candle"]', RETRY)
    record = tmp_path / "lab-1b-turn.json"
    record.write_text(json.dumps({"session": "persona-anna-later", "turn": "turn-later"}))
    assert _receipt(fresh_db).splitlines() == [
        "There is no search receipt for Anna's latest request.",
        "Next: send her full request again, then read this receipt.", f"      {SEND}"]
    record.write_text("")
    assert _receipt(fresh_db).splitlines()[0] == (
        "There is no completed turn recorded for Anna's latest send.")
    record.write_text(json.dumps({"session": "persona-anna-earlier-retry",
                                  "turn": "turn-earlier-retry"}))
    assert _rows(_receipt(fresh_db))[1:] == [["In stock only", "yes", "yes"],
                                                      ["Price limit", "$100", "$100"],
                                                      ["Excluded", "candle", "candle"]]


def test_the_1b_check_withholds_the_pass_when_the_recorded_turn_ran_no_search(
        fresh_db, tmp_path, monkeypatch) -> None:  # noqa: F811
    import importlib
    import sys

    import psycopg
    from psycopg.rows import dict_row

    sys.path.insert(0, str(REPO / "scripts"))
    lab1_retry = importlib.import_module("lab1_retry")
    _search(fresh_db, "passing-retry", ASKED, '["candle"]', RETRY)
    record = lab1_retry.check.lab1_retry_turn_path()
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"session": "persona-anna-next", "turn": "turn-next"}))
    with psycopg.connect(host=str(fresh_db.socket), user="postgres", dbname="postgres",
                         row_factory=dict_row) as conn:
        finding, _rows_found = lab1_retry.evaluate(conn)
    assert finding.state == "NOT YET PASSED"
    assert finding.observed == lab1_retry.NO_RECEIPT


def test_receipt_respects_the_lab_1_reset_point(fresh_db, tmp_path) -> None:  # noqa: F811
    _search(fresh_db, "pre-reset", ASKED, '["candle"]', RETRY)
    (tmp_path / "lab-reset-points.json").write_text(
        json.dumps({"1": datetime.now(timezone.utc).isoformat()}))
    marker = tmp_path / "lab-1b-turn.json"
    marker.write_text(json.dumps({"turn": "turn-pre-reset"}))
    assert _receipt(fresh_db).startswith("There is no search receipt")
    marker.unlink()
    assert _receipt(fresh_db).startswith("No receipt for Anna yet.")
    _search(fresh_db, "post-reset", ASKED, '["candle"]', RETRY)
    assert _rows(_receipt(fresh_db))[2] == ["Price limit", "$100", "$100"]


@pytest.mark.parametrize("payload", [b'{"turn":', b"absent", b"\xff", None])
def test_unreadable_or_malformed_marker_never_shows_an_older_retry(
        fresh_db, tmp_path, payload) -> None:  # noqa: F811
    _search(fresh_db, "older-valid", ASKED, '["candle"]', RETRY)
    marker = tmp_path / "lab-1b-turn.json"
    if payload is None:
        marker.mkdir()  # Exists, but cannot be read as a turn record.
    else:
        marker.write_bytes(payload)
    text = _receipt(fresh_db)
    assert not _rows(text)
    assert text.startswith("There is no completed turn recorded for Anna")
    assert text.count("Next:") == 1


def test_receipt_distinguishes_unknown_requirements_and_exact_cents(
        fresh_db) -> None:  # noqa: F811
    _search(fresh_db, "legacy", ASKED, '["candle"]', RETRY, requested=None)
    legacy = _receipt(fresh_db)
    assert "did not record Anna's original requirements" in legacy
    assert not _rows(legacy)

    _search(fresh_db, "cents", '{"price_max_usd": 99.90}', '["candle"]', RETRY,
            requested='{"price_max_usd": 99.99}')
    assert _rows(_receipt(fresh_db))[2] == ["Price limit", "$99.99", "$99.90"]
