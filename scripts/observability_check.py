#!/usr/bin/env python3
"""Prove that the steps outside AgentCore's trace are observable in CloudWatch.

AgentCore writes a span for each managed step of a Gateway call
(scripts/trace_agentcore_calls.py). Two steps sit outside that trace: the app on
this instance, which exports its Router's span and its agents' spans, and the database,
which no span describes because spans never carry SQL. This check reads the
evidence for both, and never writes:

    O1  App spans           a turn's routing span, with its agents' spans, is in
                            aws/spans
    O2  Database Insights   the cluster runs Advanced mode and records the
                            queries that reached Aurora, with the top SQL by
                            load when a statement was sampled
    O3  PostgreSQL log      a write that row-level security refused is in the
                            cluster's postgresql log group

Run it after a turn in Ask Pellier and after python3 scripts/lab4_rls_check.py:

    python3 scripts/observability_check.py
    python3 scripts/observability_check.py --minutes 120

Spans reach CloudWatch about ten seconds after a turn; Database Insights'
counters and the exported log, about a minute after the statement.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pellier" / "backend"))
sys.path.insert(0, str(ROOT / "scripts" / "deploy"))
sys.path.insert(0, str(ROOT / "scripts"))

from workshop_check import (CONTRADICTED, NOT_YET, PROVED, UNCHECKED,  # noqa: E402
                            Finding, render)

SPANS_GROUP = "aws/spans"
TURN_ATTR = "pellier.turn_id"  # services/evidence_spans.py ATTR_TURN_ID
RLS_REFUSAL = "violates row-level security policy"
SQL_DIMENSION = "db.sql_tokenized.statement"
QUERIES_FINISHED = "db.SQL.queries_finished"


def aws_code(exc: Exception) -> str:
    """The AWS error code, or the exception's type when there is none."""
    return getattr(exc, "response", {}).get("Error", {}).get("Code", type(exc).__name__)


def cluster_id(cluster_arn: str) -> str:
    """The cluster identifier at the end of an RDS cluster ARN."""
    return cluster_arn.rsplit(":", 1)[-1]


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


