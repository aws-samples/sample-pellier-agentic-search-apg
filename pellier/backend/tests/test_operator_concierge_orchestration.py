"""The read workflows, and the boundaries that keep them honest.

The load-bearing assertions here are about who owns what. Bedrock produces prose;
Aurora produces facts. Jessica's evidence disagrees with itself, and the disagreement
must survive from the SQL read through the prompt into the artifact without the model
being able to resolve it.

Phase 4B adds two more workflows on the same path, so the assertions are written
against the registry rather than against `client_summary` — a fourth workflow that
skipped the evidence rules or invented its own persistence should fail here.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import threading
from typing import Any, Dict, List, Optional, Tuple

import pytest

from services import operator_concierge as ORCH
from services import operator_concierge_sessions as SESSIONS
from tests.test_operator_concierge_sessions import FakeDb

SUMMARY = ORCH.WORKFLOWS[ORCH.WORKFLOW_CLIENT_SUMMARY]
INVESTIGATE = ORCH.WORKFLOWS[ORCH.WORKFLOW_INVESTIGATE]
DRAFT = ORCH.WORKFLOWS[ORCH.WORKFLOW_DRAFT_NOTE]


def test_every_published_workflow_is_implemented() -> None:
    """The config route publishes this list, so it must not name a stub."""
    assert set(ORCH.SUPPORTED_WORKFLOWS) == set(ORCH.WORKFLOWS)
    for kind in ORCH.SUPPORTED_WORKFLOWS:
        spec = ORCH.WORKFLOWS[kind]
        assert spec.contract.strip(), kind
        assert spec.primary_key, kind
        assert spec.kind in ORCH._FAILURE_COPY, kind


def test_the_three_state_classes_have_distinct_source_labels() -> None:
    labels = {ORCH.SOURCE_AURORA, ORCH.SOURCE_MEMORY, ORCH.SOURCE_BEDROCK}
    assert len(labels) == 3
    assert ORCH.SOURCE_MEMORY == "AgentCore Memory"
    assert ORCH.SOURCE_BEDROCK == "Amazon Bedrock"


def test_local_postgres_is_not_presented_as_aurora(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import settings

    monkeypatch.setattr(settings, "DB_HOST", "127.0.0.1")
    assert ORCH.database_source_label() == "Local PostgreSQL"
    monkeypatch.setattr(
        settings,
        "DB_HOST",
        "dat4xx.cluster-abc123.us-east-1.rds.amazonaws.com",
    )
    assert ORCH.database_source_label() == "Aurora PostgreSQL"
    monkeypatch.setattr(settings, "DB_HOST", "postgres.example.com")
    assert ORCH.database_source_label() == "PostgreSQL"


@pytest.mark.parametrize("remote, expected", [
    ("dat4xx.cluster-abc123.us-east-1.rds.amazonaws.com", "Aurora PostgreSQL"),
    ("postgres.example.com", "PostgreSQL"),
])
def test_tunnel_labels_the_remote_database_without_changing_its_connection(
    monkeypatch: pytest.MonkeyPatch, remote: str, expected: str,
) -> None:
    from config import settings

    monkeypatch.setattr(settings, "DB_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "DB_TUNNEL_REMOTE_HOST", remote)
    assert ORCH.database_source_label() == expected
    assert settings.DB_HOST == "127.0.0.1"
    # A direct remote connection is not identified by stale tunnel metadata.
    monkeypatch.setattr(settings, "DB_HOST", "postgres.example.com")
    assert ORCH.database_source_label() == "PostgreSQL"


# ---------------------------------------------------------------------------
# The model may not contribute structured facts
# ---------------------------------------------------------------------------

def test_only_the_declared_fields_are_read_from_model_output() -> None:
    """A model that returns extra keys must not be able to inject facts."""
    parsed = ORCH._parse_synthesis(json.dumps({
        "summary": "Five orders.",
        "recommendation": "Confirm the refund.",
        # All of these must be ignored.
        "orderCount": 999,
        "membership": "maison",
        "spend12mo": 1_000_000,
        "returns": [{"id": 1}],
    }), SUMMARY)
    assert parsed == {"summary": "Five orders.", "recommendation": "Confirm the refund."}
    assert "orderCount" not in parsed


def test_unusable_model_output_fails_rather_than_inventing() -> None:
    for bad in ("", "I could not do that.", "```json\n{not json}\n```",
                json.dumps({"recommendation": "only this"})):
        assert ORCH._parse_synthesis(bad, SUMMARY) is None, bad


def test_a_missing_primary_field_fails_but_a_missing_section_does_not() -> None:
    """No deliverable is a failure; no unconfirmed report is a legitimate answer."""
    assert ORCH._parse_synthesis(
        json.dumps({"reported": "a ticket says so", "recommendation": "check"}),
        INVESTIGATE,
    ) is None
    parsed = ORCH._parse_synthesis(
        json.dumps({"established": "Five orders.", "reported": "",
                    "recommendation": "Confirm the amount."}),
        INVESTIGATE,
    )
    assert parsed == {"established": "Five orders.", "reported": "",
                      "recommendation": "Confirm the amount."}


def test_fenced_json_is_still_parsed() -> None:
    parsed = ORCH._parse_synthesis(
        '```json\n{"summary":"S","recommendation":"R"}\n```', SUMMARY
    )
    assert parsed == {"summary": "S", "recommendation": "R"}


def test_every_workflow_inherits_the_same_evidence_discipline() -> None:
    """A new workflow must not be able to opt out of the FACT/CONTEXT rules."""
    for kind, spec in ORCH.WORKFLOWS.items():
        # The contracts wrap across lines, so match on normalised text.
        contract = " ".join(spec.contract.split())
        assert "Use ONLY the evidence supplied" in contract, kind
        assert "Never introduce an order id" in contract, kind
        # The Jessica rule, stated to the model explicitly.
        assert "Do not resolve the disagreement" in contract, kind
        assert "CONTEXT is something a source reports" in contract, kind
        # No first person, no process narration.
        assert "No greetings" in contract, kind
        assert "Do not describe your own process" in contract, kind
        # And each declares the exact JSON it expects back.
        assert f'"{spec.primary_key}"' in contract, kind


def test_the_draft_contract_forbids_offering_compensation() -> None:
    contract = " ".join(DRAFT.contract.split())
    for banned in ("discount", "credit", "refund amount", "voucher", "gift",
                   "loyalty points", "free shipping"):
        assert banned in contract, f"the draft contract does not rule out {banned}"
    assert "must not promise a date, an outcome or a resolution" in contract


def test_the_investigation_contract_keeps_the_two_blocks_apart() -> None:
    contract = " ".join(INVESTIGATE.contract.split())
    assert "FACT evidence only" in contract
    assert "CONTEXT evidence only" in contract
    assert "never state that an action has been taken" in contract.lower()


def test_memory_context_is_labelled_as_not_current_truth() -> None:
    """The model must know remembered conversation is not authority."""
    step = ORCH.synthesize.__doc__ or ""
    assert step  # documented
    import inspect

    source = inspect.getsource(ORCH.synthesize)
    assert "NOT current business truth" in source


# ---------------------------------------------------------------------------
# Epistemic roles
# ---------------------------------------------------------------------------

def test_evidence_carries_a_role() -> None:
    item = ORCH.Evidence(
        kind="ticket", role=ORCH.ROLE_CONTEXT, status="unverified",
        source=ORCH.SOURCE_AURORA, label="Service context", detail="x",
    )
    payload = item.to_payload()
    assert payload["role"] == "context"
    assert payload["status"] == "unverified"


def test_the_prompt_prefixes_every_item_with_its_role() -> None:
    rendered = ORCH._evidence_for_prompt([
        ORCH.Evidence(kind="return", role=ORCH.ROLE_FACT, status="verified",
                      source=ORCH.SOURCE_AURORA, label="Return records",
                      detail="No authoritative return record is currently present"),
        ORCH.Evidence(kind="ticket", role=ORCH.ROLE_CONTEXT, status="unverified",
                      source=ORCH.SOURCE_AURORA, label="Service context",
                      detail="Return received, refund amount disputed",
                      record_id="TKT-2026-3015"),
    ])
    assert "[FACT] Return records:" in rendered
    assert "[CONTEXT] Service context:" in rendered
    assert "TKT-2026-3015" in rendered
    # The two must not be presented identically.
    assert rendered.count("[FACT]") == 1 and rendered.count("[CONTEXT]") == 1


@pytest.mark.asyncio
async def test_client_evidence_includes_order_lines_and_attributed_ticket_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The graph must see the same bounded facts the Operator UI displays."""

    async def get_client(*, client_id: str, db: Any) -> Dict[str, Any]:
        assert client_id == "CUST-JESSICA"
        assert db is not None
        return {
            "client": {
                "customerId": "CUST-JESSICA",
                "name": "Jessica Nakamura",
                "membership": "circle",
                "spend12mo": 3940.0,
                "orderValue": 432.66,
                "creditBalance": "0.00",
                "creditBalanceCents": 0,
                "returnEvidence": {"unconfirmedReturnAssertion": True},
            },
            "orders": [
                {
                    "orderId": 406,
                    "productId": "41",
                    "productName": "Coral Lacquer Catchall",
                    "pricePaid": 325.36,
                    "quantity": 1,
                },
                {
                    "orderId": 407,
                    "productId": "42",
                    "productName": "Waffle Bath Robe, Sage",
                    "pricePaid": 107.30,
                    "quantity": 1,
                },
            ],
            "tickets": [
                {
                    "ticketId": "TKT-2026-3015",
                    "subject": "Return received, refund amount disputed",
                    "status": "pending",
                    "lastNote": (
                        "Return logged for the catchall and the robe. "
                        "Client expected a full refund including original shipping."
                    ),
                }
            ],
            "credits": [],
            "returns": [{
                "returnId": 91, "productId": "31",
                "productName": "Stoneware Pour-Over Set",
                "reason": "damaged", "status": "approved",
            }],
        }

    monkeypatch.setattr("routes.operator.get_client", get_client)

    _record, steps, evidence = await ORCH.load_client_evidence(
        object(), "CUST-JESSICA"
    )

    order = next(item for item in evidence if item.kind == "order")
    ticket = next(item for item in evidence if item.kind == "ticket")
    rendered = ORCH._evidence_for_prompt([order, ticket])

    assert "#406 Coral Lacquer Catchall: $325.36" in rendered
    assert "#407 Waffle Bath Robe, Sage: $107.30" in rendered
    assert "Return logged for the catchall and the robe." in rendered
    assert "[FACT] Order history:" in rendered
    assert "[CONTEXT] Service context:" in rendered
    return_record = next(item for item in evidence if item.kind == "return")
    return_text = ORCH._evidence_for_prompt([return_record])
    assert "Return #91: Stoneware Pour-Over Set, status approved, reason damaged" in return_text
    assert "1 authoritative return record." in return_text
    assert return_record.data["returns"][0]["productId"] == "31"
    conflict = next(item for item in evidence if item.kind == "return_conflict")
    assert "different item does not confirm" in conflict.detail
    assert next(step for step in steps if step.kind == "ticket").result == "1 ticket"
    assert next(step for step in steps if step.kind == "return").result == "1 return"


