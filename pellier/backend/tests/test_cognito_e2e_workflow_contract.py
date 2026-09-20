"""The hosted browser gate must not silently skip required live journeys."""

import importlib.util
from pathlib import Path

import pytest


WORKFLOW = Path(__file__).resolve().parents[3] / ".github/workflows/e2e.yml"
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
COGNITO_E2E = FRONTEND / "e2e" / "cognito"


def test_hosted_job_requires_all_three_identities_and_a_boundary_receipt() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    expected_fragments = (
        "E2E_BASE_URL: ${{ inputs.base_url }}",
        "E2E_ALLOWED_BASE_URL: ${{ vars.E2E_ALLOWED_BASE_URL }}",
        "E2E_BOUNDARY_RUN: ${{ inputs.boundary_run }}",
        "E2E_TEST_USER_EMAIL: ${{ secrets.E2E_TEST_USER_EMAIL }}",
        "E2E_TEST_USER_PASSWORD: ${{ secrets.E2E_TEST_USER_PASSWORD }}",
        "E2E_GOVERN_USERNAME: ${{ secrets.E2E_GOVERN_USERNAME }}",
        "E2E_GOVERN_PASSWORD: ${{ secrets.E2E_GOVERN_PASSWORD }}",
        "E2E_OPERATOR_USERNAME: ${{ secrets.E2E_OPERATOR_USERNAME }}",
        "E2E_OPERATOR_PASSWORD: ${{ secrets.E2E_OPERATOR_PASSWORD }}",
        "python3 tests/e2e/validate_deployment_inputs.py",
    )

    for fragment in expected_fragments:
        assert fragment in source
    assert "bootstrap_cognito_dev_pool.py" not in source
    assert "teardown_cognito_dev_pool.py" not in source
    assert "id-token: write" not in source
    assert "PELLIER_OPERATOR_TOKEN" not in source


def test_optional_cognito_job_runs_the_frontend_cognito_suite() -> None:
    """The auth specs must live under the frontend Playwright package.

    Passing root-level paths to the frontend runner fails in two ways: the
    smoke config excludes them, and Node resolves their ``@playwright/test``
    import relative to the root test directory instead of the frontend's
    dependency tree. Keep the runnable auth suite in the package that owns its
    runner and dependencies.
    """
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "e2e/cognito" in source
    assert "e2e/workshop-smoke.spec.ts" in source
    assert "e2e/operator-client-preview.spec.ts" in source
    assert "e2e/resolution-trace.spec.ts" in source
    assert "e2e/workbench-live.spec.ts" in source
    assert "tests/e2e/auth-happy-path.spec.ts" not in source
    assert "tests/e2e/auth-refresh.spec.ts" not in source
    assert "tests/e2e/auth-refresh-fail.spec.ts" not in source
    assert "tests/e2e/anon-to-auth.spec.ts" not in source


def test_frontend_package_contains_each_cognito_auth_spec() -> None:
    expected = {
        "auth-happy-path.spec.ts",
        "auth-refresh.spec.ts",
        "auth-refresh-fail.spec.ts",
        "anon-to-auth.spec.ts",
    }
    assert {path.name for path in COGNITO_E2E.glob("*.spec.ts")} == expected


@pytest.fixture
def input_validator():
    path = WORKFLOW.parents[2] / "tests/e2e/validate_deployment_inputs.py"
    spec = importlib.util.spec_from_file_location("validate_deployment_inputs", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def live_inputs():
    return {
        "E2E_BASE_URL": "https://workshop.example.com",
        "E2E_ALLOWED_BASE_URL": "https://workshop.example.com",
        "E2E_BOUNDARY_RUN": "boundaries-" + "a" * 32,
        "E2E_TEST_USER_EMAIL": "auth@example.com",
        "E2E_TEST_USER_PASSWORD": "private-auth-value",
        "E2E_GOVERN_USERNAME": "marco",
        "E2E_GOVERN_PASSWORD": "private-shopper-value",
        "E2E_OPERATOR_USERNAME": "operator",
        "E2E_OPERATOR_PASSWORD": "private-operator-value",
    }


def test_approved_deployment_with_complete_inputs_is_accepted(input_validator, live_inputs):
    input_validator.validate(live_inputs)


@pytest.mark.parametrize("key", [
    "E2E_ALLOWED_BASE_URL", "E2E_TEST_USER_PASSWORD", "E2E_GOVERN_USERNAME",
    "E2E_GOVERN_PASSWORD", "E2E_OPERATOR_USERNAME", "E2E_OPERATOR_PASSWORD",
    "E2E_BOUNDARY_RUN",
])
def test_missing_live_inputs_fail_without_disclosing_credentials(
    input_validator, live_inputs, key,
):
    live_inputs.pop(key)
    with pytest.raises(ValueError, match=key) as error:
        input_validator.validate(live_inputs)
    assert "private-" not in str(error.value)


@pytest.mark.parametrize("url", [
    "http://workshop.example.com",
    "https://workshop.example.com.attacker.example",
    "https://workshop.example.com@attacker.example",
    "https://attacker.example@workshop.example.com",
    "https://workshop.example.com:8443",
    "https://workshop.example.com:0",
    "https://workshop.example.com/signin",
    "https://workshop.example.com?redirect=attacker.example",
    "https://workshop.example.com#signin",
    "https://workshop.example.com?",
    "https://workshop.example.com#",
    "https://workshop.example.com/?",
    "https://workshop.example.com/#",
    "https://workshop.example.com\\@attacker.example",
    " https://workshop.example.com",
    "https://workshop.example.com\n",
])
def test_unapproved_origin_or_confusing_url_fails_before_sign_in(
    input_validator, live_inputs, url,
):
    live_inputs["E2E_BASE_URL"] = url
    with pytest.raises(ValueError):
        input_validator.validate(live_inputs)


def test_malformed_boundary_run_cannot_stand_in_for_live_proof(input_validator, live_inputs):
    live_inputs["E2E_BOUNDARY_RUN"] = "synthetic-fixture"
    with pytest.raises(ValueError, match="completed boundary"):
        input_validator.validate(live_inputs)
