"""Deployment checkpoints must not overwrite another file through a temp symlink."""

import importlib.util
import json
import os
import stat
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
