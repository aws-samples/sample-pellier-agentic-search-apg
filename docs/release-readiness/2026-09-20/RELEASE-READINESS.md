# Governed DAT416 release readiness — 2026-09-20

**Verdict: HOLD for an event release.** Source repairs and the local Studio
package are prepared for publication. Successful local and managed-service
checks do not establish a working fresh Studio root stack. Origin TLS, remote
asset access and an authorized disposable
root-stack lifecycle target remain unresolved.

The [follow-up](FOLLOW-UP.md) supersedes the original log-key and dynamic-shell
blockers and records subsequent source, template and UI repairs. Original test
counts and captured journeys below remain the earlier review snapshot.

The companion [acceptance matrix](ACCEPTANCE-MATRIX.md), [check ledger](CHECKS.jsonl)
and evidence directory preserve the checks and their limits. Failed attempts
are retained. Only the human-led fresh-event rehearsal is EXCLUDED. Studio
uploads, Git operations and publication are PENDING USER ACTION.

## Scope, identity and ownership

The reviewed source is
`sample-pellier-agentic-search-apg/.worktrees/governed-product-pass`, branch
`governed`, remote `origin` at
`https://github.com/aws-samples/sample-pellier-agentic-search-apg.git`.
The initial source was clean at
`d11ad20e2382947853e403196a420aa66a346713`.
The separate Builders checkout on `main`, initially
`2860c33b6657d28ee225e2a6d4a019dfbe807013`, and its four untracked screenshots
were preserved.

The paired Studio checkout is
`build-governed-agentic-ai-search-with-aurora-rds-bedrock-agentcore`,
branch `mainline`, base `ce9fad096bb41f1ed6f431b0e560aa305e7be667`.
Its existing content, media, template and authoring-tool changes were inventoried
before this review and retained. Its initial source pin was
`36013558…` (full initial pin retained in the local Studio handoff).
This is the governed 100-minute workshop, not the shorter Builders track.

This report belongs to the source commit containing it. The exact final full
published SHA, independent `git ls-remote` result, CI run, all final Studio pins,
derived infrastructure revision, asset digests and explicit manual file list are
recorded in the local Studio
`docs/release-readiness/2026-09-20/RELEASE-HANDOFF.md` and
`source-publication.json`. Keeping that post-commit attestation outside the
source commit avoids a self-referential SHA and an immediately stale Studio pin.
The source publication process does not publish the separate Studio repository.

The account and exact resource identifiers are in that local handoff and the
private review evidence, not this public aws-samples source. Live checks used
the established workshop account in `us-east-1`; the shell's default region was
different and was explicitly overridden. The application used Aurora through
the existing SSM tunnel with certificate verification. Existing listeners on
8003, 5173 and 15432 and the unrelated database listener were preserved.
The review used its own API/static-build listener on 18165 and a local guide
preview on 18166.

Project `CLAUDE.md`, module instructions, `VOICE.md`, product/design contracts,
Studio authoring guidance and relevant verification, publication, design-taste,
Impeccable and CloudFormation skills were read. This was authorized maintainer
work, not a participant exercise. The three referenced global steering files
were absent. Runtime `skills/` files were treated as application prompt data.

## Governed stack adoption

The Studio root is `static/pellier-governed.yml`; its children are the VPC,
database and code-editor templates. The separate AgentCore CLI stack is a
reusable managed component, not another Studio root.

That existing component was adopted in place using a reviewed tag-only
CloudFormation change set:

| Label | Value |
|---|---|
| Name | `pellier-governed-managed` |
| Project | `pellier` |
| PellierVariant | `governed` |
| PellierComponent | `agentcore` |

CloudFormation reached UPDATE_COMPLETE. All 25 physical resource identifiers
and the deployed template were unchanged; existing CLI identity tags were
preserved. The source renderer and active generated project preserve these
labels for subsequent deployments.

The physical CLI stack/project name remains its existing name. A rename is not
a tag update, and the inspected stack contains policy resources that prevent a
simple whole-stack refactor. The older Pellier component was retained because
the saved application configuration still references it and it shares Aurora
and Cognito with the reviewed component. It was not proven redundant. No
shared database, identity pool, older runtime or unrelated stack was deleted.

## Findings and repairs

