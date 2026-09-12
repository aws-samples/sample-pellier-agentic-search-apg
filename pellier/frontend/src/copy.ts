// Pellier frontend user-facing copy.
//
// This module is the single source of truth for every customer-facing string
// authored by the storefront UI. Announcement bar, nav, hero intents,
// reasoning chips, banners, modals, footer, and error strings all live here.
//
// All strings in this module must satisfy the storefront copy rules:
//   - no emoji
//   - no em dashes (use regular hyphens)
//   - none of the forbidden words listed in storefront.md
//
// The companion scanner lives at src/__tests__/copy.test.ts (or .mjs).

// Announcement bar (Requirement 1.1.2) - rendered verbatim.
export const ANNOUNCEMENT =
  "Complimentary shipping over $150 · Returns within 30 days · Resort Edit No. 06 is now live";

export interface LiveFloorFinding {
  /** Uppercase sans label that leads the copy. */
  verb?: string;
  /** Body text. */
  text: string;
  /** Mono trace stamp on the right. */
  trace?: string;
}

export const EDITORIAL_FLOOR_NOTES: LiveFloorFinding[] = [
  {
    verb: "The house edit",
    text: "Linen, leather, ceramic, and small useful objects chosen for unhurried weekends.",
  },
  {
    verb: "Travel edit",
    text: "Packable linen, leather carry, and sun-ready accessories for long weekends and warm-weather escapes.",
  },
  {
    verb: "Gift service",
    text: "Candles, ceramics, and wrapped objects for housewarmings, milestones, and just-because notes.",
  },
  {
    verb: "Home rituals",
    text: "Stoneware, soft linen, and quiet light for the objects you reach for every day.",
  },
  {
    verb: "Concierge",
    text: "Ask for a packing list, a gift shortlist, or a home ritual and Pellier will build the edit with you.",
  },
  {
    verb: "Service",
    text: "Careful packaging, complimentary shipping over $150, and clear 30-day returns.",
  },
];

export const PAGE_TITLE = "Pellier Resort Edit";

// Top nav (Requirement 1.2.1)
export const NAV = {
  HOME: "Home",
  SHOP: "Shop",
  STORYBOARD: "Storyboard",
  STORIES: "Stories",
  DISCOVER: "Discover",
  ABOUT: "About",
  ACCOUNT: "Account",
  ASK_PELLIER: "Ask Pellier",
  WORDMARK: "Pellier",
  /** The inspection surface. Renamed from "Pellier Labs": participants read
   *  "Labs" as a fifth lab they still owed, on top of the four required ones. */
  OBSERVATORY: "Pellier Observatory",
  /** Sits beside every entry point into the Observatory. The surface is worth
   *  exploring and is not required to finish the workshop, and a participant
   *  watching the clock deserves to know which of those is true before they
   *  click rather than after. */
  OBSERVATORY_OPTIONAL: "Optional",
  /** The clienteling desk. Staff-facing, so it sits beside the Observatory
   *  rather than among the shopper destinations. Unlike the Observatory it
   *  carries no "Optional" badge: it is a working surface, not an inspection
   *  one. */
  OPERATOR: "Pellier Operator",
} as const;

// Account button labels (Requirement 1.2.2, 1.2.3)
export const ACCOUNT_LABEL_SIGNED_OUT = "Account";
export const accountLabelSignedIn = (givenName: string): string =>
  `Hi, ${givenName}`;

// Hero breadcrumb + curated chip (Requirement 1.3.4, 1.3.10)
export const HERO_BREADCRUMB = "Someone just asked";
export const CURATED_FOR_YOU_CHIP = "Curated for you";
export const SEARCH_PILL_PLACEHOLDER =
  "Tell Pellier what you're looking for...";

// Hero headline block that sits above the rotating stage.
export const HERO_HEADLINE = {
  EYEBROW: "Resort Edit \u00b7 No. 06",
  TITLE_TOP: "Pellier",
  TITLE_BOTTOM: "Resort Edit",
  SUBHEADLINE: "Tell Pellier what you're looking for. Watch the pieces find you.",
} as const;

export const PELLIER_HERO_SIGNED_OUT = {
  LINE_1: "Choose a shopper profile to begin.",
  LINE_2: "Pellier will tailor the floor around that visit.",
} as const;

/**
 * Concierge panel that sits beside the hero image.
 *
 * `PROFILES` descriptors are one line each, in the same voice as the
 * `blurb` field on `data/personas.ts`. The concierge action requires one of
 * these profiles because every guided request is ranked for that shopper.
 */
