"""
The nine store tools Pellier's agents call, as Strands ``@tool`` wrappers.

Each wrapper decides only what the in-process rail must decide: which customer
the call is bound to. The SQL and row shaping live once, in
``services.store_tools``, which the Gateway Lambda
(``scripts/deploy/pellier_store_tools.py``) calls too. Every wrapper reaches it
the same way: ``store_tools.<tool>(_run_sql, ...)``.

  Shopping agent  search_products, browse_department, compare_products, ask_a_person
  Stock agent     check_stock
  Support agent   get_orders, get_return_policy, get_tickets, ask_a_person

``give_store_credit`` has no wrapper here: no agent binds it. The Operator
executes an approved credit through ``services.governed_execution``.
"""
from strands import tool
import contextvars
import json
import asyncio
import logging
import re
from typing import Any, Sequence

from config import settings
from services import store_tools, tool_evidence
from services.ranking_evidence import filter_counts, ranking_from_execution

# Global service references
_db_service = None
_main_loop = None
logger = logging.getLogger(__name__)

def set_db_service(db_service):
    """Set the database service instance"""
    global _db_service
    _db_service = db_service

def set_main_loop(loop):
    """Store reference to the main uvicorn event loop for cross-thread dispatch"""
    global _main_loop
    _main_loop = loop

def _run_async(coro):
    """Run async coroutine from a sync context (e.g. Strands @tool in a background thread).

    Dispatches to the main uvicorn event loop via run_coroutine_threadsafe so that
    the AsyncConnectionPool (bound to the main loop) works correctly. Propagates
    the caller's ContextVars (e.g. ``db_query_log_var``) into the coroutine so
    per-turn telemetry buffers catch tool-initiated DB calls.
    """
    # Capture the current ContextVars (e.g. db_query_log_var) so the
    # coroutine runs with the same context even when dispatched to a
    # different event loop.
    ctx = contextvars.copy_context()

    async def _run_in_ctx():
        # Create a Task in the captured context; this ensures ContextVars
        # set by the caller (like db_query_log_var) are visible inside
        # the coroutine even though we crossed threads.
        return await asyncio.get_running_loop().create_task(coro, context=ctx)

    if _main_loop and _main_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(_run_in_ctx(), _main_loop)
        return future.result(timeout=30)
    # Fallback for standalone / test contexts where no main loop is set.
    # Use get_running_loop() (not the deprecated get_event_loop()): it raises
    # RuntimeError exactly when there is no running loop, which is the case we
    # handle by spinning up a fresh one.
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        # A loop is already running on this thread — hand the coroutine to it.
        future = asyncio.run_coroutine_threadsafe(_run_in_ctx(), loop)
        return future.result(timeout=30)
    # No running loop: create a private one, run to completion, and tear down.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _run_sql(sql: str, params: Sequence[Any] = ()) -> list[dict]:
    """Run one ``store_tools`` statement on the live pool and return its rows."""
    rows = _run_async(_db_service.fetch_all(sql, *params))
    return [dict(row) for row in rows or []]


