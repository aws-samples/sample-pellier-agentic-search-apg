# Contract 4: Authorize and deduplicate writes

**Question:** Can execution exceed its authorized terms or repeat a business effect?

**Key takeaway:** Approval, authorization, execution and commit are separate
claims. A retry key and a business operation id answer different questions.

## Establish the business rule first

Pellier requires Nadia to approve every credit's exact terms. Another
application may permit bounded autonomous writes. Identify who or what can
authorize the action. Identify its scope, limits and expiry. Do not infer
authorization from an agent's confident proposal or from possession of an
idempotency key.

Trace every entry point to the database function and inspect the effective
role. A direct table UPDATE can bypass an otherwise correct insert guard.
A SECURITY DEFINER function needs a protected owner, schema-qualified object
names, a fixed safe search_path and restricted EXECUTE privileges. Check
inherited and PUBLIC privileges. Do not check only grants that name the role
directly. If pgAudit is the database's record of the write, make each login that
calls the function a member of its owner (`WITH INHERIT FALSE, SET FALSE` grants
nothing else). pgAudit skips statements inside a SECURITY DEFINER function when
the session's login is not a member of the role the function runs as.

## A complete, runnable example

[examples/setup.sql](../examples/setup.sql) implements a small expense-credit
example. It has a dedicated schema and two restricted roles. The write role
can execute one function. It cannot read or modify its tables directly.
Trusted example setup creates approvals. The writer cannot approve its own
request. The function does the following:

1. Finds and locks the approval named by the key.
2. Returns an existing matching credit as a replay. Changed terms conflict.
3. Requires an approved review with the exact customer, amount and reason.
4. Locks the expense and refuses a second credit under another approval.
5. Writes the credit and its first-write audit record in one transaction.

The schema bounds amounts in cents. It has unique constraints on both the
approval and expense. In this teaching example the key is `approval:<id>`.
The key is for correlation. It is not a secret and it is not a substitute for
authorization.

The example intentionally does not implement staff authentication, an
approval UI, payment settlement or a gateway. Its trusted setup represents
the approval service. It also does not claim to prevent a privileged owner
from changing records. Those boundaries require their own review.

## Replay and concurrency

At READ COMMITTED, a second call waits for the locked approval. It then reads
fresh committed state and returns the existing credit. A second approval for
the same expense is serialized on the expense row and returns `already_paid`.
Those are the example's tested outcomes. Different isolation levels can
require transaction retries. Do not copy Pellier's exact SQLSTATE outcomes
onto a different function. Test the isolation level the application uses.

Use [the worked review](../examples/expense-review.md) for the direct-update
failure, its correction and a replay. The maintainer regression tests also
race two real connections against the function in this package. Uniqueness
alone does not guarantee a friendly replay result. Inspect the error path too.

## Policy limits

Pellier uses AgentCore Policy at AgentCore Gateway for the workshop's $100
limit. This is separate from its database function's $500 ceiling. A deny
policy needs missing-input and boundary tests as well as an allowed case:

```cedar
forbid(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"pellier-store-tools___give_store_credit",
  resource == AgentCore::Gateway::"<gateway arn>"
)
unless {
  context.input has amount_cents &&
  context.input.amount_cents <= 10000
};
```

This Pellier-specific fragment assumes a compatible schema and separate
permits. A forbid does not grant access. Test no matching permit, a matching
permit, a matching forbid, missing input, 10000 cents and 10001 cents. The
local expense example does not deploy or test this policy.

## Evidence has a scope

| Claim | Evidence | Limit |
|---|---|---|
| The request was authorized | Correlated policy decision | Does not prove execution |
| The operation executed | Execution result or defined audit record | Does not by itself prove commit |
| The state change committed once | Committed row and uniqueness under the operation's key | Does not establish every attempted call |

Define the audit convention. This example records first committed writes. It
does not record every invocation. A replay returns `replayed: true` without
another audit row. A denied gateway request needs its policy decision plus
absence checks. The absence of an audit row cannot prove a denial by itself.
If every attempt must be recorded, use a separate attempt log. It should
include failures and replays.

Query `approval` in [proof-queries.sql](proof-queries.sql) checks exact terms
and missing links. Query `privileges` checks effective access. Both report
explicit counts or outcomes. Tests need positive controls, changed terms,
missing approvals, direct table writes and concurrent retries.

See [PostgreSQL SECURITY DEFINER guidance](https://www.postgresql.org/docs/current/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY)
and [effective privilege functions](https://www.postgresql.org/docs/current/functions-info.html#FUNCTIONS-INFO-ACCESS-TABLE).
