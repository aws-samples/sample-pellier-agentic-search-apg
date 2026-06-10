#!/usr/bin/env python3
"""Speak MCP to the managed AgentCore GATEWAY — same protocol, governed door.

Companion to ``mcp_handshake.py``. That script spoke MCP to a *local* process
over stdio. This one speaks the *same* protocol over **streamable HTTP** to the
managed **AgentCore Gateway**, authenticated with a real Cognito JWT. The
contract is identical (`initialize` -> `tools/list` -> `tools/call`); what
changed is the governance: the Gateway is JWT-gated, central, and
policy-filtered. That mirrors the Act II cloud beat — there the *agent* moved
behind a managed boundary; here the *tools* do.

This is a thin extract of the workshop's own production wiring in
``pellier/backend/services/agentcore_gateway.py`` (which uses the very same
``streamablehttp_client`` + Bearer-passthrough pattern), reduced to the
discovery + one read-only call so you can watch the frames.

Run (after signing in):

    source ~/pellier-token.sh        # sets $PELLIER_TOKEN
    python3 solutions/the-concierge/gateway_tools_list.py

Degrades gracefully: if the Gateway URL or a token is absent, it explains the
Atelier **Tool Registry (Card 7)** read-only fallback and exits 0 — this is an
optional "see it live" beat, never a hard gate.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Optional


def _gateway_url() -> Optional[str]:
    # The backend reads AGENTCORE_GATEWAY_URL; bootstrap also writes MCP_GATEWAY_URL.
    # Both hold the same get-gateway `gatewayUrl`. Use whichever is populated.
    for var in ("AGENTCORE_GATEWAY_URL", "MCP_GATEWAY_URL"):
        val = os.environ.get(var)
        if val:
            return val.strip()
    return None


def _token() -> Optional[str]:
    tok = os.environ.get("PELLIER_TOKEN")
    return tok.strip() if tok else None


def _pick_readonly_tool(tool_names: list[str]) -> Optional[tuple[str, dict]]:
    """Choose ONE safe read-only Gateway tool from the live list, by pattern.

    Gateway tools are exposed under their target-name prefix (e.g.
    ``pellier-discovery-search-target__semantic_search``). We prefer a
    read-oriented discovery/search/inventory tool and supply minimal arguments.
    Names drift, so match on substrings, never a hardcoded identifier. Returns
    (tool_name, arguments) or None.
    """
    lowered = {t.lower(): t for t in tool_names}

    # Prefer an obviously read-only search/find with a simple query arg.
    for key, real in lowered.items():
        if "semantic_search" in key or "find_pieces" in key or key.endswith("__search"):
            return real, {"query": "linen shirt"}

    # Next: an inventory/health read that often needs no args.
    for key, real in lowered.items():
        if "inventory_health" in key or "low_stock" in key or "trending" in key:
            return real, {}

    return None


def _print_result(result: Any) -> None:
    try:
        content = getattr(result, "content", None) or []
        for block in content:
            text = getattr(block, "text", None)
            if text is not None:
                snippet = text if len(text) <= 600 else text[:600] + " …(truncated)"
                print(f"    {snippet}")
                return
        print(f"    {result}")
    except Exception:  # noqa: BLE001
        print(f"    {result!r}")


async def _run(url: str, token: str) -> int:
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError:
        print("⚠  The `mcp` Python SDK isn't importable here — skipping the live")
        print("   Gateway handshake. (It ships with the backend venv via strands.)")
        print("   The Atelier Tool Registry (Card 7) shows the same discovery result.")
        return 0

    headers = {"Authorization": f"Bearer {token}"}
    print(f"→ connecting to the managed Gateway over streamable HTTP")
    print(f"  (Authorization: Bearer <your Cognito token>)\n")

    try:
        # NOTE: the exact URL the Gateway expects (bare gatewayUrl vs a /mcp
        # suffix) is what the backend passes verbatim to streamablehttp_client;
        # confirm on-box. terminate_on_close=False matches the neptune template.
        async with streamablehttp_client(url, headers, timeout=120, terminate_on_close=False) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print("✓ initialize → the managed Gateway accepted your JWT and")
                print("  answered the handshake\n")

                print("=== tools/list — discovered over the managed Gateway ===")
                tools_result = await session.list_tools()
                tool_names = [t.name for t in tools_result.tools]
                for t in tools_result.tools:
                    desc = (t.description or "").splitlines()[0] if t.description else ""
                    print(f"  • {t.name}: {desc}")
                print(f"\n  ({len(tool_names)} tools, discovered at runtime — not compiled into the agent.)\n")

                pick = _pick_readonly_tool(tool_names)
                if not pick:
                    print("  (No recognizably-safe read-only tool to call; the")
                    print("   JWT-gated tools/list above is the proof.)")
                    return 0

                tool_name, args = pick
                print(f"=== tools/call {tool_name}({json.dumps(args)}) — through the managed door ===")
                call_result = await session.call_tool(tool_name, args)
                _print_result(call_result)
                print()
                print("Same protocol you spoke to the local process — now fronted by a")
                print("managed, JWT-gated Gateway. The contract didn't change; the")
                print("governance did. (Act II moved the agent to the cloud; this moves")
                print("the tools.)")
                return 0
    except Exception as exc:  # noqa: BLE001 — optional beat; never scary-fail
        msg = str(exc)
        print(f"⚠  Gateway handshake didn't complete: {msg}")
        if "401" in msg or "403" in msg or "Unauthorized" in msg:
            print("   That looks like an auth issue — re-run `source ~/pellier-token.sh`")
            print("   to mint a fresh token (they last ~1h), then try again.")
        print("   This is optional. The Atelier Tool Registry (Card 7) shows the")
        print("   same GATEWAY · DISCOVER result without the live call.")
        return 0


def main() -> int:
    url = _gateway_url()
    if not url:
        print("⚠  No Gateway URL in the environment (AGENTCORE_GATEWAY_URL / MCP_GATEWAY_URL).")
        print("   The managed Gateway wasn't provisioned in this environment, so this")
        print("   live beat is unavailable — read the Atelier Tool Registry (Card 7)")
        print("   instead; it shows the same tool-discovery result. Skipping.")
        return 0

    token = _token()
    if not token:
        print("⚠  $PELLIER_TOKEN is not set. The Gateway is JWT-gated, so a live")
        print("   tools/list needs a token. Mint one and retry:")
        print("     source ~/pellier-token.sh")
        print("     python3 solutions/the-concierge/gateway_tools_list.py")
        print("   (Or read the Atelier Tool Registry / Card 7 for the same result.)")
        return 0

    return asyncio.run(_run(url, token))


if __name__ == "__main__":
    sys.exit(main())