def _json_default(value):
    """JSON fallback for timestamps, decimals, and driver-native values."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "__float__"):
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    return str(value)


def _reply(result: Any) -> str:
    return json.dumps(result, indent=2, default=_json_default)


_DB_NOT_READY = json.dumps({"error": "Database service not initialized"})


def _extract_query_structure(query: str) -> dict:
    """Ask the structured extractor for a proposed plan.

    A second live Bedrock call on the shopper's critical path, roughly 1-3 s
    and a Sonnet invocation per search, and the only way a shopper's stated
    exclusions, stock requirement or implied budget reach SQL on this rail.

    The planner reads what the shopper typed in this chat (set per turn in
    ``turn_identity.shopper_words_var``), not the agent's search words, so an
    agent cannot drop "no candles" by shortening its query. Outside a chat
    turn it reads ``query``.

    Args:
        query: The agent's search words.

    Returns:
        The extractor's dict, or an explicit failure when extraction fails.
    """
    try:
        from services.structured_extract import get_structured_extractor
        from services.turn_identity import shopper_words_var

        return get_structured_extractor().extract(shopper_words_var.get() or query)
    except Exception as exc:
        # A failed read is not an unconstrained request: the plan must say the
        # shopper's requirements went unread, never that there were none.
        logger.warning("structured extraction failed: %s", exc)
        from services.search_plan import EXTRACTION_FAILED

        return {"extraction_status": EXTRACTION_FAILED, "soft_signal": query}


def _retrieval_config() -> dict:
    """The executor knobs the storefront runs with, recorded on the receipt."""
    return {
        "k_vector": settings.HYBRID_VECTOR_K,
        "k_fts": settings.HYBRID_FTS_K,
        "rrf_k": settings.HYBRID_RRF_K,
        "top_n": settings.HYBRID_TOP_N,
        "rerank_max_documents": settings.RERANK_MAX_DOCUMENTS,
    }


def _receipt_context() -> dict:
    """The trusted turn context and models a retrieval receipt records."""
    from services.retrieval_receipt import current_turn_context

    context = current_turn_context()
    return {
        "turn_id": context.get("turn_id"),
        "session_id": context.get("session_id"),
        "principal_sub": context.get("principal_sub"),
        "rail": context.get("rail"),
        "embedding_model": settings.BEDROCK_EMBEDDING_MODEL,
        "rerank_model": settings.BEDROCK_RERANK_MODEL,
    }


_PERSONA_CUSTOMER_IDS = {
    "marco": "CUST-MARCO",
    "anna": "CUST-ANNA",
    "theo": "CUST-THEO",
    "jessica": "CUST-JESSICA",
    "fresh": "CUST-FRESH",
}


def _infer_customer_id(customer_id: str = "", persona: str = "") -> str:
    """Resolve a customer id from explicit args or the active persona preamble."""
    raw_customer = (customer_id or "").strip()
    if raw_customer:
        if raw_customer.upper().startswith("CUST-"):
            return raw_customer.upper()
        mapped = _PERSONA_CUSTOMER_IDS.get(raw_customer.lower())
        if mapped:
            return mapped
        return raw_customer

    raw_persona = (persona or "").strip().lower()
    if raw_persona in _PERSONA_CUSTOMER_IDS:
        return _PERSONA_CUSTOMER_IDS[raw_persona]

    try:
        from services.persona_context import get_persona_preamble

        preamble = get_persona_preamble()
    except Exception:
        preamble = ""

    match = re.search(r"\bCUST-[A-Z0-9_-]+\b", preamble)
    if match:
        return match.group(0)

    preamble_lower = preamble.lower()
    for persona_id, mapped in _PERSONA_CUSTOMER_IDS.items():
        if re.search(rf"\b{re.escape(persona_id)}\b", preamble_lower):
            return mapped
    return ""


def _publish_binding(
    tool: str,
    *,
    requested: str | None,
    authorized: str | None,
    bound: str | None,
    binding: str,
) -> None:
    """Record who chose the customer, from the binding code itself.

    ``binding`` on this rail is one of ``bound`` (the model named no customer),
    ``matched`` (it named the verified one), ``refused`` (it named another
    customer, or no shopper is verified, so the read did not run) and
    ``unbound`` (a handoff that ran with no verified shopper). This rail never
    overwrites: a mismatch is refused, not corrected.
    """
    if not tool:
        return
    tool_evidence.publish(tool, {
        "identity": {
            "requested_customer": requested or None,
            "authorized_customer": authorized or None,
            "bound_customer": bound or None,
            "binding": binding,
        }
    })


def _verified_read_customer_scope(
    customer_id: str = "", persona: str = "", *, tool: str = ""
) -> tuple[str | None, dict | None]:
    """Return the server-bound customer scope for a caller-bound tool.

    A customer id in model tool input is useful as a consistency check, never
    as the authority for whose records to read. Demo personas are
    intentionally not sufficient here: customer-specific facts need a verified
    principal-to-customer mapping. The binding verdict is published as
    evidence for ``tool`` whenever a turn is collecting it.
    """
    from services.turn_identity import current_authorized_customer_id

    authorized_customer = current_authorized_customer_id()
    raw_requested = (customer_id or "").strip()
    requested_customer = _infer_customer_id(customer_id, persona) if raw_requested else ""
    if not authorized_customer:
        _publish_binding(
            tool, requested=requested_customer, authorized=None, bound=None, binding="refused",
        )
        return None, {
            "status": "customer_scope_required",
            "message": (
                "A verified customer identity is required before Pellier can "
                "read customer-specific data."
            ),
            "read_only": True,
        }

    if requested_customer and requested_customer.casefold() != authorized_customer.casefold():
        _publish_binding(
            tool,
            requested=requested_customer,
            authorized=authorized_customer,
            bound=None,
            binding="refused",
        )
        return None, {
            "status": "customer_scope_mismatch",
            "message": (
                "The requested customer context does not match the verified "
                "shopper identity."
            ),
            "read_only": True,
        }

    _publish_binding(
        tool,
        requested=requested_customer,
        authorized=authorized_customer,
        bound=authorized_customer,
        binding="matched" if requested_customer else "bound",
    )
    return authorized_customer, None


def _search_evidence(payload: dict) -> None:
    """Shape what ``store_tools.search_products`` published for the Builder view.

    Runs the filter-count statement here, on the in-process rail only, and
    carries the ranking beside the result the model reads.
    """
    execution = payload.get("execution")
    counts = None
    try:
        counts = filter_counts(_run_sql, execution.plan)
    except Exception as exc:  # noqa: BLE001 - evidence must not break the turn
        logger.warning("filter counts skipped: %s", exc)
    ranking = ranking_from_execution(
        execution,
        final_rows=payload.get("final_rows") or [],
        counts=counts,
        rrf_k=int(payload.get("rrf_k") or 60),
    )
    tool_evidence.publish("search_products", {
        "ranking": ranking,
        "receipt_id": payload.get("receipt_id"),
    })


# ---------------------------------------------------------------------------
# Shopping agent
# ---------------------------------------------------------------------------


@tool
def search_products(
    query: str,
    max_price: float = None,
    min_rating: float = 0.0,
    category: str = None,
    limit: int = 5,
) -> str:
    """Find products: the shopper's requirements as SQL filters, then vector and full-text search, fused and reranked.

    If the result has constraint_notice, tell the shopper what it says and never
    present the results as meeting a requirement it names. If search_notice is
    present, explain that alternatives have not been checked. An empty result
    then means this attempt found nothing, not that the store has no eligible items.

    Args:
        query: Search words for what to find. The shopper's requirements (budget,
            stock, what they refused) are read from what they typed in this chat.
        max_price: Maximum price, a hard SQL filter (optional).
        min_rating: Minimum star rating, applied after reranking (default 0.0).
        category: A department the agent thinks fits. Recorded on the plan,
            never a filter: only the shopper's own words may restrict a department.
        limit: Number of products to return (default 5).
    """
    if not _db_service:
        return _DB_NOT_READY
    try:
        from services.embeddings import EmbeddingService
        from services.rerank import get_rerank_service

        return _reply(store_tools.search_products(
            _run_sql,
            query=query,
            embed=EmbeddingService().embed_query,
            rerank=get_rerank_service().rerank,
            extracted=_extract_query_structure(query),
            max_price=max_price,
            min_rating=min_rating,
            category=category,
            limit=limit,
            config=_retrieval_config(),
            receipt=_receipt_context(),
            evidence=_search_evidence,
        ))
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def browse_department(department: str, limit: int = 5) -> str:
    """Show the highest-rated products in one store department, such as Home or Kitchen and table.

    Args:
        department: Store department name.
        limit: Number of products to return (default 5).
    """
    if not _db_service:
        return _DB_NOT_READY
    try:
        return _reply(store_tools.browse_department(_run_sql, department=department, limit=limit))
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def compare_products(product_id_1: int, product_id_2: int) -> str:
    """Compare two products side by side by their product ids: price, rating and reviews.

    Args:
        product_id_1: First productId to compare.
        product_id_2: Second productId to compare.
    """
    if not _db_service:
        return _DB_NOT_READY
    try:
        return _reply(store_tools.compare_products(
            _run_sql, product_id_1=product_id_1, product_id_2=product_id_2
        ))
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Stock agent
# ---------------------------------------------------------------------------


@tool
def check_stock(product_query: str) -> str:
    """Stock for one named product: quantity and ship window at each warehouse.

    Pass the product name the shopper used, for example "Hadley shirt" or
    "Wabi-Sabi Bowl". The result is status "success" with the warehouse
    rows, "ambiguous" with candidate names to ask about, or "not_found".

    Args:
        product_query: Product name, or part of it, to check stock for.
    """
    # === WORKSHOP - Stock agent - check_stock: START ===
    # SOLUTION - the Stock agent's one read, wired to the shared implementation.
    #
    # store_tools.check_stock owns the SQL and the three-way contract
    # (not_found, ambiguous, success with total_units); this body only binds
    # it to the pool, exactly as the sibling tools above do.
    if not _db_service:
        return _DB_NOT_READY
    try:
        return _reply(store_tools.check_stock(_run_sql, product_query=product_query))
    except Exception as e:
        return json.dumps({"error": str(e)})
    # === WORKSHOP - Stock agent - check_stock: END ===


# ---------------------------------------------------------------------------
# Support agent
# ---------------------------------------------------------------------------


@tool
def get_orders(customer_id: str = "", limit: int = 10) -> str:
    """Read the signed-in customer's orders, newest first, with what they paid.

    The customer is the verified shopper. A customer_id argument is only checked
    against that identity; it never chooses whose orders to read.

    Args:
        customer_id: Optional, checked against the verified shopper.
        limit: Maximum orders to return.
    """
    if not _db_service:
        return _DB_NOT_READY
    customer, scope_error = _verified_read_customer_scope(customer_id, tool="get_orders")
    if scope_error:
        return json.dumps(scope_error)
    try:
        return _reply(store_tools.get_orders(_run_sql, customer_id=customer, limit=limit))
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_return_policy(department: str = "default") -> str:
    """Look up the return window, condition rules and refund method for a store department.

    Args:
        department: Store department name, such as "Home" or "Clothing".
    """
    if not _db_service:
        return _DB_NOT_READY
    try:
        return _reply(store_tools.get_return_policy(_run_sql, department=department))
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_tickets(customer_id: str = "", limit: int = 5) -> str:
    """Read the signed-in customer's support tickets, newest first, so they never repeat what already happened.

    The customer is the verified shopper. A customer_id argument is only checked
    against that identity; it never chooses whose tickets to read.

    Args:
        customer_id: Optional, checked against the verified shopper.
        limit: Maximum tickets to return.
    """
    if not _db_service:
        return _DB_NOT_READY
    customer, scope_error = _verified_read_customer_scope(customer_id, tool="get_tickets")
    if scope_error:
        return json.dumps(scope_error)
    try:
        return _reply(store_tools.get_tickets(_run_sql, customer_id=customer, limit=limit))
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def ask_a_person(reason: str, store_credit_cents: int = 0, customer_id: str = "") -> str:
    """Hand the conversation to a person at Pellier.

    Use it when the shopper asks for a person, when the request needs human
    judgment, or when the tools cannot responsibly answer. When the shopper asks
    for store credit, pass the amount in store_credit_cents: a person reviews the
    request before anything changes. Never use it for an ordinary catalog question.

    Args:
        reason: One sentence on what is being handed over and why.
        store_credit_cents: The store credit the shopper asked for, in cents;
            0 when this is not a credit request.
        customer_id: Optional, checked against the verified shopper.
    """
    from services.turn_identity import (
        current_authorized_customer_id,
        current_principal_sub,
        current_turn_id,
    )

    # A handoff runs for anyone. A mismatch is refused and the handoff goes on
    # unbound; with no verified shopper it is simply unbound.
    customer, _ = _verified_read_customer_scope(customer_id)
    authorized = current_authorized_customer_id()
    requested = _infer_customer_id(customer_id) if (customer_id or "").strip() else None
    if customer:
        binding = "matched" if requested else "bound"
    elif requested and authorized:
        binding = "refused"
    else:
        binding = "unbound"
    _publish_binding(
        "ask_a_person", requested=requested, authorized=authorized, bound=customer, binding=binding,
    )
    principal_sub = current_principal_sub()
    try:
        return _reply(store_tools.ask_a_person(
            _run_sql,
            reason=reason,
            customer_id=customer,
            store_credit_cents=store_credit_cents,
            source_turn_id=current_turn_id(),
            requested_by_sub=principal_sub,
            requester_kind="shopper" if customer and principal_sub else "unverified",
        ))
    except Exception as e:
        return json.dumps({"error": str(e)})
