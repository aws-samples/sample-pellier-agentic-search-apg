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


def _launch_args_map(server: dict) -> dict[str, str]:
    """Parse the server's launch ``args`` (``--flag value`` pairs) into a dict,
    so a tool that re-declares connection params as PER-CALL arguments can be
    fed the same values the server was configured with. Example keys:
    ``connection_method``, ``db_cluster_arn``, ``secret_arn``, ``database``,
    ``region``.
    """
    out: dict[str, str] = {}
    args = server.get("args", [])
    i = 0
    while i < len(args):
        a = args[i]
        if isinstance(a, str) and a.startswith("--"):
            flag = a[2:]
            if i + 1 < len(args) and not str(args[i + 1]).startswith("--"):
                out[flag] = str(args[i + 1])
                i += 2
                continue
            out[flag] = "true"  # bare boolean flag
        i += 1
    return out


# ConnectionMethod is a ``str``-Enum whose NAME (e.g. ``RDS_API``) is what the
# server's launch flag ``--connection_method`` takes, but whose VALUE
# (``rdsapi``) is what a per-call tool argument coerces to through pydantic.
# The two halves disagree on casing, so map name -> value here.
_CONNECTION_METHOD_VALUE = {
    "RDS_API": "rdsapi",
    "PG_WIRE_PROTOCOL": "pgwire",
    "PG_WIRE_IAM_PROTOCOL": "pgwire_iam",
}


def _fill_required_connection_args(
    input_schema: dict,
    launch: dict[str, str],
    discovered: Optional[dict] = None,
) -> dict:
    """The 1.0.11+ postgres-mcp-server declares the connection params
    (``connection_method``, ``database_type``, ``cluster_identifier``,
    ``db_endpoint``, ``database``, ``region``, ``port``) as PER-CALL tool
    inputs, not just server-launch flags. Populate the ones this tool's live
    ``inputSchema`` actually advertises. Schema-driven so it survives version
    drift: we only add a key the schema lists as a property AND we have a
    value for.

    A per-call ``run_query`` only succeeds if its
    ``(method, cluster_identifier, db_endpoint, database, port)`` arguments
    reproduce the EXACT key the server stored the connection under. On the RDS
    Data API path the server rewrites ``db_endpoint`` to the cluster's
    AWS-resolved writer hostname before keying the map (server.py
    ``internal_create_connection``), so that value is NOT reconstructable from
    the launch flags. ``discovered`` carries the real key fields read back from
    the ``get_database_connection_info`` tool and is therefore authoritative;
    the launch flags are only a fallback for fields the introspection didn't
    return. ``connection_method`` is the enum VALUE (``rdsapi``), not the
    launch NAME (``RDS_API``) — a per-call argument coerces by value.
    """
    props = (input_schema or {}).get("properties", {}) or {}
    discovered = discovered or {}
    arn = launch.get("db_cluster_arn", "") or ""
    cluster_identifier = arn.split(":")[-1] if arn else ""
    cm_launch = launch.get("connection_method", "RDS_API")
    cm_value = _CONNECTION_METHOD_VALUE.get(cm_launch, cm_launch.lower())
    resolvers: dict[str, Any] = {
        "connection_method": discovered.get("connection_method", cm_value),
        "database_type": launch.get("db_type", "APG"),
        "cluster_identifier": discovered.get("cluster_identifier", cluster_identifier),
        "db_cluster_arn": arn,
        "db_endpoint": discovered.get("db_endpoint", "") or "",
        "database": discovered.get("database") or launch.get("database", "postgres"),
        "secret_arn": launch.get("secret_arn", ""),
        "region": launch.get("region", ""),
        "port": int(discovered.get("port", launch.get("port", "5432")) or 5432),
    }
    extra: dict[str, Any] = {}
    for field, value in resolvers.items():
        if field in props:
            extra[field] = value
    return extra


def _find_tool(tools: list, *name_substrings: str):
    """Return the first live tool whose lowercased name contains any of the
    given substrings, or None. Pattern-matched (never a hardcoded name) so it
    survives tool-name drift across MCP-server versions."""
    for tool in tools:
        low = tool.name.lower()
        if any(sub in low for sub in name_substrings):
            return tool
    return None


