"""The Operator's investigation: a two-node Strands graph, Investigator then Planner.

The Investigator reads the case with bounded reads, read-only and bound to
one customer: ``get_orders``, ``get_tickets`` and ``get_return_policy`` from
``services/store_tools.py``, and the client's store credits. It states what
the records show and what is missing. The Planner proposes exactly one
``give_store_credit`` through its one tool, which computes the amount and
writes the credit's reason from the client's orders with a received return in
``pellier.returns`` that no live review already covers, whatever orders the
Planner names. It opens one ``pellier.approvals`` row for those orders, or
resolves to the review that already covers them, pending or approved. Then the
graph stops, and the investigation answers the client's open credit requests.
Nothing changes until a person approves, in a separate request, and nothing
here can call the credit write.

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

from services import store_tools

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
    "get_store_credits": "Reading {name}'s store credits",
    "get_return_policy": "Reading the return policy",
    PLANNER_NODE: "Planner proposes a credit",
}

LAYER_TAGS: Dict[str, tuple[str, ...]] = {
    INVESTIGATOR_NODE: ("Investigator",),
    "get_orders": ("Aurora",),
    "get_tickets": ("Aurora",),
    "get_store_credits": ("Aurora",),
    "get_return_policy": ("Aurora",),
    PLANNER_NODE: ("Planner", "Approval"),
}

_INVESTIGATOR_PROMPT = """You are Pellier's Investigator, a staff-side agent.

Read the client's case with your tools, then return ONLY minified JSON with
exactly these keys:
{"facts":[],"missing":[]}

Rules:
- Call get_tickets, get_orders, get_store_credits and get_return_policy
  before you answer.
