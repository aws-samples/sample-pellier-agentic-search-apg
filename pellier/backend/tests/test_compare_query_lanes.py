"""Offline checks for the comparison script's privileged identity probe."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def comparison(monkeypatch):
    def unexpected_transport(*_args, **_kwargs):
        pytest.fail("No AWS, database or external CLI call is allowed in this test.")

    monkeypatch.setattr("boto3.client", unexpected_transport)
    monkeypatch.setattr("psycopg.connect", unexpected_transport)
    monkeypatch.setattr("subprocess.run", unexpected_transport)
    path = Path(__file__).resolve().parents[3] / "scripts/compare_query_lanes.py"
    spec = importlib.util.spec_from_file_location("compare_query_lanes_for_tests", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("role", [
    "workshop_owner",
    "owner'with_quote",
    "owner' OR true; SELECT 'unexpected",
])
@pytest.mark.parametrize("owned_count", [0, 2])
def test_owner_probe_uses_database_identity_without_interpolating_role(
    comparison, monkeypatch, role, owned_count,
):
    calls = []
    client_calls = []
    responses = iter([role, owned_count, 4, 4, 12])

    class DataApi:
        def execute_statement(self, **kwargs):
            calls.append(kwargs)
            value = next(responses)
            field = "stringValue" if isinstance(value, str) else "longValue"
            return {"records": [[{field: value}]]}

    def client(service, **kwargs):
        client_calls.append((service, kwargs))
        return DataApi()

    monkeypatch.setattr("boto3.client", client)
    cfg = {
        "DB_CLUSTER_ARN": "synthetic-cluster",
        "DB_SECRET_ARN": "synthetic-secret-reference",
        "DB_NAME": "test_database",
        "AWS_REGION": "us-east-1",
    }

    result = comparison.probe_mcp_lane_identity(cfg)

    assert result == {
        "reachable": True,
        "current_user": role,
        "owns_protected_tables": bool(owned_count),
        "customers_visible": 4,
        "reads_authorization_mapping": 4,
        "reads_evidence_ledger": 12,
    }
    assert client_calls == [("rds-data", {"region_name": "us-east-1"})]
    assert len(calls) == 5
    assert calls[1]["sql"] == (
        "SELECT count(*) FROM pg_tables WHERE schemaname='pellier'"
        " AND tablename IN ('orders','returns') AND tableowner = current_user"
    )
    assert all(role not in call["sql"] for call in calls)
    assert all(
        call["resourceArn"] == cfg["DB_CLUSTER_ARN"]
        and call["secretArn"] == cfg["DB_SECRET_ARN"]
        and call["database"] == cfg["DB_NAME"]
        for call in calls
    )


def test_missing_configuration_does_not_create_a_data_api_client(comparison):
    result = comparison.probe_mcp_lane_identity({"DB_NAME": "test_database"})

    assert result["reachable"] is False
    assert "DB_CLUSTER_ARN" in result["reason"]
    assert "DB_SECRET_ARN" in result["reason"]
