---
title: Opening Talk (10 min)
weight: 20
---

**Time budget: 10 minutes — presenter driven**

This page is the instructor's outline. Participants follow along from their screens.

## Beats (with approximate timing)

### 0:00–0:02 · What Blaize Bazaar is
- A working boutique with a working agent stack behind it.
- Two surfaces: Boutique (shoppers) and Atelier (operators).
- The Atelier is the teaching surface; the Boutique is the proof.

### 0:02–0:04 · The per-agent model mix
- Five specialists, three model configurations.
- **Sonnet 4.6 at 0.4** — Style Advisor, Curator (editorial voice).
- **Haiku 4.5 at 0.1** — Value Analyst (reports numbers, fast).
- **Haiku 4.5 at 0.0** — Stock Keeper (pure factual, tightest config).
- **Sonnet 4.6 at 0.2** — Experience Guide (warm but steady).
- **Haiku 4.5 at 0.0** — Orchestrator + SkillRouter (classification).
- Model selection is an architectural decision. Variation is the lesson.

### 0:04–0:09 · Marco drives the demo
Participants click Marco's four hero pills **in order**. Presenter narrates each beat live.

| Pill | Narrate |
|---|---|
| 1 — "What linen do you have for 10 days in Goa?" | **Style Advisor on Sonnet 4.6 at 0.4.** Editorial voice. 3 pieces. ~1.3s. |
| 2 — "What would go with the Pellier shirt?" | **Curator on Sonnet with `the-packing-list` skill loaded.** Voice mentions packability. ~1.4s. |
| 3 — "What's the price range for linen shirts?" | **Value Analyst on Haiku 4.5 at 0.1.** Numbers only. Sub-200ms. |
| 4 — "Is the Pellier shirt at the Brooklyn warehouse?" | **Stock Keeper is in stub state.** Graceful non-answer. **This is the build.** |

### 0:09–0:10 · What they'll build in 25 minutes
- Author Stock Keeper's system prompt.
- Wire `floor_check` — the tool that closes Marco's gap.
- Run pytest → green.
- Re-click Marco's Turn 4 pill → real Brooklyn warehouse answer.

That's the hour's core. `restock_shelf`, `running_low`, and Experience Guide come pre-wired — you'll see them in the Atelier but won't build them.

Next: [Module 1 · Observe (5 min)](10-module1-observe.en.md)
