#!/usr/bin/env python3
"""Prove both governance windows against the live Gateway, end to end.

This is the composite proof: everything else verifies one layer at a time, and
the whole point of the design is what happens when two layers disagree.

    ENFORCE window
        Cedar DENY before the target runs. The tool never executes, so there is
        no execution row and no business change. The authoritative artifact is
        the policy decision, because the database was never reached.

    LOG_ONLY window
        The configured policy lets the request continue. The tool must report
        an explicit Aurora Row-Level Security refusal, with an attempt receipt
        and zero business change. Per-call WOULD_DENY telemetry is a separate
        observation; this response/audit comparison does not collect it.

Both windows use the same request, so the only variable is enforcement mode.

Mode is switched through the AgentCore CLI project rather than the SDK, for the
reasons in `scripts/policy_mode.py`. The script restores the shipped mode on
exit, including after a failure, so a crashed run cannot leave the account in
monitor mode.

Usage::

    python3 scripts/prove_governance_windows.py
    python3 scripts/prove_governance_windows.py --keep-log-only   # inspect it
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import uuid
from typing import Any, Dict, List, Optional, Tuple

_REPO = pathlib.Path(__file__).resolve().parents[0].parent
_BACKEND = _REPO / "pellier" / "backend"
_DEPLOY = _REPO / "scripts" / "deploy"

# The forbid policy whose mode decides which window we are in. A permit policy
# in LOG_ONLY looks identical to one in ACTIVE from the caller's side.
GATING_POLICY = "initiate_return_damaged_only"

# A reason the gating policy forbids. `damaged` is the only permitted value, so
# this request is the one Cedar has an opinion about.
FORBIDDEN_REASON = "changed_mind"

# Anna's order, requested while holding Marco's token: refused by Cedar in the
# ENFORCE window, and by Row-Level Security in the LOG_ONLY window. Using a
# cross-customer request means the LOG_ONLY window has a database-side refusal
# to demonstrate rather than merely succeeding.
TARGET_CUSTOMER = "CUST-ANNA"
TARGET_PRODUCT = "21"

# `policy_mode.py` returns this when the CLI project cannot be deployed in
# the current account. That is an environment limitation, not a governance
# failure, so it exits as a skip.
_NOT_DEPLOYABLE = 3
_OBSERVATION_TIMEOUT_SECONDS = 30

# These canonical classifiers are pure helpers; importing them does not load
# credentials, settings or managed clients.
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
from services.gateway_errors import gateway_error_text, read_gateway_error_response
from services.governed_execution import (
    AURORA_DENIED,
    classify_aurora,
    is_output_suppression,
    is_policy_denial,
)


def _load_env() -> Dict[str, str]:
    values: Dict[str, str] = {}
    env_path = _BACKEND / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    values.update(
        {
            k: v
            for k, v in os.environ.items()
            if k.startswith(("DB_", "AWS_", "COGNITO_", "AGENTCORE_")) or k == "PELLIER_DEPLOYMENT_SUFFIX"
        }
    )
    return values


def _import_tools() -> Tuple[Any, Any]:
    """Load the existing Gateway helpers rather than reimplementing them."""
    sys.path.insert(0, str(_DEPLOY))
    import importlib.util

    def load(name: str, filename: str) -> Any:
        spec = importlib.util.spec_from_file_location(name, _DEPLOY / filename)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return load("gw_auth", "test_gateway_auth.py"), load("gw_tools", "test_gateway_tools.py")


def _policy_tool() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "policy_mode_tool", _REPO / "scripts" / "policy_mode.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _policy_error_evidence(error: BaseException) -> str | None:
    """Require explicit invocation denial evidence in every exception leaf."""
    import httpx

    children = getattr(error, "exceptions", None)
    if children:
        evidence = [_policy_error_evidence(child) for child in children]
        return " ".join(evidence) if all(evidence) else None
    if isinstance(error, (httpx.RequestError, TimeoutError, OSError)):
        return None
    response = getattr(error, "response", None)
    if response is not None and getattr(response, "status_code", None) != 403:
        return None
    if not is_policy_denial(error):
        return None
    return f"{type(error).__name__}: {gateway_error_text(error)}"


def _gateway_response(response: Any) -> Dict[str, Any]:
    """Keep explicit policy errors and returned tool envelopes distinct."""
    text = "".join(
        getattr(block, "text", "") for block in (response.content or [])
    )
    if is_output_suppression(text):
        return {"outcome": "error", "error_kind": "output_suppressed"}
    if getattr(response, "isError", False) is True and is_policy_denial(text):
        return {
            "outcome": "policy_denied",
            "policy_source": "gateway-tool-error",
            "policy_evidence": text,
        }
    try:
        envelope = json.loads(text)
    except (ValueError, TypeError):
        envelope = None
    return {
        "outcome": "returned",
        "is_error": bool(getattr(response, "isError", False)),
        "result": envelope if isinstance(envelope, dict) else None,
    }


async def _call_initiate_return(
    gateway_url: str, token: str, *, reason: str, idempotency_key: str
) -> Dict[str, Any]:
    """Invoke initiate_return through the Gateway's MCP endpoint.

    Returns a dict describing the outcome, including whether the call was
    refused before the target ran.
    """
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    headers = {"Authorization": f"Bearer {token}"}
    invocation_started = False
    try:
        async with httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(30.0, read=300.0),
            follow_redirects=False,
            event_hooks={"response": [read_gateway_error_response]},
        ) as http_client:
            async with streamable_http_client(
                gateway_url, http_client=http_client
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    name = next(
                        (t.name for t in tools.tools if t.name.endswith("initiate_return")),
                        None,
                    )
                    if name is None:
                        return {"outcome": "tool_absent"}
                    invocation_started = True
                    response = await session.call_tool(
                        name,
                        {
                            "customer_id": TARGET_CUSTOMER,
                            "product_id": int(TARGET_PRODUCT),
                            "reason": reason,
                            "idempotency_key": idempotency_key,
                        },
                    )
                    result = _gateway_response(response)
        return result
    except Exception as exc:
        evidence = _policy_error_evidence(exc) if invocation_started else None
        if evidence:
            return {
                "outcome": "policy_denied",
                "policy_source": "gateway-exception",
                "policy_evidence": evidence,
            }
        if is_output_suppression(exc):
            kind = "output_suppressed"
        elif isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (401, 403):
            kind = "authentication_error"
        elif isinstance(exc, (httpx.RequestError, TimeoutError, OSError)):
            kind = "transport_error"
        else:
            kind = "gateway_error"
        # Exception strings may contain request data. Report the classification
        # without printing credentials, headers or raw transport diagnostics.
        return {"outcome": "error", "error_kind": kind}


class ObservationUnavailable(RuntimeError):
    """A database read did not establish the counts required for this proof."""


def _observed_counts(
    result: Any, *, label: str, expected: int
) -> Tuple[int, ...]:
    """Accept only a successful psql read with exactly the expected counts."""
    if result.returncode != 0:
        raise ObservationUnavailable(
            f"{label}: database observation failed (psql exit {result.returncode})"
        )
    fields = result.stdout.strip().split("|")
    # COUNT(*) is a nonnegative bigint. Empty output, missing fields and extra
    # rows are unavailable evidence, never proof that a count was zero.
    if len(fields) != expected or any(
        re.fullmatch(r"[0-9]{1,19}", field) is None for field in fields
    ):
        raise ObservationUnavailable(
            f"{label}: database observation did not return {expected} valid counts"
        )
    counts = tuple(int(field) for field in fields)
    if any(count > 2**63 - 1 for count in counts):
        raise ObservationUnavailable(f"{label}: database count is out of range")
    return counts


def _business_state(cfg: Dict[str, str]) -> Dict[str, int]:
    """Count the rows a successful return would have changed."""
    import subprocess

    child = os.environ.copy()
    child["PGPASSWORD"] = cfg["DB_PASSWORD"]
    sql = (
        "SELECT (SELECT count(*) FROM pellier.returns WHERE customer_id='"
        f"{TARGET_CUSTOMER}')::text || '|' || "
        "(SELECT count(*) FROM pellier.inventory_ledger)::text"
    )
    try:
        result = subprocess.run(
            [
                "psql", "-h", cfg["DB_HOST"], "-p", cfg.get("DB_PORT", "5432"),
                "-U", cfg["DB_USER"], "-d", cfg["DB_NAME"],
                "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1", "-c", sql,
            ],
            env=child, capture_output=True, text=True,
            timeout=_OBSERVATION_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ObservationUnavailable(
            f"business state: database observation unavailable ({type(exc).__name__})"
        ) from None
    returns, ledger = _observed_counts(
        result, label="business state", expected=2
    )
    return {"returns": returns, "ledger": ledger}


def _audit_rows(cfg: Dict[str, str], idempotency_key: str) -> int:
    """Count execution rows for one attempt."""
    import subprocess

    child = os.environ.copy()
    child["PGPASSWORD"] = cfg["DB_PASSWORD"]
    try:
        result = subprocess.run(
            [
                "psql", "-h", cfg["DB_HOST"], "-p", cfg.get("DB_PORT", "5432"),
                "-U", cfg["DB_USER"], "-d", cfg["DB_NAME"],
                "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1",
                "-c",
                "SELECT count(*) FROM pellier.tool_audit WHERE tool='initiate_return'"
                f" AND args::text LIKE '%{idempotency_key}%'",
            ],
            env=child, capture_output=True, text=True,
            timeout=_OBSERVATION_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ObservationUnavailable(
            f"execution audit: database observation unavailable ({type(exc).__name__})"
        ) from None
    return _observed_counts(result, label="execution audit", expected=1)[0]


def _run_window(
    label: str,
    cfg: Dict[str, str],
    gateway_url: str,
    token: str,
) -> Dict[str, Any]:
    """Issue the request and gather what changed."""
    import asyncio

    key = f"gov-window-{uuid.uuid4().hex[:8]}"
    before = _business_state(cfg)
    call = asyncio.run(
        _call_initiate_return(
            gateway_url, token, reason=FORBIDDEN_REASON, idempotency_key=key
        )
    )
    after = _business_state(cfg)
    return {
        "window": label,
        "idempotency_key": key,
        "call": call,
        "executions": _audit_rows(cfg, key),
        "business_change": {
            "returns": after["returns"] - before["returns"],
            "ledger": after["ledger"] - before["ledger"],
        },
    }


def _report(result: Dict[str, Any]) -> List[str]:
    """Return the assertions that failed for one window."""
    failures: List[str] = []
    window = result["window"]
    call = result["call"]

    if call["outcome"] == "tool_absent":
        return [f"{window}: initiate_return is not published on the Gateway"]

    if result["business_change"]["returns"] != 0:
        failures.append(f"{window}: a refused request committed a return row")
    if result["business_change"]["ledger"] != 0:
        failures.append(f"{window}: a refused request moved inventory")

    if window == "ENFORCE":
        if (
            call.get("outcome") != "policy_denied"
            or call.get("policy_source") not in {"gateway-exception", "gateway-tool-error"}
            or not is_policy_denial(call.get("policy_evidence", ""))
        ):
            failures.append(f"{window}: no explicit Gateway/Cedar denial was observed")
        # Cedar denies before the target runs, so nothing should have executed.
        if result["executions"] != 0:
            failures.append(
                f"{window}: expected no execution row, found {result['executions']}"
            )
    elif window == "LOG_ONLY":
        envelope = call.get("result")
        if (
            call.get("outcome") != "returned"
            or not isinstance(envelope, dict)
            or envelope.get("status") not in {"error", "policy_blocked"}
            or envelope.get("denied_by") != "database_row_level_security"
            or classify_aurora(envelope)[0] != AURORA_DENIED
        ):
            failures.append(f"{window}: no explicit Aurora Row-Level Security refusal was observed")
        # The request continued past Cedar. Execution is expected; the database
        # is what refuses. Zero executions here would mean Cedar still blocked
        # it, so the mode change did not take effect.
        if result["executions"] == 0:
            failures.append(
                f"{window}: expected the tool to execute and be refused by the "
                "database, but nothing executed — Cedar may still be enforcing"
            )
    else:
        failures.append(f"Unsupported governance window: {window}")
    return failures


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--keep-log-only",
        action="store_true",
        help="Leave the gating policy in LOG_ONLY for manual inspection.",
    )
    args = parser.parse_args(argv)

    cfg = _load_env()
    missing = [
        key
        for key in (
            "DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD",
            "AGENTCORE_GATEWAY_URL", "AGENTCORE_POLICY_ENGINE_ID",
            "COGNITO_POOL_ID", "COGNITO_CLIENT_ID",
        )
        if not cfg.get(key)
    ]
    if missing:
        print(
            "Not provisioned for this proof; missing "
            f"{', '.join(missing)}.\n"
            "Both windows need the managed Gateway, a Cedar engine, and Cognito.",
            file=sys.stderr,
        )
        return 2

    gw_auth, _gw_tools = _import_tools()
    policy = _policy_tool()
    sys.path.insert(0, str(_DEPLOY))
    from render_agentcore_project import project_root

    project_dir = project_root(_REPO, deployment_suffix=cfg.get("PELLIER_DEPLOYMENT_SUFFIX", ""))

    import boto3

    control = boto3.client(
        "bedrock-agentcore-control", region_name=cfg.get("AWS_REGION", "us-east-1")
    )
    engine_id = cfg["AGENTCORE_POLICY_ENGINE_ID"]
    gateway_id = policy.gateway_id_from_arn(cfg.get("AGENTCORE_GATEWAY_ARN", ""))
    gateway_url = cfg["AGENTCORE_GATEWAY_URL"]

    token = gw_auth.get_cognito_token(
        pool_id=cfg["COGNITO_POOL_ID"],
        client_id=cfg["COGNITO_CLIENT_ID"],
        region=cfg.get("COGNITO_REGION") or cfg.get("AWS_REGION", "us-east-1"),
        credentials_secret_arn=cfg.get("COGNITO_TEST_CREDENTIALS_SECRET_ARN"),
    )

    failures: List[str] = []
    results: List[Dict[str, Any]] = []
    exit_code = 0
    try:
        for label, mode in (("ENFORCE", "ACTIVE"), ("LOG_ONLY", "LOG_ONLY")):
            rc = policy._apply(
                project_dir, control, engine_id, gateway_id,
                policy_modes={GATING_POLICY: mode}, label=f"{label} window",
            )
            if type(rc) is not int or rc != 0:
                exit_code = 2 if rc == _NOT_DEPLOYABLE else 1
                print(f"Could not establish the {label} window (status {rc}).", file=sys.stderr)
                break
            result = _run_window(label, cfg, gateway_url, token)
            results.append(result)
            failures.extend(_report(result))
            if failures:
                break
    except ObservationUnavailable as exc:
        failures.append(f"governance evidence unavailable: {exc}")
    finally:
        if not args.keep_log_only:
            # Restore even after a failure: a crashed run must not leave the
            # account in monitor mode.
            try:
                restored = policy._restore_shipped(project_dir, control, engine_id, gateway_id)
            except Exception as exc:
                failures.append(f"shipped-mode restoration failed ({type(exc).__name__})")
            else:
                if type(restored) is not int or restored != 0:
                    failures.append("shipped-mode restoration did not report success")

    if failures:
        print("FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    if exit_code:
        return exit_code

    print()
    print("Governance windows")
    print("=" * 78)
    for result in results:
        call = result["call"]
        print(f"  {result['window']}")
        print(f"    gateway call      : {call['outcome']}"
              + (f" ({'error' if call.get('is_error') else 'ok'})"
                 if call["outcome"] == "returned" else ""))
        print(f"    execution rows    : {result['executions']}")
        print(f"    business change   : returns={result['business_change']['returns']}"
              f" ledger={result['business_change']['ledger']}")
        print()

    print("  Reading the pair:")
    print("    ENFORCE  - Gateway reported an explicit Cedar denial, with zero")
    print("               execution rows and no observed business change.")
    print("    LOG_ONLY - The target reported an Aurora Row-Level Security")
    print("               refusal, with an attempt receipt and no business change.")
    print("    Per-call WOULD_DENY telemetry is not collected by this comparison.")
    print()
    print("✅ both windows behaved as designed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
