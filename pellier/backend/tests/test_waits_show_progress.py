"""Every wait a participant sits through shows a bar, measured on event 12 (2026-10-23).

Run in a terminal on the event's box, these sat silent: each managed turn sent by
``lab_run.py send`` (20 s, 14 s and 5 s for Lab 3's three requests, because the managed rail
delivers a turn's steps in one batch), Lab 1's ``sudo systemctl restart pellier`` (14 s while
the unit rebuilds the frontend), and the start of the observability check (3.5 to 5.9 s),
the Lab 3B check (3.9 s) and the evidence export (3.7 s). Each now names what it waits for.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, List

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "deploy"))
import lab3_check  # noqa: E402
import lab_run  # noqa: E402
import observability_check  # noqa: E402
import workshop_check as check  # noqa: E402
import workshop_evidence  # noqa: E402


class Bars:
    """Stands in for ``wait_progress.waiting``: records each bar's label and what preceded it."""

    def __init__(self, capsys: pytest.CaptureFixture[str]) -> None:
        self.capsys, self.shown, self.printed_before = capsys, [], []

    @contextmanager
    def __call__(self, label: str, *, typical: float, **_: Any) -> Iterator[None]:
        assert typical > 0
        self.shown.append(label)
        self.printed_before.append(self.capsys.readouterr().out)
        yield


def _proved(task: str) -> check.Finding:
    return check.Finding(task, "title", check.PROVED, "expected", "observed")


def test_a_turn_shows_a_bar_while_pellier_answers(monkeypatch, capsys) -> None:
    bars = Bars(capsys)
    monkeypatch.setattr(lab_run, "waiting", bars)

    class Streaming:
        def stream(self, path: str, body: Any, token: str) -> Iterator[Any]:
            yield "message", {"type": "complete", "response": {"rail": lab_run.MANAGED}}

    assert lab_run.send_turn(Streaming(), "token", {}) == {"rail": lab_run.MANAGED}
    assert bars.shown == ["Waiting for Pellier's answer"]


def test_restart_restarts_the_backend_and_needs_no_lab(monkeypatch) -> None:
    restarted: List[Any] = []
    monkeypatch.setattr(lab_run, "restart_backend", lambda backend: restarted.append(backend))
    assert lab_run.main(["restart"]) == 0
    assert len(restarted) == 1


def test_the_observability_check_names_what_it_reads_before_reading(monkeypatch, capsys) -> None:
    import boto3

    bars = Bars(capsys)
    monkeypatch.setattr(observability_check, "waiting", bars)
    monkeypatch.setattr(observability_check, "check",
                        lambda *args, **kwargs: [_proved("O1"), _proved("O2"), _proved("O3")])
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: object())
    monkeypatch.setenv("DB_CLUSTER_ARN", "arn:aws:rds:us-east-1:123456789012:cluster:c1")
    monkeypatch.setattr(sys, "argv", ["observability_check.py"])
    assert observability_check.main() == 0
    assert bars.shown == ["Reading CloudWatch and Database Insights"]
    assert bars.printed_before[0].startswith("Observability outside AgentCore's trace")


def test_the_lab_3b_check_names_what_it_reads_before_reading(monkeypatch, capsys) -> None:
    bars = Bars(capsys)
    monkeypatch.setattr(lab3_check, "waiting", bars)
    monkeypatch.setattr(lab3_check, "collect", lambda: [_proved("3B")])
    assert lab3_check.main(["--task", "3B"]) == 0
    assert bars.shown == ["Reading tool_audit, AgentCore Memory, the Gateway and the row policies"]
    assert bars.printed_before[0].startswith("Lab 3B: Theo's managed turns")


def test_the_evidence_export_shows_a_bar_while_it_reads(monkeypatch, capsys) -> None:
    bars = Bars(capsys)
    monkeypatch.setattr(workshop_evidence, "waiting", bars)
    monkeypatch.setattr(workshop_evidence, "collect", lambda: [])
    monkeypatch.setattr(workshop_evidence, "render_report", lambda findings: "report")
    assert workshop_evidence.main([]) == 0
    assert bars.shown == ["Reading the evidence for the eight tasks"]
