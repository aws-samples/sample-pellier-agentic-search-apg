# Governed release acceptance matrix — 2026-09-19

Source evidence snapshot immediately before commit. Publication-dependent rows are closed only by the separately saved local Studio release handoff; this snapshot does not claim future operations succeeded. All evidence is bounded to the named environment and final affected reruns in CHECKS.jsonl.

| Gate | Status | Evidence / limitation |
|---|---|---|
| SCOPE | PASS | Exact governed worktree/branch, separate Studio package, AWS account/Region and deployment suffix identified; no RC Git branch exists. |
| CODE | PASS | First-party UI/API/service/agent/tools/SQL/scripts/configuration/release paths reviewed; root causes repaired; 3,039 backend and 1,113 frontend tests. |
| SECURITY | PASS | Principal binding, staff denial, RLS, immutable evidence, XML, output controls and dependency checks; ten Bandit candidates retained and reviewed with bounded justification. |
| BACKEND | PASS | backend-frozen-final: 3,039 passed, 64 explicitly environment-gated skips separately exercised in Aurora/isolated SQL runs. |
| FRONTEND | PASS | Independent type-check, lint, build, 1,113 tests; last label change rechecked with 5 affected tests and build. |
| DEPENDENCIES | PASS | Backend hash-lock audit, runtime dependency audit and npm audit report zero known vulnerabilities; no warning suppression. |
| BROWSER | PASS | Public journeys plus actual managed Cognito shopper, Operator and exact boundary-run interactions; persistence reconciled in Aurora. Fixture/reference surfaces identified. |
| DESIGN | PASS | Approved direction preserved; 18 axe surfaces with zero violations, 390/1280/1920 widths, keyboard/focus/recovery/reduced motion. On-screen presenter-width evidence, not physical projector testing. |
| CONTENT | PASS | All required/optional guides reviewed; 69 snippet/contract tests; actual Lab 1/2 commands plus managed Memory and Lab 4 proofs. Timing is an unmeasured target. |
| RENDER | BLOCKED | Native local Studio renderer unavailable; published Studio access returned 403. Static validation is not renderer proof. |
| INFRA_STATIC | PASS | Four CFNs linted, current RDS/service/model availability checked; participant IAM Access Analyzer returned no findings; wildcard scopes reviewed. |
| INFRA_LIVE | PASS | Established managed stack update, both runtimes, four Lambdas, Gateway/Memory/policies and permission-dependent live calls passed; bounded existing-environment proof. |
| BOOTSTRAP_STATIC | PASS | Ordering, readiness checks, migrations, fail propagation, secure credentials and shell validation repaired/tested. |
| BOOTSTRAP_FRESH | BLOCKED | No established disposable fresh event/account target; existing Aurora/Cognito shared. Automated full CFN/readiness check remains outstanding. |
| LIFECYCLE_MANAGED | PASS | Actual failed update recovered without resource skips, successful two-phase rerun, participant-policy reset and baseline readback. |
| LIFECYCLE_FULL | BLOCKED | Destructive application reset/teardown and retained-resource checks cannot run against shared environment; need disposable event target. |
| ASSETS_LOCAL | PASS | Manifest paths, source assets, 22 media checksums, editable decks/notes and local nested templates checked. |
| ASSETS_REMOTE | BLOCKED | Studio remote 403 and unavailable actual S3 destination prevent read-only delivery/byte/content-type verification. |
| MEDIA | PASS | Architecture/guide vocabulary coherent; fresh app screenshots separated from Sept 18 illustrations. Planned 75-second recording remains explicitly unrecorded, not a required automated gate. |
| LIVE | PASS | Labs 1/2 live guide overlays, Memory extraction/new-session recall, real managed shopper/Operator, five boundary outcomes and reset passed in established workshop environment. |
| IDENTITY_MANAGED | PASS | Actual runtime response fingerprints match current code; downloaded Lambda ZIPs match 20 first-party files; current production frontend hashes saved. |
| IDENTITY_HOSTED | BLOCKED | Final local UI/API plus managed AWS tested; no final Studio host deployed. Published host/cache parity remains pending publication. |
| SOURCE_RELEASE | BLOCKED | Source snapshot precedes its enclosing commit. Final commit, push and independent remote verification are recorded in local Studio RELEASE-HANDOFF.md after execution. |
| STUDIO_PIN | BLOCKED | Pin-specific gate follows source publication; authoritative final result is in local Studio RELEASE-HANDOFF.md. |
| POST_PUBLICATION | BLOCKED | Owner publication has not occurred; published rendering, assets and final event-host checks remain pending. |
| HUMAN_REHEARSAL | EXCLUDED | Only human-led end-to-end fresh Workshop Studio event/account rehearsal is excluded; checklist in release report, still required before delivery. |

## Owner publication operations

| Operation | Status |
|---|---|
| Studio S3 uploads/sync | PENDING USER ACTION |
| Studio git staging, commit, push | PENDING USER ACTION |
| Studio publication/import | PENDING USER ACTION |