export const HERO_CONCIERGE = {
  EYEBROW: "Welcome to Pellier",
  TITLE: "Choose who enters Pellier.",
  HELPER:
    "Get a more personal experience with recommendations tailored to their style.",
  ASK_ACTION: "Ask Pellier",
  CHOOSE_HELPER: "Choose Marco, Anna, or Theo to begin.",
  /**
   * Persona is scenario, not identity. This distinction is the workshop's
   * central lesson, so it is stated where the choice is made rather than left
   * for a lab page to explain later.
   *
   * `/api/persona/switch` has no authentication dependency: it records a
   * client-declared presentation choice. Governed actions authenticate through
   * Cognito, and Cedar and Row-Level Security evaluate that verified principal
   * — never this click. A participant who reads the selector as "I am now
   * Theo" would draw exactly the wrong conclusion from a later DENY.
   */
  IDENTITY_BOUNDARY:
    "Choosing Marco, Anna, or Theo changes the shopping scenario. It does not " +
    "sign you in as that customer. Actions on an account use a separately " +
    "verified sign-in.",
  /**
   * One line per profile, and each must match that persona's actual
   * curation. The mockup carried generic luxury copy which contradicted the
   * seeded profiles: Anna is the gift-giver, so a descriptor that never
   * mentions giving teaches the wrong expectation before the floor reranks.
   *
   * Aligned with the existing authoritative sources:
   *   role_tag           (Aurora)                Travel / gifting / slow-living materials
   *   curatedHeadline    (personaCurations.ts)   Pieces that travel. / Gifts, thoughtfully matched. / Quiet pieces, lived-in.
   *   weekend edit brow  (personaCurations.ts)   The Travel Edit / The Gift Edit / The Slow Edit
   */
  PROFILES: {
    marco: "Travel, utility, leather, linen.",
    anna: "Gifting, ceremony, silk, glass.",
    theo: "Slow living, craft, stoneware, natural materials.",
  },
} as const;

/**
 * Editorial hero statement. One accent word per line is rendered in the
 * burgundy italic; `ACCENT` must appear verbatim inside `HEADLINE` or the
 * headline renders unaccented rather than mis-split.
 *
 * Persona headlines reuse the approved `curatedHeadline` vocabulary from
 * `data/personaCurations.ts` so the storefront speaks one voice.
 */
export const HERO_STATEMENT = {
  CTA: "Shop the collection",
  fresh: {
    HEADLINE: "Pieces that travel well.",
    ACCENT: "travel",
  },
  marco: {
    HEADLINE: "Pieces that travel.",
    ACCENT: "travel",
  },
  anna: {
    HEADLINE: "Gifts, thoughtfully matched.",
    ACCENT: "thoughtfully",
  },
  theo: {
    HEADLINE: "Quiet pieces, lived-in.",
    ACCENT: "lived-in",
  },
} as const;

/**
 * Mood rail under the hero. Each tile browses the floor: the collections
 * are an editorial entry point into the same catalog, not four separate
 * routes that do not exist.
 */
export const COLLECTIONS = {
  EYEBROW: "Curated collections",
  TITLE: "Explore by mood",
  VIEW_ALL: "View all",
  ITEMS: [
    {
      title: "Weekend Away",
      description: "Effortless pieces for unhurried escapes.",
      image: "/products/landing-collection-weekend-away.png",
      alt: "Leather weekender on travertine beside folded linen",
      tone: "light",
    },
    {
      title: "At Home",
      description: "Objects that elevate the everyday.",
      image: "/products/landing-collection-at-home.png",
      alt: "Amber glass candle on a travertine slab with a wooden bowl",
      tone: "light",
    },
    {
      title: "Warm Evenings",
      description: "Layers and textures for golden hours.",
      image: "/products/landing-collection-warm-evenings.png",
      alt: "Linen shirt and open-knit layer in late afternoon light",
      tone: "light",
    },
    {
      title: "Gifting",
      description: "Considered pieces they will keep.",
      image: "/products/landing-collection-gifting.png",
      alt: "Wrapped gift box tied with a burgundy ribbon",
      tone: "dark",
    },
  ],
} as const;

/**
 * The storefront's bridge into Pellier Observatory. Every claim here is one a
 * participant can open and check, which is the point of the module: it
 * earns the link rather than decorating it. Do not add a claim without a
 * surface that proves it.
 */
