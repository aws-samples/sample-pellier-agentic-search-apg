"""AWS-free CLI checks for the optional manual Cognito identity helpers."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# The E2E scripts live at the workspace root, not under the backend
# package. Resolve that path relative to this test file so pytest works
# regardless of invocation cwd.
_E2E_DIR = Path(__file__).resolve().parents[3] / "tests" / "e2e"


def _load_module(name: str):
    """Import a module from ``tests/e2e/``.

    The module is registered in ``sys.modules`` before ``exec_module`` so
    that ``@dataclass`` (which looks up the class's module via
    ``sys.modules[cls.__module__]`` during ``KW_ONLY`` detection on
    Python 3.10+) can resolve the owning namespace. The ``tests/e2e``
    directory is temporarily prepended to ``sys.path`` so that
    ``teardown_cognito_dev_pool`` can ``from bootstrap_cognito_dev_pool
    import ...`` at module load time.
    """
    if name in sys.modules:
        return sys.modules[name]

    spec = importlib.util.spec_from_file_location(
        name, _E2E_DIR / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module

    e2e_str = str(_E2E_DIR)
    added_path = e2e_str not in sys.path
    if added_path:
        sys.path.insert(0, e2e_str)
    try:
        spec.loader.exec_module(module)
    except Exception:
        # Don't poison sys.modules with a half-loaded module on failure.
        sys.modules.pop(name, None)
        raise
    finally:
        if added_path and e2e_str in sys.path:
            sys.path.remove(e2e_str)
    return module


@pytest.fixture
def bootstrap():
    return _load_module("bootstrap_cognito_dev_pool")


@pytest.fixture
def teardown():
    return _load_module("teardown_cognito_dev_pool")


@pytest.fixture
def valid_env(monkeypatch):
    """A full set of env vars that satisfies both scripts."""
    values = {
        "E2E_COGNITO_POOL_ID": "us-east-1_devPool123",
        "E2E_COGNITO_CLIENT_ID": "dev-client-abc",
        "E2E_TEST_USER_EMAIL": "e2e+runner@example.com",
        "E2E_TEST_USER_PASSWORD": "C0rrectH0rse!Battery",
        "E2E_AWS_REGION": "us-east-1",
    }
    # Clear any lingering values from the host environment so tests are
    # deterministic, then install the fixture values.
    for k in values:
        monkeypatch.delenv(k, raising=False)
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    return values


# ---------------------------------------------------------------------------
# Import is side-effect free
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["bootstrap_cognito_dev_pool", "teardown_cognito_dev_pool"])
def test_module_imports_without_aws_sdk(name):
    result = subprocess.run(
        [
            sys.executable, "-B", "-c",
            "import importlib, sys; "
            "sys.modules['boto3'] = None; sys.modules['botocore'] = None; "
            "sys.path.insert(0, sys.argv[1]); importlib.import_module(sys.argv[2])",
            str(_E2E_DIR), name,
        ],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""


# ---------------------------------------------------------------------------
# Missing-config exits
# ---------------------------------------------------------------------------


def test_bootstrap_exits_on_missing_env(bootstrap, monkeypatch, capsys):
    for k in (
        "E2E_COGNITO_POOL_ID",
        "E2E_COGNITO_CLIENT_ID",
        "E2E_TEST_USER_EMAIL",
        "E2E_TEST_USER_PASSWORD",
        "E2E_AWS_REGION",
    ):
        monkeypatch.delenv(k, raising=False)

    with pytest.raises(SystemExit) as exc_info:
        bootstrap.BootstrapConfig.from_env(os.environ)

    assert exc_info.value.code == bootstrap.EXIT_MISSING_CONFIG
    err = capsys.readouterr().err
    assert "Missing required env vars" in err
    # Every key should be named in the message.
    for k in (
        "E2E_COGNITO_POOL_ID",
        "E2E_COGNITO_CLIENT_ID",
        "E2E_TEST_USER_EMAIL",
        "E2E_TEST_USER_PASSWORD",
        "E2E_AWS_REGION",
    ):
        assert k in err


def test_teardown_exits_on_missing_env(teardown, monkeypatch, capsys):
    for k in (
        "E2E_COGNITO_POOL_ID",
        "E2E_TEST_USER_EMAIL",
        "E2E_AWS_REGION",
    ):
        monkeypatch.delenv(k, raising=False)

    with pytest.raises(SystemExit) as exc_info:
        teardown.TeardownConfig.from_env(os.environ)

    assert exc_info.value.code == teardown.EXIT_MISSING_CONFIG
    assert "Missing required env vars" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Prod-pool guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pool_id",
    [
        "us-east-1_prodPool",
        "us-east-1_PRODpool",
        "us-east-1_production-users",
        "us-east-1_PRD_pool",
        "us-east-1_appPrdPool",
    ],
)
def test_prod_guard_rejects_denylisted_pool(bootstrap, pool_id, capsys):
    with pytest.raises(SystemExit) as exc_info:
        bootstrap.assert_non_production_pool(pool_id)
    assert exc_info.value.code == bootstrap.EXIT_PROD_GUARD
    err = capsys.readouterr().err
    assert "denylisted" in err


@pytest.mark.parametrize(
    "pool_id",
    [
        "us-east-1_devPool",
        "us-east-1_StagingPool",
        "eu-west-1_sandbox",
        "us-east-1_testPool42",
    ],
)
def test_denylist_does_not_classify_opaque_pool_ids(bootstrap, pool_id):
    # Passing the substring check makes no claim about the real pool's purpose.
    bootstrap.assert_non_production_pool(pool_id)


# ---------------------------------------------------------------------------
# --dry-run path
# ---------------------------------------------------------------------------


def test_bootstrap_dry_run_does_not_touch_boto3(
    bootstrap, valid_env, monkeypatch, tmp_path, capsys
):
    monkeypatch.setitem(sys.modules, "boto3", None)
    receipt = tmp_path / "identity.json"

    rc = bootstrap.main(["--dry-run", "--receipt", str(receipt)])
    assert rc == bootstrap.EXIT_OK
    captured = capsys.readouterr()
    out = captured.out
    assert "DRY RUN" in out
    assert "AdminCreateUser" in out
    assert "AdminSetUserPassword" in out
    assert "***redacted***" in out
    assert valid_env["E2E_TEST_USER_PASSWORD"] not in out + captured.err
    assert list(tmp_path.iterdir()) == []
    assert os.environ["E2E_TEST_USER_PASSWORD"] == valid_env["E2E_TEST_USER_PASSWORD"]


def test_removed_credential_output_option_is_rejected(
    bootstrap, valid_env, tmp_path, capsys
):
    out_path = tmp_path / "creds.json"
    with pytest.raises(SystemExit) as exc_info:
        bootstrap.main(["--dry-run", "--out", str(out_path)])

    assert exc_info.value.code != 0
    assert not out_path.exists()
    captured = capsys.readouterr()
    assert valid_env["E2E_TEST_USER_PASSWORD"] not in captured.out + captured.err


def test_config_repr_and_call_plan_do_not_disclose_password(bootstrap, valid_env):
    cfg = bootstrap.BootstrapConfig.from_env(os.environ)
    assert cfg.password not in repr(cfg)
    assert cfg.password not in json.dumps(bootstrap.plan(cfg))


def test_bootstrap_dry_run_respects_prod_guard(
    bootstrap, monkeypatch, capsys
):
    monkeypatch.setenv("E2E_COGNITO_POOL_ID", "us-east-1_prodUsers")
    monkeypatch.setenv("E2E_COGNITO_CLIENT_ID", "client")
    monkeypatch.setenv("E2E_TEST_USER_EMAIL", "x@example.com")
    monkeypatch.setenv("E2E_TEST_USER_PASSWORD", "pw")
    monkeypatch.setenv("E2E_AWS_REGION", "us-east-1")

    with pytest.raises(SystemExit) as exc_info:
        bootstrap.main(["--dry-run"])

    assert exc_info.value.code == bootstrap.EXIT_PROD_GUARD
    assert "denylisted" in capsys.readouterr().err


def test_teardown_dry_run_does_not_touch_boto3(
    teardown, valid_env, monkeypatch, capsys, tmp_path
):
    monkeypatch.setitem(sys.modules, "boto3", None)

    rc = teardown.main(["--dry-run", "--receipt", str(tmp_path / "missing.json")])
    assert rc == teardown.EXIT_OK

    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "AdminGetUser" in out
    assert "AdminDeleteUser" in out
    assert "No live ownership is verified" in out
    assert list(tmp_path.iterdir()) == []


def test_teardown_dry_run_respects_prod_guard(
    teardown, monkeypatch, capsys
):
    monkeypatch.setenv("E2E_COGNITO_POOL_ID", "us-east-1_ProductionUsers")
    monkeypatch.setenv("E2E_TEST_USER_EMAIL", "x@example.com")
    monkeypatch.setenv("E2E_AWS_REGION", "us-east-1")

    with pytest.raises(SystemExit) as exc_info:
        teardown.main(["--dry-run"])

    assert exc_info.value.code == teardown.EXIT_PROD_GUARD
    assert "denylisted" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Plans keep password setup and deletion conditional on ownership.
# ---------------------------------------------------------------------------


def test_bootstrap_plan_shape(bootstrap, valid_env):
    cfg = bootstrap.BootstrapConfig.from_env(os.environ)
    steps = bootstrap.plan(cfg)

    assert [s["operation"] for s in steps] == [
        "AdminCreateUser",
        "AdminSetUserPassword",
    ]
    assert all(s["service"] == "cognito-idp" for s in steps)

    create_params = steps[0]["params"]
    assert create_params["UserPoolId"] == valid_env["E2E_COGNITO_POOL_ID"]
    assert create_params["Username"] == valid_env["E2E_TEST_USER_EMAIL"]
    assert create_params["MessageAction"] == "SUPPRESS"
    assert create_params["ForceAliasCreation"] is False
    assert {"Name": "email_verified", "Value": "true"} in create_params[
        "UserAttributes"
    ]

    set_pw_params = steps[1]["params"]
    assert set_pw_params["Permanent"] is True
    # plan() must redact the real password; only bootstrap() passes the
    # real one to boto3.
    assert set_pw_params["Password"] == "***redacted***"
    assert set_pw_params["Username"] != cfg.email
    assert "receipt" in steps[1]["requires"]


def test_teardown_plan_shape(teardown, valid_env):
    cfg = teardown.TeardownConfig.from_env(os.environ)
    steps = teardown.plan(cfg)

    assert [s["operation"] for s in steps] == ["AdminGetUser", "AdminDeleteUser"]
    assert all(s["params"]["UserPoolId"] == cfg.pool_id for s in steps)
    assert all(s["params"]["Username"] != cfg.email for s in steps)
    assert "sub" in steps[1]["requires"]


@pytest.mark.parametrize("name", ["bootstrap_cognito_dev_pool", "teardown_cognito_dev_pool"])
def test_live_cli_requires_receipt_before_aws(name, valid_env, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "boto3", None)
    module = _load_module(name)
    assert module.main([]) == module.EXIT_MISSING_CONFIG
    captured = capsys.readouterr()
    assert "--receipt" in captured.err
    assert valid_env["E2E_TEST_USER_PASSWORD"] not in captured.out + captured.err
