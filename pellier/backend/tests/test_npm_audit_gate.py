"""The npm audit gate CI runs on the AgentCore CDK lockfile."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from typing import Any

import pytest

GATE = Path(__file__).resolve().parents[3] / "scripts" / "deploy" / "npm_audit_gate.py"
HIGH = "GHSA-3jxr-9vmj-r5cp"
MODERATE = "GHSA-g3hv-75wg-m249"


def _gate() -> Any:
    spec = importlib.util.spec_from_file_location("npm_audit_gate", GATE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _advisory(ghsa: str, severity: str) -> dict[str, str]:
    return {"url": f"https://github.com/advisories/{ghsa}", "severity": severity}


def _run(monkeypatch, report: dict[str, Any], *ignores: str) -> int:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(report)))
    return _gate().main([arg for ghsa in ignores for arg in ("--ignore", ghsa)])


REPORT = {"vulnerabilities": {
    "brace-expansion": {"via": [_advisory(HIGH, "high")]},
    "minimatch": {"via": [_advisory(MODERATE, "moderate")]},
    "aws-cdk-lib": {"via": ["minimatch"]},
}}


def test_an_unlisted_high_advisory_fails(monkeypatch, capsys) -> None:
    assert _run(monkeypatch, REPORT) == 1
    assert HIGH in capsys.readouterr().out


def test_a_listed_high_advisory_and_a_moderate_one_pass(monkeypatch) -> None:
    assert _run(monkeypatch, REPORT, HIGH) == 0


def test_an_exception_the_audit_no_longer_reports_fails(monkeypatch, capsys) -> None:
    assert _run(monkeypatch, {"vulnerabilities": {}}, HIGH) == 1
    assert "drop it" in capsys.readouterr().out


@pytest.mark.parametrize("report", [{"error": {"summary": "registry unreachable"}}, {}])
def test_an_audit_that_did_not_run_fails(monkeypatch, report: dict[str, Any]) -> None:
    assert _run(monkeypatch, report) == 2
