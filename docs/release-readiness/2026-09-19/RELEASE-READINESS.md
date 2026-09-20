# Governed release readiness — 2026-09-19

Status: source repairs and available live checks completed; release remains blocked on the separately identified Studio and fresh infrastructure gates. This is the source evidence snapshot immediately before publication. The final source SHA, remote verification, local Studio pin and owner commands are recorded in the sibling Studio package at `docs/release-readiness/2026-09-19/RELEASE-HANDOFF.md`. See the acceptance matrix for bounded results. This report does not certify Workshop Studio publication or a human fresh-account rehearsal.

## Scope and release ownership

- Source: `/Users/shayons/Desktop/Workshops/sample-pellier-agentic-search-apg/.worktrees/governed-product-pass`, branch `governed`, remote `https://github.com/aws-samples/sample-pellier-agentic-search-apg.git`. Initial local and advertised remote commit: `95b08e6b3d681980e2b258ef7539feefa5135a1b`.
- Builders is the separate `main` track, initially `2860c33b6657d28ee225e2a6d4a019dfbe807013`; it was not the review or release target. No new source branch was created. There is no RC source branch to merge. Future source work goes directly to `origin/governed`.
- Studio: `/Users/shayons/Desktop/Workshops/build-governed-agentic-ai-search-with-aurora-rds-bedrock-agentcore`, branch `mainline`, initial commit `ce9fad096bb41f1ed6f431b0e560aa305e7be667`. Its `workshopstudio://` remote is the separate governed workshop package. Existing source and Studio edits were inventoried and preserved; unrelated worktrees, screenshots and processes were left alone.
- AWS: account `619763002613`, workshop Region `us-east-1`; the CLI default Region was `us-west-2`, so deployment checks select the workshop Region explicitly. The existing `AgentCore-pellierrc-default` stack is the test deployment being repaired. `pellierrc` is an AWS naming suffix, not a Git release branch. Its Aurora and Cognito dependencies are shared with the older `pellier` deployment; no destructive reset of shared business data is authorized by this review.
- Read project voice/design/product contracts, applicable maintainer instructions, and the governed verification workflow. The supplied broad maintainer task supersedes the root's participant-only exercise limits. Referenced global steering files were not present at their configured paths. Frontend design-taste and Impeccable were available and applied.
- Only source Git staging, commit and push are agent-owned. All Studio S3 uploads/sync, Git staging/commit/push and publication/import remain owner operations. No Studio write/publication operation was performed.

## Repairs and material findings

| Severity | Finding | Repair / evidence |
|---|---|---|
| High | Managed session normalization could alias distinct user/session strings | Hash the complete verified-principal/session tuple; preserve a separate generated session for absent IDs. Regression cases include punctuation, Unicode and different principals. |
| High | Forensic seed could attach to a normal order or race another seeder | Exact INSERT RETURNING relationship, advisory transaction lock and idempotent marker check. Clear refuses immutable evidence. Isolated real PostgreSQL proof races two seeders, repeats seeding, and preserves ordinary business state. |
| High | Predictable generated shopper and Operator passwords | Independent random passwords; password-setting failures propagate. Staff credential is stored in the same managed test secret used by readiness and Lab 4, while the participant credential file remains mode 0600. Existing live users were not reset. |
| High | Required output policy did not deploy with the actual service grammar/schema | Record-field output path, declared tool output schema, aggregate sensitive-information score, and general PolicyStatement response support. Live syntax/schema probes preserve failed attempts and require ACTIVE; benign and sensitive-output controls passed live, including suppression after commit and same-key replay. |
| Medium | Trace link used an application session instead of the actual Runtime header | Persist `runtimeSessionId` in the receipt and build CloudWatch links from that value. Update Lab 3's SQL/trace instructions. |
| Medium | Lambda retrieval and product image lookup handled SQL LIKE metacharacters inconsistently | Escape literal search fragments and align archived-product filtering across local and managed tools. |
| Medium | Runtime/solution twins and recovery schemas had drifted | Align staff-only tool isolation, trace propagation and schemas without completing the participant's marked tasks. Guided-edit and marker tests exercise starter, solution and mistakes. |
| Medium | Bootstrap could announce an installed but unusable pg_stat_statements extension | Query the installed extension during readiness. Preserve required failure propagation, environment loading and the run.env rail switch. |
| Medium | XML parser accepted entity expansion in Memory evidence | Use defusedxml, preserve untrusted raw content as text, and add adversarial XML tests. |
| Medium | Known Python dependency vulnerabilities | Update and lock aiohttp/cryptography; audit both backend and managed-runtime dependency sets. |
| Medium | Navigation could leave a shopper stream writing stale evidence after unmount | Abort the fetch and suppress post-unmount state/evidence writes; retain timeout cancellation. |
| Medium | UI hid failures or showed contradictory readiness | Add route recovery boundary, distinct missing/unavailable evidence, error states and truthful Operator configuration state. Keep shopper errors free of internal exception detail. |
| Medium | Workbench text contrast and definition-list markup failed accessibility checks | Preserve the approved visual direction while correcting ink tokens and dt/dd semantics; verify reduced motion and narrow-layout controls. |
| Medium | Proof helper could replace an explicitly selected deployment with local dotenv values | Explicit environment wins over dotenv defaults. Test that a local file cannot redirect a proof to an older Gateway. |
| Low | A vocabulary test traversed transient third-party Runtime staging | Exclude generated dependency staging and virtual environments while retaining all first-party source/content checks. |

