"""The check and trace scripts print lines that fit a laptop's terminal.

Code Editor on a 1440-pixel laptop gives about 100 columns (``terminal_width`` is then 99).
A line outside a box that is longer breaks mid-word and under its label, so each is wrapped at
words with ``workshop_check.wrapped``. These tests render the lines at 100 and 84 columns with
a long model id and a 32-hex key, and check that no line is longer unless it is one
unbreakable word, that the words survive, and that a label's later lines stay under its text.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, List

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
check = importlib.import_module("workshop_check")
trace = importlib.import_module("trace_agentcore_calls")
follow_credit = importlib.import_module("follow_credit")
duckdb_federation = importlib.import_module("duckdb_federation")
lab3_check = importlib.import_module("lab3_check")
where_memory = importlib.import_module("lab3_where_memory_lands")
showcase = importlib.import_module("showcase_agentcore_memory")

TERMINALS = pytest.mark.parametrize("columns", [100, 84])
KEY = "operator-review:2:" + "ab" * 16
TURN = "turn-" + "cd" * 16
MODEL = "global.anthropic.claude-opus-5-5"
MARGIN = 14


def terminal(monkeypatch: pytest.MonkeyPatch, columns: int) -> int:
    """Make the scripts see a terminal ``columns`` wide; return the width they print to."""
    width = columns - 1
    monkeypatch.setattr(check, "terminal_width", lambda: width)
    return width


def assert_fits(text: str, width: int) -> None:
    """No line is longer than ``width`` unless one of its words cannot be broken."""
    for line in text.splitlines():
        if len(line) > width:
            assert max(len(word) for word in line.split()) > width - MARGIN, line


def words(text: str) -> List[str]:
    return text.split()


CALL = {
    "request_id": "9f1b7c2e-5a41-4c1e-8f43-0a6e3d2b7c11", "trace_id": "ef" * 16,
    "parent_span_id": "mcp-span", "started_ns": 1_700_000_000 * 10**9,
    "tool": "give_store_credit", "decision": "ALLOW", "policies": ["credit_limit-q6"],
    "reason": None, "subject": "7f1c2e90-jessica", "token_use": "access",
    "authorizer": "CUSTOM_JWT", "identity_checked": True, "gateway_ms": 900, "lambda_ms": 412,
}
RUNTIME = [{"name": "invoke_agent support", "attributes": {
    "gen_ai.agent.name": "support", "gen_ai.request.model": MODEL, "turn.id": TURN}}]
AURORA = {
    "window": "pgAudit: no exported write to pellier.store_credits in this window; absence "
              "does not prove non-execution",
    "lag": "pgAudit: not exported yet; the PostgreSQL log lags about a minute, so run this "
           "again shortly",
    "insert": f"pgAudit: INSERT into pellier.store_credits at 18:16:25, key {KEY} "
              "(time window only; run this again if you expect more)",
}


@TERMINALS
@pytest.mark.parametrize("which", sorted(AURORA))
def test_every_trace_line_fits_and_keeps_its_words(
        monkeypatch: pytest.MonkeyPatch, columns: int, which: str) -> None:
    width = terminal(monkeypatch, columns)
    text = "\n".join(trace.render_call(CALL, {"7f1c2e90-jessica": "jessica"}, RUNTIME,
                                      AURORA[which]))
    assert_fits(text, width)
    assert MODEL in text and TURN in text and KEY in text.replace("\n", " ") or which != "insert"
    for label, sentence in (("Runtime", trace.runtime_summary(CALL, RUNTIME)),
                            ("Aurora", AURORA[which])):
        block = _block(text, label)
        assert words(" ".join(line[12:] for line in block)) == words(sentence)
        assert all(line.startswith(" " * 12) for line in block[1:])


def _block(text: str, label: str) -> List[str]:
    """The labelled line and the lines wrapped under it."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"  {label} "))
    end = start + 1
    while end < len(lines) and lines[end].startswith(" " * 12):
        end += 1
    return lines[start:end]