export const PELLIER_APPROACH = {
  EYEBROW: "The Pellier approach",
  TITLE_TOP: "Considered pieces.",
  TITLE_BOTTOM: "Clear reasons.",
  ACCENT: "reasons",
  BODY:
    "A little context makes choosing easier. Explore the pieces, understand the details, and find what feels right for you.",
  CTA_LABEL: "Discover Pellier Observatory",
  CTA_HREF: "/observatory",
  IMAGE: "/products/landing-approach-atelier.png",
  IMAGE_ALT: "A maker stitching a leather bag by hand at the bench",
  PILLARS: [
    {
      title: "A reason for every recommendation",
      body: "Explore the catalog details and sources behind the pieces we suggest.",
      linkLabel: "See the evidence",
      href: "/observatory",
    },
    {
      title: "Personal, on your terms",
      body: "Start with your taste, your plans, or a gift in mind. Choose what you share with Pellier.",
      linkLabel: "Meet Pellier",
      href: "/about",
    },
    {
      title: "Details worth a closer look",
      body: "Linen, leather, stoneware. Compare the materials, price, and availability of each piece.",
      linkLabel: "Explore the collection",
      href: "/#shop",
    },
    {
      title: "Pieces for everyday rituals",
      body: "A slower morning, a weekend away, a thoughtful gift. Find an edit for the moment.",
      linkLabel: "Explore the stories",
      href: "/storyboard",
    },
  ],
} as const;

/**
 * Service strip above the footer. The shipping and returns numbers match
 * `FOOTER.BOTTOM_STRIP.SERVICE_ITEMS`; change both together.
 */
export const SERVICE_STRIP = {
  ITEMS: [
    { title: "Complimentary shipping", body: "On orders over $150" },
    { title: "Easy returns", body: "30-day returns and exchanges" },
    { title: "Thoughtful gift wrapping", body: "Complimentary on all orders" },
    { title: "Concierge support", body: "We are here to help" },
  ],
  LABS: {
    title: "Pellier Observatory",
    body: "Grounded intelligence behind every recommendation",
    href: "/observatory",
  },
} as const;

/**
 * Product detail page (`/product/:id`).
 *
 * Every claim here is either structural chrome or a label over a value the
 * page actually read. The availability copy is deliberately split three
 * ways — reading / read / not read — because "not read" must never be
 * rendered as "out of stock". `ON_HAND_LABEL` and `WAREHOUSE_CAPTION` name
 * their source column so a shopper-facing number stays traceable to Aurora.
 */
export const PRODUCT_DETAIL = {
  BREADCRUMB_ROOT: "Pellier",
  ADD_TO_BAG: "Add to bag",
  ASK_LABEL: "Ask Pellier about this piece",
  askQuestion: (name: string): string => `Tell me about the ${name}.`,
  DESCRIPTION_HEADING: "About this piece",
  DESCRIPTION_UNAVAILABLE:
    "Notes for this piece could not be read just now.",
  AVAILABILITY_HEADING: "Availability",
  AVAILABILITY_SOURCE: "Checked just now",
  AVAILABILITY_READING: "Reading inventory",
  AVAILABILITY_UNAVAILABLE:
    "Inventory was not read for this piece, so no stock figure is shown.",
  ON_HAND_LABEL: "units on hand",
  WAREHOUSE_CAPTION:
    "Counts by warehouse at the moment this page was read.",
  WAREHOUSE_EMPTY: "No warehouse holds this piece right now.",
  shipWindow: (min: number, max: number): string =>
    min === max ? `Ships in ${min} days` : `Ships in ${min} to ${max} days`,
  WHY_HEADING: "Why this piece",
  SIGNALS_HEADING: "Catalog signals",
  MORE_HEADING: "More from this edit",
  NOT_FOUND_TITLE: "This piece is not in the edit",
  NOT_FOUND_BODY:
    "The catalog has no piece with that number. Browse the current edit instead.",
  NOT_FOUND_ACTION: "Back to the floor",
} as const;

// Product grid section header that reveals on scroll (parallax).
export const PRODUCT_GRID_HEADER = {
  EYEBROW: "Picked for resort season",
  TITLE: "Things worth discovering",
  SORT_LABEL: "Sort: Most loved",
} as const;

// Label rendered to the left of the intent ticker pills under the hero frame.
export const OTHERS_ARE_ASKING_LABEL = "Others are asking";

