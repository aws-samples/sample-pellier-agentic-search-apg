"""Exercise capture trust with real temporary files and inert AWS clients."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_gateway_vocabulary_migration import (
    MIG, FakeCfn, FakeControl, FakeLambda, FakeSts, ownership,
)


@pytest.fixture
def case(tmp_path, monkeypatch):
    def unexpected_transport(*_args, **_kwargs):
        pytest.fail("No real AWS, database or external CLI calls are allowed.")

    monkeypatch.setattr("boto3.client", unexpected_transport)
    monkeypatch.setattr("psycopg.connect", unexpected_transport)
    monkeypatch.setattr("subprocess.run", unexpected_transport)
    monkeypatch.setattr(MIG.time, "sleep", lambda *_: None)
    monkeypatch.setattr(MIG, "_load_env", lambda: None)
    monkeypatch.setenv("AWS_REGION", ownership.EXPECTED_REGION)
    monkeypatch.setenv("DB_HOST", ownership.EXPECTED_DB_CLUSTER + ".example")
    control, sts = FakeControl(), FakeSts()
    factories = []

    def clients():
        factories.append(True)
        return control, sts, FakeLambda(), FakeCfn()

    monkeypatch.setattr(MIG, "_clients", clients)
    return SimpleNamespace(
        root=tmp_path / "captures", control=control, sts=sts, factories=factories,
    )


def run_main(case, monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["migration", "--out", str(case.root), *args])
    return MIG.main()


def save(case, *, live=None, approved=True):
    current = MIG.read_live(case.control)
    canonical = MIG.validate_canonical()
    return MIG._capture_run(
        case.root, MIG.PreflightResult(ok=approved),
        MIG.build_plan(current, canonical),
        current if live is None else live, canonical,
    )


def assert_no_updates(case):
    assert case.control.target_updates == []
    assert case.control.policy_updates == []
    assert case.control.gateway_updates == []


def test_plan_writes_only_private_complete_captures_and_no_aws_updates(case, monkeypatch):
    previous_umask = os.umask(0)
    try:
        assert run_main(case, monkeypatch) == 0
    finally:
        os.umask(previous_umask)
    runs = list(case.root.iterdir())
    assert len(runs) == 1
    run = runs[0]
    assert len(run.name.split("-")[-1]) == 32
    for directory in (case.root, run, run / "rollback"):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    files = sorted(path for path in run.rglob("*") if path.is_file())
    assert len(files) == 6
    for path in files:
        assert not path.is_symlink()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert MIG._load_capture(run / "rollback") == MIG.read_live(case.control)
    assert_no_updates(case)


@pytest.mark.parametrize("kind", ["shared", "public", "symlink", "parent-symlink", "file"])
def test_plan_rejects_untrusted_output_before_constructing_clients(case, monkeypatch, kind):
    victim = case.root.parent / "victim"
    victim.write_text("do not overwrite")
    if kind in {"shared", "public"}:
        case.root.mkdir(mode=0o700)
        case.root.chmod(0o777 if kind == "shared" else 0o755)
        stale = case.root / "20300101-000000"
        stale.mkdir()
        (stale / "preflight.json").symlink_to(victim)
    elif kind == "symlink":
        real = case.root.parent / "real"
        real.mkdir(mode=0o700)
        case.root.symlink_to(real)
    elif kind == "parent-symlink":
        real = case.root.parent / "real"
        real.mkdir(mode=0o700)
        link = case.root.parent / "linked"
        link.symlink_to(real)
        case.root = link / "captures"
    else:
        case.root.write_text("keep this file")
    with pytest.raises(MIG.CaptureError):
        run_main(case, monkeypatch)
    assert case.factories == []
    assert victim.read_text() == "do not overwrite"
    assert_no_updates(case)


def test_same_timestamp_runs_are_distinct_and_never_reuse_a_planted_directory(case, monkeypatch):
    monkeypatch.setattr(MIG.time, "strftime", lambda *_: "20300101-000000")
    case.root.mkdir(mode=0o700)
    planted = case.root / "20300101-000000"
    planted.mkdir(mode=0o700)
    victim = case.root.parent / "victim"
    victim.write_text("unchanged")
    (planted / "preflight.json").symlink_to(victim)
    first, second = save(case), save(case)
    assert first != second
    assert first != planted and second != planted
    assert victim.read_text() == "unchanged"
    assert (planted / "preflight.json").is_symlink()
    assert MIG._load_capture(first / "rollback") == MIG._load_capture(second / "rollback")


@pytest.mark.parametrize("kind", ["file", "symlink", "dangling", "fifo"])
def test_exclusive_capture_writer_preserves_existing_paths(case, kind):
    case.root.mkdir(mode=0o700)
    path = case.root / "live.json"
    victim = case.root.parent / "victim"
    if kind == "file":
        path.write_text("original")
    elif kind == "fifo":
        os.mkfifo(path, 0o600)
    else:
        if kind == "symlink":
            victim.write_text("original")
        path.symlink_to(victim)
    with MIG._private_directory(case.root) as directory_fd:
        with pytest.raises(MIG.CaptureError):
            MIG._write_capture_json(directory_fd, "live.json", {"sensitive": "synthetic"})
    if kind == "file":
        assert path.read_text() == "original"
    elif kind == "symlink":
        assert victim.read_text() == "original"
    elif kind == "dangling":
        assert not victim.exists()
    assert_no_updates(case)


@pytest.mark.parametrize("filename", [
    "preflight.json", "plan.json", "phase-proof.json",
    "rollback/live.json", "rollback/canonical.json",
])
def test_modified_capture_component_stops_rollback_before_any_update(case, filename):
    run = save(case)
    path = run / filename
    path.write_text('{"targets": [{"targetId": "attacker-target"}], "policies": []}')
    with pytest.raises(MIG.CaptureError, match="integrity"):
        MIG.rollback(case.control, run / "rollback", sts=case.sts)
    assert path.exists()
    assert_no_updates(case)


@pytest.mark.parametrize("kind", [
    "symlink", "hardlink", "fifo", "public-file", "public-root", "public-run",
    "public-rollback", "rollback-symlink", "missing-manifest", "partial-manifest",
])
def test_unsafe_or_uncertain_capture_is_refused_before_clients(case, monkeypatch, kind):
    run = save(case)
    rollback = run / "rollback"
    path = rollback / "live.json"
    if kind in {"symlink", "hardlink"}:
        original = rollback / "original.json"
        path.rename(original)
        if kind == "symlink":
            path.symlink_to(original)
        else:
            os.link(original, path)
    elif kind == "fifo":
        path.unlink()
        os.mkfifo(path, 0o600)
    elif kind == "public-file":
        path.chmod(0o644)
    elif kind.startswith("public-"):
        {"public-root": case.root, "public-run": run, "public-rollback": rollback}[kind].chmod(0o777)
    elif kind == "rollback-symlink":
        original = run / "original-rollback"
        rollback.rename(original)
        rollback.symlink_to(original)
    elif kind == "missing-manifest":
        (rollback / "manifest.json").unlink()
    else:
        (rollback / "manifest.json").write_text('{"version":')
    with pytest.raises(MIG.CaptureError):
        run_main(case, monkeypatch, "--rollback", str(rollback))
    assert case.factories == []
    assert_no_updates(case)


def test_capture_owned_by_another_os_user_is_refused(case, monkeypatch):
    run = save(case)
    owner = os.geteuid()
    monkeypatch.setattr(MIG.os, "geteuid", lambda: owner + 1)
    with pytest.raises(MIG.CaptureError, match="owned"):
        MIG.rollback(case.control, run / "rollback", sts=case.sts)
    assert_no_updates(case)


@pytest.mark.parametrize("field", ["account", "region", "gatewayId", "policyEngineId"])
def test_capture_manifest_must_match_configured_deployment(case, field):
    run = save(case)
    path = run / "rollback/manifest.json"
    manifest = json.loads(path.read_text())
    manifest["scope"][field] = "foreign-scope"
    path.write_text(json.dumps(manifest))
    with pytest.raises(MIG.CaptureError, match="scope"):
        MIG.rollback(case.control, run / "rollback", sts=case.sts)
    assert_no_updates(case)


@pytest.mark.parametrize("kind", ["target-id", "policy-id", "target-name", "missing-policy", "missing-mode"])
def test_even_a_rehashed_capture_cannot_choose_unverified_resource_identities(case, kind):
    run = save(case)
    path = run / "rollback/live.json"
    live = json.loads(path.read_text())
    if kind == "target-id":
        live["targets"][0]["targetId"] = "attacker-target"
    elif kind == "policy-id":
        live["policies"][0]["policyId"] = "attacker-policy"
    elif kind == "target-name":
        live["targets"][0]["name"] = "unexpected-target"
    elif kind == "missing-policy":
        live["policies"].pop()
    else:
        live["policies"][-1].pop("enforcementMode")
    data = json.dumps(live).encode()
    path.write_bytes(data)
    manifest_path = run / "rollback/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["live.json"] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(MIG.CaptureError):
        MIG.rollback(case.control, run / "rollback", sts=case.sts)
    assert_no_updates(case)


@pytest.mark.parametrize("kind", ["account", "region", "recreated-target", "recreated-policy"])
def test_rollback_checks_current_ownership_before_the_first_update(case, kind):
    run = save(case)
    if kind == "account":
        case.sts.account = "000000000000"
    elif kind == "region":
        case.control.meta.region_name = "eu-west-1"
    elif kind == "recreated-target":
        next(iter(case.control.targets.values()))["targetId"] = "replacement-target"
    else:
        next(iter(case.control.policies.values()))["name"] = "replacement-policy"
    with pytest.raises(MIG.CaptureError):
        MIG.rollback(case.control, run / "rollback", sts=case.sts)
    assert_no_updates(case)


def test_failed_preflight_capture_cannot_authorize_rollback(case):
    run = save(case, approved=False)
    with pytest.raises(MIG.CaptureError, match="unapproved"):
        MIG.rollback(case.control, run / "rollback", sts=case.sts)
    assert_no_updates(case)


def test_partial_capture_write_prevents_apply_and_retains_evidence(case, monkeypatch):
    original = MIG._write_capture_json

    def fail(directory_fd, name, value):
        if name == "canonical.json":
            raise MIG.CaptureError("synthetic disk failure")
        return original(directory_fd, name, value)

    monkeypatch.setattr(MIG, "_write_capture_json", fail)
    with pytest.raises(MIG.CaptureError, match="disk failure"):
        run_main(case, monkeypatch, "--apply", "--phase", "default-deny-quiesce")
    run = next(case.root.iterdir())
    assert (run / "rollback/live.json").exists()
    assert not (run / "rollback/manifest.json").exists()
    with pytest.raises(MIG.CaptureError):
        MIG.rollback(case.control, run / "rollback", sts=case.sts)
    assert_no_updates(case)


def test_capture_changed_after_planning_stops_apply(case, monkeypatch):
    def tamper(*_args):
        run = next(case.root.iterdir())
        (run / "rollback/live.json").write_text("{}")

    monkeypatch.setattr(MIG, "print_report", tamper)
    with pytest.raises(MIG.CaptureError, match="integrity"):
        run_main(case, monkeypatch, "--apply", "--phase", "default-deny-quiesce")
    assert_no_updates(case)


def test_normal_apply_and_rollback_keep_complete_evidence_and_policy_modes(case, monkeypatch):
    before = copy.deepcopy(MIG.read_live(case.control))
    original_update = case.control.update_policy

    def require_capture_before_update(**kwargs):
        run = next(case.root.iterdir())
        assert MIG._load_capture(run / "rollback") == before
        return original_update(**kwargs)

    monkeypatch.setattr(case.control, "update_policy", require_capture_before_update)
    assert run_main(case, monkeypatch, "--apply", "--phase", "default-deny-quiesce") == 0
    assert len(case.control.policy_updates) == 1
    assert case.control.target_updates == []
    run = next(case.root.iterdir())
    assert run_main(case, monkeypatch, "--rollback", str(run / "rollback")) == 0
    assert len(case.control.target_updates) == len(before["targets"])
    assert len(case.control.policy_updates) == 1 + len(before["policies"])
    restored = MIG.read_live(case.control)
    for wanted in before["policies"]:
        actual = next(p for p in restored["policies"] if p["policyId"] == wanted["policyId"])
        assert actual["definition"] == wanted["definition"]
        assert actual["enforcementMode"] == wanted["enforcementMode"]
    assert all(
        update["enforcementMode"] == "ACTIVE"
        and update["validationMode"] == "FAIL_ON_ANY_FINDINGS"
        for update in case.control.policy_updates[-len(before["policies"]):]
    )
    assert MIG._load_capture(run / "rollback") == before


def test_existing_unverified_historical_capture_is_not_silently_ignored(case):
    case.root.mkdir(mode=0o700)
    legacy = case.root / "old-run"
    legacy.mkdir(mode=0o700)
    (legacy / "rollback").mkdir(mode=0o700)
    (legacy / "rollback/live.json").write_text(json.dumps(MIG.read_live(case.control)))
    with pytest.raises(MIG.CaptureError):
        MIG.assert_broad_baseline_matches_capture(legacy)
    assert_no_updates(case)
