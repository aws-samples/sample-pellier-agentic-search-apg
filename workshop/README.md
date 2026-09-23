# Governed workshop: keep building after the session

Workshop Studio contains the instructions and recovery answers for the four labs.
This directory is the source map and portable notebook for the **governed** track.
The Builders event informed its pacing and exercises; `main` is a different track.

Use `learning-notes.md` to retain a prediction, the code you changed, the exact
evidence, and a design decision. A supplied answer, an open page, or a successful
conversation is not a completed task. Record where you used recovery and keep
the same verification requirements.

| Lab and task | Work you do | Evidence to keep |
|---|---|---|
| 1A · Marco | Connect inventory to Aurora | Test inputs you chose, classified by the catalog; unknown, ambiguous and zero stay distinct. |
| 1B · Marco | Make the agent use the facts | Exact turn, tool result, warehouse rows. |
| 2A · Anna | Explain the ranking | Your RRF judged against the recorded scores of the exact receipt. |
| 2B · Anna | Relax preferences, keep requirements | The preference you chose, counts proving strict-empty, unchanged requirements, eligible IDs. |
| 3A · Theo | Connect the customer-scoped tool | Direct owned and foreign Gateway results. |
| 3B · Theo | Deploy and challenge the conversation | Agent-path ticket reads bound to Theo, fresh session, executed build; Memory is context. |
| 4A · Jessica | Write the ownership rule | Five control outcomes under your Cedar rule. |
| 4B · Jessica | Test ownership and reconcile the case | Rollback-only RLS, keyed absence with a positive control, one reviewed return and what it did not settle. |

Only edit the lab's markers. Python edits in Labs 1–2 need the guide's backend
restart. Lab 3 packages its support adapter and needs a new Runtime session; it reuses
provided Lambda tools. The Lab 1 wrapper and Lab 2 planner remain in-process. Lab 4 needs
policy validation and deployment. Changing a local file does not update AWS.

## One concierge, four growing responsibilities

**Know the facts → respect the requirements → establish the caller → govern the action.**

Each customer introduces the next responsibility. Keep the code and evidence from
each chapter, while using a separate identity and conversation for each customer.
See [the task contract](../docs/WORKSHOP-STORY-ARC.md) for edit locations, rejected
implementations and evidence boundaries.

## Follow the request, then challenge the result

- **Marco:** Storefront → chat API → specialist → tool → business logic → Aurora.
  Compare the direct tool envelope with the exact turn's execution record.
- **Anna:** in-process retrieval executor → SQL eligibility → lexical/vector ranks →
  RRF → candidate budget → rerank. Explain where a candidate disappeared before
  changing that stage. A fallback may relax preferences, but it must carry the original hard constraints and exclusions into every attempt.
- **Theo:** verified identity → Runtime → Gateway and Policy → scoped tool.
  The cross-session Memory experiment uses one verified-user/run actor; regular
  Storefront history uses a separate actor per conversation. Memory is context,
  not proof of a purchase or current availability.
- **Jessica:** identity → Cedar → tool → transaction → output control. A response
  suppressed after a commit must not be retried with a new operation key. Compare
  the existing operation, domain effect, and audit evidence first.

## Revisit Lab 2 without more model calls

The required guide saves one comparison. For an optional pool experiment, first save two same-query comparisons as `lab-2-before.json` and `lab-2-comparison.json`, changing only the candidate budget. Then score the saved returned IDs against the supplied Anna relevance labels:

```bash
python3 scripts/eval_retrieval_harness.py --compare-saved \
  /tmp/pellier-evidence/lab-2-before.json \
  /tmp/pellier-evidence/lab-2-comparison.json
```

This mode makes no service calls. Candidate coverage, Recall@5, MRR@5, and Hit@1 answer different
questions. Unchanged and worse results are valid observations, not reasons to
relabel the products. A changed executed plan makes the captures incomparable as
a pool-only experiment. SQL still establishes eligibility and receipt identity.

For an advanced follow-up, author a new `GoldenQuery` in
`scripts/eval_retrieval_harness.py`: label products and exclusions before running,
include a paraphrase and a no-eligible-result case, then use the existing live
harness. Its normal mode requires a deployed environment and incurs service use;
saved scoring does not reconstruct an expired sandbox.

## Keep a useful continuation checkpoint

Before the sandbox closes, download your learning notes and the evidence archive
described in Summary. Record the source revision, last passing check, first failed
check, and next action. Keep the public source link and save or print the Studio
guides if you need them offline. Do not archive `.env`, tokens, credential files,
or the generated deployment directory. Review evidence files for private values
before sharing them. Sandbox lifetime is set by the event; these files do not
extend it.

A 409 alone does not identify the cause. Save the route, response detail, and
exact receipt or operation ID privately. A starter-state warning needs the
bounded edit and reload; a managed-path warning needs deployment readiness; a
review conflict needs the stored review and operation state. Do not disable a
control or issue a fresh write key to make the error disappear.