// Intent shape used by HeroStage.
export interface IntentProductRef {
  name: string;
}
export interface IntentProductOverride {
  name: string;
  brand: string;
  color: string;
  price: number;
  rating: number;
  reviewCount: number;
  /** Pre-formatted review-count display (e.g. "1.4k reviews"); overrides reviewCount at render time when present. */
  reviews?: string;
  imageUrl: string;
}
export interface Intent {
  id: number;
  query: string;
  matchedOn: string[];
  /** Per-intent latency stamp rendered in IntentInfoCard (Req 1.3.4). e.g. "340 ms". */
  latency: string;
  productRef?: IntentProductRef;
  productOverride?: IntentProductOverride;
}

// The 8 rotating intents (Requirement 1.3.1, storefront.md). Intent 2 carries
// a productOverride for the Cloudform Studio Runner.
export const INTENTS: Intent[] = [
  {
    id: 1,
    query: "something for long summer walks",
    matchedOn: ["linen", "warm", "everyday"],
    latency: "340 ms",
    productRef: { name: "Italian Linen Camp Shirt" },
  },
  {
    id: 2,
    query: "a thoughtful gift for someone who runs",
    matchedOn: ["athletic", "footwear", "gift"],
    latency: "412 ms",
    productOverride: {
      name: "Cloudform Studio Runner",
      brand: "Pellier Editions",
      color: "Ember \u00b7 9.5",
      price: 168,
      rating: 4.9,
      reviewCount: 1400,
      reviews: "1.4k reviews",
      imageUrl:
        "https://images.unsplash.com/photo-1469395446868-fb6a048d5ca3?w=1600&q=85",
    },
  },
  {
    id: 3,
    query: "something to wear for warm evenings out",
    matchedOn: ["evening", "warm", "dresses"],
    latency: "298 ms",
    productRef: { name: "Hadley Linen Shirt" },
  },
  {
    id: 4,
    query: "pieces that travel well",
    matchedOn: ["travel", "accessories", "neutral"],
    latency: "325 ms",
    productRef: { name: "Canvas Dopp Kit" },
  },
  {
    id: 5,
    query: "something for slow Sunday mornings",
    matchedOn: ["slow", "soft", "home"],
    latency: "367 ms",
    productRef: { name: "Stoneware Pour-Over Set" },
  },
  {
    id: 6,
    query: "a linen piece that earns its golden hour",
    matchedOn: ["linen", "evening", "warm"],
    latency: "288 ms",
    productRef: { name: "Hadley Linen Shirt" },
  },
  {
    id: 7,
    query: "a cozy layer for cool summer nights",
    matchedOn: ["outerwear", "evening", "slow"],
    latency: "315 ms",
    productRef: { name: "Linen Overshirt" },
  },
  {
    id: 8,
    query: "something relaxed for weekend markets",
    matchedOn: ["everyday", "linen", "classic"],
    latency: "302 ms",
    productRef: { name: "Cotton-Linen Crew Tee" },
  },
];

// Sign-in strip (Requirement 1.4.1)
export const SIGN_IN_STRIP = {
  EYEBROW: "PERSONALIZED VISIONS",
  HEADLINE: "Sign in and watch Pellier tailor the storefront to you.",
  CTA: "Sign in for personalized visions",
  DISMISS: "Not now",
} as const;

// Curated banner (Requirement 1.4.3)
export const curatedHeadline = (
  givenName: string,
  prefs: [string, string, string],
): string =>
  `Tailored to your preferences, ${givenName}. ${prefs[0]} \u00b7 ${prefs[1]} \u00b7 ${prefs[2]}`;

export const CURATED_BANNER = {
  LABEL: "CURATED FOR YOU",
  ADJUST_LINK: "Adjust preferences",
  headline: curatedHeadline,
} as const;

// Live status strip (Requirement 1.5.1)
export const LIVE_STATUS =
  "Live inventory \u00b7 refreshed daily \u00b7 curated by hand";
// Pellier policy phrases rendered as plain labels on the right side of
// the live status strip (mock pellier_5.html parity).
export const SHIPPING = "Free shipping over $150";
export const RETURNS = "Ships within 1 to 2 days";
export const CONFIRMED_TOTALS = "Confirmed totals";

// Category chips (Requirement 1.5.3)
export const CATEGORY_CHIPS = [
  "All",
  "Linen",
  "Dresses",
  "Accessories",
  "Outerwear",
  "Footwear",
  "Home",
] as const;

