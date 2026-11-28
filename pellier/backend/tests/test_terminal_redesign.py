"""The participant terminal's compact output: ticks on a pass, only the failures otherwise,
the full box behind ``--details``, the progression elements, and the Operator card's words.

Everything runs on fixtures; nothing reaches Aurora or AWS.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
check = importlib.import_module("workshop_check")
card = importlib.import_module("card_vocabulary")
pellier_map = importlib.import_module("pellier_map")
lab_run = importlib.import_module("lab_run")
lab1_vector = importlib.import_module("lab1_vector")
lab2_check = importlib.import_module("lab2_check")
lab3_check = importlib.import_module("lab3_check")
lab4_policy = importlib.import_module("lab4_policy")
trace = importlib.import_module("trace_agentcore_calls")

CARD_SOURCE = (REPO / "pellier" / "frontend" / "src" / "operator" / "components"
               / "ProposedCreditCard.tsx")


@pytest.fixture(autouse=True)
def plain_terminal(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv(check.NO_NEXT_ENV, raising=False)
    monkeypatch.setattr(check, "terminal_width", lambda: 100)


# ---------------------------------------------------------------------------
# The shared renderer
# ---------------------------------------------------------------------------


def _finding(state: str) -> check.Finding:
    return check.Finding("3A", "title", state, "expected", "observed", ["evidence"], "next")


def test_the_full_box_is_what_it_was_with_or_without_the_compact_fields() -> None:
    plain = _finding(check.FAILED)
    ruled = check.with_rules(plain, "headline", [check.Rule("rule", "result")])
    assert check.render(ruled) == check.render(plain)


def test_a_pass_is_a_headline_then_one_tick_per_rule() -> None:
    verdict = check.with_rules(_finding(check.PASSED), "Lab 3A: Theo's lookups use his ID.", [
        check.Rule("Request names Jessica", "sent as CUST-THEO"),
        check.Rule("Nobody signed in", "refused")])
    lines = check.compact(verdict).splitlines()
    assert lines[0] == "Lab 3A: Theo's lookups use his ID."
    ticks = [line for line in lines if "\u2713" in line]
    assert len(ticks) == 2 and "sent as CUST-THEO" in ticks[0] and "refused" in ticks[1]
    assert "Evidence" not in "\n".join(lines)


def test_a_failure_prints_only_the_failing_rules_with_expected_observed_next() -> None:
    verdict = check.with_rules(_finding(check.FAILED), "headline", [
        check.Rule("Passed rule", "fine"),
        check.Rule("Failing rule", ok=False, expected="a", observed="b",
                   next_step="first line\nsecond line")])
    text = check.compact(verdict)
    assert "Passed rule" not in text and "\u2717  Failing rule" in text
    for word in ("Expected", "Observed", "Next"):
        assert word in text
    assert "Evidence" not in text and "evidence" not in text


def test_not_yet_and_failed_share_one_cross_and_could_not_check_is_a_question_mark() -> None:
    assert "\u2717" in check.compact(_finding(check.NOT_YET))
    assert "\u2717" in check.compact(_finding(check.FAILED))
    assert "  ?  " in check.compact(_finding(check.COULD_NOT_CHECK))


def test_details_prints_the_full_box_and_nothing_else_takes_a_value(capsys) -> None:
    finding = check.with_rules(_finding(check.FAILED), "headline", [])
    check.emit(finding, ["--details"], "Lab 3A check", "3A")
    out = capsys.readouterr().out
    assert "Evidence" in out and "Lab 3A check failed" in out
    check.emit(finding, [], "Lab 3A check", "3A")
    assert "Evidence" not in capsys.readouterr().out


def test_every_check_script_accepts_details_as_a_plain_flag() -> None:
    for name in ("lab2_check", "lab3_check", "lab3_row_ownership_check", "lab4_policy",
                 "lab4_credit", "trace_agentcore_calls"):
        source = (REPO / "scripts" / f"{name}.py").read_text(encoding="utf-8")
        assert '"--details", action="store_true"' in source, name
    for name in ("lab1_vector", "lab1_retry"):
        assert "check.emit(" in (REPO / "scripts" / f"{name}.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The checks, on fixtures
# ---------------------------------------------------------------------------


PASSING_1A = [("Stoneware Mugs, Set of 2", "Stoneware Mugs, Set of 2", "1.000", 20, "ok"),
              ("Hadley Linen Shirt", "Hadley Linen Shirt", "1.000", 20, "ok"),
              ("Sunday Morning Candle", "Sunday Morning Candle", "1.000", 20, "ok"),
              ("Sunday Morning Candle, Anna's requirements", "Espresso Cups, Set of 4",
               "0.460", 5, "ok")]



def test_1a_before_the_fix_is_one_cross_not_one_per_search() -> None:
    rows = [(name, "(none)", "none", 0, "fails") for name, *_ in PASSING_1A]
    finding = check.Finding("1A", "t", check.FAILED, "e", "o")
    text = check.compact(lab1_vector.verdict(finding, rows))
    assert text.count("\u2717") == 1 and text.count("Next") == 1
    assert "nothing came back for any of the 4 searches" in text
    assert "(none)" not in text and lab1_vector.SOLUTION_COMMAND in text


def test_1a_a_single_failing_search_names_that_search_and_says_next_once() -> None:
    rows = [*PASSING_1A[:3], (PASSING_1A[3][0], "Sunday Morning Candle", "1.000", 5, "fails")]
    finding = check.Finding("1A", "t", check.FAILED, "e", "o")
    text = check.compact(lab1_vector.verdict(finding, rows))
    assert "\u2717  Sunday Morning Candle again, with Anna's requirements" in text
    assert "Sunday Morning Candle came back first (similarity 1.000)" in text
    assert text.count("Next") == 1


def _patch_2b(monkeypatch) -> None:
    catalogs = {"Velvet Opera Cape": {"matches": [], "stock": []},
                "Linen shirt": {"matches": [{"product_id": "2", "name": "a"},
                                            {"product_id": "3", "name": "b"},
                                            {"product_id": "4", "name": "c"}], "stock": []},
                "Quilted Silk Vest": {"matches": [{"product_id": "43", "name": "v"}],
                                      "stock": [{"warehouse_code": "BK-01", "quantity": 0}]},
                "Hadley Linen Shirt": {"matches": [{"product_id": "2", "name": "h"}],
                                       "stock": [{"warehouse_code": "BK-01", "quantity": 0},
                                                 {"warehouse_code": "ATX-02", "quantity": 6},
                                                 {"warehouse_code": "PDX-01", "quantity": 14}]}}
    monkeypatch.setattr(lab2_check, "catalog_answer", lambda conn, query: catalogs[query])
    monkeypatch.setattr(lab2_check, "judge_function",
                        lambda conn, worksheet=None: (None, "live", "evidence"))
    monkeypatch.setattr(lab2_check, "keeps_contract", lambda case, env, catalog: True)


def _inputs():
    return {case: (lab2_check.DEFAULT_INPUTS[case], "the check") for case in lab2_check.CASES}


def test_2b_pass_is_four_plain_ticks(monkeypatch) -> None:
    _patch_2b(monkeypatch)
    finding, _rows = lab2_check.judge_2b(None, lambda product_query: '{"status": "x"}',
                                         _inputs())
    text = check.compact(finding)
    assert "Velvet Opera Cape" in text and "not carried" in text
    assert "Linen shirt" in text and "3 products" in text
    assert "Quilted Silk Vest" in text and "0 units, sold out" in text
    assert "Hadley Linen Shirt" in text and "20 units, in stock" in text
    assert text.count("\u2713") == 4
    for hidden in ("not_found", "ambiguous", "ATX-02", "sha256"):
        assert hidden not in text


def test_2b_failure_names_the_cape_with_expected_observed_next(monkeypatch) -> None:
    _patch_2b(monkeypatch)
    monkeypatch.setattr(lab2_check, "keeps_contract",
                        lambda case, env, catalog: case != "unknown")
    finding, _rows = lab2_check.judge_2b(
        None, lambda product_query: '{"status": "success", "total_units": 0}', _inputs())
    text = check.compact(finding)
    assert "\u2717  Velvet Opera Cape" in text and "Tests" not in text
    assert "Expected not carried" in text and "Observed 0 units" in text
    assert "no row, not 0 units" in text and text.count("\u2717") == 1


def test_3a_failure_before_the_fix_shows_only_the_failing_rules() -> None:
    published = frozenset({"get_orders", "get_return_policy"})
    probes = {read: {"sent": "CUST-JESSICA", "unsigned": "CUST-JESSICA"}
              for read in lab3_check.SHOPPER_READS}
    findings = lab3_check.judge_catalog(published, ("get_orders", "get_return_policy"),
                                        frozenset(), probes)
    text = check.compact(check.combine("3A", lab3_check.HEADLINE_3A, findings))
    assert "get_tickets published on the Gateway" in text
    assert "the server sends CUST-JESSICA" in text
    assert "Publish it in 3A-1-publish-tool.py" in text
    assert "Evidence" not in text and "\u2713" not in text


def test_3a_pass_matches_the_owner_example() -> None:
    probes = {read: {"sent": "CUST-THEO", "unsigned": "refused"}
              for read in lab3_check.SHOPPER_READS}
    findings = lab3_check.judge_catalog(
        frozenset({"get_orders", "get_tickets", "get_return_policy"}),
        ("get_orders", "get_return_policy", "get_tickets"),
        frozenset({"get_orders", "get_tickets"}), probes)
    text = check.compact(check.combine("3A", lab3_check.HEADLINE_3A, findings))
    assert text.startswith("Lab 3A: the server binds the caller, so the model cannot pick whose "
                           "data it reads.")
    assert re.search(r"Request names Jessica\s+sent as CUST-THEO", text)
    assert re.search(r"Nobody signed in\s+refused", text)
    assert re.search(r"Store credits\s+on no shopper agent", text)


def test_3b_memory_shows_the_preferences_the_turn_used_without_ids() -> None:
    seeded = {"namespace": "/pellier/preferences/CUST-THEO/", "actor": "CUST-THEO",
              "session": "prefseed", "events": [{"eventId": "0000001-theo-1"}],
              "records": [{"memoryRecordId": "mem-1"}, {"memoryRecordId": "mem-2"}]}
    remembered = [{"record_id": "mem-1", "preference": "Prefers one quiet tactile piece he'll "
                   "keep, not many items"},
                  {"record_id": "mem-2", "preference": "Prefers hand-thrown ceramics, stoneware "
                   "and linen throws"},
                  {"record_id": "mem-3", "preference": "Not used by the turn"}]
    finding = lab3_check.judge_memory("pellier_PellierMemory-x", seeded, remembered,
                                      {"turn_id": "turn-abc", "record_ids": ["mem-1", "mem-2"]})
    text = check.compact(finding)
    assert "Theo's agent used his saved preferences from AgentCore Memory" in text
    assert "\u2022 Prefers one quiet tactile piece" in text
    assert "\u2022 Prefers hand-thrown ceramics" in text and "Not used by the turn" not in text
    assert "Stored under Theo's own customer ID" in text
    for hidden in ("mem-1", "turn-abc", "0000001", "pellier_PellierMemory"):
        assert hidden not in text
    assert "mem-1" in check.render(finding)


# ---------------------------------------------------------------------------
# The Operator card's words
# ---------------------------------------------------------------------------


def test_the_terminal_uses_the_operator_cards_sentences() -> None:
    source = CARD_SOURCE.read_text(encoding="utf-8")
    for sentence in (card.APPROVED_SENTENCE, card.NO_APPROVAL_SENTENCE,
                     card.NOT_WRITTEN_SENTENCE, card.RETRY_SENTENCE, card.NOT_WRITTEN_TAG,
                     card.NO_APPROVAL_TAG, card.RECORDED_ONCE_TAG):
        assert sentence in source, sentence
    assert "The Gateway answered: ${outcome}." in source
    assert "' The tool never ran.'" in source
    assert card.policy_row("DENY", tool_ran=False) == (
        "DENY", "The Gateway answered: denied. The tool never ran.")


def _call(**over):
    base = {"request_id": "req-1", "trace_id": "trace-1", "parent_span_id": None,
            "started_ns": 1_700_000_000_000_000_000, "tool": "give_store_credit",
            "target": "pellier-operator-tools", "decision": "DENY", "gateway_denied": True,
            "policies": ["credit_limit"], "reason": None, "subject": "sub-nadia",
            "token_use": "access", "authorizer": "CUSTOM_JWT", "identity_checked": True,
            "gateway_ms": 12, "lambda_ms": None}
    return {**base, **over}


def test_the_agentcore_trace_keeps_its_rows_in_plain_values() -> None:
    lines = trace.render_call(_call(), {"sub-nadia": "nadia"})
    text = "\n".join(lines)
    assert re.match(r"\d\d:\d\d:\d\d  nadia\s+give_store_credit  DENY  ->  Lambda never called",
                    lines[0])
    for label in ("Runtime", "Identity", "Policy", "Gateway"):
        assert label in text
    assert "Gateway accepted nadia's sign-in token" in text
    assert "The Gateway answered: denied. The tool never ran." in text
    assert "Gateway refused the call before the tool ran" in text
    for hidden in ("CUSTOM_JWT", "Cognito", "trace-1", "req-1"):
        assert hidden not in text
    assert "trace trace-1  request req-1" in "\n".join(
        trace.render_call(_call(), {"sub-nadia": "nadia"}, details=True))


# ---------------------------------------------------------------------------
# The progression: the Path line, the arc and the maps
# ---------------------------------------------------------------------------


def _steps(path, finding, tools, tags=(), rail="in-process"):
    path.reset()
    path.observe({"id": "route", "finding": finding, "tags": ["Router", *tags],
                  "builder": {"tool": None, "rail": rail}})
    for tool in tools:
        path.observe({"id": f"step-{tool}", "tags": ["Aurora"], "builder": {"tool": tool}})


@pytest.mark.parametrize("persona, finding, tools, rail, expected", [
    ("anna", "Sent to the Catalog agent: housewarming", ["search_products"], lab_run.IN_PROCESS,
     "Anna \u2192 Router \u2192 Catalog agent \u2192 search_products \u2192 "
     "Aurora (words + meaning)"),
    ("marco", "Sent to the Stock agent", ["check_stock"], lab_run.IN_PROCESS,
     "Marco \u2192 Router \u2192 Stock agent \u2192 check_stock \u2192 Aurora warehouse rows"),
    ("theo", "Sent to the Support agent", ["get_tickets"], lab_run.MANAGED,
     "Theo, signed in \u2192 AgentCore Runtime \u2192 Support agent \u2192 Gateway (Cedar checks "
     "each call) \u2192 Lambda \u2192 Aurora (his rows only)"),
    ("jessica", "Sent to the Support agent", ["ask_a_person"], lab_run.IN_PROCESS,
     "Jessica \u2192 Router \u2192 Support agent \u2192 ask_a_person \u2192 Nadia reviews"),
])
def test_the_path_line_is_read_from_the_turn_that_ran(persona, finding, tools, rail, expected):
    path = lab_run.TurnPath()
    _steps(path, finding, tools, rail=rail)
    assert path.line(persona, rail) == expected


def test_the_path_names_a_layer_only_when_the_turn_showed_it() -> None:
    path = lab_run.TurnPath()
    _steps(path, "Sent to the Support agent", [], tags=("Memory",), rail=lab_run.MANAGED)
    assert path.line("theo", lab_run.MANAGED) == (
        "Theo, signed in \u2192 AgentCore Runtime with Memory \u2192 Support agent")
    _steps(path, "Sent to the Support agent", [])
    assert "AgentCore" not in path.line("theo", lab_run.IN_PROCESS)


@pytest.mark.parametrize("task, expected", [
    ("1A", ""), ("1B", ""), ("2A", ""), ("2B", ""),
    ("3A", "Retrieve \u2713  Ground \u2713  Deploy \u25cf  Govern \u00b7"),
    ("3B", "Retrieve \u2713  Ground \u2713  Deploy \u2713  Govern \u00b7"),
])
def test_the_arc_lights_the_labs_the_path_has_passed(task, expected) -> None:
    assert pellier_map.arc(task) == expected


def test_the_lab4_arc_stays_current_until_the_payment_and_replay_are_proved(capsys) -> None:
    # Participants pass 4B first, pay and replay, then run the final 4A probe.
    # Neither task check reads Jessica's payment rows. The absence SQL does that next.
    for task in ("4B", "4A"):
        passed = check.with_rules(check.Finding(task, "t", check.PASSED, "e", "o"), "h", [])
        check.emit(passed, [], f"Lab {task} check", task)
        out = capsys.readouterr().out.splitlines()
        assert f"Lab {task} check passed" in out
        assert out[-1] == "Retrieve ✓  Ground ✓  Deploy ✓  Govern ●"


def test_a_pass_ends_with_the_arc_and_a_lab_end_adds_the_map(capsys, monkeypatch) -> None:
    """Labs 3 and 4 keep the arc and the map; Labs 1 and 2 end with the proved grid."""
    monkeypatch.setattr(pellier_map, "facts",
                        lambda env=None: {"runtime": True, "memory": True, "gateway": True})
    passed = check.with_rules(check.Finding("3B", "t", check.PASSED, "e", "o"), "h",
                              [check.Rule("rule", "result")])
    check.emit(passed, [], "Lab 3B check", "3B")
    out = capsys.readouterr().out.rstrip().splitlines()
    assert out[-1] == pellier_map.arc("3B")
    assert "Pellier so far" in "\n".join(out) and "Lab 2  + Stock agent" in "\n".join(out)
    check.emit(check.with_rules(check.Finding("2B", "t", check.PASSED, "e", "o"), "h", []), [],
               "Lab 2B check", "2B")
    lab_2 = capsys.readouterr().out
    assert "Pellier so far" not in lab_2 and "Retrieve" not in lab_2
    check.emit(check.with_rules(check.Finding("1A", "t", check.PASSED, "e", "o"), "h", []), [],
               "Lab 1A check", "1A")
    lab_1 = capsys.readouterr().out
    assert "Pellier so far" not in lab_1 and "Retrieve" not in lab_1
    check.emit(check.with_rules(check.Finding("1B", "t", check.PASSED, "e", "o"), "h", []), [],
               "Lab 1B check", "1B", after=["See it", "Row"])
    lines = capsys.readouterr().out.splitlines()
    assert "Pellier so far" not in lines and "Retrieve" not in "\n".join(lines)
    assert lines[lines.index("Lab 1B check passed") + 1:][:2] == ["See it", "Row"]
    assert lines[-2].startswith("Next  In the guide, open Lab 2")


@pytest.mark.parametrize("lab, last", [
    (1, "Aurora: full text + pgvector + RRF + Cohere Rerank"),
    (2, "Aurora: warehouse rows"), (3, "Aurora row rules"), (4, "one row per key")])
def test_each_labs_map_ends_with_what_that_lab_added(lab, last) -> None:
    have = {"runtime": True, "memory": True, "gateway": True}
    lines = pellier_map.system_map(lab, have).splitlines()
    assert len(lines) == lab + 1 <= 5
    assert lines[-1].startswith("  \u25cf") and lines[-1].endswith(last)
    assert all(line.startswith("  \u2713") for line in lines[1:-1])


def test_the_map_never_claims_a_component_that_is_not_running() -> None:
    off = {"runtime": False, "memory": False, "gateway": False}
    line = pellier_map.system_map(3, off).splitlines()[-1]
    for name in ("AgentCore Runtime", "Memory", "Gateway", "Cedar", "Lambda"):
        assert name not in line
    assert "Aurora row rules" in line


def test_the_finale_shows_only_the_components_the_trace_found() -> None:
    have = {"runtime": True, "memory": True, "gateway": True}
    text = pellier_map.finale(have, ["AgentCore Runtime", "Gateway", "Policy (Cedar)"])
    assert "AgentCore Runtime \u2500 Gateway \u2500 Policy (Cedar)" in text
    assert "Lambda" not in text and "Memory" not in text
    assert text.splitlines()[0] == "Pellier, all four labs"


def test_each_task_headline_states_one_idea() -> None:
    lab1_retry = importlib.import_module("lab1_retry")
    lab3_row = importlib.import_module("lab3_row_ownership_check")
    lab4_credit = importlib.import_module("lab4_credit")
    assert lab1_retry.HEADLINE == ("Lab 1B: Anna's budget, stock rule and exclusion filter first, "
                                   "and survive every retry.")
    assert lab2_check.HEADLINE_2A == (
        "Lab 2A: Marco's stock answer comes only from the warehouse row.")
    assert lab2_check.HEADLINE_2B.startswith("Lab 2B: not carried is not the same as sold out")
    assert lab3_check.HEADLINE_3B == lab3_row.HEADLINE == (
        "Lab 3B: Aurora enforces ownership too, on the deployed AgentCore path.")
    assert lab4_policy.HEADLINE_4A == (
        "Lab 4A: Cedar decides what may be attempted: a credit up to $100.")
    assert lab4_credit.HEADLINE == "Lab 4B: the database limits what the credit writer can change."
    follow = importlib.import_module("follow_credit")
    assert "paid exactly once" in follow.PAID_ONCE


# ---------------------------------------------------------------------------
# Task 1A's check: the reference lookup, then the pass line as the last line
# ---------------------------------------------------------------------------
REPAIRED = lab1_vector.Lookup(rows=[("Stoneware Pour-Over Set", 0.0, 1.0),
                                    ("Ceramic Tumblers", 0.31, 0.69),
                                    ("Stoneware Mugs, Set of 2", 0.329, 0.671),
                                    ("Ceramic Pitcher, Slate, 750 ml", 0.37, 0.63),
                                    ("Ceramic Pitcher, Slate, 1500 ml", 0.381, 0.619)])


def _run_1a(monkeypatch, capsys, state, found, argv=()):
    finding = check.Finding("1A", lab1_vector.TITLE, state, "e", "o", ["evidence"], "next")
    rows = PASSING_1A if state == check.PASSED else [
        (name, "(none)", "none", 0, "fails") for name, *_ in PASSING_1A]
    monkeypatch.setattr(lab1_vector, "run_all",
                        lambda: (lab1_vector.judge_lookup(finding, found), rows, found))
    monkeypatch.setattr(check, "refuse_missing_lab_file", lambda lab: False)
    code = lab1_vector.main(list(argv))
    return code, capsys.readouterr().out


def test_1a_pass_prints_the_lookup_then_the_pass_line_last(monkeypatch, capsys) -> None:
    code, out = _run_1a(monkeypatch, capsys, check.PASSED, REPAIRED)
    lines = out.rstrip("\n").splitlines()
    assert code == 0
    assert lines == [*lab1_vector.lookup_lines(REPAIRED), "", "Lab 1A check passed"]
    assert lines[1] == "5 products returned."
    assert re.fullmatch(r"Ceramic Tumblers +0\.310 +0\.690", lines[4])
    for hidden in ("\u2713", "Each unfiltered", "Next", "Retrieve"):
        assert hidden not in out, hidden


def test_1a_pass_line_is_green_on_a_terminal_and_plain_otherwise(monkeypatch, capsys) -> None:
    monkeypatch.setattr(check, "colour_enabled", lambda stream=None: True)
    _, out = _run_1a(monkeypatch, capsys, check.PASSED, REPAIRED)
    assert out.rstrip("\n").splitlines()[-1] == "\033[32mLab 1A check passed\033[0m"
    monkeypatch.setattr(check, "colour_enabled", lambda stream=None: False)
    _, out = _run_1a(monkeypatch, capsys, check.PASSED, REPAIRED)
    assert out.rstrip("\n").splitlines()[-1] == "Lab 1A check passed" and "\033[" not in out


def test_1a_details_keep_the_four_checks_and_the_candle_exclusion(monkeypatch, capsys) -> None:
    _, out = _run_1a(monkeypatch, capsys, check.PASSED, REPAIRED, ["--details"])
    assert "Storefront products closest to the Stoneware Pour-Over Set" in out
    assert "searched with" in out and "Espresso Cups" in out and "Hadley Linen Shirt" in out
    assert out.rstrip("\n").splitlines()[-1] == "Lab 1A check passed"


@pytest.mark.parametrize("found, shown", [
    (lab1_vector.Lookup(), "0 products returned."),
    (lab1_vector.Lookup(error="OperationalError: connection refused"),
     "Lookup failed: OperationalError: connection refused"),
])
def test_1a_failure_shows_the_lookup_the_reason_and_the_next_step(
        monkeypatch, capsys, found, shown) -> None:
    code, out = _run_1a(monkeypatch, capsys, check.FAILED, found)
    lines = out.rstrip("\n").splitlines()
    assert code == 1
    assert lines[:2] == ["Storefront products closest to the Stoneware Pour-Over Set", shown]
    assert "nothing came back for any of the 4 searches" in out
    assert 'read "Find the line and apply the provided fix"' in out
    assert lines[-1] == "Lab 1A check failed"



@pytest.mark.parametrize("found, mark, observed", [
    (lab1_vector.Lookup(error="the Stoneware Pour-Over Set has no stored embedding"), "?",
     "the pour-over lookup failed: the Stoneware Pour-Over Set has no stored embedding"),
    (lab1_vector.Lookup(), "\u2717", "the pour-over lookup returned 0 products, not 5"),
    (lab1_vector.Lookup(rows=REPAIRED.rows[1:] + REPAIRED.rows[:1]), "\u2717",
     "the pour-over lookup put Ceramic Tumblers first, not the Stoneware Pour-Over Set"),
])
def test_1a_passing_probes_do_not_pass_without_the_lookup_the_participant_reads(
        monkeypatch, capsys, found, mark, observed) -> None:
    """Codex's review: the four probes passed while the visible lookup had failed."""
    code, out = _run_1a(monkeypatch, capsys, check.PASSED, found)
    assert code == 1
    assert "Lab 1A check passed" not in out
    assert out.rstrip("\n").splitlines()[-1] == "Lab 1A check failed"
    assert f"  {mark}  The pour-over lookup" in out and observed in " ".join(out.split())
    assert "Troubleshoot with Claude Code or go deeper" in out
    assert "solution --lab 1 --task 1A" not in out



