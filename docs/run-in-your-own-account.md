# Run Pellier in your own account

The workshop guide assumes an AWS event, where Workshop Studio deploys Pellier for you. This
page is the other way in: the same stack, deployed from this repository into an account you
own, with one script that creates everything and one that removes it. Nothing here changes the
event path; the templates and the bootstrap are the ones the event uses.

## 1. What you get and what it costs

One CloudFormation stack, `pellier-governed`, with three nested stacks: a VPC, an Aurora
PostgreSQL cluster, and a Code Editor host that builds Pellier, loads the catalog and runs
the labs' checks. The host sits in a private subnet behind CloudFront. Lab 3 then creates the
AgentCore Runtime, Gateway, Memory and Policy from the host, outside the stack, which is why the
teardown in section 6 has two parts.

Everything below bills by the hour or by use while it exists. Pricing is linked, not quoted,
because it changes by Region and over time.

| Resource | What the stack creates | Pricing |
|---|---|---|
| EC2 | one `c6g.2xlarge` (8 Graviton vCPUs, 16 GiB) with a 100 GiB gp3 volume | [EC2](https://aws.amazon.com/ec2/pricing/on-demand/), [EBS](https://aws.amazon.com/ebs/pricing/) |
| Aurora PostgreSQL | engine 18.3, one Serverless v2 writer scaling between 0 and 16 ACU, Advanced Database Insights, PostgreSQL logs to CloudWatch | [Aurora](https://aws.amazon.com/rds/aurora/pricing/) |
| VPC | two NAT gateways with Elastic IPs and three interface endpoints (Bedrock Runtime, Secrets Manager, STS) in two subnets | [VPC](https://aws.amazon.com/vpc/pricing/) |
| CloudFront and WAF | one distribution with a VPC origin; a web ACL in us-east-1 only | [CloudFront](https://aws.amazon.com/cloudfront/pricing/), [WAF](https://aws.amazon.com/waf/pricing/) |
| Secrets Manager, Cognito, KMS | the database secret and demo accounts, a user pool with a hosted domain, one customer-managed key for AgentCore logs | [Secrets Manager](https://aws.amazon.com/secrets-manager/pricing/), [Cognito](https://aws.amazon.com/cognito/pricing/), [KMS](https://aws.amazon.com/kms/pricing/) |
| CloudWatch and Lambda | log groups, X-Ray transaction search, the custom-resource and tool Lambdas | [CloudWatch](https://aws.amazon.com/cloudwatch/pricing/), [Lambda](https://aws.amazon.com/lambda/pricing/) |
| AgentCore (from Lab 3) | Runtime, Gateway, Memory and Policy | [AgentCore](https://aws.amazon.com/bedrock/agentcore/pricing/) |
| Bedrock model calls | Claude Opus 5.5, Claude Sonnet 5.5, Cohere Embed v4, Cohere Rerank 3.5 | [Bedrock](https://aws.amazon.com/bedrock/pricing/) |
| S3 | the private bucket holding the four templates | [S3](https://aws.amazon.com/s3/pricing/) |

The NAT gateways and the host are the fixed hourly costs; Aurora scales to zero when idle.
The newest proof run built the stack in 39 min 43 s and removed it in 31 min 7 s, as the
deploy and teardown commands printed it (`Stack ready in 39 min 43 s`, `Stack deleted in 31
min 7 s`, us-west-2, 30 October 2026); the whole run is in the newest record under
[docs/evidence](evidence/), one per Region.

## 2. Before you start

- **An AWS account where you hold administrator rights.** The deploy creates IAM roles,
  a VPC, a database and a CloudFront distribution. A role with restricted rights will fail
  partway and roll back.
- **No other Pellier deployment in that account and Region.** AgentCore keeps Cedar policy
  names unique per account and Region, across policy engines, and the host creates Pellier's
  seven policies by name, so a second deployment in the same account and Region fails at the
  first policy whatever else is renamed. The check below lists any deployment the account
  already holds; remove it first, or deploy in the other Region. The `--deployment-suffix`
  option only keeps stack, function and AgentCore resource names apart from leftovers of an
  earlier deployment whose policies are gone.
- **The account's X-Ray Transaction Search groups, if they exist.** The host sends AgentCore
  traces to the account-wide log groups `aws/spans` and `/aws/application-signals/data`,
  encrypted with the stack's key and kept for 30 days. If your account already has them with
  other settings, the host refuses to change them unless you deploy with
  `--allow-shared-trace-log-changes`; the check below says whether you need it. The teardown
  restores their previous settings, but what was written in between stays encrypted with the
  stack's key, so keep that key if you want to read it.
- **A Region: `us-east-1` or `us-west-2`.** The templates run nowhere else. In `us-west-2`
  the CloudFront web ACL is not created, because CloudFront-scope WAF exists only in
  `us-east-1`, so the storefront has no edge rate limit there.
- **Bedrock model access in that Region** for `anthropic.claude-opus-5-5`,
  `anthropic.claude-sonnet-5-5`, `cohere.embed-v4:0` and `cohere.rerank-v3-5:0`. The
  Claude models are called through the `global.` cross-Region inference profiles. In the
  Bedrock console, **Model access** lists each model; the first Anthropic request in an
  account asks for the use-case details form, and the Cohere models ask you to accept a
  subscription. Both are one-time steps per account.
- **The RDS service-linked role**, `AWSServiceRoleForRDS`. Workshop Studio creates it
  before an event; the check below reports whether your account has it, and the deploy
  creates it when it is missing.
- **Quotas** in that Region: 8 on-demand Graviton vCPUs free under *Running On-Demand
  Standard instances*, one Aurora cluster, one VPC under the default five, and two Elastic
  IPs under the default five. The check below reads the VPC and Elastic IP usage against
  the quotas, and the deploy refuses to start when the stack would exceed either, because
  CloudFormation would otherwise roll back only after the Aurora cluster has been built.
- **On your machine:** `git`, `uv` (it installs boto3 for the scripts), and AWS credentials
  for that account in the usual places (`AWS_PROFILE` or the default profile).

**Step 1.** Run the account check. It changes nothing: it names the account and Region,
lists any Pellier deployment the account already holds, reports whether the RDS
service-linked role exists, reads the two quotas and lists which of the four models the
Region offers.

```bash
uv run deploy/own-account/deploy.py check --region us-east-1
```

**Step 2.** Prove invoke access, which a listing does not. This sends one minimal request
to each model and prints a pass or fail per model.

```bash
uv run --with boto3 scripts/check_model_access.py
```

## 3. Prepare the data

Nothing to prepare: the catalog, its photographs and the embeddings ship in this repository
under `data/`, and the host builds the database from them.

## 4. Deploy

**Step 1.** Clone the repository and check out the release commit. Arriving from the
workshop guide, the link that brought you here names the commit in its path; from GitHub,
use the newest commit on `governed`. The host fetches the same commit, so it must exist on
GitHub.

```bash
git clone https://github.com/aws-samples/sample-pellier-agentic-search-apg.git && cd sample-pellier-agentic-search-apg && git checkout governed
```

**Step 2.** Deploy. The script creates the service-linked role if it is missing, creates a
private bucket named `pellier-own-account-<account>-<region>` in the Region (Block Public
Access on, SSE-S3, TLS only, tagged as this script's), uploads the four templates under
`pellier/`, waits until S3's global endpoint serves the new bucket, creates the stack with
that bucket as its two asset parameters, the checked-out commit as the source and your
`--deployment-suffix` if you need one, then prints
one line per stack event until the stack is complete, followed by `Stack ready in` and the
Outputs. Add `--dry-run` first: it still reads your account to build the plan, prints every
write it would make, and makes none.

```bash
uv run deploy/own-account/deploy.py deploy --region us-east-1
```

The stack is not complete until the host has built Pellier, loaded the catalog, provisioned
AgentCore and signalled CloudFormation; the measured time is in the evidence record. If the
stack rolls back, the script waits for the rollback to finish and prints the first failed
resource and its reason. Once the stack is complete, the script copies the host's provisioning
receipt from `/tmp` to `/var/lib/pellier/`, where the teardown in section 6 reads it; `/tmp` on
the host is memory-backed, so a reboot would otherwise lose it.

## 5. Use the workshop guide

The guide's Getting started reads the event's **Event outputs** panel. In your account, the
same four names are the stack's **Outputs** tab in the CloudFormation console, or this
command, which masks the staff password and the editor token unless you add
`--show-secrets`:

```bash
uv run deploy/own-account/deploy.py status --region us-east-1
```

`CodeEditorURL` opens Code Editor, `PellierURL` opens the store, and `OperatorUsername` and
`OperatorPassword` sign Nadia in to the Operator for Lab 4. Then follow the guide from
Getting started; every step is the same from there.

## 6. Tear down

The stack does not own everything the host created, so one command removes it all, in this
order. It first runs the repository's observability teardown on the host over SSM, which
restores the account-wide X-Ray settings and log policies from the provisioning receipt; that
receipt lives only on the host, so if the host is stopped, the receipt is gone or that step
fails, the command stops before deleting anything and says what to fix (`--force` deletes
anyway and lists what you must restore by hand). It then deletes the log deliveries, the
inline policy on the Gateway role and the `AgentCore-pellier-default` stack the AgentCore CLI
created; the two Lambda functions, their roles and their log groups; the AgentCore log groups;
and the workshop stack, which it waits for. With the two flags below it also schedules the
retained KMS key for deletion, only when the host restored the account-wide settings, and
empties and deletes the bucket, only if this script created it. It refuses a stack name it
cannot find, a deployment suffix that does not match the stack, and an AgentCore stack that
is older than the workshop stack, so a typo cannot delete another deployment's resources. Add `--dry-run` to see the plan first.

```bash
uv run deploy/own-account/deploy.py teardown --region us-east-1 --delete-bucket --schedule-kms-key-deletion 7
```

It ends with a **Left in place** list. What can remain, and how to remove it:

- **The CDK bootstrap**, stack `CDKToolkit` and bucket `cdk-hnb659fds-assets-<account>-<region>`,
  which the host created for the AgentCore CLI. The script leaves it because other CDK apps in
  the account may use it. Empty the bucket and delete the stack in the console if nothing else
  does.
- **The readiness log group** `/aws/pellier/readiness`, which every Pellier deployment in the
  Region shares. Delete it in the CloudWatch console if this was the only one.
- **Account-wide X-Ray settings**, if you passed `--force`: the trace segment destination and
  the indexing rule the provisioner changed, and the CloudWatch Logs resource policy
  `TransactionSearchXRayAccess`. In the X-Ray console, under **Settings**, set Transaction
  Search back to the values you had, and delete the policy with
  `aws logs delete-resource-policy --policy-name TransactionSearchXRayAccess`.
- **The KMS key**, if you did not pass `--schedule-kms-key-deletion` or passed `--force`: the
  script prints its ARN; schedule its deletion in the KMS console once the account-wide log
  groups no longer use it.
- **Bedrock model subscriptions** stay with the account; they bill nothing while unused.

## 7. Adapt it to your own data

The patterns are documented to be carried, not copied. Start with
[`takeaway/governed-postgres-agent/SKILL.md`](../takeaway/governed-postgres-agent/SKILL.md),
a review you can run against any agent tool that reads or writes PostgreSQL, and the
[Architecture](../README.md#architecture) and [Take it home](../README.md#take-it-home)
sections of the README, which map each Pellier component to the question it answers.