def _events(logs: Any, group: str, start_ms: int, pattern: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for page in logs.get_paginator("filter_log_events").paginate(
        logGroupName=group, startTime=start_ms, filterPattern=pattern,
    ):
        events.extend(page.get("events", []))
    return events


def app_spans(logs: Any, start_ms: int, minutes: int) -> Finding:
    """O1: a turn's spans from the app, read back from Transaction Search.

    Only the app's chat path opens the ``routing`` span, so a turn counts once its
    routing span arrives; the Strands agent spans that carry the same turn id
    (invoke_agent, execute_tool, chat) are listed as its evidence.
    """
    expected = (f"the routing span of a turn, with its agents' spans, carrying {TURN_ATTR}, "
                f"in {SPANS_GROUP} within the last {minutes} minutes")
    try:
        events = _events(logs, SPANS_GROUP, start_ms, f'"{TURN_ATTR}"')
    except Exception as exc:  # noqa: BLE001 - the finding says which read failed
        return Finding("O1", "App spans in CloudWatch", UNCHECKED, expected,
                       f"could not read {SPANS_GROUP}: {aws_code(exc)}")
    spans = []
    for event in events:
        try:
            span = json.loads(event["message"])
        except (KeyError, ValueError):
            continue
        turn = (span.get("attributes") or {}).get(TURN_ATTR)
        if turn:
            spans.append((int(span.get("startTimeUnixNano") or 0), str(span.get("name", "")),
                          str(turn)))
    spans.sort()
    routed = [(start, turn) for start, name, turn in spans if name == "routing"]
    if not routed:
        return Finding("O1", "App spans in CloudWatch", NOT_YET, expected,
                       "no routing span from the app yet",
                       next_step="send a request in Ask Pellier, wait about ten seconds and "
                                 "run this again; if it stays empty, grep 'Failed to export span "
                                 "batch' /tmp/pellier/uvicorn.log: a 403 means this instance's "
                                 "role cannot write traces")
    turns = {turn for _, turn in routed}
    _, newest = routed[-1]
    names = list(dict.fromkeys(name for _, name, turn in spans if turn == newest))
    in_turns = sum(1 for _, _, turn in spans if turn in turns)
    return Finding("O1", "App spans in CloudWatch", PROVED, expected,
                   f"{_plural(in_turns, 'span')} across {_plural(len(turns), 'routed turn')}",
                   [f"newest turn {newest}: {', '.join(names)}"])


def _writer(rds: Any, cluster: Dict[str, Any]) -> Dict[str, Any]:
    members = cluster.get("DBClusterMembers") or []
    writer = next((m for m in members if m.get("IsClusterWriter")), members[0] if members else None)
    if writer is None:
        raise LookupError("the cluster has no instances")
    found = rds.describe_db_instances(DBInstanceIdentifier=writer["DBInstanceIdentifier"])
    return found["DBInstances"][0]


def busy_minutes(pi: Any, resource_id: str, minutes: int, now: datetime) -> Tuple[int, int]:
    """Minutes in the window in which Aurora finished queries, and the minutes reported.

    Database Insights collects this counter once a minute from every finished
    query, so a quiet cluster still shows its traffic; database load is sampled
    once a second and misses statements that finish in a few milliseconds.
    """
    found = pi.get_resource_metrics(
        ServiceType="RDS", Identifier=resource_id, StartTime=now - timedelta(minutes=minutes),
        EndTime=now, PeriodInSeconds=60, MetricQueries=[{"Metric": f"{QUERIES_FINISHED}.avg"}])
    points = [point for series in found.get("MetricList", [])
              for point in series.get("DataPoints", []) if "Value" in point]
    return sum(1 for point in points if point["Value"] > 0), len(points)


def top_sql(pi: Any, resource_id: str, minutes: int, now: datetime) -> List[str]:
    """The statements carrying the most database load in the window, tokenized."""
    found = pi.describe_dimension_keys(
        ServiceType="RDS", Identifier=resource_id, StartTime=now - timedelta(minutes=minutes),
        EndTime=now, Metric="db.load.avg",
        GroupBy={"Group": "db.sql_tokenized", "Dimensions": [SQL_DIMENSION], "Limit": 3})
    statements = []
    for key in found.get("Keys", []):
        statement = " ".join(str((key.get("Dimensions") or {}).get(SQL_DIMENSION, "")).split())
        if statement:
            statements.append(statement if len(statement) <= 90 else statement[:87] + "...")
    return statements


def database_insights(rds: Any, pi: Any, cluster: Dict[str, Any], minutes: int,
                      now: datetime) -> Finding:
    """O2: Database Insights in Advanced mode, recording the queries that reached Aurora."""
    expected = ("Database Insights in advanced mode, with Performance Insights, recording "
                f"the queries Aurora finished in the last {minutes} minutes")
    mode = cluster.get("DatabaseInsightsMode") or "not set"
    try:
        writer = _writer(rds, cluster)
    except Exception as exc:  # noqa: BLE001 - the finding says which read failed
        return Finding("O2", "Database Insights on Aurora", UNCHECKED, expected,
                       f"DatabaseInsightsMode {mode}; could not describe its writer: "
                       f"{aws_code(exc)}")
    # An Aurora cluster may report Performance Insights only on its instances.
    enabled = bool(cluster.get("PerformanceInsightsEnabled",
                               writer.get("PerformanceInsightsEnabled")))
    retention = cluster.get("PerformanceInsightsRetentionPeriod",
                            writer.get("PerformanceInsightsRetentionPeriod", "none"))
    setting = (f"DatabaseInsightsMode {mode}, Performance Insights "
               + (f"on, retention {retention} days" if enabled else "off"))
    if mode != "advanced" or not enabled:
        return Finding("O2", "Database Insights on Aurora", CONTRADICTED, expected, setting,
                       next_step="this event's database stack predates Database Insights; "
                                 "provision from the current template")
    try:
        busy, reported = busy_minutes(pi, writer["DbiResourceId"], minutes, now)
        statements = top_sql(pi, writer["DbiResourceId"], minutes, now)
    except Exception as exc:  # noqa: BLE001 - the setting is proved; the read is not
        return Finding("O2", "Database Insights on Aurora", UNCHECKED, expected,
                       f"{setting}; could not read its metrics: {aws_code(exc)}")
    if not busy:
        return Finding("O2", "Database Insights on Aurora", NOT_YET, expected,
                       f"{setting}; no finished queries recorded in the window yet",
                       next_step="send a request in Ask Pellier, wait about a minute and run "
                                 "this again")
    evidence = [f"queries finished in {busy} of the {reported} minutes reported "
                f"({QUERIES_FINISHED})"]
    evidence += ([f"top SQL by load: {s}" for s in statements]
                 or ["top SQL by load: no statement sampled in the window"])
    return Finding("O2", "Database Insights on Aurora", PROVED, expected, setting, evidence)


def postgresql_log(logs: Any, cluster: Dict[str, Any], start_ms: int, minutes: int) -> Finding:
    """O3: a refused write in the cluster's PostgreSQL log, exported to CloudWatch."""
    group = f"/aws/rds/cluster/{cluster['DBClusterIdentifier']}/postgresql"
    expected = (f"an ERROR '{RLS_REFUSAL}' in {group} within the last {minutes} minutes; "
                "the log line does not print the SQLSTATE")
    if "postgresql" not in (cluster.get("EnabledCloudwatchLogsExports") or []):
        return Finding("O3", "Refused writes in the PostgreSQL log", CONTRADICTED, expected,
                       "the cluster does not export its postgresql log to CloudWatch",
                       next_step="this event's database stack predates the log export; "
                                 "provision from the current template")
    try:
        events = _events(logs, group, start_ms, f'"{RLS_REFUSAL}"')
    except Exception as exc:  # noqa: BLE001 - a group appears with its first exported line
        code = aws_code(exc)
        if code != "ResourceNotFoundException":
            return Finding("O3", "Refused writes in the PostgreSQL log", UNCHECKED, expected,
                           f"could not read {group}: {code}")
        events = []
    if not events:
        return Finding("O3", "Refused writes in the PostgreSQL log", NOT_YET, expected,
                       "no refused write in the window",
                       next_step="run python3 scripts/lab4_rls_check.py, wait about a minute "
                                 "and run this again")
    newest = max(events, key=lambda e: int(e.get("timestamp") or 0))
    when = datetime.fromtimestamp(int(newest.get("timestamp") or 0) / 1000,
                                  tz=timezone.utc).astimezone().strftime("%H:%M:%S")
    line = ((newest.get("message") or "").strip().splitlines() or [""])[0]
    detail = line[line.find("ERROR"):] if "ERROR" in line else line
    return Finding("O3", "Refused writes in the PostgreSQL log", PROVED, expected,
                   f"{_plural(len(events), 'refused write')} logged", [f"{when}  {detail}"])


def check(logs: Any, rds: Any, pi: Any, cluster_arn: str, minutes: int,
          now: Optional[datetime] = None) -> List[Finding]:
    """The three findings, in order. Reads only."""
    now = now or datetime.now(timezone.utc)
    start_ms = int((now.timestamp() - minutes * 60) * 1000)
    findings = [app_spans(logs, start_ms, minutes)]
    try:
        cluster = rds.describe_db_clusters(DBClusterIdentifier=cluster_arn)["DBClusters"][0]
    except Exception as exc:  # noqa: BLE001 - both database findings say why
        observed = f"could not describe {cluster_id(cluster_arn) or 'the cluster'}: {aws_code(exc)}"
        return findings + [
            Finding("O2", "Database Insights on Aurora", UNCHECKED,
                    "Database Insights in advanced mode", observed),
            Finding("O3", "Refused writes in the PostgreSQL log", UNCHECKED,
                    "a refused write in the exported PostgreSQL log", observed)]
    return findings + [database_insights(rds, pi, cluster, minutes, now),
                       postgresql_log(logs, cluster, start_ms, minutes)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--minutes", type=int, default=60, help="how far back to read")
    args = parser.parse_args()

    import boto3
    from gateway_client import _load_env

    _load_env()
    cluster_arn = os.environ.get("DB_CLUSTER_ARN", "")
    if cluster_arn.count(":") < 6:
        print("DB_CLUSTER_ARN is not set in pellier/backend/.env or the environment.",
              file=sys.stderr)
        return 1
    region = cluster_arn.split(":")[3]  # the cluster's own Region, where its evidence lives
    findings = check(boto3.client("logs", region_name=region),
                     boto3.client("rds", region_name=region),
                     boto3.client("pi", region_name=region), cluster_arn, args.minutes)
    print(f"Observability outside AgentCore's trace, last {args.minutes} minutes "
          f"({time.strftime('%H:%M:%S')})")
    for finding in findings:
        print()
        print(render(finding))
    proved = sum(f.state == PROVED for f in findings)
    print()
    print("Observability check passed" if proved == len(findings)
          else f"Observability check: {proved} of {len(findings)} proved")
    return 0 if proved == len(findings) else 1


if __name__ == "__main__":
    raise SystemExit(main())