| Severity | Finding | Repair and evidence |
|---|---|---|
| High | Prepared Studio template forwards session/editor traffic over an HTTP origin connection | **OPEN:** the prepared CloudFront-to-EC2 hop remains HTTP; no deployed governed Studio root was found. Prefix-list filtering and an origin header do not provide encryption. A workshop-specific domain/certificate dependency is unsuitable for arbitrary ephemeral participant accounts. See the follow-up transport design boundary. |
| Medium | Model-generated SQL could balance out of a query wrapper and retain a second statement | Added a bounded, quote/comment-aware single-statement guard; forced prepared protocol for both EXPLAIN and execution; reject configurations that disable preparation and unsafe SQL-in-string/GUC helpers. Preserve read-only transactions, principal/RLS, timeouts, plan checks and row limits. 75 real Aurora adversarial/RLS cases passed. This is not a claim of a general-purpose SQL sandbox. |
| Medium | Authentication verifier outages could be treated as invalid identity | Preserve 503 unavailability, existing identity/cookies/preferences and bounded refresh behavior; coalesce frontend refreshes and guard identity races. Cached preferences now belong to one verified identity; a subject change clears them before fetching, and a late save response cannot populate a new session. Both privacy regressions failed before repair and pass afterward. Password sign-in records only the failure class and distinguishes verifier unavailability from an invalid upstream result. No credentials or JWT claims are logged. |
| Medium | A live managed tool's target-qualified name exceeded Bedrock's 64-character tool-name limit | Give the model validated, unique logical names through the public MCP adapter API, while retaining the original wire name/client/timeout for invocation. A real managed deployment and the edited Lab 3 path passed after repair. |
| Medium | Policy readers assumed an older AgentCore SDK response shape | Read the current `definition.policy.statement` union, retain archived Cedar compatibility, fetch complete policy details and fail closed on broken pagination. Governance UI and migration logic share the corrected contract. |
| Medium | Deployment receipts, rollback captures and trace downloads lacked adequate local trust boundaries | Exclusive private receipt writes; descriptor-based receipt reads; private capture directories/files and integrity manifests; captured account/region/resource ownership checks before cleanup/rollback; randomized private trace output directories with cleanup. Focused negative cases cover symlinks, hard links, permissions, tampering and wrong ownership. |
| Medium | Failed database observations could become a successful absence proof | Require successful SQL status and exact nonnegative count output. Unavailable evidence stops proof generation and retains mode restoration. Authentication/transport failures cannot substitute for a Cedar decision. |
| Medium | Hosted E2E could accept unsafe origins or manage shared fixed identities | Validate the exact protected HTTPS origin before credentials are used. Dedicated temporary identities have private ownership receipts and fail-closed cleanup; existing users/passwords are preserved. Browser sign-in uses the real form and scoped cookies. Six live identity lifecycle checks passed. |
| Medium | Bootstrap/runtime readiness and environment handoffs could report a started but unusable system | Require functioning database, authentication, managed components and observability; distinguish app Runtime ARN from the CLI endpoint alias; retain bounded failure diagnostics. Studio now uses an EC2 CreationPolicy signal after health gates and re-signals a replaced editor on infrastructure revision changes. |
| Medium | Existing observability evidence could imply KMS protection without observed protection | Receipts distinguish requested and observed keys and require the actual log-group state. Governed provisioning fails closed without required key/retention configuration. The follow-up associated and read back a dedicated retained customer-managed key on all four governed Runtime/trace groups. Fresh-root behavior is unexecuted. |
| Medium | Node 20 was beyond its published support period | Bootstrap, health gates and all three workflows now require Node 24 LTS. An isolated official Node 24 binary was checksum-verified; frontend gates and generated AgentCore CDK build passed with it. Fresh AL2023 package installation remains part of the blocked root bootstrap. |
| Low | A failed backend-directory change could launch from the wrong directory | Stop immediately on failed `cd`; successful launch and optional config behavior have focused tests. |
| Low | Trusted-role and principal-seeding SQL interpolated values | Use database `current_user` and Psycopg literal composition for the complete parameter set, including quote/backslash/NUL cases. |
| Low | Legacy retrieval reference omitted the category bind argument | Correct the retained reference's ordered parameter vector and exercise category/no-category behavior without changing the governed starter. |
| Low | UI could imply evidence or availability that had not been established | Separate denied, unavailable, empty, loading and completed states; suppress stale/unproved boundary outcomes; use recorded return evidence instead of fixed Jessica assumptions; keep fixture examples explicitly recorded. |
| Low | Narrow-screen focus and status presentation had accessibility gaps | Correct sticky scroll clearance, names/landmarks/heading semantics, dialog/keyboard handling, trace playback group semantics, and pending-status contrast using existing design tokens. |

