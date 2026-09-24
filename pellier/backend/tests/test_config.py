"""Unit tests for ``config.Settings``.

Covered assertions:

  * ``USE_AGENTCORE_RUNTIME`` defaults to ``False`` so a fresh clone
    runs the in-process Strands orchestrator from in-process orchestrator without
    any env setup (Req 2.5.1 runtime selection switch).
  * Every Cognito/OAuth key added by Tasks 2.5 and 3.1 is declared on
    ``Settings`` with an ``Optional`` typing, so the backend can still
    boot without them. Auth-dependent services are expected to raise
    503 at call time when these are unset, not crash at startup.
  * ``cognito_region_resolved`` falls back to ``AWS_REGION`` when
    ``COGNITO_REGION`` is unset (Req 4.1.2, 4.1.4 — Cognito pools are
    regional and provisioned in the same region as the rest of the
    stack).
  * ``cognito_pool_id_resolved`` accepts the new ``COGNITO_POOL_ID``
    as well as the legacy ``COGNITO_USER_POOL_ID`` so existing demo
    .env files keep working after Task 6.1 renames the key.
  * Required DB env vars are still enforced: constructing ``Settings``
    with none of ``DB_HOST``/``DB_NAME``/``DB_USER``/``DB_PASSWORD``
    set SHALL raise a pydantic ``ValidationError`` that names the
    missing fields — "a clear startup error" per Task 6.1.
  * The feature flag ``USE_AGENTCORE_RUNTIME`` honours common string
    truthy forms (``true``, ``1``) when read from env so the single
    flip documented in ``.env.example`` actually works.

Runnable from the repo root per ``pytest.ini``:

    pellier/backend/.venv/bin/python -m pytest \
        pellier/backend/tests/test_config.py -v
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clear_env(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Drop the named env vars so ``Settings()`` sees no override."""
    for name in names:
        monkeypatch.delenv(name, raising=False)


_AUTH_ENV_VARS = (
    "COGNITO_POOL_ID",
    "COGNITO_USER_POOL_ID",
    "COGNITO_REGION",
    "COGNITO_CLIENT_ID",
    "COGNITO_CLIENT_SECRET",
    "COGNITO_DOMAIN",
    "APP_BASE_URL",
    "OAUTH_REDIRECT_URI",
)


_DB_ENV_VARS = (
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DATABASE_URL",
    "DB_TUNNEL_REMOTE_HOST",
    "DB_SSLROOTCERT",
)


def test_ssm_connection_verifies_remote_identity_but_routes_only_to_loopback(tmp_path):
    from config import Settings
    from urllib.parse import parse_qs, urlsplit

    certificate = tmp_path / "rds bundle.pem"
    certificate.write_text("test certificate")
    settings = Settings(
        DB_HOST="127.0.0.1", DB_TUNNEL_REMOTE_HOST="test.cluster.example",
        DB_PORT=15432, DB_NAME="postgres", DB_USER="operator", DB_PASSWORD="test-password",
        DB_SSLROOTCERT=str(certificate), DATABASE_URL="postgresql://unused?sslmode=disable",
    )
    parsed = urlsplit(settings.database_url)
    query = parse_qs(parsed.query)
    assert parsed.hostname == "test.cluster.example"
    assert parsed.port == 15432
    assert query["hostaddr"] == ["127.0.0.1"]
    assert query["sslmode"] == ["verify-full"]
    assert query["sslrootcert"] == [str(certificate)]
    assert query["ssl_min_protocol_version"] == ["TLSv1.2"]


def test_ssm_connection_refuses_a_missing_ca_bundle(tmp_path):
    from config import Settings

    settings = Settings(
        DB_HOST="127.0.0.1", DB_TUNNEL_REMOTE_HOST="test.cluster.example",
        DB_SSLROOTCERT=str(tmp_path / "missing.pem"),
    )
    with pytest.raises(ValueError, match="CA bundle is missing"):
        _ = settings.database_url


def test_ssm_connection_refuses_a_non_loopback_destination():
    from config import Settings

    settings = Settings(DB_HOST="10.0.0.4", DB_TUNNEL_REMOTE_HOST="test.cluster.example")
    with pytest.raises(ValueError, match="loopback"):
        _ = settings.database_url