- facts: at most five short sentences, each stating something the records
  show: what was ordered and paid, which orders the records mark as returned
  (the "returned" field, not the ticket's wording), what the open ticket says,
  which store credits are recorded, the return window. Name items and amounts
  exactly as the records give them.
- missing: at most three short sentences on what the records do not show,
  such as a returned item with no store credit recorded for it.
- Do not recommend an action, write to the client, or guess at anything the
  records do not contain.
"""

_PLANNER_PROMPT = """You are Pellier's Planner, a staff-side agent.

You receive the Investigator's brief about one client's case. If the records
show items that went back with no store credit recorded, call
propose_store_credit exactly once with the order ids the records mark as
returned and one sentence a staff member would recognize as the reason. The
tool computes the amount and writes the credit's wording from the received
returns that no review already covers; you never state an amount yourself.

If no credit is warranted, call nothing and say why in one sentence.

After the tool returns, answer with one plain sentence that names the amount
it reported and the orders it covers, and that a person must approve it. If
the tool reports that a review already covers these items, say so. Never claim
the credit was issued.
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
    # The live review's state: ``pending`` when this run opened it or found it
    # waiting, ``approved`` when a person already approved this exact credit
    # and the run resolved to that review instead of opening a second one.
    status: str = "pending"

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
            "status": self.status,
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
        orders = [o for o in parsed.get("orders") or [] if isinstance(o, dict)]
        total = _paid_total(orders)
        returned = sum(1 for o in orders if o.get("returned"))
        line = f"{count} order{'' if count == 1 else 's'} on file, {_money(total)} paid"
        return f"{line}, {returned} returned" if returned else line
    if tool == "get_tickets":
        tickets = [t for t in parsed.get("tickets") or [] if isinstance(t, dict)]
        open_tickets = [t for t in tickets if t.get("status") in ("open", "pending")]
        if not open_tickets:
            return "No open ticket" if tickets else "No tickets on file"
        subject = str(open_tickets[0].get("subject") or "").strip()
        head = f"{len(open_tickets)} open ticket{'' if len(open_tickets) == 1 else 's'}"
        return f"{head}: {subject}" if subject else head
    if tool == "get_store_credits":
        count = int(parsed.get("count") or 0)
        if count == 0:
            return "No store credit recorded"
        noun = "store credit" if count == 1 else "store credits"
        return f"{count} {noun} recorded, {_money(parsed.get('total_cents'))}"
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
    if status == "already_approved":
        return (
            f"{_money(parsed.get('amount_cents'))} credit already approved in review "
            f"{parsed.get('review_id')}; no second review opened"
        )
    if status == "already_covered":
        return (
            f"{_money(parsed.get('amount_cents'))} credit already waiting in review "
            f"{parsed.get('review_id')}; no second review opened"
        )
    if status == "already_proposed":
        return "One proposal per investigation; the first stands"
    if status == "nothing_returned":
        return "No received return on file, so no credit was proposed"
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


# The client's recorded store credits, newest first. A staff-side read, not one
# of the nine store tools: no shopper agent reads another ledger's credits.
_STORE_CREDITS_SQL = """
    SELECT amount_cents, reason, created_at
      FROM pellier.store_credits
     WHERE customer_id = %s
     ORDER BY created_at DESC
     LIMIT %s
"""
_MAX_CREDITS = 10


def read_store_credits(run: Run, *, customer_id: str, limit: Any = 5) -> Dict[str, Any]:
    """The client's recorded store credits, newest first, at most ``_MAX_CREDITS``."""
    try:
        bounded = max(1, min(int(limit), _MAX_CREDITS))
    except (TypeError, ValueError):
        bounded = 5
    credits = [
        {
            "amount_cents": int(row.get("amount_cents") or 0),
            "amount": _money(row.get("amount_cents")),
            "reason": str(row.get("reason") or ""),
            "created_at": str(row.get("created_at") or "")[:10] or None,
        }
        for row in run(_STORE_CREDITS_SQL, (customer_id, bounded))
    ]
    return {
        "status": "success",
        "customer_id": customer_id,
        "count": len(credits),
        "total_cents": sum(credit["amount_cents"] for credit in credits),
        "credits": credits,
    }


def _investigator_tools(case: _Case) -> list:
    """The four read-only reads, bound to this customer by closure.

    The model cannot pass a customer id: these read one client's records and
    nobody else's, which is what makes the Investigator safe to run as staff.
    """
    from strands import tool

    @tool
    def get_orders(limit: int = 10) -> str:
        """Read this client's orders, newest first, with what was paid and whether each went back.

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
    def get_store_credits(limit: int = 5) -> str:
        """Read the store credits already recorded for this client, newest first.

        Args:
            limit: Maximum credits to return.
        """
        return _reply(read_store_credits(case.run, customer_id=case.customer_id, limit=limit))

    @tool
    def get_return_policy(department: str = "default") -> str:
        """Read the return window and refund method for a store department.

        Args:
            department: Store department name, such as "Home" or "Clothing".
        """
        return _reply(store_tools.get_return_policy(case.run, department=department))

    return [get_orders, get_tickets, get_store_credits, get_return_policy]


# This client's orders with a received return, through the same join the client
# record and get_orders use, so "returned" means one thing on every surface.
_RETURNED_ORDERS_SQL = f"""
    SELECT o.id AS order_id, o.amount_paid_cents, o.quantity, p.name
      FROM pellier.orders o
      JOIN pellier.product_catalog p ON p."productId" = o.product_id{store_tools.RETURN_STATUS_JOIN}
     WHERE o.customer_id = %s
       AND r.status = ANY(%s)
     ORDER BY o.id
"""


def _order_ids(values: Sequence[Any]) -> List[int]:
    ids: List[int] = []
    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number not in ids:
            ids.append(number)
    return ids


def _paid_total(rows: Sequence[Dict[str, Any]]) -> int:
    return sum(
        int(row.get("amount_paid_cents") or 0) * int(row.get("quantity") or 1) for row in rows
    )


def credit_reason(rows: Sequence[Dict[str, Any]]) -> str:
    """The credit's reason, written from the returned orders and nothing else.

    The reason is part of the fingerprint a person approves. Written from the
    records, it is the same sentence on every investigation of the same case,
    so the same credit has the same fingerprint and resolves to its one live
    review. A model-written reason would differ from run to run and open a
    second review, with a second write key, for the same returned items.
    """
    count = len(rows)
    items = "; ".join(f"{row.get('name')} (order {int(row['order_id'])})" for row in rows)
    return f"Store credit for {count} returned item{'' if count == 1 else 's'}: {items}."


def _proposal_refusal(named: List[int], rows: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Why the records support no proposal for these named orders, else None."""
    if not named:
        return {"status": "error", "message": "Name the order ids of the items that went back."}
    if not rows:
        return {
            "status": "nothing_returned",
            "message": (
                "No order of this client has a received return, so the records support "
                "no credit."
            ),
        }
    returned = [int(row["order_id"]) for row in rows]
    if not set(named) & set(returned):
        return {
            "status": "error",
            "message": (
                f"None of orders {named} has a received return for this client. "
                f"The orders that went back are {returned}."
            ),
        }
    return None


def _amount_refusal(rows: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Why the credit for ``rows`` cannot be proposed, else None."""
    amount = _paid_total(rows)
    if amount <= 0:
        return {"status": "error", "message": "The returned orders carry no paid amount."}
    if amount > store_tools.MAX_CREDIT_CENTS:
        order_ids = [int(row["order_id"]) for row in rows]
        return {"status": "over_ceiling", "amount_cents": amount, "order_ids": order_ids}
    return None


# The client's live credit reviews, newest first. Live is pending or approved,
# and an executed review stays approved, so a returned order a live review
# covers is never proposed again. A declined review releases its orders.
_LIVE_REVIEWS_SQL = """
    SELECT id, status, args, action_hash, order_id, recommendation
      FROM pellier.approvals
     WHERE customer_id = %s
       AND tool = 'give_store_credit'
       AND status IN ('pending', 'approved')
     ORDER BY id DESC
"""


def _covering_reviews(case: _Case) -> Dict[int, Dict[str, Any]]:
    """Each order id a live review covers, mapped to the newest such review."""
    from services.operator_review import referenced_order_ids

    covering: Dict[int, Dict[str, Any]] = {}
    for row in case.run(_LIVE_REVIEWS_SQL, (case.customer_id,)):
        for order_id in referenced_order_ids(row):
            covering.setdefault(order_id, dict(row))
    return covering


def propose_credit(case: _Case, *, order_ids: Sequence[Any], reason: str) -> Dict[str, Any]:
    """Open one review for the received returns no review covers yet.

    The amount is the paid total of this client's orders with a received return
    in ``pellier.returns`` that no live review already covers, and the credit's
    reason is written from those same rows (:func:`credit_reason`); neither
    comes from the model. The orders the Planner names only have to include one
    that went back: naming a subset, or extra orders, still yields the credit
    the records support, so Jessica's case proposes 10000 cents whatever the
    model names. When a live review covers every received return, the
    investigation resolves to it instead of opening a second one; a later,
    genuinely new return gets a review of its own covering only that order.
    The Planner's own sentence is kept as the review's rationale. One proposal
    per investigation: a second call returns the first.
    """
    if case.proposal is not None:
        return {**case.proposal_result, "status": "already_proposed"}
    rationale = " ".join(str(reason or "").split())
    if not rationale:
        return {"status": "error", "message": "Say in one sentence why the credit is warranted."}
    rows = case.run(_RETURNED_ORDERS_SQL, (case.customer_id, sorted(store_tools.RETURNED_STATUSES)))
    refusal = _proposal_refusal(_order_ids(order_ids), rows)
    if refusal is not None:
        return refusal
    covering = _covering_reviews(case)
    uncovered = [row for row in rows if int(row["order_id"]) not in covering]
    if not uncovered:
        newest = max((covering[int(row["order_id"])] for row in rows), key=lambda r: int(r["id"]))
        return _resolve_proposal(case, newest, rationale)
    refusal = _amount_refusal(uncovered)
    if refusal is not None:
        return refusal
    return _open_proposal(case, uncovered, rationale)


def _record_proposal(
    case: _Case, review: store_tools.CreditReview, *, amount: int, reason: str,
    order_ids: List[int], items: List[str], rationale: str, status: str,
) -> Dict[str, Any]:
    """Keep the proposal on the case and return what the Planner's tool reports."""
    action_hash = store_tools.write_request_hash(
        "give_store_credit", customer_id=case.customer_id, amount_cents=amount, reason=reason,
    )
    case.proposal = Proposal(
        review_id=review.id,
        amount_cents=amount,
        reason=reason,
        order_ids=order_ids,
        action_hash=action_hash,
        idempotency_key=store_tools.execution_idempotency_key(review.id, action_hash),
        customer_id=case.customer_id,
        status=review.status,
    )
    case.proposal_result = {
        "status": status,
        "review_id": review.id,
        "amount_cents": amount,
        "amount": f"{amount / 100:.2f}",
        "reason": reason,
        "rationale": rationale,
        "order_ids": order_ids,
        "items": items,
        "next": _NEXT_BY_STATUS[status],
    }
    return dict(case.proposal_result)


_NEXT_BY_STATUS = {
    "review_opened": "A person approves this exact credit before anything is written.",
    "already_covered": (
        "A review already covers these returned items and waits for a person. No second "
        "review was opened."
    ),
    "already_approved": (
        "A person already approved the credit for these returned items. Its review stands "
        "and admits one credit; no second review was opened."
    ),
}


def _open_proposal(case: _Case, rows: Sequence[Dict[str, Any]], rationale: str) -> Dict[str, Any]:
    """Open the review for the credit ``rows`` support, and record the proposal."""
    returned = [int(row["order_id"]) for row in rows]
    items = [str(row.get("name") or "") for row in rows]
    amount = _paid_total(rows)
    reason = credit_reason(rows)
    review = store_tools.open_credit_review(
        case.run,
        customer_id=case.customer_id,
        amount_cents=amount,
        reason=reason,
        source_turn_id=case.turn_id,
        requested_by_sub=case.operator_sub,
        requester_kind="operator",
        order_id=returned[0],
        issue=rationale,
        recommendation={
            "primaryAction": "give_store_credit",
            "rationale": rationale,
            "orderIds": returned,
            "items": items,
            "graphId": GRAPH_ID,
            "investigationTurnId": case.turn_id,
        },
    )
    if review is None:
        return {"status": "error", "message": "The review could not be opened."}
    status = "already_approved" if review.status == "approved" else "review_opened"
    return _record_proposal(case, review, amount=amount, reason=reason, order_ids=returned,
                            items=items, rationale=rationale, status=status)


def _resolve_proposal(case: _Case, row: Dict[str, Any], rationale: str) -> Dict[str, Any]:
    """Resolve to the live review that already covers every received return."""
    from services.operator_review import parse_json, referenced_order_ids

    args = parse_json(row.get("args")) or {}
    recommendation = parse_json(row.get("recommendation")) or {}
    review = store_tools.CreditReview(id=int(row["id"]), status=str(row.get("status") or "pending"))
    status = "already_approved" if review.status == "approved" else "already_covered"
    return _record_proposal(
        case, review, amount=int(args.get("amount_cents") or 0), reason=str(args.get("reason") or ""),
        order_ids=referenced_order_ids(row), items=[str(i) for i in recommendation.get("items") or []],
        rationale=rationale, status=status,
    )


def answer_open_requests(case: _Case) -> List[int]:
    """Answer the client's open credit requests with this investigation.

    A request is answered by the review the investigation opened or resolved
    to, or by no review when the records supported none. A failed write leaves
    the request open for the next investigation, and says so in the log.
    """
    review_id = case.proposal.review_id if case.proposal else None
    try:
        return store_tools.answer_credit_requests(
            case.run, customer_id=case.customer_id, investigation_turn_id=case.turn_id,
            review_id=review_id,
        )
    except Exception as exc:  # noqa: BLE001 - the investigation stands; the request stays open
        logger.warning("open credit requests not answered for %s: %s", case.customer_id, exc)
        return []


def _planner_tools(case: _Case) -> list:
    from strands import tool

    @tool
    def propose_store_credit(order_ids: List[int], reason: str) -> str:
        """Propose one store credit for the orders that went back, for a person to approve.

        The amount is computed from what the client paid for the orders the
        records mark as returned. Call this at most once.

        Args:
            order_ids: The ids of the orders the records mark as returned.
            reason: One sentence a staff member would recognize, on why.
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


def _task(case: _Case) -> str:
    return (
        f"CLIENT: {case.customer_name} ({case.customer_id})\n"
        "TASK: Investigate the client's open case from the records, then plan the one "
        "store credit the records support, if any."
    )


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

    started = time.perf_counter()
    try:
        result = graph(_task(case))
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
    answer_open_requests(case)
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
