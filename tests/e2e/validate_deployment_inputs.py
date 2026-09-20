#!/usr/bin/env python3
"""Fail before sending test credentials to an unapproved deployment.

The protected ``workshop-e2e`` GitHub environment owns the allowed origin and
dedicated identities. This check does not provision or delete identities.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Mapping
from urllib.parse import urlsplit


REQUIRED = (
    "E2E_BASE_URL",
    "E2E_ALLOWED_BASE_URL",
    "E2E_BOUNDARY_RUN",
    "E2E_TEST_USER_EMAIL",
    "E2E_TEST_USER_PASSWORD",
    "E2E_GOVERN_USERNAME",
    "E2E_GOVERN_PASSWORD",
    "E2E_OPERATOR_USERNAME",
    "E2E_OPERATOR_PASSWORD",
)


def _origin(value: str) -> tuple[str, str, int]:
    try:
        parsed = urlsplit(value)
        if (
            value != value.strip()
            or any(ord(char) < 32 for char in value)
            or "\\" in value
            or "?" in value
            or "#" in value
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError
        port = parsed.port if parsed.port is not None else 443
        if port == 0:
            raise ValueError
        return parsed.scheme, parsed.hostname, port
    except ValueError:
        raise ValueError(
            "Deployment URLs must be HTTPS origins without credentials, paths, "
            "queries or fragments."
        ) from None


def validate(env: Mapping[str, str]) -> None:
    missing = [name for name in REQUIRED if not env.get(name, "").strip()]
    if missing:
        raise ValueError("Missing required live E2E inputs: " + ", ".join(missing))
    if _origin(env["E2E_BASE_URL"]) != _origin(env["E2E_ALLOWED_BASE_URL"]):
        raise ValueError(
            "The requested deployment does not match the protected "
            "environment's approved origin."
        )
    if env["E2E_BASE_URL"].endswith("/"):
        raise ValueError("E2E_BASE_URL must omit the trailing slash.")
    if not re.fullmatch(r"boundaries-[a-f0-9]{32}", env["E2E_BOUNDARY_RUN"]):
        raise ValueError("E2E_BOUNDARY_RUN must identify a completed boundary proof run.")


def main() -> int:
    try:
        validate(os.environ)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("Approved deployment and all required live E2E inputs are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
