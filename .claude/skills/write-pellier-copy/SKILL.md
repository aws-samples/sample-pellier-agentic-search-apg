---
name: write-pellier-copy
description: Create or revise Pellier shopper copy, editorial model prompts, runtime skill prose, outcome states, and Builder view and Operator explanations. Use when changing storefront text, specialist voice, follow-up suggestions, policy or failure messages, VOICE.md, pellier_copy.py, or skills/*/SKILL.md.
---

# Write Pellier copy

Read `VOICE.md` and the nearest `CLAUDE.md` before editing.

## Workflow

1. Classify the surface:
   - Pellier copy is warm, grounded, brief, and free of system jargon.
   - Builder view and Operator copy is operational and may name architecture
     precisely.
   - Workshop copy is instructional and must name the canonical proof.
2. Find the owning source. Do not patch rendered or generated output.
3. Identify the evidence available to the sentence. Remove claims the runtime
   cannot prove.
4. Write the shortest useful copy that preserves the intended action.
5. Check that policy denial, authentication, validation, and availability
   remain distinct.
6. Run the relevant copy, frontend, and backend tests.

## Guardrails

- Do not invent products, variants, prices, inventory, memory, audit rows, or
  policy decisions.
- Do not use human handoff as a generic empty-result response.
- Do not expose raw tokens, ARNs, endpoints, or internal stack identifiers to
  shoppers.
- Do not repeat product-card fields in prose.
- Keep follow-up suggestions answerable from the current tool result and use
  only verified product or variant relationships.
- Do not add follow-up questions when the current request can be answered.
- Preserve code and SQL typography when editing the Builder view or the
  Operator.

## Validation

For backend shopper copy:

```bash
cd pellier/backend
python tests/test_copy_compliance.py
python -m pytest tests/test_backend_copy_hardcoded.py -q
```

For frontend copy:

```bash
cd pellier/frontend
npm test -- --run
npm run type-check
```
