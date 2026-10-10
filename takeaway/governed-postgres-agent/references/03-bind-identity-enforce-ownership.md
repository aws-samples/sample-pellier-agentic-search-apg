# Contract 3: bind identity, enforce ownership

The caller comes from the verified token. The server sets the customer on
every scoped call. The database enforces ownership on its own.

## Template: the server overwrites what the model proposed

The model may ask for anyone's records; the conversation may contain a
plausible reason ("we share an address"). The server replaces the customer
argument with the signed-in principal before the call leaves the runtime,
for every tool that takes one. Keep that list explicit, and keep it beside the
list of tools the agent may call, so the two are reviewed together:

```python
SUPPORT_TOOLS = ("get_orders", "get_tickets", "get_return_policy")
CALLER_BOUND = ("get_orders", "get_tickets")   # the server overwrites customer_id on these

def reconcile(call, principal):
    if call.name in CALLER_BOUND:
        asked = call.args.get("customer_id")
        call.args["customer_id"] = principal.customer_id
        if asked and asked != principal.customer_id:
            audit_note(f"model asked for {asked}, server bound {principal.customer_id} (overwritten)")
    return call
```

The test that proves it: send a forged call for another customer through the
binding while a shopper is signed in. It must leave as the shopper. Do not
rely on real conversations; the model rarely asks, so a passing turn proves
little. Run the forged call every time.

## Template: a principal per transaction

Bind the verified username on the session, local to the transaction, and read
it in the policy with the `missing_ok` form so an unbound session matches
nobody:

```python
async with conn.transaction():
    await conn.execute("SELECT set_config('app.principal_username', $1, true)", username or "")
    rows = await conn.fetch(query, *params)
```

`set_config(..., true)` scopes the value to the transaction. Pooling then
cannot leak one principal into the next request. Over the RDS Data API the
same `set_config` runs as the first statement in the transaction.

## Template: row-level security

One expression decides which rows the session may see (`USING`) and which it
may write (`WITH CHECK`). Resolve the principal to the owner id with a
subselect so the policy does not depend on the username column being on the
owned table:

```sql
ALTER TABLE orders          ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_tickets ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_owner ON orders TO app_agent
    USING      (customer_id = (SELECT id FROM customers
                                WHERE cognito_username = current_setting('app.principal_username', true)))
    WITH CHECK (customer_id = (SELECT id FROM customers
                                WHERE cognito_username = current_setting('app.principal_username', true)));
-- the same policy on support_tickets
```

A write in someone else's name fails with SQLSTATE `42501`. A read of someone
else's rows returns none. Note the asymmetry: reads fail silently (an empty
result), writes fail loudly. An empty result therefore has two possible causes,
out-of-scope rows or an unbound principal; log which.

Preconditions, or a denial proves nothing (Pellier checks these in the lab
worksheet before trusting a result):

- the agent role has no `BYPASSRLS` and is not superuser;
- the agent role does not own the tables, or `FORCE ROW LEVEL SECURITY` is on;
- exactly one permissive policy per table (permissive policies combine with
  OR, so a second one widens access whatever the first says);
- the policy is `TO` the agent role, and the app connects as that role.

## Template: policy at the gateway

Where tool calls cross a gateway, authorization decides whether the call runs
at all. In Cedar, an owner-only read permit matches the customer in the call
to the identity in the token, so a direct call with a mismatched customer is
denied before any tool runs:

```cedar
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"store-tools___get_tickets",
  resource == AgentCore::Gateway::"<gateway arn>"
)
when { context.input.customer_id == principal.customer_id };
```

Policy stops a wrong call. Row-level security stops a wrong query. One without
the other leaves a path open: a direct caller who bypasses the agent, or a tool
whose own SQL asks for the wrong rows.

## Memory is context, not authority

Remembered preferences (AgentCore Memory, a profile table, a vector store of
past turns) may shape an answer. They never set `customer_id`, never satisfy a
policy, and never justify a write. Read them under the signed-in id and pass
them to the model as labelled context.

## Review questions

- Whose data was read, and what would have stopped a read of someone else's?
- Is the customer argument set by the server after the model proposes the call?
- Does the agent role bypass RLS by ownership, attribute or a second policy?
