"""The Operator's investigation: a two-node Strands graph, Investigator then Planner.

The Investigator reads the case with the bounded store tools, read-only and
bound to one customer: ``get_orders``, ``get_tickets`` and
``get_return_policy`` from ``services/store_tools.py``. It states what the
records show and what is missing. The Planner proposes exactly one
``give_store_credit`` through its one tool, which computes the amount from the
orders the Planner names and opens one ``pellier.approvals`` row. Then the
graph stops. Nothing changes until a person approves, in a separate request,
and nothing here can call the credit write.

The graph runs in process, on a worker thread, and reports each step as it
happens through ``emit``: the same ``step`` shape Ask Pellier streams, so the
desk renders it with the same components. Findings are fixed templates over
the actual tool results; the model writes the brief, never the step lines.

Every model reads leaves a ``tool_audit`` row through the shared writer, with
the Investigator as the caller, so the desk's reads are on the same ledger as
the shopper's.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

GRAPH_ID = "operator-investigation-v2"
GRAPH_PATTERN = "strands-graph"
EXECUTION = "in-process"
INVESTIGATOR_NODE = "investigator"
PLANNER_NODE = "planner"
INVESTIGATOR_CALLER = "investigator"

_INVESTIGATOR_MAX_TOKENS = 1024
_PLANNER_MAX_TOKENS = 1024
_GRAPH_TIMEOUT_SECONDS = 180
_NODE_TIMEOUT_SECONDS = 90
_MAX_FACTS = 5
_MAX_MISSING = 3

Run = Callable[[str, Any], List[Dict[str, Any]]]
Emit = Callable[[Dict[str, Any]], None]

# The step ids, labels and layer tags the desk shows. One step per tool, in the
# order the Investigator usually reads, plus one per node.
STEP_LABELS: Dict[str, str] = {
    INVESTIGATOR_NODE: "Investigator reads the case",
    "get_orders": "Reading {name}'s orders",
    "get_tickets": "Reading {name}'s tickets",
    "get_return_policy": "Reading the return policy",
    PLANNER_NODE: "Planner proposes a credit",
}

LAYER_TAGS: Dict[str, tuple[str, ...]] = {
    INVESTIGATOR_NODE: ("Investigator",),
    "get_orders": ("Aurora",),
    "get_tickets": ("Aurora",),
    "get_return_policy": ("Aurora",),
    PLANNER_NODE: ("Planner", "Approval"),
}

_INVESTIGATOR_PROMPT = """You are Pellier's Investigator, a staff-side agent.

Read the client's case with your tools, then return ONLY minified JSON with
exactly these keys:
{"facts":[],"missing":[]}

Rules:
- Call get_tickets, get_orders and get_return_policy before you answer.
- facts: at most five short sentences, each stating something the records
  show: what was ordered and paid, what the open ticket says, the return
  window. Name items and amounts exactly as the records give them.
- missing: at most three short sentences on what the records do not show,
  such as a store credit that has not been recorded.
- Do not recommend an action, write to the client, or guess at anything the
  records do not contain.
"""

_PLANNER_PROMPT = """You are Pellier's Planner, a staff-side agent.

You receive the Investigator's brief about one client's case. If the records
show items that went back with no store credit recorded, call
propose_store_credit exactly once with the order ids of the items that went
back and a one-sentence reason a staff member would recognise. The tool
computes the amount from what was paid; you never state an amount yourself.

If no credit is warranted, call nothing and say why in one sentence.

