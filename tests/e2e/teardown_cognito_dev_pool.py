#!/usr/bin/env python3
"""Delete only the Cognito identity proven by a manual bootstrap receipt.

Live cleanup requires ``--receipt`` plus ``E2E_COGNITO_POOL_ID``,
``E2E_TEST_USER_EMAIL`` and ``E2E_AWS_REGION`` matching its creation scope.
The configured email alone never authorizes deletion. The receipt remains
available after success, absence or failure. Dry run contacts no AWS services.
An opaque pool ID does not establish that the pool is nonproduction.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from bootstrap_cognito_dev_pool import (
    EXIT_AWS_ERROR,
    EXIT_MISSING_CONFIG,
    EXIT_OK,
    EXIT_PROD_GUARD,
    EXIT_RECEIPT_ERROR,
    ReceiptError,
    assert_non_production_pool,
    is_service_error,
    load_receipt,
    user_identity,
)


@dataclass(frozen=True)
class TeardownConfig:
    """Config subset needed to delete a single user."""

    pool_id: str
    email: str
    region: str

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "TeardownConfig":
        required = {
            "E2E_COGNITO_POOL_ID": "pool_id",
            "E2E_TEST_USER_EMAIL": "email",
            "E2E_AWS_REGION": "region",
        }
        missing = [k for k in required if not env.get(k)]
        if missing:
            msg = (
                "[teardown_cognito_dev_pool] Missing required env vars: "
                + ", ".join(missing)
            )
            print(msg, file=sys.stderr)
            raise SystemExit(EXIT_MISSING_CONFIG)

        return cls(
            pool_id=env["E2E_COGNITO_POOL_ID"],
            email=env["E2E_TEST_USER_EMAIL"],
            region=env["E2E_AWS_REGION"],
        )


def plan(cfg: TeardownConfig) -> list[dict[str, Any]]:
    """Describe receipt verification and conditional deletion without AWS."""
    return [
        {
            "service": "cognito-idp",
            "operation": "AdminGetUser",
            "requires": "private creation receipt matching configured pool, region and email",
            "params": {
                "UserPoolId": cfg.pool_id,
                "Username": "<created username from --receipt>",
            },
        },
        {
            "service": "cognito-idp",
            "operation": "AdminDeleteUser",
            "requires": "AdminGetUser username and sub exactly match the creation receipt",
            "params": {
                "UserPoolId": cfg.pool_id,
                "Username": "<created username from --receipt>",
            },
        },
    ]


def teardown(
    cfg: TeardownConfig,
    *,
    dry_run: bool,
    receipt_path: Optional[str] = None,
    client: Any = None,
) -> int:
    """Verify ownership before deletion; only explicit user absence is idempotent."""
    assert_non_production_pool(cfg.pool_id)

    steps = plan(cfg)
    if dry_run:
        print(
            "[teardown_cognito_dev_pool] DRY RUN — conditional call plan; "
            "no AWS client or files are created. No live ownership is verified:"
        )
        print(json.dumps(steps, indent=2))
        return EXIT_OK

    if not receipt_path:
        print("[teardown_cognito_dev_pool] Live cleanup requires --receipt.", file=sys.stderr)
        return EXIT_MISSING_CONFIG

    try:
        receipt = load_receipt(receipt_path)
        if (
            receipt["pool_id"] != cfg.pool_id
            or receipt["region"] != cfg.region
            or receipt["requested_username"] != cfg.email
        ):
            raise ReceiptError("Configured scope does not match creation.")
    except (OSError, ValueError):
        print(
            "[teardown_cognito_dev_pool] Receipt is missing, unsafe, incomplete "
            "or outside the configured scope. No user was deleted; evidence retained.",
            file=sys.stderr,
        )
        return EXIT_RECEIPT_ERROR

    params = {"UserPoolId": receipt["pool_id"], "Username": receipt["username"]}
    try:
        if client is None:
            import boto3

            client = boto3.client("cognito-idp", region_name=cfg.region)
        user = client.admin_get_user(**params)
    except Exception as exc:
        if is_service_error(exc, "UserNotFoundException"):
            print(
                "[teardown_cognito_dev_pool] Receipted user is already absent; "
                "no deletion performed. Receipt retained.",
                file=sys.stderr,
            )
            return EXIT_OK
        print(
            "[teardown_cognito_dev_pool] Ownership lookup failed. No deletion "
            "performed; receipt retained.",
            file=sys.stderr,
        )
        return EXIT_AWS_ERROR

    try:
        if user_identity(user, "UserAttributes") != (receipt["username"], receipt["sub"]):
            raise ReceiptError("User identity no longer matches creation.")
    except ReceiptError:
        print(
            "[teardown_cognito_dev_pool] Live username or sub does not match "
            "the receipt. No deletion performed; receipt retained.",
            file=sys.stderr,
        )
        return EXIT_RECEIPT_ERROR

    try:
        client.admin_delete_user(**params)
    except Exception as exc:
        if is_service_error(exc, "UserNotFoundException"):
            print(
                "[teardown_cognito_dev_pool] Verified user became absent before "
                "deletion completed. Receipt retained.",
                file=sys.stderr,
            )
            return EXIT_OK
        print(
            "[teardown_cognito_dev_pool] Delete failed or its outcome is uncertain; "
            "receipt retained for a verified retry.",
            file=sys.stderr,
        )
        return EXIT_AWS_ERROR

    print(
        "[teardown_cognito_dev_pool] Deleted the receipt-verified user. Receipt retained.",
        file=sys.stderr,
    )
    return EXIT_OK


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Delete the E2E test user from a dedicated Cognito dev pool."
        ),
    )
    parser.add_argument(
        "--receipt",
        default=None,
        help="Required for live cleanup: the private identity receipt created by bootstrap.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print the AWS calls that would be made without invoking "
            "boto3. Safe to run without any AWS credentials."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    cfg = TeardownConfig.from_env(os.environ)
    return teardown(cfg, dry_run=args.dry_run, receipt_path=args.receipt)


if __name__ == "__main__":  # pragma: no cover — CLI entrypoint
    raise SystemExit(main())