# ---------------------------------------------------------------------------
# Observable steps only
# ---------------------------------------------------------------------------

def test_a_step_never_carries_a_reasoning_label() -> None:
    import inspect

    source = inspect.getsource(ORCH)
    for banned in ("Reasoning trace", "chain of thought", "Let me think",
                   "thinking step"):
        assert banned.lower() not in source.lower(), banned


def test_only_participating_sources_are_reported() -> None:
    steps = [
        ORCH.Step("client", "Client record loaded", ORCH.SOURCE_AURORA),
        ORCH.Step("order", "Order history loaded", ORCH.SOURCE_AURORA),
        ORCH.Step("synthesis", "Summary synthesized", ORCH.SOURCE_BEDROCK),
    ]
    sources = ORCH._sources(steps)
    names = {s["source"] for s in sources}
    assert names == {ORCH.SOURCE_AURORA, ORCH.SOURCE_BEDROCK}
    # Memory did not participate, so it is absent rather than listed as idle.
    assert ORCH.SOURCE_MEMORY not in names


def test_an_unavailable_source_is_not_claimed_as_a_contributor() -> None:
    steps = [
        ORCH.Step("memory", "Conversation memory unavailable", ORCH.SOURCE_MEMORY,
                  status="unavailable"),
        ORCH.Step("client", "Client record loaded", ORCH.SOURCE_AURORA),
    ]
    names = {s["source"] for s in ORCH._sources(steps)}
    assert ORCH.SOURCE_MEMORY not in names, (
        "a failed memory read was reported as an evidence source"
    )
    assert ORCH.SOURCE_AURORA in names


