#!/usr/bin/env python3
"""
Test AgentCore Gateway tool discovery — lists all MCP tools registered with the Gateway.

Usage:
    uv run test_gateway_tools.py \
      --gateway-url $GATEWAY_URL \
      --token "$TOKEN"
"""
import argparse
import os
import sys

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


EXPECTED_TOOLS = {
    "get_customer_preferences",
    "get_audit_trail",
    "check_inventory",
    "get_trending_products",
    "get_price_analysis",
    "restock_inventory",
    "initiate_return",
    "escalate_to_human",
    "search_products",
    "search_products_hybrid",
    "browse_category",
    "get_low_stock",
    "compare_products",
    "get_return_policy",
    "get_related_products",
}


def _canonical_name(name: str) -> str:
    """Strip AgentCore's target prefix from a discovered tool name."""
    return name.rsplit("__", 1)[-1]


async def _discover_gateway_tools(gateway_url: str, token: str):
    timeout = httpx.Timeout(30.0, read=300.0)
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
        follow_redirects=True,
    ) as http_client:
        async with streamable_http_client(
            gateway_url,
            http_client=http_client,
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return result.tools


def discover_gateway_tools(gateway_url: str, token: str):
    """Discover registered target tools, excluding Gateway's search helper."""
    tools = anyio.run(_discover_gateway_tools, gateway_url, token)
    return [
        tool for tool in tools
        if tool.name != "x_amz_bedrock_agentcore_search"
    ]


def list_gateway_tools(gateway_url: str, token: str):
    """Discover and display the exact Gateway MCP tool contract."""
    try:
        tools = discover_gateway_tools(gateway_url, token)
    except Exception as exc:
        print(f"ERROR: Could not discover Gateway MCP tools: {exc}")
        sys.exit(1)

    if not tools:
        print("ERROR: No tools discovered. Check that Lambda targets are registered.")
        sys.exit(1)

    # Group tools by server (inferred from tool naming conventions)
    print("Discovered tools:\n")
    for tool in sorted(tools, key=lambda item: item.name):
        name = tool.name
        desc = tool.description or ""
        # Truncate long descriptions for display
        if len(desc) > 80:
            desc = desc[:77] + "..."
        print(f"  - {name}")
        print(f"    {desc}")

    observed = {_canonical_name(tool.name) for tool in tools}
    missing = sorted(EXPECTED_TOOLS - observed)
    unexpected = sorted(observed - EXPECTED_TOOLS)
    print(f"\nTotal: {len(tools)} tools")
    if len(tools) != 15 or missing or unexpected:
        print("ERROR: Expected the governed 15-tool Gateway subset.")
        if missing:
            print(f"  Missing: {', '.join(missing)}")
        if unexpected:
            print(f"  Unexpected: {', '.join(unexpected)}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Test AgentCore Gateway tool discovery")
    parser.add_argument("--gateway-url", required=True, help="AgentCore Gateway URL")
    parser.add_argument("--token", required=True, help="JWT token for authentication")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"Gateway Tool Discovery")
    print(f"  Gateway: {args.gateway_url}")
    print(f"{'='*60}\n")

    list_gateway_tools(args.gateway_url, args.token)

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
