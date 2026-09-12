#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""Participant-facing client for retrieval Lab 1 and agent-extension Lab 2."""

from __future__ import annotations

import argparse
import json
import math
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = os.environ.get("PELLIER_BASE_URL", "http://localhost:8000")
DEFAULT_QUERY = "A housewarming gift under $100 that is in stock"


def _print_build_state_legend() -> None:
    """Explain workshop-only state labels without changing JSON stdout."""
    print(
        "Status legend: 'exercise' is an intentional workshop gap; "
        "'shipped' means the capability or agent grant is complete.",
        file=sys.stderr,
    )
    print(
        "Build state checks the implementation and grant, not database "
        "results. Run tool-check to prove the direct Aurora contract; "
        "Stock Keeper also needs floor_check in its tool list.",
        file=sys.stderr,
    )


def _url(base_url: str, path: str, query: dict[str, str] | None = None) -> str:
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    return url


def _request_json(
    base_url: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    timeout: int = 75,
) -> dict[str, Any]:
    request = urllib.request.Request(
        _url(base_url, path, query),
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"{path} failed: {exc}") from exc


def _stream_chat(
    base_url: str,
    payload: dict[str, Any],
    *,
    session_token: str,
    output_path: Path,
    timeout: int = 75,
) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        _url(base_url, "/api/chat/stream"),
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "X-Pellier-Session-Token": session_token,
        },
    )
    events: list[dict[str, Any]] = []
    try:
        with (
            urllib.request.urlopen(request, timeout=timeout) as response,
            output_path.open("w", encoding="utf-8") as output,
        ):
            for raw_line in response:
                line = raw_line.decode("utf-8")
                output.write(line)
                if not line.startswith("data: "):
                    continue
                try:
                    events.append(json.loads(line.removeprefix("data: ")))
                except json.JSONDecodeError:
                    continue
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"/api/chat/stream failed: {exc}") from exc
    return events


