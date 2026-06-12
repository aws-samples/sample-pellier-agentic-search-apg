#!/usr/bin/env python3
"""Speak MCP on the wire to the LOCAL Postgres MCP server (Act III, page 02).

The MCP page lets you *read* the config and *see* a static `tools/call` frame.
This script makes the protocol real: it spawns the same AWS Labs Postgres MCP
server the config describes, performs the JSON-RPC handshake over **stdio**
(`initialize` -> `notifications/initialized`), lists the tools the server
advertises, then calls ONE read-only tool so you get an actual result back
over the wire. No diagram — the frames.

It deliberately reuses the generated ``pellier/config/mcp-server-config.json``
(the artifact you just `cat`-ed) as the source of truth for the server command
and args, so this script proves the *same* server that config wires up.

Run (from the repo root, after the lab is provisioned):

    python3 solutions/the-concierge/mcp_handshake.py

Read-only + safe: the server is launched with ``--readonly True`` and the only
tool call is a trivial SELECT-style probe. Nothing is written.

Requires the ``mcp`` Python SDK (present in the backend venv via strands). If a
piece is missing it prints a clear, non-scary message and exits 0 — this is an
optional "see it live" beat, never a hard gate.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Locate the generated MCP config — the same file the lab teaches you to cat.
# ---------------------------------------------------------------------------
def _find_config() -> Optional[Path]:
    # repo_root/solutions/the-concierge/this_file -> repo_root
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "pellier" / "config" / "mcp-server-config.json",
        Path("/workshop/sample-pellier-agentic-search-apg/pellier/config/mcp-server-config.json"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _load_local_server(config_path: Path) -> Optional[dict]:
    try:
        data = json.loads(config_path.read_text())
    except Exception as exc:  # noqa: BLE001 — surface a friendly message, not a trace
        print(f"⚠  Could not parse {config_path}: {exc}")
        return None
    servers = data.get("mcpServers", {})
    # The lab registers exactly one: awslabs.postgres-mcp-server.
    for name, cfg in servers.items():
        if cfg.get("command"):
            return {"name": name, **cfg}
    return None


def _pick_readonly_tool(tool_names: list[str]) -> Optional[tuple[str, dict]]:
    """Choose ONE safe read-only tool from the live list, by pattern — never a
    hardcoded name (tool names drift across MCP-server versions). Prefer a
    raw-SQL runner so we can issue a trivial ``SELECT 1``; otherwise fall back
    to a schema/table-listing tool that needs no arguments.

    Returns (tool_name, arguments) or None if nothing safe is recognized.
    """
    lowered = {t.lower(): t for t in tool_names}

    # 1) A SQL runner — issue a harmless read-only query.
    for key, real in lowered.items():
        if "query" in key or key in ("run_query", "readonly_query", "execute_query"):
            return real, {"sql": "SELECT 1 AS mcp_live"}

    # 2) A no-arg schema/listing tool.
    for key, real in lowered.items():
        if any(tok in key for tok in ("list_tables", "get_table", "schema", "list_schemas")):
            return real, {}

    return None


def _print_result(result: Any) -> None:
    """Best-effort pretty-print of a CallToolResult's content."""
    try:
        content = getattr(result, "content", None) or []
        for block in content:
            text = getattr(block, "text", None)
            if text is not None:
                print(f"    {text}")
                return
        print(f"    {result}")
    except Exception:  # noqa: BLE001
        print(f"    {result!r}")


async def _run(server: dict) -> int:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        print("⚠  The `mcp` Python SDK isn't importable here — skipping the live")
        print("   handshake. (It ships with the backend venv via strands; run this")
        print("   from the repo with that environment active.) Nothing is broken;")
        print("   this is an optional 'see it live' beat.")
        return 0

    params = StdioServerParameters(
        command=server["command"],
        args=server.get("args", []),
        env={**os.environ, **server.get("env", {})},
    )

    print(f"→ launching local MCP server: {server['name']}")
    print(f"  ({server['command']} {' '.join(server.get('args', [])[:1])} … read-only by default)\n")

    try:
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # The JSON-RPC handshake — this is the wire moment.
                await session.initialize()
                print("✓ initialize → the server answered the handshake\n")

                print("=== tools/list — what this server advertises ===")
                tools_result = await session.list_tools()
                tool_names = [t.name for t in tools_result.tools]
                for t in tools_result.tools:
                    desc = (t.description or "").splitlines()[0] if t.description else ""
                    print(f"  • {t.name}: {desc}")
                print()

                pick = _pick_readonly_tool(tool_names)
                if not pick:
                    print("  (No recognizably-safe read-only tool to call; the")
                    print("   tools/list above is itself the proof you spoke MCP.)")
                    return 0

                tool_name, args = pick
                print(f"=== tools/call {tool_name}({json.dumps(args)}) — a real round-trip ===")
                call_result = await session.call_tool(tool_name, args)
                _print_result(call_result)
                print()
                print("That JSON-RPC exchange — initialize, tools/list, tools/call —")
                print("IS the Model Context Protocol. Not a diagram: the wire.")
                return 0
    except Exception as exc:  # noqa: BLE001 — optional beat; never scary-fail
        print(f"⚠  Live handshake didn't complete: {exc}")
        print("   This is optional. The config you read + `uvx … --help` already")
        print("   show the server is real; this just exchanges the frames live.")
        return 0


def main() -> int:
    config_path = _find_config()
    if not config_path:
        print("⚠  mcp-server-config.json not found. It's generated at bootstrap")
        print("   (pellier/backend/generate_mcp_config.py). Run the lab's bootstrap")
        print("   first, or `cat` the config per the Act III page. Skipping.")
        return 0

    server = _load_local_server(config_path)
    if not server:
        print(f"⚠  No runnable MCP server found in {config_path}. Skipping.")
        return 0

    return asyncio.run(_run(server))


if __name__ == "__main__":
    sys.exit(main())
