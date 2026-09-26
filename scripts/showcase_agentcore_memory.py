#!/usr/bin/env python3
"""Run the workshop Memory exercise with real Cognito, Memory and Runtime.

Run from the repository root with pellier/backend/.venv/bin/python.
No long-term records are seeded. `learn` writes a visible, scripted conversation;
`recall` retrieves extracted records and invokes the live product agent.
`recall` requires all four record types, including a completed source episode.
`finish` closes the recommendation conversation so its later episode can form.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pellier" / "backend"))
sys.path.insert(0, str(ROOT / "scripts" / "deploy"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("learn", "status", "recall", "finish"))
    parser.add_argument("--persona", choices=("marco", "anna", "theo", "jessica"), default="marco")
    args = parser.parse_args()
    from gateway_initiate_return import _load_env, _token_from_cognito
    _load_env()
    import boto3
    from services.memory_showcase import AWS_CONFIG, MemoryShowcase
    from services.turn_identity import customer_id_for_verified_username
    from config import settings

    try:
        showcase = MemoryShowcase()
        token = _token_from_cognito(args.persona)
        # Resolve identity with Cognito, never by decoding an unverified JWT.
        user = boto3.client("cognito-idp", region_name=settings.aws_region_resolved, config=AWS_CONFIG).get_user(AccessToken=token)
        sub = next(a["Value"] for a in user["UserAttributes"] if a["Name"] == "sub")
        customer = customer_id_for_verified_username(user["Username"])
        if customer != "CUST-" + args.persona.upper():
            raise RuntimeError("Signed-in principal does not match the selected persona")
        if args.command == "learn":
            result = showcase.learn(sub, args.persona)
        elif args.command == "recall":
            result = asyncio.run(showcase.recall(sub, token, customer))
        elif args.command == "finish":
            result = showcase.finish(sub)
        else:
            result = showcase.inspect(sub)
        print(json.dumps(result, indent=2, default=str))
        return 0
    except Exception as exc:
        # SDK exceptions can carry request content. Keep credentials and prompts
        # out of failure output; explicit local contract failures are safe.
        detail = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__
        print(f"Memory showcase unavailable: {detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
