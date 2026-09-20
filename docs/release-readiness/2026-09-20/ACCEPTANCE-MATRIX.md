# Governed DAT416 acceptance matrix — 2026-09-20

**Event release: HOLD.** PASS applies only to the scope and evidence stated in
that row. FAIL records a known unmet requirement. BLOCKED records an unavailable
environment, access or execution boundary. Only the human-led fresh-event
rehearsal is EXCLUDED. Owner publication operations are PENDING USER ACTION.
See [the report](RELEASE-READINESS.md), [check ledger](CHECKS.jsonl) and
[evidence index](evidence/README.md).

The exact final source SHA, remote verification, CI result and generated Studio
revision are in the local Studio `docs/release-readiness/2026-09-20/` handoff.
They identify the source commit containing this matrix; a document cannot
contain its own final Git SHA.

| ID | Acceptance gate | State | Evidence and boundary |
|---|---|---|---|
| S01 | Intended source/worktree and unrelated-work ownership | PASS | `governed` worktree initially clean at `d11ad20e2382947853e403196a420aa66a346713`; separate Builders `main` and its four untracked screenshots preserved. |
| S02 | Studio repository, track, initial pins and dirty inventory | PASS | Correct governed Studio folder; `mainline` at `ce9fad096bb41f1ed6f431b0e560aa305e7be667`; preexisting local package/media changes inventoried. Full old/new pins are in the local handoff. |
| S03 | Instructions, skills, voice and design direction | PASS | Project/module instructions, VOICE, authoring and relevant skills read. Referenced global steering files were unavailable and are disclosed. |
| S04 | AWS identity, region, service and process ownership | PASS | Read-only identity/resource inspection in the established workshop account, explicit `us-east-1`, existing SSM tunnel and listeners preserved; exact private identifiers in local Studio handoff. |
| S05 | Reuse and governed naming of managed component | PASS | Reviewed tag-only CFN update completed; unchanged template and all 25 physical IDs; renderer/generated project preserve governed labels. Older shared component retained with an explicit dependency reason. |
| C01 | Repository-wide first-party review | PASS | Inventory and security scanning across application, APIs, agents/tools, runtime skills, SQL/migrations, scripts, tests, solutions and automation; manual participant/write/identity/deploy path review. No claim of identical manual line coverage. |
| C02 | Authentication, authorization and tenant isolation | PASS | Final real Cognito/browser checks; unsigned 401, shopper-to-Operator 403, owner/cross-customer Gateway and Aurora RLS cases. Verifier outage stays 503 and does not invalidate identity. Earlier isolated 502 and its unresolved cause are retained. |
| C03 | Transaction, concurrency, idempotency and truthful recovery | PASS | Full backend tests, isolated transaction/concurrency fixtures and real Lab 4 writes/replay/absence checks. Data-impact limits and consumed quantities are recorded. |
| C04 | AI grounding, tool names/grants, injection and failure boundaries | PASS | Real retrieval/managed calls, current tool-name adapter, constrained SQL, principal-scoped Memory/Gateway and truthful failed return. Full model robustness against arbitrary future prompts is not established. |
| C05 | Backend required suite | PASS | `backend-closeout` and final post-repair suite in CHECKS; pinned dependency environment. Environment-dependent skips are mapped to separate checks, not treated as passes. |
| C06 | Frontend tests, independent types, lint and build | PASS | `frontend-final-privacy-*`: 1,128 tests, independent TypeScript, ESLint and Vite build on official checksum-verified Node 24. |
| C07 | Dependency/security/secret checks | PASS | Known-vulnerability audits, expanded Bandit dispositions and final delta review, current tracked-secret and environment-identifier gates. Historical exposure and private ignored candidates remain explicitly bounded findings. |
| C08 | Scripts, migration captures and automation correctness | PASS | Shell syntax, focused ownership/rollback/SQL tests, private trace/receipt checks and failure-observation proofs. No material diagnostic suppressed. |
| C09 | Full static expansion of environment-sourced shell files | BLOCKED | ShellCheck cannot resolve the local NVM/environment source paths from its static context. Raw diagnostics retained; fresh-bootstrap behavior requires the authorized root environment. |
| U01 | Rendered required routes and actual controls | PASS | Playwright Chromium against the identified local build; 39 route/viewport probes, 44 public checks and 13 authenticated checks; API/SSE/ledger effects separately asserted. |
| U02 | Desktop, laptop, narrow/mobile and presenter viewport | PASS | 1440, 1280×720, tablet, 390 and 320 layouts; overflow/focus/text-scale checks and current screenshots. No physical projector test is claimed. |
| U03 | Keyboard, focus, accessible names/dialogs and reduced motion | PASS | Focus traps/return, named controls, semantic trace group, keyboard table scrolling, sticky-clearance and reduced-motion probes. Automated results do not establish complete screen-reader conformance. |
| U04 | Loading, empty, error, denied, success and recovery UI | PASS | Explicit intercepted-state evidence plus live success/denial evidence. Synthetic state probes are labeled, not represented as service integrations. |
| U05 | Authenticated Storefront, Operator and persisted evidence | PASS | Final form sign-in, shopper turn, saved Operator investigation, principal-scoped ledger, current client records and preview handoff. Separate Operator smoke is labeled fixture-backed. |
| W01 | Complete participant path and optional guide branches | PASS | All ten pages read/rendered locally; prerequisites, four labs, summary/cleanup, appendix and coding-coach branch reviewed. |
| W02 | Safe commands, paths, SQL and environment handoffs | PASS | Executed Labs 1/2 SQL/retrieval, Lab 3 isolated edited candidate/deployment/browser, Lab 4 proof bundle; CLI endpoint and intentional failure handling repaired. Fresh bootstrap/teardown commands are tracked separately below. |
| W03 | Eight genuine starters and solution/fallback parity | PASS | Marker, guided-exercise and solution-parity tests; candidate edits kept outside the source starter. Retained legacy reference defect repaired without populating a starter. |
| W04 | Learning objectives, technical depth and 100-minute design | PASS | Four-lab/two-build structure, observable criteria and recovery reviewed. Pacing is a design target; only a timed human run can validate it. |
| W05 | Native and published Workshop Studio rendering | BLOCKED | Access unavailable. The 20 local page/viewport checks use a Markdown approximation, not Studio. |
| W06 | Slides, diagrams, images, notes and provenance | PASS | 20 capture hashes matched 9-slide architecture/11-slide introduction decks. Historical media remains historical; actual package/link/assets validated locally. |
| W07 | Recorded MP4 playback | NOT APPLICABLE | No recording is shipped or linked as a completed artifact. The recording plan explicitly uses a narrated fallback; no fabricated execution footage. |
| W08 | Positive new Theo return | BLOCKED | Real tool attempt correctly refused by Aurora because the existing order has no eligible quantity. Need a fresh authorized order/case; conversation completion is not a committed return. |
| I01 | Root/nested CFN/schema/package checks | PASS | All four templates lint cleanly; 74 Studio tests plus final release validator. |
| I02 | IAM/trust/PassRole/resource scoping review | PASS | Calls and identities traced; trusted CLI regional wildcards described honestly. Static inspection and established component calls are bounded evidence. |
| I03 | Event-account effective IAM/SCP/permissions | BLOCKED | No disposable Studio root/event-role target established. Admin component success is not participant/bootstrap-role proof. |
| I04 | Bootstrap readiness, retries and failure signaling | PASS | Node 24, database/service gates, marker/migration ordering, required observability and EC2 CreationPolicy contracts tested. Whole new-root execution remains I06. |
| I05 | Current region/service/model/quotas | PASS | Read-only Aurora/model/prefix-list/quota inventory and current primary documentation. Entitlement/capacity in a fresh event remains unproved. |
| I06 | Automated root bootstrap, partial failure, rollback and teardown | BLOCKED | Existing managed components share Aurora/Cognito; no authorized disposable root target. No destructive shared-resource operation performed. |
| I07 | Safe managed restoration and owned cleanup | PASS | Edited candidate and eight policies restored; tag-only update preserved physical IDs; temporary identities removed; receipt-based cleanup tested with exact scope and refusal cases. Not root teardown. |
| I08 | CloudFront-to-editor origin TLS | FAIL | HTTP origin carries session/editor credentials; no approved trusted certificate/domain available. Requires an approved TLS design and live verification. |
| I09 | Required existing log-group customer-managed KMS protection | FAIL | Existing groups lack the required customer-managed key; default service encryption exists. Provisioner/receipt now refuse false protection claims. Need approved key and shared-trace ownership. |
| I10 | Retention, data deletion and cost accounting | PASS | Root database delete/no-final-snapshot behavior, independent CLI/Lambda/log resources, seven-day key deletion and ongoing NAT/Aurora/editor/model costs documented. Execution is I06. |
| A01 | contentspec, ordering, paths, links and local assets | PASS | Current package tests and final release validator; local images/decks/nested templates inspected. |
| A02 | Remote assets, checksums, metadata and delivery access | BLOCKED | Three nested-template HeadObject reads returned 403. No upload was attempted. Remote assets remain unverified until owner upload/readback. |
| A03 | Final local source pins, derived revision and asset manifest | PASS | Project pinner and final clean-source release validation; exact SHA/revision/digests in local Studio handoff. Historical media provenance is intentionally not rewritten. |
| R01 | Task-related source commit and push | PASS | Explicit reviewed task file set committed/pushed on `governed`; containing-commit publication is independently attested in the local Studio handoff. |
| R02 | Independent remote SHA and exact-commit CI | PASS | HEAD/tracking ref/fresh `git ls-remote` agreement and exact-commit CI result in `source-publication.json`. |
| R03 | Exact clean source and local Studio release validation | PASS | Final `validate_workshop.py --release --source-repo` against the verified clean checkout and complete generated pin/template set. |
| R04 | Final managed package and local-build identity | PASS | Runtime versions 19/11, current runtime fingerprint, four Lambdas/20 matched files and final static JS digests in artifacts evidence. |
| R05 | Final hosted root/application/asset identity | BLOCKED | Final Studio root/frontend/API deployment has not been published/deployed. Existing user application remains an older deployment. |
| R06 | Findings, evidence and exact owner handoff | PASS | This report/matrix/checks/evidence plus local Studio full-SHA publication record, checksums, explicit file list and reviewed command sequence. |
| R07 | Post-publication checks | BLOCKED | Remote byte/content-type, native Studio and final hosted journey checks await owner publication and environment/access fixes. |
| H01 | Human end-to-end fresh Workshop Studio rehearsal | EXCLUDED | Still required: fresh startup, timed eight-edit participant path, expected data/denial/recovery outcomes, presentation and cleanup. |

| Owner publication operation | State |
|---|---|
| Studio S3 uploads/sync | PENDING USER ACTION |
| Studio Git staging | PENDING USER ACTION |
| Studio Git commit and push | PENDING USER ACTION |
| Workshop Studio import/publication | PENDING USER ACTION |
