"""Unit tests for ``config.Settings`` (Task 6.1).

Validates the storefront spec's configuration contract from
`.kiro/specs/pellier-storefront/tasks.md` Task 6.1:

    Acceptance: Req 4.1.2, 4.1.4, 7.2.3; Design runtime switch.

Covered assertions:

  * ``USE_AGENTCORE_RUNTIME`` defaults to ``False`` so a fresh clone
    runs the in-process Strands orchestrator from Challenge 4 without
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
)


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
    monkeypatch.setenv("COGNITO_POOL_ID", "us-west-2_ABC123")
    monkeypatch.setenv("COGNITO_REGION", "us-east-1")
    monkeypatch.setenv("COGNITO_CLIENT_ID", "client-xyz")
    monkeypatch.setenv("COGNITO_CLIENT_SECRET", "secret-xyz")
    monkeypatch.setenv(
        "COGNITO_DOMAIN",
        "pellier.auth.us-west-2.amazoncognito.com",
    )
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:5173")
    monkeypatch.setenv(
        "OAUTH_REDIRECT_URI",
        "http://localhost:8000/api/auth/callback",
    )

    s = Settings()

    assert s.COGNITO_POOL_ID == "us-west-2_ABC123"
    assert s.COGNITO_REGION == "us-east-1"
    assert s.COGNITO_CLIENT_ID == "client-xyz"
    assert s.COGNITO_CLIENT_SECRET == "secret-xyz"
    assert s.COGNITO_DOMAIN == "pellier.auth.us-west-2.amazoncognito.com"
    assert s.APP_BASE_URL == "http://localhost:5173"
    assert s.OAUTH_REDIRECT_URI == "http://localhost:8000/api/auth/callback"


def test_cognito_region_falls_back_to_aws_region(
    monkeypatch: pytest.MonkeyPatch, _db_env: None
) -> None:
    """When ``COGNITO_REGION`` is unset, ``cognito_region_resolved``
    SHALL return ``AWS_REGION`` — Cognito pools are regional and the
    workshop provisions them in the same region as the rest of the
    stack (Req 4.1.4)."""
    from config import Settings

    _clear_env(monkeypatch, "COGNITO_REGION")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")

    s = Settings()

    assert s.COGNITO_REGION is None
    assert s.cognito_region_resolved == "eu-west-1"


def test_cognito_pool_id_resolved_prefers_new_name(
    monkeypatch: pytest.MonkeyPatch, _db_env: None
) -> None:
    """The storefront spec standardises on ``COGNITO_POOL_ID`` but the
    older demo used ``COGNITO_USER_POOL_ID``. ``cognito_pool_id_resolved``
    SHALL prefer the new name when both are set so existing .env
    files keep working through the rename."""
    from config import Settings

    monkeypatch.setenv("COGNITO_POOL_ID", "us-west-2_NEW")
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-west-2_OLD")

    s = Settings()

    assert s.cognito_pool_id_resolved == "us-west-2_NEW"


def test_cognito_pool_id_resolved_falls_back_to_legacy_name(
    monkeypatch: pytest.MonkeyPatch, _db_env: None
) -> None:
    """If only the legacy ``COGNITO_USER_POOL_ID`` is set, the
    resolved value SHALL still be populated so participants don't
    have to rename their .env during the upgrade."""
    from config import Settings

    _clear_env(monkeypatch, "COGNITO_POOL_ID")
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-west-2_LEGACY")

    s = Settings()

    assert s.cognito_pool_id_resolved == "us-west-2_LEGACY"


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
      - Claude Opus 4.7 (global.anthropic.claude-opus-4-7) for the
        legacy BEDROCK_CHAT_MODEL alias

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
    )

    # Point env_file at a path that doesn't exist so pydantic-settings
    # falls back to in-code defaults. tmp_path is per-test, so this
    # doesn't affect other tests.
    nonexistent_env = str(tmp_path / "no-such-file.env")
    s = Settings(_env_file=nonexistent_env)

    assert s.BEDROCK_EMBEDDING_MODEL == "us.cohere.embed-v4:0"
    assert s.BEDROCK_RERANK_MODEL == "cohere.rerank-v3-5:0"
    assert s.BEDROCK_CHAT_MODEL == "global.anthropic.claude-opus-4-7"
    # Per-agent model mix should also default cleanly.
    assert s.BEDROCK_SONNET_MODEL == "global.anthropic.claude-sonnet-4-6"
    assert s.BEDROCK_HAIKU_MODEL == "global.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert s.BEDROCK_OPUS_MODEL == "global.anthropic.claude-opus-4-7"


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
