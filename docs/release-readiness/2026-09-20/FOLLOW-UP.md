# Governed release follow-up — 2026-09-20

**Event release remains HOLD.** This follow-up distinguishes the newly repaired
source and live log protection from the unpublished Studio root. The original
review's tests, screenshots, failed attempts and historical resource receipts
remain evidence for that earlier snapshot. They are not relabeled as new runs.
The local Studio handoff records this follow-up's final published source SHA,
exact-commit CI, derived template revision and reviewed publication file list.

## Source and local template repairs

- `START_FRONTEND.sh` preserves an already active Node 24. Otherwise it loads
  NVM without activating its default, selects an installed Node 24, verifies
  the actual major version and stops before the build if selection fails.
  Previously, sourcing the installed NVM activated its Node 22 default.
- The managed provisioner inspects both account-wide trace log groups before
  changing either. Existing groups that need a key or retention change require
  `AGENTCORE_ALLOW_SHARED_TRACE_LOG_CHANGES=true`; matching existing protection
  remains a no-op. Creation races are checked again before a write. This flag
  authorizes changes only when the owner has accepted the shared-group impact
  and continuing decryption-key responsibility.
- The explicit flag survives the Stage 2 manifest, recovery environment and
  sudo boundary, defaulting to false. Governed bootstrap defers its earlier
  Transaction Search activation to the provisioner so it cannot bypass that
  ownership check. The other workshop format retains its prior behavior.
- Transaction Search indexing is read before activation, then explicitly set
  to 100 percent and verified. The private receipt captures the previous rule
  and update time. Cleanup restores only an unchanged owned setting, refusing
  a newer writer; an absent default rule fails before account-wide mutation.
- KMS ARN validation accepts the documented `mrk-` plus 32 hexadecimal digit
  identifier as well as a standard key UUID, and rejects malformed identifiers.
  Before provisioning mutations, the supplied key must match the caller's
  account, Region and partition and be an enabled, customer-managed symmetric
  encryption key. CloudWatch association establishes effective service access.
- The paired local Studio templates retain the log key on deletion and
  replacement. Reverting a log-group association changes future ingestion;
  it does not re-encrypt events already stored under that key. Key retirement
  therefore requires a separate review of every retained encrypted-log
  dependency. The new root/child parameter exposes shared trace changes as an
  explicit, default-false choice.
- The Studio editor's inline IAM document exceeded the service limit once
  ARNs resolved. CDK bootstrap permissions now live in an attached managed
  policy: maximum-stack-name checks measure 8,477/10,240 inline characters
  and 3,573/6,144 managed-policy characters. Missing scoped ECR, SSM and S3
  resource-handler reads and rollback operations were added after comparing
  the deployed CDK bootstrap template with current provider schemas. Live IAM
  Access Analyzer validation reported no errors or warnings; two existing
  redundant-resource suggestions remain in the inline policy.
- The local Studio UserData no longer attempts an obsolete Node 20 install or
  hides a failed core-package installation. Source bootstrap owns Node 24 and
  Python 3.14 installation; core-package failure now stops and signals failure.
- Model readiness now requires successful InvokeModel and Rerank calls.
  Validation errors for invalid identifiers or payloads no longer count as
  access proof. A working embedding fallback is persisted for both backend
  and MCP Lambda consumers; the editorial fallback also updates the chat and
  optional analytics model alias before readiness is recorded.
- CDK bootstrap and its recovery instruction now pin `aws-cdk@2.1126.0`,
  matching the pinned AgentCore CLI scaffold. Its version-32 bootstrap template
  is byte-identical to the newer CLI previously resolved locally. This removes
  a floating package version without claiming first-account bootstrap proof.

## Live log protection and ownership

The user authorized the current Isengard account in `us-east-1` for these live
checks. A dedicated CloudFormation-managed, rotating customer-managed key was
created for the two governed Runtime groups and the two account-wide trace
groups. Its service policy is restricted to those four encryption-context
ARNs. The key is retained on stack deletion and replacement.

All four groups were associated and independently read back with the new key
and their existing 30-day retention. The original unprotected configuration is
preserved in the private migration receipt. The older AgentCore component and
its separate Runtime log group were not retired or silently included in this
migration. Aurora, Cognito, the existing listeners and application configuration
remain shared dependencies.

Key association protects newly ingested events after AWS propagation; it does
not retroactively change encryption of older events. The owner must keep this
key enabled and accessible while any retained events require it. Exact key,
group and stack identifiers are in the local Studio handoff and private
evidence, rather than this public source repository.

## Dynamic shell evidence

The exact generated `.env` emitter and sourcing block passed a synthetic
literal-value/export check in Bash 5.2.15 on an existing Amazon Linux 2023 host.
The check used a temporary directory, removed it on exit, and made no service,
package or database changes. The same boundary passed locally in Bash 5.3.
The test values included shell metacharacters; no live credential was read.

The real local NVM boundary reproduced the older default and verified the
repaired selection of installed Node 24. NVM is a local frontend convenience;
the Studio bootstrap installs system Node 24. ShellCheck's external-source
SC1091 diagnostics are retained. These executable checks resolve the two
source-path questions without claiming full static expansion or a fresh-root
bootstrap.

## Positive return and UI follow-up

The authorized proof created one new synthetic Theo order containing one bowl,
then exercised the temporary participant candidate through real managed
Runtime API turns. The return committed, with a finalized write operation and
matching Gateway audit. Replaying that exact operation key returned the same
return identifier and left order/return counts unchanged. The earlier exhausted
order and its returns were preserved.

