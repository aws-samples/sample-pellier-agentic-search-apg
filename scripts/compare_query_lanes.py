#!/usr/bin/env python3
"""Compare two paths that answer the same question about business records.

Observe-only, and never required. The point is not that one mechanism is
better. It is that two paths can return the same rows while leaving materially
different evidence and operating under materially different authorization.

The two lanes
-------------

**Governed lane** — `services/governed_query.py`. Generated SQL is wrapped and
planned before it runs, then executed as `pellier_query` in a READ ONLY
transaction with a statement timeout, a fixed search_path, a schema allowlist,
an implementation-owned row cap, and `pellier.principal_sub` bound so
Row-Level Security scopes the result. Every attempt writes a receipt.

**Postgres MCP lane** — `awslabs.postgres-mcp-server`, configured by
`pellier/backend/generate_mcp_config.py`. It reaches Aurora through the RDS
Data API using one fixed `--secret_arn`. Read-only is the server's default, so
it will not write. But the credential is a *database identity*, and which one
it is decides everything else.

This script measures that rather than asserting it: it runs the comparison
probes through the same transport and the same secret the MCP server is
configured with, so the authorization facts are the MCP lane's own. Only the
MCP protocol wrapper is skipped, and that wrapper does not affect authorization.

Usage::

    python3 scripts/compare_query_lanes.py
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
from typing import Any, Dict, List, Optional, Tuple

_REPO = pathlib.Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "pellier" / "backend"
_MCP_CONFIG = _REPO / "pellier" / "config" / "mcp-server-config.json"

# The comparison question. Fixed rather than caller-supplied: the MCP-lane
# probes run with a broadly privileged credential, and this script exists to
# characterize that credential, not to become a way to use it.
COMPARISON_SQL = "SELECT DISTINCT customer_id FROM pellier.orders ORDER BY 1"


def _load_env() -> Dict[str, str]:
    values: Dict[str, str] = {}
    env_path = _BACKEND / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    values.update({k: v for k, v in os.environ.items() if k.startswith(("DB_", "AWS_"))})
    return values


def mcp_lane_facts() -> Dict[str, Any]:
    """Read what the MCP server is actually configured to do.

    Facts come from the generated config file, not from this script's
    assumptions, so a change to the flag contract shows up here.
    """
    facts: Dict[str, Any] = {
        "configured": False,
        "version": None,
        "connection_method": None,
        "write_allowed": None,
        "binds_principal": False,
        "role_source": None,
    }
    if not _MCP_CONFIG.exists():
        return facts

    config = json.loads(_MCP_CONFIG.read_text())
    server = (config.get("mcpServers") or {}).get("awslabs.postgres-mcp-server")
    if not server:
        return facts

    args: List[str] = list(server.get("args") or [])
    facts["configured"] = True
    facts["version"] = next(
        (a for a in args if a.startswith("awslabs.postgres-mcp-server")), None
    )
    if "--connection_method" in args:
        facts["connection_method"] = args[args.index("--connection_method") + 1]
    # Read-only is the server default; writes are opt-in.
    facts["write_allowed"] = "--allow_write_query" in args
    facts["role_source"] = "--secret_arn" if "--secret_arn" in args else "unknown"
    # There is no flag that binds a per-request principal, so RLS cannot be
    # scoped to a shopper on this lane.
    facts["binds_principal"] = False
    return facts


def probe_mcp_lane_identity(cfg: Dict[str, str]) -> Dict[str, Any]:
    """Ask the MCP lane's own credential what it is and what it can reach."""
    import boto3

    result: Dict[str, Any] = {"reachable": False}
    required = ("DB_CLUSTER_ARN", "DB_SECRET_ARN", "DB_NAME")
    if not all(cfg.get(key) for key in required):
        result["reason"] = f"missing {', '.join(k for k in required if not cfg.get(k))}"
        return result

    client = boto3.client("rds-data", region_name=cfg.get("AWS_REGION", "us-east-1"))

    def scalar(sql: str) -> Any:
        response = client.execute_statement(
            resourceArn=cfg["DB_CLUSTER_ARN"],
            secretArn=cfg["DB_SECRET_ARN"],
            database=cfg["DB_NAME"],
            sql=sql,
        )
        records = response.get("records") or []
        if not records:
            return None
        return next(iter(records[0][0].values()))

    try:
        result["current_user"] = scalar("SELECT current_user")
        result["owns_protected_tables"] = bool(
            scalar(
                "SELECT count(*) FROM pg_tables WHERE schemaname='pellier'"
                " AND tablename IN ('orders','returns')"
                " AND tableowner = current_user"
            )
        )
        result["customers_visible"] = scalar(
            "SELECT count(DISTINCT customer_id) FROM pellier.orders"
        )
        for label, sql in (
            ("reads_authorization_mapping",
             "SELECT count(*) FROM pellier.principal_customers"),
            ("reads_evidence_ledger", "SELECT count(*) FROM pellier.tool_audit"),
        ):
            try:
                result[label] = scalar(sql)
            except Exception:
                result[label] = "denied"
        result["reachable"] = True
    except Exception as exc:
        result["reason"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    return result


async def probe_governed_lane(principal_sub: Optional[str]) -> Dict[str, Any]:
    """Run the same question through the governed lane."""
    sys.path.insert(0, str(_BACKEND))
    from urllib.parse import quote_plus

    # `config.Settings` resolves `.env` relative to the process working
    # directory, and this script runs from the repo root. Inject the values
    # before importing it, or Settings raises on required DB_* fields.
    for key, value in _load_env().items():
        os.environ.setdefault(key, value)

    from config import settings
    from services.database import DatabaseService
    from services.governed_query import run_governed_query

    cfg = _load_env()
    settings.DATABASE_URL = (
        f"postgresql://{cfg['DB_USER']}:{quote_plus(cfg['DB_PASSWORD'])}"
        f"@{cfg['DB_HOST']}:{cfg.get('DB_PORT', '5432')}/{cfg['DB_NAME']}"
    )

    service = DatabaseService()
    await service.connect()
    try:
        # The call receipts itself, so this observe-only script leaves the
        # artifact the comparison table below credits to this lane.
        result = await run_governed_query(
            service,
            COMPARISON_SQL,
            turn_id="turn-lane-comparison",
            principal_sub=principal_sub,
            caller="operator",
            session_id="lane-comparison",
        )
        mapping = await service.fetch_all(
            "SELECT customer_id, principal_sub FROM pellier.principal_customers"
            " ORDER BY customer_id"
        )
        # Read on the ordinary connection, which is the table owner and so
        # bypasses RLS. This is the answer key: it says which customers a
        # scoped read *should* be able to see, and therefore which principal
        # makes the comparison mean something.
        with_orders = await service.fetch_all(
            "SELECT DISTINCT customer_id FROM pellier.orders ORDER BY 1"
        )
        return {
            "accepted": result.accepted,
            "customers_visible": len(result.rows),
            "rows": [row.get("customer_id") for row in result.rows],
            "evidence": result.evidence(),
            "available_principals": {r["customer_id"]: r["principal_sub"] for r in mapping},
            "customers_with_orders": [r["customer_id"] for r in with_orders],
        }
    finally:
        await service.disconnect()


def _receipts_written(*probes: Optional[Dict[str, Any]]) -> str:
    """Report the receipt ids this run actually created.

    Named ids rather than the table name: the row is the claim, and quoting a
    table that could be empty is how the previous version of this line came to
    advertise evidence none of its three queries had written.
    """
    ids = [
        probe["evidence"].get("receipt_id")
        for probe in probes
        if probe and probe.get("evidence", {}).get("receipt_id")
    ]
    return f"receipt {', '.join(str(i) for i in ids)}" if ids else "none written"


def _yes(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return str(value)


def render(
    mcp_facts: Dict[str, Any],
    mcp_probe: Dict[str, Any],
    anonymous: Dict[str, Any],
    scoped: Optional[Dict[str, Any]],
    other: Optional[Dict[str, Any]],
    *,
    holder: Optional[str],
    bystander: Optional[str],
    with_orders: List[str],
) -> None:
    print("Question: which customers have orders?")
    print(f"SQL     : {COMPARISON_SQL}")
    print()

    print("Postgres MCP lane, as configured")
    print("-" * 72)
    if not mcp_facts["configured"]:
        print("  not configured; run pellier/backend/generate_mcp_config.py")
    else:
        print(f"  server            : {mcp_facts['version']}")
        print(f"  transport         : RDS Data API ({mcp_facts['connection_method']})")
        print(f"  writes allowed    : {_yes(mcp_facts['write_allowed'])}"
              "   (read-only is the server default)")
        print(f"  database identity : one fixed credential ({mcp_facts['role_source']})")
        print(f"  binds a principal : {_yes(mcp_facts['binds_principal'])}")
    print()

    if mcp_probe.get("reachable"):
        print("  measured through that same credential:")
        print(f"    current_user            : {mcp_probe['current_user']}")
        print(f"    owns the protected tables: {_yes(mcp_probe['owns_protected_tables'])}"
              "  <- owners bypass RLS")
        print(f"    customers visible       : {mcp_probe['customers_visible']}")
        print(f"    reads authorization map : {mcp_probe['reads_authorization_mapping']}")
        print(f"    reads evidence ledger   : {mcp_probe['reads_evidence_ledger']}")
    else:
        print(f"  credential not probed: {mcp_probe.get('reason')}")
    print()

    print("Governed lane")
    print("-" * 72)
    print(f"  role used         : {anonymous['evidence']['role_used']}")
    print(f"  statement timeout : {anonymous['evidence']['statement_timeout']}")
    print(f"  result limit      : {anonymous['evidence']['result_limit']}")
    print(f"  turn_id           : {anonymous['evidence']['turn_id']}")
    print()
    print(f"  owner's answer key: {', '.join(with_orders) or 'no orders in the table'}")
    print(f"  anonymous turn    : {anonymous['customers_visible']} row(s) "
          f"{anonymous['rows']}")
    if scoped is not None:
        print(f"  as {holder:<14}: {scoped['customers_visible']} row(s) "
              f"{scoped['rows']}   <- own record, visible")
    if other is not None:
        print(f"  as {bystander:<14}: {other['customers_visible']} row(s) "
              f"{other['rows']}   <- someone else's record, invisible")

    # State whether the run actually distinguished scoping from blanket denial.
    # Without this, a dataset that cannot produce the contrast still prints
    # three plausible-looking lines.
    if scoped is None:
        print()
        print("  ⚠ No mapped shopper owns a row in pellier.orders, so this run")
        print("    cannot tell RLS scoping apart from RLS denying everyone. Seed an")
        print("    order for a mapped customer to make the comparison meaningful.")
    elif scoped["customers_visible"] == 0:
        print()
        print(f"  ⚠ {holder} owns a row the owner can see, but the scoped read")
        print("    returned nothing. That is RLS denying a shopper their own data,")
        print("    not scoping. Check pellier.principal_customers and the policy.")
    print()

    print("What each path leaves behind")
    print("-" * 72)
    rows = [
        ("principal context", "no per-request principal", "principal_sub bound, RLS scoped"),
        ("policy context", "none", "Cedar decision recorded on the turn"),
        ("SQL visible", "in the MCP transcript", "in the query receipt"),
        ("durable receipt", "none", f"{_receipts_written(anonymous, scoped, other)} written just now"),
        ("turn_id correlation", "none", "yes"),
        ("database constraints", "owner: RLS bypassed", "non-owner: RLS enforced"),
    ]
    print(f"  {'dimension':<22} {'MCP lane':<28} governed lane")
    for dimension, mcp, governed in rows:
        print(f"  {dimension:<22} {mcp:<28} {governed}")
    print()
    print("Neither lane is categorically better. The MCP lane is a fast, general")
    print("database tool; the governed lane is narrower and answers to a shopper's")
    print("identity. Choosing between them is a governance decision, and the")
    print("difference is visible in what each leaves behind.")


def main(argv: Optional[List[str]] = None) -> int:
    cfg = _load_env()
    if not all(cfg.get(k) for k in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")):
        print("Database not configured; nothing to compare.", file=sys.stderr)
        return 2

    mcp_facts = mcp_lane_facts()
    mcp_probe = probe_mcp_lane_identity(cfg)

    anonymous = asyncio.run(probe_governed_lane(None))
    principals: Dict[str, str] = anonymous.get("available_principals") or {}
    with_orders = set(anonymous.get("customers_with_orders") or [])

    # Pick the two principals deliberately. An earlier revision took whichever
    # mapping row came back first, which on this dataset was a shopper with no
    # orders: the scoped read returned 0 rows, the anonymous read returned 0
    # rows, and the output presented that as a demonstration of scoping. Zero
    # against zero demonstrates nothing — it looks identical to RLS refusing
    # everyone, which is the failure the comparison is supposed to detect.
    holder = next(
        (customer for customer in sorted(principals) if customer in with_orders), None
    )
    bystander = next(
        (customer for customer in sorted(principals) if customer not in with_orders),
        None,
    )

    scoped = (
        asyncio.run(probe_governed_lane(principals[holder])) if holder else None
    )
    other = (
        asyncio.run(probe_governed_lane(principals[bystander])) if bystander else None
    )

    render(
        mcp_facts,
        mcp_probe,
        anonymous,
        scoped,
        other,
        holder=holder,
        bystander=bystander,
        with_orders=sorted(with_orders),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