After the tool returns, answer with one plain sentence that names the amount
it reported and that a person must approve it. Never claim the credit was
issued.
"""


@dataclass
class Proposal:
    """What the Planner put in front of a person."""

    review_id: int
    amount_cents: int
    reason: str
    order_ids: List[int]
    action_hash: str
    idempotency_key: str
    customer_id: str

    def as_payload(self) -> Dict[str, Any]:
        return {
            "reviewId": self.review_id,
            "customerId": self.customer_id,
            "amountCents": self.amount_cents,
            "amount": f"{self.amount_cents / 100:.2f}",
            "reason": self.reason,
            "orderIds": list(self.order_ids),
            "actionHash": self.action_hash,
            "idempotencyKey": self.idempotency_key,
            "status": "pending",
        }


@dataclass
class InvestigationResult:
    """The graph's answer: the brief, the proposal and how the run went."""

    turn_id: str
    customer_id: str
    status: str
    facts: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    planner: str = ""
    proposal: Optional[Proposal] = None
    model_id: str = ""
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    error: str = ""

    def as_payload(self) -> Dict[str, Any]:
        return {
            "type": "answer",
            "turnId": self.turn_id,
            "customerId": self.customer_id,
            "status": self.status,
            "investigation": {"facts": list(self.facts), "missing": list(self.missing)},
            "planner": self.planner,
            "proposal": self.proposal.as_payload() if self.proposal else None,
            "graph": {
                "graphId": GRAPH_ID,
                "pattern": GRAPH_PATTERN,
                "execution": EXECUTION,
                "modelId": self.model_id,
                "nodes": list(self.nodes),
                "durationMs": self.duration_ms,
            },
            "error": self.error or None,
        }


# ---------------------------------------------------------------------------
# Step events
# ---------------------------------------------------------------------------


def _money(cents: Any) -> str:
    try:
        amount = int(cents) / 100.0
    except (TypeError, ValueError):
        amount = 0.0
    return f"${amount:,.2f}"


def _parse(result_text: Any) -> Dict[str, Any]:
    if isinstance(result_text, dict):
        return result_text
    text = str(result_text or "").strip()
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except (TypeError, ValueError):
            pass
    return {"_text": text}


def finding_for(tool: str, parsed: Dict[str, Any]) -> str:
    """One plain line computed from the actual result of ``tool``."""
    if parsed.get("status") == "error" or "error" in parsed:
        return "This read did not complete"
    if tool == "get_orders":
        count = int(parsed.get("count") or 0)
        if count == 0:
            return "No orders on file"
        total = sum(int(o.get("amount_paid_cents") or 0) * int(o.get("quantity") or 1) for o in parsed.get("orders") or [])
        return f"{count} order{'' if count == 1 else 's'} on file, {_money(total)} paid"
    if tool == "get_tickets":
        tickets = [t for t in parsed.get("tickets") or [] if isinstance(t, dict)]
        open_tickets = [t for t in tickets if t.get("status") in ("open", "pending")]
        if not open_tickets:
            return "No open ticket" if tickets else "No tickets on file"
        subject = str(open_tickets[0].get("subject") or "").strip()
        head = f"{len(open_tickets)} open ticket{'' if len(open_tickets) == 1 else 's'}"
        return f"{head}: {subject}" if subject else head
    if tool == "get_return_policy":
        if parsed.get("status") == "not_found":
            return "No return policy found"
        days = int(parsed.get("return_window_days") or 0)
        department = str(parsed.get("department") or "default")
        return f"{days}-day returns, store-wide" if department == "default" else f"{days}-day returns for {department}"
    return "Done"


def proposal_finding(parsed: Dict[str, Any]) -> str:
    """The Planner step's line, from the proposal tool's result."""
    status = str(parsed.get("status") or "")
    if status == "review_opened":
        count = len(parsed.get("order_ids") or [])
        return (
            f"{_money(parsed.get('amount_cents'))} credit proposed for "
            f"{count} returned item{'' if count == 1 else 's'}, waiting for approval"
        )
    if status == "already_proposed":
        return "One proposal per investigation; the first stands"
    if status == "over_ceiling":
        return f"{_money(parsed.get('amount_cents'))} is above the $500 safety ceiling"
    return str(parsed.get("message") or "No credit was proposed")


def step_event(
    step_id: str,
    *,
    label: str,
    status: str,
    finding: Optional[str] = None,
    tool: Optional[str] = None,
    duration_ms: Optional[int] = None,
    audit_id: Optional[int] = None,
    agent: Optional[str] = None,
) -> Dict[str, Any]:
    """One ``step`` event in the shape Ask Pellier streams."""
    event: Dict[str, Any] = {
        "type": "step",
        "id": step_id,
        "label": label,
        "status": status,
        "tags": list(LAYER_TAGS.get(step_id, ())),
        "builder": {
            "tool": tool,
            "rail": EXECUTION,
            "duration_ms": duration_ms,
            "audit_id": audit_id,
            "agent": agent,
        },
    }
    if finding is not None:
        event["finding"] = finding
    return event


