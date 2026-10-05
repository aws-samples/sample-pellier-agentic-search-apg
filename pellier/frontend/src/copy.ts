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
  "Complimentary shipping over $150. Returns within 30 days. Resort Edit No. 06 is now live";

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
  /** The core participant surface for labs and connected system evidence. */
  OBSERVATORY: "Pellier Observatory",
  /** The clienteling desk, connected to Storefront conversations and Observatory evidence. */
  OPERATOR: "Pellier Operator",
} as const;

// Account button labels (Requirement 1.2.2, 1.2.3)
export const ACCOUNT_LABEL_SIGNED_OUT = "Account";
export const accountLabelSignedIn = (givenName: string): string =>
  `Hi, ${givenName}`;

export const PELLIER_HERO_SIGNED_OUT = {
  LINE_1: "Choose a shopper profile to begin.",
  LINE_2: "Pellier will tailor the floor around that visit.",
} as const;

/**
 * The home page's shopper chooser. Choosing a shopper signs in with that
 * shopper's demo account and opens their edit; browsing without choosing
 * stays signed out.
 */
export const HERO_CONCIERGE = {
  EYEBROW: "Welcome to Pellier",
  TITLE: "Choose who enters Pellier.",
  HELPER:
    "Choose Marco, Anna, Theo or Jessica to see their edit and ask Pellier as them.",
  /**
   * Stated where the choice is made. The choice performs a real sign-in, and
   * every governed check reads the signed token it produced, never this click.
   * The Builder view shows that verified principal on every turn.
   */
  IDENTITY_BOUNDARY:
    "Choosing a shopper signs you in with their demo account. Pellier trusts the signed token, not this choice.",
  SIGNING_IN: "Signing in",
  FAILED: "That sign-in did not complete. Try again, or use the sign-in page.",
} as const;

/**
 * Editorial hero statement. One accent word per line is split out as an
 * `<em>`; `ACCENT` must appear verbatim inside `HEADLINE` or the headline
 * renders unaccented rather than mis-split.
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
  jessica: {
    HEADLINE: "Home comforts, made to last.",
    ACCENT: "comforts",
  },
} as const;

/**
 * The large bar on the home page: agentic search, where a search and a
 * question are the same thing. The chips are the moments the storefront shops
 * by, named as the store names them in VOICE.md, until a shopper is signed in.
 */
export const ASK_BAR = {
  LABEL: "Search or ask Pellier", // copy-allow: search-as-verb
  PLACEHOLDER: "Search or ask Pellier…", // copy-allow: search-as-verb
  SEND: "Send",
  TRY: "Try",
  promptsFor: (displayName: string): string => `Suggestions for ${displayName}`,
  MOMENTS: [
    "For the trip",
    "For the table and slow mornings",
    "Gifts under $100",
    "Home comforts",
    "Everyday basics",
    "Made to last",
  ],
} as const;

/**
 * The results view: a question from the home bar or the dock fills the page
 * grid with the pieces that answer came from, in its order. Every number is
 * the turn's own evidence; nothing here is counted in the browser.
 */
export const RESULTS = {
  title: (query: string): string => `Results for \u201c${query}\u201d`,
  fit: (kept: number, of: number): string => `${kept} of ${of} fit`,
  shown: (count: number): string => `${count} ${count === 1 ? "piece" : "pieces"}`,
  FROM_EARLIER: "from earlier",
  LIMITS: "Limits",
  CLEAR: "Show the whole store",
  GRID: "Pieces that fit",
  LOADING: "Loading the pieces",
  STARTING: "Sending your request",
  EMPTY_TITLE: "Nothing fits all of that right now.",
  emptyLeftOut: (parts: readonly string[]): string => `Left out: ${parts.join(", ")}.`,
  EMPTY_HINT: "Try a higher budget or one fewer limit.",
  EMPTY_NO_COUNTS: "Nothing matched that request. Try other words or one fewer limit.",
  FAILED: "That request did not finish, so the pieces below are from before.",
  FAILED_STORE: "That request did not finish. The store is as it was.",
  CARDS_FAILED: "The pieces could not be loaded just now.",
  RETRY: "Try again",
} as const;

