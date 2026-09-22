# Governed source release checks

Date: 22 September 2026. Branch: `governed`.
Base: `1f9fe29b584891f6d2aad680c48afb1990de0496`.

This release packages the connected four-lab, eight-task curriculum, its starter
and recovery contracts, the source-to-app workbench explanation, and Lab 3's
participant deployment mode. Workshop Studio must pin the resulting published
commit before the revised guides are published. See Studio's
`docs/SOURCE-PIN-HANDOFF-2026-09-22.md` for the exact publication and pin receipt.

## Corrections found during release validation

- The Resume accessibility assertion still expected the previous Lab 3 short
  title. It now checks the current title and retains the exact destination check.
- Operator replacement search constructed its fallback before checking whether
  the strict result was sufficient. It now returns sufficient strict results
  without consulting the unfinished Lab 2 fallback. Its regression test rejects
  any attempt to construct that unnecessary fallback.
- Tests of completed fallback behavior now explicitly use the existing completed
  plan fixture. The starter refusal and recovery implementation remain separately
  checked; a passing surrounding service test does not complete the exercise.
- The copy scanner now recognizes the source-state sentinel as internal inspection,
  not a sentence returned by the route.
- Source authoring notes and the speaker brief now match the A/B task order and
  15/15/20/25-minute lab budgets. The presenter introduction remains separate.

The first backend run reported six failures, and the first frontend run reported
one stale-label failure. The initial backend report is retained in `evidence/`.
The final runs below supersede those results without removing the failed evidence.

## Local validation

| Check | Result |
|---|---|
| Full backend suite | PASS: 3,594 passed, 90 skipped; two dependency deprecation warnings |
| Focused backend repair suite | PASS: 197 tests |
| Full frontend suite | PASS: 158 files, 1,138 tests |
| TypeScript, lint and production build | PASS |
| Production dependency audit | PASS: zero vulnerabilities |
| Shell syntax | PASS: 17 scripts |
| Participant reset contract | PASS: all nine regions remain starters |
| Studio automated suite | PASS: 109 tests, including isolated SQL exercise checks |
| Source whitespace and credential-pattern review | PASS |

Logs in `evidence/source-release-*` belong to this release review. Earlier logs
in this directory retain their original scope and date. Source checks do not
prove Workshop Studio publication, hosted parity, or a fresh-account rehearsal.
The owner retains Studio staging, commits, pushes, S3 synchronization and publication.