## Evidence boundaries

`CHECKS.jsonl` retains command, working directory, UTC timestamp, exit code, duration and the original local log path, including failed and superseded attempts. Raw local logs are under `/tmp/pellier-review-20260919`; they are not credentials or deployable assets. The dated source report and selected screenshots are reviewed artifacts. A passing targeted rerun supersedes only the affected failure, never an unrelated missing check.

The production frontend bundle was served by a separately started current-source backend at `http://localhost:18163`. Earlier checks at port 8003 used an already-running backend and are baseline evidence only. The original backend/Vite servers and SSM tunnel were preserved. Final managed checks use `http://localhost:18164`, a freshly started current-source backend with real Cognito/Aurora and the repaired managed Runtime/Gateway. Port 18163 predates the last Observatory identity-panel SQL repair; those checks cover unaffected public and in-process paths. The final identity panel and all five outcomes were retested on 18164. Neither local endpoint is a published Workshop Studio host.

Public Playwright checks include navigation, responsive routes, anonymous/denied access, scenario selection, reset and recovery, dialogs and reduced motion. Some storytelling/reference panels intentionally display recorded fixtures; their browser tests are presentation checks. Separate authenticated tests use real Cognito, stream real backend requests and reconcile persisted Aurora receipts. Neither type is a human fresh-account rehearsal.

The current axe scan covers Storefront, sign-in, Observatory collection, Workbench, Govern verification and signed-out Operator at 1920, 1280 and 390 pixels. No WCAG A/AA violations were reported on those 18 surfaces. Axe's incomplete checks remain manual-review items; automated accessibility scans do not establish universal accessibility. Current screenshots are in `screenshots/`, with responsive navigation also inspected in the browser.

## Security review boundaries

Authentication, customer binding, staff group authorization, strict principal-scoped SQL and RLS were traced across UI/API/service/database boundaries. Staff-only tools are excluded from shopper specialists; policy admission, business refusal, committed effects and output suppression remain distinct. Managed Operator is IAM-authenticated and read-only; approval/execution is a separate backend path. Prompt and tool data are bounded, retrieved Memory is untrusted context, and a missing/stale managed build must fail visibly.

Bandit reports ten remaining medium-severity candidates and no high-severity findings. They were retained rather than suppressed: intentional server interface binding (2); a constructed HTTPS AgentCore URL (1); controlled SQL fragments with bound values/placeholder lists (3); local diagnostic/rollback receipt paths (4). These are bounded static-review judgments, not proof of general exploit resistance. Trace diagnostics and deployment receipts remain local workshop operational artifacts; use the established per-participant host and file permissions. Upstream Starlette/Node deprecation warnings remain visible; no tests or material warnings were disabled to make the result green.

## Content, assets and media

The participant path is four labs/eight marked tasks in 100 minutes: introduction, inventory grounding, retrieval measurement, managed deployment/Memory, Cedar/SQL proof, summary/cleanup, plus background, coaching and deeper-reference branches. Required tasks remain visible; starter code does not contain the finished exercise. Guides distinguish tool results from current SQL, scenario selection from identity, fixture examples from evidence, policy admission from commit, and suppressed output from rollback.

Lab 3 now uses the canonical rail-switch helper and reads the actual Runtime session identifier from the receipt. The root template's duration and Observatory wording match the required path. Local content tests execute guided snippets and counterexamples; they do not replace participant timing or AWS execution. The 100-minute budget and recovery allocations are unmeasured targets until the excluded human rehearsal.

Local referenced assets, paths and case were checked. Both editable PowerPoint packages open as valid ZIP/XML documents with matching slide/notes counts (architecture 6/6, introduction 10/10). All 22 files represented in capture checksum manifests match their recorded hashes. The September 18 images remain historical illustrations with their original provenance; they were not relabelled as current execution. The 75-second introduction demo is planned, not recorded or embedded.

Studio's configured remote returned HTTP 403 on read-only verification. Its published renderer and actual S3 asset delivery/checksums could not be inspected with available credentials. No native local Workshop Studio renderer is installed. Static package validation and app rendering are separate evidence and do not count as Studio rendering. The owner must publish the prepared files and then verify actual rendered pages, downloads, nested-template bytes/content types and source/infra pins.


