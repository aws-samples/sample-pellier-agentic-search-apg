"""Exercise Cognito ownership boundaries with fake responses and real temp files.

No AWS clients are created. The doubles intentionally lack ``exceptions`` so
an unrelated failure cannot pass through a fallback-to-Exception handler.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

from tests.test_e2e_bootstrap_dry_run import _load_module


PASSWORD = 'Synthet1c!Never"Log\\ThisPassword'
USERNAME = "created-cognito-username"
SUB = "d8688ca0-c332-4155-82d8-8337e7f9479b"


def service_error(code: str) -> ClientError:
    # Error details can echo request data; the helpers must never print them.
    return ClientError({"Error": {"Code": code, "Message": PASSWORD}}, "SyntheticOperation")


class CognitoDouble:
    def __init__(self):
        self.calls = []
        self.create_error = self.password_error = self.get_error = self.delete_error = None
        self.on_create = self.on_password = None
        self.create_response = {
            "User": {
                "Username": USERNAME,
                "Attributes": [
                    {"Name": "sub", "Value": SUB},
                    # Receipts must not copy arbitrary response attributes.
                    {"Name": "custom:sensitive", "Value": PASSWORD},
                ],
            },
        }
        self.get_response = {
            "Username": USERNAME,
            "UserAttributes": [{"Name": "sub", "Value": SUB}],
        }

    def admin_create_user(self, **params):
        self.calls.append(("create", params))
        if self.on_create:
            self.on_create()
        if self.create_error:
            raise self.create_error
        return self.create_response

    def admin_set_user_password(self, **params):
        self.calls.append(("password", params))
        if self.on_password:
            self.on_password(params)
        if self.password_error:
            raise self.password_error
        return {}

    def admin_get_user(self, **params):
        self.calls.append(("get", params))
        if self.get_error:
            raise self.get_error
        return self.get_response

    def admin_delete_user(self, **params):
        self.calls.append(("delete", params))
        if self.delete_error:
            raise self.delete_error
        return {}


@pytest.fixture
def case(tmp_path, monkeypatch):
    # Even an accidental non-injected code path must fail without contacting AWS.
    import sys

    monkeypatch.setitem(sys.modules, "boto3", None)
    bootstrap = _load_module("bootstrap_cognito_dev_pool")
    teardown = _load_module("teardown_cognito_dev_pool")
    cfg = bootstrap.BootstrapConfig(
        pool_id="us-east-1_opaque123", client_id="example-client",
        email="disposable@example.com", password=PASSWORD, region="us-east-1",
    )
    return SimpleNamespace(
        bootstrap=bootstrap, teardown=teardown, cfg=cfg,
        cleanup_cfg=teardown.TeardownConfig(cfg.pool_id, cfg.email, cfg.region),
        receipt=tmp_path / "identity.json", client=CognitoDouble(),
    )


def create(case):
    return case.bootstrap.bootstrap(
        case.cfg, dry_run=False, receipt_path=str(case.receipt), client=case.client,
    )


def cleanup(case):
    return case.teardown.teardown(
        case.cleanup_cfg, dry_run=False, receipt_path=str(case.receipt), client=case.client,
    )


def receipt_payload(case):
    return {
        "version": 1, "kind": "pellier-e2e-cognito-user",
        "pool_id": case.cfg.pool_id, "region": case.cfg.region,
        "requested_username": case.cfg.email, "username": USERNAME, "sub": SUB,
    }


def write_receipt(case, payload=None):
    case.receipt.write_text(json.dumps(receipt_payload(case) if payload is None else payload))
    case.receipt.chmod(0o600)


def assert_private(path):
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def assert_secret_absent(text):
    assert PASSWORD not in text
    assert json.dumps(PASSWORD)[1:-1] not in text


def test_receipt_is_complete_private_and_published_before_password_setup(case, capsys):
    def during_create():
        assert not case.receipt.exists()
        assert_private(Path(str(case.receipt) + ".pending"))

    def before_password(params):
        assert json.loads(case.receipt.read_text()) == receipt_payload(case)
        assert_private(case.receipt)
        assert params == {
            "UserPoolId": case.cfg.pool_id, "Username": USERNAME,
            "Password": PASSWORD, "Permanent": True,
        }
        assert list(case.receipt.parent.iterdir()) == [case.receipt]

    case.client.on_create, case.client.on_password = during_create, before_password
    old_umask = os.umask(0)
    try:
        assert create(case) == 0
    finally:
        os.umask(old_umask)
    assert [call[0] for call in case.client.calls] == ["create", "password"]
    assert case.client.calls[0][1]["ForceAliasCreation"] is False
    captured = capsys.readouterr()
    assert_secret_absent(captured.out + captured.err + case.receipt.read_text())


@pytest.mark.parametrize("kind", ["file", "symlink", "dangling-symlink", "directory"])
def test_existing_receipt_path_is_never_overwritten_or_followed(case, kind):
    target = case.receipt.parent / "unrelated.json"
    if kind == "file":
        case.receipt.write_text("keep this receipt")
    elif kind == "directory":
        case.receipt.mkdir()
    else:
        if kind == "symlink":
            target.write_text("keep this target")
        case.receipt.symlink_to(target)
    assert create(case) == case.bootstrap.EXIT_RECEIPT_ERROR
    assert case.client.calls == []
    if kind == "file":
        assert case.receipt.read_text() == "keep this receipt"
    elif kind == "symlink":
        assert target.read_text() == "keep this target"
    elif kind == "dangling-symlink":
        assert not target.exists()
        assert case.receipt.is_symlink()


@pytest.mark.parametrize("symlink", [False, True])
def test_pending_receipt_reservation_blocks_another_create(case, symlink):
    pending = Path(str(case.receipt) + ".pending")
    if symlink:
        pending.symlink_to(case.receipt.parent / "unrelated")
    else:
        pending.write_text("prior attempt; reconcile")
    assert create(case) == case.bootstrap.EXIT_RECEIPT_ERROR
    assert case.client.calls == []
    assert not case.receipt.exists()
    if not symlink:
        assert pending.read_text() == "prior attempt; reconcile"


@pytest.mark.parametrize("competitor", ["file", "symlink"])
def test_receipt_publication_race_retains_actual_identity_and_never_sets_password(case, competitor):
    target = case.receipt.parent / "unrelated"
    target.write_text("unrelated content")

    def win_destination_race():
        if competitor == "file":
            case.receipt.write_text("competing receipt")
        else:
            case.receipt.symlink_to(target)

    case.client.on_create = win_destination_race
    assert create(case) == case.bootstrap.EXIT_RECEIPT_ERROR
    assert [c[0] for c in case.client.calls] == ["create"]
    assert target.read_text() == "unrelated content"
    if competitor == "file":
        assert case.receipt.read_text() == "competing receipt"
    else:
        assert case.receipt.is_symlink()
    recovery = list(case.receipt.parent.glob(".identity.json.*.created"))
    assert len(recovery) == 1
    assert json.loads(recovery[0].read_text()) == receipt_payload(case)
    assert_private(recovery[0])
    assert Path(str(case.receipt) + ".pending").exists()
    # The complete recovery receipt can authorize cleanup after scope verification.
    case.receipt = recovery[0]
    assert cleanup(case) == 0
    assert [c[0] for c in case.client.calls] == ["create", "get", "delete"]


@pytest.mark.parametrize("code", ["UsernameExistsException", "AliasExistsException"])
def test_existing_cognito_identity_is_never_adopted_or_password_reset(case, code, capsys):
    case.client.create_error = service_error(code)
    assert create(case) == case.bootstrap.EXIT_AWS_ERROR
    assert [c[0] for c in case.client.calls] == ["create"]
    assert not case.receipt.exists()
    pending = Path(str(case.receipt) + ".pending")
    assert json.loads(pending.read_text())["status"] == "create-unconfirmed"
    assert_private(pending)
    captured = capsys.readouterr()
    assert "Existing user or alias refused" in captured.err
    assert_secret_absent(captured.out + captured.err + pending.read_text())


@pytest.mark.parametrize("error", [RuntimeError(PASSWORD), service_error("AccessDeniedException")])
def test_create_errors_preserve_uncertain_evidence_without_secret_or_false_success(case, error, capsys):
    case.client.create_error = error
    assert create(case) == case.bootstrap.EXIT_AWS_ERROR
    assert [c[0] for c in case.client.calls] == ["create"]
    captured = capsys.readouterr()
    assert "outcome is uncertain" in captured.err
    assert_secret_absent(captured.out + captured.err)
    assert not case.receipt.exists()
    pending = Path(str(case.receipt) + ".pending")
    assert pending.exists()
    # A retry must not guess whether the previous request reached Cognito.
    case.client.calls.clear()
    assert create(case) == case.bootstrap.EXIT_RECEIPT_ERROR
    assert case.client.calls == []
    case.receipt = pending
    assert cleanup(case) == case.teardown.EXIT_RECEIPT_ERROR
    assert case.client.calls == []


def test_password_failure_keeps_a_receipt_that_can_clean_up_exact_created_user(case, capsys):
    case.client.password_error = service_error("InvalidPasswordException")
    assert create(case) == case.bootstrap.EXIT_AWS_ERROR
    assert json.loads(case.receipt.read_text()) == receipt_payload(case)
    captured = capsys.readouterr()
    assert_secret_absent(captured.out + captured.err + case.receipt.read_text())
    before = case.receipt.read_bytes()
    assert cleanup(case) == 0
    assert case.client.calls[-2:] == [
        ("get", {"UserPoolId": case.cfg.pool_id, "Username": USERNAME}),
        ("delete", {"UserPoolId": case.cfg.pool_id, "Username": USERNAME}),
    ]
    assert case.receipt.read_bytes() == before


@pytest.mark.parametrize("response", [
    None, {}, {"User": {}},
    {"User": {"Username": USERNAME, "Attributes": []}},
    {"User": {"Username": USERNAME, "Attributes": [
        {"Name": "sub", "Value": SUB}, {"Name": "sub", "Value": SUB},
    ]}},
])
def test_incomplete_create_response_retains_evidence_and_never_sets_password(case, response):
    case.client.create_response = response
    assert create(case) == case.bootstrap.EXIT_RECEIPT_ERROR
    assert [c[0] for c in case.client.calls] == ["create"]
    assert not case.receipt.exists()
    assert Path(str(case.receipt) + ".pending").exists()


def test_receipt_write_failure_after_create_never_sets_password(case, monkeypatch):
    original = case.bootstrap.ReceiptReservation._write_private

    def fail_created(self, name, payload):
        if name.endswith(".created"):
            raise OSError(PASSWORD)
        return original(self, name, payload)

    monkeypatch.setattr(case.bootstrap.ReceiptReservation, "_write_private", fail_created)
    assert create(case) == case.bootstrap.EXIT_RECEIPT_ERROR
    assert [c[0] for c in case.client.calls] == ["create"]
    assert Path(str(case.receipt) + ".pending").exists()
    assert not case.receipt.exists()


@pytest.mark.parametrize("field,value", [
    ("pool_id", "us-east-1_other123"),
    ("region", "eu-west-1"),
    ("email", "unrelated@example.com"),
])
def test_teardown_rejects_changed_configured_scope_before_aws(case, field, value):
    write_receipt(case)
    before = case.receipt.read_bytes()
    case.cleanup_cfg = replace(case.cleanup_cfg, **{field: value})
    assert cleanup(case) == case.teardown.EXIT_RECEIPT_ERROR
    assert case.client.calls == []
    assert case.receipt.read_bytes() == before


@pytest.mark.parametrize("unsafe", [
    "missing", "symlink", "dangling-symlink", "public-mode", "hardlink",
    "directory", "fifo", "malformed-json", "credential-artifact", "extra-key",
    "empty-sub", "wrong-version", "oversize",
])
def test_teardown_rejects_unsafe_or_incomplete_receipts_before_aws(case, unsafe, capsys):
    if unsafe in {"symlink", "hardlink"}:
        write_receipt(case)
        target = case.receipt.with_name("actual-receipt.json")
        case.receipt.rename(target)
        if unsafe == "symlink":
            case.receipt.symlink_to(target)
        else:
            os.link(target, case.receipt)
    elif unsafe == "dangling-symlink":
        case.receipt.symlink_to(case.receipt.with_name("missing-target"))
    elif unsafe == "directory":
        case.receipt.mkdir()
    elif unsafe == "fifo":
        os.mkfifo(case.receipt, 0o600)
    elif unsafe == "public-mode":
        write_receipt(case)
        case.receipt.chmod(0o644)
    elif unsafe == "malformed-json":
        case.receipt.write_text("broken " + PASSWORD)
        case.receipt.chmod(0o600)
    elif unsafe == "oversize":
        case.receipt.write_text(" " * 20_000)
        case.receipt.chmod(0o600)
    elif unsafe != "missing":
        payload = receipt_payload(case)
        if unsafe == "credential-artifact":
            payload = {"email": case.cfg.email, "password": PASSWORD}
        elif unsafe == "extra-key":
            payload["password"] = PASSWORD
        elif unsafe == "empty-sub":
            payload["sub"] = ""
        elif unsafe == "wrong-version":
            payload["version"] = True
        write_receipt(case, payload)
    assert cleanup(case) == case.teardown.EXIT_RECEIPT_ERROR
    assert case.client.calls == []
    captured = capsys.readouterr()
    assert_secret_absent(captured.out + captured.err)


@pytest.mark.parametrize("response", [
    {"Username": "different-user", "UserAttributes": [{"Name": "sub", "Value": SUB}]},
    {"Username": USERNAME, "UserAttributes": [{"Name": "sub", "Value": "different-sub"}]},
    {"Username": USERNAME, "UserAttributes": []},
    {"Username": USERNAME, "UserAttributes": [{"Name": "sub", "Value": None}]},
    {"Username": USERNAME, "UserAttributes": [
        {"Name": "sub", "Value": SUB}, {"Name": "sub", "Value": SUB},
    ]},
    None,
])
def test_teardown_requires_canonical_username_and_unique_matching_sub(case, response):
    write_receipt(case)
    before = case.receipt.read_bytes()
    case.client.get_response = response
    assert cleanup(case) == case.teardown.EXIT_RECEIPT_ERROR
    assert [c[0] for c in case.client.calls] == ["get"]
    assert case.receipt.read_bytes() == before


@pytest.mark.parametrize("operation", ["get", "delete"])
def test_only_explicit_user_not_found_is_idempotent(case, operation, capsys):
    write_receipt(case)
    before = case.receipt.read_bytes()
    setattr(case.client, operation + "_error", service_error("UserNotFoundException"))
    assert cleanup(case) == 0
    assert [c[0] for c in case.client.calls] == (
        ["get"] if operation == "get" else ["get", "delete"]
    )
    captured = capsys.readouterr()
    assert "absent" in captured.err
    assert "Deleted" not in captured.err
    assert_secret_absent(captured.out + captured.err)
    assert case.receipt.read_bytes() == before


@pytest.mark.parametrize("operation", ["get", "delete"])
@pytest.mark.parametrize("error", [
    RuntimeError(PASSWORD),
    service_error("AccessDeniedException"),
    service_error("ResourceNotFoundException"),
])
def test_unrelated_lookup_and_delete_failures_are_nonzero_and_retain_receipt(case, operation, error, capsys):
    write_receipt(case)
    before = case.receipt.read_bytes()
    setattr(case.client, operation + "_error", error)
    assert cleanup(case) == case.teardown.EXIT_AWS_ERROR
    assert [c[0] for c in case.client.calls] == (
        ["get"] if operation == "get" else ["get", "delete"]
    )
    captured = capsys.readouterr()
    assert "absent" not in captured.err
    assert "Deleted" not in captured.err
    assert_secret_absent(captured.out + captured.err)
    assert case.receipt.read_bytes() == before


def test_create_rerun_refused_cleanup_rerun_is_honest_and_reused_name_is_protected(case, capsys):
    assert create(case) == 0
    case.client.calls.clear()
    assert create(case) == case.bootstrap.EXIT_RECEIPT_ERROR
    assert case.client.calls == []
    assert cleanup(case) == 0
    case.client.get_error = service_error("UserNotFoundException")
    assert cleanup(case) == 0
    case.client.get_error = None
    case.client.get_response["UserAttributes"][0]["Value"] = "new-user-sub"
    case.client.calls.clear()
    assert cleanup(case) == case.teardown.EXIT_RECEIPT_ERROR
    assert [c[0] for c in case.client.calls] == ["get"]
    assert case.receipt.exists()
    captured = capsys.readouterr()
    assert_secret_absent(captured.out + captured.err)


@pytest.mark.parametrize("operation", ["create", "cleanup"])
def test_missing_sdk_reports_nonzero_without_traceback_or_secret(case, monkeypatch, capsys, operation):
    import sys

    monkeypatch.setitem(sys.modules, "botocore.exceptions", None)
    if operation == "create":
        rc = case.bootstrap.bootstrap(
            case.cfg, dry_run=False, receipt_path=str(case.receipt),
        )
        assert not case.receipt.exists()
        assert Path(str(case.receipt) + ".pending").exists()
    else:
        write_receipt(case)
        rc = case.teardown.teardown(
            case.cleanup_cfg, dry_run=False, receipt_path=str(case.receipt),
        )
        assert case.receipt.exists()
    assert rc == case.bootstrap.EXIT_AWS_ERROR
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert_secret_absent(captured.out + captured.err)


def test_a_non_sdk_exception_cannot_claim_user_absence(case, capsys):
    write_receipt(case)
    error = RuntimeError(PASSWORD)
    error.response = {"Error": {"Code": "UserNotFoundException"}}
    case.client.get_error = error
    assert cleanup(case) == case.teardown.EXIT_AWS_ERROR
    assert [c[0] for c in case.client.calls] == ["get"]
    captured = capsys.readouterr()
    assert "absent" not in captured.err
    assert_secret_absent(captured.out + captured.err)
