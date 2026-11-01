"""Reviewed defects in the provisioning and lab scripts, each held by a behavior check."""

from __future__ import annotations

import importlib
import io
import json
import os
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "deploy"))

repair = importlib.import_module("repair_workshop_files")
exercises = importlib.import_module("reset_participant_exercises")
check_model_access = importlib.import_module("check_model_access")
provisioner = importlib.import_module("provision_agentcore_end_to_end")

BOOTSTRAP = (SCRIPTS / "bootstrap-labs.sh").read_text(encoding="utf-8")
HEALTH_GATE = SCRIPTS / "health-gate.sh"


# --- .env rewrites are atomic and keep the mode and export lines ------------------------


def test_env_upsert_keeps_mode_export_lines_and_leaves_no_temp_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("DB_PASSWORD=secret\nexport MODEL=old\n", encoding="utf-8")
    env.chmod(0o640)

    check_model_access._upsert_env(str(env), "MODEL", "new")
    check_model_access._upsert_env(str(env), "READY", "true")

    assert env.read_text(encoding="utf-8") == "DB_PASSWORD=secret\nexport MODEL=new\nREADY=true\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o640
    assert [p.name for p in tmp_path.iterdir()] == [".env"]


def test_env_upsert_failure_leaves_the_original_whole(tmp_path: Path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text("DB_PASSWORD=secret\n", encoding="utf-8")

    def broken(*_a, **_k):
        raise OSError("simulated kill before the replace")

    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(OSError):
        check_model_access._upsert_env(str(env), "MODEL", "new")

    assert env.read_text(encoding="utf-8") == "DB_PASSWORD=secret\n"
    assert [p.name for p in tmp_path.iterdir()] == [".env"]


def test_env_upsert_creates_a_private_file_when_none_exists(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    check_model_access._upsert_env(str(env), "A", "1")
    assert env.read_text(encoding="utf-8") == "A=1\n"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


# --- the participant receipt survives a reboot ------------------------------------------


def test_participant_receipt_is_copied_out_of_tmp(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / "state"
    monkeypatch.setenv("PELLIER_STATE_DIR", str(state))
    receipt = tmp_path / "participant.json"
    receipt.write_text('{"mode": "participant"}', encoding="utf-8")

    provisioner._save_participant_receipt(receipt)
    provisioner._save_participant_receipt(state / "participant-receipt.json")

    assert json.loads((state / "participant-receipt.json").read_text()) == {"mode": "participant"}


def test_saving_the_receipt_never_fails_a_finished_deploy(tmp_path: Path, monkeypatch, capsys) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    monkeypatch.setenv("PELLIER_STATE_DIR", str(blocker / "state"))
    receipt = tmp_path / "participant.json"
    receipt.write_text("{}", encoding="utf-8")

    provisioner._save_participant_receipt(receipt)

    assert "Could not save the participant receipt" in capsys.readouterr().err


@pytest.mark.parametrize("script", ["health-gate.sh", "lab3-start.sh", "lib/agentcore-reset.sh"])
def test_receipt_readers_fall_back_to_the_saved_copy(script: str) -> None:
    text = (SCRIPTS / script).read_text(encoding="utf-8")
    assert "/var/lib/pellier/participant-receipt.json" in text
    if script != "lib/agentcore-reset.sh":
        assert "/var/lib/pellier/managed-receipt.json" in text


# --- bootstrap ---------------------------------------------------------------------------


def test_the_log_directory_is_recreated_on_every_boot() -> None:
    assert "/etc/tmpfiles.d/pellier.conf" in BOOTSTRAP
    assert "d /tmp/pellier 0755 %s %s -" in BOOTSTRAP
    assert "systemd-tmpfiles --create /etc/tmpfiles.d/pellier.conf" in BOOTSTRAP
    assert BOOTSTRAP.index("systemd-tmpfiles --create") < BOOTSTRAP.index("systemctl start pellier")


def test_the_uv_installer_pipe_fails_when_curl_fails() -> None:
    line = next(row for row in BOOTSTRAP.splitlines() if "install.sh | sh" in row)
    assert 'bash -c "set -o pipefail; curl' in line


def test_cognito_secrets_stay_off_command_lines() -> None:
    gate = HEALTH_GATE.read_text(encoding="utf-8")
    assert "--password" not in BOOTSTRAP.split("admin-set-user-password", 1)[1][:400]
    assert "--auth-parameters" not in gate
    assert "COGNITO_CLIENT_SECRET\" 2>" not in gate
    assert gate.count("--cli-input-json") == 2


def test_the_staff_block_is_written_once_and_reuses_the_stored_password() -> None:
    writer = (SCRIPTS / "write-test-credentials.sh").read_text(encoding="utf-8")
    assert "umask 077" in writer
    assert writer.index("umask 077") < writer.index('} > "$OUT_FILE"')
    assert "continue" in writer.split("PELLIER_OPERATOR_USERNAME", 1)[1][:200]
    assert "get-secret-value" in BOOTSTRAP.split("OPERATOR_PASSWORD=", 1)[1][:300]


def test_the_credentials_writer_skips_the_staff_user(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    secret = {"users": [{"username": "marco", "password": "pw-marco"},
                        {"username": "Nadia", "password": "old-nadia"}]}
    aws = fake_bin / "aws"
    aws.write_text(f"#!/bin/bash\nprintf '%s' '{json.dumps(secret)}'\n", encoding="utf-8")
    aws.chmod(0o755)
    out = tmp_path / "creds.txt"
    result = subprocess.run(
        ["bash", str(SCRIPTS / "write-test-credentials.sh")], capture_output=True, text=True,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "OUT_FILE": str(out),
             "COGNITO_TEST_CREDENTIALS_SECRET_ARN": "synthetic", "CODE_EDITOR_USER": "nobody-x"},
        check=False)
    assert result.returncode == 0, result.stderr
    body = out.read_text(encoding="utf-8")
    assert "pw-marco" in body
    assert "old-nadia" not in body and "Nadia" not in body.split("Username:", 1)[1]
    assert stat.S_IMODE(out.stat().st_mode) == 0o600


# --- health gate: an absent provision state is not a pass -------------------------------


def _gate_state_lines(tmp_path: Path, phase: str | None) -> str:
    """Run the provision-state block of the gate, alone, with no state file."""
    text = HEALTH_GATE.read_text(encoding="utf-8")
    start = text.index("PROVISION_STATE_FILE=")
    end = text.index("# 1. Backend health")
    program = (
        "ok=true; managed_required=true\n"
        'pass() { echo "PASS $1"; }; fail() { echo "FAIL $1"; }\n'
        + text[start:end] + '\necho "ok=$ok"\n'
    )
    env = {**os.environ, "PELLIER_PROVISION_STATE_FILE": str(tmp_path / "missing")}
    env.pop("PELLIER_PROVISION_PHASE", None)
    if phase:
        env["PELLIER_PROVISION_PHASE"] = phase
    return subprocess.run(["bash", "-c", program], env=env, capture_output=True, text=True,
                          check=False).stdout


def test_gate_fails_when_the_provision_state_is_absent(tmp_path: Path) -> None:
    out = _gate_state_lines(tmp_path, None)
    assert "FAIL Provision state absent" in out and "ok=false" in out


def test_gate_tolerates_an_absent_state_during_bootstrap_proving(tmp_path: Path) -> None:
    out = _gate_state_lines(tmp_path, "bootstrap")
    assert "FAIL" not in out and "ok=true" in out


# --- repair and reset keep what the participant wrote -----------------------------------


def _tar(path: Path, sha: str, files: dict[str, str]) -> None:
    top = f"sample-pellier-agentic-search-apg-{sha}"
    with tarfile.open(path, "w:gz", format=tarfile.PAX_FORMAT, pax_headers={"comment": sha}) as t:
        folder = tarfile.TarInfo(top)
        folder.type = tarfile.DIRTYPE
        folder.mode = 0o755
        t.addfile(folder)
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size = len(data)
            info.mode = 0o644
            t.addfile(info, io.BytesIO(data))


def test_repair_keeps_the_participants_lab_edit_before_restoring(tmp_path: Path) -> None:
    sha = "0123456789abcdef0123456789abcdef01234567"
    repo = tmp_path / "repo"
    (repo / "workshop").mkdir(parents=True)
    (repo / ".workshop-ref.json").write_text(json.dumps({"resolved_sha": sha}))
    (repo / "workshop" / "participant-files.json").write_text(json.dumps([
        {"alias": "labs/01-retrieve/1B.py", "source": "pellier/search_plan.py", "solution": "s"}]))
    (repo / "pellier").mkdir()
    (repo / "pellier" / "search_plan.py").write_text("my attempt\n")
    (repo / "pellier" / "other.py").write_text("not a lab file, edited\n")
    tarball = tmp_path / "pin.tar.gz"
    _tar(tarball, sha, {"pellier/search_plan.py": "starter\n", "pellier/other.py": "pin\n",
                        "workshop/participant-files.json":
                        (repo / "workshop" / "participant-files.json").read_text()})

    report = repair.repair(repo, fetch=lambda _s, dest: dest.write_bytes(tarball.read_bytes()))

    assert (repo / "pellier" / "search_plan.py").read_text() == "starter\n"
    assert (repo / "labs/01-retrieve/1B.py.bak").read_text() == "my attempt\n"
    assert len(report.kept) == 1 and "1B.py.bak" in report.kept[0]
    assert not list(repo.rglob("other.py.bak*"))

    (repo / "pellier" / "search_plan.py").write_text("second attempt\n")
    repair.repair(repo, fetch=lambda _s, dest: dest.write_bytes(tarball.read_bytes()))
    assert (repo / "labs/01-retrieve/1B.py.bak.2").read_text() == "second attempt\n"
    assert (repo / "labs/01-retrieve/1B.py.bak").read_text() == "my attempt\n"


def test_a_lab_reset_keeps_every_edited_task_file_not_only_optional_ones(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    markers, files = exercises.exercises_for(1)
    for exercise in (*markers, *files):
        for relative in (exercise.starter, exercise.destination):
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((REPO / relative).read_bytes())
    required = next(e for e in files if not e.optional) if any(
        not e.optional for e in files) else None
    marker = markers[0]
    path = repo / marker.destination
    text = path.read_text(encoding="utf-8")
    _s, body_start, _e, _l = exercises._marker_bounds(text, marker.marker)
    path.write_text(text[:body_start] + "# participant edit\n" + text[body_start:],
                    encoding="utf-8")
    edited = path.read_bytes()
    if required is not None:
        (repo / required.destination).write_text("-- my required attempt\n", encoding="utf-8")

    exercises._restore(repo, 1, keep_edits=True)

    assert path.with_name(path.name + ".bak").read_bytes() == edited
    if required is not None:
        backup = (repo / required.destination)
        assert backup.with_name(backup.name + ".bak").read_text() == "-- my required attempt\n"