## Final measured checks and late live repairs

| Check | Result | Evidence |
|---|---|---|
| Backend suite | 3,039 passed, 64 skipped, 2 upstream warnings | `backend-frozen-final`, exit 0. The skipped cases require explicit database environments. |
| Environment-dependent database cases | 49 Aurora SQL/RLS cases; 55 isolated receipt/commerce cases including 13 skipped cases; 2 Aurora immutability/held-out cases passed | `live-database`, `isolated-receipt-commerce-sql`, `live-immutability-heldout`. Together account for the 64 default-suite skips without treating skips as passes. |
| Frontend | 157 files / 1,113 tests passed; independent tsc, ESLint, production build and npm audit passed | `frontend-release-final`; last label-only change passed 5 affected tests plus tsc/lint/build in `boundary-ui-final`. |
| Public UI | 25 passed, 3 authentication-gated cases skipped | `public-browser-final`; authenticated cases are covered separately, not inferred from the skips. |
| Managed shopper UI | 3 passed, 1 Operator-credential case skipped | `shopper-managed-browser-complete`; real Cognito login, streamed tool completion, persisted Aurora receipt and session replay. |
| Managed staff UI | 2 passed | `operator-boundary-render-final`; Jessica investigation, retained numbered graph steps, exact five-boundary evidence and identity-panel HTTP 200. An ephemeral staff identity was created and deleted; no existing password changed. |
| Accessibility/design | 18 public surfaces across 1920/1280/390, zero axe violations; responsive, focus, recovery and reduced-motion checks passed | `final-browser-static`, `public-browser-final`, current screenshots. Projector width was inspected on screen; no physical projector or assistive-technology certification is claimed. |
| Lab 1 live contract | Unknown is not_found without a count; sold-out product is success with zero units | `labs12-live`, `evidence/lab1-live.json`; verbatim guide edit compiled in a temporary process against Aurora. |
| Lab 2 live contract | All 8 before/after assertions true; real reranking; 15 fusion rows agree with recorded scores | `labs12-live`, `evidence/lab2-live.json`; real Bedrock embedding/extraction, Cohere rerank, persisted comparison receipts and authored psql worksheet. Starter files unchanged. |
| Lab 3 managed/Memory | Current build, distinct new session, no prior history, six extracted context records, 10 current products; anonymous 401, other shopper 403, owner 200 | `managed-smoke`, `memory-managed-recall`, `memory-owner-scope`. The separate Operator deployment smoke is explicitly fixture-based; the staff UI check is real case execution. |
| Lab 4 live | Authentication rejection, policy deny, transaction refusal, one commit/replay, benign output, suppressed output/replay, and positive/negative RLS passed | `lab4-five-boundaries-final`; exact run `boundaries-3f948b9abbc94808a03d6aec4991c5f7`, identity run `61dbaec454`. |
| Lab 4 reset | Participant policy removed via pinned CLI; baseline read back | `lab4-reset-live`; all eight baseline policies ACTIVE, Gateway ENFORCE. No business or audit records erased. |
| Build/dependency/static checks | Both Python dependency audits and frontend audit report no known vulnerabilities; hash lock integrity, targeted Ruff, shellcheck/syntax and four CFN lints passed | See named commands in CHECKS. Bandit retained ten reviewed medium candidates and zero high; its exit 1 is not relabelled as a clean scan. |
| Local content/assets | 69 content/guided-edit tests passed; 114 app references and 336 required local assets with zero missing/untracked assets | `studio-tests-after-live-repairs`, `source-assets`. Final pin-specific validation occurs after source publication in the Studio handoff. |

Live execution found and repaired defects that mocks did not expose:

- Managed SSE emitted `success` where the UI required `completed`. Normalize the boundary and preserve original persisted tool status.
- Gateway read tools omitted audit rows, and session replay treated turn IDs as session IDs. Record real read executions and resolve each through its durable, principal-scoped turn receipt. Downloaded live Lambda ZIPs match all 20 checked first-party files.
- Return preflight selected exhausted items and RLS probes used invalid business values. Select remaining returnable quantity, run rollback-only RLS controls before consumption, preserve actual reason/status constraints, and compare the database's textual product ID as an integer. Independent PostgreSQL regression tests cover exhaustion and constraints.
- A refused operation retains an unfinished idempotency claim. Measure it separately; require exact request/key/hash matching and zero committed business effect. The UI now explains this distinction. No claim or audit evidence was deleted to obtain a pass.
- MCP discarded the streamed 403 body. Retain only the bounded error message before stream closure, require the observed suppression marker and exact configured policy ID, and do not follow redirects. The actual service returns `Output blocked by policy: Policy evaluation denied due to credit_output_sensitive_information-7i88owc6gk` after the credit commits.
- The identity evidence SQL contained a psycopg percent placeholder collision. Use `position` for the literal substring and assert the actual browser request succeeds.
- The boundary run selector had an ambiguous accessible name. Give it the explicit name `Evidence run` and exercise the selected recorded run through the browser.

