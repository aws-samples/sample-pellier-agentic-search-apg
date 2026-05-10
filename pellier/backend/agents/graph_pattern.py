"""
Graph Pattern (Pattern II) — real Strands ``GraphBuilder`` execution for
the Atelier's `pattern="graph"` chat request.

The chat streaming pipeline in ``services/chat.py`` was written against
a single Strands ``Agent`` shape: it calls ``orchestrator(full_message)``
to get an ``AgentResult``, stringifies the result for the final bubble,
and relies on ``agent.callback_handler`` + ``agent.add_hook`` to emit
SSE deltas and tool lifecycle events. A raw Strands ``Graph`` satisfies
the callable shape but returns a ``GraphResult`` whose ``__str__`` is
the dataclass repr, not the winning specialist's prose — and it has no
``callback_handler`` / ``add_hook`` surface.

``GraphAgentAdapter`` bridges the two. It:

  1. Builds a router node (Haiku classifier) + five specialist nodes
     (search / recommendation / pricing / inventory / support) via the
     existing factories. The router's prose picks one specialist; five
     conditional edges fan out so exactly one specialist runs per turn.
  2. Exposes ``callback_handler`` and ``add_hook`` as plain attributes
     and attaches them to the *specialist* agents at build time, so
     that when the pipeline does ``_attach_streaming_and_hooks(adapter)``
     the SSE deltas and tool hooks flow from whichever specialist ends
     up running. The router is a short classifier; its tokens are not
     forwarded to the user bubble.
  3. When called, runs ``Graph.__call__`` and repackages the winning
     specialist's ``AgentResult`` so ``str(adapter_result)`` returns
     the specialist's text — which is what the downstream parser
     feeds to ``_parse_agent_response``.

The adapter is intentionally non-streaming for the router step and
lets the specialist stream naturally — that keeps the Atelier's
telemetry panel honest: one deterministic route decision, then one
specialist's prose streams to the client.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from strands import Agent
from strands.models import BedrockModel

from config import settings

logger = logging.getLogger(__name__)


# Deterministic router prompt. Kept tight — Haiku's whole job here is
# to emit exactly one of the five specialist tokens. Any other output
# falls through to ``search`` as a safe default.
_ROUTER_SYSTEM_PROMPT = (
    "You are a routing classifier for a retail assistant. "
    "Read the shopper's message and respond with EXACTLY ONE word from "
    "this set: search, recommendation, pricing, inventory, support. "
    "No punctuation, no explanation, no quotes. Pick the best match.\n"
    "- search: product search, category browsing, comparisons.\n"
    "- recommendation: 'what should I get', gifts, trending, personalized picks.\n"
    "- pricing: 'how much', deals, discounts, price comparisons.\n"
    "- inventory: 'do you have', stock, availability, restocking.\n"
    "- support: returns, policies, troubleshooting, account help."
)


_VALID_ROUTES = ("search", "recommendation", "pricing", "inventory", "support")


def _build_router_agent() -> Agent:
    """Small Haiku agent that outputs one specialist token."""
    return Agent(
        model=BedrockModel(
            model_id=settings.BEDROCK_HAIKU_MODEL
            if hasattr(settings, "BEDROCK_HAIKU_MODEL")
            else "us.anthropic.claude-haiku-4-5-20251001-v1:0",
            max_tokens=16,
            temperature=0.0,
        ),
        system_prompt=_ROUTER_SYSTEM_PROMPT,
    )


def _extract_route(router_text: str) -> str:
    """Normalize the router's output to a valid route key.

    The router is instructed to emit one token, but real LLM calls
    occasionally leak whitespace, punctuation, or extra prose. We
    defensively lowercase, strip, and match against the valid set.
    Anything unmatched falls through to ``search`` — broad enough to
    cover most off-target queries and still produce a useful reply.
    """
    if not router_text:
        return "search"
    token = router_text.strip().lower().split()[0] if router_text.strip() else ""
    token = token.rstrip(".,!?:;\"'")
    if token in _VALID_ROUTES:
        return token
    logger.warning("Graph router produced unparseable token %r; defaulting to search", router_text[:40])
    return "search"


class GraphAgentAdapter:
    """Drop-in replacement for a Strands ``Agent`` that executes a
    real ``Graph`` under the hood.

    The adapter satisfies four contracts the chat streaming pipeline
    depends on:

    * ``__call__(message)`` — synchronous call returning an object with
      a useful ``__str__``. We return the winning specialist's
      ``AgentResult`` directly, so ``str(result)`` yields the
      specialist's prose exactly as the dispatcher path would.
    * ``callback_handler`` — the pipeline assigns a streaming callback
      into this attribute. We forward the assignment to every specialist
      agent so tokens stream regardless of which specialist wins. (The
      router's short classifier output is deliberately excluded; routing
      decisions live in telemetry, not the user bubble.)
    * ``add_hook(callback)`` — tool lifecycle hooks. Forwarded to every
      specialist so ``_tool_start`` / ``_tool_done`` SSE events fire for
      whichever specialist ended up running.
    * ``trace_attributes`` + ``session_manager`` — applied to every
      specialist so OTEL spans and session persistence match the rest
      of the pipeline.
    """

    def __init__(self) -> None:
        # Lazy imports — the specialist factories pull in Strands
        # tools; importing at module load would drag the whole tool
        # registry into any file that touches chat.py.
        from agents.search_agent import build_search_agent
        from agents.recommendation_agent import build_recommendation_agent
        from agents.pricing_agent import build_pricing_agent
        from agents.inventory_agent import build_inventory_agent
        from agents.customer_support_agent import build_support_agent

        # Router + specialists. We build the specialists eagerly so
        # GraphBuilder can validate them and so ``callback_handler`` /
        # ``add_hook`` assignments propagate to all of them before the
        # graph runs.
        self._router = _build_router_agent()
        self._specialists: Dict[str, Agent] = {
            "search": build_search_agent(),
            "recommendation": build_recommendation_agent(),
            "pricing": build_pricing_agent(),
            "inventory": build_inventory_agent(),
            "support": build_support_agent(),
        }

        # Expose trace_attributes / session_manager as plain dicts —
        # the pipeline assigns to these directly. Assignment is captured
        # in __setattr__ and forwarded to each specialist so every
        # execution path inherits the same trace and session wiring.
        self.trace_attributes: Dict[str, Any] = {}
        self.session_manager: Any = None

        # Route picked during the most recent __call__, exposed for
        # telemetry panels that want to label which specialist ran.
        self.last_route: Optional[str] = None

        # Eagerly build the graph. The builder validates node instances
        # so any factory failure surfaces at adapter-construction time,
        # not mid-turn.
        self._graph = self._build_graph()

    # --- Streaming / hook surfaces ------------------------------------

    def __setattr__(self, name: str, value: Any) -> None:
        """Forward a small set of attribute assignments to every
        specialist so the pipeline's ``orchestrator.x = y`` lines reach
        the agent that actually runs.

        We can't do this via @property because the pipeline assigns
        these values unconditionally; __setattr__ is the least invasive
        hook. Unknown attributes fall through to normal object storage.
        """
        super().__setattr__(name, value)
        # Guard: during __init__, _specialists may not exist yet. The
        # inner attributes are set on the adapter only; specialists get
        # synced once they're built.
        specialists = self.__dict__.get("_specialists")
        if not specialists:
            return
        if name in ("callback_handler", "trace_attributes", "session_manager"):
            for agent in specialists.values():
                try:
                    setattr(agent, name, value)
                except Exception as exc:
                    logger.debug("GraphAdapter forward %s to specialist failed: %s", name, exc)

    def add_hook(self, hook: Callable) -> None:
        """Forward a Strands hook to every specialist.

        Strands' ``add_hook`` registers the hook on the agent's
        registry; forwarding it to each specialist means tool lifecycle
        events fire from whichever specialist the graph routes to.
        """
        for agent in self._specialists.values():
            try:
                agent.add_hook(hook)
            except Exception as exc:
                logger.warning("GraphAdapter add_hook on specialist failed: %s", exc)

    # --- Graph construction -------------------------------------------

    def _build_graph(self):
        """Assemble the router + specialists into a conditional graph.

        Five edges from router → specialist, each gated on the router's
        output matching the specialist's key. Exactly one edge fires per
        turn. The graph has no edges between specialists; the pattern is
        explicitly a fan-out from one decision, not a chain.
        """
        # Lazy import to avoid hard-failing module load when the
        # installed Strands version doesn't ship the GraphBuilder yet.
        from strands.multiagent import GraphBuilder

        builder = GraphBuilder()
        builder.add_node(self._router, "router")

        for route_key, agent in self._specialists.items():
            builder.add_node(agent, route_key)

        def _route_matches(key: str):
            """Condition factory. Reads the router node's result from
            ``GraphState.results`` and returns True iff the router's
            normalized token equals ``key``.
            """
            def condition(state) -> bool:
                router_result = state.results.get("router")
                if router_result is None:
                    return False
                # router_result.get_agent_results() returns a list of
                # AgentResult; the router only has one cycle so len==1.
                agent_results = router_result.get_agent_results()
                if not agent_results:
                    return False
                token = _extract_route(str(agent_results[0]))
                return token == key
            return condition

        for route_key in self._specialists.keys():
            builder.add_edge("router", route_key, condition=_route_matches(route_key))

        builder.set_entry_point("router")
        return builder.build()

    # --- Invocation ---------------------------------------------------

    def __call__(self, task: str, **kwargs: Any) -> Any:
        """Run the graph and return the winning specialist's result.

        Returns the specialist's raw ``AgentResult`` so that
        ``str(result)`` yields the specialist's prose directly — which
        is the same contract ``Agent(__call__)`` satisfies. If no
        specialist ran (e.g., all conditions false because the router
        produced an unparseable token — which shouldn't happen given
        ``_extract_route``'s fallback), we return the router's result
        as a last-resort pass-through so the pipeline still has text
        to stream.
        """
        graph_result = self._graph(task, **kwargs)

        # Prefer the specialist result. Iterate in ``execution_order``
        # so we surface whichever specialist actually ran (there should
        # be exactly one given the conditional edges, but the loop is
        # defensive against future multi-specialist topologies).
        for node in graph_result.execution_order:
            if node.node_id == "router":
                continue
            node_result = graph_result.results.get(node.node_id)
            if node_result is None:
                continue
            self.last_route = node.node_id
            agent_results = node_result.get_agent_results()
            if agent_results:
                return agent_results[0]

        # No specialist executed — fall back to the router's own output.
        # Not great UX, but better than a silent empty bubble, and the
        # warning above already logged the routing failure.
        router_result = graph_result.results.get("router")
        if router_result is not None:
            agent_results = router_result.get_agent_results()
            if agent_results:
                self.last_route = "router"
                return agent_results[0]

        # Truly empty — return a minimal object whose str() produces a
        # short fallback. The pipeline's empty-response guard will
        # replace this with a generic line if products also missed.
        return _EmptyResult()


class _EmptyResult:
    """Fallback result when the graph produced nothing usable.

    Mirrors just enough of ``AgentResult`` for the pipeline's
    ``str(orchestrator_result[0])`` call to succeed without raising.
    """

    def __str__(self) -> str:
        return ""


def build_graph_orchestrator() -> GraphAgentAdapter:
    """Public factory. Kept as a thin wrapper so chat.py can import
    a single entry point; swapping the implementation (e.g., to a
    compiled graph or a cached instance) later is a one-line change.
    """
    return GraphAgentAdapter()
