#!/usr/bin/env python3
"""Run the workshop Memory exercise with real Cognito, Memory and Runtime.

Run from the repository root with pellier/backend/.venv/bin/python.
No long-term records are seeded. `learn` writes a visible, scripted conversation;
`recall` retrieves extracted records and invokes the live product agent.
`recall` requires all four record types, including a completed source episode.
`finish` closes the recommendation conversation so its later episode can form.

`provisioned` is Lab 3's memory check. It needs no sign-in: it reads the
conversation provisioning wrote for the persona (session `prefseed`) and the
user-preference records AgentCore extracted from it, and prints Expected,
Observed and Evidence with the source event ids beside the record ids:

    python3 scripts/showcase_agentcore_memory.py provisioned --persona theo
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
sys.path.insert(0, str(ROOT / "scripts"))


def _customer_for(database_url: str, username: str) -> str:
    """The customer whose Cognito username this is, from pellier.customers."""
    import psycopg

    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            "SELECT id FROM pellier.customers WHERE cognito_username = %s",
            (str(username).casefold(),),
        ).fetchone()
    return str(row[0]) if row else ""


def _text(event_or_record: dict) -> str:
    """The first text an event or a record carries, cut to one readable line."""
    content = event_or_record.get("content") or {}
    if isinstance(content.get("text"), str):
        return content["text"][:90]
    for payload in event_or_record.get("payload") or []:
        text = ((payload.get("conversational") or {}).get("content") or {}).get("text")
        if isinstance(text, str):
            return text[:90]
    return ""


def provisioned_finding(seeded: dict, memory_id: str):
    """Lab 3's memory finding from ``seed_agentcore_memory.seeded_memory``."""
    import workshop_check as check

    expected = ("the conversation provisioning recorded for this customer, and at least one "
                "user-preference record AgentCore extracted from it")
    events, records = seeded["events"], seeded["records"]
    evidence = [f"AgentCore Memory {memory_id}, actor {seeded['actor']}, "
                f"session {seeded['session']}"]
    evidence += [f"source event {e.get('eventId')}: {_text(e)}" for e in events]
    evidence += [f"{seeded['strategy']} record {r.get('memoryRecordId')}: {_text(r)}"
                 for r in records]
    evidence.append(f"namespace {seeded['namespace']}")
    observed = f"{len(events)} source event(s), {len(records)} preference record(s)"
    if not events:
        return check.Finding("3B", "the provisioning conversation is remembered",
                             check.CONTRADICTED, expected, observed, evidence,
                             "the provisioning conversation is missing; rerun "
                             "scripts/deploy/seed_agentcore_memory.py.")
    if not records:
        return check.Finding("3B", "the provisioning conversation is remembered", check.NOT_YET,
                             expected, observed, evidence,
                             "extraction runs after the conversation; run this again in a "
                             "minute.")
    return check.Finding("3B", "the provisioning conversation is remembered", check.PROVED,
                         expected, observed, evidence)


def _provisioned(persona: str) -> int:
    """Print Lab 3's memory finding; exit 0 only when it is proved."""
    import boto3
    import workshop_check as check
    from gateway_client import _load_env
    from seed_agentcore_memory import seeded_memory

    _load_env()
    from config import settings
    from services.memory_showcase import AWS_CONFIG

    memory_id = settings.AGENTCORE_MEMORY_ID
    if not memory_id:
        print("Memory showcase unavailable: AGENTCORE_MEMORY_ID is not configured",
              file=sys.stderr)
        return 1
    region = settings.aws_region_resolved
    seeded = seeded_memory(
        boto3.client("bedrock-agentcore-control", region_name=region, config=AWS_CONFIG),
        boto3.client("bedrock-agentcore", region_name=region, config=AWS_CONFIG),
        memory_id, "CUST-" + persona.upper(),
    )
    finding = provisioned_finding(seeded, memory_id)
    print(check.render(finding))
    return 0 if finding.state == check.PROVED else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("learn", "status", "recall", "finish", "provisioned"))
    parser.add_argument("--persona", choices=("marco", "anna", "theo", "jessica"), default="marco")
    args = parser.parse_args()
    if args.command == "provisioned":
        try:
            return _provisioned(args.persona)
        except Exception as exc:
            detail = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__
            print(f"Memory showcase unavailable: {detail}", file=sys.stderr)
            return 1
    from gateway_client import _load_env, _token_from_cognito
    _load_env()
    import boto3
    from services.memory_showcase import AWS_CONFIG, MemoryShowcase
    from config import settings

    try:
        showcase = MemoryShowcase()
        token = _token_from_cognito(args.persona)
        # Resolve identity with Cognito, never by decoding an unverified JWT.
        user = boto3.client("cognito-idp", region_name=settings.aws_region_resolved, config=AWS_CONFIG).get_user(AccessToken=token)
        sub = next(a["Value"] for a in user["UserAttributes"] if a["Name"] == "sub")
        customer = _customer_for(settings.database_url, user["Username"])
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