The earlier 19:55 authenticated run had one password-sign-in 502; it was not
relabelled as a pass or attributed to throttling. Sixteen new Cognito token
validations did not reproduce it. Sanitized verification diagnostics and
unavailable-to-recovered regression cases were added; the subsequent real
13-check browser run passed. The original failure's specific provider/verifier
cause remains unestablished. Repeat sign-in under the final hosted environment
and retain the new exception-class diagnostic if it recurs.

## Code and security review boundary

The repository inventory covered frontend, backend, routes, agents, tools,
SQL/migrations, runtime skills, scripts, solutions, infrastructure/configuration
and CI. At the expanded security snapshot it contained 1,007 code files and
399 first-party Python files, including tests/reference files. This is coverage
of the repository inventory, not a claim that every line received an identical
manual review. Manual review followed the required participant flows and their
authorization, write, recovery and deployment boundaries.

The expanded Bandit snapshot and reviewed deltas dispositioned all original
75 MEDIUM and 85 LOW findings. No HIGH scanner finding was reported.
Assertions, controlled subprocess calls, synthetic credentials and SQL
construction were inspected in context rather than suppressed to obtain a
zero count. One intentionally indented solution fragment cannot parse
standalone; its unchanged body also passed a wrapped scan. The original parser
error remains recorded.

The final scan covered 402 Python files: 7,993 LOW and 92 MEDIUM flags, zero
HIGH flags and zero untriaged findings. The increase is dominated by test
assertions and synthetic fixtures. Two source interpolation flags and the
shared trace-output flag disappeared after their root-cause repairs. The
final reconciliation checked the reported source contexts against the actual
files; it did not turn retained trust assumptions into universal guarantees.

Current-tree secret scans found no confirmed tracked credential. Two candidates
are in an ignored private local environment file; their validity was not tested
and their values were not copied. An older committed password exposure remains
in Git history; read-only checks found the old secret absent and the current
workshop password different. History was not rewritten. This does not establish
the revocation status of every possible historical credential.

Shell syntax passed. ShellCheck's full diagnostic set is retained, including
indirect-trap/literal-expansion cases and two environment-source analysis gaps.
Those gaps are partial static evidence, not a clean-shell or fresh-event pass.
Dependency audits reported no known vulnerabilities in the installed pinned
backend and production frontend sets. Two upstream deprecation warnings remain:
Starlette's TestClient/httpx transition and AgentCore's Pydantic class Config.
No test or material warning was weakened or suppressed.

| Final check | Result |
|---|---|
| Full backend suite | 3,432 passed, 90 environment-dependent skips, two upstream deprecation warnings; separate skip evidence below |
| Frontend | 1,128 passed; independent type-check, lint, build and dependency audit passed on Node 24 |
| Public browser | 44 passed; 13 credential-dependent checks skipped in this invocation |
| Authenticated browser | All 13 corresponding real-Cognito/managed-data checks passed in the dedicated invocation |
| Aurora adversarial SQL/RLS | 75 passed against the established Aurora environment |
| Immutable/held-out data | Two live checks passed |
| Isolated transaction/commerce SQL | 55 passed, including the 13 environment-dependent SQL cases; disposable test fixture, not application infrastructure |
| Studio package tests | 74 passed |
| CloudFormation | Four templates passed lint |
| Final local delivery identity | HTML, all JavaScript and CSS: 110 HTTP responses matched build bytes |

## Participant journeys and observable results

| Journey | Executed evidence | Limit |
|---|---|---|
| Startup and sign-in | Isolated final API health reports functioning Aurora/Bedrock/tools; real Cognito form, cookies, refresh, anonymous and shopper/staff boundaries exercised | Existing workshop services, not a new root-stack bootstrap. Temporary users were removed; existing passwords were unchanged. |
| Lab 1: PostgreSQL grounding | Live known/unknown inventory queries distinguish an absent product from a known product with zero warehouse units | Starter markers remain incomplete in source; the exercise is validated through controlled candidate edits. |
| Lab 2: measured retrieval | Same-query baseline/candidate comparison; 15 RRF candidates and constrained reranking; one product recovered after expanding the candidate pool; eight receipt assertions | Real Aurora/embedding/rerank calls. Result counts belong to the captured catalog, not a promised universal ranking. |
| Lab 3: managed path | Both participant edits were made in an isolated candidate, deployed, fingerprint-checked and exercised through three real browser turns; own ticket-history read succeeded and a cross-customer read was denied; baseline and eight policies restored | Candidate fingerprint differs intentionally from the starter. One second-turn tool error recovered through a successful search. The third turn attempted a return but Aurora refused because no eligible quantity remained. No new Theo return was committed. |
| Lab 4: governance proof | Five live outcomes, including permitted execution, Cedar refusal/nonexecution, database defense, replay and output suppression; actual audit/data observations; policies restored to ENFORCE | The captured run made two one-cent credits and one eligible Jessica return. It was not replayed after quantity was consumed. Later changes did not alter those Lambda/policy bytes. |
| Operator investigation and client preview | Real staff form login, current client book, read-only investigation with persisted numbered steps, canonical preview handoff and current return evidence | The separate managed Operator smoke uses an explicit fixture. That fixture is not the real browser/Aurora investigation proof. |
| Memory and observability | New learning run; recall in a new session with zero prior history, extracted facts/preferences/summary and real product tools; principal-scoped checks; 32 real managed trace spans | Optional episodic extraction was absent. Trace content was redacted; no hidden model reasoning or full tool payload visibility is claimed. |
| Reset and cleanup | Baseline managed component/policies restored after candidate checks; owned temporary Cognito identities deleted; receipt/rollback/cleanup failure cases tested | Full shared-data reset, root rollback and stack teardown were not executed without a disposable authorized root target. |

