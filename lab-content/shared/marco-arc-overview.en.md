# Marco's arc — the workshop's narrative spine

*Both lab guides reference this file. Same story, two formats — the Builder's Session wires the bare minimum for Marco's gap to close; the Workshop wires it in full plus Experience Guide.*

---

## Who is Marco?

Marco is the protagonist of the Blaize Bazaar workshop. He's a returning customer — natural fabrics, linen, travel-ready, warm tones. His signals are clear and the system remembers him. Anna and Theo appear in the Sessions list as evidence of range, but they don't drive instructional checkpoints. **Marco is the only protagonist in both delivery formats.**

## The 5-minute opening demo

Participants drive the demo themselves by clicking Marco's four hero pills in order. The pills are pre-configured in the Boutique to match Marco's exact workshop sequence. The presenter narrates the beats out loud — never clicks.

| Turn | Marco clicks | Route | Agent (model · temp) | Tool | Outcome |
|---|---|---|---|---|---|
| 1 | "What linen do you have for 10 days in Goa?" | Style Advisor | Sonnet 4.6 · 0.4 | `find_pieces` | 3 linen pieces with editorial voice |
| 2 | "What would go with the Pellier shirt?" | Curator *(with `the-packing-list` loaded)* | Sonnet 4.6 · 0.4 | `style_match` | Complementary pieces; voice mentions packability |
| 3 | "What's the price range for linen shirts?" | Value Analyst | Haiku 4.5 · 0.1 | `price_intelligence` | "$88 to $285, median $148" — sub-200ms |
| 4 | **"Is the Pellier shirt at the Brooklyn warehouse?"** | **Stock Keeper (stubbed)** | — | — | **Graceful non-answer** — the gap you're about to close |

Marco closes with *"I'll come back when I'm ready to commit."* The gap isn't a bug — it's a build. The Atelier shows the routing fall-through honestly.

## The 3-minute midpoint checkpoint

After participants wire the Stock Keeper agent (and at minimum `floor_check`), they re-click Marco's Turn 4 pill. The same question now returns:

> "Yes — Brooklyn (BK-01) has 8 of the Pellier Linen Shirt in ecru on the floor right now. Also 4 at Austin (ATX-02) and 12 at Portland (PDX-01). Ship window from Brooklyn to your zip is 1–2 business days."

The code behind that response is participant-authored. The Boutique didn't change. The Atelier's **Routing** page connects the dotted line. The Agents page drops the "Your turn" pill on Stock Keeper. The Performance page shows a new latency bar at ~150 ms p50 on Haiku 4.5.

That's the workshop's core teaching moment: **capability is composable**. You wrote a tool; the tool changed the system's answer.

## The 5-minute capstone

Participants click through the **Marco capstone** — a 5-turn sequence that invokes every specialist:

1. Curator on Sonnet — "What pairs with the Ecru overshirt?" (with `the-packing-list` loaded)
2. Value Analyst on Haiku — "What's the cheapest piece that goes with it?"
3. Stock Keeper on Haiku — "Is it in stock at Brooklyn?" *(the tool participants wrote)*
4. Experience Guide on Sonnet — "What's the return window?" *(workshop format only; pre-applied in Builder's)*
5. Style Advisor on Sonnet — "Show me one more linen piece under $100."

The presenter narrates each turn's agent / tool / model live so the per-agent variation lands. The Atelier's **Performance** page visualizes it: Sonnet turns at ~1200 ms, Haiku turns at ~150 ms. An order of magnitude apart. That's the capstone payoff — the architectural lesson, made visible.

## Replay any part of the arc

Every turn in the arc is captured as an Atelier Session fixture:

- `/atelier/sessions/marco-opening-demo` — the 4-turn opener with the Turn 4 gap
- `/atelier/sessions/marco-midpoint-checkpoint` — the "now it works" payoff
- `/atelier/sessions/marco-capstone` — the full 5-turn journey

Anna and Theo each have 2 supporting sessions in the same list. Theo's `theo-ceramics-return` session models the Experience Guide stub gap for the Workshop format.
