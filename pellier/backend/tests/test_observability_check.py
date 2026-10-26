"""The observability check: the app's spans, Database Insights and the PostgreSQL log.

Each fake returns what the live service returns: span JSON in ``aws/spans``,
the RDS cluster and instance descriptions, Performance Insights dimension keys,
and PostgreSQL log lines exported to CloudWatch Logs. A finding is PROVED only
when the evidence itself is there; a cluster without the settings is
CONTRADICTED, and evidence that has not arrived yet is NOT YET.
"""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
obs = importlib.import_module("observability_check")
workshop_check = importlib.import_module("workshop_check")

NOW = datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)
CREATED = NOW - timedelta(hours=6)
CLUSTER_ARN = "arn:aws:rds:us-east-1:123456789012:cluster:pellier-cluster-ws1"
GROUP = "/aws/rds/cluster/pellier-cluster-ws1/postgresql"
REFUSAL = ("2026-10-09 14:58:02 UTC:10.0.1.5(51234):pellier_agent@pellier:[4242]:ERROR:  new "
           "row violates row-level security policy for table \"support_tickets\"")


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


@pytest.fixture(autouse=True)
def _no_reset_points(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Each test starts with no lab reset, whatever this checkout's .local holds."""
    path = tmp_path / "lab-reset-points.json"
    monkeypatch.setenv(workshop_check.RESET_POINTS_ENV, str(path))
    return path


class _Error(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class _Logs:
    """FilterLogEvents by group and start time, matching the quoted term as the service does."""

    def __init__(self, groups: Dict[str, List[Dict[str, Any]]],
                 missing: Optional[str] = None) -> None:
        self.groups, self.missing, self.calls = groups, missing, []

    def get_paginator(self, operation: str) -> Any:
        assert operation == "filter_log_events"
        outer = self

        class _Paginator:
            def paginate(self, **kwargs: Any):
                outer.calls.append(kwargs)
                group = kwargs["logGroupName"]
                if outer.missing and group == outer.missing:
                    raise _Error(outer.missing_code)
                term = kwargs["filterPattern"].strip('"')
                start = kwargs["startTime"]
                yield {"events": [e for e in outer.groups.get(group, [])
                                  if term in e["message"] and e.get("timestamp", start) >= start]}

        return _Paginator()

    missing_code = "ResourceNotFoundException"


def _span(name: str, turn: Optional[str], start: int,
          rail: str = "gateway-mcp") -> Dict[str, Any]:
    attrs = {"pellier.turn_id": turn, "pellier.rail": rail} if turn else {}
    return {"message": json.dumps({"name": name, "startTimeUnixNano": str(start),
                                   "attributes": attrs})}


def _cluster(mode: str = "advanced", exports: Optional[List[str]] = None,
             pi_on_cluster: bool = True) -> Dict[str, Any]:
    cluster = {"DBClusterIdentifier": "pellier-cluster-ws1", "DatabaseInsightsMode": mode,
               "ClusterCreateTime": CREATED,
               "EnabledCloudwatchLogsExports": ["postgresql"] if exports is None else exports,
               "DBClusterMembers": [{"DBInstanceIdentifier": "pellier-writer-ws1",
                                     "IsClusterWriter": True}]}
    if pi_on_cluster:
        cluster.update(PerformanceInsightsEnabled=True, PerformanceInsightsRetentionPeriod=465)
    return cluster


class _Rds:
    def __init__(self, cluster: Optional[Dict[str, Any]], instance_pi: bool = True) -> None:
        self.cluster, self.instance_pi = cluster, instance_pi

    def describe_db_clusters(self, DBClusterIdentifier: str) -> Dict[str, Any]:  # noqa: N803
        if self.cluster is None:
            raise _Error("AccessDenied")
        assert DBClusterIdentifier == CLUSTER_ARN
        return {"DBClusters": [self.cluster]}

    def describe_db_instances(self, DBInstanceIdentifier: str) -> Dict[str, Any]:  # noqa: N803
        assert DBInstanceIdentifier == "pellier-writer-ws1"
        return {"DBInstances": [{"DbiResourceId": "db-WRITER", "PerformanceInsightsEnabled":
                                 self.instance_pi, "PerformanceInsightsRetentionPeriod": 465}]}


class _Pi:
    """Top SQL by load, and the queries-finished counter one point a minute."""

    def __init__(self, statements: List[str], denied: bool = False,
                 finished: Tuple[float, ...] = (0.0, 3.7, 4.1)) -> None:
        self.statements, self.denied, self.finished = statements, denied, finished
        self.calls: List[Dict[str, Any]] = []
        self.metric_calls: List[Dict[str, Any]] = []

    def get_resource_metrics(self, **kwargs: Any) -> Dict[str, Any]:
        self.metric_calls.append(kwargs)
        if self.denied:
            raise _Error("AccessDeniedException")
        return {"MetricList": [{"Key": {"Metric": "db.SQL.queries_finished.avg"},
                                "DataPoints": [{"Value": v} for v in self.finished]
                                + [{"Timestamp": "no value yet"}]}]}

    def describe_dimension_keys(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(kwargs)
        if self.denied:
            raise _Error("AccessDeniedException")
        limit = kwargs["GroupBy"]["Limit"]
        return {"Keys": [{"Dimensions": {"db.sql_tokenized.statement": s}, "Total": 0.1}
                         for s in self.statements[:limit]]}


SQL = "SELECT id, name FROM pellier.product_catalog WHERE price <= $1 ORDER BY embedding <=> $2"


def _run(spans=None, logs_events=None, cluster=None, statements=(SQL,), **kw) -> List[Any]:
    logs = _Logs({"aws/spans": spans if spans is not None else [
        _span("routing", "turn-1", 1), _span("execute_tool search_products", "turn-1", 2),
        _span("routing", "turn-2", 3), _span("AgentCore.Gateway.InvokeTool", None, 4)],
        GROUP: logs_events if logs_events is not None else [
            {"message": REFUSAL, "timestamp": _ms(NOW) - 118_000}]}, kw.get("missing"))
    rds = _Rds(_cluster() if cluster is None else cluster, kw.get("instance_pi", True))
    pi = _Pi(list(statements), kw.get("denied", False), kw.get("finished", (0.0, 3.7, 4.1)))
    return obs.check(logs, rds, pi, CLUSTER_ARN, 60, NOW)


def test_all_three_proved_from_the_evidence_itself() -> None:
    spans, insights, log = _run()
    assert [spans.state, insights.state, log.state] == [obs.PROVED] * 3
    assert spans.observed == "3 spans across 2 routed turns"
    assert spans.evidence == ["newest turn turn-2: routing"]
    assert insights.observed == ("DatabaseInsightsMode advanced, Performance Insights on, "
                                 "retention 465 days")
    assert insights.evidence == [
        "queries finished in 2 of the 3 minutes reported (db.SQL.queries_finished)",
        f"top SQL by load: {SQL}"]
    assert log.observed == "1 refused write logged"
    assert log.evidence[0].endswith('ERROR:  new row violates row-level security policy for '
                                    'table "support_tickets"')


def test_app_spans_ignore_agentcore_spans_and_unreadable_lines() -> None:
    spans, _, _ = _run(spans=[_span("AgentCore.Gateway.InvokeTool", None, 1),
                              {"message": "not json pellier.turn_id"},
                              _span("routing", None, 2),
                              _span("invoke_agent shopping", "turn-9", 3)])
    assert spans.state == obs.NOT_YET
    assert "Failed to export span batch" in spans.next_step


def test_a_turn_routed_in_process_does_not_prove_the_managed_path() -> None:
    # Labs 1 and 2 route in the app's own process; span export after the move to AgentCore
    # is what Lab 4 asks about, so only a turn on the gateway-mcp rail counts.
    spans, _, _ = _run(spans=[_span("routing", "turn-lab1", 1, rail="in-process"),
                              _span("routing", "turn-old", 2, rail="")])
    assert spans.state == obs.NOT_YET
    assert spans.observed == "no routing span from a turn on AgentCore yet"
    assert "a turn on AgentCore" in spans.expected


def test_the_newest_routed_turn_lists_its_agent_spans_in_order() -> None:
    spans, _, _ = _run(spans=[_span("routing", "turn-4", 1), _span("chat", "turn-4", 2),
                              _span("invoke_agent shopping", "turn-5", 4),
                              _span("routing", "turn-5", 3), _span("chat", "turn-5", 6),
                              _span("execute_tool search_products", "turn-5", 5),
                              _span("chat", "turn-5", 7),
                              _span("invoke_agent stock", "turn-6", 8)])
    assert spans.state == obs.PROVED
    assert spans.observed == "7 spans across 2 routed turns"
    assert spans.evidence == ["newest turn turn-5: routing, invoke_agent shopping, "
                              "execute_tool search_products, chat"]


def test_a_cluster_without_advanced_mode_is_contradicted() -> None:
    _, insights, _ = _run(cluster=_cluster(mode="standard"))
    assert insights.state == obs.CONTRADICTED
    assert "DatabaseInsightsMode standard" in insights.observed


def test_performance_insights_falls_back_to_the_writer_instance() -> None:
    _, insights, _ = _run(cluster=_cluster(pi_on_cluster=False))
    assert insights.state == obs.PROVED
    _, off, _ = _run(cluster=_cluster(pi_on_cluster=False), instance_pi=False)
    assert off.state == obs.CONTRADICTED
    assert "Performance Insights off" in off.observed


def test_a_quiet_cluster_is_proved_by_its_counter_without_sampled_sql() -> None:
    _, quiet, _ = _run(statements=())
    assert quiet.state == obs.PROVED
    assert quiet.evidence[1] == "top SQL by load: no statement sampled in the window"


def test_load_no_statement_carries_is_left_out_of_top_sql() -> None:
    # Performance Insights files load it cannot tie to a statement under "Unknown"; it is
    # not a query, so it neither takes a top-SQL line nor pushes a real statement out.
    others = ("INSERT INTO lab_2_probes VALUES ($1)", "SELECT 1")
    _, insights, _ = _run(statements=("Unknown", SQL) + others)
    assert insights.state == obs.PROVED
    assert insights.evidence[1:] == [f"top SQL by load: {s}" for s in (SQL,) + others]


def test_statements_that_print_alike_share_one_line() -> None:
    # Two tokenized statements can share their first 87 characters, and cut to fit a line
    # they printed as the same text twice (test event 17: two INSERT INTO lab_2_probes lines).
    start = ('INSERT INTO lab_2_probes WITH named AS ( SELECT c.ord, p."productId" AS id '
             'FROM lab_2_cases c')
    orders = "SELECT customer_id, count(*)::int AS orders FROM pellier.orders GROUP BY customer_id"
    _, insights, _ = _run(statements=(start + " JOIN a", start + " JOIN b", "Unknown", orders, SQL))
    assert insights.state == obs.PROVED
    assert insights.evidence[1:] == [f"top SQL by load: {start[:87]}... (2 statements)",
                                     f"top SQL by load: {orders}", f"top SQL by load: {SQL}"]


def test_load_with_no_statement_at_all_says_so() -> None:
    _, insights, _ = _run(statements=("Unknown",))
    assert insights.state == obs.PROVED
    assert insights.evidence[1] == ("top SQL by load: none; the load sampled in the window "
                                    "names no statement")


def test_insights_without_finished_queries_yet_and_without_permission() -> None:
    _, waiting, _ = _run(finished=(0.0, 0.0))
    assert waiting.state == obs.NOT_YET
    assert waiting.observed.endswith("no finished queries recorded in the window yet")
    _, empty, _ = _run(finished=())
    assert empty.state == obs.NOT_YET
    _, denied, _ = _run(denied=True)
    assert denied.state == obs.UNCHECKED
    assert denied.observed.endswith("could not read its metrics: AccessDeniedException")


def test_database_insights_reads_ask_for_the_writer_and_the_window() -> None:
    logs = _Logs({})
    pi = _Pi([SQL])
    obs.check(logs, _Rds(_cluster()), pi, CLUSTER_ARN, 30, NOW)
    call = pi.calls[0]
    assert call["Identifier"] == "db-WRITER"
    assert call["GroupBy"]["Group"] == "db.sql_tokenized"
    assert (call["EndTime"] - call["StartTime"]).total_seconds() == 30 * 60
    counter = pi.metric_calls[0]
    assert counter["Identifier"] == "db-WRITER"
    assert counter["MetricQueries"] == [{"Metric": "db.SQL.queries_finished.avg"}]
    assert counter["PeriodInSeconds"] == 60
    assert (counter["EndTime"] - counter["StartTime"]).total_seconds() == 30 * 60


def test_postgresql_log_states() -> None:
    _, _, none_yet = _run(logs_events=[])
    assert none_yet.state == obs.NOT_YET
    assert "lab3_row_ownership_check.py" in none_yet.next_step
    _, _, not_exported = _run(cluster=_cluster(exports=[]))
    assert not_exported.state == obs.CONTRADICTED
    _, _, no_group = _run(missing=GROUP)
    assert no_group.state == obs.NOT_YET


def test_a_log_line_without_the_refusal_is_not_evidence() -> None:
    _, _, log = _run(logs_events=[{"message": "LOG:  checkpoint complete", "timestamp": 1}])
    assert log.state == obs.NOT_YET


def test_an_undescribable_cluster_leaves_both_database_findings_unchecked() -> None:
    logs = _Logs({"aws/spans": [_span("routing", "turn-1", 1)]})
    spans, insights, log = obs.check(logs, _Rds(None), _Pi([SQL]), CLUSTER_ARN, 60, NOW)
    assert spans.state == obs.PROVED
    assert spans.observed == "1 span across 1 routed turn"
    assert [insights.state, log.state] == [obs.UNCHECKED, obs.UNCHECKED]
    assert "pellier-cluster-ws1: AccessDenied" in insights.observed


def test_spans_and_the_log_read_from_the_clusters_creation() -> None:
    logs = _Logs({})
    obs.check(logs, _Rds(_cluster()), _Pi([]), CLUSTER_ARN, 60, NOW)
    starts = {call["logGroupName"]: call["startTime"] for call in logs.calls}
    assert starts == {"aws/spans": _ms(CREATED), GROUP: _ms(CREATED)}


def test_a_routed_turn_counts_however_long_ago_lab_4_sent_it() -> None:
    # Lab 4's Step 1 sends the last turn; Step 19 can come more than an hour later.
    turn = {**_span("routing", "turn-lab4", 5), "timestamp": _ms(NOW - timedelta(minutes=80))}
    spans, _, _ = _run(spans=[turn])
    assert spans.state == obs.PROVED
    assert "since the cluster was created at 2026-10-09 09:00:00 UTC" in spans.expected


def test_an_undescribable_cluster_reads_spans_from_the_window() -> None:
    turn = {**_span("routing", "turn-old", 5), "timestamp": _ms(NOW - timedelta(minutes=80))}
    logs = _Logs({"aws/spans": [turn]})
    spans, _, _ = obs.check(logs, _Rds(None), _Pi([SQL]), CLUSTER_ARN, 60, NOW)
    assert spans.state == obs.NOT_YET
    assert "within the last 60 minutes" in spans.expected


def _refusal_at(moment: datetime) -> Dict[str, Any]:
    return {"message": REFUSAL, "timestamp": _ms(moment)}


def test_lab_3s_refusal_counts_however_long_ago_it_ran() -> None:
    # Event 12: Lab 3's check refused the write 80 minutes before Lab 4's Step 17.
    _, _, log = _run(logs_events=[_refusal_at(NOW - timedelta(minutes=80))])
    assert log.state == obs.PROVED
    assert "since the cluster was created at 2026-10-09 09:00:00 UTC" in log.expected


def test_a_lab_3_reset_moves_the_log_start_to_the_reset(_no_reset_points: Path) -> None:
    reset = NOW - timedelta(hours=2)
    workshop_check.record_reset_point(3, reset)
    _, _, before = _run(logs_events=[_refusal_at(reset - timedelta(minutes=1))])
    assert before.state == obs.NOT_YET
    assert "since Lab 3 was reset at 2026-10-09 13:00:00 UTC" in before.expected
    _, _, after = _run(logs_events=[_refusal_at(reset + timedelta(minutes=1))])
    assert after.state == obs.PROVED


def test_a_cluster_without_a_creation_time_reads_the_window() -> None:
    cluster = _cluster()
    del cluster["ClusterCreateTime"]
    _, _, log = _run(cluster=cluster, logs_events=[_refusal_at(NOW - timedelta(minutes=80))])
    assert log.state == obs.NOT_YET
    assert "within the last 60 minutes" in log.expected