## Deployed identity, rollback and retained state

`evidence/deployed-artifacts.json` records runtime versions, Lambda code SHA-256 values and production frontend bundle hashes. Both current managed Runtime responses match fingerprint `34184fa574bd0a689fe0669214c45cbec40df36f516da97671233b6b0bb57c06`; shopper is version 9 and Operator version 1. The final local backend/UI plus these managed services were tested. A final source commit is not itself a remotely deployed workshop host.

The existing managed update initially failed on output-policy grammar and policy/schema ordering. Failed attempts remain in CHECKS. Memory's transitional state temporarily prevented rollback; after it became ACTIVE, continuation completed without skipping resources. The repaired two-phase provisioner completed the infrastructure update, then attached policies. This proves an update and recovery of this established stack, not a new event's root/nested CFN bootstrap.

Review execution preserved three successful synthetic return rows (products 41, 42 and 43), four one-cent synthetic credits (two diagnostic and two final controls), refused idempotency claims, and append-only audit/proof observations. Same-key credit replay did not duplicate an effect. These records are intentional evidence; do not delete them to make a later run look fresh. Reset removed only the participant policy. Memory extraction records and managed resources remain and can incur normal service costs; CloudWatch retention is 30 days. Full teardown and retained-resource verification need a disposable workshop environment.

## Concrete blockers and smallest next actions

| Gate | Blocker | Smallest action |
|---|---|---|
| Native Studio render | No local Workshop Studio renderer is installed; published Studio remote is inaccessible | Restore Studio access and inspect the imported package in its actual renderer, including tabs, expanders, code copy/paste, downloads and laptop navigation. |
| Remote Studio delivery | Read-only remote lookup returned HeadBucket HTTP 403; actual assets bucket/prefix is not available | Owner supplies/uses the package's actual asset destination and valid Studio session; verify existing bytes before upload and final bytes/content types afterward. |
| Fresh infrastructure automation | Existing Aurora/Cognito are shared with the older deployment; destructive bootstrap/reset/teardown would affect shared state | Provide an established disposable event/account target for automated root/nested CFN provisioning, readiness, partial-failure, reset and teardown checks. These automated gates remain in scope and are BLOCKED, separately from the excluded human rehearsal. |
| Final hosted application | Final UI/API was tested locally with managed AWS services; no final Studio host exists yet | After owner publication, provision/update the authorized event host and compare source, infra, runtime and asset identities; rerun the automated journeys there. |

## Remaining release procedure

Final source commit/push, independent remote verification, local Studio re-pin and clean-source release validation are recorded in the local Studio handoff after they run. Read the exact source SHA from that handoff/contentspec, not from the initial commit recorded above. No guide or media provenance field should be rewritten to imply that an older capture used the new commit.

Owner operations use an explicit reviewed file list, three named nested-template uploads, and the established Studio import/publication workflow. Do not use `git add .`, `git add -A`, force-push, or destructive S3 sync flags. Asset destination and credentials must come from the actual Studio package; do not guess from the source deployment's CDK bucket.

## Human fresh-Workshop-Studio rehearsal — EXCLUDED, still required

1. Record Studio revision, source SHA, infrastructure digest, AWS account/Region and runtime fingerprints. Provision the event environment and measure cold startup separately.
2. Confirm readiness, four shoppers, separate staff sign-in, all eight starter blocks, catalog/warehouse rows, Memory strategy readiness and both managed Runtime endpoints.
3. Time the 0–5 introduction, 5–25 inventory lab, 25–50 retrieval lab, 50–75 managed/Memory lab, 75–95 governance/Operator lab and 95–100 wrap-up. Record waits and recovery time without moving required work outside the clock.
4. Prove unknown versus zero stock; candidate-budget changes and held-out eligibility; three extracted Memory types, empty new-session history, cited current products, matching deployed fingerprint and correlated trace.
5. Prove authentication rejection, Cedar denial with keyed absence, business refusal, one commit and same-key replay, benign output, sensitive-output suppression without duplicate effects, RLS rejection, and a separate staff investigation ending at human review.
6. Exercise missing configuration, stale/unknown build, unavailable service, failed evidence read and bounded catch-up. Check keyboard navigation, laptop Studio rendering, code copy/paste and downloads.
7. Export sanitized evidence. Run documented policy reset and validate the baseline. Teardown only event-owned resources; verify retained logs/snapshots/Memory and their cost ownership. Record failures rather than announcing a successful cleanup.
