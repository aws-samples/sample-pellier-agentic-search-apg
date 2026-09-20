# Governed managed deployment

Pellier's existing governed managed-services deployment uses the legacy physical
CloudFormation name `AgentCore-pellierrc-default`. Adopt that deployment in place.
Its governed display name is `pellier-governed-managed`; the display name does
not rename the CloudFormation stack or its resources.

The nonsecret adoption profile is:

```sh
export WORKSHOP_FORMAT=governed
export PELLIER_DEPLOYMENT_SUFFIX=rc
export WORKSHOP_ID=dat416-rc
```

Set this profile before starting the renderer or provisioner process. The suffix
is read when the renderer module is imported. Supply account, identity, model,
and resource inputs through the deployment environment or private deployment
receipt. Do not commit those environment values or deployment endpoints.

| Identity | Existing value to preserve |
| --- | --- |
| CLI project | `pellierrc` |
| CLI target | `default` |
| Physical stack | `AgentCore-pellierrc-default` |
| Deployment suffix | `rc` |
| Workshop ownership tag | `PellierWorkshopId=dat416-rc` |

For `WORKSHOP_FORMAT=governed`, `scripts/deploy/render_agentcore_project.py`
adds these project and managed-resource tags while preserving the existing
workshop, deployment-class, and runtime-exposure tags:

```text
Name=pellier-governed-managed
Project=pellier
PellierVariant=governed
PellierComponent=agentcore
```

With `WORKSHOP_FORMAT` unset or set to `builders`, existing naming and tags stay
unchanged. Governed labeling does not change the shared Builders project default,
the selected suffix, the target, or the tool names embedded in Cedar actions.
Runtime, memory, gateway, policy-engine, and external Lambda identities must stay
the same during adoption.

## Pinned scaffold customization

The provisioner creates the `@aws/agentcore@0.29.0` scaffold before rendering.
On a governed render, the renderer customizes only the reviewed StackProps tag
block in `agentcore/cdk/bin/cdk.ts`:

```ts
      tags: {
        ...spec.tags,
        'agentcore:project-name': spec.name,
        'agentcore:target-name': target.name,
      },
```

CLI identity tags take precedence over project tags. Repeated rendering does not
duplicate the spread or rewrite an already customized scaffold. An unexpected or
ambiguous tag block stops rendering before runtime staging or configuration
writes; review the scaffold when upgrading the pinned CLI.

Configuration-only rendering without a CDK directory remains supported. Create
the pinned scaffold and render again before deploying so stack tags are included.
The renderer does not change the CLI's deployed-state file or choose a new stack.

## Adoption and lifecycle

Do not render into or customize the active generated project while a deployment
or Lab 3 rehearsal is running. Complete the schema/policy restoration first.
Source implementation and isolated tests can run independently.

Apply existing-stack labels with a reviewed tag-only change set that preserves
the deployed template, parameters, existing tags, and CLI identity tags. Confirm
there are no resource additions, removals, replacements, artifact changes, or
policy changes. Rendering the full project is not a tag-only operation because
it also stages runtime source and writes tool schemas and policy configuration.
After the rehearsal is restored, the next governed render must populate the
generated project tags and apply the scaffold customization before a later CLI
deployment. A source edit alone does not update an already generated project.

Do not change `pellierrc`, `default`, or `rc` to obtain a different physical stack
name. The CLI derives the physical stack name from project and target, so those
changes can select another stack. A literal rename would require a separate
CloudFormation ownership migration and matching CLI state, not a labeling update.

The managed CLI stack owns the runtimes, memory, gateway, targets, policy engine,
policies, and its service roles. Tool Lambdas and their execution roles are
provisioned separately. The governed Studio parent owns the VPC, database, and
Code Editor children; its bootstrap provisions the CLI stack independently.
Record exact existing resource identifiers and owners in a private receipt.
Do not claim shared Aurora, Cognito, or logging dependencies as exclusively owned
by this adopted stack, or delete the older Pellier set without proving its
consumers have moved.

## Studio IAM scope

No Studio IAM change is needed for this adoption. Fresh Studio roots continue to
use the default `pellier` project and their existing instance-role permissions.
The local existing `pellierrc` stack is adopted through the current administrator
session's tag-only change set. This is component labeling, not a migration of
shared stack ownership or a Studio-run adoption.

The Code Editor's `AgentCoreGatewayOutputGuardrailRole` statement currently scopes
`iam:PutRolePolicy` to `role/AgentCore-pellier-*`. That does not include the
adopted RC gateway's generated role, but the mismatch is not applicable to either
the fresh default path or the current administrator's tag-only adoption. Do not
widen it to `AgentCore-pellier*`.

Running the RC adoption from a future Studio instance would need a separately
reviewed grant for that exact gateway role. The current package does not promise
that deployment path.

The CLI endpoint-alias correction is separate: pass
`AGENTCORE_RUNTIME_ENDPOINT=DEFAULT` only to CLI child processes; keep the
application's runtime ARN intact. Do not broaden trace IAM permissions to
compensate for an ARN being interpreted as an endpoint alias.

## Legacy Gateway migration captures and recovery

`scripts/migrate_gateway_vocabulary.py` serves a separately authorized legacy
deployment whose Gateway and policies have direct API ownership. Supply its
deployment pins from `scripts/deploy/ownership.py`. The managed stack adoption
above continues through its existing CLI/CloudFormation owner.

The migration's `--out` argument names a capture root. It must be owned by the
current OS user with mode `0700`, or be a new directory under an existing parent.
Existing `0755`/`0777` roots and caller-controlled symlinks are refused. For a new
exercise, run from the repository root:

```sh
migration_python="$PWD/pellier/backend/.venv/bin/python"
migration_capture_root="$(mktemp -d "${TMPDIR:-/tmp}/pellier-gateway-migration.XXXXXXXX")"

# Plan only: read the pinned deployment and save a private capture.
"$migration_python" scripts/migrate_gateway_vocabulary.py \
  --out "$migration_capture_root"
```

Each plan or apply creates a fresh timestamp-and-random-ID directory. An approved
phase uses the same root, for example `--out "$migration_capture_root" --apply
--phase default-deny-quiesce`. Apply reads current live state and saves a new
capture before updating anything; it does not execute a previously saved plan.

Keep the **whole run directory**: `preflight.json`, `plan.json`, `phase-proof.json`,
and `rollback/{live.json,canonical.json,manifest.json}`. All files are mode `0600`.
For recovery, use the exact rollback directory printed by the run being restored:

```sh
migration_rollback_dir="<exact rollback directory printed by that run>"
"$migration_python" scripts/migrate_gateway_vocabulary.py \
  --rollback "$migration_rollback_dir"
```

Rollback verifies directory/file ownership and permissions, rejects symlinks and
hard-linked files, and checks every capture file against the integrity manifest.
It requires a passed captured preflight and matching deployment pins, then checks
the current caller account, client region, and live resource names/IDs before
the first update. The manifest relies on the private directory and owning OS
user; it does not protect against compromise of that user.

Legacy captures without a manifest, changed files, and incomplete captures fail
closed. Preserve that evidence for independent reconciliation. Changing file
permissions or manufacturing a manifest does not establish its provenance.
A new capture records current state and cannot reconstruct a missing earlier
state. Failed writes retain partial evidence; partial captures cannot authorize
apply or rollback.
