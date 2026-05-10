---
inclusion: always
---

# Pellier — Storefront Conventions

This file covers design, UX, copy, and auth conventions specific to the customer-facing storefront. Code conventions live in `coding-standards.md`. Project context and module structure live in `project.md`. Tech stack lives in `tech.md`. Database patterns live in `database.md`.

---

## Customer-facing copy rules

These apply to every user-facing string in the storefront UI. They do **not** apply to workshop lab guides, instructor notes, or code comments.

- **No emojis** anywhere in customer copy
- **No em dashes** — use regular hyphens
- **No tech jargon** — these words are forbidden in customer-facing text:
  - "AI", "search" (as a noun for the feature), "intelligent", "smart", "agent", "LLM", "vector", "embedding"
- **Instead use**: "Ask Pellier", "concierge", "the storefront", "curated"
- Technical references (embeddings, agents, latency, Aurora, pgvector, AgentCore) appear only in **10px monospace footnotes** that engineers can find if they lean in
- Warm, editorial, catalog-style voice. Read like Aesop or Toast, not like Best Buy

Examples:
- ✗ "AI-powered search finds products matching your intent"
- ✓ "Tell Pellier what you're looking for. Watch the pieces find you."

- ✗ "Our smart recommendation engine picked this"
- ✓ "Picked because you mentioned warm evenings"

---

## Design tokens

### Color palette (CSS custom properties)

Warm palette only. No blue, grey, slate, navy, or cold tones.

- `--cream: #fbf4e8` — primary background
- `--ink: #2d1810` — primary text, dark actions
- `--accent: #c44536` — terracotta accent (CTAs, pulse dots, links)
- `--dusk: #3d2518` — dark surfaces, hover states
- `--cream-warm: #f5e8d3` — secondary background, hover fills
- `--ink-soft: #6b4a35` — secondary text
- `--ink-quiet: #a68668` — tertiary text, metadata, 10px footnotes

### Typography

- **Inter** for UI body, buttons, navigation, metadata
- **Fraunces** (italic-capable) for display type, product names, hero headlines, logo wordmark
- Italic Fraunces carries the "editorial" voice; use it for intent queries, section headlines, story titles

### Animations and timings

- `pulse-dot` — 2s infinite (terracotta status indicators)
- `think-dot` — 1.4s staggered (loading states)
- `slow-zoom` — 14s alternate, scale 1.02 → 1.08 (hero stage Ken Burns)
- `intent-reveal` — 0.8s blur-in (intent query text transitions)
- `cascade-in` — 0.5s staggered (sequential content reveal)
- `concierge-glow` — 3s soft pulse (concierge CTA idle state)
- `fade-slide-up` — 0.6s (banner reveals, curated banner entrance)
- **`parallax-card`** — this is the one to get right:
  - Start: `opacity: 0; transform: translateY(56px) scale(0.975)`
  - End: `opacity: 1; transform: translateY(0) scale(1)`
  - Transition: `opacity 1100ms cubic-bezier(0.16, 1, 0.3, 1), transform 1200ms cubic-bezier(0.16, 1, 0.3, 1)` (ease-out-expo for luxurious deceleration)
  - Stagger: 220ms between cards in the same row
  - IntersectionObserver threshold 0.05, rootMargin `'0px 0px -5% 0px'`
  - `will-change: opacity, transform`
  - Triggers once per card per page view

---

## Top navigation

Exactly five items + centered wordmark + right actions. Sticky on scroll.

- **Home** (current page, ink-highlighted)
- **Shop**
- **Storyboard** (editorial hub: mood films, vision boards, behind-the-scenes)
- **Discover** (personalized curation landing)
- Centered "Pellier" wordmark with circular B logo
- Right: "Ask Pellier" text link (hidden on mobile), Account button, Bag icon with live count badge

About content lives in the footer, not the top nav. Old nav items (Shop/Journal/About) from earlier prototypes should not be referenced.

---

## Account button state

- Signed out: generic account icon + "Account" label
- Signed in: same icon + "Hi, [Name]" using the `given_name` claim from verified Cognito JWT

---

## Sign-in strip vs curated banner

Mutually exclusive band below the hero stage:

- **Sign-in strip** (signed out): warm cream-warm gradient, B mark with pulse dot, "PERSONALIZED VISIONS" eyebrow, italic Fraunces headline "Sign in and watch Pellier tailor the storefront to you.", "Sign in for personalized visions" CTA, "Not now" dismiss (sessionStorage)
- **Curated banner** (signed in with saved preferences): terracotta gradient, pulse dot, "CURATED FOR YOU" label, "Tailored to your preferences, [Name]. [pref1] · [pref2] · [pref3]", "Adjust preferences" link

Neither appears if the user is signed in without preferences yet (in that state, the preferences modal is auto-opened instead).

---

## The 8 rotating intents

Hero stage cycles through these every 7.5 seconds. Rotation pauses on hover. Ticker chips are clickable. Search input keyword-matches to jump.

1. "something for long summer walks" → Italian Linen Camp Shirt
2. "a thoughtful gift for someone who runs" → **productOverride**: Featherweight Trail Runner, $168, 4.9 rating, athletic running shoe image
3. "something to wear for warm evenings out" → Sundress in Washed Linen
4. "pieces that travel well" → Signature Straw Tote
5. "something for slow Sunday mornings" → Ceramic Tumbler Set
6. "a linen piece that earns its golden hour" → Sundress in Washed Linen (repeated — it fits)
7. "a cozy layer for cool summer nights" → Cashmere-Blend Cardigan
8. "something relaxed for weekend markets" → Relaxed Oxford Shirt