def _first_name(customer_name: str, customer_id: str) -> str:
    name = str(customer_name or "").strip()
    if name:
        return name.split(" ")[0]
    return str(customer_id).replace("CUST-", "", 1).title()


# ---------------------------------------------------------------------------
# Tools, bound to one case
# ---------------------------------------------------------------------------


@dataclass
class _Case:
    run: Run
    customer_id: str
    customer_name: str
    operator_sub: str
    turn_id: str
    emit: Emit
    proposal: Optional[Proposal] = None
    proposal_result: Dict[str, Any] = field(default_factory=dict)

    @property
    def first_name(self) -> str:
        return _first_name(self.customer_name, self.customer_id)


def _reply(result: Dict[str, Any]) -> str:
    return json.dumps(result, default=str)


def _investigator_tools(case: _Case) -> list:
    """The three read-only store tools, bound to this customer by closure.

    The model cannot pass a customer id: these read one client's records and
    nobody else's, which is what makes the Investigator safe to run as staff.
    """
    from strands import tool

    from services import store_tools

    @tool
    def get_orders(limit: int = 10) -> str:
        """Read this client's orders, newest first, with what was paid.

        Args:
            limit: Maximum orders to return.
        """
        return _reply(store_tools.get_orders(case.run, customer_id=case.customer_id, limit=limit))

    @tool
    def get_tickets(limit: int = 5) -> str:
        """Read this client's support tickets, newest first.

        Args:
            limit: Maximum tickets to return.
        """
        return _reply(store_tools.get_tickets(case.run, customer_id=case.customer_id, limit=limit))

    @tool
    def get_return_policy(department: str = "default") -> str:
        """Read the return window and refund method for a store department.

        Args:
            department: Store department name, such as "Home" or "Clothing".
        """
        return _reply(store_tools.get_return_policy(case.run, department=department))

    return [get_orders, get_tickets, get_return_policy]


_ORDERS_BY_ID_SQL = """
    SELECT o.id AS order_id, o.amount_paid_cents, o.quantity, p.name
      FROM pellier.orders o
      JOIN pellier.product_catalog p ON p."productId" = o.product_id
     WHERE o.customer_id = %s
       AND o.id = ANY(%s)
     ORDER BY o.id
"""


def propose_credit(case: _Case, *, order_ids: Sequence[Any], reason: str) -> Dict[str, Any]:
    """Open one pending review for the credit the named orders are worth.

    The amount is computed here from ``amount_paid_cents`` on this client's
    own orders, never taken from the model. One proposal per investigation:
    a second call returns the first.
    """
    from services import store_tools
    from services.governed_execution import execution_idempotency_key

    if case.proposal is not None:
        return {**case.proposal_result, "status": "already_proposed"}
    clean_reason = " ".join(str(reason or "").split())
    if not clean_reason:
        return {"status": "error", "message": "A reason is required for a credit."}
    ids: List[int] = []
    for value in order_ids or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number not in ids:
            ids.append(number)
    if not ids:
        return {"status": "error", "message": "Name the order ids of the items that went back."}
    rows = case.run(_ORDERS_BY_ID_SQL, (case.customer_id, ids))
    if not rows:
        return {"status": "error", "message": "None of those orders belong to this client."}
    found = [int(row["order_id"]) for row in rows]
    amount = sum(int(row.get("amount_paid_cents") or 0) * int(row.get("quantity") or 1) for row in rows)
    if amount <= 0:
        return {"status": "error", "message": "Those orders carry no paid amount."}
    if amount > store_tools.MAX_CREDIT_CENTS:
        return {"status": "over_ceiling", "amount_cents": amount, "order_ids": found}

    review_id = store_tools.open_credit_review(
        case.run,
        customer_id=case.customer_id,
        amount_cents=amount,
        reason=clean_reason,
        source_turn_id=case.turn_id,
        requested_by_sub=case.operator_sub,
        requester_kind="operator",
        order_id=found[0],
        issue=clean_reason,
        recommendation={
            "primaryAction": "give_store_credit",
            "rationale": clean_reason,
            "orderIds": found,
            "items": [str(row.get("name") or "") for row in rows],
            "graphId": GRAPH_ID,
            "investigationTurnId": case.turn_id,
        },
    )
    if review_id is None:
        return {"status": "error", "message": "The review could not be opened."}
    action_hash = store_tools.write_request_hash(
        "give_store_credit", customer_id=case.customer_id, amount_cents=amount, reason=clean_reason,
    )
    case.proposal = Proposal(
        review_id=review_id,
        amount_cents=amount,
        reason=clean_reason,
        order_ids=found,
        action_hash=action_hash,
        idempotency_key=execution_idempotency_key(review_id, action_hash),
        customer_id=case.customer_id,
    )
    case.proposal_result = {
        "status": "review_opened",
        "review_id": review_id,
        "amount_cents": amount,
        "amount": f"{amount / 100:.2f}",
        "reason": clean_reason,
        "order_ids": found,
        "items": [str(row.get("name") or "") for row in rows],
        "next": "A person approves this exact credit before anything is written.",
    }
    return dict(case.proposal_result)


