"""The manual AgentCore rehearsal workflow wires what the provisioner needs and uploads only
an allowlisted summary, because artifacts of a public repository are downloadable by any
signed-in user and the managed receipt names accounts, ARNs and the Gateway URL."""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
summary = importlib.import_module("rehearsal_summary")

WORKFLOW = REPO / ".github" / "workflows" / "agentcore-rehearsal.yml"
PROVISIONER = REPO / "scripts" / "provision_agentcore_end_to_end.py"
SECRET_REF = re.compile(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}")


def _job() -> Dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["rehearsal"]


def _steps() -> List[Dict[str, Any]]:
    return _job()["steps"]


def _required_by_provisioner() -> List[str]:
    text = PROVISIONER.read_text(encoding="utf-8")
    return sorted(set(re.findall(r'_require_env\(\s*"([A-Z0-9_]+)"', text)))


def test_every_variable_the_provisioner_requires_is_wired_from_a_secret() -> None:
    env = _job()["env"]
    for name in _required_by_provisioner():
        if name in ("AWS_REGION",):
            continue
        assert name in env, f"{name} is required by the provisioner but not wired"
        assert SECRET_REF.fullmatch(str(env[name])), f"{name} must come from a secret reference"


def test_both_restricted_tool_logins_come_from_the_protected_environment() -> None:
    env = _job()["env"]
    assert _job()["environment"] == "agentcore-rehearsal"
    for name in ("STORE_TOOLS_SECRET_ARN", "OPERATOR_TOOLS_SECRET_ARN"):
        assert SECRET_REF.fullmatch(str(env[name]))
        assert "arn:aws" not in str(env[name])


def test_the_preflight_fails_fast_when_either_restricted_secret_is_unset() -> None:
    (preflight,) = [s for s in _steps() if "Require dedicated" in s.get("name", "")]
    script = preflight["run"]
    for name in ("STORE_TOOLS_SECRET_ARN", "OPERATOR_TOOLS_SECRET_ARN"):
        assert re.search(rf"^\s*{name} \\$", script, re.M), f"{name} missing from preflight"
    assert "exit 1" in script
    names = [s["name"] for s in _steps()]
    assert names.index(preflight["name"]) < names.index("Provision and prove the managed path")


def test_the_only_uploaded_file_is_the_allowlisted_summary_never_the_receipt() -> None:
    env = _job()["env"]
    uploads = [s for s in _steps() if str(s.get("uses", "")).startswith("actions/upload-artifact")]
    assert len(uploads) == 1
    path = uploads[0]["with"]["path"]
    assert path == env["AGENTCORE_REHEARSAL_SUMMARY_JSON"]
    assert path != env["AGENTCORE_MANAGED_OUTPUT_JSON"]
    assert "managed" not in path
    assert "receipt" not in uploads[0]["with"]["name"]


def test_the_summary_is_written_from_the_receipt_even_after_a_failure() -> None:
    (step,) = [s for s in _steps() if "rehearsal_summary.py" in s.get("run", "")]
    assert step["if"] == "always()"
    assert "$AGENTCORE_MANAGED_OUTPUT_JSON" in step["run"]
    upload = [s for s in _steps() if "upload-artifact" in str(s.get("uses", ""))][0]
    assert _steps().index(step) < _steps().index(upload)


RECEIPT = {
    "status": "failed",
    "error": "AccessDenied on arn:aws:iam::123456789012:role/x at https://gw.example.com/mcp",
    "region": "us-east-1",
    "gateway": {"url": "https://gw-abc.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
                "arn": "arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/g-1"},
    "runtime": {"arn": "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/r-1"},
    "lambdas": {"store": "arn:aws:lambda:us-east-1:123456789012:function:f"},
    "verification": {
        "gateway_tools_discovered": True,
        "targets_attached": False,
        "gateway_tool_count": 9,
        "gateway_tool_names": ["get_tickets"],
        "gateway_control_plane": {
            "gateway_arn": "arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/g-1"},
        "runtime_invoke_smoke": {"endpoint": "https://rt.example.com"},
        "arn:aws:iam::123456789012:role/odd_key": True,
        "Account 123456789012": True,
    },
}
SHA = "6d2d2265" + "a" * 32


def test_the_job_log_masks_the_account_id_before_anything_prints_an_arn() -> None:
    """A public repository's job log is public; ARNs the provisioner derives carry the account."""
    steps = _steps()
    names = [step.get("name") for step in steps]
    configure = next(step for step in steps if "configure-aws-credentials" in step.get("uses", ""))
    assert configure.get("with", {}).get("mask-aws-account-id") is True, configure
    assert names.index(configure["name"]) < names.index("Provision and prove the managed path")


def test_the_summary_keeps_only_the_revision_status_and_check_outcomes() -> None:
    out = summary.summarize(RECEIPT, SHA)
    assert out == {
        "source_revision": SHA,
        "status": "failed",
        "checks": {"gateway_tools_discovered": True, "targets_attached": False},
        "failed_checks": ["targets_attached"],
    }


def test_no_account_id_arn_url_or_endpoint_survives_in_the_summary() -> None:
    text = json.dumps(summary.summarize(RECEIPT, SHA))
    for leaked in ("arn:", "123456789012", "http", "amazonaws", ".com", "AccessDenied",
                   "us-east-1"):
        assert leaked not in text


def test_a_missing_or_malformed_receipt_summarizes_as_no_receipt() -> None:
    for receipt in (None, {}, {"status": "arn:aws:iam::123456789012:x", "verification": "nope"}):
        out = summary.summarize(receipt, SHA)
        assert out["status"] == "no_receipt" and out["checks"] == {}


def test_a_revision_that_is_not_a_commit_sha_is_refused() -> None:
    for bad in ("", "main", "arn:aws:iam::123456789012:role/x", "6d2d226 5"):
        try:
            summary.summarize(RECEIPT, bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} must be refused")


def test_the_command_writes_the_summary_file_and_tolerates_a_missing_receipt(
        tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(RECEIPT), encoding="utf-8")
    out = tmp_path / "summary.json"
    assert summary.main(["--receipt", str(receipt), "--revision", SHA, "--output", str(out)]) == 0
    assert json.loads(out.read_text())["status"] == "failed"
    gone = tmp_path / "gone.json"
    assert summary.main(["--receipt", str(gone), "--revision", SHA, "--output", str(out)]) == 0
    assert json.loads(out.read_text())["status"] == "no_receipt"