The final managed starter package matches fingerprint `b6e836b82047…`; the
shopper and Operator Runtime versions are 19 and 11. Four deployed Lambda
packages matched all 20 compared first-party source files. The exact digests
are in [artifact evidence](evidence/artifacts.json), with detailed resource
identity in the private/local Studio handoff.

The final API and frontend were tested locally against these real managed
services. The existing user-owned application deployment was not replaced.
The final Studio EC2/root templates have not been deployed. A managed package
match is bounded content evidence, not a cryptographic service attestation and
not proof of the complete hosted source commit.

## UI, design and content

The existing warm editorial Pellier direction, typography and product vocabulary
were retained. Browser review covered 39 route/viewport probes plus loading,
empty, denied, unavailable, recovery and dialog states, keyboard focus,
horizontal table scrolling, 320-pixel layout, reduced motion and 200% text scale.
Failure-state probes explicitly intercept responses and are not live-service
success evidence. Six current authenticated desktop/laptop/mobile captures use
real Aurora records; screenshots and browser evidence are retained.

Automated accessibility checks found no remaining reported violations in the
final captures. Axe still marks text over images, gradients and pseudo-elements
for manual contrast assessment. Those surfaces were inspected visually; this
is not a complete assistive-technology certification. Physical projector
legibility and screen-reader operation were not executed. Laptop/presenter
viewport inspection is separate from those physical checks.

All ten guide pages, required and optional branches, commands, SQL, outputs,
working directories, identity transitions, recovery and cleanup were read and
compared with the source. Eight starter edits and solution parity remain
enforced. The guides now explain the CLI endpoint environment handoff,
intentional nonzero doctor checks, five Lab 4 outcomes and the difference
between a completed conversation and a committed return.

The 100-minute design remains 5/20/25/25/20/5 minutes for introduction,
Labs 1–4 and close. Deployment waits, participant edits and recovery share
these budgets. This is a reviewed pacing target, not a measured human run.
The separate extended introduction deck has its own presentation budget.

A local Markdown approximation rendered all ten pages at 1280 and 390 pixels:
20 successful page/viewport checks, no broken images or page overflow.
This renderer is not Workshop Studio. Native Studio tabs/callouts/navigation,
the published package and embedded delivery behavior remain unverified.
All 20 referenced deck capture hashes matched the 9-slide architecture and
11-slide introduction decks. Existing diagrams/images/deck captures retain
their historical provenance. No MP4 exists; the recording plan names a narrated
fallback. No old media was presented as fresh execution evidence.

## Infrastructure, IAM and delivery

All four Studio templates passed `cfn-lint` and the package's 74 tests.
The root/nested ordering, regional constraints, mappings, immutable source pin,
derived infrastructure revision, private encrypted Aurora, forced database TLS,
IMDSv2, encrypted editor storage, Cognito and log-key resources were inspected.
CreationPolicy failure/retry/signaling and the revision-driven editor replacement
have static/unit coverage. A started process alone cannot signal readiness.

Read-only regional checks established the configured Aurora engine/serverless
range, required Bedrock models, prefix list and available quota metadata.
This does not prove fresh-account capacity, model entitlement, event SCPs or
the effective workshop participant role.

Deployment, bootstrap, participant inspection, Runtime, Gateway/Lambda and
cleanup permissions were traced against the calls. The CLI deployment identity
retains broad regional AgentCore permissions appropriate to this trusted
development/workshop automation; it is not represented as production least
privilege. IAM/PassRole scoping and resource-creation wildcards are documented
in the templates. Static policy analysis is not a live event-role simulation.