def test_durations_are_measured_not_invented() -> None:
    with ORCH._Timer() as timer:
        pass
    assert timer.ms >= 0
    # A step with no measurement carries None rather than a plausible number.
    assert ORCH.Step("x", "y", ORCH.SOURCE_AURORA).to_payload()["durationMs"] is None


# ---------------------------------------------------------------------------
# Read-only
# ---------------------------------------------------------------------------

def test_no_workflow_proposes_an_action() -> None:
    for spec in ORCH.WORKFLOWS.values():
        artifact = ORCH._artifact(spec, [], [], {spec.primary_key: "p"}, [])
        assert artifact["proposedActions"] == [], spec.kind
        assert artifact["products"] == [], spec.kind


def test_the_orchestrator_never_calls_a_governed_write() -> None:
    import inspect

    source = inspect.getsource(ORCH)
    for forbidden in ("propose_review", "give_store_credit(", "ask_a_person(",
                      "execute_review"):
        assert forbidden not in source, f"read workflow references {forbidden}"


def test_the_request_is_persisted_before_synthesis() -> None:
    """A synthesis failure must not lose what the operator asked."""
    import inspect

    source = inspect.getsource(ORCH.stream_turn)
    assert source.index("append_operator_turn") < source.index("synthesize_async(")


@pytest.mark.asyncio
async def test_blocking_graph_synthesis_runs_off_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_loop_thread = threading.get_ident()
    synthesis_thread: list[int] = []
    expected = ({"summary": "done"}, None, "model")

    def fake_synthesize(**_kwargs: Any) -> tuple[Any, Any, str]:
        synthesis_thread.append(threading.get_ident())
        return expected

    monkeypatch.setattr(ORCH, "synthesize", fake_synthesize)

    result = await ORCH.synthesize_async(
        request="Summarize",
        evidence=[],
        memory_turns=[],
        spec=SUMMARY,
    )

    assert result == expected
    assert synthesis_thread
    assert synthesis_thread[0] != event_loop_thread


def test_the_answer_is_persisted_before_the_memory_mirror() -> None:
    """Memory must never be the only record of an answer."""
    import inspect

    source = inspect.getsource(ORCH.stream_turn)
    assert source.index("append_assistant_artifact") < source.index(
        "record_memory_event"
    )


def test_memory_write_failure_does_not_gate_the_response() -> None:
    import inspect

    source = inspect.getsource(ORCH.stream_turn)
    tail = source[source.index("record_memory_event"):]
    assert "raise" not in tail, "a memory failure can abort the turn"


# ---------------------------------------------------------------------------
# Progressive progress: real work only
# ---------------------------------------------------------------------------

def test_no_step_is_reported_complete_before_the_work_happens() -> None:
    """The one in-flight event is `running`, and only for synthesis.

    A simulated sequence of ticks would look identical to a real one and be a lie in
    a surface whose whole purpose is showing what actually happened.
    """
    import inspect
    import re

    source = inspect.getsource(ORCH.stream_turn)
    emitted = re.findall(r'"status": "(\w+)"', source)
    assert "running" in emitted
    assert emitted.count("running") == 1, "more than one in-flight event"
    # Every literal `complete` emitted inline follows a completed operation.
    running_at = source.index('"status": "running"')
    assert source.index("synthesize_async(") > running_at, (
        "synthesis is announced after it already ran"
    )


def test_the_streaming_and_blocking_paths_share_one_implementation() -> None:
    """Two code paths would drift; the blocking one drains the generator."""
    import inspect

    blocking = inspect.getsource(ORCH.run_turn)
    assert "stream_turn(" in blocking
    assert "append_operator_turn" not in blocking, (
        "the blocking path re-implements the turn instead of draining it"
    )


