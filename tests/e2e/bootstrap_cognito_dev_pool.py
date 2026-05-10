#!/usr/bin/env python3
"""Bootstrap a single E2E test user in a dedicated Cognito dev pool.

Design: ``.kiro/specs/pellier-storefront/design.md`` — Testing Strategy,
"E2E (Playwright against a dedicated Cognito dev pool)".

This script is CI-only. It uses a CI-scoped admin role (via ambient AWS
credentials in the CI runner, never developer laptops) to call
``AdminCreateUser`` + ``AdminSetUserPassword`` against a Cognito User Pool
that is **separate from the workshop infrastructure**.  Google and Apple
IdP flows are validated via manual workshop dry-runs; this pool is
email/password-only.

Environment variables (all required unless ``--dry-run`` is passed):

* ``E2E_COGNITO_POOL_ID``   — dedicated dev pool (must NOT contain ``prod``)
* ``E2E_COGNITO_CLIENT_ID`` — email-only app client
* ``E2E_TEST_USER_EMAIL``   — email for the test user (also becomes the
  Cognito ``username``)
* ``E2E_TEST_USER_PASSWORD`` — password meeting the pool's password policy
* ``E2E_AWS_REGION``        — AWS region of the pool

Side effects are gated behind ``main()`` so the module can be imported for
unit testing without hitting AWS.

Production safety:
    * The pool id is checked against a denylist of substrings (``prod``,
      ``production``, ``prd``). Any match aborts with exit code ``2``.
    * Only ``AdminCreateUser``, ``AdminSetUserPassword`` and
      ``AdminGetUser`` are invoked. No destructive operations are performed
      by this script; teardown is a sibling script.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Mapping, Optional

# Substrings that signal a production pool id. Matching is case-insensitive
# and triggers an immediate abort per the workspace production-safety rule.
_PROD_POOL_DENYLIST: tuple[str, ...] = ("prod", "production", "prd")

# Exit codes
EXIT_OK = 0
EXIT_MISSING_CONFIG = 1
EXIT_PROD_GUARD = 2
EXIT_AWS_ERROR = 3


@dataclass(frozen=True)
class BootstrapConfig:
    """Immutable bundle of config read from the environment."""

    pool_id: str
    client_id: str
    email: str
    password: str
    region: str

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "BootstrapConfig":
        """Build a ``BootstrapConfig`` from an env-like mapping.

        Raises ``SystemExit(EXIT_MISSING_CONFIG)`` with a helpful message
        listing the missing keys.
        """
        required = {
            "E2E_COGNITO_POOL_ID": "pool_id",
            "E2E_COGNITO_CLIENT_ID": "client_id",
            "E2E_TEST_USER_EMAIL": "email",
            "E2E_TEST_USER_PASSWORD": "password",
            "E2E_AWS_REGION": "region",
        }
        missing = [k for k in required if not env.get(k)]
        if missing:
            msg = (
                "[bootstrap_cognito_dev_pool] Missing required env vars: "
                + ", ".join(missing)
            )
            print(msg, file=sys.stderr)
            raise SystemExit(EXIT_MISSING_CONFIG)

        return cls(
            pool_id=env["E2E_COGNITO_POOL_ID"],
            client_id=env["E2E_COGNITO_CLIENT_ID"],
            email=env["E2E_TEST_USER_EMAIL"],
            password=env["E2E_TEST_USER_PASSWORD"],
            region=env["E2E_AWS_REGION"],
        )


def assert_non_production_pool(pool_id: str) -> None:
    """Hard-guard against accidental production pool usage.

    Raises ``SystemExit(EXIT_PROD_GUARD)`` if ``pool_id`` contains any
    denylisted substring (case-insensitive).
    """
    lowered = pool_id.lower()
    for needle in _PROD_POOL_DENYLIST:
        if needle in lowered:
            print(
                f"[bootstrap_cognito_dev_pool] Refusing to operate on pool "
                f"'{pool_id}': contains denylisted substring '{needle}'. "
                f"This script is restricted to dedicated dev pools.",
                file=sys.stderr,
            )
            raise SystemExit(EXIT_PROD_GUARD)


def plan(cfg: BootstrapConfig) -> list[dict[str, Any]]:
    """Return the ordered list of AWS calls we WOULD make.

    Shared between ``--dry-run`` (for visibility) and the real path (so we
    keep a single source of truth for argument shapes).
    """
    return [
        {
            "service": "cognito-idp",
            "operation": "AdminCreateUser",
            "params": {
                "UserPoolId": cfg.pool_id,
                "Username": cfg.email,
                "UserAttributes": [
                    {"Name": "email", "Value": cfg.email},
                    {"Name": "email_verified", "Value": "true"},
                ],
                "MessageAction": "SUPPRESS",
                "DesiredDeliveryMediums": ["EMAIL"],
            },
        },
        {
            "service": "cognito-idp",
            "operation": "AdminSetUserPassword",
            "params": {
                "UserPoolId": cfg.pool_id,
                "Username": cfg.email,
                "Password": "***redacted***",
                "Permanent": True,
            },
        },
    ]


def _emit_credentials(cfg: BootstrapConfig, out_path: Optional[str]) -> None:
    """Emit the bootstrapped credentials for the Playwright runner.

    When ``out_path`` is provided, writes a JSON object there; otherwise
    prints the same JSON to stdout. Playwright specs read these via env
    vars ``E2E_TEST_USER_EMAIL`` / ``E2E_TEST_USER_PASSWORD``, but some CI
    providers prefer a file artifact for the next step to consume.
    """
    payload = {"email": cfg.email, "password": cfg.password}
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        # Do NOT echo the password to stdout when writing a file.
        print(
            f"[bootstrap_cognito_dev_pool] Wrote credentials to {out_path}",
            file=sys.stderr,
        )
    else:
        print(json.dumps(payload))


def bootstrap(
    cfg: BootstrapConfig,
    *,
    dry_run: bool,
    out_path: Optional[str] = None,
    client: Any = None,
) -> int:
    """Bootstrap a single test user.

    ``client`` is injectable so unit tests can pass a stub; production
    callers leave it ``None`` and boto3 is imported lazily.
    """
    assert_non_production_pool(cfg.pool_id)

    steps = plan(cfg)
    if dry_run:
        print(
            "[bootstrap_cognito_dev_pool] DRY RUN — the following AWS calls "
            "would be made (no boto3 client will be created):"
        )
        print(json.dumps(steps, indent=2))
        _emit_credentials(cfg, out_path)
        return EXIT_OK

    if client is None:
        # Lazy import so ``python -c 'import bootstrap_cognito_dev_pool'``
        # never pulls boto3 on machines that don't have it installed.
        import boto3  # type: ignore[import-not-found]

        client = boto3.client("cognito-idp", region_name=cfg.region)

    try:
        # AdminCreateUser — idempotent-ish: if the user already exists from
        # a previous failed run, we fall through to AdminSetUserPassword
        # which will reset the password and mark it Permanent.
        try:
            client.admin_create_user(**steps[0]["params"])
        except client.exceptions.UsernameExistsException:  # type: ignore[attr-defined]
            print(
                f"[bootstrap_cognito_dev_pool] User {cfg.email} already "
                f"exists in pool {cfg.pool_id}; resetting password.",
                file=sys.stderr,
            )

        # AdminSetUserPassword — Permanent=True so the user can sign in
        # immediately without the FORCE_CHANGE_PASSWORD challenge.
        client.admin_set_user_password(
            UserPoolId=cfg.pool_id,
            Username=cfg.email,
            Password=cfg.password,
            Permanent=True,
        )
    except Exception as exc:  # noqa: BLE001 — surface every AWS failure
        print(
            f"[bootstrap_cognito_dev_pool] AWS error: {exc}",
            file=sys.stderr,
        )
        return EXIT_AWS_ERROR

    _emit_credentials(cfg, out_path)
    return EXIT_OK


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a Cognito test user for E2E (AdminCreateUser + "
            "AdminSetUserPassword) in a dedicated dev pool."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print the AWS calls that would be made without invoking "
            "boto3. Safe to run without any AWS credentials."
        ),
    )
    parser.add_argument(
        "--out",
        default=None,
        help=(
            "Optional path to write {email, password} JSON. When omitted, "
            "JSON is written to stdout (useful for CI ``outputs``)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    cfg = BootstrapConfig.from_env(os.environ)
    return bootstrap(cfg, dry_run=args.dry_run, out_path=args.out)


if __name__ == "__main__":  # pragma: no cover — CLI entrypoint
    raise SystemExit(main())