def _parse_discovered_key(text: str) -> Optional[dict]:
    """Parse the JSON returned by ``get_database_connection_info`` and return
    the first registered connection's key fields, or None. The server
    serializes each key as ``{connection_method, cluster_identifier,
    db_endpoint, database, port}`` (the enum is rendered as its VALUE,
    e.g. ``rdsapi``), which is exactly what a per-call ``run_query`` needs to
    reproduce the lookup key."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    if isinstance(data, dict) and data.get("cluster_identifier"):
        return data
    return None


def _pick_readonly_tool(
    tools: list, launch: dict[str, str], discovered: Optional[dict] = None
) -> Optional[tuple[str, dict]]:
    """Choose ONE safe read-only tool from the live list, by pattern — never a
    hardcoded name (tool names drift across MCP-server versions). Prefer a
    raw-SQL runner so we can issue a trivial ``SELECT 1``; otherwise fall back
    to a schema/table-listing tool that needs no arguments.

    ``tools`` is the live list of Tool objects (so we can read each one's
    ``inputSchema`` and satisfy any required per-call connection args).
    ``discovered`` is the real registered connection key (from
    ``get_database_connection_info``) and is authoritative for the per-call
    connection arguments. Returns (tool_name, arguments) or None.
    """
    by_lower = {t.name.lower(): t for t in tools}

    def _schema(tool) -> dict:
        return getattr(tool, "inputSchema", None) or {}

    # 1) A SQL runner – issue a harmless read-only query, plus whatever
    #    connection args this version declares as required per call.
    for key, tool in by_lower.items():
        if "query" in key or key in ("run_query", "readonly_query", "execute_query"):
            args: dict[str, Any] = {"sql": "SELECT 1 AS mcp_live"}
            args.update(_fill_required_connection_args(_schema(tool), launch, discovered))
            return tool.name, args

    # 2) A no-arg (or connection-arg-only) schema/listing tool.
    for key, tool in by_lower.items():
        if any(tok in key for tok in ("list_tables", "get_table", "schema", "list_schemas")):
            return tool.name, _fill_required_connection_args(_schema(tool), launch, discovered)

    return None


def _result_text(result: Any) -> Optional[str]:
    """Pull the first text block out of a CallToolResult, or None. Used both to
    print a tool result and to parse the introspection tool's JSON."""
    try:
        content = getattr(result, "content", None) or []
        for block in content:
            text = getattr(block, "text", None)
            if text is not None:
                return text
    except Exception:  # noqa: BLE001
        return None
    return None


def _print_result(result: Any) -> None:
    """Best-effort pretty-print of a CallToolResult's content."""
    text = _result_text(result)
    if text is not None:
        print(f"    {text}")
        return
    print(f"    {result}")


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
                for t in tools_result.tools:
                    desc = (t.description or "").splitlines()[0] if t.description else ""
                    print(f"  • {t.name}: {desc}")
                print()

                # The 1.0.11+ servers declare the connection params as per-call
                # tool args AND key the live connection under the cluster's
                # AWS-resolved writer endpoint (which we can't reconstruct from
                # the launch flags). So ask the server for its own registered
                # key via get_database_connection_info, and feed those exact
                # values to run_query. Falls back to the launch flags if the
                # tool isn't advertised (older servers).
                launch = _launch_args_map(server)
                discovered: Optional[dict] = None
                info_tool = _find_tool(tools_result.tools, "connection_info", "database_connection")
                if info_tool is not None:
                    try:
                        info_result = await session.call_tool(info_tool.name, {})
                        info_text = _result_text(info_result)
                        discovered = _parse_discovered_key(info_text or "")
                        if discovered:
                            print(f"✓ {info_tool.name} → registered connection:")
                            print(f"    {json.dumps(discovered)}\n")
                    except Exception as exc:  # noqa: BLE001 — introspection is best-effort
                        print(f"  ({info_tool.name} unavailable: {exc}; using launch flags)\n")

                pick = _pick_readonly_tool(tools_result.tools, launch, discovered)
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
