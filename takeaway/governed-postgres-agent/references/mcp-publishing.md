# Publishing tools over MCP

How Pellier exposes its nine store tools to agents running on Amazon Bedrock
AgentCore through Gateway, and what to keep if your gateway is something else.

## One implementation, two paths

The tool bodies live in one module (`services/store_tools.py`). The in-process
agents call them directly with a database connection. The Gateway target is a
Lambda (`scripts/deploy/pellier_store_tools.py`) that imports the same module
and runs it over the RDS Data API. There is no second implementation to drift.
The Data API is Aurora-only; on RDS for PostgreSQL the Lambda would connect
with a driver, through RDS Proxy, and keep the same tool module.

```
agent (in process) ──► store_tools.check_stock(run_sql, ...) ──► Aurora over TLS
agent (on Runtime) ──► Gateway (MCP) ──► Lambda ──► store_tools.check_stock(run_dataapi, ...) ──► Aurora over Data API
```

The `run` argument is the only thing that differs: a callable that executes
one parameterised statement on whichever transport the path uses.

## Schemas from one source of truth

Tool schemas are declared once (`scripts/deploy/gateway_tool_schemas.py`), as
plain JSON Schema with a small allowed key set (`type`, `properties`,
`required`, `items`, `description`), because gateways reject what they do not
know. The same file states which tools are published, and the deploy script
reads it. A tool can have a schema and still be unpublished; publication is an
explicit list, which is what Lab 3 Task A edits.

Descriptions do the routing work. "Quantity and ship window at each warehouse
for one named product" tells a model when to call `check_stock` and when not
to; a description that names infrastructure ("queries the inventory table")
does not.

## Identity across the boundary

- The shopper's Cognito access token is validated at Runtime and again at
  Gateway (AgentCore Identity). Both require a token.
- The server binds `customer_id` on caller-bound tools before the call leaves
  Runtime (`services/agentcore_gateway.py`, the reconcile step), so the
  Gateway sees the signed-in customer regardless of what the model asked.
- Cedar policies (AgentCore Policy) evaluate every Gateway call, including the
  tool list: a shopper token cannot see `give_store_credit` because no shopper
  permit names it. Action ids take the form `<target>___<tool>`.
- The Lambda binds the same principal on the database transaction, so
  row-level security applies on the gateway path too.

## Evidence on the gateway path

Every executed Lambda call writes a `tool_audit` row with the caller, the
arguments, the result and the build fingerprint of the Runtime that made the
call. AgentCore Observability writes a span per managed step (Runtime,
Identity, Policy and Gateway, whose span records whether the Lambda ran) under
one trace id to CloudWatch. A span proves a call ran; it does not prove what
it wrote. The row does.

## If your gateway is not AgentCore

Keep the invariants, change the plumbing:

- one tool implementation for every path;
- schemas and the published list in one file the deploy reads;
- identity bound by the server before the call leaves the agent, verified again
  at the gateway, and bound again on the database transaction;
- authorization at the gateway for the call, row-level security in the
  database for the rows;
- an audit row per executed call, written by the tool, not by the gateway.
