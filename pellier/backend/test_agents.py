#!/usr/bin/env python3
"""
Test Pellier agents from the terminal.

Runs sample queries against individual agents and the orchestrator,
printing response quality metrics (tool calls, product count, latency).

Usage:
    cd pellier/backend
    uv run test_agents.py                          # run all test queries
    uv run test_agents.py --agent orchestrator     # test orchestrator only
    uv run test_agents.py --agent recommendation   # test recommendation agent only
    uv run test_agents.py --agent pricing          # test pricing agent only
    uv run test_agents.py --agent inventory        # test inventory agent only
    uv run test_agents.py --agent single           # test single-agent (Lab 2) mode
    uv run test_agents.py --query "Find me laptops under $500"  # custom query
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time
import re

# Ensure backend/ is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Suppress noisy logs — show only our output
logging.getLogger("strands").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("services").setLevel(logging.WARNING)
logging.basicConfig(level=logging.WARNING)

# ── Test queries ────────────────────────────────────────────────────────
RECOMMENDATION_QUERIES = [
    "Show me running shoes",
    "Find laptops under $800",
    "I need a gift for someone who likes cooking",
    "What sunglasses do you have?",
    "Electronics under $200",
]

PRICING_QUERIES = [
    "What are the best deals right now?",
    "Compare prices across electronics",
    "Find me the cheapest watches",
    "Budget laptops under $500",
    "What's the price range for shoes?",
]

INVENTORY_QUERIES = [
    "What items are low on stock?",
    "Show me inventory health",
    "Which products need restocking?",
]

SINGLE_AGENT_QUERIES = [
    "Show me trending products",
    "Find me watches under $100",
    "What electronics do you have?",
    "Shoes with good ratings",
]

ORCHESTRATOR_QUERIES = [
    "Show me running shoes under $100",
    "What's trending right now?",
    "Find me the cheapest laptops",
    "What items are low on stock?",
    "I need sunglasses under $50",
]


# ── Helpers ─────────────────────────────────────────────────────────────
def extract_products_from_response(text: str) -> list:
    """Pull product JSON from agent response text."""
    # Try JSON code blocks first
    for pattern in [r'```json\s*(\[[\s\S]*?\])\s*```', r'```\s*(\[[\s\S]*?\])\s*```']:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    # Try raw JSON parse
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "products" in data:
            return data["products"]
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def score_response(text: str, products: list, latency_ms: int, query: str) -> dict:
    """Score a response on multiple quality dimensions."""
    has_text = bool(text.strip()) and len(text.strip()) > 5
    has_products = len(products) > 0
    text_short = len(text.split()) <= 60  # should be concise
    no_apology = not any(w in text.lower() for w in ["apologize", "sorry", "unfortunately"])
    no_unavailable = not any(w in text.lower() for w in ["unavailable", "being refreshed", "updating"])
    no_markdown_table = "|" not in text or text.count("|") < 4
    reasonable_latency = latency_ms < 15000

    score = sum([has_text, has_products, text_short, no_apology,
                 no_unavailable, no_markdown_table, reasonable_latency])
    return {
        "score": f"{score}/7",
        "has_text": has_text,
        "has_products": has_products,
        "product_count": len(products),
        "concise": text_short,
        "no_apology": no_apology,
        "no_unavailable_claim": no_unavailable,
        "no_markdown_table": no_markdown_table,
        "latency_ok": reasonable_latency,
    }


# ── DB bootstrap ────────────────────────────────────────────────────────
async def bootstrap():
    """Connect to Aurora and wire the database service into agent_tools."""
    from services.database import DatabaseService
    from services.agent_tools import set_db_service

    db = DatabaseService()
    await db.connect()
    set_db_service(db)

    # Verify connectivity
    row = await db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM pellier.product_catalog"
    )
    count = row["cnt"] if row else "?"
    print(f"  Database connected — {count} products in catalog\n")

    return db


# ── Test runners ────────────────────────────────────────────────────────
def run_agent_query(agent, query: str) -> dict:
    """Run a single query and return structured results."""
    start = time.time()
    try:
        result = agent(query)
        text = str(result)
    except Exception as e:
        text = f"ERROR: {e}"
    latency_ms = int((time.time() - start) * 1000)
    products = extract_products_from_response(text)
    scores = score_response(text, products, latency_ms, query)
    return {
        "query": query,
        "response_text": text[:300],
        "products": products,
        "latency_ms": latency_ms,
        "scores": scores,
    }


def print_result(r: dict):
    """Pretty-print a single test result."""
    s = r["scores"]
    product_names = [p.get("name") or p.get("product_description", "?") for p in r["products"][:3]]
    status = "PASS" if int(s["score"].split("/")[0]) >= 5 else "WARN" if int(s["score"].split("/")[0]) >= 3 else "FAIL"
    icon = {"PASS": "\u2705", "WARN": "\u26a0\ufe0f ", "FAIL": "\u274c"}[status]

    print(f"  {icon} [{s['score']}] {r['query']}")
    print(f"     Latency: {r['latency_ms']}ms | Products: {s['product_count']}")
    if product_names:
        print(f"     Sample:  {', '.join(product_names)}")
    # Show first 150 chars of response text
    snippet = r["response_text"][:150].replace("\n", " ")
    print(f"     Text:    {snippet}")
    if not s["no_apology"]:
        print(f"     FLAG:    Contains apology language")
    if not s["no_unavailable_claim"]:
        print(f"     FLAG:    Claims products unavailable")
    if not s["no_markdown_table"]:
        print(f"     FLAG:    Contains markdown table")
    print()


def test_agent(name: str, create_fn, queries: list):
    """Test an agent with a list of queries."""
    print(f"\n{'='*70}")
    print(f"  TESTING: {name}")
    print(f"{'='*70}\n")

    agent = create_fn()
    if agent is None:
        print(f"  SKIP: {name} returned None (not implemented yet)\n")
        return []

    results = []
    for q in queries:
        r = run_agent_query(agent, q)
        print_result(r)
        results.append(r)

    # Summary
    total = len(results)
    passed = sum(1 for r in results if int(r["scores"]["score"].split("/")[0]) >= 5)
    avg_latency = sum(r["latency_ms"] for r in results) // max(total, 1)
    avg_products = sum(r["scores"]["product_count"] for r in results) / max(total, 1)
    print(f"  Summary: {passed}/{total} passed | avg latency {avg_latency}ms | avg products {avg_products:.1f}")
    print()
    return results


def create_single_agent():
    """Create a single-agent (Lab 2 mode) for testing."""
    from strands import Agent
    from strands.models.bedrock import BedrockModel
    from services.agent_tools import find_pieces, whats_trending, price_intelligence
    from config import settings

    # Import the prompt from chat.py
    from services.chat import SINGLE_AGENT_PROMPT

    return Agent(
        model=BedrockModel(model_id=settings.BEDROCK_CHAT_MODEL, max_tokens=8192, temperature=0.0),
        system_prompt=SINGLE_AGENT_PROMPT,
        tools=[find_pieces, whats_trending, price_intelligence],
    )


def create_recommendation():
    from agents.curator import recommendation
    class _Wrapper:
        def __call__(self, query):
            return recommendation(query)
    return _Wrapper()


def create_pricing():
    from agents.value_analyst import pricing
    class _Wrapper:
        def __call__(self, query):
            return pricing(query)
    return _Wrapper()


def create_inventory():
    from agents.stock_keeper import inventory
    class _Wrapper:
        def __call__(self, query):
            return inventory(query)
    return _Wrapper()


# ── Main ────────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(description="Test Pellier agents from the terminal")
    parser.add_argument("--agent", choices=["all", "orchestrator", "recommendation", "pricing", "inventory", "single"],
                        default="all", help="Which agent to test (default: all)")
    parser.add_argument("--query", type=str, default=None,
                        help="Run a single custom query against the selected agent")
    args = parser.parse_args()

    print("\n" + "="*70)
    print("  Pellier Agent Test Suite")
    print("="*70 + "\n")

    print("  Bootstrapping database connection...")
    db = await bootstrap()

    all_results = {}

    if args.query:
        # Custom query mode — run against specified agent
        agent_name = args.agent if args.agent != "all" else "orchestrator"
        creators = {
            "orchestrator": ("Orchestrator", lambda: __import__("agents.orchestrator", fromlist=["create_orchestrator"]).create_orchestrator()),
            "recommendation": ("Recommendation Agent", create_recommendation),
            "pricing": ("Pricing Agent", create_pricing),
            "inventory": ("Inventory Agent", create_inventory),
            "single": ("Single Agent (Lab 2)", create_single_agent),
        }
        name, create_fn = creators[agent_name]
        all_results[agent_name] = test_agent(name, create_fn, [args.query])
    else:
        # Full suite
        tests = {
            "orchestrator": ("Orchestrator", lambda: __import__("agents.orchestrator", fromlist=["create_orchestrator"]).create_orchestrator(), ORCHESTRATOR_QUERIES),
            "recommendation": ("Recommendation Agent", create_recommendation, RECOMMENDATION_QUERIES),
            "pricing": ("Pricing Agent", create_pricing, PRICING_QUERIES),
            "inventory": ("Inventory Agent", create_inventory, INVENTORY_QUERIES),
            "single": ("Single Agent (Lab 2)", create_single_agent, SINGLE_AGENT_QUERIES),
        }

        for key, (name, create_fn, queries) in tests.items():
            if args.agent == "all" or args.agent == key:
                all_results[key] = test_agent(name, create_fn, queries)

    # Final summary
    print("\n" + "="*70)
    print("  FINAL SUMMARY")
    print("="*70)
    for key, results in all_results.items():
        total = len(results)
        passed = sum(1 for r in results if int(r["scores"]["score"].split("/")[0]) >= 5)
        print(f"  {key:20s}: {passed}/{total} passed")
    print("="*70 + "\n")

    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
