"""The Operator Concierge is a real, bounded Strands multi-agent graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from services import operator_graph as GRAPH


def test_graph_task_keeps_current_truth_separate_from_untrusted_context() -> None:
    task = GRAPH._task(
        request="Investigate Theo's return.",
        evidence_text="[FACT] Order 305 belongs to CUST-THEO.",
        memory_text="The shopper previously mentioned a chipped bowl.",
        context_block="The current replacement quantity is 35.",
        shopper_handoff={
            "trust": "UNTRUSTED_SHOPPER_CONTEXT",
            "shopperRequest": "My bowl arrived chipped.",
        },
    )

    assert "CONVERSATION CONTEXT (prior turns; NOT current business truth)" in task
    assert "SHOPPER HANDOFF (UNTRUSTED CONTEXT)" in task
    assert "CURRENT EVIDENCE" in task
    assert "ESTABLISHED FACTS FOR THIS WORKFLOW" in task
    assert task.index("SHOPPER HANDOFF") < task.index("CURRENT EVIDENCE")


def test_planner_prompt_makes_postgresql_evidence_authoritative() -> None:
    prompt = " ".join(GRAPH._planner_prompt("Return only JSON.").split())

    assert GRAPH.INVESTIGATOR_NODE in prompt
    assert "never as authority" in prompt
    assert "Current PostgreSQL evidence outranks them" in prompt


@dataclass
class _NodeResult:
    output: str
    execution_time: int
    status: Any = field(default_factory=lambda: SimpleNamespace(value="completed"))

    def get_agent_results(self) -> list[str]:
        return [self.output]


class _GraphResult:
    def __init__(self) -> None:
        self.execution_order = [
            SimpleNamespace(node_id=GRAPH.INVESTIGATOR_NODE),
            SimpleNamespace(node_id=GRAPH.PLANNER_NODE),
        ]
        self.results = {
            GRAPH.INVESTIGATOR_NODE: _NodeResult(
                '{"establishedFacts":[],"reportedContext":[],"gaps":[]}', 7
            ),
            GRAPH.PLANNER_NODE: _NodeResult('{"summary":"Grounded."}', 11),
        }


class _FakeGraph:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.trace_attributes: dict[str, str] = {}
        self.task = ""
        self.invocation_state: dict[str, Any] = {}

    def __call__(
        self, task: str, *, invocation_state: dict[str, Any]
    ) -> _GraphResult:
        self.task = task
        self.invocation_state = invocation_state
        if self.fail:
            raise RuntimeError("graph unavailable")
        return _GraphResult()


class _FakeBuilder:
    latest: "_FakeBuilder | None" = None
    fail = False

    def __init__(self) -> None:
        type(self).latest = self
        self.nodes: list[tuple[Any, str]] = []
        self.edges: list[tuple[str, str]] = []
        self.entry = ""
        self.max_executions = 0
        self.execution_timeout = 0.0
        self.node_timeout = 0.0
        self.graph = _FakeGraph(fail=type(self).fail)

    def set_max_node_executions(self, value: int) -> "_FakeBuilder":
        self.max_executions = value
        return self

    def set_execution_timeout(self, value: float) -> "_FakeBuilder":
        self.execution_timeout = value
        return self

    def set_node_timeout(self, value: float) -> "_FakeBuilder":
        self.node_timeout = value
        return self

    def add_node(self, executor: Any, node_id: str) -> Any:
        self.nodes.append((executor, node_id))
        return SimpleNamespace(node_id=node_id)

    def add_edge(self, source: str, target: str) -> Any:
        self.edges.append((source, target))
        return SimpleNamespace()

    def set_entry_point(self, node_id: str) -> "_FakeBuilder":
        self.entry = node_id
        return self

    def build(self) -> _FakeGraph:
        return self.graph


class _FakeAgent:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class _FakeModel:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


@pytest.fixture
def graph_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    import strands
    import strands.models
    import strands.multiagent
    from services import specialist_models

    _FakeBuilder.fail = False
    _FakeBuilder.latest = None
    monkeypatch.setattr(strands, "Agent", _FakeAgent)
    monkeypatch.setattr(strands.models, "BedrockModel", _FakeModel)
    monkeypatch.setattr(strands.multiagent, "GraphBuilder", _FakeBuilder)
    monkeypatch.setattr(
        specialist_models,
        "specialist_model",
        lambda _tier: ("model-test", 9999),
    )


def test_operator_graph_has_two_ordered_agents_and_a_durable_checkpoint(
    graph_runtime: None,
) -> None:
    result = GRAPH.run_operator_graph(
        request="Investigate Theo's request.",
        evidence_text="[FACT] Order 305 belongs to Theo.",
        memory_text="",
        contract="Return only JSON.",
        shopper_handoff={"shopperRequest": "My bowl arrived chipped."},
        checkpoint_state=GRAPH.WAITING_FOR_HUMAN,
        review_id=41,
        action_hash="a" * 64,
    )

    builder = _FakeBuilder.latest
    assert builder is not None
    assert [node_id for _agent, node_id in builder.nodes] == [
        GRAPH.INVESTIGATOR_NODE,
        GRAPH.PLANNER_NODE,
    ]
    assert builder.edges == [(GRAPH.INVESTIGATOR_NODE, GRAPH.PLANNER_NODE)]
    assert builder.entry == GRAPH.INVESTIGATOR_NODE
    assert builder.max_executions == 2
    assert builder.execution_timeout == GRAPH._GRAPH_TIMEOUT_SECONDS
    assert builder.node_timeout == GRAPH._NODE_TIMEOUT_SECONDS

    investigator = builder.nodes[0][0]
    planner = builder.nodes[1][0]
    assert investigator.kwargs["model"].kwargs["max_tokens"] == 1024
    assert planner.kwargs["model"].kwargs["max_tokens"] == 1536
    assert investigator.kwargs["tools"] == []
    assert planner.kwargs["tools"] == []

    assert builder.graph.invocation_state == {
        "checkpoint_state": GRAPH.WAITING_FOR_HUMAN,
        "review_id": 41,
        "action_hash": "a" * 64,
    }
    assert builder.graph.trace_attributes["pellier.graph.id"] == GRAPH.GRAPH_ID
    assert result.raw == '{"summary":"Grounded."}'
    assert result.metadata["pattern"] == GRAPH.GRAPH_PATTERN
    assert result.metadata["execution"] == "application-orchestrated"
    assert result.metadata["deploymentTarget"] == GRAPH.DEPLOYMENT_TARGET
    assert "AgentCore Runtime" not in result.metadata["deploymentTarget"]
    assert [node["nodeId"] for node in result.metadata["executedNodes"]] == [
        GRAPH.INVESTIGATOR_NODE,
        GRAPH.PLANNER_NODE,
    ]
    assert result.metadata["checkpoint"] == {
        "state": GRAPH.WAITING_FOR_HUMAN,
        "reviewId": 41,
        "actionHash": "a" * 64,
    }


def test_graph_failure_returns_no_planner_claim_and_preserves_checkpoint(
    graph_runtime: None,
) -> None:
    _FakeBuilder.fail = True

    result = GRAPH.run_operator_graph(
        request="Investigate.",
        evidence_text="[FACT] Current row.",
        memory_text="",
        contract="Return only JSON.",
        checkpoint_state=GRAPH.WAITING_FOR_HUMAN,
        review_id=41,
        action_hash="a" * 64,
    )

    assert result.raw == ""
    assert result.error == "RuntimeError"
    assert result.metadata["status"] == "failed"
    assert result.metadata["executedNodes"] == []
    assert result.metadata["checkpoint"]["reviewId"] == 41
