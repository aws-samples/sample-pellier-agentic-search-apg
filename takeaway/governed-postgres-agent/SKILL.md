---
name: governed-postgres-agent
description: Review an agent tool that reads or writes PostgreSQL. Trace its permissions, caller identity, SQL and retry behavior; return source-backed findings and a verification plan that separates code evidence from tested behavior.
---

# Can this agent read or change something it should not?

Review one tool against the applicable database contracts from DAT416. An
agent selects tools and proposes arguments; the application implements their
SQL and controls their authority. Establish what those controls enforce.

**Key takeaway:** An agent's answer is a claim. Permissions, identity,
database behavior and retry behavior determine what it can actually do.

## Start with the requested tool

Identify the tool, its caller and the operation under review. Trace its
arguments through the implementation to the SQL, database role and returned
result. Follow wrappers and alternative entry points when they affect that
operation. Cite file paths and lines. If the entry point is unclear, locate
likely candidates before asking one focused question.

Keep the review within the user's request. Default to source inspection and
a proposed test plan. Do not edit files, create approvals, deploy, or execute
database writes unless authorized. Database probes that write or change
policies belong in an explicitly selected disposable test environment.
Rollback does not undo every possible external trigger side effect.

## Select the contracts that apply

| Contract | Question | Read when relevant |
|---|---|---|
| 1. Preserve requirements | Can retrieval or a retry lose the caller's hard constraints? | [Retrieval](references/01-filter-before-ranking.md) |
| 2. Ground bounded answers | Does the tool preserve authoritative facts, missing records and errors? | [Tool results](references/02-bounded-facts.md) |
| 3. Bind identity and ownership | Can proposed arguments change whose records are accessed? | [Identity and RLS](references/03-bind-identity-enforce-ownership.md) |
| 4. Authorize and deduplicate writes | Can execution bypass the approved scope or repeat a business effect? | [Writes](references/04-approve-and-deduplicate-writes.md) |

A stock lookup may need contracts 1 and 2; a customer ticket read needs 2 and
3; a reimbursement needs 3 and 4. Explain exclusions. Pellier's human
approval, RRF configuration, role layout and AgentCore services are examples,
not requirements for every application. Establish the application's intended
authorization and business rules before judging its implementation.

For tools published through a gateway, also read [MCP and AgentCore](references/mcp-publishing.md).
Read only the references needed for the selected operation.

## Build evidence for each claim

Separate what source inspection supports from what a test actually observed.
Do not mark behavior as passed because a function exists or a query could be
run. An unavailable database leaves runtime behavior **not tested**; it does
not prevent a useful source review.

Use **passed**, **failed**, **not tested**, or **not applicable** for each
specific probe. Include its identity, inputs, environment and correlation
key. A successful local probe is not evidence that a deployed build behaves
the same way. State which build or deployment was tested when known.

Every denial needs a positive control through the same relevant path. A
query returning no rows may mean missing evidence. Report the number of
requests and records examined; distinguish an empty test from a clean one.
Compare outcomes against requirements preserved independently of the code
being tested. Use request, receipt or write keys rather than the latest
global audit row.

[Query examples](references/proof-queries.sql) demonstrate these checks on
the supplied example schema. Map schema names, identity, permissions and
business expectations before adapting them. They do not run unchanged on
Pellier. `pg_stat_statements` is optional aggregated workload evidence, not
proof of one request. A policy decision establishes authorization; an
execution record establishes a recorded execution; a committed row establishes
stored state. Correlate the evidence needed for the claim.

## Return a review someone can act on

Lead with the most consequential supported finding. For each finding give:

- **Claim:** the invariant and its business scope.
- **Code evidence:** source location and the mechanism or gap.
- **Test evidence:** what ran, inputs, expected and observed results.
- **Result:** the probe status, including not tested where appropriate.
- **Limit:** what remains unproven or depends on an assumption.
- **Next action:** the smallest useful correction or verification step.

End with the applicable contracts still untested. Do not certify an entire
application from one reviewed tool. [Worked expense review](examples/expense-review.md)
shows the expected level of specificity, including a failing case and its
corrected outcome.
