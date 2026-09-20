"""Managed read execution must have correlated evidence, not only a response."""
from pathlib import Path
import sys
import time
from unittest.mock import Mock
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/deploy'))
from common import handler


def test_read_handler_preserves_correlation_without_passing_metadata_to_tool(monkeypatch):
    import common.dataapi as dataapi
    writer = Mock()
    monkeypatch.setattr(dataapi, 'write_tool_audit_independently', writer)
    tool = Mock(return_value={'count': 2})
    result = handler.build_handler({'browse': {'fn': tool}})(
        {'name': 'browse', 'arguments': {'query': 'linen', 'turn_id': 'turn-read-proof'}}, None)
    tool.assert_called_once_with(query='linen')
    assert not result.get('isError')
    writer.assert_called_once()
    assert writer.call_args.kwargs['args']['turn_id'] == 'turn-read-proof'
    assert writer.call_args.kwargs['result'] == {'count': 2}


def test_uncorrelated_and_unknown_calls_cannot_invent_turn_evidence(monkeypatch):
    import common.dataapi as dataapi
    writer = Mock()
    monkeypatch.setattr(dataapi, 'write_tool_audit_independently', writer)
    handler.audit_read_call('browse', {}, {'count': 2}, time.monotonic())
    handler.build_handler({})({'name': 'unknown', 'arguments': {'turn_id': 'turn-read-proof'}}, None)
    writer.assert_not_called()
