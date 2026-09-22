# Governed hands-on learning pass

Date: 2026-09-21. Source base: `1f9fe29b584891f6d2aad680c48afb1990de0496`.
These changes are local to the `governed-product-pass` worktree on `governed`.
Builders/main was inspected as evidence and remains unchanged.

## Changes prompted by the Builders event feedback

- All eight governed tasks now expose the implementation contract, source file,
  edit boundary, prediction, hints, and checks before the worked answer. Complete
  answers are explicitly labelled recovery references. Existing exercise markers
  and the eight-task completion contract are unchanged.
- The Workbench has a collapsed source-to-app explanation per lab: the files,
  request path, expected observable change, and a counterexample. Full task
  instructions remain in Workshop Studio.
- The existing retrieval harness scores the two saved Anna comparisons without
  initializing the live backend or loading credentials. It reuses the existing
  labels and scoring functions. Candidate coverage is separate from Recall@5,
  MRR@5, and Hit@1. Worse and unchanged results remain visible. Changed soft
  preferences or relaxation are reported alongside both plans; changed hard
  constraints, models, reused receipts, and fallback runs are refused.
- Lab 3 brings Memory actor scope and deployment-versus-local-save distinctions
  into the required path. Lab 4 asks participants to reconcile a committed but
  suppressed credit before deciding whether to replay its existing key.
- The opening fits inside the existing five-minute allocation. The full
  ten-minute presentation remains a separately budgeted narrative; no slide
  binary was changed. A late start uses explicit incomplete checkpoints and
  continuation, not skipped proof or an implied sandbox extension.
- A portable source map and learning notebook retain predictions, edits,
  evidence IDs, recovery use, and next actions. Introduction creates the notes
  only if absent; Summary includes them in the existing evidence export.
- Recovery distinguishes starter state, authentication, managed readiness,
  stale review, and uncertain writes. Builders source includes a starter-state
  409 path, but the event's specific 409 cannot be diagnosed without its route
  and response details. No incident-root-cause claim is made.
- Corrected the RRF documentation: membership in both branches does not
  necessarily outrank a high-ranked single-branch result.

## Validation

| Gate | Result and boundary |
|---|---|
| Frontend | PASS: 158 files, 1,138 tests; type check, lint, production build; dependency audit reports zero vulnerabilities. |
| Affected backend | PASS: 153 targeted checks during implementation, including exercise markers, solution parity, naming, copy, retrieval and endpoint contracts. After final scoring changes, the complete retrieval/endpoint subset passed again: 59 tests. |
| Studio tests | PASS: 101 tests, including scoped recovery snippets, isolated PostgreSQL checks, and false-positive counterexamples. |
| Browser | PASS: disclosure opens, follows selected lab, and resets when switching labs. Checked the actual preview at desktop and 900px width; no browser error logs. Original route and viewport restored. No managed write performed. |
| Guide budget | PASS: 5,394 required-path words and 34 command blocks, within existing limits. Commands and proof gates remain visible. |
| Source/Studio whitespace; shell syntax | PASS. |
| Complete Studio package validation | PENDING SOURCE PUBLICATION/PIN: the current `894b04a8...` participant pin lacks `workshop/README.md` and `workshop/learning-notes.md`. These are the only remaining validator errors. The new harness option also requires the new source revision. |
| Fresh-account execution and elapsed timing | NOT RUN in this pass. Reading budgets and local tests do not prove 100-minute completion, provisioning, managed services, or hosted behavior. |

## Publication handoff

Review and publish the governed source before updating the Studio source pin.
Do not publish guides against the old revision: they now reference new files and
the saved-comparison scoring option. Studio staging, commits, push, S3 sync,
import, and publication remain owner-managed. This pass neither commits nor
pushes either repository and does not advance the pin.

Studio files changed by this pass: `WORKSHOP_AUTHORING.md`,
`content/00-introduction/index.en.md`, the four lab `index.en.md` files,
`content/60-summary/index.en.md`, `content/90-appendix/index.en.md`,
`docs/INTRODUCTION-DECK.md`, and `scripts/test_guided_exercises.py`.
Preserve the other pre-existing Studio changes during review and publication.