def test_the_first_turn_does_not_claim_a_successful_memory_load() -> None:
    """"Loaded ... 0 prior turns" reads as retrieving nothing successfully."""
    import inspect

    source = inspect.getsource(ORCH.load_memory_context)
    assert "Conversation context checked" in source
    assert "No prior conversation context" in source
    # And the loaded wording is reserved for a non-empty read.
    checked_at = source.index("Conversation context checked")
    loaded_at = source.index("Conversation context loaded")
    assert checked_at < loaded_at, "the empty case must be handled first"


# ---------------------------------------------------------------------------
# Routing: a suggestion chip is a shortcut, not a private channel
# ---------------------------------------------------------------------------

def test_the_request_text_decides_the_workflow() -> None:
    """The browser sends text only. A workflow kind is a claim, so the server derives it."""
    cases = {
        "Summarize Jessica's recent relationship with Pellier.":
            ORCH.WORKFLOW_CLIENT_SUMMARY,
        "Investigate Jessica's open service issue (TKT-2026-3015).":
            ORCH.WORKFLOW_INVESTIGATE,
        "What happened with her last order?": ORCH.WORKFLOW_INVESTIGATE,
        "Draft a short, sincere note to Jessica.": ORCH.WORKFLOW_DRAFT_NOTE,
        "Write a note about the delay.": ORCH.WORKFLOW_DRAFT_NOTE,
        "Which customer, order, return, and identity records are authoritative "
        "for this decision?": ORCH.WORKFLOW_INVESTIGATE,
        "Prepare the fairest next step for human review without executing it. Name any missing facts the reviewer must resolve.":
            ORCH.WORKFLOW_INVESTIGATE,
    }
    for request, expected in cases.items():
        assert ORCH.classify_workflow(request) == expected, request


def test_routing_is_keyed_to_the_deliverable_not_the_topic() -> None:
    """"Draft a reply about the ticket" asks for copy, not an investigation."""
    assert ORCH.classify_workflow(
        "Draft a reply about ticket TKT-2026-3015 and the disputed refund"
    ) == ORCH.WORKFLOW_DRAFT_NOTE


def test_an_unrecognised_request_falls_back_to_the_defensible_read() -> None:
    for request in ("", "hello", "tell me about this person"):
        assert ORCH.classify_workflow(request) == ORCH.WORKFLOW_CLIENT_SUMMARY


def test_the_guided_human_review_turn_does_not_prepare_an_action() -> None:
    request = (
        "Prepare the fairest next step for human review without executing it. Name any missing facts the reviewer must resolve."
    )
    assert ORCH.classify_workflow(request) == ORCH.WORKFLOW_INVESTIGATE
    spec = ORCH.WORKFLOWS[ORCH.classify_workflow(request)]
    artifact = ORCH._artifact(spec, [], [], {spec.primary_key: "p"}, [])
    assert artifact["proposedActions"] == []


def test_every_suggestion_keyword_the_ui_ships_actually_routes() -> None:
    """Pins the cross-language contract with `templates.ts`.

    The frontend asserts each template's request opens with its verb; this asserts
    that verb routes to the matching workflow. Renaming a keyword on one side without
    the other breaks one of the two tests rather than silently routing every chip to
    a client summary.
    """
    assert ORCH.classify_workflow("Investigate ...") == ORCH.WORKFLOW_INVESTIGATE
    assert ORCH.classify_workflow("Summarize ...") == ORCH.WORKFLOW_CLIENT_SUMMARY
    assert ORCH.classify_workflow("Draft ...") == ORCH.WORKFLOW_DRAFT_NOTE


# ---------------------------------------------------------------------------
# A draft may not commit Pellier to anything
# ---------------------------------------------------------------------------

def test_unauthorized_commitments_are_detected() -> None:
    assert ORCH.unauthorized_commitments(
        "We would like to offer you 20% off your next order."
    ) == ["% off"]
    assert ORCH.unauthorized_commitments(
        "A complimentary alteration is on the house."
    ) == ["complimentary", "on the house"]
    assert ORCH.unauthorized_commitments(
        "Thank you for your patience while we look into this."
    ) == []


class _FakeOperatorGraph:
    """Returns the planner JSON without constructing a Strands graph or calling AWS."""

    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.calls = 0

    def run(self, **_kwargs: Any) -> Any:
        from services.operator_graph import OperatorGraphResult

        self.calls += 1
        return OperatorGraphResult(
            raw=self.raw,
            model_id="model-test",
            metadata={
                "graphId": "operator-concierge-v1",
                "pattern": "strands-graph",
                "executedNodes": [
                    {"nodeId": "case-investigator", "durationMs": 2},
                    {"nodeId": "resolution-planner", "durationMs": 3},
                ],
                "durationMs": 5,
                "status": "complete",
                "checkpoint": {"state": "READ_ONLY_COMPLETE"},
            },
        )


def _stub_bedrock(monkeypatch: pytest.MonkeyPatch, raw: str) -> _FakeOperatorGraph:
    from services import operator_graph

    fake = _FakeOperatorGraph(raw)
    monkeypatch.setattr(operator_graph, "run_operator_graph", fake.run)
    return fake


