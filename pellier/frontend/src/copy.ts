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
  "Free shipping on orders over $150 \u00b7 Returns within 30 days \u00b7 Summer Edit No. 06 is now live";

export const PAGE_TITLE = "Pellier - Summer Edit No. 06";

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
} as const;

// Global surface toggle (Header). Replaces the standalone Workshop
// link with a segmented control that flips between the shopper-facing
// storefront and the operator-facing /workshop surface. Labels
// deliberately pair boutique register (Boutique) with editorial /
// atelier register (Atelier) instead of operator jargon.
export const SURFACE_TOGGLE = {
  ARIA_LABEL: "Switch surface",
  STOREFRONT: "Boutique",
  ATELIER: "Atelier",
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
  EYEBROW: "Summer Edit \u00b7 No. 06",
  TITLE_TOP: "Search,", // copy-allow: search-as-verb
  TITLE_BOTTOM: "re:Engineered.",
  SUBHEADLINE: "Tell Pellier what you're looking for. Watch the pieces find you.",
} as const;

// Product grid section header that reveals on scroll (parallax).
export const PRODUCT_GRID_HEADER = {
  EYEBROW: "Picked for your summer",
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
  HEADLINE: "Sign in and watch Pellier tailor the boutique to you.",
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
// Boutique policy phrases rendered as plain labels on the right side of
// the live status strip (mock pellier_5.html parity).
export const SHIPPING = "Free shipping over $150";
export const RETURNS = "Ships within 1 to 2 days";
export const SECURE_CHECKOUT = "Secure checkout";

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
  // header wordmark — the refinement chip and the header speak with
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
    link: "Read the full vision \u203a",
    imageUrl:
      "https://images.unsplash.com/photo-1693928126497-d9bda6903c03?w=1600&q=85",
    imageAlt: "Golden afternoon light falling across a linen-draped table",
  },
  {
    badge: "VISION BOARD",
    volume: "Vol. 11",
    theme: "The Makers",
    title: "The last clay studio in Ojai.",
    excerpt:
      "One kiln, two hands, forty years of practice. A visit with the makers behind our ceramic line.",
    link: "Read the full vision \u203a",
    imageUrl:
      "https://images.unsplash.com/photo-1607556671927-78a6605e290b?w=1600&q=85",
    imageAlt: "A pair of hands shaping clay on a potter's wheel",
  },
  {
    badge: "BEHIND THE SCENES",
    volume: "Vol. 10",
    theme: "The Edit",
    title: "How we chose this season.",
    excerpt:
      "Nine pieces survived the cut. A quiet walk-through of the edit room conversations that got us here.",
    link: "Read the full vision \u203a",
    imageUrl:
      "https://images.unsplash.com/photo-1761896902115-49793a359daf?w=1600&q=85",
    imageAlt: "An open edit room with fabric swatches laid out on a warm wood table",
  },
];

// Minimal Storyboard and Discover routes (Requirement 1.13)
export const STORYBOARD_PAGE_COMING_SOON =
  "Coming soon - the full editorial hub arrives with the next Edit.";
export const DISCOVER_PAGE_SIGNED_OUT =
  "Discover is tailored to you. Sign in and watch the boutique tune itself.";
export const DISCOVER_PAGE_COMING_SOON = STORYBOARD_PAGE_COMING_SOON;

// Footer \u2014 three live columns + a brand + a bottom strip.
//
// Earlier iterations carried four product/editorial columns with a
// dozen links, a newsletter form, and a bottom strip. Every one of
// those links was a stub. Replaced with three columns pointing at
// routes that actually exist: Explore (the three real storefront
// routes), Storyboard (editorial entry), Atelier (the workshop).
// Fewer promises, every promise kept.
export const FOOTER = {
  BRAND: {
    TAGLINE: "Carefully curated goods from makers who care about craft",
  },
  EXPLORE: {
    HEADING: "Explore",
    ITEMS: [
      { label: "The floor", href: "/#shop" },
      { label: "Discover", href: "/discover" },
      { label: "Storyboard", href: "/storyboard" },
    ],
  },
  STORYBOARD: {
    HEADING: "Storyboard",
    COPY: "Field notes from a slower kind of shopping \u2014 one short essay at a time.",
    CTA_LABEL: "Read the latest",
    CTA_HREF: "/storyboard",
  },
  ATELIER: {
    HEADING: "Atelier",
    COPY: "Behind the curtain \u2014 every tool call, every reasoning step, on display.",
    CTA_LABEL: "Open the Atelier",
    CTA_HREF: "/atelier",
  },
  BOTTOM_STRIP: {
    COPYRIGHT: "\u00a9 Pellier",
    /** Centered service line \u2014 retail boilerplate moved out of the
     * hero capabilities strip so the strip can stay focused on agent
     * claims. Lives in the footer where shipping/returns info belongs. */
    SERVICE: "Ships in 1\u20132 days \u00b7 Free over $150",
    /** Right-hand credit in the footer strip (replaces workshop banner). */
    ATTRIBUTION: "\u00a9 Shayon Sanyal",
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
  SUBHEADER: "Sign in for a boutique built for you",
  EYEBROW: "PERSONALIZED VISIONS",
  ITALIC_HEADLINE: "Let the boutique find you.",
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
  SUBMIT: "Save and see my boutique",
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

export const ERROR_CODES = {
  AGENT_TIMEOUT: "agent_timeout",
  AUTH_FAILED: "auth_failed",
  INVALID_STATE: "invalid_state",
  INVALID_PREFERENCES: "invalid_preferences",
  UNAVAILABLE: "unavailable",
  DB_UNAVAILABLE: "db_unavailable",
} as const;
