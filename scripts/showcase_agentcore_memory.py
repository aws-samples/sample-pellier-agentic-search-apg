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

`strategies` is Lab 3's look at all four strategies. It reads, and never
writes, every record AgentCore made from that one conversation: preferences,
facts, the session summary, the episode and its reflection. Each strategy says
whether its records follow the customer into new conversations and whether a
Pellier turn reads them. `--versus` runs the same reads for a second shopper:

    python3 scripts/showcase_agentcore_memory.py strategies --persona theo --versus marco
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

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


FOLLOWS = "follows the customer into every new conversation"
STAYS = "stays with the conversation it came from"
NOT_READ = "kept; no Pellier turn reads it"
# Each strategy as printed: its namespace kind, how far its records reach, and
# whether a Pellier turn reads them. Only preferences go ahead of a prompt.
STRATEGY_ROWS = (
    ("preferences", "USER_PREFERENCE", FOLLOWS,
     "read into every signed-in turn; the Router step names these ids"),
    ("facts", "SEMANTIC", FOLLOWS, NOT_READ),
    ("summary", "SUMMARIZATION", STAYS, NOT_READ),
    ("episodic", "EPISODIC", STAYS, NOT_READ),
    ("reflection", "EPISODIC reflection", FOLLOWS, NOT_READ),
)
_LINE_TEXT = 90


def _cut(text: str) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= _LINE_TEXT else text[: _LINE_TEXT - 3] + "..."


def _json_field(raw: str, key: str) -> str:
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return ""
    return str(parsed.get(key) or "") if isinstance(parsed, dict) else ""


def record_text(record: dict, kind: str) -> str:
    """What one record says, on one line: a preference, a fact, a topic, an episode."""
    from services.memory_records import record_view

    view = record_view(record, "episodic" if kind == "reflection" else kind)
    if kind == "summary":
        text = re.sub(r'<topic name="([^"]*)">', r"\1: ", view["raw"])
        return _cut(re.sub(r"<[^>]+>", " ", text))
    if kind == "episodic" and view["episode"]:
        episode = view["episode"]
        return _cut(f"goal met: {episode['assessment']}. {episode['intent']}")
    if kind == "reflection":
        return _cut(_json_field(view["raw"], "title") or view["content"])
    return _cut(view["content"])


def _records(data: Any, memory_id: str, strategy_id: Optional[str], path: str) -> list:
    from services.memory_contract import record_matches

    if not strategy_id:
        return []
    found: list = []
    for page in data.get_paginator("list_memory_records").paginate(
        memoryId=memory_id, namespace=path, memoryStrategyId=strategy_id,
    ):
        found.extend(r for r in page.get("memoryRecordSummaries", [])
                     if record_matches(r, strategy_id, path))
    return found


def strategy_records(control: Any, data: Any, memory_id: str, actor: str) -> dict:
    """Everything AgentCore Memory holds for ``actor``'s provisioning conversation.

    The conversation (session ``prefseed``) and, per strategy, the records in
    that actor's namespace, plus the episodic reflection. Nothing here writes.
    """
    from seed_agentcore_memory import SEED_SESSION
    from services.memory_contract import REFLECTION_NAMESPACE, STRATEGIES, namespace

    resource = control.get_memory(memoryId=memory_id)["memory"]
    ids = {s.get("name"): s.get("strategyId") for s in resource.get("strategies", [])}
    events: list = []
    for page in data.get_paginator("list_events").paginate(
        memoryId=memory_id, actorId=actor, sessionId=SEED_SESSION, includePayloads=True,
    ):
        events.extend(page.get("events", []))
    events.sort(key=lambda event: (str(event.get("eventTimestamp", "")), str(event.get("eventId"))))
    strategies = {}
    for kind, *_rest in STRATEGY_ROWS:
        name = STRATEGIES["episodic" if kind == "reflection" else kind][1]
        path = (REFLECTION_NAMESPACE.format(actorId=actor) if kind == "reflection"
                else namespace(kind, actor, SEED_SESSION))
        strategies[kind] = {"name": name, "namespace": path,
                            "records": _records(data, memory_id, ids.get(name), path)}
    return {"actor": actor, "session": SEED_SESSION, "events": events, "strategies": strategies}


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


