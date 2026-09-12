# Handoff source contract

The stable anchors to author lab content, screenshots, and validation steps against.
Everything here is verified in source on this branch (`governed`, DAT416). Where a number
can be recomputed, the command that recomputes it is given instead of a copy: a hand-kept
number is how the eighteen-versus-three policy drift survived for weeks.

Read `CLAUDE.md` first for the repository contract and the participant/maintainer modes.

## Two tool counts, and why both are correct

| number | meaning | source |
|---|---|---|
| **17** | the canonical tool vocabulary. Every Gateway surface Lambda and every schema in `TOOL_SCHEMAS` covers all of them, and `/api/observatory/build-state` reports all of them. | `scripts/deploy/gateway_tool_schemas.py` |
| **15** | what this workshop iteration **publishes** at the start, 16 after Lab 3a. `restock_inventory` and `get_ticket_history` are deferred; `issue_credit` is published for staff only. | `WORKSHOP_DEFERRED_TOOLS` in the same module |

Conflating them produces a step that counts tools and gets the wrong answer. Recompute
both, plus the per-target split and the baseline Cedar, with:

```bash
python3 scripts/describe_workshop_publication.py
```

`schema_for(surface, workshop=...)` has **no default** on purpose. Publication paths pass
`workshop=True`; the Gateway vocabulary migration passes `workshop=False` because it needs
the full vocabulary to compute what it is deliberately not publishing.

## Baseline authorization on a fresh stack

7 policies, all permits, no forbid. `scripts/deploy/render_agentcore_project.py` is
the source; this table is checked against it by
`pellier/backend/tests/test_fresh_policy_set.py`. Every statement types the
principal as `AgentCore::OAuthUser` and pins `resource ==` to the deployed
Gateway ARN, which is why policies render only in the second deploy phase.

| policy | effect | shape |
|---|---|---|
| `baseline_permit_workshop_tools` | permit | `action in [...]` over 11 catalogue reads that expose no customer data. No wildcard, so a tool published later is denied by default. |
| `get_customer_preferences_owner_only` | permit | only when the token's `custom:customer_id` equals `context.input.customer_id` |
| `get_audit_trail_owner_only` | permit | the same condition on the audit-trail read |
| `initiate_return_shopper_damaged` | permit | a principal carrying `custom:customer_id`, with `context.input.reason == "damaged"`; no ownership binding |
| `initiate_return_staff_scope` | permit | a principal whose `custom:staff_scope` is `returns`; no reason condition |
| `issue_credit_staff_scope` | permit | the same staff condition on `issue_credit`; no shopper permit names that action |
| `replace_damaged_item_staff_scope` | permit | staff scope `returns`, damaged reason; the target and Aurora separately validate the exact approved terms |

Identity reaches Cedar as a claim. The Cognito pre-token trigger
(`scripts/deploy/cognito_customer_claim.py`) stamps `custom:customer_id` from
`pellier.principal_customers`, the table Row-Level Security keys off, and
`custom:staff_scope` from operator group membership. A token with neither claim
may read the catalogue and nothing else.

The two `*_owner_only` policies matter to how Lab 4 is described: the
customer-read boundary on the managed rail is **Cedar**, evaluated before the
tool runs. Aurora Row-Level Security is a second, independent refusal on the
database session, and Lab 4 proves them separately for exactly that reason. A
claim that "RLS scopes what the agent can read" is only half the sentence.

`restock_inventory` is not published on the shopper Gateway and has no permit.
It is an operator capability behind the desk's own authorization; keeping it
unpublished means a shopper token has no action id to attempt, and keeping it
out of every permit means a later publication is still denied by default.

The Lab 4 identity condition (`principal.getTag("custom:customer_id")` bound to
`context.input.customer_id` on the return action) is **absent from the baseline
on purpose**. A fresh stack that shipped it would make Lab 4 step 3's DENY fire
before the participant wrote anything. The participant's forbid is scoped by
`when { principal.hasTag("custom:customer_id") }`, so it never touches staff.
`pellier/backend/tests/test_fresh_policy_set.py` owns this contract.

## Operator authorization

The Pellier Operator desk is one authorization boundary, and it is **not** the same thing
as being signed in.

| caller | result |
|---|---|
| anonymous | `401 authentication_required` |
| authenticated, not in the group | `403 operator_group_required` |
| member of `pellier-operators` | access |

Enforced in **one** place, and the honesty of that number matters:

1. `services/auth.py::require_operator`, declared once on the `APIRouter` so a new route
   inherits the boundary rather than being forgotten.
2. `bootstrap-labs.sh` creates the group and its one member, **verifies membership rather
   than assuming it** (every create call tolerates "already exists", so success of the
   calls proves nothing), and asserts that no shopper is in it. Health-gate check 11
   refuses readiness when the operator is not a member, and fails when a shopper is. That
   second case is the regression to watch: it restores the original defect through a
   configuration change that looks legitimate.

### There is no Gateway defence-in-depth for operator authorization

This is a structural limit, not an omission, and it will not be fixed by writing a better
policy. The desk invokes exactly two capabilities:

| capability | on a fresh Gateway | why it cannot carry an operator-only condition |
|---|---|---|
| `initiate_return` | published, permitted (damaged-only) | shared with the shopper rail, and it is Lab 4's whole subject |
| `issue_credit` | published, permitted (staff scope only) | the desk executes an approved credit with the operator's own token; no shopper permit names it |

A policy gating `restock_inventory` on the group was added and removed. It enforced
nothing: `restock_inventory` is a deferred tool with no operator route (the shopper-facing
Inventory Agent no longer binds it), and it has no matching permit, so an operator and a shopper are **both denied either way**. It changed
the recorded reason and no outcome, while risking the whole provision on an unproven
`getTag(...).contains(...)` under `FAIL_ON_ANY_FINDINGS`, where a rejected policy fails
`agentcore deploy` and leaves no Gateway, Runtime or Memory.

`test_staff_authority_is_a_scope_claim_never_a_group_name` stops that returning as reassurance.
**When an operator-only tool is intentionally published**, add a separate single-action
policy for it, live-validate it, and update that test to expect it by name rather than
deleting the guard.

Note the layers precisely: a shopper cannot execute `issue_credit` through the Gateway
because no permit names a shopper principal for it, so the engine denies by default; and
no shopper-facing specialist can bind it, because the managed dispatcher refuses to build
one that does. Neither is a forbid. Naming the wrong layer as the one denying is how each
layer ends up believing the other is enforcing.

The group name has exactly one source: `services/auth.py::OPERATOR_GROUP`. The renderer
no longer carries a copy, because a second constant with no policy behind it is drift
waiting to happen.

**What this replaced.** `require_operator` stopped at "the token verifies and carries a
subject", and all eight `GET` routes were open. So `marco` could confirm, decline and
execute any review and call `issue_credit`, while the module docstring explained that
Cedar forbids `issue_credit` for shopper principals because a shopper-facing agent must
never issue itself store credit. The reads were open for a real reason (a `GET` needing no
token means the desk is never a blank `401` on a fresh box), and that reason lost to what
the reads return: client standing, preferences, order history, credits, and the governance
verdicts.

## Resource ownership

Who may change each deployed resource, and how you would know it drifted. Ownership is
determined by **what created it plus CloudFormation membership**, never by tags:
`PellierWorkshopId` carries three different values in the audited account from separate
provisioning runs, so it is forensic provenance and not authority.

| resource | created by | updated by | destroyed by | declared in | drift check |
|---|---|---|---|---|---|
| AgentCore Runtime | `agentcore deploy`, lands in CFN stack `AgentCore-pellier-default` | the same CLI | the CLI / stack delete | `render_agentcore_project.py` `runtimes[]` | `scripts/health-gate.sh`, AgentCore state |
| AgentCore Memory | same stack, same CLI | the same CLI | the CLI / stack delete | `memories[]`, `USER_PREFERENCE` only | `scripts/health-gate.sh`; runtime DATA cleaned by `reset_memory_runtime.py`, which never touches the resource |
| Gateway | fresh: the CLI project. Audited account: direct control-plane API, in **no** stack | fresh: CLI. Audited: `update_gateway`, and only for policy mode | never deleted by any script here | `agentCoreGateways[]` | `describe_workshop_publication.py` vs live discovery |
| Gateway targets | as Gateway | `update_gateway_target`, in place | never deleted and recreated | inline `toolSchema` from `gateway_tool_schemas.py` | `provision_agentcore_end_to_end.py` asserts live discovery == expected |
| Policy engine | as Gateway | never replaced: `add policy-engine` creates rather than adopts, so a project-declared engine would be a *second* engine | never | `policyEngines[]` | `policy_mode.py` (read-only with no flags) |
| Policies | fresh: `baseline_policies()` through the CLI. Participant rule: `agentcore add policy` in Lab 4 | `update_policy` keeps the policy id, so history and attachments survive | reset removes only the participant rule | `render_agentcore_project.py` | `policy_mode.py`; reset restores mode at both scopes |
| Target Lambdas (4) | `deploy_lambda.py`, invoked by `provision_agentcore_end_to_end.py` | the same script | not by any script here | `scripts/deploy/pellier_*_server.py` | `provision_agentcore_end_to_end.py` code-SHA assertion |
| IAM (3 resources) | the CFN stack | the stack | the stack | CDK output of `agentcore deploy` | stack status `UPDATE_COMPLETE` |