def _planner_tools(case: _Case) -> list:
    from strands import tool

    @tool
    def propose_store_credit(order_ids: List[int], reason: str) -> str:
        """Propose one store credit for the orders that went back, for a person to approve.

        The amount is computed from what the client paid for those orders.
        Call this at most once.

        Args:
            order_ids: The ids of the orders whose items went back.
            reason: One sentence a staff member would recognise.
        """
        return _reply(propose_credit(case, order_ids=order_ids, reason=reason))

    return [propose_store_credit]


# ---------------------------------------------------------------------------
# Hooks: steps as they happen, audit rows for the reads
# ---------------------------------------------------------------------------


def _tool_result_text(raw: Any) -> str:
    if isinstance(raw, dict):
        for block in raw.get("content") or []:
            if isinstance(block, dict) and "text" in block:
                return str(block["text"])
    return "" if raw is None else str(raw)


class _NodeHooks:
    """Reports one node's tool calls and its start and end as ``step`` events."""

    def __init__(self, case: _Case, node: str) -> None:
        self.case = case
        self.node = node
        self._started: Dict[str, float] = {}
        self._node_started = 0.0

    def register_hooks(self, registry: Any, **_kwargs: Any) -> None:
        from strands.hooks import (
            AfterInvocationEvent,
            AfterToolCallEvent,
            BeforeInvocationEvent,
            BeforeToolCallEvent,
        )

        registry.add_callback(BeforeInvocationEvent, self.before_node)
        registry.add_callback(AfterInvocationEvent, self.after_node)
        registry.add_callback(BeforeToolCallEvent, self.before_tool)
        registry.add_callback(AfterToolCallEvent, self.after_tool)

    def _label(self, step_id: str) -> str:
        return STEP_LABELS.get(step_id, "Checking something").format(name=self.case.first_name)

    def before_node(self, _event: Any) -> None:
        self._node_started = time.perf_counter()
        self.case.emit(step_event(self.node, label=self._label(self.node), status="running", agent=self.node))

    def after_node(self, _event: Any) -> None:
        # The node's finding is written by the graph runner once the output is
        # parsed; here only the clock is known.
        self._node_started = 0.0

    def before_tool(self, event: Any) -> None:
        tool_use = getattr(event, "tool_use", None) or {}
        name = str(tool_use.get("name") or "")
        tool_use_id = tool_use.get("toolUseId")
        if not name:
            return
        self._started[str(tool_use_id)] = time.perf_counter()
        if name in STEP_LABELS:
            self.case.emit(step_event(name, label=self._label(name), status="running", tool=name, agent=self.node))
        if self.node == INVESTIGATOR_NODE:
            from services import tool_audit_writer

            tool_audit_writer.record_allow(
                tool_use_id, name, INVESTIGATOR_CALLER,
                dict(tool_use.get("input") or {}), f"operator-{self.case.customer_id}",
            )

    def after_tool(self, event: Any) -> None:
        tool_use = getattr(event, "tool_use", None) or {}
        name = str(tool_use.get("name") or "")
        tool_use_id = tool_use.get("toolUseId")
        started = self._started.pop(str(tool_use_id), None)
        duration = int((time.perf_counter() - started) * 1000) if started else None
        text = _tool_result_text(getattr(event, "result", None))
        parsed = _parse(text)
        audit_id = None
        if self.node == INVESTIGATOR_NODE:
            from services import tool_audit_writer

            audit_id = tool_audit_writer.pending_audit_id(tool_use_id)
            tool_audit_writer.record_after(tool_use_id, parsed, duration or 0)
        if name in STEP_LABELS:
            failed = parsed.get("status") == "error" or "error" in parsed
            self.case.emit(step_event(
                name, label=self._label(name), status="failed" if failed else "done",
                finding=finding_for(name, parsed), tool=name, duration_ms=duration,
                audit_id=audit_id, agent=self.node,
            ))


