"""Task 3B accepts the Lab 1 search plan the deploy chose, and only a stale deploy fails.

The Lab 3 deploy ships the participant's own search plan only when both Lab 1 checks pass and
the file matches the supplied one outside its marked region, and the supplied plan otherwise.
Task 3B used to hash the participant's file always, so a correct fallback deploy read as
"another build answered" and the redeploy it prescribed shipped the same fallback again.
The expected digests here come from the files, never from the receipt.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

from tests.test_lambda_package import (
    PROVISIONED_SCHEMAS,
    _provisioner,
    _stamped,
    _two_lambdas,
)

REPO = Path(__file__).resolve().parents[3]
DEPLOY = REPO / "scripts" / "deploy"
sys.path[:0] = [str(REPO / "scripts"), str(DEPLOY)]
import lab3_check as lab3  # noqa: E402
from common.fingerprint import SOURCE_PATHS, compute_fingerprint  # noqa: E402
from deploy_lambda import package_files  # noqa: E402

check = lab3.check
RUNTIME = "r" * 64
YOUR_PLAN = REPO / "pellier" / "backend" / "services" / "search_plan.py"
SUPPLIED_RECEIPT = {"runs": "supplied", "failing_checks": ["1B"],
                    "edited_outside_region": False, "updated": True}
YOURS_RECEIPT = {"runs": "yours", "failing_checks": [], "edited_outside_region": False,
                 "updated": True}


def _tools_digest(search_plan: Path | None) -> str:
    files = package_files(str(DEPLOY / "pellier_store_tools.py"),
                          "pellier_store_tools.lambda_handler")
    if search_plan is not None:
        files["services/search_plan.py"] = search_plan
    return compute_fingerprint(files)


YOURS_DIGEST = _tools_digest(YOUR_PLAN)
SUPPLIED_DIGEST = _tools_digest(None)


def _row(tools: str | None, runtime: str = RUNTIME) -> dict:
    return {"audit_id": 7, "turn_id": "turn-theo", "tool": "get_tickets",
            "deployed_fingerprint": runtime, "deployed_tools_fingerprint": tools}


def test_the_two_legitimate_choices_are_different_builds() -> None:
    assert YOURS_DIGEST != SUPPLIED_DIGEST, "the starter search plan must differ from the supplied"


def test_an_older_receipt_accepts_the_supplied_search_plan_as_well_as_the_participants() -> None:
    assert lab3.judge_build(_row(SUPPLIED_DIGEST), RUNTIME).state == check.PASSED
    assert lab3.judge_build(_row(YOURS_DIGEST), RUNTIME).state == check.PASSED


@pytest.mark.parametrize("receipt", [None, {}, {"runs": "elsewhere"}])
def test_a_receipt_without_a_usable_choice_is_an_older_receipt(receipt) -> None:
    finding = lab3.judge_build(_row(SUPPLIED_DIGEST), RUNTIME, search_plan=receipt)
    assert finding.state == check.PASSED


def test_a_valid_fallback_passes_and_says_which_search_plan_shipped_and_why() -> None:
    finding = lab3.judge_build(_row(SUPPLIED_DIGEST), RUNTIME, search_plan=SUPPLIED_RECEIPT)
    assert finding.state == check.PASSED
    assert "provided Lab 1 search plan" in finding.observed
    assert any("the provided Lab 1 search plan shipped: Lab 1 check 1B did not pass" in line
               for line in finding.evidence)
    assert f"checkout tools   {SUPPLIED_DIGEST}" in finding.evidence


def test_a_fallback_because_of_an_edit_outside_the_region_says_so() -> None:
    receipt = {**SUPPLIED_RECEIPT, "failing_checks": [], "edited_outside_region": True}
    finding = lab3.judge_build(_row(SUPPLIED_DIGEST), RUNTIME, search_plan=receipt)
    assert finding.state == check.PASSED
    assert any("outside its marked region" in line for line in finding.evidence)


def test_the_participants_own_plan_passes_when_the_receipt_says_it_shipped() -> None:
    finding = lab3.judge_build(_row(YOURS_DIGEST), RUNTIME, search_plan=YOURS_RECEIPT)
    assert finding.state == check.PASSED
    assert finding.observed == "the two builds match"
    assert not any("provided Lab 1 search plan shipped" in line for line in finding.evidence)


@pytest.mark.parametrize("receipt, deployed", [(YOURS_RECEIPT, SUPPLIED_DIGEST),
                                               (SUPPLIED_RECEIPT, YOURS_DIGEST)])
def test_a_tools_build_that_is_not_the_one_the_receipt_names_is_stale(receipt, deployed) -> None:
    finding = lab3.judge_build(_row(deployed), RUNTIME, search_plan=receipt)
    assert finding.state == check.FAILED
    assert "--mode participant" in finding.next_step


@pytest.mark.parametrize("receipt", [None, YOURS_RECEIPT, SUPPLIED_RECEIPT])
def test_a_stale_tools_package_fails_with_redeploy_guidance(receipt) -> None:
    finding = lab3.judge_build(_row("e" * 64), RUNTIME, search_plan=receipt)
    assert finding.state == check.FAILED
    assert any("stale deploy" in line for line in finding.evidence)
    assert "deploy your Task 3A change with --mode participant" in finding.next_step
    assert lab3.SEND in finding.next_step


@pytest.mark.parametrize("digest", [SUPPLIED_DIGEST, YOURS_DIGEST])
def test_a_runtime_without_the_task_3a_edit_fails_whatever_the_tools_are(digest) -> None:
    finding = lab3.judge_build(_row(digest, runtime="a" * 64), RUNTIME,
                               search_plan=SUPPLIED_RECEIPT if digest == SUPPLIED_DIGEST
                               else YOURS_RECEIPT)
    assert finding.state == check.FAILED
    assert finding.observed == "another build answered"
    assert "deploy your Task 3A change with --mode participant" in finding.next_step


def test_a_pinned_tools_digest_still_compares_exactly() -> None:
    assert lab3.judge_build(_row("p" * 64), RUNTIME, "p" * 64).state == check.PASSED
    assert lab3.judge_build(_row("p" * 64), RUNTIME, "q" * 64).state == check.FAILED


def test_a_row_without_a_tools_stamp_cannot_be_compared() -> None:
    assert lab3.judge_build(_row(None), RUNTIME,
                            search_plan=SUPPLIED_RECEIPT).state == check.COULD_NOT_CHECK


# ---------------------------------------------------------------------------
# The receipt the deploy writes
# ---------------------------------------------------------------------------


def _receipt(path: Path, body: object) -> None:
    path.write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")


@pytest.fixture
def receipts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    tmp_copy, state = tmp_path / "participant.json", tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("AGENTCORE_PARTICIPANT_OUTPUT_JSON", str(tmp_copy))
    monkeypatch.setenv("PELLIER_STATE_DIR", str(state))
    return tmp_copy, state / "participant-receipt.json"


def test_the_deploys_choice_is_read_from_its_participant_receipt(receipts) -> None:
    tmp_copy, _ = receipts
    _receipt(tmp_copy, {"status": "ready", "lab1_search": SUPPLIED_RECEIPT})
    assert lab3.deploy_search_plan() == SUPPLIED_RECEIPT


def test_the_copy_kept_under_the_state_directory_serves_after_a_reboot(receipts) -> None:
    _, saved = receipts
    _receipt(saved, {"lab1_search": YOURS_RECEIPT})
    assert lab3.deploy_search_plan() == YOURS_RECEIPT


@pytest.mark.parametrize("body", [{"status": "ready"}, "not json", [], {"lab1_search": "x"},
                                  {"lab1_search": {"runs": "elsewhere"}}])
def test_a_receipt_that_predates_the_field_or_is_unreadable_gives_no_choice(
        receipts, body) -> None:
    tmp_copy, _ = receipts
    _receipt(tmp_copy, body)
    assert lab3.deploy_search_plan() is None


def test_no_receipt_gives_no_choice(receipts) -> None:
    assert lab3.deploy_search_plan() is None


# ---------------------------------------------------------------------------
# The deploy and the check agree, end to end through a fake Lambda
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("failing, runs", [([], "yours"), (["1B"], "supplied")])
def test_what_the_deploy_ships_is_what_task_3b_accepts(
        monkeypatch, tmp_path: Path, failing: list[str], runs: str) -> None:
    provisioner = _provisioner()
    lambdas, store, _ = _two_lambdas(provisioner, monkeypatch, PROVISIONED_SCHEMAS)
    monkeypatch.setattr(provisioner, "_lab1_checks_failing", lambda repo, env: failing)
    shipped = provisioner._ship_participant_modules(
        REPO, region="us-east-1", identity=provisioner.deployment_identity(), env={},
        reset_to_starters=False)
    assert shipped["lab1_search"]["runs"] == runs
    stamped = _stamped(lambdas.packages[store], tmp_path / "store", SOURCE_PATHS)
    assert stamped == (YOURS_DIGEST if runs == "yours" else SUPPLIED_DIGEST)
    supplied_plan = (REPO / "solutions" / "lab-1-retrieve" / "retrieval"
                     / "search_plan_solution.py")
    shipped_plan = zipfile.ZipFile(io.BytesIO(lambdas.packages[store])).read(
        "services/search_plan.py")
    assert shipped_plan == (YOUR_PLAN if runs == "yours" else supplied_plan).read_bytes()
    assert lab3.judge_build(_row(stamped), RUNTIME).state == check.PASSED
    finding = lab3.judge_build(_row(stamped), RUNTIME, search_plan=shipped["lab1_search"])
    assert finding.state == check.PASSED
