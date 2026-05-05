# Why these agents use different models

*Referenced from Module 1 · Observe of both the Workshop and Builder's Session lab guides. A 2-minute read that lands the workshop's core architectural lesson before participants touch any code.*

---

Five specialists, three model configurations. The system isn't homogeneous on purpose.

**Style Advisor** and **Curator** run on **Sonnet 4.6 at 0.4** because their job is editorial. They describe linen, suggest pairings, carry the voice of the boutique. Flat answers make a flat catalog, and the temperature lift gives the Sonnet model enough room to surprise you without drifting into noise.

**Value Analyst** and **Stock Keeper** run on **Haiku 4.5 at 0.1 and 0.0** because their job is to report. Prices, ranges, warehouse counts. The only thing worse than a slow stock check is a wrong one — Stock Keeper ships at temperature zero, which is the tightest configuration in the system.

**Experience Guide** sits in the middle: **Sonnet for tone** when handling a return, but a **steadier 0.2** because policy is policy. Warmth when the customer needs it; no wandering when the answer is "30 days, prepaid label, refund in 5–7 business days."

**The Orchestrator** that classifies intent runs on **Haiku 4.5 at 0.0** — routing is classification, classification wants determinism. The **SkillRouter** that decides which persona-specific skill to load also runs Haiku 4.5 at 0.0 for the same reason.

## What the Atelier shows

Two surfaces make this variation visible:

- **`/atelier/agents`** — every row shows a different model tag. Sonnet 4.6, Haiku 4.5, temperatures from 0.0 to 0.4. No row is normalized; the variation is the point.
- **`/atelier/performance`** — latency bars that vary by **an order of magnitude**. Sonnet agents run 800–1500 ms p50 warm. Haiku agents run 100–250 ms. The routing layer runs 60–120 ms. You'll see this live when Marco's capstone plays.

## What this means for you

When you design your own agent stack, **model selection is an architectural decision, not a configuration knob**. Ask: does this agent describe, or does it report? Does it carry voice, or does it return a number? The answer tells you which model and which temperature.

The code reflects the answer — `config.py` exposes `BEDROCK_SONNET_MODEL`, `BEDROCK_HAIKU_MODEL`, and `BEDROCK_OPUS_MODEL` as three separate constants. There's no `DEFAULT_MODEL` that all five agents inherit from. If there were, the lesson would be invisible.
