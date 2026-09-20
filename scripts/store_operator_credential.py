#!/usr/bin/env python3
"""Keep the generated workshop staff credential in the managed test secret.

The bootstrap, health gate, and Lab 4 proof must use the same credential source.
Values arrive through the process environment and are never printed.
"""
from __future__ import annotations

import json
import os


def store(client, secret_id: str, username: str, password: str) -> None:
    if not all((secret_id, username, password)):
        raise ValueError("The workshop secret, staff username, and password are required")
    payload = json.loads(client.get_secret_value(SecretId=secret_id)["SecretString"])
    users = payload.get("users")
    if not isinstance(users, list) or not all(isinstance(user, dict) for user in users):
        raise ValueError("The workshop credential secret must contain a users array")
    payload["users"] = [
        user for user in users
        if str(user.get("username", "")).casefold() != username.casefold()
    ] + [{"username": username, "password": password}]
    client.put_secret_value(SecretId=secret_id, SecretString=json.dumps(payload))


if __name__ == "__main__":
    import boto3
    try:
        store(
            boto3.client("secretsmanager", region_name=os.environ["AWS_REGION"]),
            os.environ["COGNITO_TEST_CREDENTIALS_SECRET_ARN"],
            os.environ["OPERATOR_USERNAME"], os.environ["OPERATOR_PASSWORD"],
        )
    except Exception as exc:
        raise SystemExit(f"Could not store workshop staff credential: {type(exc).__name__}") from None