# ---------------------------------------------------------------------------
# The graph
# ---------------------------------------------------------------------------


def _brief_from(raw: str) -> tuple[List[str], List[str]]:
    """The Investigator's facts and gaps, parsed leniently from its output."""
    text = str(raw or "")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return [], []
    try:
        parsed = json.loads(match.group(0))
    except (TypeError, ValueError):
        return [], []
    if not isinstance(parsed, dict):
        return [], []

    def lines(key: str, cap: int) -> List[str]:
        values = parsed.get(key) or []
        return [str(v).strip() for v in values if str(v).strip()][:cap] if isinstance(values, list) else []

    return lines("facts", _MAX_FACTS), lines("missing", _MAX_MISSING)


def _node_text(graph_result: Any, node: str) -> str:
    result = (getattr(graph_result, "results", {}) or {}).get(node)
    if result is None:
        return ""
    agent_results = result.get_agent_results()
    return str(agent_results[-1]).strip() if agent_results else ""


def _node_metadata(graph_result: Any) -> List[Dict[str, Any]]:
    nodes: List[Dict[str, Any]] = []
    results = getattr(graph_result, "results", {}) or {}
    for node in getattr(graph_result, "execution_order", []) or []:
        node_id = str(getattr(node, "node_id", "") or "")
        result = results.get(node_id)
        status = getattr(getattr(result, "status", None), "value", None)
        nodes.append({
            "nodeId": node_id,
            "status": str(status or "completed").lower(),
            "durationMs": int(getattr(result, "execution_time", 0) or 0),
        })
    return nodes


def _task(case: _Case, credits: Sequence[Dict[str, Any]]) -> str:
    on_file = (
        "none"
        if not credits
        else "; ".join(
            f"{_money(c.get('amount_cents'))} on {str(c.get('created_at') or '')[:10]}: {c.get('reason')}"
            for c in credits
        )
    )
    return (
        f"CLIENT: {case.customer_name} ({case.customer_id})\n"
        f"STORE CREDITS ON FILE: {on_file}\n"
        "TASK: Investigate the client's open case from the records, then plan the one "
        "store credit the records support, if any."
    )


_CREDITS_SQL = """
    SELECT amount_cents, reason, created_at
      FROM pellier.store_credits
     WHERE customer_id = %s
     ORDER BY created_at DESC
     LIMIT 5
"""


