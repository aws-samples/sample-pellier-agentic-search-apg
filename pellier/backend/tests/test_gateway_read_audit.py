"""Managed read execution must have correlated evidence, not only a response."""
from pathlib import Path
import sys
import time
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/deploy'))
from common import handler
import pellier_store_tools as store_lambda


def test_read_handler_preserves_correlation_without_passing_metadata_to_tool(monkeypatch):
    import common.dataapi as dataapi
    writer = Mock()
    monkeypatch.setattr(dataapi, 'write_tool_audit_independently', writer)
    tool = Mock(return_value={'count': 2})
    monkeypatch.setitem(store_lambda.TOOLS, 'browse_department', tool)
    result = store_lambda.lambda_handler(
        {'name': 'browse_department',
         'arguments': {'department': 'candles', 'turn_id': 'turn-read-proof'}}, None)
    tool.assert_called_once_with({'department': 'candles'}, 'turn-read-proof')
    assert not result.get('isError')
    writer.assert_called_once()
    assert writer.call_args.kwargs['args']['turn_id'] == 'turn-read-proof'
    assert writer.call_args.kwargs['result'] == {'count': 2}
    assert writer.call_args.kwargs['session_id'] == 'turn-read-proof'


def test_uncorrelated_and_unknown_calls_cannot_invent_turn_evidence(monkeypatch):
    import common.dataapi as dataapi
    writer = Mock()
    monkeypatch.setattr(dataapi, 'write_tool_audit_independently', writer)
    handler.audit_read_call('browse_department', {}, {'count': 2}, time.monotonic())
    result = store_lambda.lambda_handler(
        {'name': 'unknown', 'arguments': {'turn_id': 'turn-read-proof'}}, None)
    assert result == {'error': 'Unknown tool: unknown'}
    writer.assert_not_called()
