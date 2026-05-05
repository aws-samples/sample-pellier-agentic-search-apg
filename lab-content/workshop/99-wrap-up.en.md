---
title: Wrap-Up
weight: 50
---

**Time budget: 5 minutes**

## What you shipped

- **Stock Keeper** — full specialist build (system prompt + `floor_check` + `restock_shelf` + `running_low`). Marco's Turn 4 lands.
- **Experience Guide** — full specialist build (system prompt + chaining pattern). Theo's return question resolves.
- Five tools wired end-to-end. Two Atelier states changed from dashed-exercise to solid-shipped.
- A "swap a model" moment that made the architectural cost of the wrong choice tangible.
- A capstone where all five specialists fire on their own models — Sonnet for voice, Haiku for reports, no normalization.

## What's deferred (on purpose)

The real stack ships these; the 2-hour budget made us trade them off:

- **Long-Term Memory (LTM)** — preference learning across sessions. The Atelier already has Marco's LTM preamble baked in; you didn't build the writer. See `backend/services/agentcore_memory.py` for where it would hook in.
- **AgentCore Runtime (managed)** — the same Strands agent, hosted on Bedrock AgentCore instead of local. Flip `settings.USE_AGENTCORE_RUNTIME = True` to compare cold-start and latency.
- **Additional guardrails** — the Cedar policy hook you exercised blocks > 500-unit restocks. Production would also guard PII in tool outputs, rate-limit per-user, etc.
- **The sixth specialist** — returns-processing agent that actually issues refund labels. Stubbed in the `archive/` directory of the repo.
- **10K-product catalog** — the 40-product seed is for workshop tempo. A full-scale pgvector comparison (HNSW vs IVFFlat) lives in `docs/benchmarks.md`.

## 30 days from now

If this system were yours tomorrow, here's the honest order:

1. **Extend the Evaluations scorecard** first. Regressions are silent in agent systems — instrument before you build.
2. **Wire LTM** next. Personalization carries disproportionate quality uplift for modest engineering cost.
3. **Add one more specialist** that has real customer value. Marco's journey has 5; your domain might want 7 or 3. Don't normalize.
4. **Swap the Dispatcher for Agents-as-Tools** on a single route that would benefit from LLM-based intent classification (edge cases the regex misses). Pattern III is fast but brittle; Pattern II is smart but ~200 ms slower. Measure first.

## Resources

- Source repository: `https://github.com/aws-samples/sample-blaize-bazaar-agentic-search-apg`
- Strands Agents SDK: `https://strandsagents.com/latest/`
- Bedrock AgentCore: `https://aws.amazon.com/bedrock/agentcore/`
- pgvector 0.8.0 + Aurora: `https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.VectorDB.html`

## One last thing

Grab a note of Marco's pills before you close the Boutique tab. You'll want to show a teammate. The thing that made Marco's Turn 4 land isn't magic — it's five files worth of code you wrote in the last 90 minutes. That's the lesson.

Thanks for building with us.