Two rules follow from that table and both have already been learned the hard way:

1. **A resource in the stack is changed by the tool that owns the stack.** A direct
   control-plane update to Runtime or Memory drifts the stack from reality, and the next
   CLI deploy reverts it.
2. **The audited engineering account is not shaped like a fresh one.** Its Gateway,
   targets and policy engine were created by direct API and are in no stack, which is why
   `agentcore import gateway` mapped it with zero targets (the CLI cannot represent an
   inline tool schema) and `agentcore import memory` refused outright. A fresh account
   does not have that split. `scripts/migrate_gateway_vocabulary.py` exists only for the
   historical environment and its `ownership.py` pins make it refuse to run anywhere else.

## Participant agent names, exact

    Search Agent · Personalization Agent · Pricing Agent · Inventory Agent
    Customer Service Agent

`Inventory Agent` is the Lab 1 exercise and reports `"exercise"` in build-state until it
is wired.

## Lab 1 edit points, the only safe edit sites

| file | markers |
|---|---|
| `pellier/backend/agents/inventory_agent.py` | `# === WORKSHOP · Inventory Agent · definition: START ===` / `: END ===` |
| `pellier/backend/services/agent_tools.py` | `# === WORKSHOP · Inventory Agent · check_inventory: START ===` / `: END ===` |

The separator is U+00B7. A participant searches the file for the string the guide quotes,
so an ASCII substitution breaks the only instruction that lane gives.

Five fields in the definition block: `_INVENTORY_AGENT_STUBBED`,
`_INVENTORY_SYSTEM_PROMPT_FOR_AGENT`, `_INVENTORY_MODEL_ID`, `_INVENTORY_MAX_TOKENS`,
`_INVENTORY_TOOLS`. No `temperature`; the configured Sonnet profile rejects it. The tool
body calls `BusinessLogic.check_inventory` through `_run_async`.

## Recovery paths

    solutions/waking-the-stock-keeper/agents/inventory_agent_solution.py
      -> pellier/backend/agents/inventory_agent.py
    solutions/closing-marcos-gap/services/agent_tools_check_inventory_solution.py
      -> pellier/backend/services/agent_tools.py
    solutions/the-concierge/policies/identity_match_forbid.cedar
      -> policies/workshop_identity_match_forbid.cedar

Directory names keep their historical form deliberately; the **file** names are canonical.
Both Lab 1 copies retain the marker regions, so a participant who takes the fallback can
still read what changed.

`pellier/backend/tests/test_workshop_marker_contract.py` asserts every anchor above from
the source side, including that the Lab 4 starter still holds `unless { false }` rather
than the answer.

## Proof endpoints

    GET  /api/observatory/build-state          {"agents": {...}, "tools": {...}} -> "shipped"|"exercise"
    GET  /api/observatory/executions[/{id}]    execution reconstruction, principal-scoped
    GET  /api/observatory/proof-board          the assembled proof view
    POST /api/observatory/tools/discover       Aurora semantic tool-registry search
    GET  /api/operator/capabilities            live governance truth per capability
    GET  /api/operator/reviews[/{id}]          review + four assurance axes + execution receipt
    POST /api/operator/reviews/{id}/confirm    human decision, then execution

`POST /api/observatory/tools/discover` is an Aurora search, **not** MCP `list_tools`. MCP
tool discovery is reached only through `MCPClient(streamablehttp_client(...))` with a
Cognito bearer token; no HTTP endpoint proxies it.

