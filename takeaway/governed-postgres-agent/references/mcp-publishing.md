# Optional: tools across AgentCore Gateway

Use this reference when the reviewed operation crosses a tool gateway.
The four contracts still apply; the extra task is tracing the same operation
across independently authenticated and authorized boundaries.

## One implementation, explicit publication

Pellier's local agents and Gateway Lambda use the shared store tools. The
Lambda uses the Aurora RDS Data API; a conventional PostgreSQL deployment
can use a driver and its chosen connection management. RDS Proxy is an
option, not a requirement of the tool contract.

Inspect both paths for wrappers that change arguments, status or role.
Sharing a function does not prove equivalent authentication or transaction
handling. A declared tool schema is also not proof that the tool was
published. Compare schema, published tools and the deployed version.

## Identity and permission

In Pellier, AgentCore Runtime receives authenticated shopper requests. The
server binds customer-scoped tool arguments before invoking AgentCore
Gateway. AgentCore Policy checks the Gateway request against the caller's
claims, and the database transaction carries the caller context for RLS.
AgentCore Identity and token configuration are supporting authentication
infrastructure; they do not replace the application's authorization rules.

Review these separately:

- a forged argument through the application's binding;
- a direct Gateway request with a mismatched customer;
- a wrong-customer SQL query under the intended database role and context.

Use a correlation key for each probe. Name the deployed build when testing
managed behavior. A local source check does not establish which build served
an actual request.

## Evidence across the boundary

Distinguish a policy denial, authentication failure, transport error, tool
result and committed write. A 401 is not evidence of a Cedar decision.
Use the trace or response that actually identifies the boundary's outcome;
do not infer execution solely from an outer request span.

Pellier's write evidence distinguishes the initial execution from replay.
Read the tool's audit convention before interpreting row counts. A retry
that returns a stored result need not add an execution ledger row. The
expense example in this package records first committed writes only.

For another gateway, preserve these review questions. Do not require
AgentCore service names, a particular claim name or Pellier's audit schema
where the application uses a different implementation.
