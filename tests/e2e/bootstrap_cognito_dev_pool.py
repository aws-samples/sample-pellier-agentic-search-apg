#!/usr/bin/env python3
"""Manually create one disposable Cognito test identity with an ownership receipt.

The hosted E2E workflow uses existing identities and does not run this helper.
Live creation requires an unused ``--receipt`` path and explicitly configured
``E2E_COGNITO_POOL_ID``, ``E2E_COGNITO_CLIENT_ID``, ``E2E_TEST_USER_EMAIL``,
``E2E_TEST_USER_PASSWORD`` and ``E2E_AWS_REGION`` environment variables.
Dry run uses the same configuration, but never contacts AWS or writes files.

Passwords stay in process memory. A private, nonsecret identity receipt is
published after creation and before password setup. Existing users are refused.
Pool-name denylisting is supplemental: an opaque pool ID cannot prove that a
pool is nonproduction. See docs/E2E-IDENTITIES.md for scope and recovery.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

# Supplemental typo guard, not a classification of the configured pool.
_PROD_POOL_DENYLIST: tuple[str, ...] = ("prod", "production", "prd")

# Exit codes
EXIT_OK = 0
EXIT_MISSING_CONFIG = 1
EXIT_PROD_GUARD = 2
EXIT_AWS_ERROR = 3
EXIT_RECEIPT_ERROR = 4

_RECEIPT_KIND = "pellier-e2e-cognito-user"
_RECEIPT_KEYS = {
    "version", "kind", "pool_id", "region", "requested_username", "username", "sub",
}
_MAX_RECEIPT_BYTES = 16_384


@dataclass(frozen=True)
class BootstrapConfig:
    """Immutable bundle of config read from the environment."""

    pool_id: str
    client_id: str
    email: str
    password: str = field(repr=False)
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
    """Reject denylisted labels; passing this check does not establish scope."""
    lowered = pool_id.lower()
    for needle in _PROD_POOL_DENYLIST:
        if needle in lowered:
            print(
                "[bootstrap_cognito_dev_pool] Refusing a pool ID containing "
                "a denylisted label. Independently verify the dedicated dev "
                "pool and the AWS credential scope.",
                file=sys.stderr,
            )
            raise SystemExit(EXIT_PROD_GUARD)


class ReceiptError(ValueError):
    """Ownership evidence is unavailable, unsafe or inconsistent."""


def user_identity(user: Any, attributes_key: str) -> tuple[str, str]:
    """Extract only the canonical username and unique sub from an AWS response."""
    if not isinstance(user, dict) or not isinstance(user.get("Username"), str):
        raise ReceiptError("Missing created username.")
    attributes = user.get(attributes_key)
    if not isinstance(attributes, list):
        raise ReceiptError("Missing user attributes.")
    subs = [
        item.get("Value") for item in attributes
        if isinstance(item, dict) and item.get("Name") == "sub"
    ]
    if (
        not user["Username"].strip()
        or len(subs) != 1
        or not isinstance(subs[0], str)
        or not subs[0].strip()
    ):
        raise ReceiptError("Missing or ambiguous user identity.")
    return user["Username"], subs[0]


def is_service_error(exc: Exception, code: str) -> bool:
    """Only an explicit SDK service error can mean that a user is absent."""
    try:
        from botocore.exceptions import ClientError
    except ImportError:
        return False

    if not isinstance(exc, ClientError):
        return False
    error = exc.response.get("Error")
    return isinstance(error, dict) and error.get("Code") == code


class ReceiptReservation:
    """Reserve a path, then atomically publish a complete receipt without replacing it.

    All file operations share a pinned directory descriptor. The exclusive
    .pending file blocks cooperating creators, including a retry after an
    uncertain create result. A failed publish retains the .created file.
    """

    def __init__(self, receipt_path: str, cfg: BootstrapConfig):
        path = Path(receipt_path)
        self.name = path.name
        self.pending_name = self.name + ".pending"
        self.directory_fd: Optional[int] = None
        self.scope = {
            "pool_id": cfg.pool_id,
            "region": cfg.region,
            "requested_username": cfg.email,
        }
        try:
            self.directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.stat(self.name, dir_fd=self.directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ReceiptError("Receipt already exists.")
            self._write_private(
                self.pending_name,
                {"version": 1, "status": "create-unconfirmed", **self.scope},
            )
            os.fsync(self.directory_fd)
        except Exception:
            self.close()
            raise

    def _write_private(self, name: str, payload: dict[str, Any]) -> None:
        fd = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=self.directory_fd,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(payload, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

    def publish(self, username: str, sub: str) -> None:
        staging_name = f".{self.name}.{uuid.uuid4().hex}.created"
        self._write_private(
            staging_name,
            {
                "version": 1,
                "kind": _RECEIPT_KIND,
                **self.scope,
                "username": username,
                "sub": sub,
            },
        )
        # link(), unlike replace(), atomically fails if a file or symlink won
        # the destination race. Keep staging evidence if any later step fails.
        os.link(
            staging_name, self.name,
            src_dir_fd=self.directory_fd, dst_dir_fd=self.directory_fd,
            follow_symlinks=False,
        )
        os.fsync(self.directory_fd)
        os.unlink(staging_name, dir_fd=self.directory_fd)
        os.unlink(self.pending_name, dir_fd=self.directory_fd)
        os.fsync(self.directory_fd)

    def close(self) -> None:
        if self.directory_fd is not None:
            os.close(self.directory_fd)
            self.directory_fd = None

    def __enter__(self) -> "ReceiptReservation":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


def load_receipt(receipt_path: str) -> dict[str, Any]:
    """Read private regular-file evidence without following a leaf symlink."""
    fd = os.open(receipt_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or info.st_size > _MAX_RECEIPT_BYTES
        ):
            raise ReceiptError("Receipt must be a private, owned, regular file.")
        receipt = json.loads(stream.read(_MAX_RECEIPT_BYTES + 1))
    if (
        not isinstance(receipt, dict)
        or set(receipt) != _RECEIPT_KEYS
        or type(receipt["version"]) is not int
        or receipt["version"] != 1
        or receipt["kind"] != _RECEIPT_KIND
        or any(
            not isinstance(receipt[key], str) or not receipt[key].strip()
            for key in _RECEIPT_KEYS - {"version"}
        )
    ):
        raise ReceiptError("Receipt is not complete creation evidence.")
    return receipt


def plan(cfg: BootstrapConfig) -> list[dict[str, Any]]:
    """Describe conditional calls without exposing the environment password."""
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
                "ForceAliasCreation": False,
                "MessageAction": "SUPPRESS",
                "DesiredDeliveryMediums": ["EMAIL"],
            },
        },
        {
            "service": "cognito-idp",
            "operation": "AdminSetUserPassword",
            "requires": "successful create and atomic private identity receipt",
            "params": {
                "UserPoolId": cfg.pool_id,
                "Username": "<username returned by AdminCreateUser>",
                "Password": "***redacted***",
                "Permanent": True,
            },
        },
    ]


def bootstrap(
    cfg: BootstrapConfig,
    *,
    dry_run: bool,
    receipt_path: Optional[str] = None,
    client: Any = None,
) -> int:
    """Create a new identity; never reset or adopt an existing user."""
    assert_non_production_pool(cfg.pool_id)

    steps = plan(cfg)
    if dry_run:
        print(
            "[bootstrap_cognito_dev_pool] DRY RUN — conditional call plan; "
            "no AWS client or files are created. Live creation requires an "
            "unused --receipt path:"
        )
        print(json.dumps(steps, indent=2))
        return EXIT_OK

    if not receipt_path:
        print("[bootstrap_cognito_dev_pool] Live creation requires --receipt.", file=sys.stderr)
        return EXIT_MISSING_CONFIG

    create_attempted = False
    try:
        with ReceiptReservation(receipt_path, cfg) as reservation:
            try:
                if client is None:
                    import boto3

                    client = boto3.client("cognito-idp", region_name=cfg.region)
                create_attempted = True
                response = client.admin_create_user(**steps[0]["params"])
            except Exception as exc:
                if (
                    is_service_error(exc, "UsernameExistsException")
                    or is_service_error(exc, "AliasExistsException")
                ):
                    message = "Existing user or alias refused; no password was changed."
                else:
                    message = "Create failed or its outcome is uncertain; no password was set."
                print(
                    f"[bootstrap_cognito_dev_pool] {message} "
                    "Keep the private .pending evidence for reconciliation.",
                    file=sys.stderr,
                )
                return EXIT_AWS_ERROR

            try:
                username, sub = user_identity(response.get("User"), "Attributes")
                reservation.publish(username, sub)
            except (OSError, ValueError, AttributeError, TypeError):
                print(
                    "[bootstrap_cognito_dev_pool] Create returned, but its identity "
                    "receipt could not be published. No password was set. Keep the "
                    "receipt directory, including .pending and .created evidence.",
                    file=sys.stderr,
                )
                return EXIT_RECEIPT_ERROR

            try:
                client.admin_set_user_password(
                    UserPoolId=cfg.pool_id,
                    Username=username,
                    Password=cfg.password,
                    Permanent=True,
                )
            except Exception:
                # AWS/transport error text can contain request data. Do not echo it.
                print(
                    "[bootstrap_cognito_dev_pool] Password setup failed or its "
                    "outcome is uncertain. The identity receipt is retained; "
                    "use receipt-verified teardown to clean up.",
                    file=sys.stderr,
                )
                return EXIT_AWS_ERROR
    except (OSError, ValueError):
        print(
            "[bootstrap_cognito_dev_pool] Receipt file operation failed. "
            "Retain the receipt directory and its evidence. "
            + (
                "Use an unused receipt path in an existing directory; "
                "no AWS create was attempted."
                if not create_attempted else
                "A create was attempted; reconcile the retained evidence."
            ),
            file=sys.stderr,
        )
        return EXIT_RECEIPT_ERROR

    print("[bootstrap_cognito_dev_pool] Created user; password configured; identity receipt retained.")
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
        "--receipt",
        default=None,
        help=(
            "Required for live creation: unused path for a private, nonsecret "
            "identity receipt. No credentials are written."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    cfg = BootstrapConfig.from_env(os.environ)
    return bootstrap(cfg, dry_run=args.dry_run, receipt_path=args.receipt)


if __name__ == "__main__":  # pragma: no cover — CLI entrypoint
    raise SystemExit(main())