@pytest.fixture
def _db_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the four required DB env vars so ``Settings()`` validates.

    The Settings class treats DB_HOST/DB_NAME/DB_USER/DB_PASSWORD as
    required. Tests that are not specifically asserting about DB
    validation use this fixture to isolate the key under test.
    """
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_NAME", "postgres")
    monkeypatch.setenv("DB_USER", "postgres")
    monkeypatch.setenv("DB_PASSWORD", "pw")


# ---------------------------------------------------------------------------
# USE_AGENTCORE_RUNTIME default + parsing
# ---------------------------------------------------------------------------


def test_use_agentcore_runtime_defaults_to_false(
    monkeypatch: pytest.MonkeyPatch, _db_env: None
) -> None:
    """A fresh ``.env`` with no runtime override SHALL keep the
    orchestrator running in-process (Req 2.5.1)."""
    from config import Settings

    _clear_env(monkeypatch, "USE_AGENTCORE_RUNTIME")

    s = Settings()

    assert s.USE_AGENTCORE_RUNTIME is False


@pytest.mark.parametrize("truthy", ["true", "True", "1", "yes"])
def test_use_agentcore_runtime_flips_on_env_override(
    monkeypatch: pytest.MonkeyPatch, _db_env: None, truthy: str
) -> None:
    """Setting ``USE_AGENTCORE_RUNTIME=true`` in ``backend/.env`` SHALL
    flip the feature flag (single-switch migration per Design
    "Runtime selection switch")."""
    from config import Settings

    monkeypatch.setenv("USE_AGENTCORE_RUNTIME", truthy)

    s = Settings()

    assert s.USE_AGENTCORE_RUNTIME is True


# ---------------------------------------------------------------------------
# Cognito / OAuth keys are declared and Optional (Req 4.1.2, 4.1.4, 7.2.3)
# ---------------------------------------------------------------------------


def test_auth_env_vars_are_declared_and_optional(
    monkeypatch: pytest.MonkeyPatch, _db_env: None
) -> None:
    """Every auth key added by Task 6.1 SHALL be a declared field on
    ``Settings`` AND default to ``None`` so the backend boots without
    them; services that actually need auth raise 503 at call time."""
    from config import Settings

    _clear_env(monkeypatch, *_AUTH_ENV_VARS)

    s = Settings()

    # Declared (would AttributeError if Task 6.1 didn't add them).
    assert hasattr(s, "COGNITO_POOL_ID")
    assert hasattr(s, "COGNITO_REGION")
    assert hasattr(s, "COGNITO_CLIENT_ID")
    assert hasattr(s, "COGNITO_CLIENT_SECRET")
    assert hasattr(s, "COGNITO_DOMAIN")
    assert hasattr(s, "APP_BASE_URL")
    assert hasattr(s, "OAUTH_REDIRECT_URI")

    # Optional — unset env SHALL NOT raise.
    assert s.COGNITO_POOL_ID is None
    assert s.COGNITO_CLIENT_ID is None
    assert s.COGNITO_CLIENT_SECRET is None
    assert s.COGNITO_DOMAIN is None
    assert s.APP_BASE_URL is None
    assert s.OAUTH_REDIRECT_URI is None


def test_auth_env_vars_load_from_env(
    monkeypatch: pytest.MonkeyPatch, _db_env: None
) -> None:
    """When set, auth env vars SHALL be readable as-is so route
    handlers can use them directly (Req 3.1.1, 3.1.2)."""
    from config import Settings

    _clear_env(monkeypatch, "COGNITO_USER_POOL_ID")
    monkeypatch.setenv("COGNITO_POOL_ID", "us-east-1_ABvector-search23")
    monkeypatch.setenv("COGNITO_REGION", "us-east-1")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "client-xyz")
    monkeypatch.setenv("COGNITO_CLIENT_SECRET", "secret-xyz")
    monkeypatch.setenv(
        "COGNITO_DOMAIN",
        "pellier.auth.us-east-1.amazoncognito.com",
    )
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:5173")
    monkeypatch.setenv(
        "OAUTH_REDIRECT_URI",
        "http://localhost:8000/api/auth/callback",
    )

    s = Settings()

    assert s.COGNITO_POOL_ID == "us-east-1_ABvector-search23"
    assert s.COGNITO_REGION == "us-east-1"
    assert s.COGNITO_CLIENT_ID == "client-xyz"
    assert s.COGNITO_CLIENT_SECRET == "secret-xyz"
    assert s.COGNITO_DOMAIN == "pellier.auth.us-east-1.amazoncognito.com"
    assert s.APP_BASE_URL == "http://localhost:5173"
    assert s.OAUTH_REDIRECT_URI == "http://localhost:8000/api/auth/callback"


def test_cognito_region_falls_back_to_aws_region(
    monkeypatch: pytest.MonkeyPatch, _db_env: None
) -> None:
    """When ``COGNITO_REGION`` is unset, ``cognito_region_resolved``
    SHALL return the resolved AWS region. ``AWS_DEFAULT_REGION`` wins when
    both region env vars exist so a local .env can override a stale parent
    shell ``AWS_REGION``."""
    from config import Settings

    _clear_env(monkeypatch, "COGNITO_REGION")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")

    s = Settings()

    assert s.COGNITO_REGION is None
    assert s.cognito_region_resolved == "eu-west-1"


def test_aws_default_region_overrides_ambient_aws_region(
    monkeypatch: pytest.MonkeyPatch, _db_env: None
) -> None:
    """Local VSCode shells can inherit AWS_REGION from other tooling. The
    backend SHALL prefer AWS_DEFAULT_REGION so ``pellier/backend/.env`` can
    keep Aurora, Bedrock, AgentCore, and Cognito in one region."""
    from config import Settings

    monkeypatch.setenv("AWS_REGION", "us-east-2")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    s = Settings()

    assert s.aws_region_resolved == "us-east-1"
    assert s.cognito_region_resolved == "us-east-1"


def test_cloudwatch_span_export_uses_the_resolved_aws_region() -> None:
    """Startup must not bypass the stale-shell override for trace export."""
    from pathlib import Path

    app_source = (Path(__file__).parents[1] / "app.py").read_text()
    export_call = app_source.split("init_cloudwatch_span_export(", 1)[1].split(
        ")", 1
    )[0]

    assert "region=settings.aws_region_resolved" in export_call
    assert "region=settings.AWS_REGION" not in export_call


def test_operator_capability_probe_uses_the_resolved_aws_region(monkeypatch) -> None:
    """Operator control-plane checks must target the workshop stack region."""
    from types import SimpleNamespace
    import boto3
    from config import settings
    from services import operator_capabilities

    calls = []
    client = SimpleNamespace(
        list_gateway_targets=lambda **_: {"items": []},
        list_policies=lambda **_: {"policies": []},
    )
    def create(service, **kwargs):
        calls.append((service, kwargs))
        return client
    monkeypatch.setattr(boto3, "client", create)
    monkeypatch.setattr(settings, "AGENTCORE_GATEWAY_ARN", "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/test")
    monkeypatch.setattr(settings, "AGENTCORE_POLICY_ENGINE_ID", "test-engine")
    operator_capabilities._live_gateway_facts()
    assert calls[0][0] == "bedrock-agentcore-control"
    assert calls[0][1]["region_name"] == settings.aws_region_resolved
    assert calls[0][1]["config"].read_timeout <= 8


def test_cognito_pool_id_resolved_prefers_new_name(
    monkeypatch: pytest.MonkeyPatch, _db_env: None
) -> None:
    """The storefront spec standardises on ``COGNITO_POOL_ID`` but the
    older demo used ``COGNITO_USER_POOL_ID``. ``cognito_pool_id_resolved``
    SHALL prefer the new name when both are set so existing .env
    files keep working through the rename."""
    from config import Settings

    monkeypatch.setenv("COGNITO_POOL_ID", "us-east-1_NEW")
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_OLD")

    s = Settings()

    assert s.cognito_pool_id_resolved == "us-east-1_NEW"


def test_cognito_pool_id_resolved_falls_back_to_legacy_name(
    monkeypatch: pytest.MonkeyPatch, _db_env: None
) -> None:
    """If only the legacy ``COGNITO_USER_POOL_ID`` is set, the
    resolved value SHALL still be populated so participants don't
    have to rename their .env during the upgrade."""
    from config import Settings

    _clear_env(monkeypatch, "COGNITO_POOL_ID")
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_LEGACY")

    s = Settings()

    assert s.cognito_pool_id_resolved == "us-east-1_LEGACY"


# ---------------------------------------------------------------------------
# Bedrock model IDs still present (the "plus the existing Bedrock model IDs"
# clause in Task 6.1 means the rename SHALL NOT drop them)
# ---------------------------------------------------------------------------


def test_bedrock_model_ids_have_spec_defaults(
    monkeypatch: pytest.MonkeyPatch, _db_env: None, tmp_path
) -> None:
    """The IN-CODE Bedrock model defaults SHALL match the spec:

      - Cohere Embed v4 (us.cohere.embed-v4:0)
      - Cohere Rerank v3.5 (cohere.rerank-v3-5:0)
      - Claude Opus 5 (global.anthropic.claude-opus-5) for the
        legacy BEDROCK_CHAT_MODEL alias and editorial-agent default

    Settings normally loads ``.env`` via SettingsConfigDict, which would
    override these defaults with whatever the deploy environment set
    (e.g. an older value the workshop CFN UserData wrote). We point the
    Settings at a non-existent env_file so this test exercises the
    in-code defaults specifically — the .env-overridden behavior is
    covered by smoke tests against the live backend.
    """
    from config import Settings

    _clear_env(
        monkeypatch,
        "BEDROCK_EMBEDDING_MODEL",
        "BEDROCK_RERANK_MODEL",
        "BEDROCK_CHAT_MODEL",
        "BEDROCK_OPUS_MODEL",
        "BEDROCK_SONNET_MODEL",
        "BEDROCK_ROUTER_MODEL",
        "BEDROCK_REPORTING_MODEL",
        "BEDROCK_FAST_MODEL",
    )

    # Point env_file at a path that doesn't exist so pydantic-settings
    # falls back to in-code defaults. tmp_path is per-test, so this
    # doesn't affect other tests.
    nonexistent_env = str(tmp_path / "no-such-file.env")
    s = Settings(_env_file=nonexistent_env)

    assert s.BEDROCK_EMBEDDING_MODEL == "us.cohere.embed-v4:0"
    assert s.BEDROCK_RERANK_MODEL == "cohere.rerank-v3-5:0"
    assert s.BEDROCK_CHAT_MODEL == "global.anthropic.claude-opus-5"
    # Per-agent model mix should also default cleanly. Sonnet owns routing,
    # structured extraction, and reporting; Haiku owns explicit fast mode.
    assert s.BEDROCK_OPUS_MODEL == "global.anthropic.claude-opus-5"
    assert s.BEDROCK_SONNET_MODEL == "global.anthropic.claude-sonnet-5"
    assert s.BEDROCK_ROUTER_MODEL == "global.anthropic.claude-sonnet-5"
    assert s.BEDROCK_REPORTING_MODEL == "global.anthropic.claude-sonnet-5"
    assert s.BEDROCK_FAST_MODEL == "global.anthropic.claude-haiku-4-5-20251001-v1:0"


# ---------------------------------------------------------------------------
# "Missing required env vars cause a clear startup error"
# ---------------------------------------------------------------------------


def test_missing_required_db_env_vars_raise_clear_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh clone with no ``.env`` SHALL fail fast with a pydantic
    ``ValidationError`` that names the missing required fields, so
    operators see a clear startup error rather than a late runtime
    crash (Task 6.1 "Done when" clause).

    The storefront spec deliberately keeps the Cognito keys optional
    (they surface as 503s at call time via `CognitoAuthService`), so
    the "required env var" contract is carried by the DB fields that
    the app needs to even connect to Aurora.
    """
    from config import Settings

    _clear_env(monkeypatch, *_DB_ENV_VARS)
    # Also clear the .env fallback by pointing at a non-existent file
    # so the test does not accidentally pick up a developer's local
    # .env sitting next to config.py.
    monkeypatch.setenv(
        "PYDANTIC_SETTINGS_ENV_FILE", "/nonexistent/.env.missing"
    )

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # type: ignore[call-arg]

    message = str(exc_info.value)

    # Each missing required field SHALL be named — that's what makes
    # the error "clear" to an operator tailing startup logs.
    assert "DB_HOST" in message
    assert "DB_NAME" in message
    assert "DB_USER" in message
    assert "DB_PASSWORD" in message
