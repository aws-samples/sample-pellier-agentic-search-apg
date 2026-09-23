# Governed source and Workshop Studio audit

Date: 22 September 2026. Scope: the `governed` source worktree and the separate
governed Workshop Studio package. Source base: `9732cddf1b71ed49a28c63d126d5200017a4f5d0`.
The Builders tree was not changed. This is a local audit receipt, not an AWS
rehearsal or a Workshop Studio publication receipt.

## Findings and corrections

1. **Support history routed to product recommendations.** The shared intent
   router did not recognize ticket requests. Three reproductions failed before
   adding ticket vocabulary; local and managed rails now select customer support.
2. **Lab 2 could inspect a different comparison.** High-water and source filters
   did not distinguish a later comparison. The worksheet, starter and recovery
   scaffold now require the comparison ID captured by the guide.
3. **Partial RRF evidence could pass.** PostgreSQL `bool_and` ignores NULL inputs.
   Explicitly reject a missing recomputed score. The executable SQL regression
   failed before the fix and now rejects NULL, missing and mismatched results.
4. **Lab 3 probes rejected the documented shell state.** The guide sourced a token,
   then combined it with `--user`. The probe correctly rejects ambiguous identity.
   The two commands now clear the token for their child process only and mint Theo's
   verified token. The parent shell retains its token.
5. **Lab 3 did not require the new support capability to execute.** Its second
   required Storefront turn now asks for ticket history, replacing a product
   pairing question. The guide checks that exact support turn, current run,
   customer binding, managed execution, and executed build. Pairing and return
   questions remain optional; the required Storefront path still has two turns.
6. **Incomplete or unrelated Lab 3 evidence could pass.** The combined proof now
   requires named boolean checks and reconciles both Gateway probe identities with
   the selected database principal. Missing assertions, foreign customers, wrong
   targets/tools/outcomes and unknown or stale builds fail the executable tests.
7. **Guide and source copy had drifted.** Task 3A now consistently includes both
   catalogue and caller-binding edits; Task 3B deploys and checks them. The guide
   makes Lab 1 restart explicit, keeps tracing optional, labels exercises as tasks,
   and links the appendix to the governed source branch. The CLI help now matches
   its refusal to combine `--user` with an inherited token.

## Validation completed

| Gate | Result |
|---|---|
| Full backend suite, lock-aligned Python environment | PASS: 3,597 passed, 90 skipped; two upstream deprecation warnings |
| Final comparison and recovery parity tests | PASS: 42 tests |
| Full frontend suite | PASS: 1,141 tests in 159 files |
| Frontend type checks, lint, production build | PASS |
| Frontend production dependency audit | PASS: zero known vulnerabilities |
| Python requirements.lock dependency audit | PASS: zero known vulnerabilities |
| Shell syntax | PASS: 18 scripts |
| Studio suite, including real isolated PostgreSQL and jq counterexamples | PASS: 123 tests, one optional integration skipped |
| Studio source/guide validator | PASS: 95 local links/assets, four templates, 28 required Bash blocks and 29 optional blocks, 28 source artifacts, four SQL contracts |
| CloudFormation lint | PASS: four Studio templates |
| Product assets | PASS: 336 required assets; no missing or untracked assets |

The Studio validator retains the existing 5,400-word required-path cap. The
four labs, eight A/B tasks and 15/15/20/25-minute lab targets are unchanged.

## Browser checks and remaining proof

Inspected Storefront, Lab Collection, Lab 3 Workbench, Operator action queue and
client-book error states, Govern, the five-outcome verification view, mobile
navigation and How Pellier Works. Storefront and How Pellier Works had no
horizontal overflow or broken images at 390 px. Evidence remains explicitly
unavailable when the backend is offline; recorded examples identify their origin.

This browser check used a local frontend without a live backend. It does not
establish authenticated customer conversations, Operator investigation, managed
Runtime deployment, Memory extraction, Cedar outcomes, output suppression or
business writes. Those still require a fresh-account rehearsal, including the
TLS connection and measured participant timing. The 90 backend skips and optional
Studio integration skip are not successful deployment evidence.

The source fixes and guide edits must be released together. After source push,
update all local Studio source pins and run the release validator. The owner
retains Studio commits, pushes, S3 synchronization and publication.