// Refinement panel (Requirement 1.8.1)
export const REFINEMENT = {
  // Single-letter mark inside the brand circle. "P" matches the
  // header wordmark - the refinement chip and the header speak with
  // the same brand voice.
  B_MARK_PREFIX: "P",
  PROMPT: "Pellier here, want me to narrow this down?",
  CHIPS: [
    "Under $100",
    "Ships by Friday",
    "Gift-wrappable",
    "From smaller makers",
  ],
} as const;

// Reasoning chip copy (Requirement 1.7). The pricing style exposes its urgent
// clause separately so the UI can render it in terracotta.
export const reasoningPicked = (reason: string): string =>
  `Picked because ${reason}`;

export const reasoningMatched = (
  attr1: string,
  attr2: string,
  attr3: string,
): string => `Matched on: ${attr1} \u00b7 ${attr2} \u00b7 ${attr3}`;

export interface PricingReasoning {
  lead: string;
  urgent: string;
}
export const reasoningPricing = (
  amountBelow: number,
  unitsLeft: number,
): PricingReasoning => ({
  lead: `Price watch: $${amountBelow} below category average.`,
  urgent: `Only ${unitsLeft} left.`,
});

export const reasoningContext = (text: string): string => text;

export const REASONING = {
  picked: reasoningPicked,
  matched: reasoningMatched,
  pricing: reasoningPricing,
  context: reasoningContext,
  DEFAULT_CONTEXT: "Gift-ready: signature packaging, arrives tomorrow",
} as const;

// Storyboard teaser cards (Requirement 1.9.4)
//
// Each card composes to the eyebrow line
//   `{badge} \u00b7 {volume} \u00b7 {theme}` above the italic Fraunces title,
// followed by a 2-3 sentence excerpt and the terracotta `link`. See
// StoryboardTeaser.tsx for the rendering contract.
export interface StoryboardTeaser {
  badge: string;
  volume: string;
  theme: string;
  title: string;
  excerpt: string;
  link: string;
  imageUrl: string;
  imageAlt: string;
}
export const STORYBOARD_TEASERS: StoryboardTeaser[] = [
  {
    badge: "MOOD FILM",
    volume: "Vol. 12",
    theme: "Summer",
    title: "A summer worth slowing for.",
    excerpt:
      "Linen, ceramic, light that lingers. Three days in the hills with the pieces we kept reaching for.",
    link: "Read the notes \u203a",
    imageUrl: "/products/story-summer.png",
    imageAlt: "A folded stack of oatmeal linen shirt and trousers on a travertine ledge, a stem of dried wheat across it and a charcoal stoneware tumbler beside it, in raking afternoon light",
  },
  {
    badge: "VISION BOARD",
    volume: "Vol. 11",
    theme: "The Makers",
    title: "The last clay studio in Ojai.",
    excerpt:
      "One kiln, two hands, forty years of practice. A visit with the makers behind our ceramic line.",
    link: "Read the notes \u203a",
    imageUrl: "/products/story-makers.png",
    imageAlt: "A freshly thrown charcoal stoneware bowl resting on a potter's wheel with a wooden rib tool, olive-branch shadows on the plaster wall behind",
  },
  {
    badge: "BEHIND THE SCENES",
    volume: "Vol. 10",
    theme: "The Edit",
    title: "How we chose the Edit.",
    excerpt:
      "Nine pieces survived the cut. A quiet walk-through of the edit room conversations that got us here.",
    link: "Read the notes \u203a",
    imageUrl: "/products/story-edit.png",
    imageAlt: "Linen swatches in sage, oat, charcoal and warm white fanned across an oak table, with a folded linen shirt, a stoneware cup, wooden rings and tailor's shears",
  },
];

// Minimal Storyboard and Discover routes (Requirement 1.13)
export const STORYBOARD_PAGE_COMING_SOON =
  "Coming soon - the full editorial hub arrives with the next Edit.";
export const DISCOVER_PAGE_SIGNED_OUT =
  "Discover is tailored to you. Sign in and watch the storefront tune itself.";
export const DISCOVER_PAGE_COMING_SOON = STORYBOARD_PAGE_COMING_SOON;
export const DISCOVER_PAGE_CATALOG_LOADING = "Loading the current edit.";
export const DISCOVER_PAGE_CATALOG_UNAVAILABLE =
  "The current edit is unavailable. Try again shortly.";