/**
 * What the storefront stands for, in four claims. Each links to a page that
 * explains it; do not add a claim without one.
 */
export const PELLIER_APPROACH = {
  EYEBROW: "The Pellier approach",
  TITLE_TOP: "Considered pieces.",
  TITLE_BOTTOM: "Clear reasons.",
  ACCENT: "reasons",
  BODY:
    "A little context makes choosing easier. Explore the pieces, understand the details, and find what feels right for you.",
  CTA_LABEL: "About Pellier",
  CTA_HREF: "/about",
  IMAGE: "/products/landing-approach-atelier.png",
  IMAGE_ALT:
    "A leather holdall on a pale wood workbench beside a roll of burlap, a stitching awl and a spool of waxed thread",
  PILLARS: [
    {
      title: "A reason for every recommendation",
      body: "Explore the catalog details and sources behind the pieces we suggest.",
      linkLabel: "How Pellier answers",
      href: "/about",
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
} as const;

/**
 * Product detail page (`/product/:id`).
 *
 * Every claim here is either structural chrome or a label over a value the
 * page actually read. The availability copy is deliberately split three
 * ways (reading, read, not read) because "not read" must never be
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
  SIGNALS_HEADING: "Details at a glance",
  MORE_HEADING: "More from the collection",
  UNAVAILABLE_TITLE: "We couldn’t load this piece",
  UNAVAILABLE_BODY:
    "Its details are unavailable just now. Try again, or return to the collection.",
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

// Sign-in strip (Requirement 1.4.1)
export const SIGN_IN_STRIP = {
  EYEBROW: "YOUR ACCOUNT",
  HEADLINE: "Sign in and watch Pellier tailor the storefront to you.",
  CTA: "Sign in for personalized visions",
  DISMISS: "Not now",
} as const;

// Reasoning chip copy (Requirement 1.7). The pricing style exposes its urgent
// clause separately so the UI can render it in terracotta.
export const reasoningPicked = (reason: string): string =>
  `Picked because ${reason}`;

export const reasoningMatched = (
  attr1: string,
  attr2: string,
  attr3: string,
): string => `Matched on: ${attr1}, ${attr2}, ${attr3}`;

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
//   `{badge} {volume}: {theme}` above the Instrument Sans title,
// followed by a 2-3 sentence excerpt and the terracotta `link`. See
// StoryboardTeaser.tsx for the rendering contract.
export interface StoryboardTeaser {
  badge: string;
  volume: string;
  theme: string;
  title: string;
  excerpt: string;
  link: string;
  noteId: string;
  imageUrl: string;
  imageAlt: string;
}
export const STORYBOARD_TEASERS: StoryboardTeaser[] = [
  {
    badge: "FIELD NOTE",
    volume: "No. 02",
    theme: "Marco",
    title: "On being remembered.",
    excerpt: "How a returning shopper's choices shape what comes next.",
    link: "Read Marco's note \u203a",
    noteId: "field-note-marco",
    imageUrl: "/products/story-summer.png",
    imageAlt: "A folded linen shirt tied with twine and dried wheat on an oak window ledge, a charcoal stoneware mug beside it",
  },
  {
    badge: "FIELD NOTE",
    volume: "No. 03",
    theme: "Anna",
    title: "On gifting as a practiced art.",
    excerpt: "Start with the person, then the piece.",
    link: "Read Anna's note \u203a",
    noteId: "field-note-anna",
    imageUrl: "/products/story-edit.png",
    imageAlt: "Linen fabrics in white, oat, sage, charcoal and grey fanned across a pale wood table, with a stoneware cup, a coiled leather strap and black shears",
  },
  {
    badge: "FIELD NOTE",
    volume: "No. 04",
    theme: "Theo",
    title: "On pieces that wear in.",
    excerpt: "Stoneware and linen that earn their place over time.",
    link: "Read Theo's note \u203a",
    noteId: "field-note-theo",
    imageUrl: "/products/story-makers.png",
    imageAlt: "A freshly thrown charcoal stoneware bowl on a potter's wheel against a white plaster wall",
  },
];

export const ABOUT_BRIEF = {
  EYEBROW: "About",
  IMAGE: "/products/hero-about.png",
  IMAGE_ALT:
    "A leather weekender, folded linen, two charcoal stoneware cups and a stoneware vase with an olive sprig on an oak shelf against a white wall",
  TITLE_LINES: ["A store that", "shows its work."],
  LABEL: "Pellier + Pellier Operator",
  PARAGRAPHS: [
    "Pellier sells natural materials: linen for travel, stoneware for the table, leather that wears in. Ask in your own words. Every answer is checked against live stock in Aurora, and anything that moves money goes to a person.",
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
    "Built so the shopper, the operator and the auditor see the same answer.",
} as const;

// Footer \u2014 two live columns + a brand + a bottom strip.
//
// Earlier iterations carried four product/editorial columns with a
// dozen links, a newsletter form, and a bottom strip. Every one of
// those links was a stub. Replaced with three columns pointing at
// routes that actually exist: Explore (the three real storefront
// routes) and Storyboard (editorial entry).
// Fewer promises, every promise kept.
export const FOOTER = {
  BRAND: {
    TAGLINE: "Well-made everyday pieces for travel, gifts, and home.",
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
    COPY: "Field notes from a slower kind of shopping.",
    CTA_LABEL: "Read the stories",
    CTA_HREF: "/storyboard",
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
      "https://github.com/aws-samples/sample-pellier-agentic-search-apg/tree/governed",
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
  BUTTON_EMAIL: "Continue with workshop account",
  DISCLAIMER: "Use the username and password provided in your workshop workspace.",
  FOOTER: "Sign-in with Amazon Cognito",
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
  TRACE_REFERENCE: "Trace reference",
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
  COPY_TRACE_REFERENCE: "Copy trace reference",
  COPIED_REFERENCE: "Reference copied",
} as const;

/**
 * Choosing a shopper is a sign-in with their demo account. A workshop
 * convenience, not a production pattern: the server performs a real Cognito
 * sign-in for the four demo shoppers only. Staff never appear here.
 */
export const SHOPPER = {
  CHOOSE: "Choose a shopper",
  SIGN_OUT: "Sign out",
  /** The banner over an open conversation: whose edit this is. */
  edit: (displayName: string): string => `${displayName}'s edit`,
} as const;

/** The status lines under the chat header, each from its own source. */
export const STATUS_LINES = {
  VERIFIED_IDENTITY: "Signed in as",
  NOT_SIGNED_IN: "Not signed in",
  EXECUTION_PATH: "Execution path",
  EXECUTION_UNKNOWN: "Unknown until the first turn",
  /** The session label when the shopper chooser signed the shopper in. */
  WORKSHOP_SESSION: "Workshop sign-in (demo shoppers)",
} as const;

/**
 * The verified principal a turn ran as, for the Builder view. From the
 * server's `turn_start`, never from the shopper chosen on screen.
 */
export const TURN_PRINCIPAL = {
  WORKSHOP: "Workshop sign-in",
  SIGNED_IN: "Signed in",
  NOT_SIGNED_IN: "Not signed in",
  NO_CUSTOMER: "no customer account",
} as const;

export const ERROR_CODES = {
  AGENT_TIMEOUT: "agent_timeout",
  AUTH_FAILED: "auth_failed",
  INVALID_STATE: "invalid_state",
  INVALID_PREFERENCES: "invalid_preferences",
  UNAVAILABLE: "unavailable",
  DB_UNAVAILABLE: "db_unavailable",
} as const;
