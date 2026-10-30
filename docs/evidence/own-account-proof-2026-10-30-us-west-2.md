# Own-account proof, 2026-10-30, us-west-2

One full run of [Run Pellier in your own account](../run-in-your-own-account.md) in an
account that is not a Workshop Studio event account. Every value below was printed by the
commands named, on the date given; nothing is rounded or recalled.

| Item | Value |
|---|---|
| Account | 619763002613, Region us-west-2, the maintainer's own account |
| Source the host fetched | `739be98f710ca5a5e81516b3238f0484340ba99a` on `governed` |
| Templates deployed | `deploy/own-account/templates/` at this commit, infrastructure revision `d867ceb58472272b` (nested stacks named through the regional S3 endpoint) |
| Deploy command | `uv run deploy/own-account/deploy.py deploy --region us-west-2 --source-revision 739be98f710ca5a5e81516b3238f0484340ba99a --allow-shared-trace-log-changes` |
| Stack name | `pellier-governed`, no deployment suffix |
| Bucket | `pellier-own-account-619763002613-us-west-2`, created by an earlier attempt the same day and reused by its tag |

## Deploy

CloudFormation timestamps for the root stack and its nested stacks:

| Stack | Started | Complete | Took |
|---|---|---|---|
| `pellier-governed` (root) | 06:47:28Z | 07:26:50Z | 39 min 22 s |
| `VpcStack` | 06:47:31Z | 06:50:08Z | 2 min 37 s |
| `DatabaseStack` | 06:50:08Z | 06:59:34Z | 9 min 26 s |
| `CodeEditorStack` | 06:59:34Z | 07:26:49Z | 27 min 15 s |

The deploy command's own line, which polls every 30 seconds: `Stack ready in 39 min 43 s`.
It then printed `provisioning receipt saved to /var/lib/pellier/managed-receipt.json on the
box` and the Outputs with `OperatorPassword` and the editor token masked.

Before the stack creation call, the command waited for the regional S3 endpoint; the global
endpoint had still been answering 307 for the same bucket 28 minutes after its creation,
which is why the templates name their nested stacks through the regional endpoint.

## On the host

Run over SSM as `participant` in `/workshop/sample-pellier-agentic-search-apg`, right after
`CREATE_COMPLETE`:

| Command | Took | Printed |
|---|---|---|
| `uv run scripts/event_readiness.py --live` | 25 s | `READY FOR LAB 1` |
| `uv run scripts/lab_run.py finish --lab 1` | 31 s | `Lab 1A check passed`, `Lab 1B check passed` |
| `uv run scripts/lab_run.py finish --lab 2` | 15 s | `Lab 2A check passed`, `Lab 2B function check passed`, `Lab 2B check passed` |
| `uv run scripts/lab_run.py finish --lab 3` | 236 s | `Lab 3A check passed`, `Lab 3B predicate check passed`, `Lab 3B check passed` |
| `uv run scripts/lab_run.py finish --lab 4` | 123 s | `Lab 4A check passed`, `Lab 4B privileges check passed`, `Lab 4B check passed`, the Task 4B proof table with `4 of 4 probes match` |

## Account-wide settings, before and after

The host's provisioner changes two account-wide CloudWatch log groups and X-Ray Transaction
Search. This account already had them from another project's run earlier the same day, which
is why the deploy needed `--allow-shared-trace-log-changes`.

| Setting | Before the deploy | While deployed | After the teardown |
|---|---|---|---|
| `aws/spans` | no KMS key, retention 30 days | stack key `7974b3d4…`, 30 days | no KMS key, retention 30 days |
| `/aws/application-signals/data` | no KMS key, no retention | stack key `7974b3d4…`, 30 days | no KMS key, no retention |
| X-Ray trace segment destination | CloudWatchLogs, ACTIVE | CloudWatchLogs, ACTIVE | CloudWatchLogs, ACTIVE |
| X-Ray indexing rule `Default` | 100 percent | 100 percent | 100 percent |
| Logs resource policy `TransactionSearchXRayAccess` | present (put by an earlier attempt) | present | present |

Read with `aws xray get-trace-segment-destination`, `aws xray get-indexing-rules`, `aws logs
describe-resource-policies` and `aws logs describe-log-groups` at 07:28Z (while deployed) and
08:35Z (after the teardown). The after column equals the before column: the host's
observability teardown restored what it had changed and left what it had found.

## Teardown

Command: `uv run deploy/own-account/deploy.py teardown --region us-west-2 --delete-bucket`,
without `--schedule-kms-key-deletion`, so the key that encrypted the shared groups' history
during the run stays readable.

The first attempt refused before deleting anything: the deploy had tightened
`/var/lib/pellier` to mode 700 when it copied the receipt there, so the receipt's owner could
not read the copy and the host's observability teardown exited 1. That is the refusal the
script is built to give; the copy command was corrected in the same session and the
directory's mode restored by hand before the second attempt.

Second attempt, started 07:59:40Z and returned 08:34:39Z: the host's observability teardown
reported `"status": "restored"` eight times, then the script deleted the AgentCore CDK stack
`AgentCore-pellier-default` (about 4 minutes), the two Lambda functions and their roles and
log groups, the AgentCore log groups, and the workshop stack, printing `Stack deleted in 31
min 7 s` (the Code Editor stack about 12 minutes, the database stack about 13, the VPC stack
the rest), then `delete 4 object versions` and `delete bucket
pellier-own-account-619763002613-us-west-2`.

Its `Left in place` list, verbatim:

- the retained KMS key `arn:aws:kms:us-west-2:619763002613:key/7974b3d4-145c-449d-a65f-dcc9ff08d2d9` stays; rerun with `--schedule-kms-key-deletion 7`, or schedule it in the console
- log group `/aws/pellier/readiness` stays: every Pellier deployment in this Region shares it
- the CDKToolkit stack and its `cdk-hnb659fds-*` bucket stay: other CDK apps in the account may use them

Checked at 08:35Z with `list-stacks`, `list-functions`, `list-policy-engines`,
`list-agent-runtimes`, `describe-log-groups` and `list-buckets`: no stack, function, policy
engine, runtime, runtime log group or `pellier-own-account` bucket named for Pellier remained
in us-west-2. The key stays enabled on purpose: the two shared groups' events from the run's
hour are encrypted with it. The `TransactionSearchXRayAccess` resource policy predates this
run's receipt and is for the account owner to keep or remove.
