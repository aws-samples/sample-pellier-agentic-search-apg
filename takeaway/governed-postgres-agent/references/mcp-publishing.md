# Optional: Tools across AgentCore Gateway

Use this reference when the reviewed operation crosses a tool gateway.
The four contracts still apply. The extra task is to trace the same operation
across boundaries that are authenticated and authorized independently.

## One implementation, explicit publication

Pellier's local agents and Gateway Lambda use the shared store tools. The
Lambda uses the Aurora RDS Data API. A conventional PostgreSQL deployment
can use a driver and its chosen connection management. RDS Proxy is an
option. It is not a requirement of the tool contract.

Inspect both paths for wrappers that change arguments, status or role.
Sharing a function does not prove equivalent authentication or transaction
handling. A declared tool schema is also not proof that the tool was
published. Compare the schema, the published tools and the deployed version.

## Identity and permission

In Pellier, AgentCore Runtime receives authenticated shopper requests. The
server binds customer-scoped tool arguments before invoking AgentCore
Gateway. AgentCore Policy checks the Gateway request against the caller's
claims, and the database transaction carries the caller context for RLS.
AgentCore Identity and token configuration are supporting authentication
infrastructure. They do not replace the application's authorization rules.

Review these separately:

- A forged argument through the application's binding.
- A direct Gateway request with a mismatched customer.
- A wrong-customer SQL query under the intended database role and context.

Use a correlation key for each probe. Name the deployed build when testing
managed behavior. A local source check does not establish which build served
an actual request.

## Evidence across the boundary

Tell a policy denial, an authentication failure, a transport error, a tool
result and a committed write apart. A 401 is not evidence of a Cedar decision.
Use the trace or response that actually identifies the boundary's outcome.
Do not infer execution solely from an outer request span.

Pellier's write evidence distinguishes the initial execution from a replay.
Read the tool's audit convention before interpreting row counts. A retry
that returns a stored result need not add an execution ledger row. The
expense example in this package records first committed writes only.

For another gateway, keep these review questions. Do not require
AgentCore service names, a particular claim name or Pellier's audit schema
where the application uses a different implementation.
