"""
Graph Orchestrator — Multi-agent DAG visualization using Strands 1.0.

Provides the graph structure (nodes + edges) for the orchestrator's
decision flow: Router → Recommendation | Pricing | Inventory (sequential routing).

If Strands GraphBuilder is available, uses it; otherwise returns a static
DAG structure for visualization purposes.
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Try importing Strands graph support
GRAPH_AVAILABLE = False
try:
    from strands.agent.graph import GraphBuilder  # type: ignore
    GRAPH_AVAILABLE = True
    logger.info("Strands GraphBuilder available — graph orchestrator enabled")
except ImportError:
    logger.info("Strands GraphBuilder not available — using static graph structure")


def get_graph_structure() -> Dict[str, Any]:
    """
    Return the multi-agent orchestrator graph structure.

    Nodes represent agents/decision points, edges represent data flow.
    This structure is used by the frontend GraphVisualization component.
    """
    nodes = [
        {
            "id": "router",
            "label": "Orchestrator",
            "type": "decision",
            "description": "Analyzes query intent and routes to one specialist agent",
            "model": "Claude Haiku 4.5",
        },
        {
            "id": "recommendation",
            "label": "Product Recommendation",
            "type": "agent",
            "description": "Trending products, personalized recommendations, and gift suggestions",
            "model": "Claude Opus 4.6",
        },
        {
            "id": "pricing",
            "label": "Price Optimization",
            "type": "agent",
            "description": "Price analysis, deals, and discount finder",
            "model": "Claude Opus 4.6",
        },
        {
            "id": "inventory",
            "label": "Inventory & Restock",
            "type": "agent",
            "description": "Stock levels, restocking, and availability",
            "model": "Claude Opus 4.6",
        },
        {
            "id": "support",
            "label": "Customer Support",
            "type": "agent",
            "description": "Return policies, troubleshooting, and general support",
            "model": "Claude Opus 4.6",
        },
        {
            "id": "search",
            "label": "Product Search",
            "type": "agent",
            "description": "Product search, category browsing, and product comparison",
            "model": "Claude Opus 4.6",
        },
    ]

    edges = [
        {"from": "router", "to": "recommendation", "label": "product queries"},
        {"from": "router", "to": "pricing", "label": "price queries"},
        {"from": "router", "to": "inventory", "label": "stock queries"},
        {"from": "router", "to": "support", "label": "support queries"},
        {"from": "router", "to": "search", "label": "search queries"},
    ]

    return {
        "available": True,
        "graph_builder_available": GRAPH_AVAILABLE,
        "nodes": nodes,
        "edges": edges,
        "description": (
            "The orchestrator routes each user query to one specialist agent. "
            "The Orchestrator (Haiku 4.5) classifies intent and dispatches to "
            "Recommendation, Pricing, Inventory, Customer Support, or Search "
            "(each running Opus 4.6)."
        ),
    }
