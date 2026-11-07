"""Runtime resolves Memory records with the verified customer, ignoring payload provenance."""
import json
import sys
import types

from services.runtime_memory import load_preferences


def test_only_records_from_the_bound_customers_namespace_are_used(monkeypatch):
    calls = []
    namespace = "/pellier/preferences/CUST-THEO/"
    class Manager:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def list_long_term_memory_records(self, **kwargs):
            calls.append(kwargs)
            return [
                {"memoryRecordId": "own", "namespaces": [namespace],
                 "content": {"text": json.dumps({"preference": "Stoneware"})}},
                {"memoryRecordId": "foreign", "namespaces": ["/pellier/preferences/CUST-JESSICA/"],
                 "content": {"text": json.dumps({"preference": "Private"})}},
                {"memoryRecordId": "malformed", "content": {"text": "not json"}},
            ]
    module = types.ModuleType("bedrock_agentcore.memory")
    module.MemorySessionManager = Manager
    monkeypatch.setitem(sys.modules, "bedrock_agentcore.memory", module)
    monkeypatch.setenv("AGENTCORE_MEMORY_ID", "memory-test")
    assert load_preferences("CUST-THEO") == [{"record_id": "own", "preference": "Stoneware"}]
    assert calls[1] == {"namespace": namespace, "max_results": 20}


def test_no_customer_or_no_memory_never_uses_a_fallback(monkeypatch):
    monkeypatch.delenv("AGENTCORE_MEMORY_ID", raising=False)
    assert load_preferences("CUST-THEO") == []
    monkeypatch.setenv("AGENTCORE_MEMORY_ID", "memory-test")
    assert load_preferences("") == []