Eligibility in the current tool is aggregated by customer and product; the
return row has no order identifier. This proof therefore does not claim an
order-linked return implementation. The first two prompts included explicit
no-write constraints containing the word "return", which selected the support
route. The record preserves that actual routing: this is a managed API positive
return/replay proof, not a browser run or the exact canonical three-turn teaching
journey. The temporary candidate was restored and independently checked: the
original runtime fingerprint, Gateway target schemas, eight active policies
and ENFORCE mode match the saved baseline. All 25 managed physical resource
identifiers remain unchanged. New proof records remain in Aurora. Newly
ingested session evidence is visible in protected Runtime and Application
Signals groups; the spans observation is time-bounded rather than independently
session-correlated.

The UI pass preserves Pellier's existing visual direction and factual copy.
Workbench's three phase controls now form equal-width touch targets on narrow
screens, and prediction/proof guidance uses the neighboring 20px reading inset.
Hover and keyboard-focus presentation are consistent. Browser checks at 320,
390, 768 and 1440 pixels found no page overflow or page errors and verified
panel transitions, disclosure expansion and focus. These local unauthenticated
views include loading states; they are not authenticated service evidence.

## Transport and fresh-root boundary

The original prepared Studio code-editor template specified a public HTTP
CloudFront origin. The current account inventory did
not contain a deployed governed Pellier Studio distribution or root, so this
review does not describe an observed live Pellier HTTP session path. The
workshop must deploy into arbitrary ephemeral participant accounts. Requiring
a Pellier-controlled hostname, distributing a shared certificate private key,
or requiring participant DNS/ACM issuance is not an acceptable repair. The
transport repair uses CloudFront VPC origins through a stable internal ALB
to a private editor instance. It needs no participant domain or certificate.
Viewer HTTPS uses the CloudFront hostname; the private origin hops remain HTTP
and are not described as end-to-end TLS. Removing public origin exposure and
proving the private path is the workshop transport acceptance boundary.

The source nginx emitter supports an explicit private-origin mode. It retains
the secret guard on the user port, uses a separate CloudFront-supplied viewer
scheme header because ALB rewrites `X-Forwarded-Proto`, and exposes only the
application health path on a dedicated ALB-only port. HTTP/1.1 is explicit for
Code Editor WebSocket upgrades. The optional mode defaults off for existing
launches; the new Studio template enables it. Complete root, HTTPS, SSE and
WebSocket proof remains required before this repair is marked deployed.

Local template lint, handler-schema and wiring checks do not prove effective
event-role permissions, a complete root bootstrap, reset, rollback or teardown.
Those gates remain separate from the deployed observability-key stack and
existing managed-component checks. Studio asset reads and its remote helper
returned 403. Subsequent signed-in browser access reached the existing
September 13 native preview and confirmed that the workshop remains
unpublished. That older preview does not validate the current local package.
S3 uploads, Studio staging, commit, push, import and
publication remain owner operations. Human fresh-event rehearsal remains
EXCLUDED from automated work and required before event delivery.

A differently named root alone is not a disposable target in the current
account: the default managed project and Lambda names would collide with the
retained original component. The root and editor now accept an optional
validated deployment suffix; fresh participant accounts retain the empty
default. Source bootstrap and participant helpers carry that identity through
configuration, recovery and managed-resource paths. The Cognito claim function
and its role also use that suffix, preventing a second root from replacing the
original user-pool claim mapping. The isolated real-resource
rehearsal must prove this contract before lifecycle gates can pass.

The deployment target is approximately 200 separate Workshop Studio accounts,
one per participant. Every account must provision its own workshop resources
from the same pinned templates and source. Current-account real-resource proof
is required; it does not establish model entitlement, regional capacity or
organization policies in all event accounts. These remain launch preflight
requirements, rather than participant-specific code or DNS setup.

## Verification record

The companion follow-up evidence records the actual check results and their
scope. Original September 20 evidence remains unchanged; final source and
Studio publication identities are attested in the local Studio handoff.

## First isolated root attempt and Python repair

The first real root attempt created its private network and separate Aurora
database. Its editor ran with the new instance role and installed Node 24,
Python 3.14, AWS CLI v2 and nginx. The existing shared CDK toolkit upgraded from
template version 30 to 32 with all eleven physical resource identifiers
unchanged. That proves an upgrade, not first creation in an empty account.

The account's existing Systems Manager patch association then requested a
reboot during initialization. The exact patch-command receipt and guest journal
establish the requester and timing. Starting Code Editor conflicted with the
pending shutdown; CloudFormation received a failure signal. Stage 2 did not run
and no isolated managed AgentCore resources were created. Account-wide patching
was not changed.

The next boot exposed a source defect: selecting Python 3.14 through
`update-alternatives` had replaced Amazon Linux's `/usr/bin/python3`, breaking
the OS installations of cloud-init and dnf. Restoring the RPM-declared Python
3.9 symlink on this owned failed instance restored package integrity and both
tools. This diagnosis and repair check does not count as a successful bootstrap.

Source bootstrap now preserves OS Python. It installs private workshop aliases
under `/opt/pellier/bin`, explicitly selects Python 3.14 across sudo boundaries,
and uses `/usr/bin/python3.14` for the application service. Editor, participant
and recovery shells select the workshop interpreter. The Operator credential
writer runs as the participant, where its AWS dependency is installed. AWS CLI
extraction uses a separate temporary directory per attempt so an interrupted
installation can be retried without extraction prompts or shared-path cleanup.

The paired Studio initialization also needs durable reboot recovery, with
completed-stage and delivered-environment guards because Stage 2 resets
participant exercises and baseline data. The local handoff records that
template repair, its validation, and the subsequent clean launch and lifecycle
results. Neither local regression tests nor restoring the failed instance closes
the fresh-root gate.
