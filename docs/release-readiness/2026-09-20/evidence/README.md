# Evidence index

This directory contains selected, sanitized evidence from the September 20
maintainer review. Exact account/resource identifiers and raw service responses
remain in the reviewer's private `/tmp/pellier-review-20260920` directory and
the separate local Studio release handoff. No credentials, JWTs or copied
environment values belong in this source repository.

| Evidence | What it establishes |
|---|---|
| [artifacts.json](artifacts.json) | Managed Runtime content fingerprints/versions, four Lambda source comparisons, static build digests and byte-for-byte HTTP delivery of 110 final local assets/documents. Does not attest a Studio-hosted deployment. |
| [journeys.json](journeys.json) | Live Labs 1–4, Memory/trace and disposable identity evidence, including recovered errors, refused writes and fixture boundaries. |
| [managed-adoption.json](managed-adoption.json) | Completed governed-label update with unchanged template and 25 physical resources. |
| [browser-accessibility.json](browser-accessibility.json) | Six final authenticated viewports: no reported axe violations, overflow or page errors; incomplete automated contrast determinations retained. |
| [route-captures.json](route-captures.json) | Earlier 39 route/viewport probes. Later affected controls were rechecked by final public/authenticated browser suites. This snapshot is not every backend API. |
| [state-checks.json](state-checks.json) | Simulated loading/empty/error/denial/recovery behavior, explicitly separate from live service outcomes. |
| [keyboard-scroll-checks.json](keyboard-scroll-checks.json) | Keyboard scrolling, named selector and unobscured focus at 390 and 320 pixels. |
| [dialog-checks.json](dialog-checks.json) | Dialog naming, focus entry/trapping/return and evidence interactions. |
| [screenshots.json](screenshots.json) | Current screenshot timestamps, source/derived hashes and encoding provenance. These are new browser captures, not the historical presentation media. |
| [external-gates.json](external-gates.json) | Failed asset reads, absent approved certificate/domain inventory and historical-secret disposition, with account identifiers removed. |
| [shellcheck.json](shellcheck.json) | Complete final ShellCheck diagnostics, including unresolved external-source analysis and informational/style results. Its scanner exit status remains nonzero. |
| [security-reconciliation.json](security-reconciliation.json) | Final Bandit scope/dispositions and repaired security findings. A scanner finding count is not a count of exploitable vulnerabilities. |
| [source-inputs.json](source-inputs.json) | Hashes of final code/config inputs, excluding private/generated dependency directories and this report. Used to detect changes after validation. |
| [logs](logs) | Selected exact check output with ANSI escapes and deployment identifiers removed. Expected synthetic error messages in negative tests remain visible. |

The parent [CHECKS.jsonl](../CHECKS.jsonl) records command, working directory,
UTC start/finish, exit code, duration and original output path. It retains
earlier failures and nonzero scanners. Private one-off harness paths describe
what ran on the authorized account; they are not a portable public deployment
recipe. The repository's maintained tests, scripts and Studio guide remain
the reproducible participant/release commands.

The final full backend suite has environment-dependent skips. Seventy-five
Aurora/RLS/adversarial checks, two immutable/held-out-data checks, and thirteen
SQL cases were executed separately within their recorded boundaries. The
isolated transaction/concurrency SQL fixture used a disposable local test
cluster; the application itself used Aurora. That fixture does not prove
Aurora engine/service behavior or a fresh workshop environment.

Post-commit remote and CI evidence cannot be embedded in the commit it
identifies. The local Studio handoff records those results, the final source
SHA and pin, package checksums, explicit file list and owner publication
commands. Root bootstrap/teardown and native/published Studio checks remain
blocked as described in the acceptance matrix.