export const ABOUT_BRIEF = {
  EYEBROW: "About",
  IMAGE: "/products/hero-about.png",
  IMAGE_ALT:
    "A leather weekender, a folded stack of linen, a charcoal stoneware bowl and tumbler, and a ceramic vase holding an olive branch on a travertine counter in raking afternoon light",
  TITLE_LINES: ["A boutique that", "shows its work."],
  LABEL: "Pellier + Pellier Operator + Pellier Observatory",
  PARAGRAPHS: [
    "Pellier is a working boutique for natural materials: linen for travel, stoneware for the table, leather that wears in. Ask for what you mean, a linen shirt for ten days in Goa, a gift under a hundred, a tumbler that earns its place, and Pellier answers with one piece, one reason, and whether it is on the floor today.",
    "Every answer is read from live stock and your own history in Aurora PostgreSQL, checked before it is promised, and written down. Some requests should not be settled by software alone. A return, a credit, an action the policy holds back: those go to the Pellier Operator desk, where a person sees the same client record and the same evidence, decides, and the decision is kept.",
    "Pellier Observatory opens the same answer from the other side: which specialist took the request, what it read, what it was allowed to do, and what the database actually changed. Nothing is recommended, held, or approved that cannot be shown.",
  ],
  STACK: [
    "Aurora PostgreSQL",
    "pgvector",
    "Amazon Bedrock",
    "AgentCore",
    "Strands SDK",
    "Claude",
    "Cohere Embed v4",
    "Cohere Rerank",
    "Cedar",
  ],
  COLOPHON:
    "Built for teams who need the same answer to hold for the shopper, the operator, and the auditor.",
} as const;

// Footer \u2014 three live columns + a brand + a bottom strip.
//
// Earlier iterations carried four product/editorial columns with a
// dozen links, a newsletter form, and a bottom strip. Every one of
// those links was a stub. Replaced with three columns pointing at
// routes that actually exist: Explore (the three real storefront
// routes), Storyboard (editorial entry), Pellier Observatory (the workshop).
// Fewer promises, every promise kept.
export const FOOTER = {
  BRAND: {
    TAGLINE: "Curated goods for travel, gifting, and home rituals",
  },
  EXPLORE: {
    HEADING: "Explore",
    ITEMS: [
      { label: "Shop", href: "/#shop" },
      { label: "Stories", href: "/storyboard" },
      { label: "About", href: "/about" },
    ],
  },
  STORYBOARD: {
    HEADING: "Stories",
    COPY: "Field notes from a slower kind of shopping. One short essay at a time.",
    CTA_LABEL: "Read the stories",
    CTA_HREF: "/storyboard",
  },
  OBSERVATORY: {
    HEADING: "Pellier Observatory",
    COPY: "Inspect the routing, retrieval, tools, memory, and evidence behind each workshop turn.",
    CTA_LABEL: "Open Pellier Observatory",
    CTA_HREF: "/observatory",
  },
  /** Official owner artwork in the footer only. The visible label and the
   * disclaimer keep the strip inside the same non-processing demo contract. */
  CHECKOUT: {
    LABEL: "Secure demo checkout",
    ARIA_LABEL: "Secure demo checkout payment methods",
    PAYMENT_METHODS: [
      { id: "visa", label: "Visa" },
      { id: "mastercard", label: "Mastercard" },
      { id: "amex", label: "American Express" },
      { id: "paypal", label: "PayPal" },
      { id: "apple-pay", label: "Apple Pay" },
      { id: "google-pay", label: "Google Pay" },
    ],
  },
  /** Stated outright rather than implied, because a storefront that looks
   * this finished invites the assumption that it transacts. */
  DISCLAIMER:
    "Nothing here charges a card. Products, prices, reviews, and availability are synthetic data built for this workshop. AI-generated imagery is for illustrative purposes only.",
  BOTTOM_STRIP: {
    COPYRIGHT: "\u00a9 Pellier",
    /** Retail assurances, moved out of the hero capabilities strip so that
     * strip can stay focused on agent claims. The shipping and returns
     * figures must match SERVICE_STRIP.ITEMS below; two numbers for one
     * policy is the kind of quiet contradiction a participant notices. */
    SERVICE_ITEMS: [
      "Free shipping over $150",
      "Returns within 30 days",
      "Confirmed totals",
    ],
    /** The repository is MIT, explicitly NOT MIT-0. Formal individual
     * attribution remains in NOTICE; the storefront credits the team and
     * links to the source. Keep this in step with LICENSE and NOTICE. */
    RIGHTS: "\u00a9 2026 Amazon Web Services",
    LICENSE: "Sample code under the MIT License",
    ATTRIBUTION: "Built with the AWS Database Specialists team",
    GITHUB_URL:
      "https://github.com/aws-samples/sample-pellier-agentic-search-apg",
    GITHUB_LABEL: "View the source on GitHub",
  },
} as const;

