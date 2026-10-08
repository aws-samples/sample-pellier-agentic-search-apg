"""A paused Aurora instance is retryable; an ambiguous write failure is not."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError


@pytest.fixture
def dataapi(monkeypatch):
    path = Path(__file__).resolve().parents[3] / "scripts/deploy/common/dataapi.py"
    spec = importlib.util.spec_from_file_location("resume_dataapi", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    return module


@pytest.mark.parametrize("entrypoint", ["execute_sql", "execute_write", "begin_transaction"])
def test_autopaused_database_rejects_then_resumes(dataapi, monkeypatch, entrypoint):
    calls = []

    def operation(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise ClientError({"Error": {"Code": "DatabaseResumingException"}}, "test")
        return {"transactionId": "tx", "columnMetadata": [{"name": "n"}],
                "records": [[{"longValue": 1}]]}

    monkeypatch.setattr(dataapi, "rds_client", SimpleNamespace(
        execute_statement=operation, begin_transaction=operation))
    result = getattr(dataapi, entrypoint)(*(() if entrypoint == "begin_transaction" else ("SELECT 1",)))
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert result == {"execute_sql": [{"n": 1}], "execute_write": None,
                      "begin_transaction": "tx"}[entrypoint]


@pytest.mark.parametrize("code, attempts", [
    ("DatabaseResumingException", 7), ("StatementTimeoutException", 1),
    ("AccessDeniedException", 1), ("DatabaseUnavailableException", 1),
])
def test_resume_retries_are_bounded_and_specific(dataapi, code, attempts):
    calls = []

    def operation(**kwargs):
        calls.append(kwargs)
        raise ClientError({"Error": {"Code": code}}, "test")

    with pytest.raises(ClientError):
        dataapi._while_resuming(operation, sql="INSERT INTO ledger VALUES (1)")
    assert len(calls) == attempts