@TERMINALS
def test_the_trace_and_request_line_keeps_both_ids(
        monkeypatch: pytest.MonkeyPatch, columns: int) -> None:
    width = terminal(monkeypatch, columns)
    text = "\n".join(trace.render_call(CALL, {}, RUNTIME))
    assert_fits(text, width)
    assert CALL["trace_id"] in text and CALL["request_id"] in text


@TERMINALS
def test_the_no_call_message_fits(monkeypatch: pytest.MonkeyPatch, columns: int) -> None:
    width = terminal(monkeypatch, columns)
    text = trace.no_call_message("give_store_credit")
    assert_fits(text, width)
    assert words(text) == words("No give_store_credit call yet. Spans arrive about ten seconds "
                                "after a call; run this again in a moment.")


def _followed() -> Any:
    return follow_credit.Followed(
        state=check.PASSED, observed="", rows=[], next_step="",
        joins=[f"Turn  {TURN} joins the agent's span, the audit row and her request.",
               f"Key   {KEY} joins the audit row, the pgAudit line and the credit.",
               "Paid once: pgAudit logged one INSERT with this key, and Aurora holds one "
               "credit with it."])


@TERMINALS
def test_the_joins_after_the_table_fit(monkeypatch: pytest.MonkeyPatch, columns: int) -> None:
    width = terminal(monkeypatch, columns)
    text = follow_credit.report(_followed())
    assert_fits(text, width)
    for join in _followed().joins:
        assert words(join)[0] in text
    flat = " ".join(text.split())
    assert f"Key {KEY} joins the audit row, the pgAudit line and the credit." in flat
    key_block = _block_at(text, "Key   ")
    assert all(line.startswith(" " * 6) for line in key_block[1:])


def _block_at(text: str, prefix: str) -> List[str]:
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(prefix))
    end = start + 1
    while end < len(lines) and lines[end].startswith(" " * len(prefix)):
        end += 1
    return lines[start:end]


@TERMINALS
def test_a_waiting_report_wraps_its_state_and_next_step(
        monkeypatch: pytest.MonkeyPatch, columns: int) -> None:
    width = terminal(monkeypatch, columns)
    waiting = follow_credit.Followed(
        state=check.NOT_YET, observed="Spans arrive about ten seconds after a call and the "
        "PostgreSQL log lags about a minute, so nothing joins yet.", rows=[],
        next_step="run this again in about a minute, after Jessica's credit has been written "
                  "and exported.")
    assert_fits(follow_credit.report(waiting), width)


@TERMINALS
def test_the_task_3b_heading_fits(monkeypatch: pytest.MonkeyPatch, columns: int,
                                  capsys: pytest.CaptureFixture[str]) -> None:
    width = terminal(monkeypatch, columns)
    monkeypatch.setattr(check, "refuse_missing_lab_file", lambda lab: False)
    monkeypatch.setattr(lab3_check, "collect", lambda: [])
    lab3_check.main(["--task", "3B"])
    out = capsys.readouterr().out
    assert_fits(out, width)
    assert words(out)[:3] == ["Lab", "3B:", "Theo's"]
    assert "the row policies" in " ".join(out.split())


@TERMINALS
def test_duckdb_pass_line_stands_alone_and_the_explanation_wraps(
        monkeypatch: pytest.MonkeyPatch, columns: int,
        capsys: pytest.CaptureFixture[str]) -> None:
    width = terminal(monkeypatch, columns)
    monkeypatch.setattr(duckdb_federation, "check_reader", lambda _local: None)
    monkeypatch.setattr(sys, "argv", ["duckdb_federation.py", "check"])
    assert duckdb_federation.main() == 0
    out = check.plain(capsys.readouterr().out)
    assert_fits(out, width)
    assert out.splitlines()[0] == "DuckDB check passed"
    assert "Live stock matches; missing forecast stays NULL; customer reads and writes are " \
        "denied." in " ".join(out.split())