// Command pill (Requirement 1.11.1)
export const COMMAND_PILL = {
  LABEL: "Ask Pellier",
  KEY_CAP_MAC: "\u2318K",
  KEY_CAP_WIN: "Ctrl K",
} as const;

// Auth modal (storefront.md "Auth modal" section, Requirement 2.6.6)
export const AUTH_MODAL = {
  HEADER: "Welcome to Pellier",
  SUBHEADER: "Sign in for a storefront built for you",
  EYEBROW: "PERSONALIZED VISIONS",
  ITALIC_HEADLINE: "Let Pellier find the right pieces.",
  BUTTON_GOOGLE: "Continue with Google",
  BUTTON_APPLE: "Continue with Apple",
  BUTTON_EMAIL: "Continue with email",
  DISCLAIMER: "By continuing, you agree to our terms and privacy policy.",
  FOOTER: "Secured by AgentCore Identity",
  VERSION: "v2.4",
} as const;

// Preferences onboarding modal (storefront.md "Preferences onboarding modal")
export interface PreferenceChip {
  label: string;
  descriptor?: string;
  swatch?: string;
}
export interface PreferenceGroup {
  heading: string;
  kind: "card" | "pill";
  chips: PreferenceChip[];
}
export const PREFERENCES_MODAL = {
  HEADER: "A quick tune-up",
  SUBHEADER: "Takes about 20 seconds. You can change these anytime.",
  ITALIC_HEADLINE: "What moves you?",
  SUBHEADLINE: "Pick what resonates. Pellier will take it from here.",
  GROUPS: [
    {
      heading: "Your overall vibe",
      kind: "card",
      chips: [
        { label: "Minimal", descriptor: "Quiet \u00b7 Considered" },
        { label: "Bold", descriptor: "Statement \u00b7 Saturated" },
        { label: "Serene", descriptor: "Soft \u00b7 Calming" },
        { label: "Adventurous", descriptor: "Outdoor \u00b7 Durable" },
        { label: "Creative", descriptor: "Layered \u00b7 Textured" },
        { label: "Classic", descriptor: "Timeless \u00b7 Refined" },
      ],
    },
    {
      heading: "Favorite colors",
      kind: "pill",
      chips: [
        { label: "Warm tones", swatch: "terracotta-to-amber" },
        { label: "Neutrals", swatch: "sand-to-ink-soft" },
        { label: "Earth", swatch: "ink-soft-to-dusk" },
        { label: "Soft pastels", swatch: "cream-warm-to-cream" },
        { label: "Deep and moody", swatch: "ink-to-near-black" },
      ],
    },
    {
      heading: "Where you wear it",
      kind: "pill",
      chips: [
        { label: "Everyday" },
        { label: "Travel" },
        { label: "Evenings out" },
        { label: "Outdoor" },
        { label: "Slow mornings" },
        { label: "Work" },
      ],
    },
    {
      heading: "Categories you love",
      kind: "pill",
      chips: [
        { label: "Linen" },
        { label: "Footwear" },
        { label: "Outerwear" },
        { label: "Accessories" },
        { label: "Home" },
        { label: "Dresses" },
      ],
    },
  ] as PreferenceGroup[],
  SKIP: "Skip for now",
  SUBMIT: "Save and see my storefront",
  FOOTER: "Preferences stored with AgentCore Memory",
} as const;

// Error copy (design.md "Error Handling" table). Machine codes are colocated
// for grep-ability; the scanner still treats them as regular string values.
export const ERRORS = {
  AGENT_TIMEOUT: "Taking a moment. Try again?",
  DB_UNAVAILABLE: "I can't reach the catalog right now.",
  AUTH_INTERRUPTED: "Something interrupted the sign-in. Try again.",
  EMPTY_SEARCH_RESULT: "Nothing yet. Try a different wording.",
  SILENT_REFRESH_SAY: "",
  SEARCH_FALLBACK_LOADING: "Pellier is thinking...",
} as const;

