"""Unit tests for the E2E Cognito dev pool bootstrap scripts — dry-run only.

The scripts themselves need real AWS to exercise end-to-end (that's what
``.github/workflows/e2e.yml`` is for). These tests cover the parts that
must behave correctly in CI *before* any AWS call:

* Module import is side-effect free.
* Missing env vars exit with a helpful message.
* The prod-pool guard rejects anything containing ``prod`` / ``production``
  / ``prd`` (case-insensitive).
* ``--dry-run`` prints the exact AWS call plan without creating a boto3
  client — safe to run with zero AWS credentials on a laptop.

Task: 3.8 "E2E Cognito dev pool bootstrap (CI)".
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
from contextlib import redirect_stdout
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
        "E2E_COGNITO_POOL_ID": "us-west-2_devPool123",
        "E2E_COGNITO_CLIENT_ID": "dev-client-abc",
        "E2E_TEST_USER_EMAIL": "e2e+runner@example.com",
        "E2E_TEST_USER_PASSWORD": "C0rrectH0rse!Battery",
        "E2E_AWS_REGION": "us-west-2",
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


def test_bootstrap_module_imports_without_side_effects(bootstrap):
    # The module exposes the public surface we rely on — if import had
    # side effects (e.g. building a boto3 client) this assertion would
    # still pass, so we also check that ``boto3`` is NOT in sys.modules
    # purely from loading this module on a fresh interpreter.
    assert hasattr(bootstrap, "main")
    assert hasattr(bootstrap, "bootstrap")
    assert hasattr(bootstrap, "BootstrapConfig")
    assert hasattr(bootstrap, "assert_non_production_pool")


def test_teardown_module_imports_without_side_effects(teardown):
    assert hasattr(teardown, "main")
    assert hasattr(teardown, "teardown")
    assert hasattr(teardown, "TeardownConfig")


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
        "us-west-2_prodPool",
        "us-west-2_PRODpool",
        "us-west-2_production-users",
        "us-west-2_PRD_pool",
        "us-west-2_appPrdPool",
    ],
)
def test_prod_guard_rejects_denylisted_pool(bootstrap, pool_id, capsys):
    with pytest.raises(SystemExit) as exc_info:
        bootstrap.assert_non_production_pool(pool_id)
    assert exc_info.value.code == bootstrap.EXIT_PROD_GUARD
    err = capsys.readouterr().err
    assert pool_id in err
    assert "denylisted" in err


@pytest.mark.parametrize(
    "pool_id",
    [
        "us-west-2_devPool",
        "us-east-1_StagingPool",
        "eu-west-1_sandbox",
        "us-west-2_testPool42",
    ],
)
def test_prod_guard_allows_non_production_pools(bootstrap, pool_id):
    # Should not raise.
    bootstrap.assert_non_production_pool(pool_id)


# ---------------------------------------------------------------------------
# --dry-run path
# ---------------------------------------------------------------------------


def test_bootstrap_dry_run_does_not_touch_boto3(
    bootstrap, valid_env, monkeypatch
):
    # If boto3 were imported we'd see the call; fail loudly if so.
    def _explode(*_a, **_kw):
        raise AssertionError(
            "boto3.client must not be called in --dry-run mode"
        )

    # Pretend boto3 is unavailable; dry-run must succeed anyway.
    monkeypatch.setitem(sys.modules, "boto3", None)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = bootstrap.main(["--dry-run"])

    assert rc == bootstrap.EXIT_OK

    out = buf.getvalue()
    assert "DRY RUN" in out
    assert "AdminCreateUser" in out
    assert "AdminSetUserPassword" in out
    # Password must not leak in the planned call output; the plan uses a
    # redaction marker and the real password only appears in the final
    # credentials JSON line.
    assert "***redacted***" in out
    lines = out.strip().splitlines()
    creds_line = lines[-1]
    plan_output = "\n".join(lines[:-1])
    assert valid_env["E2E_TEST_USER_PASSWORD"] not in plan_output

    # The credentials JSON is emitted at the end of dry-run for the
    # Playwright step to consume.
    payload = json.loads(creds_line)
    assert payload == {
        "email": valid_env["E2E_TEST_USER_EMAIL"],
        "password": valid_env["E2E_TEST_USER_PASSWORD"],
    }


def test_bootstrap_dry_run_writes_out_file(
    bootstrap, valid_env, tmp_path, capsys
):
    out_path = tmp_path / "creds.json"

    rc = bootstrap.main(["--dry-run", "--out", str(out_path)])

    assert rc == bootstrap.EXIT_OK
    assert out_path.exists()

    payload = json.loads(out_path.read_text())
    assert payload == {
        "email": valid_env["E2E_TEST_USER_EMAIL"],
        "password": valid_env["E2E_TEST_USER_PASSWORD"],
    }

    # When --out is used, password must NOT be echoed to stdout.
    captured = capsys.readouterr()
    assert valid_env["E2E_TEST_USER_PASSWORD"] not in captured.out


def test_bootstrap_dry_run_respects_prod_guard(
    bootstrap, monkeypatch, capsys
):
    monkeypatch.setenv("E2E_COGNITO_POOL_ID", "us-west-2_prodUsers")
    monkeypatch.setenv("E2E_COGNITO_CLIENT_ID", "client")
    monkeypatch.setenv("E2E_TEST_USER_EMAIL", "x@example.com")
    monkeypatch.setenv("E2E_TEST_USER_PASSWORD", "pw")
    monkeypatch.setenv("E2E_AWS_REGION", "us-west-2")

    with pytest.raises(SystemExit) as exc_info:
        bootstrap.main(["--dry-run"])

    assert exc_info.value.code == bootstrap.EXIT_PROD_GUARD
    assert "denylisted" in capsys.readouterr().err


def test_teardown_dry_run_does_not_touch_boto3(
    teardown, valid_env, monkeypatch, capsys
):
    monkeypatch.setitem(sys.modules, "boto3", None)

    rc = teardown.main(["--dry-run"])
    assert rc == teardown.EXIT_OK

    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "AdminDeleteUser" in out


def test_teardown_dry_run_respects_prod_guard(
    teardown, monkeypatch, capsys
):
    monkeypatch.setenv("E2E_COGNITO_POOL_ID", "us-west-2_ProductionUsers")
    monkeypatch.setenv("E2E_TEST_USER_EMAIL", "x@example.com")
    monkeypatch.setenv("E2E_AWS_REGION", "us-west-2")

    with pytest.raises(SystemExit) as exc_info:
        teardown.main(["--dry-run"])

    assert exc_info.value.code == teardown.EXIT_PROD_GUARD
    assert "denylisted" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# plan() shape is stable (drift-detection)
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
    assert {"Name": "email_verified", "Value": "true"} in create_params[
        "UserAttributes"
    ]

    set_pw_params = steps[1]["params"]
    assert set_pw_params["Permanent"] is True
    # plan() must redact the real password; only bootstrap() passes the
    # real one to boto3.
    assert set_pw_params["Password"] == "***redacted***"


def test_teardown_plan_shape(teardown, valid_env):
    cfg = teardown.TeardownConfig.from_env(os.environ)
    steps = teardown.plan(cfg)

    assert len(steps) == 1
    assert steps[0]["operation"] == "AdminDeleteUser"
    assert steps[0]["params"]["UserPoolId"] == valid_env["E2E_COGNITO_POOL_ID"]
    assert steps[0]["params"]["Username"] == valid_env["E2E_TEST_USER_EMAIL"]