# ---------------------------------------------------------------------------
# The proved grid that ends Labs 1 and 2
# ---------------------------------------------------------------------------
def test_the_grid_after_lab_2_has_both_rows_and_counts_only_proved_labs() -> None:
    rows = [("1 \u00b7 Retrieve", "Search by meaning and a retry that keeps Anna\u2019s rules",
             "Anna\u2019s retry kept all three rules."),
            ("2 \u00b7 Ground", "Inventory tool backed by Aurora",
             "Brooklyn had 0 shirts. The Velvet Opera Cape had no catalog entry.")]
    lines = pellier_map.proved_grid(rows, width=200)
    assert lines[0] == "What you\u2019ve proved \u00b7 2 of 4 labs"
    assert lines[1].split() == ["Lab", "What", "you", "added", "What", "you", "proved"]
    assert lines[2].startswith("1 \u00b7 Retrieve") and lines[3].startswith("2 \u00b7 Ground")
    unproved = pellier_map.proved_grid([(*rows[0][:2], None), rows[1]], width=200)
    assert unproved[0].endswith("1 of 4 labs") and pellier_map.NOT_PROVED in unproved[2]


def test_the_grid_wraps_to_a_narrow_terminal() -> None:
    rows = [("2 \u00b7 Ground", "Inventory tool backed by Aurora",
             "Brooklyn had 0 shirts. The Velvet Opera Cape had no catalog entry.")]
    assert all(len(line) <= 70 for line in pellier_map.proved_grid(rows, width=70))


