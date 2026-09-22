# Governed browser connection release checks

Date: 22 September 2026. Branch: `governed`.
Source base: `6486b613` (the preceding connected-story release).

This change pairs the private EC2 editor with an authenticated SageMaker browser
workspace. The workspace validates the EC2 origin's certificate and DNS name;
the governed templates remove the HTTP ALB and CloudFront origin. The source
also keeps frontend API requests beneath `/ports/8000/`, persists the matching
Cognito callback, and requests progressive forwarding for both chat streams.
See [the transport contract](../../WORKSHOP-TRANSPORT.md).

## Completed local checks

| Check | Result |
|---|---|
| Backend suite | 3,594 passed, 90 skipped; two dependency deprecation warnings |
| Frontend suite | 159 files, 1,141 tests passed |
| Stream and prefix regression tests after final assertions | 19 passed |
| TypeScript, lint, production build | Passed |
| Production dependency audit | Zero vulnerabilities |
| Build with `/ports/8000/` application prefix | Passed |
| Shell syntax | 18 scripts passed |
| Paired Studio automated suite | 111 tests, one optional integration test skipped |
| Explicit transport integration run | Passed using actual nginx and Jupyter server proxy 4.4.0 |
| CloudFormation schema and reference checks | Four templates passed |

The explicit integration run verifies authenticated entry, launcher routes,
relative editor redirects, app paths, request and response cookies, authorization
headers, streaming before response completion, WebSockets, certificate/name
rejection and TLS 1.1 rejection. It generates synthetic credentials, publishes
only the public certificate through a fake AWS command, and calls no AWS API.

The Mac initially stalled while Bash wrote a large test-fixture heredoc to a
pipe. The completed backend run used a temporary subprocess adapter that sets
`BASH_COMPAT=50` even for fixtures that replace their environment. It changes no
application logic. A focused bootstrap fixture now carries a timeout and this
compatibility setting directly. An initial run from the wrong directory and
the interrupted runs are retained locally under `/tmp/pellier-backend-replacement-*`;
they are not claimed as passing checks. GitHub's ordinary Linux test command is
a separate check whose result belongs in the Studio handoff.

The first Linux CI run passed 3,593 backend tests and skipped 90, but its
repository identifier check mistook a 12-digit substring in the historical Git
SHA above for an AWS account ID. The historical reference now uses its unambiguous
short SHA; the identifier check remains unchanged. The complete preceding SHA
remains in Git history and the Studio handoff. The frontend CI job passed.

## Publication and deployment boundary

Studio must pin the resulting published source SHA before publishing these
templates. The paired repository's `docs/SOURCE-PIN-HANDOFF-2026-09-22.md` records
that SHA and its derived infrastructure revision after publication.

This is local implementation and validation. It does not prove the managed
endpoint's actual TLS boundary, event-role permissions, notebook capacity,
AL2023 lifecycle execution, real Code Editor or Cognito behavior, lifecycle
replacement, rollback, teardown or a timed fresh-account rehearsal. The owner
retains Studio staging, commits, pushes, S3 synchronization and publication.
