# Marco's arc — the workshop's narrative spine

*Both lab guides reference this file. Same story, two formats — the Builder's Session wires `floor_check` plus AgentCore STM verify and Runtime invoke (pre-launched); the Workshop wires specialists and production patterns in full.*

---

## Who is Marco?

Marco is the protagonist of the Pellier workshop. He's a returning customer — natural fabrics, linen, travel-ready, warm tones. His signals are clear and the system remembers him. Anna and Theo appear in the Sessions list as evidence of range, but they don't drive instructional checkpoints. **Marco is the only protagonist in both delivery formats.**

## The 5-minute opening demo

Participants drive the demo themselves by clicking Marco's hero pills **in fixture order**. The Boutique pills are **`personaCurations` · `PERSONA_HERO_PILLS.marco`** (must match **`session-marco-opening-demo.json`** and **`marco-capstone`** as referenced in the labs). Presenter narrates; participants click.

Where we say **Hadley shirt**, that's the storefront line for **Pellier Linen Shirt in ecru** — same SKU, two names participants will hear.

The **opening fixture** spans **four** shopper turns (turns 1–4) plus Marco's closing line; hero pill five (*Ecru overshirt*) is the **capstone** opening turn — see **`marco-capstone`**.

| Turn | Marco clicks | Route | Agent (model · temp) | Tool | Outcome |
|---|---|---|---|---|---|
| 1 | "What linen do you have for 10 days in Goa?" | Style Advisor | Opus 4.6 · 0.4 | `find_pieces` | Three linen pieces; editorial voice |
| 2 | "What would go with the Hadley shirt?" | Curator *(with `the-packing-list` loaded)* | Opus 4.6 · 0.4 | `style_match` | Companion pieces; cosine from Hadley / Pellier linen |
| 3 | "What's the price range for linen shirts?" | Value Analyst | Haiku 4.5 · 0.1 | `price_intelligence` | Numeric band — sub-200 ms class |
| 4 | **"Is the Hadley shirt at the Brooklyn warehouse?"** | **Fall-through · `floor_check` stubbed** | — | — | **Graceful non-answer** — Builder's Session / workshop build |

Marco closes the opening replay with *"I'll come back when I'm ready to commit."* The gap isn't a bug — it's a build. The Atelier shows the routing fall-through honestly.

## The 3-minute midpoint checkpoint

After participants wire **`floor_check`**, they re-click Turn 4 — *"Is the Hadley shirt at the Brooklyn warehouse?"* The payoff line matches **`session-marco-midpoint-checkpoint.json`** (Brooklyn counts for **Hadley / Pellier Linen Shirt in ecru**).

The Atelier **Routing** page connects the dotted line. **Agents** drops the exercise pill on Stock Keeper when shipped. **Performance** shows Haiku **~150 ms** p50 on stock.

## The 5-minute capstone

**`marco-capstone`** — five turns, every specialist:

1. Curator on **Opus** — "What pairs with the Ecru overshirt?" · `style_match`
2. Value Analyst on **Haiku** — "What's the cheapest piece that goes with it?" · `price_intelligence`
3. Stock Keeper on **Haiku** — "Is it in stock at Brooklyn?" · **`floor_check`** *(participant-authored)*
4. Experience Guide on **Opus** — "What's the return window?" · `returns_and_care` *(workshop build in long format; often pre-applied in Builder's)*
5. Style Advisor on **Opus** — "Show me one more linen piece under $100." · `find_pieces`

Narrate **Opus (~1–1.5 s)** vs **Haiku (~100–250 ms)** — order of magnitude, same Architecture / Performance surfaces.

## Replay any part of the arc

Every turn ships as an Atelier Session fixture:

- **`/atelier/sessions/marco-opening-demo`** — turns 1–4 + Marco's closing line (Turn 4 gap)
- **`/atelier/sessions/marco-midpoint-checkpoint`** — Hadley warehouse answer after `floor_check` ships
- **`/atelier/sessions/marco-capstone`** — full five-specialist ladder

Anna and Theo each have two supporting sessions. Theo's ceramics return models the Experience Guide arc in the Workshop.

---

## Where to next

Marco anchored pgvector semantic search as the workshop's first Aurora capability. Anna and Theo stack hybrid + system-of-record on top — see [anna-arc-overview.en.md](./anna-arc-overview.en.md), [theo-arc-overview.en.md](./theo-arc-overview.en.md), [aurora-capabilities-arc.en.md](./aurora-capabilities-arc.en.md).
