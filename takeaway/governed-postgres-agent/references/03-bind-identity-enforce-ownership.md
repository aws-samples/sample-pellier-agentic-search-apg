# Contract 3: Bind identity and enforce ownership

**Question:** Can a proposed argument change whose records are accessed?

**Key takeaway:** Authentication identifies the caller. Authorization decides
what that caller may do. RLS can enforce the row boundary when a tool's SQL
uses the wrong customer filter.

## Trace each boundary

Follow the verified caller through application binding, tool authorization
and the database transaction. In Pellier, the server replaces customer-scoped
arguments before the call leaves AgentCore Runtime. AgentCore Policy checks
direct calls at AgentCore Gateway. Aurora PostgreSQL enforces row ownership.
These are separate controls with separate tests.

Test a forged tool argument while authenticated as another customer. Inspect
what crosses the boundary using that probe's correlation id. The latest
unrelated ticket audit row cannot prove that binding worked. Then test a
direct gateway call. This exercises authorization independently of
application binding. A local binding probe does not establish deployed
behavior.

## Bind identity on the same connection and transaction

An application using transaction-local roles and context can follow this
pattern after validating authentication:

```python
async with conn.transaction():
    await conn.execute("SET LOCAL ROLE app_agent")
    await conn.execute(
        "SELECT set_config('app.customer_id', $1, true)", verified_customer_id
    )
    rows = await conn.fetch(query, *params)
```

The role name is fixed by trusted code. The customer value is bound as a
parameter. `SET LOCAL` ends with the transaction. All scoped operations must
use that same transaction and connection. Test pooled connection reuse with
two customers and an unbound request. Do not leave a broader session-level
identity setting for the next transaction to inherit.

`session_user` identifies the login. `current_user` reflects the effective
role, including role switches and SECURITY DEFINER functions. A custom
setting supplies application context. It is not independently authenticated.
A caller allowed to issue arbitrary SQL can change an ordinary custom GUC.
This pattern assumes trusted parameterized tools and a protected database
connection. It does not protect against an attacker who holds that connection
or its privileged login. Review who can switch roles, who can set context and
who can reach each entry point.

## Review the policies as a whole

For equal read and write ownership, a policy may use the same expression:

```sql
CREATE POLICY tickets_own_rows ON support_tickets TO app_agent
    USING (customer_id = nullif(current_setting('app.customer_id', true), ''))
    WITH CHECK (customer_id = nullif(current_setting('app.customer_id', true), ''));
```

This adaptation pattern assumes the role has the intended table privileges.
`USING` controls existing rows. `WITH CHECK` controls new row values. Review
all policies that apply to the command and role. Permissive policies combine
with OR. Restrictive policies further constrain access. Multiple policies
can be correct. Also inspect table ownership, superuser, `BYPASSRLS`, RLS
enablement, `FORCE ROW LEVEL SECURITY` where applicable, and any function
that changes the effective role.

## Verification

Query `ownership` in [proof-queries.sql](proof-queries.sql) uses known fixture
rows to establish own-row access and a wrong-customer denial. A separate
unbound probe must return none. Where writes are intended, pair a permitted
own-row insert with a refused foreign insert. SQLSTATE `42501` alone cannot
distinguish missing INSERT privilege from RLS enforcement.

An `EXPLAIN` can help inspect enforcement and performance. Correct RLS
behavior does not require a particular InitPlan, One-Time Filter or
never-executed scan. Judge the access result first.

AgentCore Memory may supply preferences. It supplies neither authenticated
identity nor authorization. The caller's verified identity identifies the
caller. The policies determine what the caller can access.

See [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