export const CHAT_FAILURES = {
  policy_denied: {
    eyebrow: "Protected action",
    title: "That action is not available.",
    body: "A storefront rule kept your account and inventory unchanged. Adjust the request or choose another option.",
  },
  authentication_required: {
    eyebrow: "Session refresh",
    title: "Sign in again to continue.",
    body: "Your conversation is saved. Refresh your session, then retry this request.",
  },
  rate_limited: {
    eyebrow: "High demand",
    title: "Pellier needs a brief moment.",
    body: "Your conversation is saved. Try the request again in a few seconds.",
  },
  request_timeout: {
    eyebrow: "Request paused",
    title: "This took longer than expected.",
    body: "Nothing was changed. Try again, or narrow the request for a faster answer.",
  },
  service_unavailable: {
    eyebrow: "Temporarily unavailable",
    title: "Pellier cannot complete this request yet.",
    body: "Your conversation is saved. Try again in a moment without starting over.",
  },
  invalid_request: {
    eyebrow: "Request needs detail",
    title: "Pellier needs a different wording.",
    body: "Adjust the request and send it again. Your earlier conversation will stay in place.",
  },
  stream_interrupted: {
    eyebrow: "Response interrupted",
    title: "The reply ended before it was complete.",
    body: "Your conversation is saved. Retry the request to receive a complete answer.",
  },
  network_error: {
    eyebrow: "Connection interrupted",
    title: "Pellier cannot reach the catalog right now.",
    body: "Your conversation is saved. Check the connection and try this request again.",
  },
  request_failed: {
    eyebrow: "Request paused",
    title: "Pellier could not complete that request.",
    body: "Try again, or adjust the wording while keeping the rest of the conversation.",
  },
  /** An expected build state, not an error: the capability this request
   * needs is left unbuilt on purpose until a lab step lands. The card stays
   * quiet and in the shopper's voice; the reference code beneath it is the
   * participant's pointer to the build step, and nothing here claims a tool
   * ran. */
  workshop_build_required: {
    eyebrow: "Still being set up",
    title: "Pellier cannot answer this one yet.",
    body: "The part of the boutique that checks this is not finished. Nothing was changed, and a stylist can confirm it for you in the meantime.",
  },
  TRY_AGAIN: "Try again",
  EDIT_REQUEST: "Edit request",
  SIGN_IN_AGAIN: "Sign in again",
} as const;

export const CHAT_TRUST = {
  MATCH_DETAILS: "Match details",
  TURN_RECEIPT: "Turn receipt",
  /** The stream finished. Says nothing about evidence. */
  RESPONSE_COMPLETE: "Response complete",
  /** Every required evidence-sufficiency check for the turn is satisfied. */
  EVIDENCE_RECORDED: "Evidence recorded",
  /**
   * The ledger was read and at least one required check is not satisfied.
   *
   * Distinct from showing nothing, which is what "we have not looked" looks
   * like. A refuted or incomplete ledger that renders identically to an
   * unchecked one is the same conflation the sufficiency states exist to
   * prevent, one surface further out.
   */
  EVIDENCE_INCOMPLETE: "Evidence incomplete",
  COPY_REFERENCE: "Copy turn reference",
  COPIED_REFERENCE: "Reference copied",
} as const;

/**
 * A persona is a workshop scenario, not a login. Cognito sign-in keeps its
 * own wording; these strings never claim that
 * choosing Marco authenticated anyone.
 */
export const SCENARIO = {
  SELECT: "Select scenario",
  CHOOSE_TITLE: "Choose a scenario",
  NONE_SELECTED: "None selected",
  /**
   * The banner over an open conversation. It reports the scenario already
   * running, so it reads as a label; "Select scenario: Marco" is the control
   * that starts one, and putting an imperative on a state banner asked the
   * reader to do something they had already done.
   */
  active: (displayName: string): string => `Scenario: ${displayName}`,
} as const;

/** The three status lines under the chat header, each from its own source. */
export const STATUS_LINES = {
  SCENARIO: "Scenario",
  VERIFIED_IDENTITY: "Verified identity",
  NOT_SIGNED_IN: "Not signed in",
  EXECUTION_PATH: "Execution path",
  EXECUTION_UNKNOWN: "Unknown until the first turn",
} as const;

export const ERROR_CODES = {
  AGENT_TIMEOUT: "agent_timeout",
  AUTH_FAILED: "auth_failed",
  INVALID_STATE: "invalid_state",
  INVALID_PREFERENCES: "invalid_preferences",
  UNAVAILABLE: "unavailable",
  DB_UNAVAILABLE: "db_unavailable",
} as const;
