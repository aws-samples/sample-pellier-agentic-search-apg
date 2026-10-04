#!/usr/bin/env python3
"""Invoke any Gateway tool through the real MCP path and classify the outcome.

Call an arbitrary tool, including one no policy names, and report exactly what
the service said. Lab 3 uses it to show that Theo's token reads his own
tickets and is refused Jessica's; Lab 4 uses it for the credit decisions.

The classifier is imported from ``gateway_client`` rather than reimplemented.
It distinguishes a Cedar DENY from a transport, JWT, or tool-name failure, and
a second copy would eventually disagree with it and turn a broken Gateway into
a fake policy proof.

The tool name is an argument precisely so this file does not have to name whichever
vocabulary is currently live:

    PY=pellier/backend/.venv/bin/python
    $PY scripts/probe_gateway_tool.py --tool "$TOOL" \\
        --args '{"customer_id":"CUST-THEO"}'
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "deploy"))

import anyio  # noqa: E402
import httpx  # noqa: E402
from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

from gateway_client import (  # noqa: E402
    _exception_summary,
    _is_authorization_denial,
    _jsonable,
    _load_env,
    _require,
    _token_from_cognito,
    _verified_identity,
)


async def _call(gateway_url: str, token: str, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    timeout = httpx.Timeout(30.0, read=120.0)
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
        follow_redirects=True,
    ) as http_client:
        async with streamable_http_client(gateway_url, http_client=http_client) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                catalog = await session.list_tools()
                names = sorted(t.name for t in catalog.tools)
                result = await session.call_tool(tool, args)
                serialized = _jsonable(result)
                outcome = "allow"
                if serialized.get("isError"):
                    message = " ".join(str(item.get("text", "")) for item in serialized.get("content", []))
                    outcome = "policy_denied" if _is_authorization_denial(RuntimeError(message)) else "error"
                return {
                    "outcome": outcome,
                    "tool": tool,
                    "arguments": args,
                    "gatewayCatalog": names,
                    "result": serialized,
                }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--args", default="{}", help="JSON object of tool arguments")
    parser.add_argument("--gateway-url", default="")
    parser.add_argument("--user", default="", help="Mint a token for this workshop Cognito user")
    parser.add_argument("--expect", choices=("allow", "policy_denied"), help="Fail unless this exact outcome occurs")
    args = parser.parse_args()

    _load_env()
    gateway_url = args.gateway_url or _require("AGENTCORE_GATEWAY_URL")

    # Explicit environment wins over a local .env, and the principal is never
    # guessed: this script's entire output is a claim about what one identity was
    # allowed to do. Minting Marco's token because PELLIER_TOKEN was exported and
    # --user was not passed produces a transcript that reads like a proof about
    # someone else. An identity-source ambiguity is an error, not a default.
    preset_token = os.environ.get("PELLIER_TOKEN", "").strip()
    if preset_token and args.user:
        raise SystemExit(
            "Refusing to guess the principal: --user "
            f"{args.user!r} and PELLIER_TOKEN both name an identity.\n"
            "  Use one:\n"
            f"    --user {args.user}          mint a fresh token for that Cognito user\n"
            "    unset PELLIER_TOKEN     then re-run with --user\n"
            "    (or drop --user)        to use the token already in the environment"
        )
    token = preset_token or _token_from_cognito(args.user)
    identity = _verified_identity(token)
    tool_args = json.loads(args.args)

    try:
        payload = anyio.run(_call, gateway_url, token, args.tool, tool_args)
    except BaseException as exc:  # noqa: BLE001 - the outcome IS the result here
        summary = _exception_summary(exc)
        payload = {
            # A denial and a broken Gateway must never print the same word.
            "outcome": "policy_denied" if _is_authorization_denial(exc) else "error",
            "tool": args.tool,
            "arguments": tool_args,
            "serviceResponse": summary,
        }

    # Name the principal in the payload. A reader should never have to infer
    # whose token produced an ALLOW or a DENY.
    payload["identity"] = identity
    print(json.dumps(payload, indent=2, default=str))
    expected = {args.expect} if args.expect else {"allow", "policy_denied"}
    return 0 if payload["outcome"] in expected else 1


if __name__ == "__main__":
    sys.exit(main())