---

## The 9 showcase products (with preference tags)

Every product carries a `tags text[]` column populated from this mapping. Personalization sorts by count of overlapping tags with user preferences.

| Name | Brand | Color | Price | Tags |
|---|---|---|---|---|
| Italian Linen Camp Shirt | Pellier Editions | Sand | $128 | minimal, serene, classic, warm, neutral, everyday, slow, linen |
| Wide-Leg Linen Trousers | Pellier Editions | Terracotta | $98 | creative, bold, warm, earth, everyday, travel, linen |
| Signature Straw Tote | Pellier Editions | Natural | $68 | classic, serene, neutral, soft, travel, everyday, accessories |
| Relaxed Oxford Shirt | Pellier Editions | Warm Ivory | $88 | classic, minimal, neutral, soft, everyday, work, linen |
| Sundress in Washed Linen | Pellier Editions | Golden Ochre | $148 | creative, bold, warm, earth, evening, dresses, linen |
| Leather Slide Sandal | Pellier Editions | Chestnut | $112 | minimal, classic, earth, warm, everyday, travel, footwear |
| Cashmere-Blend Cardigan | Pellier Editions | Driftwood | $158 | minimal, serene, classic, neutral, earth, slow, evening, outerwear |
| Ceramic Tumbler Set | Pellier Home | 4pc Set | $52 | minimal, serene, creative, neutral, soft, slow, home |
| Linen Utility Jacket | Pellier Editions | Faded Olive | $178 | adventurous, creative, earth, neutral, outdoor, travel, outerwear |

These 9 products are the hero/featured set surfaced in the storefront grid. The full ~444-product catalog (from the catalog-enrichment spec) also carries tags and powers search.

---

## Auth UX (Cognito + AgentCore Identity)

### Auth modal (entry point)

Triggered by sign-in strip CTA, Account button, or `/signin` route.

- Centered cream rounded-3xl card, glass backdrop
- Header: B mark + "Welcome to Pellier" + "Sign in for a storefront built for you"
- Body headline: "PERSONALIZED VISIONS" eyebrow + italic "Let the storefront find you."
- Three buttons redirect to Cognito Hosted UI with IdP param:
  1. "Continue with Google" → `?identity_provider=Google`
  2. "Continue with Apple" → `?identity_provider=SignInWithApple`
  3. "Continue with email" → no IdP param (native Cognito)
- Disclaimer: "By continuing, you agree to our terms and privacy policy."
- Footer strip: "Secured by AgentCore Identity" in 10px mono + shield icon + "v2.4" version

### Preferences onboarding modal

Auto-opens after first successful auth if `/api/auth/me` returns `preferences === null`.

- Header: B mark + "A quick tune-up" + "Takes about 20 seconds. You can change these anytime."
- Body headline: italic "What moves you?" + "Pick what resonates. Pellier will take it from here."
- Four preference groups, all multi-select chips:

**Group 1 — Your overall vibe** (6 cards with 2-word descriptors):
- Minimal (Quiet · Considered)
- Bold (Statement · Saturated)
- Serene (Soft · Calming)
- Adventurous (Outdoor · Durable)
- Creative (Layered · Textured)
- Classic (Timeless · Refined)

**Group 2 — Favorite colors** (5 pill chips with gradient swatches):
- Warm tones (terracotta → amber)
- Neutrals (sand → ink-soft)
- Earth (ink-soft → dusk)
- Soft pastels (cream-warm → cream)
- Deep & moody (ink → near-black)

**Group 3 — Where you wear it** (6 pill chips):
- Everyday, Travel, Evenings out, Outdoor, Slow mornings, Work

**Group 4 — Categories you love** (6 pill chips):
- Linen, Footwear, Outerwear, Accessories, Home, Dresses

**Submit row:**
- "Skip for now" secondary link
- "Save and see my storefront" primary CTA (ink, dusk on hover)

**Footer strip:** "Preferences stored with AgentCore Memory" in 10px mono with shield icon

### Selected chip visual state

- `background: #2d1810` (ink fill)
- `color: #fbf4e8` (cream text)
- `border-color: #2d1810`

---

## Global UI elements

- **⌘K command pill** (bottom-right corner): compact dusk pill, small B mark, "Ask Pellier" label, styled `⌘K` keycap
- ⌘K / Ctrl+K globally opens/closes the concierge modal
- Escape closes any open modal
- All modals: centered cream rounded-3xl cards with glass backdrop-blur backgrounds

---

## From the Storyboard (editorial teaser grid)

Three-card grid below the product sections. Never a single-card editorial block (that was an earlier prototype).

- MOOD FILM · Vol. 12 · Summer · "A summer worth slowing for."
- VISION BOARD · Vol. 11 · The Makers · "The last clay studio in Ojai."
- BEHIND THE SCENES · Vol. 10 · The Edit · "How we chose this season."

Each card: editorial image with golden wash, category badge, volume number, italic Fraunces title, 2–3 sentence excerpt, "Read the full vision ›" link in terracotta. Hover: image scales 1.05.

---

## Footer (5 columns)

1. Brand — logo + "Carefully curated goods from makers who care about craft"
2. Shop — New arrivals / Summer Edit / Gift guide / Sale
3. About — Our story / Makers we love / Sustainability / Press (moved here from top nav)
4. Service — Shipping / Returns / Contact / FAQ
5. Storyboard newsletter — "A weekly letter on craft, makers, and a slower kind of shopping" + email signup

Bottom strip: © + Privacy / Terms / Accessibility.