def test_a_draft_offering_a_discount_is_discarded_not_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator scanning well-formed copy is exactly who would paste it."""
    _stub_bedrock(monkeypatch, json.dumps({
        "draft": "We are sorry for the delay. Please accept 20% off your next order.",
        "operatorContext": "Five orders, one open ticket.",
    }))
    fields, step, _model = ORCH.synthesize(
        request="Draft a note", evidence=[], memory_turns=[], spec=DRAFT
    )
    assert fields is None, "unauthorised copy reached the operator"
    assert step is not None and step.status == "failed"
    assert "cannot authorise" in step.result


def test_a_clean_draft_is_returned_with_its_operator_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_bedrock(monkeypatch, json.dumps({
        "draft": "Thank you for your patience while we review your return.",
        "operatorContext": "Ticket TKT-2026-3015 reports a return; no return record.",
    }))
    fields, step, _model = ORCH.synthesize(
        request="Draft a note", evidence=[], memory_turns=[], spec=DRAFT
    )
    assert fields is not None
    assert fields["draft"].startswith("Thank you")
    assert "TKT-2026-3015" in fields["operatorContext"]
    assert step is not None and step.status == "complete"
    assert step.label == DRAFT.done_label


def test_the_commitment_check_reads_the_draft_not_the_operator_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator legitimately reads "store credit: 0.00"; a client may not be offered it."""
    _stub_bedrock(monkeypatch, json.dumps({
        "draft": "Thank you for your patience while we review your return.",
        "operatorContext": "Store credit on file: 0.00. Confirm before responding.",
    }))
    fields, step, _model = ORCH.synthesize(
        request="Draft a note", evidence=[], memory_turns=[], spec=DRAFT
    )
    assert fields is not None, "an operator-only note was treated as client copy"
    assert step is not None and step.status == "complete"


# ---------------------------------------------------------------------------
# One turn, end to end, on the real session substrate
# ---------------------------------------------------------------------------

def _evidence_stub() -> Any:
    """A minimal but truthy client record. Aurora's shape is asserted elsewhere."""
    async def load(_db: Any, _customer_id: str) -> Any:
        return (
            {"client": {"customerId": "CUST-JESSICA", "name": "Jessica Chen"}},
            [ORCH.Step("client", "Client record loaded", ORCH.SOURCE_AURORA)],
            [ORCH.Evidence(kind="client", role=ORCH.ROLE_FACT, status="verified",
                           source=ORCH.SOURCE_AURORA, label="Client standing",
                           detail="circle")],
        )
    return load


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    spec: ORCH.WorkflowSpec,
    fields: Optional[Dict[str, str]],
    real_mirror: bool = False,
) -> None:
    """Stub the collaborators so the turn lifecycle itself is under test.

    `real_mirror` leaves `record_memory_event` alone, for the tests that assert what
    the memory mirror reports. Re-setting the attribute to itself after it has already
    been stubbed does nothing, which is how three of these tests first read a bool
    where they expected a store name.
    """
    async def no_memory(**_kwargs: Any) -> Any:
        return [], None

    async def no_mirror(**_kwargs: Any) -> bool:
        return False

    def synth(**_kwargs: Any) -> Any:
        step = (
            ORCH.Step("synthesis", spec.done_label, ORCH.SOURCE_BEDROCK, duration_ms=5)
            if fields is not None
            else ORCH.Step("synthesis", spec.running_label, ORCH.SOURCE_BEDROCK,
                           status="failed")
        )
        return fields, step, "model-x"

    monkeypatch.setattr(ORCH, "load_memory_context", no_memory)
    if not real_mirror:
        monkeypatch.setattr(ORCH, "record_memory_event", no_mirror)
    monkeypatch.setattr(ORCH, "load_client_evidence", _evidence_stub())
    monkeypatch.setattr(ORCH, "synthesize", synth)


