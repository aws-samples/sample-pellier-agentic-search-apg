---
title: Module 1 · Observe
weight: 20
---

**Time budget: 20 minutes**
**Surfaces: Sessions → Observatory**

Module 1 is orientation. Before you change anything, you observe what Blaize already does — which specialists the Dispatcher routes to, which tools each agent reaches for, what the model mix looks like, and where the gap is that you'll be closing.

---

## Part 1 · Marco's opening demo (5 minutes, whole class)

Open the Boutique tab. Make sure the **Marco** persona is active in the header.

**Click the four Marco pills in order.** The presenter will narrate each beat live — you're driving the clicks.

| Click | Listen for |
|---|---|
| Pill 1 — "What linen do you have for 10 days in Goa?" | **Style Advisor on Sonnet 4.6 at 0.4.** Editorial voice. 3 pieces. ~1.3 seconds. |
| Pill 2 — "What would go with the Pellier shirt?" | **Curator on Sonnet 4.6 at 0.4, with `the-packing-list` skill loaded.** Voice mentions packability. ~1.4 seconds. |
| Pill 3 — "What's the price range for linen shirts?" | **Value Analyst on Haiku 4.5 at 0.1.** No narrative, just a number. Sub-200ms. |
| Pill 4 — "Is the Pellier shirt at the Brooklyn warehouse?" | **Stock Keeper — in stub state.** Voice-matched non-answer. That's your build. |

Marco closes: *"I'll come back when I'm ready to commit."*

Flip to the Atelier tab. In the sidebar, click **Sessions**, then `marco-opening-demo`. The full 4-turn replay appears — chat transcript, per-turn telemetry, curator's brief. Turn 4 shows a **routing fall-through** panel (telemetry index 11) linking to "Open the Stock Keeper build." That panel is honest about the gap.

---

## Part 2 · Read the model-mix sidebar (2 minutes, solo)

The most important 2 minutes of the day. Open:

`lab-content/shared/model-mix-sidebar.en.md`

Read it through once. Come back.

Back? Now open `blaize-bazaar/backend/config.py` and find the three constants:

```python
BEDROCK_SONNET_MODEL: str = "global.anthropic.claude-sonnet-4-6-v1"
BEDROCK_HAIKU_MODEL:  str = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
BEDROCK_OPUS_MODEL:   str = "global.anthropic.claude-opus-4-6-v1"
```

There's **no `DEFAULT_MODEL`**. Every agent picks its own.

---

## Part 3 · Tour the Atelier (8 minutes, solo)

In the Atelier's left sidebar, work top to bottom:

### `/atelier/sessions`
The replay store. Seven sessions shipped: 3 Marco (opening / midpoint / capstone), 2 Anna (birthday / housewarming), 2 Theo (pour-over / return). You just watched `marco-opening-demo`. Keep it bookmarked.

### `/atelier/observatory`
Wide-angle dashboard. Look at the **Agent Status** card — five rows, model tags per row, live/idle indicators. Then the **Performance headlines** at the bottom. Note the P50 numbers for Sonnet vs Haiku agents.

### `/atelier/agents` (under UNDERSTAND)
Five specialist cards. **Stock Keeper has a "Your turn" pill** — that's the build. Note every card's model + temperature badge. No row is normalized.

### `/atelier/tools`
Ten tool cards. Three are in dashed **exercise** treatment: `floor_check`, `restock_shelf`, `running_low`. The discovery card at the bottom surfaces `floor_check` as the top match for *"check stock at the Brooklyn warehouse"* — but tagged "○ Pending implementation."

### `/atelier/routing`
Three routing patterns. **Dispatcher** (Pattern III) is the active one in the Boutique — pattern-matched, deterministic, no LLM call. Agents-as-Tools (Pattern II) and Graph (Pattern I) are documented for reference.

### `/atelier/memory`
STM + LTM orbit. Marco's LTM preferences are visible (minimal, warm tones, linen). This is what makes Turn 1 return Marco-shaped results.

### `/atelier/performance`
Per-agent latency bars. Sonnet agents sit at ~1000-1500 ms. Haiku agents sit at ~100-250 ms. **An order of magnitude apart.** Stock Keeper's bar shows "—" with a "pending" tag.

---

## Part 4 · Swap a model (5 minutes, solo hands-on)

Before you start the real build, a quick experiment to make the model-mix lesson tactile.

Open `blaize-bazaar/backend/agents/pricing_agent.py`. Find the `build_pricing_agent()` factory:

```python
return Agent(
    model=BedrockModel(
        model_id=settings.BEDROCK_HAIKU_MODEL,  # ← this
        max_tokens=2048,
        temperature=0.1,
    ),
    ...
)
```

**Change `BEDROCK_HAIKU_MODEL` to `BEDROCK_SONNET_MODEL`. Save.** Uvicorn will reload.

Click Marco's Turn 3 pill again in the Boutique: *"What's the price range for linen shirts?"*

Open the Atelier Performance page. Value Analyst's latency bar just jumped from ~150 ms to ~1200 ms. **Almost 10× slower** for a question that wanted a number.

**Now swap it back.** Save. Latency drops back. You've just made the architectural argument for Haiku on a reporting agent tangible — you felt the cost of the wrong choice.

---

## What's next

You've observed the whole system. You've felt the model-mix lesson in your hands. Time to close Marco's gap.

Next: [Module 2 · Understand](20-module2-understand.en.md)