## Evidence surfaces, and the question each answers

    pellier.approvals            was it authorized by a human, and against which turn
    pellier.execution_receipts   what the policy, Aurora and evidence verdicts were,
                                 one row per attempt, append-only
    pellier.tool_audit           which tools actually ran. Absent on a Cedar DENY, by
                                 design: that absence is the evidence
    pellier.write_operations     the idempotency claim; completed = applied exactly once
    pellier.operator_episodes    derived memory of terminal outcomes
    pellier.model_invocation_receipts
                                 redacted model metadata: model/profile id, token
                                 counts, latency, outcome and trace correlation
    pellier.evidence_ledger_event_refs
                                 typed metadata index over the canonical receipts;
                                 API reads still filter by verified principal
    pellier.observatory_spans    reserved, retention-bounded Aurora span cache.
                                 CloudWatch/AgentCore telemetry is the managed span
                                 authority; migration 027 only converges the name

An ALLOW never proves execution occurred. Keep policy, execution and data evidence
separate.

## Reset

```bash
PELLIER_REPO=<repo> bash scripts/reset-governed-workshop.sh
```

One command. The Memory leg is part of the lifecycle now, not a second step someone has
to remember: Aurora alone is not enough, because AgentCore Memory holds actor-scoped
`USER_PREFERENCE` records and a new session id does not isolate an actor-scoped
namespace. `reset_memory_runtime.py` is dry-run by default, preserves the three seeded
persona actors, and never touches the Memory resource.

**Reset stops the application.** It quiesces `pellier.service`, proves no session is
mid-execution, resets, cleans Memory, restores participant Cedar, restarts on a trap, and
verifies the baseline. A truncate underneath a live turn can clear an idempotency claim
after its write committed. Four explicit escape hatches, documented in the script header:
`PELLIER_RESET_ALLOW_LIVE`, `PELLIER_BACKEND_PORT`, `PELLIER_RESET_SKIP_MEMORY`,
`PELLIER_RESET_SKIP_AGENTCORE`.

### Which interpreter

`pellier/backend/requirements.lock` is the validated set (botocore pinned at 1.43.51).
Where it lives differs by host, and assuming either answer is a real failure mode:

| host | validated interpreter | note |
|---|---|---|
| workshop box | `python3` | the lock is installed into `~/.local`; **there is no venv** |
| developer box | `./pellier/backend/.venv/bin/python` | ambient `python3` may be older |

Governance mutations refuse to run under an SDK whose service model lacks the fields they
set. Measured: ambient botocore 1.43.28 has no `UpdatePolicy.enforcementMode`, so
`policy_mode.py` would have switched Cedar enforcement off while returning success.
`scripts/deploy/sdk_preflight.py` reports what an interpreter can do.

### Expected baseline after reset

Derived from the canonical seed contract (migrations plus `seed_pellier_catalog.py`), not
from a live count minus known rows:

    customers 17 · orders 66 · product_catalog 1000 · warehouses 3
    warehouse_inventory 120 · inventory_ledger 120 · customer_episodic_seed 9
    return_policies 5 · tools 15 · principal_customers 3
    returns 1 · tool_audit 1 · governed_receipts 1   (all three: the migration 010 forensic incident)
    store_credits 1 (CUST-SARAH) · support_tickets 3
    approvals 0 · conversations 0 · messages 0 · operator_episodes 0
    execution_receipts 0 · write_operations 0 · semantic_cache 0 · observatory_spans 0

`reconcile_inventory()` returns no rows on a clean baseline.

**Do not author against serial ids.** Reset uses `RESTART IDENTITY`, so review and return
ids restart from 1 on every reset. Screenshot a review by its content, not `#40`.

## Canonical personas and clients

    Marco   CUST-MARCO    maison      7 orders
    Anna    CUST-ANNA     circle      5 orders
    Theo    CUST-THEO     registered  4 orders
    Jessica CUST-JESSICA  circle      5 orders   ticket asserts a return with no row (deliberate)
    Rachel  CUST-RACHEL   registered  3 orders
    Amara   CUST-AMARA    maison      5 orders   no principal_customers mapping (deliberate RLS fixture)

The three personas are shoppers with Cognito users; the remaining twelve are
operator-side client records only. A client id must never resolve as a signed-in shopper.

## Product assets

Catalog imagery is a release asset, not a local convenience. A file on disk that git does
not track renders as a broken image in a clean clone while looking finished locally.

```bash
python3 scripts/audit_product_assets.py --table
python3 scripts/audit_product_assets.py --print-untracked | xargs git add
```

