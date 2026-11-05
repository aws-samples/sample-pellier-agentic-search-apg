---
name: governed-postgres-agent
description: Use when reviewing an agent tool that reads or writes PostgreSQL, such as whether an agent could read another customer's rows, lose a user's requirements on a retry, or write the same business effect twice. Not for building a new agent.
---

# Can this agent read or change something it should not?

Review one tool against the applicable database contracts from DAT416. An
agent selects tools and proposes arguments. The application implements their
SQL and controls their authority. Establish what those controls enforce.

**Key takeaway:** An agent's answer is a claim. Permissions, identity, database
behavior and retry behavior determine what the agent can actually do.

## Start with the requested tool

Identify the tool, its caller and the operation under review. Trace its
arguments through the implementation to the SQL, database role and returned
result. Follow wrappers and alternative entry points when they affect that
operation. Cite file paths and lines. If the entry point is unclear, locate
likely candidates before asking one focused question.

Keep the review within the user's request. Default to source inspection and
a proposed test plan. Do not edit files, create approvals, deploy or execute
database writes unless the user authorizes it. Database probes that write or
change policies belong in a disposable test environment that the user selects
explicitly. Rollback does not undo every possible external trigger side
effect.

## Select the contracts that apply

| Contract | Question | Read when relevant |
|---|---|---|
| 1. Preserve requirements | Can retrieval or a retry lose the caller's hard constraints? | [Retrieval](references/01-filter-before-ranking.md) |
| 2. Ground bounded answers | Does the tool preserve authoritative facts, missing records and errors? | [Tool results](references/02-bounded-facts.md) |
| 3. Bind identity and ownership | Can proposed arguments change whose records are accessed? | [Identity and RLS](references/03-bind-identity-enforce-ownership.md) |
| 4. Authorize and deduplicate writes | Can execution bypass the approved scope or repeat a business effect? | [Writes](references/04-approve-and-deduplicate-writes.md) |

A stock lookup may need contracts 1 and 2. A customer ticket read needs 2 and
3. A reimbursement needs 3 and 4. Explain any exclusion. Pellier's human
approval, RRF configuration, role layout and AgentCore services are examples.
They are not requirements for every application. Establish the application's
intended authorization and business rules before judging its implementation.

For tools published through a gateway, also read [MCP and AgentCore](references/mcp-publishing.md).
Read only the references needed for the selected operation.

## Build evidence for each claim

Separate what source inspection supports from what a test actually observed.
Do not mark behavior as passed because a function exists or a query could be
run. An unavailable database leaves runtime behavior **not tested**. It does
not prevent a useful source review.

Use **passed**, **failed**, **not tested** or **not applicable** for each
specific probe. Include its identity, inputs, environment and correlation
key. A successful local probe is not evidence that a deployed build behaves
the same way. State which build or deployment was tested when you know it.

Every denial needs a positive control through the same relevant path. A
query that returns no rows may mean missing evidence. Report the number of
requests and records examined. Tell an empty test apart from a clean one.
Compare outcomes against requirements that were preserved independently of
the code being tested. Use request, receipt or write keys rather than the
latest global audit row.

[Query examples](references/proof-queries.sql) demonstrate these checks on
the example schema in this package. Map schema names, identity, permissions and
business expectations before adapting them. They do not run unchanged on
Pellier. `pg_stat_statements` is optional aggregated workload evidence. It is
not proof of one request. A policy decision establishes authorization. An
execution record establishes a recorded execution. A committed row establishes
stored state. Correlate the evidence needed for the claim.

## Return a review someone can act on

Lead with the most consequential supported finding. For each finding give:

- **Claim:** the invariant and its business scope.
- **Code evidence:** source location and the mechanism or gap.
- **Test evidence:** what ran, inputs, expected and observed results.
- **Result:** the probe status, including not tested where appropriate.
- **Limit:** what remains unproven or depends on an assumption.
- **Next action:** the smallest useful correction or verification step.

End with the applicable contracts that are still untested. Do not certify an
entire application from one reviewed tool. The
[worked expense review](examples/expense-review.md) shows the expected level
of specificity. It includes a failing case and its corrected outcome.