def run_investigation(
    *,
    run: Run,
    customer_id: str,
    customer_name: str,
    operator_sub: str,
    turn_id: str,
    emit: Emit,
) -> InvestigationResult:
    """Run the two-node graph for one client and return what it established.

    Synchronous: the route runs it on a worker thread and relays ``emit``
    events to its SSE stream. The model never chooses the customer, the
    amount, or whether a credit is written.

    Args:
        run: Statement runner bound to the request's database pool.
        customer_id: The client under investigation.
        customer_name: For the step labels.
        operator_sub: The verified staff subject, recorded as the requester.
        turn_id: The investigation's turn id, the review's source turn.
        emit: Receives each ``step`` event as it happens.
    """
    from strands import Agent
    from strands.models import BedrockModel
    from strands.multiagent import GraphBuilder

    from services.specialist_models import specialist_model

    case = _Case(run=run, customer_id=customer_id, customer_name=customer_name,
                 operator_sub=operator_sub, turn_id=turn_id, emit=emit)
    model_id, _configured_max = specialist_model("sonnet")
    investigator = Agent(
        name=INVESTIGATOR_NODE,
        description="Reads one client's orders, tickets and the return policy, and states the case.",
        model=BedrockModel(model_id=model_id, max_tokens=_INVESTIGATOR_MAX_TOKENS),
        system_prompt=_INVESTIGATOR_PROMPT,
        tools=_investigator_tools(case),
        hooks=[_NodeHooks(case, INVESTIGATOR_NODE)],
        callback_handler=None,
    )
    planner = Agent(
        name=PLANNER_NODE,
        description="Proposes one store credit for a person to approve.",
        model=BedrockModel(model_id=model_id, max_tokens=_PLANNER_MAX_TOKENS),
        system_prompt=_PLANNER_PROMPT,
        tools=_planner_tools(case),
        hooks=[_NodeHooks(case, PLANNER_NODE)],
        callback_handler=None,
    )

    builder = GraphBuilder()
    builder.set_max_node_executions(2)
    builder.set_execution_timeout(_GRAPH_TIMEOUT_SECONDS)
    builder.set_node_timeout(_NODE_TIMEOUT_SECONDS)
    builder.add_node(investigator, INVESTIGATOR_NODE)
    builder.add_node(planner, PLANNER_NODE)
    builder.add_edge(INVESTIGATOR_NODE, PLANNER_NODE)
    builder.set_entry_point(INVESTIGATOR_NODE)
    graph = builder.build()
    graph.trace_attributes = {
        "gen_ai.operation.name": "operator_investigation",
        "pellier.graph.id": GRAPH_ID,
        "pellier.turn.id": turn_id,
    }

    try:
        credits = [dict(row) for row in run(_CREDITS_SQL, (customer_id,))]
    except Exception as exc:  # noqa: BLE001 - the brief says so, the graph still runs
        logger.warning("store credits read failed for %s: %s", customer_id, exc)
        credits = []

    started = time.perf_counter()
    try:
        result = graph(_task(case, credits))
    except Exception as exc:  # noqa: BLE001 - the caller renders a failed turn
        duration = int((time.perf_counter() - started) * 1000)
        logger.warning("Operator investigation failed: %s", exc)
        for node in (INVESTIGATOR_NODE, PLANNER_NODE):
            emit(step_event(node, label=STEP_LABELS[node].format(name=case.first_name),
                            status="failed", finding="The investigation did not complete", agent=node))
        return InvestigationResult(
            turn_id=turn_id, customer_id=customer_id, status="failed",
            proposal=case.proposal, model_id=model_id, duration_ms=duration,
            error=exc.__class__.__name__,
        )

    duration = int((time.perf_counter() - started) * 1000)
    facts, missing = _brief_from(_node_text(result, INVESTIGATOR_NODE))
    planner_text = _node_text(result, PLANNER_NODE)
    nodes = _node_metadata(result)
    by_node = {node["nodeId"]: node for node in nodes}

    emit(step_event(
        INVESTIGATOR_NODE, label=STEP_LABELS[INVESTIGATOR_NODE], status="done" if facts else "failed",
        finding=(
            f"{len(facts)} thing{'' if len(facts) == 1 else 's'} the records show, "
            f"{len(missing)} missing"
            if facts else "The Investigator returned no brief"
        ),
        duration_ms=by_node.get(INVESTIGATOR_NODE, {}).get("durationMs"), agent=INVESTIGATOR_NODE,
    ))
    emit(step_event(
        PLANNER_NODE, label=STEP_LABELS[PLANNER_NODE], status="done" if case.proposal else "failed",
        finding=proposal_finding(case.proposal_result) if case.proposal else (
            " ".join(planner_text.split())[:160] or "No credit was proposed"
        ),
        duration_ms=by_node.get(PLANNER_NODE, {}).get("durationMs"), agent=PLANNER_NODE,
    ))
    return InvestigationResult(
        turn_id=turn_id, customer_id=customer_id, status="complete",
        facts=facts, missing=missing, planner=" ".join(planner_text.split()),
        proposal=case.proposal, model_id=model_id, nodes=nodes, duration_ms=duration,
    )
