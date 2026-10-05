---
name: verify-governed-workshop
description: Audit Pellier's governed 100-minute workshop against its title, abstract, four labs, runtime claims, proof surfaces, and delivery gates. Use before flagship delivery, after changes to retrieval, audit, AgentCore, Cedar, workshop navigation, bootstrap, or participant-facing evidence.
---

# Verify the governed workshop

Read `references/contract.md` before starting.

## Workflow

1. Confirm the sample application checkout is on `governed`. Do not make or
   backport changes to `main`.
2. Locate the sibling Workshop Studio checkout when available. Treat it as
   the source of truth for participant wording and launch wiring.
3. Map every abstract claim to current code, a repeatable command, and a
   participant-visible proof point.
4. Walk Labs 1-4 in order. Verify the required path before optional
   extensions.
5. Check bootstrap branch selection, model IDs, migrations, service startup,
   and participant-global Claude Code guidance.
6. Run the validation gates in the root `CLAUDE.md`.
7. Verify the storefront (with Ask Pellier and its Builder view) and the
   Operator in a browser. Check console errors, layout, streaming, identity
   state, and evidence provenance.
8. Report findings first, ordered by severity, with file and line references.
   Separate blockers from polish.

## Proof standard

- Prefer curl, SQL, logs, tests, and managed receipts over screenshots alone.
- Treat UI cards as assisted reads, not canonical proof.
- Require an execution row for ALLOW claims.
- Require a DENY receipt plus verified absence of a matching execution row
  for no-execution claims.
- Do not infer Cedar denial from authentication failure.
- Mark any unverified managed-service claim explicitly.

## Scope control

- Preserve the flagship title and four-lab spine.
- Keep the storefront, the Operator and Code Editor primary; the Builder view
  assists a named proof point and never replaces the terminal check.
- Do not add a persona, specialist, business flow, or unrelated AWS service
  merely to make the workshop look broader.
- Fix drift between the app and Workshop Studio in the owning source rather
  than duplicating prose.