def _last_complete(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        if event.get("type") == "complete":
            response = event.get("response")
            if isinstance(response, dict):
                return response
    raise RuntimeError("The chat stream ended without a complete event")


def readiness(args: argparse.Namespace) -> int:
    health = _request_json(args.base_url, "/api/health", timeout=10)
    build_state = _request_json(
        args.base_url,
        "/api/agent-trace/build-state",
        timeout=10,
    )
    version = subprocess.run(
        ["claude", "--version"],
        text=True,
        capture_output=True,
        check=False,
    )
    result = {
        "application": {
            "status": health.get("status"),
            "database": health.get("database"),
        },
        "claudeCode": {
            "version": version.stdout.strip() if version.returncode == 0 else None,
            "bedrockMode": os.environ.get("CLAUDE_CODE_USE_BEDROCK"),
            "model": os.environ.get("ANTHROPIC_MODEL"),
        },
        "exercise": {
            "Stock Keeper": (build_state.get("agents") or {}).get("Stock Keeper"),
            "floor_check": (build_state.get("tools") or {}).get("floor_check"),
        },
    }
    print(json.dumps(result, indent=2))
    _print_build_state_legend()
    ready = (
        result["application"]["status"] == "healthy"
        and result["application"]["database"] == "connected"
        and bool(result["claudeCode"]["version"])
        and result["claudeCode"]["bedrockMode"] == "1"
        # Pinned global profile — Workshop Studio does not expose Sonnet 5,
        # so the floating `sonnet` alias would resolve to a denied model.
        and result["claudeCode"]["model"] == "global.anthropic.claude-sonnet-4-6"
        and set(result["exercise"].values()) == {"exercise"}
    )
    if not ready:
        print("Readiness did not match the expected starter state.", file=sys.stderr)
        return 1
    return 0


def build_state(args: argparse.Namespace) -> int:
    payload = _request_json(
        args.base_url,
        "/api/agent-trace/build-state",
        timeout=10,
    )
    result = {
        "Stock Keeper": (payload.get("agents") or {}).get("Stock Keeper"),
        "floor_check": (payload.get("tools") or {}).get("floor_check"),
    }
    print(json.dumps(result, indent=2))
    _print_build_state_legend()
    expected_agent = args.expect_agent or args.expect
    expected_tool = args.expect_tool or args.expect
    if expected_agent is None or expected_tool is None:
        print(
            "Set --expect for both states or set both "
            "--expect-tool and --expect-agent.",
            file=sys.stderr,
        )
        return 2
    if (
        result["Stock Keeper"] != expected_agent
        or result["floor_check"] != expected_tool
    ):
        print(
            "Expected "
            f"Stock Keeper={expected_agent!r}, floor_check={expected_tool!r}.",
            file=sys.stderr,
        )
        return 1
    return 0


def tool_check(args: argparse.Namespace) -> int:
    payload = _request_json(
        args.base_url,
        "/api/agent-trace/tools/floor-check/run",
        query={"product_query": args.query},
        timeout=30,
    )
    print(json.dumps(payload, indent=2))
    if getattr(args, "expect_status", "success") != "success":
        return 0 if payload.get("status") == args.expect_status else 1
    brooklyn = next(
        (
            warehouse
            for warehouse in payload.get("warehouses", [])
            if warehouse.get("city") == "Brooklyn"
            or warehouse.get("warehouse_id") == "BK-01"
        ),
        None,
    )
    valid = (
        payload.get("status") == "success"
        and isinstance(brooklyn, dict)
        and isinstance(brooklyn.get("quantity"), int)
        and isinstance(brooklyn.get("ship_window_min"), int)
        and isinstance(brooklyn.get("ship_window_max"), int)
    )
    if not valid:
        print(
            "floor_check did not return the Brooklyn quantity and ship window.",
            file=sys.stderr,
        )
        return 1
    return 0


def retrieval_errors(payload: dict[str, Any], max_price: float) -> list[str]:
    """Check results independently of the participant's SQL expressions."""
    errors: list[str] = []
    rows = payload.get("rows")
    eligible = payload.get("eligibleCount")
    if not isinstance(rows, list) or not isinstance(eligible, int):
        return ["Expected rows and eligibleCount in the SQL output."]
    if len(rows) != min(5, eligible):
        errors.append("Return up to five eligible products; do not fill with ineligible rows.")
    if len({row["productId"] for row in rows}) != len(rows):
        errors.append("A product appears more than once after fusion.")
    previous = float("inf")
    for row in rows:
        if float(row["price"]) > max_price or int(row["quantity"]) <= 0:
            errors.append(f'{row["productId"]}: price or stock requirement failed.')
        ranks = [row.get(key) for key in ("vectorRank", "keywordRank")]
        if not any(isinstance(rank, int) and rank > 0 for rank in ranks):
            errors.append("Every result needs at least one positive branch rank.")
            continue
        if any(rank is not None and (not isinstance(rank, int) or rank < 1) for rank in ranks):
            errors.append("Branch ranks must be positive integers or null.")
            continue
        expected = sum(1.0 / (60 + rank) for rank in ranks if rank is not None)
        score = float(row["rrfScore"])
        if not math.isclose(score, expected, rel_tol=1e-8, abs_tol=1e-10):
            errors.append(f'{row["productId"]}: RRF score does not match its branch ranks.')
        if score > previous:
            errors.append("Results must be sorted by descending fused score.")
        previous = score
    return errors


def retrieval(args: argparse.Namespace) -> int:
    if not math.isfinite(args.max_price) or args.max_price < 0:
        raise RuntimeError("--max-price must be a finite, nonnegative number.")
    vector = ""
    source = "stored candle vector (SQL practice only; not the request embedding)"
    if not args.reference_vector:
        if not args.comparison.is_file():
            raise RuntimeError("Run compare first, or use --reference-vector for SQL practice.")
        comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
        embedding = comparison.get("queryEmbedding")
        if comparison.get("query") != DEFAULT_QUERY:
            raise RuntimeError("Use the default compare request for this exercise.")
        if (
            not isinstance(embedding, list) or len(embedding) != 1024
            or any(isinstance(n, bool) or not isinstance(n, (int, float))
                   or not math.isfinite(n) for n in embedding)
        ):
            raise RuntimeError("Comparison has no valid 1024-dimensional query embedding.")
        vector = json.dumps(embedding)
        source = "the same query embedding used by compare"
    environment = os.environ.copy()
    environment["PGOPTIONS"] = (
        environment.get("PGOPTIONS", "")
        + " -c default_transaction_read_only=on -c statement_timeout=15000"
    ).strip()
    environment["PGCONNECT_TIMEOUT"] = "5"
    result = subprocess.run(
        ["psql", "-X", "-Atq", "-v", "ON_ERROR_STOP=1",
         "-v", f"embedding={vector}", "-v", f"terms={args.terms}",
         "-v", f"max_price={args.max_price}", "-f", str(args.sql)],
        env=environment, capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"SQL failed:\n{result.stderr.strip()}")
    payload = json.loads(result.stdout)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Vector source: {source}")
    print(json.dumps(payload, indent=2))
    errors = retrieval_errors(payload, args.max_price)
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    print("FAIL: repair the marked SQL blocks." if errors else
          "PASS: eligibility, unique products, fused scores, and ordering.")
    return 1 if errors else 0


def agent_check(args: argparse.Namespace) -> int:
    """Create one turn, then verify only that turn's persisted tool evidence."""
    session_id = f"builders-floor-{int(time.time())}-{secrets.token_hex(8)}"
    events = _stream_chat(
        args.base_url,
        {"message": "Is the Hadley shirt at the Brooklyn warehouse?",
         "customer_id": "CUST-MARCO", "session_id": session_id, "pattern": "dispatcher"},
        session_token=secrets.token_hex(32), output_path=args.output,
    )
    response = _last_complete(events)
    print(json.dumps(response, indent=2))
    print(f"Checking the new request's session: {session_id}")
    return receipt(argparse.Namespace(
        base_url=args.base_url, session=session_id, within_minutes=5,
    ))


def compare(args: argparse.Namespace) -> int:
    payload = _request_json(
        args.base_url,
        "/api/agent-trace/search-strategies/compare",
        query={"query": args.query},
    )
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(
        f"Shared query embedding: "
        f"{payload.get('sharedQueryEmbeddingObservedMs')} ms"
    )
    for strategy in payload.get("strategies", []):
        products = ", ".join(
            product.get("name", "")
            for product in strategy.get("products", [])[:3]
        )
        components = ", ".join(strategy.get("costComponents", []))
        order_source = strategy.get("productOrderSource")
        rerank_status = (
            json.dumps(strategy["rerankExecuted"])
            if "rerankExecuted" in strategy
            else "not used"
        )
        print(
            f"\n{strategy.get('strategy')}\n"
            f"  observed once: {strategy.get('observedMs')} ms\n"
            f"  rerankExecuted: {rerank_status}\n"
            f"  modeled cost/1K: "
            f"${strategy.get('modeledCostPerThousandUsd')}\n"
            f"  components: {components}\n"
            + (f"  ordered by: {order_source}\n" if order_source else "")
            + f"  top 3: {products}"
        )
        if strategy.get("degradedReason"):
            print(
                f"  DEGRADED: {strategy['degradedReason']}",
                file=sys.stderr,
            )

    cost_model = payload.get("costModel") or {}
    filters = ((payload.get("strategies") or [{}])[-1]).get(
        "extractedFilters",
        {},
    )
    print("\nCost model:")
    print(
        json.dumps(
            {
                "pricingReviewedOn": cost_model.get("pricingReviewedOn"),
                "pricingSource": cost_model.get("pricingSource"),
                "components": cost_model.get("components"),
            },
            indent=2,
        )
    )
    print("\nAgentic filters:")
    print(json.dumps(filters, indent=2))
    print(f"\nFull response: {args.output}")

    strategies = payload.get("strategies") or []
    # Any strategy whose name claims reranking must actually have reranked.
    # Otherwise the comparison shows fusion order under a rerank label and
    # the "is the rerank spend worth it?" question has no honest answer.
    degraded = [
        strategy.get("strategy")
        for strategy in strategies
        if "rerank" in str(strategy.get("strategy", ""))
        and strategy.get("rerankExecuted") is not True
    ]
    valid = (
        len(strategies) == 4
        and filters.get("priceMaxUsd") == 100
        and filters.get("inStockOnly") is True
        and filters.get("hardConstraintsEnforced") is True
        and bool(cost_model.get("components"))
        and not degraded
    )
    if not valid:
        if degraded:
            print(
                "Reranking did not execute for: "
                + ", ".join(str(name) for name in degraded)
                + ". The rows shown are fusion order, not reranked order, so "
                "this comparison is not evidence about reranking. Use the "
                "lab's recovery path. If the issue continues, show this error "
                "to workshop support.",
                file=sys.stderr,
            )
        print("Comparison did not satisfy the Lab 1 evidence contract.", file=sys.stderr)
        return 1
    return 0


def receipt(args: argparse.Namespace) -> int:
    """Verify a recent floor_check receipt, optionally scoped to a session.

    A rehearsal or neighbour's turn can fall inside the freshness window.
    Participants must match the arguments and time to their turn;
    ``--session`` also restricts the lookup to a known session id.
    """
    query = {
        "tool": "floor_check",
        "limit": "1",
        "within_minutes": str(args.within_minutes),
    }
    if args.session:
        query["session_id"] = args.session
    payload = _request_json(
        args.base_url,
        "/api/agent-trace/tool-audit/recent",
        query=query,
        timeout=10,
    )
    rows = payload.get("rows") or []
    row = rows[0] if rows and isinstance(rows[0], dict) else {}
    result = row.get("result")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = {}
    if not isinstance(result, dict):
        result = {}

    brooklyn = next(
        (
            warehouse
            for warehouse in result.get("warehouses", [])
            if isinstance(warehouse, dict)
            and (
                warehouse.get("city") == "Brooklyn"
                or warehouse.get("warehouse_id") == "BK-01"
            )
        ),
        None,
    )
    proof = {
        "source": payload.get("source"),
        "auditId": row.get("audit_id"),
        "sessionId": row.get("session_id"),
        "tool": row.get("tool"),
        "caller": row.get("caller"),
        "args": row.get("args"),
        "result": result,
        "latencyMs": row.get("latency_ms"),
        "createdAt": row.get("created_at"),
        "freshnessWindowMinutes": args.within_minutes,
        "sessionFilter": args.session,
    }
    print(json.dumps(proof, indent=2))
    print(
        "This receipt is scoped to the last "
        f"{args.within_minutes} minutes"
        + (f" and session {args.session}" if args.session else "")
        + ". A recent row alone does not identify your turn; compare the "
        "session and arguments, or use --session for an exact session filter.",
        file=sys.stderr,
    )

    valid = (
        proof["source"] == "pellier.tool_audit"
        and isinstance(proof["auditId"], int)
        and bool(proof["sessionId"])
        and (not args.session or proof["sessionId"] == args.session)
        and proof["tool"] == "floor_check"
        and proof["caller"] == "agent"
        and isinstance(proof["latencyMs"], int)
        and result.get("status") == "success"
        and isinstance(brooklyn, dict)
        and isinstance(brooklyn.get("quantity"), int)
        and isinstance(brooklyn.get("ship_window_min"), int)
        and isinstance(brooklyn.get("ship_window_max"), int)
    )
    if not valid:
        print(
            "No complete agent floor_check receipt from the last "
            f"{args.within_minutes} minutes was found in pellier.tool_audit. "
            "Replay the Marco turn in Pellier, then run this again.",
            file=sys.stderr,
        )
        return 1
    return 0


def ledger(args: argparse.Namespace) -> int:
    session_id = args.session or (
        f"builders-ledger-{int(time.time())}-{secrets.token_hex(4)}"
    )
    session_token = args.token or secrets.token_hex(32)

    turn_one = {
        "message": (
            "My Wabi-Sabi Bowl arrived chipped. Please file a damaged "
            "return (my customer id is 'theo')."
        ),
        "session_id": session_id,
        "pattern": "dispatcher",
    }
    turn_two = {
        "message": (
            "Without calling a tool, what customer id and damage did I "
            "just report?"
        ),
        "session_id": session_id,
        "pattern": "dispatcher",
    }
    _stream_chat(
        args.base_url,
        turn_one,
        session_token=session_token,
        output_path=args.ledger_output,
    )
    memory_events = _stream_chat(
        args.base_url,
        turn_two,
        session_token=session_token,
        output_path=args.memory_output,
    )
    memory = _last_complete(memory_events).get("memory") or {}

    print(f"Session: {session_id}")
    print("Memory receipt:")
    print(json.dumps(memory, indent=2))
    print(f"Session file: {args.session_file}")
    valid = (
        memory.get("source") == "agentcore-memory"
        and memory.get("loaded_messages") == 2
        and memory.get("persisted") is True
    )
    if not valid:
        print(
            "The recall check did not prove AgentCore session memory.",
            file=sys.stderr,
        )
        return 1
    args.session_file.write_text(session_id + "\n", encoding="utf-8")
    return 0


def _repo_env() -> dict[str, str]:
    """Read the bootstrap-written repository .env without extra dependencies."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    values: dict[str, str] = {}
    if not env_path.is_file():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def runtime(args: argparse.Namespace) -> int:
    """Invoke the managed AgentCore Runtime once, outside the storefront rail.

    This is the optional flex. Pellier itself keeps answering on the
    in-process rail, so the floor_check written in Lab 2 stays the code that
    serves shoppers. The managed Runtime executes its tools in the Gateway's
    Lambda target instead, which is why this beat proves the execution
    boundary and the identity check rather than re-proving the tool body.
    """
    env = _repo_env()
    endpoint = env.get("AGENTCORE_RUNTIME_ENDPOINT") or os.environ.get(
        "AGENTCORE_RUNTIME_ENDPOINT", ""
    )
    if not endpoint:
        print(
            "SKIPPED: no managed Runtime on this account.\n"
            "AGENTCORE_RUNTIME_ENDPOINT is unset, so provisioning did not "
            "complete the managed path. This beat is optional and nothing in "
            "the required labs depends on it; see /var/log/pellier-agentcore.log."
        )
        return 0

    region = (
        env.get("AWS_DEFAULT_REGION")
        or env.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or os.environ.get("AWS_REGION")
        or "us-east-1"
    )
    token = "" if args.without_token else os.environ.get("PELLIER_TOKEN", "")
    if not token and not args.without_token:
        print(
            "ERROR: no Cognito access token in $PELLIER_TOKEN.\n"
            "The managed Runtime is JWT-gated and refuses unauthenticated "
            "calls. Mint one first:\n\n"
            "    source ~/pellier-token.sh marco\n",
            file=sys.stderr,
        )
        return 1

    # The Runtime keys managed session state off this header and requires at
    # least 33 characters.
    session_id = f"flex-{secrets.token_hex(16)}".ljust(33, "0")
    payload = json.dumps(
        {
            "prompt": args.query,
            "session_id": session_id,
            "user_id": args.user_id,
        }
    ).encode("utf-8")

    # A CUSTOM_JWT runtime is invoked over the raw HTTPS data plane with the
    # Cognito token as a Bearer header; SigV4 signing is rejected.
    url = (
        f"https://bedrock-agentcore.{region}.amazonaws.com"
        f"/runtimes/{urllib.parse.quote(endpoint, safe='')}"
        "/invocations?qualifier=DEFAULT"
    )
    headers = {
        "Content-Type": "application/json",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    started = time.monotonic()
    try:
        request = urllib.request.Request(
            url, data=payload, headers=headers, method="POST"
        )
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        if args.without_token and exc.code in (401, 403):
            print(
                f"Refused, as expected: HTTP {exc.code}.\n{detail}\n\n"
                "The endpoint rejected this unauthenticated request. Compare "
                "with a successful authenticated request to assess its access control."
            )
            return 0
        print(f"ERROR: Runtime refused the call: HTTP {exc.code}\n{detail}",
              file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: could not reach the managed Runtime: {exc}", file=sys.stderr)
        return 1

    elapsed_ms = int((time.monotonic() - started) * 1000)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"response": raw}

    if args.without_token:
        print(
            "Unexpected: the Runtime answered an unauthenticated call.\n"
            f"{json.dumps(parsed, indent=2)}",
            file=sys.stderr,
        )
        return 1

    rail = str(parsed.get("rail") or "unknown")
    answer = str(parsed.get("response") or parsed.get("error") or raw)
    print(json.dumps(parsed, indent=2))
    print(
        f"\nrail: {rail}    observedMs: {elapsed_ms}    session: {session_id}",
        file=sys.stderr,
    )
    print(
        "\nThe Pellier storefront did not change. It still answers Marco "
        "in-process with the floor_check you wrote in Lab 2. This one call "
        "went to the managed Runtime instead, which runs its tools in the "
        "Gateway's Lambda target — a different execution boundary reached "
        "with your Cognito token.",
        file=sys.stderr,
    )
    if rail != "gateway-mcp":
        print(
            f"\nNote: expected rail 'gateway-mcp', got {rail!r}. The managed "
            "path may be only partly provisioned.",
            file=sys.stderr,
        )
    if answer.strip().startswith("{"):
        return 1
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--base-url", default=DEFAULT_BASE_URL)
    commands = root.add_subparsers(dest="command", required=True)

    readiness_parser = commands.add_parser("readiness")
    readiness_parser.set_defaults(handler=readiness)

    build_parser = commands.add_parser("build-state")
    build_parser.add_argument("--expect", choices=("exercise", "shipped"))
    build_parser.add_argument(
        "--expect-tool",
        choices=("exercise", "shipped"),
    )
    build_parser.add_argument(
        "--expect-agent",
        choices=("exercise", "shipped"),
    )
    build_parser.set_defaults(handler=build_state)

    tool_parser = commands.add_parser("tool-check")
    tool_parser.add_argument("--query", default="Hadley shirt")
    tool_parser.add_argument("--expect-status", choices=("success", "not_found", "ambiguous"), default="success")
    tool_parser.set_defaults(handler=tool_check)

    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("--query", default=DEFAULT_QUERY)
    compare_parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/retrieval-comparison.json"),
    )
    compare_parser.set_defaults(handler=compare)

    retrieval_parser = commands.add_parser("retrieval")
    retrieval_parser.add_argument("--sql", type=Path, default=Path(__file__).resolve().parents[1] / "workshop/retrieval.sql")
    retrieval_parser.add_argument("--comparison", type=Path, default=Path("/tmp/retrieval-comparison.json"))
    retrieval_parser.add_argument("--output", type=Path, default=Path("/tmp/retrieval-sql-result.json"))
    retrieval_parser.add_argument("--reference-vector", action="store_true")
    retrieval_parser.add_argument("--max-price", type=float, default=100)
    retrieval_parser.add_argument("--terms", default="housewarming | gift")
    retrieval_parser.set_defaults(handler=retrieval)

    agent_parser = commands.add_parser("agent-check")
    agent_parser.add_argument("--output", type=Path, default=Path("/tmp/pellier-floor-turn.sse"))
    agent_parser.set_defaults(handler=agent_check)

    receipt_parser = commands.add_parser("receipt")
    receipt_parser.add_argument(
        "--within-minutes",
        type=int,
        default=30,
        help=(
            "Only accept a receipt created in the last N minutes. "
            "Use --session to also scope it to your session."
        ),
    )
    receipt_parser.add_argument(
        "--session",
        help="Only accept a receipt from this exact session id.",
    )
    receipt_parser.set_defaults(handler=receipt)

    ledger_parser = commands.add_parser("ledger")
    ledger_parser.add_argument("--session")
    ledger_parser.add_argument("--token")
    ledger_parser.add_argument(
        "--session-file",
        type=Path,
        default=Path("/tmp/pellier-ledger-session.txt"),
    )
    ledger_parser.add_argument(
        "--ledger-output",
        type=Path,
        default=Path("/tmp/pellier-ledger-turn.sse"),
    )
    ledger_parser.add_argument(
        "--memory-output",
        type=Path,
        default=Path("/tmp/pellier-memory-turn.sse"),
    )
    ledger_parser.set_defaults(handler=ledger)

    runtime_parser = commands.add_parser("runtime")
    runtime_parser.add_argument(
        "--query",
        default="Is the Hadley shirt at the Brooklyn warehouse?",
    )
    runtime_parser.add_argument("--user-id", default="marco")
    runtime_parser.add_argument("--timeout", type=int, default=120)
    runtime_parser.add_argument(
        "--without-token",
        action="store_true",
        help=(
            "Invoke with no Authorization header to show the managed "
            "Runtime refusing an unauthenticated call."
        ),
    )
    runtime_parser.set_defaults(handler=runtime)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return int(args.handler(args))
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