async def _run(
    db: FakeDb,
    request: str,
    *,
    session_id: str = "",
    transport_key: str = "",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    sid = session_id or (
        await SESSIONS.create_session(
            db, customer_id="CUST-JESSICA", operator_sub="op-1"
        )
    )["sessionId"]
    steps: List[Dict[str, Any]] = []
    final: Dict[str, Any] = {}
    async for kind, data in ORCH.stream_turn(
        db, customer_id="CUST-JESSICA", session_id=sid,
        operator_sub="op-1", request=request, transport_key=transport_key,
    ):
        if kind == "step":
            steps.append(data)
        else:
            final = data
    return steps, final


@pytest.mark.asyncio
async def test_a_draft_turn_is_labelled_as_not_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unlabelled customer-facing copy invites being treated as sent."""
    _wire(monkeypatch, spec=DRAFT, fields={
        "draft": "Thank you for your patience while we review your return.",
        "operatorContext": "One open ticket; no authoritative return record.",
    })
    db = FakeDb()
    _steps, final = await _run(db, "Draft a short note to Jessica")

    assert final["workflow"] == ORCH.WORKFLOW_DRAFT_NOTE
    assert final["primaryLabel"] == "Draft — not sent"
    assert "does not send messages" in final["primaryNote"]
    assert final["summary"].startswith("Thank you")
    # The operator's own context is a separate labelled block, never merged into
    # the copy the client would read.
    assert [s["id"] for s in final["sections"]] == ["operatorContext"]
    assert final["sections"][0]["label"] == "Operator context"
    # A draft has no recommendation line: the next step is the operator's judgement.
    assert final["recommendation"] is None
    assert final["proposedActions"] == []

    # And Aurora holds the draft as the durable answer.
    assistant = [m for m in db.messages if m["role"] == "assistant"]
    assert assistant[-1]["content"].startswith("Thank you")
    assert assistant[-1]["metadata"]["artifact"]["workflow"] == ORCH.WORKFLOW_DRAFT_NOTE


@pytest.mark.asyncio
async def test_the_live_answer_is_emitted_only_after_it_is_durable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch, spec=SUMMARY, fields={
        "summary": "The client has one open service issue.",
        "recommendation": "Review the ticket before responding.",
    })
    db = FakeDb()
    session = await SESSIONS.create_session(
        db, customer_id="CUST-JESSICA", operator_sub="op-1"
    )
    stream = ORCH.stream_turn(
        db,
        customer_id="CUST-JESSICA",
        session_id=session["sessionId"],
        operator_sub="op-1",
        request="Summarize this client",
    )

    kinds: List[str] = []
    async for kind, data in stream:
        kinds.append(kind)
        if kind == "answer":
            assistant = [m for m in db.messages if m["role"] == "assistant"]
            assert assistant[-1]["content"] == data["summary"]

    assert kinds[-2:] == ["answer", "complete"]


@pytest.mark.asyncio
async def test_an_investigation_with_nothing_unconfirmed_shows_no_empty_heading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A heading over nothing reads as missing data rather than as "none"."""
    _wire(monkeypatch, spec=INVESTIGATE, fields={
        "established": "Five orders. No authoritative return record is present.",
        "reported": "",
        "recommendation": "Confirm the refund amount with the client.",
    })
    db = FakeDb()
    _steps, final = await _run(db, "Investigate the open service issue")

    assert final["workflow"] == ORCH.WORKFLOW_INVESTIGATE
    assert final["sections"] == []
    assert final["primaryLabel"] == "Established by the records"
    assert final["recommendation"]["body"].startswith("Confirm")


@pytest.mark.asyncio
async def test_an_investigation_keeps_the_unconfirmed_report_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(monkeypatch, spec=INVESTIGATE, fields={
        "established": "The returns table holds no record for this client.",
        "reported": "TKT-2026-3015 states a return was received.",
        "recommendation": "Confirm receipt before adjusting anything.",
    })
    db = FakeDb()
    _steps, final = await _run(db, "Investigate ticket TKT-2026-3015")

    assert final["summary"] == "The returns table holds no record for this client."
    assert final["sections"][0]["body"].startswith("TKT-2026-3015 states")
    assert final["sections"][0]["tone"] == "context"
    # The two must not be concatenated into one block.
    assert "TKT-2026-3015" not in final["summary"]


@pytest.mark.asyncio
async def test_a_failed_turn_reports_which_deliverable_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The artifact's `summary` is empty on failure and must not blank the sentence.

    `**artifact` spread after the explicit keys silently replaced the failure copy
    with an empty string on the wire, while Aurora kept the correct sentence — so a
    reload showed the failure and the live turn showed nothing.
    """
    _wire(monkeypatch, spec=DRAFT, fields=None)
    db = FakeDb()
    _steps, final = await _run(db, "Draft a note to Jessica")

    assert final["status"] == "failed"
    assert final["summary"] == "No draft was produced."
    assistant = [m for m in db.messages if m["role"] == "assistant"]
    assert assistant[-1]["content"] == "No draft was produced."
    assert assistant[-1]["metadata"]["turn_state"] == SESSIONS.TURN_FAILED


@pytest.mark.asyncio
async def test_the_in_flight_step_names_the_work_being_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"Synthesizing response" under a draft request describes the wrong work."""
    _wire(monkeypatch, spec=DRAFT, fields={"draft": "d", "operatorContext": "c"})
    db = FakeDb()
    steps, _final = await _run(db, "Draft a note to Jessica")

    running = [s for s in steps if s["status"] == "running"]
    assert len(running) == 1
    assert running[0]["label"] == "Drafting client note"
    # The request is saved first, and nothing precedes it.
    assert steps[0]["kind"] == "request" and steps[0]["status"] == "complete"


# ---------------------------------------------------------------------------
# Memory: a fallback dict is not durable memory
# ---------------------------------------------------------------------------

class _FakeMemory:
    """An AgentCoreMemory stand-in that reports which store served each call."""

    def __init__(self, *, backend: str, turns: Optional[List[Dict[str, Any]]] = None,
                 raise_on_read: bool = False,
                 raise_on_write: bool = False) -> None:
        self.backend = backend
        self.turns = turns or []
        self.raise_on_read = raise_on_read
        self.raise_on_write = raise_on_write
        self.written: List[Dict[str, Any]] = []

    async def get_memory_events(self, **_kwargs: Any) -> Any:
        if self.raise_on_read:
            raise RuntimeError("AccessDeniedException")
        return self.turns, self.backend

    async def append_memory_event(self, **kwargs: Any) -> str:
        if self.raise_on_write:
            raise RuntimeError("ThrottlingException")
        self.written.extend(kwargs.get("turns") or [])
        return self.backend


def _install_memory(monkeypatch: pytest.MonkeyPatch, memory: _FakeMemory) -> None:
    from services import agentcore_memory

    monkeypatch.setattr(agentcore_memory, "AgentCoreMemory", lambda *a, **k: memory)


@pytest.mark.asyncio
async def test_a_process_local_read_is_reported_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"The managed store holds nothing" is not "the managed store was not asked".

    Found live: uvicorn launched outside the venv has no `bedrock-agentcore`, so every
    operator turn silently used the in-process dict while the payload still said
    `memoryPersisted: true`.
    """
    from services.agentcore_memory import BACKEND_PROCESS_LOCAL

    _install_memory(monkeypatch, _FakeMemory(
        backend=BACKEND_PROCESS_LOCAL,
        turns=[{"role": "user", "content": "an earlier question"}],
    ))
    turns, step = await ORCH.load_memory_context(
        operator_sub="op-1", session_id="sess-1"
    )
    assert turns == [], "process-local state was offered to the model as memory"
    assert step is not None and step.status == "unavailable"
    assert "not reached" in step.result
    # And an unreached service is never claimed as an evidence source.
    assert ORCH.SOURCE_MEMORY not in {s["source"] for s in ORCH._sources([step])}


@pytest.mark.asyncio
async def test_a_managed_read_is_used_as_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.agentcore_memory import BACKEND_AGENTCORE

    _install_memory(monkeypatch, _FakeMemory(
        backend=BACKEND_AGENTCORE,
        turns=[{"role": "user", "content": "an earlier question"}],
    ))
    turns, step = await ORCH.load_memory_context(
        operator_sub="op-1", session_id="sess-1"
    )
    assert len(turns) == 1
    assert step is not None and step.status == "complete"
    assert step.result == "1 prior turn"
    assert ORCH.SOURCE_MEMORY in {s["source"] for s in ORCH._sources([step])}


@pytest.mark.asyncio
async def test_a_memory_read_failure_does_not_fail_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_memory(monkeypatch, _FakeMemory(backend="agentcore", raise_on_read=True))
    turns, step = await ORCH.load_memory_context(
        operator_sub="op-1", session_id="sess-1"
    )
    assert turns == []
    assert step is not None and step.status == "unavailable"


@pytest.mark.asyncio
async def test_a_process_local_write_is_not_reported_as_persisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.agentcore_memory import BACKEND_PROCESS_LOCAL

    _wire(monkeypatch, spec=SUMMARY, fields={"summary": "s", "recommendation": "r"},
          real_mirror=True)
    _install_memory(monkeypatch, _FakeMemory(backend=BACKEND_PROCESS_LOCAL))
    db = FakeDb()
    _steps, final = await _run(db, "Summarize this client")

    assert final["status"] == "complete", "a memory fallback must not fail the turn"
    assert final["memoryStore"] == BACKEND_PROCESS_LOCAL
    assert final["memoryPersisted"] is False


@pytest.mark.asyncio
async def test_a_managed_write_is_reported_as_persisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.agentcore_memory import BACKEND_AGENTCORE

    _wire(monkeypatch, spec=SUMMARY, fields={"summary": "s", "recommendation": "r"},
          real_mirror=True)
    memory = _FakeMemory(backend=BACKEND_AGENTCORE)
    _install_memory(monkeypatch, memory)
    db = FakeDb()
    _steps, final = await _run(db, "Summarize this client")

    assert final["memoryPersisted"] is True
    assert final["memoryStore"] == BACKEND_AGENTCORE
    # Conversational content only: no evidence, no prompt, no policy material.
    assert [turn["role"] for turn in memory.written] == ["user", "assistant"]
    assert set(memory.written[0]) == {"role", "content"}


@pytest.mark.asyncio
async def test_a_memory_write_failure_leaves_the_answer_intact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aurora is the transcript. Memory is context, and it never gates the answer."""
    _wire(monkeypatch, spec=SUMMARY, fields={"summary": "the answer",
                                             "recommendation": "r"},
          real_mirror=True)
    _install_memory(monkeypatch, _FakeMemory(backend="agentcore", raise_on_write=True))
    db = FakeDb()
    _steps, final = await _run(db, "Summarize this client")

    assert final["status"] == "complete"
    assert final["summary"] == "the answer"
    assert final["memoryPersisted"] is False
    assert final["memoryStore"] == ""
    # And Aurora holds it regardless.
    assistant = [m for m in db.messages if m["role"] == "assistant"]
    assert assistant[-1]["content"] == "the answer"


def test_a_figure_is_formatted_the_way_the_record_beside_it_formats_it() -> None:
    """`3940.0` next to `$3,940.00` for the same number reads as a different system."""
    assert ORCH._money(3940.0) == "$3,940.00"
    assert ORCH._money("40.00") == "$40.00"
    assert ORCH._money(0) == "$0.00"
    # An unparseable value passes through: an evidence detail must never fail a turn.
    assert ORCH._money("unknown") == "unknown"


@pytest.mark.asyncio
async def test_a_replayed_submission_returns_the_stored_answer_without_paying_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transport idempotency. A network retry must not create a second turn.

    Nor a second Bedrock call: synthesis is the expensive part, and an operator
    double-pressing Enter should not be billed for it twice or shown two answers to
    one question.
    """
    calls = {"n": 0}

    def counting_synth(**_kwargs: Any) -> Any:
        calls["n"] += 1
        return (
            {"summary": "Two orders. One open ticket.", "recommendation": "Confirm."},
            ORCH.Step("synthesis", SUMMARY.done_label, ORCH.SOURCE_BEDROCK),
            "model-x",
        )

    _wire(monkeypatch, spec=SUMMARY, fields={"summary": "unused",
                                             "recommendation": "unused"})
    monkeypatch.setattr(ORCH, "synthesize", counting_synth)
    db = FakeDb()
    session = await SESSIONS.create_session(
        db, customer_id="CUST-JESSICA", operator_sub="op-1"
    )
    sid = session["sessionId"]

    _s1, first = await _run(db, "Summarize this client", session_id=sid,
                            transport_key="tk-1")
    _s2, second = await _run(db, "Summarize this client", session_id=sid,
                             transport_key="tk-1")

    assert first["replayed"] is False and second["replayed"] is True
    assert second["turnId"] == first["turnId"], "a retry minted a second turn"
    assert second["summary"] == first["summary"]
    assert calls["n"] == 1, "a replayed submission paid for synthesis again"
    # And exactly one question and one answer are on the record.
    assert len([m for m in db.messages if m["role"] == "user"]) == 1
    assert len([m for m in db.messages if m["role"] == "assistant"]) == 1


# ---------------------------------------------------------------------------
# Routing keyed to the deliverable, and the empty context-stage registry
# ---------------------------------------------------------------------------

def test_a_replacement_request_has_no_workflow_of_its_own() -> None:
    """Replacement search is gone, so such a request reads as a plain client read."""
    assert ORCH.classify_workflow(
        "Find a replacement for her recent vase"
    ) == ORCH.WORKFLOW_CLIENT_SUMMARY
    assert set(ORCH.WORKFLOWS) == {
        ORCH.WORKFLOW_CLIENT_SUMMARY, ORCH.WORKFLOW_INVESTIGATE, ORCH.WORKFLOW_DRAFT_NOTE,
    }


def test_a_request_for_copy_about_a_replacement_is_still_a_draft() -> None:
    """Routing is keyed to the deliverable. The operator asked for a note."""
    assert ORCH.classify_workflow(
        "Draft a note telling her about the replacement options"
    ) == ORCH.WORKFLOW_DRAFT_NOTE


def test_no_workflow_declares_a_context_stage() -> None:
    """`has_context_stage` on the spec and the side table must not drift apart."""
    declared = {k for k, s in ORCH.WORKFLOWS.items() if s.has_context_stage}
    assert declared == set(ORCH._CONTEXT_STAGES) == set()


def test_the_concierge_cannot_execute_a_governed_action() -> None:
    """The permanent architecture guard.

    The Concierge reads and writes prose. Execution stays owned by the review
    record and the governed execute route, so no call that mutates business state
    may appear here.
    """
    source = inspect.getsource(ORCH)
    for forbidden in (
        "give_store_credit(", "ask_a_person(", "store_tools",
        "invoke_tool", "gateway_invoke", "invoke_gateway", "execute_review",
        "execution_rail", "managed_rail",
        # An episode is an OUTCOME. A read is not one.
        "store_episode",
    ):
        assert forbidden not in source, f"the Concierge references {forbidden}"


@pytest.mark.asyncio
async def test_a_recorded_request_is_not_reported_as_received(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After the robe is recorded, the catchall still lacks a record, and neither
    piece is shown as received: Pellier records requests, not parcels arriving."""

    async def get_client(*, client_id: str, db: Any) -> Dict[str, Any]:
        return {
            "client": {
                "customerId": "CUST-JESSICA", "name": "Jessica Nakamura",
                "membership": "circle", "spend12mo": 3940.0, "orderValue": 432.66,
                "creditBalance": "0.00", "creditBalanceCents": 0,
                "returnEvidence": {
                    "unconfirmedReturnAssertion": True,
                    "disputedProductIds": ["41", "42"],
                    "unrecordedDisputedProductIds": ["41"],
                },
            },
            "orders": [
                {"orderId": 406, "productId": "41", "productName": "Coral Lacquer Catchall",
                 "pricePaid": 325.36, "quantity": 1},
                {"orderId": 407, "productId": "42", "productName": "Waffle Bath Robe, Sage",
                 "pricePaid": 107.30, "quantity": 1},
            ],
            "tickets": [{
                "ticketId": "TKT-2026-3015", "status": "pending",
                "subject": "Return received, refund amount disputed",
                "lastNote": "Return logged for the catchall and the robe.",
            }],
            "credits": [],
            "returns": [{"returnId": 92, "productId": "42",
                         "productName": "Waffle Bath Robe, Sage",
                         "reason": "changed_mind", "status": "pending"}],
        }

    monkeypatch.setattr("routes.operator.get_client", get_client)
    _record, _steps, evidence = await ORCH.load_client_evidence(object(), "CUST-JESSICA")

    conflict = next(item for item in evidence if item.kind == "return_conflict")
    assert "No return record exists for Coral Lacquer Catchall." in conflict.detail
    assert "A return request is recorded for Waffle Bath Robe, Sage" in conflict.detail
    assert "remains unverified" in conflict.detail
    assert conflict.status == "unverified"


def test_client_standing_detail_uses_membership_display_names() -> None:
    """Stored rung values stay in the data; the visible detail uses the labels."""
    assert [ORCH._membership_label(v) for v in ("registered", "circle", "maison")] == [
        "Member", "Silver", "Gold",
    ]
    assert ORCH._membership_label(None) == ""


@pytest.mark.parametrize(
    ("stored", "label"), [("registered", "Member"), ("circle", "Silver"), ("maison", "Gold")]
)
def test_model_prompt_carries_the_tier_label_not_the_stored_value(
    monkeypatch: pytest.MonkeyPatch, stored: str, label: str
) -> None:
    """The model sees Silver, never circle; the evidence payload keeps the stored value."""
    async def get_client(*, client_id: str, db: Any) -> Dict[str, Any]:
        return {"client": {"customerId": "CUST-X", "name": "X", "membership": stored,
                           "spend12mo": 100.0}}

    monkeypatch.setattr("routes.operator.get_client", get_client)
    _record, _steps, evidence = asyncio.run(ORCH.load_client_evidence(object(), "CUST-X"))

    prompt = ORCH._evidence_for_prompt(evidence)
    assert label in prompt
    assert stored not in prompt.lower()
    standing = next(e for e in evidence if e.label == "Client standing")
    assert standing.to_payload()["data"]["membership"] == stored