def test_duckdb_pass_line_is_green_only_at_a_terminal(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(duckdb_federation, "check_reader", lambda _local: None)
    monkeypatch.setattr(sys, "argv", ["duckdb_federation.py", "check"])
    duckdb_federation.main()
    assert "\033[" not in capsys.readouterr().out


@TERMINALS
def test_where_memory_lands_lines_fit(monkeypatch: pytest.MonkeyPatch, columns: int,
                                      capsys: pytest.CaptureFixture[str]) -> None:
    width = terminal(monkeypatch, columns)
    monkeypatch.setattr(where_memory, "_connect", lambda: (object(), "mem-1", "sub-1"))
    monkeypatch.setattr(where_memory, "extracting", lambda *_a: [("x", 120.0)])
    monkeypatch.setattr(where_memory, "wait_for_extraction", lambda *_a: False)
    monkeypatch.setattr(where_memory, "report", lambda *_a: ["CUST-THEO"])
    where_memory.main()
    assert_fits(capsys.readouterr().out, width)


@TERMINALS
def test_memory_showcase_record_lines_fit(monkeypatch: pytest.MonkeyPatch, columns: int) -> None:
    width = terminal(monkeypatch, columns)
    record = {"memoryRecordId": "mem-" + "0123456789abcdef" * 3, "content": {"text": "x " * 40}}
    monkeypatch.setattr(showcase, "record_text", lambda _r, _k: "likes quiet colours " * 4)
    strategies = {kind: {"name": kind, "namespace": "/strategies/x/actors/CUST-JESSICA/sessions/p",
                         "records": [record]} for kind, *_ in showcase.STRATEGY_ROWS}
    found = {"actor": "CUST-JESSICA", "session": "prefseed", "events": [],
             "strategies": strategies}
    assert_fits(showcase.render_strategies(found, "memory-id", found), width)


@TERMINALS
def test_marcos_two_lines_fit_and_keep_their_words(
        monkeypatch: pytest.MonkeyPatch, columns: int) -> None:
    """On the box the second line ran 96 columns in an 85-column terminal."""
    lab2_check = importlib.import_module("lab2_check")
    width = terminal(monkeypatch, columns)
    request = lab2_check.marco_cape_request()
    rows = [("not carried", "Velvet Opera Cape", "default",
             "not_found: no product matches Velvet Opera Cape", "not_found", "matches")]
    lines = lab2_check.marco_line(rows, request).splitlines()
    assert all(len(line) <= width for line in lines), lines
    assert lines[0] == f'Marco asks "{request}"'
    assert " ".join(" ".join(lines[1:]).split()) == (
        'check_stock("Velvet Opera Cape") answers not_found; the catalog: '
        "not_found: no product matches Velvet Opera Cape")
    assert all(line.startswith("  ") for line in lines[1:])


@TERMINALS
def test_the_not_deployed_4a_box_fits_the_terminal(
        monkeypatch: pytest.MonkeyPatch, columns: int) -> None:
    """A box row wider than the terminal wraps, and every row after it breaks the box."""
    lab4_policy = importlib.import_module("lab4_policy")
    width = terminal(monkeypatch, columns)
    waiting = lab4_policy._deployed_rule_gap(
        "forbid(principal, action, resource) unless { false };",
        "forbid(principal, action, resource) unless { context.input.amount_cents <= 10000 };",
        True, ["policy credit_limit credit_limit-abc, policy set sha256:" + "0" * 16])
    assert waiting is not None and waiting.observed == lab4_policy.NOT_DEPLOYED
    for line in check.render(waiting).splitlines():
        assert len(check.plain(line)) <= width, line


def test_a_catch_up_never_points_at_a_next_line_it_hides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inside a catch-up no closing Next prints, so the box must not send the reader to one."""
    lab4_policy = importlib.import_module("lab4_policy")
    monkeypatch.setenv(check.NO_NEXT_ENV, "1")
    waiting = lab4_policy._deployed_rule_gap(
        "forbid(principal, action, resource) unless { false };",
        "forbid(principal, action, resource) unless { context.input.amount_cents <= 10000 };",
        True, ["policy credit_limit credit_limit-abc"])
    assert waiting is not None and "Next line" not in waiting.next_step
    assert "Next:" not in check.plain(lab4_policy.closing(True, waiting))
