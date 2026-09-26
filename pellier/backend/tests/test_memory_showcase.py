"""The showcase must prove extraction and ownership, not decorate fixtures."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.types import Tool
from botocore.paginate import Paginator
from botocore.session import Session
from strands.tools.mcp.mcp_agent_tool import MCPAgentTool

from routes import observatory
from services import memory_showcase as module
from services.auth import get_current_user
from services.memory_showcase import MemoryShowcase, STRATEGIES, owner_actor, record_view


def service():
    data, control = MagicMock(), MagicMock()
    strategies = [{"name": v[1], "type": v[0], "strategyId": k + "-strategy", "status": "ACTIVE", "namespaces": [v[3]]} for k, v in STRATEGIES.items()]
    strategies[-1]["configuration"] = {"reflection": {"episodicReflectionConfiguration": {"namespaces": [module.REFLECTION_NAMESPACE]}}}
    control.get_memory.return_value = {"memory": {"status": "ACTIVE", "eventExpiryDuration": 30, "strategies": strategies}}
    session = Session()
    api_model = session.get_service_model("bedrock-agentcore")
    paginator_model = session.get_paginator_model("bedrock-agentcore")
    def paginator(operation):
        api_name = ''.join(word.title() for word in operation.split('_'))
        return Paginator(getattr(data, operation), paginator_model.get_paginator(api_name), api_model.operation_model(api_name))
    data.get_paginator.side_effect = paginator
    data.create_event.return_value = {"event": {"eventId": "event-1"}}
    data.list_events.return_value = {"events": []}
    data.list_memory_records.return_value = {"memoryRecordSummaries": []}
    return MemoryShowcase(data=data, control=control, memory_id="test-memory")



def managed_record(kind, actor="owned", session="learn"):
    raw = json.dumps({"situation": "Shopping brief", "intent": "Record preferences", "assessment": "Yes", "justification": "The brief was recorded"}) if kind == "episodic" else "RETRIEVED_" + kind
    return {"memoryRecordId": kind + "-record", "memoryStrategyId": kind + "-strategy",
            "content": {"text": raw}, "namespaces": [module.namespace(kind, actor, session)]}


def populated_service(monkeypatch):
    s = service()
    proof = {"actorId": "owned", "sourceSessionId": "learn", "conversation": [{"content": "RAW_HISTORY_MUST_NOT_BE_REPLAYED"}], "recall": None}
    monkeypatch.setattr(s, "latest", lambda sub: proof)
    def response(**kwargs):
        kind = next((k for k in STRATEGIES if module.namespace(k, "owned", "learn") == kwargs["namespace"]), None)
        return {"memoryRecordSummaries": [managed_record(kind)] if kind else []}
    s.data.list_memory_records.side_effect = response
    s.data.retrieve_memory_records.side_effect = response
    return s

def test_source_conversation_has_separate_completion_event_and_blob_proof():
    s = service()
    proof = s.learn("marco-sub", "marco")
    writes = [c.kwargs for c in s.data.create_event.call_args_list]
    assert len(writes) == 3
    assert writes[0]["actorId"] == writes[1]["actorId"] == proof["actorId"]
    assert writes[0]["sessionId"] == writes[1]["sessionId"]
    assert "completes this conversation" in writes[1]["payload"][0]["conversational"]["content"]["text"]
    assert json.loads(writes[2]["payload"][0]["blob"]) == proof
    assert writes[2]["actorId"] != proof["actorId"]


def test_latest_proof_cannot_redirect_actor_to_another_customer():
    s = service()
    stored = {"version": 1, "runId": "c" * 32, "actorId": "someone-else"}
    s.data.list_events.return_value = {"events": [{"payload": [{"blob": json.dumps(stored)}]}]}
    assert s.latest("marco-sub")["actorId"] == owner_actor("marco-sub") + "-" + "c" * 32
    assert s.data.list_events.call_args.kwargs["actorId"] == owner_actor("marco-sub")
    assert owner_actor("anna-sub") != owner_actor("marco-sub")


@pytest.mark.parametrize("text", ["", "<summary><summary_turn><assessment_user>Yes</assessment_user></summary_turn></summary>", "<reflection>Task complete</reflection>", '{"status":"completed"}'])
def test_raw_or_in_progress_record_does_not_claim_completed_episode(text):
    assert record_view({"content": {"text": text}}, "episodic")["episode"] is None


def test_completed_episode_is_distinct_from_successful_outcome():
    text = "<summary><situation>Gift request</situation><intent>Find a gift</intent><assessment>No</assessment><justification>No stock</justification></summary>"
    result = record_view({"memoryRecordId": "aws-id", "content": {"text": text}}, "episodic")
    assert result["id"] == "aws-id"
    assert result["episode"]["assessment"] == "No"
    assert result["raw"] == text


def test_live_json_episode_shape_is_recognized_but_partial_turns_are_not():
    payload = {"situation": "Shopping brief", "intent": "Record preferences", "assessment": "Yes", "justification": "Shopper acknowledged completion", "turns": [{"assessmentUser": "Yes"}]}
    record = record_view({"content": {"text": json.dumps(payload)}}, "episodic")
    assert record["episode"]["assessment"] == "Yes"
    assert record["content"].startswith("Shopping brief")
    del payload["justification"]
    assert record_view({"content": {"text": json.dumps(payload)}}, "episodic")["episode"] is None


def test_pagination_keeps_later_records():
    s = service()
    s.data.list_memory_records.side_effect = [{"memoryRecordSummaries": [{"memoryRecordId": "first"}], "nextToken": "next"}, {"memoryRecordSummaries": [{"memoryRecordId": "second"}]}]
    rows = s._pages("list_memory_records", "memoryRecordSummaries", namespace="/owned/")
    assert [r["memoryRecordId"] for r in rows] == ["first", "second"]
    assert s.data.list_memory_records.call_args.kwargs["nextToken"] == "next"


def test_active_but_empty_episode_stays_waiting(monkeypatch):
    s = service()
    monkeypatch.setattr(s, "latest", lambda sub: {"actorId": "owned", "sourceSessionId": "learn"})
    result = s.inspect("marco-sub")
    assert result["strategies"]["episodic"]["state"] == "waiting"
    assert result["strategies"]["episodic"]["records"] == []


@pytest.mark.parametrize("user,status", [(None, 401), ({"sub": "anna-sub", "username": "anna"}, 403), ({"sub": "operator-sub", "username": "operator"}, 403)])
def test_showcase_rejects_unauthorized_reads_before_aws(user, status, monkeypatch):
    monkeypatch.setattr(module, "MemoryShowcase", lambda: pytest.fail("unauthorized AWS read"))
    api = FastAPI()
    api.include_router(observatory.router)
    api.dependency_overrides[get_current_user] = lambda: user
    assert TestClient(api).get("/api/observatory/memory-showcase/marco").status_code == status


def test_recall_refuses_to_invoke_before_extraction(monkeypatch):
    s = service()
    monkeypatch.setattr(s, "latest", lambda sub: {"actorId": "owned", "sourceSessionId": "learn"})
    with pytest.raises(RuntimeError, match="must be extracted"):
        asyncio.run(s.recall("marco-sub", "token", "CUST-MARCO"))


def test_recall_passes_retrieved_records_without_replaying_source_chat(monkeypatch):
    s = populated_service(monkeypatch)
    calls = []

    async def invoke(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(response="A current catalog piece.", products=[{"id": "P1", "name": "Linen"}], tool_calls=[{"name": "search_products"}], rail="gateway-mcp", specialist="Catalog")

    monkeypatch.setattr("services.agentcore_runtime.run_agent_on_runtime_result", invoke)
    result = asyncio.run(s.recall("marco-sub", "token", "CUST-MARCO"))
    assert calls[0]["history"] == []
    assert calls[0]["session_id"] != "learn"
    assert "RAW_HISTORY_MUST_NOT_BE_REPLAYED" not in calls[0]["message"]
    assert "RETRIEVED_preferences" in calls[0]["message"]
    assert result["recall"]["historyEventsLoaded"] == 0
    assert result["recall"]["products"][0]["id"] == "P1"
    assert s.data.create_event.call_args_list[0].kwargs["payload"][1]["conversational"]["role"] == "TOOL"
    # A second invocation reuses this cited answer.
    asyncio.run(s.recall("marco-sub", "token", "CUST-MARCO"))
    assert len(calls) == 1


def test_finish_requires_product_evidence_and_never_sets_episode_complete(monkeypatch):
    s = service()
    proof = {"actorId": "owned", "recall": {"sessionId": "recall", "products": []}}
    monkeypatch.setattr(s, "latest", lambda sub: proof)
    with pytest.raises(RuntimeError, match="no product citations"):
        s.finish("marco-sub")
    s.data.create_event.assert_not_called()
    proof["recall"]["products"] = [{"id": "P1"}]
    result = s.finish("marco-sub")
    assert result["recall"]["closureEventId"]
    assert "completed" not in result["recall"]


def test_gateway_reads_real_strands_tool_contract(monkeypatch):
    from services import agentcore_gateway as gateway
    client = MagicMock()
    tool = MCPAgentTool(Tool(name="target___search_products", description="Catalog", inputSchema={"type": "object", "properties": {"query": {"type": "string"}}}), client)
    assert not hasattr(tool, "name")
    client.list_tools_sync.return_value = [tool]
    monkeypatch.setattr(gateway, "_runtime_or_app_setting", lambda key: "https://gateway.example/mcp")
    monkeypatch.setattr("strands.tools.mcp.mcp_client.MCPClient", lambda transport: client)
    rows = gateway.list_gateway_tools(access_token="token")
    assert rows == [{"name": "target___search_products", "description": "Catalog", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}}]


def test_dispatcher_selects_real_sdk_tools(monkeypatch):
    from services import agentcore_gateway as gateway
    client = MagicMock()
    tool = MCPAgentTool(Tool(name="target___search_products", inputSchema={"type": "object"}), client)
    client.list_tools_sync.return_value = [tool]
    agent = MagicMock(return_value="grounded answer")
    factory = MagicMock(return_value=agent)
    monkeypatch.setattr(gateway, "_managed_specialist_spec", lambda *a, **kw: ("Catalog", "Find products", ["search_products"]))
    monkeypatch.setattr(gateway, "_runtime_or_app_setting", lambda key: "https://gateway.example/mcp")
    monkeypatch.setattr("services.response_mode.response_model_for_intent", lambda *a: ("model", 1000, None))
    monkeypatch.setattr("strands.tools.mcp.mcp_client.MCPClient", lambda transport: client)
    monkeypatch.setattr("strands.Agent", factory)
    monkeypatch.setattr("strands.models.BedrockModel", lambda **kw: object())
    result = gateway.ManagedGatewayDispatcher("token")("Find linen")
    assert result == "grounded answer"
    adapted = factory.call_args.kwargs["tools"]
    assert len(adapted) == 1
    assert adapted[0].tool_name == "search_products"
    assert adapted[0].mcp_tool is tool.mcp_tool
    assert adapted[0].mcp_client is client


@pytest.mark.parametrize("kind", ["summary", "episodic"])
def test_memory_xml_entities_remain_untrusted_text(kind):
    raw = '<!DOCTYPE summary [<!ENTITY secret "expanded-secret">]><summary>&secret;</summary>'
    result = record_view({"content": {"text": raw}}, kind)
    assert result["content"] == raw
    assert result["episode"] is None


@pytest.mark.parametrize("kind", STRATEGIES)
def test_recall_requires_each_of_the_four_retrieved_types(kind, monkeypatch):
    s = populated_service(monkeypatch)
    retrieve = s.data.retrieve_memory_records.side_effect
    s.data.retrieve_memory_records.side_effect = lambda **kw: {"memoryRecordSummaries": []} if kw["namespace"] == module.namespace(kind, "owned", "learn") else retrieve(**kw)
    with pytest.raises(RuntimeError, match="all four required"):
        asyncio.run(s.recall("marco-sub", "token", "CUST-MARCO"))


@pytest.mark.parametrize("field,value", [("namespaces", ["/someone-else/"]), ("memoryStrategyId", "wrong-strategy"), ("memoryRecordId", "")])
def test_inspection_rejects_unidentified_or_foreign_records(field, value, monkeypatch):
    s = populated_service(monkeypatch)
    bad = managed_record("preferences")
    bad[field] = value
    s.data.list_memory_records.side_effect = None
    s.data.list_memory_records.return_value = {"memoryRecordSummaries": [bad]}
    assert s.inspect("marco-sub")["strategies"]["preferences"]["records"] == []


def test_partial_episode_blocks_recall_even_with_all_other_records(monkeypatch):
    s = populated_service(monkeypatch)
    response = s.data.list_memory_records.side_effect
    def partial(**kw):
        result = response(**kw)
        for record in result["memoryRecordSummaries"]:
            if record["memoryStrategyId"] == "episodic-strategy":
                record["content"]["text"] = '<summary><summary_turn>Still working</summary_turn></summary>'
        return result
    s.data.list_memory_records.side_effect = partial
    with pytest.raises(RuntimeError, match="completed episode must be extracted"):
        asyncio.run(s.recall("marco-sub", "token", "CUST-MARCO"))


@pytest.mark.parametrize("kind", STRATEGIES)
def test_learning_refuses_namespace_drift(kind):
    s = service()
    strategy = next(x for x in s.control.get_memory.return_value["memory"]["strategies"] if x["type"] == STRATEGIES[kind][0])
    strategy["namespaces"] = ["/wrong/{actorId}/"]
    with pytest.raises(RuntimeError, match="namespace must be"):
        s.learn("marco-sub", "marco")
    s.data.create_event.assert_not_called()


def readiness_module():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[3] / 'scripts/deploy/verify_memory_readiness.py'
    spec = importlib.util.spec_from_file_location('verify_memory_readiness_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provisioning_requires_extraction_not_just_accepted_events():
    s = service()
    s.data.create_event.side_effect = [{"event": {"eventId": "source"}}, {"event": {"eventId": "closure"}}]
    with pytest.raises(RuntimeError, match="extraction/retrieval timed out"):
        readiness_module().verify_memory_readiness(s.control, s.data, "test-memory", timeout=0)
    assert s.data.create_event.call_count == 2
    s.data.get_memory_record.assert_not_called()


def test_provisioning_proves_readback_retrieval_and_isolation():
    s = service()
    s.data.create_event.side_effect = [{"event": {"eventId": "source"}}, {"event": {"eventId": "closure"}}]
    records = {}
    def listing(**kw):
        if "readiness-control-" in kw["namespace"]:
            return {"memoryRecordSummaries": []}
        kind = next(k for k, v in STRATEGIES.items() if kw["namespace"].startswith(v[3].split('{')[0]))
        actor = kw["namespace"].split('/')[3]
        record = managed_record(kind, actor, 'learn-' + actor.removeprefix('readiness-'))
        records[record['memoryRecordId']] = record
        return {"memoryRecordSummaries": [record]}
    s.data.list_memory_records.side_effect = listing
    s.data.retrieve_memory_records.side_effect = listing
    s.data.get_memory_record.side_effect = lambda **kw: {"memoryRecord": records[kw['memoryRecordId']]}
    s.data.list_events.side_effect = lambda **kw: {"events": [{"eventId": "source"}, {"eventId": "closure"}]} if kw['sessionId'].startswith('learn-') else {"events": []}
    result = readiness_module().verify_memory_readiness(s.control, s.data, 'test-memory', timeout=0)
    assert result['status'] == 'ready'
    assert set(result['strategies']) == set(STRATEGIES)
    assert s.data.get_memory_record.call_count == 4
    assert result['namespaceIsolation'] is True
    assert result['sourceSessionId'] != result['recallSessionId']
    assert all(v['retrievedRecordIds'] for v in result['strategies'].values())


def test_configuration_failure_never_seeds_conversations():
    s = service()
    s.control.get_memory.return_value['memory']['strategies'][0]['status'] = 'FAILED'
    with pytest.raises(RuntimeError, match='configuration failed'):
        readiness_module().verify_memory_readiness(s.control, s.data, 'test-memory', timeout=0)
    s.data.create_event.assert_not_called()