The contract: a committed 4:5 PNG master per SKU, plus `-480` and `-960` derivatives in
both WebP and AVIF, all tracked. Hero and landing slots are intentionally landscape and
some publish a 1600 variant; `scripts/derive_product_variants.py` treats the widths a
master already publishes as its contract and refuses to crop a master that fails the 4:5
rule. `pellier/backend/tests/test_product_asset_tracking.py` fails on an untracked
required asset, a half-tracked srcset, or a fixture path that resolves to nothing.

Client and persona portraits are composed at runtime from a slug list in
`personaPhotos.ts`, so no literal exists to grep. That list is parsed by the audit; adding
a client without a portrait fails rather than resolving to an initial circle.

## Intentional historical names, do not "fix"

    process_return_idempotent            Postgres function, stable identifier
    solutions/waking-the-stock-keeper/   recovery path directory
    _MIGRATION_TOOL_ALIASES              Lambda dispatch compatibility, marked TEMPORARY
    migration 002 ALTER TABLE, 027       one-time convergence of an existing cluster

## What remains

**No known source defect.** The outstanding gap is a fresh-account deployment rehearsal of
the exact Studio pin. Everything below has passed on the pushed SHA: the backend and
frontend suites, type-check, lint, build, the Studio validator, and `git diff --check` over
the whole commit range. None of that exercises a clean AWS account.

### How to close it

1. Deploy a new Workshop Studio environment from the current pin.
2. Require CloudFormation success **and** the health gate reporting READY. Either alone is
   insufficient: CloudFormation has reported success over a box whose managed path failed.
3. Read the three logs, in this order:
   * `/var/log/bootstrap-environment.log`
   * `/var/log/pellier-agentcore.log`
   * `/var/log/pellier-health-gate.log`
4. Verify Runtime, Memory, Gateway, **15** published tools, **6** Cedar policies, Aurora
   Row-Level Security, and the `pellier-operators` membership boundary.
5. Run all four labs with the participant commands, including operator access and the
   shopper `403`.
6. Fix any failure **in the owning bootstrap, template or source file**, re-pin Studio, and
   repeat from another clean account. A repair applied by hand on the box is not a fix; it
   is a fix the next account will not receive.

### Likely remediation owners

| symptom | owner |
|---|---|
| `Missing required environment variable: AGENT_MODEL_ID` | model-access detection, and the bootstrap export in the `sudo -u` block |
| RLS denies every signed-in shopper | principal seeding, or the migration policy |
| Wrong or empty region | IMDSv2 token-first discovery in `bootstrap-environment.sh` |
| Operator desk refuses a legitimate operator, or admits a shopper | Cognito group creation, membership, or `cognito:groups` claim parsing |
| Runtime, Memory or Gateway absent | `provision_agentcore_end_to_end.py`, or the generated deployment configuration |

Each of those five was fixed from a log or from source inspection, not from a green fresh
run, so the rehearsal is their first real exercise. Expect them here before anything else.

**Do not reintroduce the ineffective operator Cedar policy.** `issue_credit` is
published because the desk executes an approved credit through it, and its only permit
requires the staff scope claim; that is a purpose, not manufactured coverage. Both are
recorded decisions with tests behind them:
`test_staff_authority_is_a_scope_claim_never_a_group_name` and
`test_issue_credit_is_published_for_staff_and_unreachable_by_a_shopper`.

### Known open, and not defects

These are decisions or deferrals, listed so nobody rediscovers them as surprises.

| item | state |
|---|---|
| Live Gateway vocabulary | Three targets still publish the retired names. Source is aligned; convergence is `migrate_gateway_vocabulary.py`, which is pinned to one audited account. |
| Live baseline permits restock | The live baseline permits the retired restock action where fresh does not. `scripts/deploy/plan_restock_alignment.py` prepares the alignment and cannot apply it. |
| RLS reclassification | Scoped to `initiate_return` only. |
| Weak tests, swallowed exceptions, alias removal trigger | Explicitly deferred. |
| Trailing-whitespace debt | 527 lines predate this work. `test_no_whitespace_damage.py` holds the ceiling and explains why a repo-wide strip is unsafe. |

## Validation gates

```bash
cd pellier/backend && python -m pytest -q
cd pellier/frontend && npm test -- --run && npm run type-check && npm run lint && npm run build
python3 scripts/audit_product_assets.py
python3 scripts/describe_workshop_publication.py
git diff --check
find scripts -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n
```

None of these need AWS. Anything that does is called out where it appears; a green suite
is not evidence that a live environment matches this source.
