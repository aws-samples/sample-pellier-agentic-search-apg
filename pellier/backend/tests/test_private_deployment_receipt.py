"""Deployment checkpoints must not overwrite another file through a temp symlink."""

import importlib.util
import json
import os
import stat
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


@pytest.fixture
def provisioner():
    path = Path(__file__).resolve().parents[3] / "scripts/provision_agentcore_end_to_end.py"
    spec = importlib.util.spec_from_file_location("private_receipt_provisioner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_precreated_temp_and_destination_symlinks_do_not_overwrite_targets(
    provisioner, tmp_path,
):
    sentinel = tmp_path / "unrelated.txt"
    sentinel.write_text("preserve this file")
    output = tmp_path / "receipt.json"
    old_temp = tmp_path / f".{output.name}.{os.getpid()}.tmp"
    old_temp.symlink_to(sentinel)
    output.symlink_to(sentinel)

    provisioner._write_result(output, {"status": "ready"})

    assert sentinel.read_text() == "preserve this file"
    assert old_temp.is_symlink()
    assert not output.is_symlink()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text()) == {"status": "ready"}
    assert list(tmp_path.glob(".receipt.json.*.tmp")) == [old_temp]


def test_concurrent_checkpoints_are_complete_private_documents(provisioner, tmp_path):
    output = tmp_path / "receipt.json"
    records = [{"worker": number, "payload": str(number) * 4096} for number in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda record: provisioner._write_result(output, record), records))

    assert json.loads(output.read_text()) in records
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".receipt.json.*.tmp"))


def test_failed_replacement_preserves_prior_receipt_and_removes_temp(
    provisioner, tmp_path, monkeypatch,
):
    output = tmp_path / "receipt.json"
    output.write_text('{"status":"previous"}')

    def refuse_replace(self, target):
        raise OSError("simulated filesystem failure")

    monkeypatch.setattr(Path, "replace", refuse_replace)
    with pytest.raises(OSError, match="filesystem failure"):
        provisioner._write_result(output, {"status": "new"})

    assert json.loads(output.read_text()) == {"status": "previous"}
    assert not list(tmp_path.glob(".receipt.json.*.tmp"))


def test_memory_progress_is_visible_before_the_child_finishes(provisioner, tmp_path, monkeypatch):
    signal = tmp_path / "progress-observed"
    lines = []

    class Progress:
        def write(self, line):
            lines.append(line)
            if "Memory extraction pending" in line:
                signal.touch()

        def flush(self):
            pass

    monkeypatch.setattr(provisioner.sys, "stderr", Progress())
    script = (
        "import sys,time,json; from pathlib import Path; "
        "print('Memory extraction pending: episodic',file=sys.stderr,flush=True); "
        f"signal=Path({str(signal)!r}); deadline=time.monotonic()+5\n"
        "while not signal.exists():\n"
        " assert time.monotonic()<deadline, 'progress was buffered'\n"
        " time.sleep(.01)\n"
        "print(json.dumps({'status':'ready','private_result':'x'*256000}))"
    )
    result = provisioner._run([sys.executable, "-c", script], cwd=tmp_path, stream_stderr=True)
    assert json.loads(result.stdout)["status"] == "ready"
    assert result.stderr == "Memory extraction pending: episodic\n"
    assert "private_result" not in "".join(lines)


def test_failed_provisioning_is_distinct_from_an_active_checkpoint(provisioner, tmp_path, monkeypatch):
    output = tmp_path / "receipt.json"
    snapshots = []
    original_write = provisioner._write_result

    def checkpoint(path, payload):
        snapshots.append(json.loads(json.dumps(payload)))
        original_write(path, payload)

    class Sts:
        def get_caller_identity(self):
            return {"Account": "123456789012", "Arn": "arn:aws:iam::123456789012:role/fixture"}

    def failed_schema():
        raise RuntimeError("fixture schema validation failed")

    monkeypatch.setattr(provisioner, "_write_result", checkpoint)
    monkeypatch.setattr(provisioner, "_load_env_fallback", lambda *_: None)
    monkeypatch.setattr(provisioner, "_require_env", lambda name: "us-east-1" if name == "AWS_REGION" else "fixture")
    monkeypatch.setattr(provisioner, "_verify_local_schema", failed_schema)
    monkeypatch.setattr(provisioner.boto3, "client", lambda *_args, **_kwargs: Sts())
    monkeypatch.setenv("AGENTCORE_RUNTIME_LOG_RETENTION_DAYS", "30")
    monkeypatch.setattr(sys, "argv", ["provisioner", "--repo-path", str(tmp_path), "--output-json", str(output)])
    assert provisioner.main() == 1
    assert snapshots[0]["status"] == "provisioning"
    assert snapshots[-1]["status"] == "failed"
    assert json.loads(output.read_text())["error"] == "fixture schema validation failed"
