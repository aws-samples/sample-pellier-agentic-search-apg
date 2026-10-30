# Evidence

Records of proof runs that a page in this repository relies on. Each file is one run, named
`<subject>-proof-<YYYY-MM-DD>-<region>.md`, and holds only measured values: what was run, the
commit and infrastructure revision, the printed lines the claim rests on, and what was left
afterwards. A page quotes the newest record for its subject; a claim with no record here is
not validated.

## Own-account proof

`own-account-proof-<date>-<region>.md` records one full run of
[Run Pellier in your own account](../run-in-your-own-account.md): the `deploy` command's
`Stack ready in` line, the readiness check and the four labs' pass lines run on the host, the
`teardown` command's `Stack deleted in` line and its **Left in place** list, and the
`describe-stacks`, `list-functions` and `list-buckets` results after it.
