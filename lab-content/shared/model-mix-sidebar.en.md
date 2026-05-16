# Why these agents use different models

*Referenced from Module 1 · Observe of both the Workshop and Builder's Session lab guides. A 2-minute read that lands the workshop's core architectural lesson before participants touch any code.*

---

Five specialists, three model configurations. The system isn't homogeneous on purpose.

**Style Advisor** and **Curator** run on **Claude Opus 4.6 at 0.4** because their job is editorial. They describe linen, suggest pairings, carry the voice of the boutique. Flat answers make a flat catalog, and the temperature lift gives the model enough expressive room without drifting into noise.

**Value Analyst** and **Stock Keeper** run on **Claude Haiku 4.5 at 0.1 and 0.0** because their job is to report. Prices, ranges, warehouse counts. The only thing worse than a slow stock check is a wrong one — Stock Keeper ships at temperature zero, which is the tightest configuration in the system.

**Experience Guide** sits in the middle: **Opus at 0.2** — warmth when the customer needs it; steadier temperature because policy is policy (returns, labels, SLA language).

**The Orchestrator** (intent routing) runs on **Haiku 4.5 at 0.0**. So does **SkillRouter** loading persona skills — classification wants determinism.

## What the Atelier shows

Two surfaces make this variation visible:

- **`/atelier/agents`** — every row shows a different model tag. Opus 4.6 vs Haiku 4.5, temperatures 0.0–0.4. No row is normalized.
- **`/atelier/performance`** — latency bars varying by **an order of magnitude**. Opus-heavy turns often land **~800–1500 ms** p50 warm; Haiku **~100–250 ms**; routing **~60–120 ms**.

## Configuration

In **`pellier/backend/config.py`**, editorial agents consume **`BEDROCK_OPUS_MODEL`**; reporting agents **`BEDROCK_HAIKU_MODEL`**. **`BEDROCK_SONNET_MODEL`** is **legacy naming only** — it defaults to the same Opus inference profile when older overrides still set it.

## What this means for you

**Model selection is an architectural decision, not one global default.** Ask: does this agent *describe*, or *report*? The answer picks model + temperature — visible in **`config.py`**, audible in Boutique tone, measurable in `/atelier/performance`.