def render_strategies(found: dict, memory_id: str, versus: Optional[dict] = None) -> str:
    """The four strategies for one shopper, then the same reads for a second one."""
    lines = [f"AgentCore Memory {memory_id}",
             f"{found['actor']}'s first conversation (session {found['session']}): "
             f"{_plural(len(found['events']), 'event')}"]
    lines += [f"  {e.get('eventId')}  {_cut(_text(e))}" for e in found["events"]]
    for kind, strategy_type, reach, use in STRATEGY_ROWS:
        strategy = found["strategies"][kind]
        records = strategy["records"]
        lines += ["", f"{strategy_type} ({strategy['name']}): {_plural(len(records), 'record')}",
                  f"  {strategy['namespace']}  {reach}", f"  Pellier: {use}"]
        lines += [f"  {r.get('memoryRecordId')}  {record_text(r, kind)}" for r in records]
        if not records:
            lines.append("  none yet: AgentCore extracts after the conversation; run this again")
    if versus is not None:
        lines += ["", *_versus_lines(found["actor"], versus)]
    return "\n".join(lines)


def _versus_lines(actor: str, versus: dict) -> list:
    """The same reads for a second shopper, and the preferences their turns are given."""
    counts = {kind: len(versus["strategies"][kind]["records"]) for kind, *_ in STRATEGY_ROWS}
    other = versus["actor"]
    if not any(counts.values()):
        return [f"{other}, the same five reads: 0 records. {other}'s turns are given no "
                f"remembered preference, and none of {actor}'s: every read is keyed by the "
                "signed-in customer."]
    held = ", ".join(f"{counts[kind]} {strategy_type}" for kind, strategy_type, *_ in STRATEGY_ROWS)
    preferences = versus["strategies"]["preferences"]["records"]
    return [f"{other}, the same five reads: {held}, all under {other}'s own namespaces. "
            f"None of {actor}'s records are among them. {other}'s turns are given:",
            *(f"  {r.get('memoryRecordId')}  {record_text(r, 'preferences')}"
              for r in preferences)]


def _strategies(persona: str, versus: Optional[str]) -> int:
    """Print every strategy's records for one shopper; exit 0 when Memory answered."""
    import boto3
    from gateway_client import _load_env

    _load_env()
    from config import settings
    from services.memory_showcase import AWS_CONFIG

    memory_id = settings.AGENTCORE_MEMORY_ID
    if not memory_id:
        print("Memory showcase unavailable: AGENTCORE_MEMORY_ID is not configured",
              file=sys.stderr)
        return 1
    region = settings.aws_region_resolved
    control = boto3.client("bedrock-agentcore-control", region_name=region, config=AWS_CONFIG)
    data = boto3.client("bedrock-agentcore", region_name=region, config=AWS_CONFIG)
    found = strategy_records(control, data, memory_id, "CUST-" + persona.upper())
    other = (strategy_records(control, data, memory_id, "CUST-" + versus.upper())
             if versus else None)
    print(render_strategies(found, memory_id, other))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",
                        choices=("learn", "status", "recall", "finish", "provisioned", "strategies"))
    parser.add_argument("--persona", choices=("marco", "anna", "theo", "jessica"), default="marco")
    parser.add_argument("--versus", choices=("marco", "anna", "theo", "jessica"),
                        help="strategies only: run the same reads for a second shopper")
    args = parser.parse_args()
    if args.command in ("provisioned", "strategies"):
        try:
            if args.command == "strategies":
                return _strategies(args.persona, args.versus)
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