def test_the_2b_pass_prints_the_grid_then_the_resend(monkeypatch, capsys) -> None:
    finding = check.with_rules(check.Finding("2B", "t", check.PASSED, "e", "o"), "h",
                               [check.Rule("Velvet Opera Cape", "not carried")])
    grid = pellier_map.proved_grid([("2 \u00b7 Ground", "Inventory tool backed by Aurora",
                                     "Brooklyn had 0 shirts.")], width=100)
    monkeypatch.setattr(lab2_check, "run", lambda task, inputs: (finding, []))
    monkeypatch.setattr(lab2_check, "lab_2_grid", lambda unknown: grid)
    monkeypatch.setattr(check, "refuse_missing_lab_file", lambda lab: False)
    assert lab2_check.main(["--task", "2B"]) == 0
    lines = capsys.readouterr().out.splitlines()
    passed = lines.index("Lab 2B check passed")
    assert lines[passed + 1:passed + 2 + len(grid)] == ["", *grid]
    assert lines[-1].endswith("send --lab 2 --task 2B")


def test_a_2b_check_that_did_not_pass_prints_no_grid(monkeypatch, capsys) -> None:
    finding = check.Finding("2B", "t", check.FAILED, "e", "o", [], "next")
    monkeypatch.setattr(lab2_check, "run", lambda task, inputs: (finding, []))
    monkeypatch.setattr(lab2_check, "lab_2_grid", lambda unknown: ["SHOULD NOT PRINT"])
    monkeypatch.setattr(check, "refuse_missing_lab_file", lambda lab: False)
    assert lab2_check.main(["--task", "2B"]) == 1
    assert "SHOULD NOT PRINT" not in capsys.readouterr().out
