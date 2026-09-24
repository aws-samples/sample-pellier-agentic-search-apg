# Governed global model refresh — 2026-09-23

The governed release now selects these Amazon Bedrock global inference profiles:

| Role | Profile |
|---|---|
| Editorial specialists and legacy chat alias | `global.anthropic.claude-opus-5` |
| Router, reporting, structured extraction, and Claude Code | `global.anthropic.claude-sonnet-5` |
| Explicit fast response mode | `global.anthropic.claude-haiku-4-5-20251001-v1:0` |

Haiku already used 4.5. No GPT model is selected by this governed application.
Cohere Embed v4 (`us.cohere.embed-v4:0`) and Rerank v3.5 (`cohere.rerank-v3-5:0`)
are unchanged, as are embedding dimensions and the retrieval schema. Global Claude
profiles can route across supported AWS Regions worldwide.

Config defaults, the example environment, bootstrap, access preflight, Claude Code,
the facilitator rehearsal, and the current Observatory model catalogue move
together. Preflight still requires Sonnet and Haiku and permits a successfully
invoked Sonnet profile to serve editorial work when Opus is inaccessible. The
resolved environment also supplies the managed AgentCore runtime.

## Live verification

Verified from `us-east-1` with the supplied fresh Workshop Studio test account's
`WSOpsRole` credentials:

- All three global Claude profiles returned text through Bedrock Converse.
- All three completed a Strands streaming tool round trip: the model requested
  `inventory_count` for a synthetic SKU, received a count of 7 plus an evidence
  code, and included both in its response. This exercised the installed SDK's
  streaming and tool-result handling without changing request parameters.
- The application's `StructuredExtractor.extract` called global Sonnet 5 with
  its existing 400-token limit. For an in-stock ceramic gift under $100 with
  candles excluded, it returned parsed filters with `price_max_usd=100`,
  `in_stock_only=true`, and `exclusions=["candle"]`.
- `scripts/check_model_access.py --write-env <temporary-file>` successfully
  invoked all five required/primary models and persisted the new application
  and managed-runtime model IDs, including both embedding environment aliases.

These checks establish model access and SDK compatibility in the test account.
They do not establish EC2 instance-role access, a new CloudFormation deployment,
or completion of the participant browser and governed-action walkthrough.

## Evidence provenance and regression coverage

Recorded Observatory session fixtures retain their original model names and
spans. Only the current model catalogue and new live sessions use the new release.
The workbench regression checks render both Opus 5 and the historical Opus 4.6
identifier from emitted evidence; no recording is relabeled as a new-model run.

Release checks cover config/environment/preflight/CLI/frontend parity, editorial
fallback persistence, specialist and router defaults, and the existing backend,
frontend, shell, and Workshop Studio validation suites. Workshop Studio must pin
the published source revision and synchronized assets before its build is used.

AWS references: [Opus 5](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5.html),
[Sonnet 5](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html),
and [Haiku 4.5](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html).

Local release results: backend **3,678 passed, 90 skipped**; frontend **1,150
passed**; copy compliance, shell syntax, TypeScript type-check, ESLint, production
build, and production dependency audit passed (zero vulnerabilities). The Studio
suite passed **137 tests**, content validation passed, and all four CloudFormation
templates passed `cfn-lint`. The skipped backend tests are not live acceptance
proof. One existing frontend visibility assertion was updated to wait for its
panel's entrance animation; its visibility requirement remains intact.
