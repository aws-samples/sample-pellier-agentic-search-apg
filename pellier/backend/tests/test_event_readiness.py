"""Event readiness is recorded at bootstrap for the facilitator, never shown to participants.

``scripts/event_readiness.py`` runs ``workshop-start.sh`` with a time cap, writes the
result to the participant's home and to CloudWatch, prints the latest record, and re-runs
the checks live on the box or through SSM. These tests drive it with fakes: no AWS, no box.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "event_readiness.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("pellier_event_readiness", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


readiness = _load()
NOW = datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)

READY_OUTPUT = """Pellier workshop start
------------------------------------------------------------
  \x1b[32m+ OK\x1b[0m    Pellier backend is healthy
  \x1b[32m+ OK\x1b[0m    psql 18.6, server 18.3
  \x1b[32m+ OK\x1b[0m    Theo's AgentCore Memory holds 2 preference records for Lab 3
------------------------------------------------------------
  \x1b[32m+ OK\x1b[0m    Ready for Lab 1
"""
MEMORY_MISSING = ("Facilitator: Theo's AgentCore Memory has no preference records, so Lab 3's "
                  "Memory finding will fail.")


class Completed:
    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0) -> None:
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def _runner(stdout: str, stderr: str = "", returncode: int = 0) -> Any:
    calls: List[List[str]] = []

    def run(argv: List[str], **kwargs: Any) -> Completed:
        calls.append(argv)
        return Completed(stdout, stderr, returncode)
    run.calls = calls  # type: ignore[attr-defined]
    return run


class Logs:
    """A CloudWatch Logs client that keeps what it was given."""

    def __init__(self, records: Optional[List[Dict[str, Any]]] = None, fail: bool = False) -> None:
        self.events: List[Dict[str, Any]] = []
        self.created: List[str] = []
        self.records = records or []
        self.fail = fail

    def create_log_group(self, logGroupName: str) -> None:
        if self.fail:
            raise RuntimeError("AccessDeniedException")
        self.created.append(logGroupName)

    def create_log_stream(self, logGroupName: str, logStreamName: str) -> None:
        self.created.append(f"{logGroupName}/{logStreamName}")

    def put_log_events(self, **kwargs: Any) -> None:
        self.events.append(kwargs)

    def describe_log_streams(self, **kwargs: Any) -> Dict[str, Any]:
        assert kwargs["orderBy"] == "LastEventTime" and kwargs["descending"] is True
        if not self.records:
            return {"logStreams": []}
        return {"logStreams": [{"logStreamName": "i-0abc"}]}

    def get_log_events(self, **kwargs: Any) -> Dict[str, Any]:
        return {"events": [{"message": json.dumps(r)} for r in self.records]}


def _record(ready: bool = True, final: str = "READY FOR LAB 1", age_hours: float = 1,
            instance: str = "i-0abc") -> Dict[str, Any]:
    return {"recordedAt": (NOW - timedelta(hours=age_hours)).isoformat(),
            "instanceId": instance, "ready": ready, "final": final,
            "lines": ["+ OK    Pellier backend is healthy", final]}


# ---------------------------------------------------------------------------
# the verdict from workshop-start.sh's output
# ---------------------------------------------------------------------------


def test_a_clean_start_is_ready_for_lab_one() -> None:
    lines, code = readiness.run_checks(run=_runner(READY_OUTPUT))
    assert readiness.verdict(lines, code, 180) == (True, "READY FOR LAB 1")
    assert all("\x1b" not in line for line in lines)


def test_the_first_failing_check_is_the_final_line() -> None:
    output = "  x FAIL  Pellier backend is not healthy at http://localhost:8000/api/health\n"
    lines, code = readiness.run_checks(run=_runner("", output, 1))
    ready, final = readiness.verdict(lines, code, 180)
    assert not ready and final.startswith("x FAIL  Pellier backend is not healthy")


def test_a_facilitator_issue_is_not_ready_even_when_lab_one_could_start() -> None:
    output = READY_OUTPUT.replace("+ OK\x1b[0m    Theo's AgentCore Memory holds 2 preference "
                                  "records for Lab 3", "- WARN\x1b[0m  " + MEMORY_MISSING)
    lines, code = readiness.run_checks(run=_runner(output))
    assert readiness.verdict(lines, code, 180) == (False, MEMORY_MISSING)


def test_a_check_that_runs_past_the_cap_is_recorded_as_a_failure() -> None:
    def run(argv: List[str], **kwargs: Any) -> Completed:
        assert kwargs["timeout"] == 5
        raise subprocess.TimeoutExpired(argv, 5, output="Pellier workshop start\n")

    lines, code = readiness.run_checks(run=run, cap=5)
    assert readiness.verdict(lines, code, 5) == (
        False, "x FAIL  the readiness check did not finish within 5 s")


# ---------------------------------------------------------------------------
# --record: the local file and CloudWatch
# ---------------------------------------------------------------------------


def test_record_writes_the_local_file_and_one_cloudwatch_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    logs, local = Logs(), tmp_path / ".pellier" / "readiness.json"
    status = readiness.main(["--record"], run=_runner(READY_OUTPUT), logs=logs, local=local,
                            now=lambda: NOW, instance=lambda: "i-0abc", on_box=True)
    assert status == 0
    saved = json.loads(local.read_text())
    assert saved["ready"] is True and saved["lines"][-1] == "READY FOR LAB 1"
    assert saved["recordedAt"] == NOW.isoformat() and saved["instanceId"] == "i-0abc"
    assert local.stat().st_mode & 0o077 == 0
    (event,) = logs.events
    assert event["logGroupName"] == "/aws/pellier/readiness"
    assert event["logStreamName"] == "i-0abc"
    assert json.loads(event["logEvents"][0]["message"]) == saved
    assert "READY FOR LAB 1" in capsys.readouterr().out


def test_a_cloudwatch_failure_keeps_the_local_record_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    local = tmp_path / "readiness.json"
    status = readiness.main(["--record"], run=_runner(READY_OUTPUT), logs=Logs(fail=True),
                            local=local, now=lambda: NOW, instance=lambda: "i-0abc",
                            on_box=True)
    assert status == 0
    assert local.exists()
    assert "could not write the CloudWatch record" in capsys.readouterr().err


def test_record_exits_non_zero_when_not_ready(tmp_path: Path) -> None:
    status = readiness.main(["--record"], run=_runner("", "  x FAIL  backend down\n", 1),
                            logs=Logs(), local=tmp_path / "r.json", now=lambda: NOW,
                            instance=lambda: "i-0abc", on_box=True)
    assert status == 1


# ---------------------------------------------------------------------------
# the latest record, on the box or from a laptop
# ---------------------------------------------------------------------------


def _show(tmp_path: Path, record: Optional[Dict[str, Any]], on_box: bool = True,
          logs: Optional[Logs] = None, extra: Optional[List[str]] = None) -> int:
    local = tmp_path / "readiness.json"
    if record is not None:
        local.write_text(json.dumps(record))
    return readiness.main(extra or [], logs=logs or Logs(), local=local, now=lambda: NOW,
                          instance=lambda: "i-0abc", on_box=on_box)


def test_a_ready_record_exits_zero_and_says_when_it_ran(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    assert _show(tmp_path, _record()) == 0
    out = capsys.readouterr().out
    assert "Recorded 2026-12-01T07:00:00+00:00 (1 h ago) on i-0abc" in out
    assert out.rstrip().endswith("READY FOR LAB 1")


def test_a_not_ready_record_exits_one(tmp_path: Path) -> None:
    assert _show(tmp_path, _record(False, "x FAIL  backend down")) == 1


def test_a_missing_record_exits_one_and_says_how_to_make_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    assert _show(tmp_path, None) == 1
    out = capsys.readouterr().out
    assert "No readiness record yet" in out and "--live" in out


def test_a_stale_ready_record_is_flagged_but_not_failed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    assert _show(tmp_path, _record(age_hours=30)) == 0
    assert "STALE: recorded 30 h ago, more than 24 h" in capsys.readouterr().out


def test_from_a_laptop_the_latest_record_comes_from_cloudwatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    logs = Logs(records=[_record(age_hours=3), _record(age_hours=2)])
    assert _show(tmp_path, None, on_box=False, logs=logs) == 0
    assert "(2 h ago)" in capsys.readouterr().out


def test_a_laptop_with_no_cloudwatch_record_exits_one(tmp_path: Path) -> None:
    assert _show(tmp_path, None, on_box=False, logs=Logs()) == 1


# ---------------------------------------------------------------------------
# --live: on the box, or through SSM from a laptop
# ---------------------------------------------------------------------------


class Ssm:
    def __init__(self, code: int = 0, output: str = "READY FOR LAB 1\n") -> None:
        self.code, self.output = code, output
        self.sent: List[Dict[str, Any]] = []
        self.polls = 0

    def send_command(self, **kwargs: Any) -> Dict[str, Any]:
        self.sent.append(kwargs)
        return {"Command": {"CommandId": "cmd-1"}}

    def get_command_invocation(self, **kwargs: Any) -> Dict[str, Any]:
        self.polls += 1
        if self.polls == 1:
            return {"Status": "InProgress"}
        status = "Success" if self.code == 0 else "Failed"
        return {"Status": status, "ResponseCode": self.code,
                "StandardOutputContent": self.output, "StandardErrorContent": ""}


def test_live_on_the_box_records_again(tmp_path: Path) -> None:
    run = _runner(READY_OUTPUT)
    status = readiness.main(["--live"], run=run, logs=Logs(), local=tmp_path / "r.json",
                            now=lambda: NOW, instance=lambda: "i-0abc", on_box=True)
    assert status == 0 and len(run.calls) == 1


def test_live_from_a_laptop_runs_the_record_through_ssm_on_the_recorded_instance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    ssm = Ssm()
    status = readiness.main(["--live"], logs=Logs(records=[_record(instance="i-0box")]),
                            ssm=ssm, local=tmp_path / "r.json", now=lambda: NOW,
                            instance=lambda: "unused", on_box=False, sleep=lambda s: None)
    assert status == 0
    (sent,) = ssm.sent
    assert sent["InstanceIds"] == ["i-0box"]
    assert sent["DocumentName"] == "AWS-RunShellScript"
    assert "scripts/event_readiness.py --record" in sent["Parameters"]["commands"][0]
    assert "READY FOR LAB 1" in capsys.readouterr().out


def test_live_from_a_laptop_reports_a_failed_box(tmp_path: Path) -> None:
    status = readiness.main(["--live", "--instance-id", "i-0box"], logs=Logs(),
                            ssm=Ssm(code=1, output="x FAIL  backend down\n"),
                            local=tmp_path / "r.json", now=lambda: NOW,
                            instance=lambda: "unused", on_box=False, sleep=lambda s: None)
    assert status == 1


def test_live_from_a_laptop_without_an_instance_id_says_what_to_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    status = readiness.main(["--live"], logs=Logs(), ssm=Ssm(), local=tmp_path / "r.json",
                            now=lambda: NOW, instance=lambda: "unused", on_box=False,
                            sleep=lambda s: None)
    assert status == 1
    assert "--instance-id" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# bootstrap records readiness, capped, after its health gate, and never shows it
# ---------------------------------------------------------------------------


def test_bootstrap_records_readiness_after_the_health_gate_without_failing_on_it() -> None:
    source = (REPO / "scripts" / "bootstrap-labs.sh").read_text(encoding="utf-8")
    gate = source.index("STEP 19: POST-BOOT HEALTH GATE")
    step = source.index('scripts/event_readiness.py" --record', gate)
    block = source[source.rfind("\n# ====", 0, step):source.index("\nfi\n", step)]
    assert 'sudo -u "$CODE_EDITOR_USER"' in block
    assert "timeout " in block
    assert "fail " not in block, "readiness is recorded, never a bootstrap failure"


def test_nothing_participant_facing_prints_readiness() -> None:
    environment = (REPO / "scripts" / "bootstrap-environment.sh").read_text(encoding="utf-8")
    labs = (REPO / "scripts" / "bootstrap-labs.sh").read_text(encoding="utf-8")
    for source in (environment, labs):
        bashrc_blocks = [part for part in source.split(".bashrc")[1:]]
        assert not any("event_readiness" in part[:2000] for part in bashrc_blocks)