Relevant current primary references were checked through available AWS
documentation tools: Bedrock ToolSpecification name constraints, AgentCore
Runtime security guidance, CloudFront HTTPS-origin requirements, CloudFormation
CreationPolicy/SignalResource and stack-refactoring limits, and CloudWatch Logs
KMS integration. Official Node release metadata and archive checksums were also
read. An attempted large IAM service-authorization table read was incomplete;
that attempt is not counted as full-table verification.

Cleanup must account for the independent AgentCore CLI stack, external tool
Lambdas/roles, retained logs and any captured evidence. The locally repaired template retains its customer-managed log key on root
removal or replacement. Dependent encrypted logs must be reviewed before a
separate manual key retirement; retention and ongoing key costs are explicit. The root's
database policy deletes workshop data without a final snapshot. Two NAT
gateways, Aurora, the editor, model calls and retained managed resources incur
cost while present. No destructive cleanup was performed on shared resources.

## Open gates and smallest next actions

| Gate | State | Smallest action |
|---|---|---|
| CloudFront-to-editor transport | FAIL | Resolve the origin transport architecture without a shared private key or participant DNS/certificate prerequisite. Verify the chosen workshop design live; do not label private HTTP as origin TLS. |
| Automated fresh root lifecycle | BLOCKED | Identify an existing disposable workshop stack/account explicitly authorized for bootstrap, partial failure, rollback, reset and teardown. The reviewed component's shared Aurora/Cognito do not qualify. |
| Existing log-group customer-managed keys | PASS | Follow-up user-authorized migration created a retained rotating key and independently read back all four governed Runtime/trace associations with 30-day retention. Keep the key for retained encrypted history; older logs are not re-encrypted. |
| Studio S3 and Git/native package access | BLOCKED | Restore authorized asset/package read access. Three nested-template HeadObject calls and the Studio remote read returned 403. Validate remote bytes, content types and published rendering after the owner uploads/imports. |
| Final hosted source and assets | BLOCKED | Complete the owner's manual publication and deploy the verified source/templates into the authorized environment. Compare runtime and static artifact identities, clear stale sessions/caches, then run authenticated automated journeys. |
| Positive Theo return in this existing account | BLOCKED | Supply an eligible authorized test order/case. The current bowl has no unreturned quantity; retain the observed refusal and do not reset shared records to manufacture success. |
| Native Studio/physical presentation checks | BLOCKED | Inspect the actual imported Studio package and available presentation/screen-reader environment. The local approximation does not establish native behavior. |

## Release order and owner boundary

Source changes, including this report, are staged as an explicit reviewed file
set, committed and pushed to `origin/governed` without force. Local HEAD,
tracking ref and independent remote SHA must agree. Exact-commit CI is recorded
separately from local checks.

Only after source remote verification is the local Studio package repinned with
`python3 scripts/set_source_revision.py <full-published-SHA>`. This updates all
source defaults and derives the infrastructure revision from the template set.
The release validator must run against the exact clean source checkout and the
updated local package. Subsequent source changes require another verified push
and another complete re-pin.

The local Studio handoff contains the exact three `aws s3 cp` commands, working
directory, reviewed source SHA, checksums and explicit file list for the owner's
`git add --pathspec-from-file`, diff review, commit, push and established Studio
import. No broad staging or destructive sync is needed. This review performs
none of those Studio publication operations.

After publication, repeat remote template byte/content-type checks, native
Studio navigation/download/media review, source/infra identity checks on the
hosted editor, fresh sign-in, the automated four-lab path and authorized reset/
cleanup. Resolve the open transport and environment gates before event launch.

## Human fresh-event rehearsal — EXCLUDED, still required

1. Launch a genuinely fresh Studio event/account, confirm infrastructure and
   bootstrap complete, and sign in from a clean browser/session.
2. Run the full timed 100-minute participant path, including all eight starter
   edits and deployment waits; record where participants require assistance.
3. Verify inventory grounding, measured retrieval differences, the changed
   managed fingerprint, actual ticket/return outcomes, and the five governance
   outcomes with audit/nonexecution evidence.
4. Exercise an expired session, a service failure, a participant mistake and
   each documented recovery/fallback without hidden facilitator setup.
5. Check projector readability, keyboard/screen-reader use, native Studio
   navigation and optional branches, then perform the documented reset and
   cleanup and account for resources/data/logs that remain.

Automated checks and the existing deployment were not this rehearsal.
