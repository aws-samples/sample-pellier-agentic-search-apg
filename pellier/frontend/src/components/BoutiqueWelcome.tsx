/**
 * BoutiqueWelcome — editorial welcome state for the storefront concierge.
 *
 * Renders when the conversation is empty (no user messages yet) in
 * storefront mode. Matches the design in docs/pellier-chat-synthesis.html:
 *
 *   Cover image (CSS-only vessel composition) → greeting → boutique
 *   stats → pre-vetted picks (3 stacked pills) → centered-dot divider
 *   → "Or tell me what you're after" prompt → P.S. close with 3
 *   quoted suggestions.
 *
 * When a persona is active (Marco, Anna), greeting + picks + P.S. chips
 * swap to persona-specific copy grounded in their signals from
 * docs/personas-config.json. Fresh visitors see the editorial default.
 *
 * All picks and P.S. suggestions fire `onSend(text)` on click, which
 * the parent wires to `useAgentChat.sendMessage`.
 */
import '../styles/boutique-welcome.css'
import type { PersonaSnapshot } from '../contexts/PersonaContext'
import { useCatalogStats, type CatalogStats } from '../hooks/useCatalogStats'
import { SHOWCASE_PRODUCTS } from '../data/showcaseProducts'
import type { BoutiqueProduct } from '../services/types'

interface BoutiqueWelcomeProps {
  onSend: (text: string) => void
  persona?: PersonaSnapshot | null
}

type TimeOfDay = 'morning' | 'afternoon' | 'evening'

function timeOfDay(): TimeOfDay {
  const h = new Date().getHours()
  if (h < 12) return 'morning'
  if (h < 17) return 'afternoon'
  return 'evening'
}

const TOD_GREETING: Record<TimeOfDay, string> = {
  morning: 'Good morning',
  afternoon: 'Good afternoon',
  evening: 'Good evening',
}

const TOD_EYEBROW: Record<TimeOfDay, string> = {
  morning: 'This morning at the boutique',
  afternoon: 'This afternoon at the boutique',
  evening: 'Tonight at the boutique',
}

const TOD_COVER_EYEBROW: Record<TimeOfDay, string> = {
  morning: "This morning's standout",
  afternoon: "This afternoon's standout",
  evening: "Tonight's standout",
}

// ---------------------------------------------------------------------------
// Cover resolution — picks the cover product + its eyebrow per persona.
//
// Each returning persona gets a pinned cover piece anchored to their
// clearest signal, with an eyebrow that swaps the newsroom "standout"
// language for something that reads as curated-for-them. Fresh users
// (and null) fall through to the global standout from the catalog-
// stats endpoint with the time-of-day eyebrow — no signal to tailor
// against, so the boutique voice stays honest.
//
// If a pinned piece isn't found in the provided catalog (defensive
// guard against future showcase edits), the persona falls through to
// the global path so the cover never disappears.
// ---------------------------------------------------------------------------

interface PersonaCover {
  /** Product name to find in the catalog (exact match on `name`). */
  coverName: string
  /** Eyebrow copy that replaces the time-of-day "standout" line. */
  eyebrow: string
}

// Pinned covers keyed by persona id. Extending this is the one-line
// way to tailor a new persona's welcome cover.
const PERSONA_COVERS: Record<string, PersonaCover> = {
  marco: {
    coverName: 'Italian Linen Camp Shirt',
    eyebrow: 'Matched to your thread',
  },
  anna: {
    // Swapped from Ceramic Tumbler Set (now Theo's) to the Straw
    // Tote — bestseller, under $100, reads as a considered gift.
    coverName: 'Beeswax Taper Candles',
    eyebrow: 'A gift, ready to go',
  },
  theo: {
    coverName: 'Stoneware Pour-Over Set',
    eyebrow: 'Quiet pieces for slow days',
  },
}

export interface CoverResolution {
  product: BoutiqueProduct
  eyebrow: string
}

export function resolveCover(
  persona: PersonaSnapshot | null | undefined,
  stats: CatalogStats | null,
  tod: TimeOfDay,
  catalog: readonly BoutiqueProduct[] = SHOWCASE_PRODUCTS,
): CoverResolution {
  // Persona-specific cover path. Try the pinned piece; fall through if
  // it isn't in the catalog.
  const pinned = persona?.id ? PERSONA_COVERS[persona.id] : undefined
  if (pinned) {
    const product = catalog.find((p) => p.name === pinned.coverName)
    if (product) {
      return { product, eyebrow: pinned.eyebrow }
    }
  }

  // Global standout — match the stats endpoint's standout_name against
  // the showcase catalog, otherwise fall back to the first piece.
  const standoutMatch = stats?.standout_name
    ? catalog.find(
        (p) =>
          p.name.toLowerCase().includes(stats.standout_name!.toLowerCase()) ||
          stats.standout_name!.toLowerCase().includes(p.name.toLowerCase()),
      )
    : undefined
  return {
    product: standoutMatch ?? catalog[0],
    eyebrow: TOD_COVER_EYEBROW[tod],
  }
}

interface PersonaCopy {
  /** Greeting line without time-of-day prefix. For fresh visitors this
   * is empty and the time-of-day stands alone ("Good evening."). For
   * returning personas it's the warm back-reference ("Marco — welcome
   * back."). */
  greetingSuffix: (firstName: string) => string
  /** Short context paragraph that follows the greeting. Grounded in
   * persona signals so it reads like the storefront remembers them.
   * Receives live catalog stats so copy that cites the catalog size
   * never goes stale. */
  context: (stats: CatalogStats | null) => React.ReactNode
  picks: ReadonlyArray<{ label: string; primary: boolean }>
  ps: ReadonlyArray<string>
}

// CatalogStats is imported from the hook module so resolveCover and
// PersonaCopy.context can both reference the same shape.

const FRESH_COPY: PersonaCopy = {
  greetingSuffix: () => '',
  context: (stats) => {
    if (!stats || stats.product_count === 0) {
      return (
        <>
          Welcome to Pellier. I'm Pellier — your personal shopping
          concierge. Tell me what you're looking for and I'll find the
          right pieces.
        </>
      )
    }
    return (
      <>
        I've been watching the floor —{' '}
        <span className="sf-context-num">{stats.product_count}</span>{' '}
        curated pieces across {stats.category_count} categories. The{' '}
        <span className="sf-context-product">Nocturne Leather Weekender</span>{' '}
        and{' '}
        <span className="sf-context-product">Pellier Linen Shirt</span>{' '}
        are the standouts this week.
      </>
    )
  },
  picks: [
    { label: 'A thoughtful gift for someone who runs', primary: true },
    { label: 'Linen pieces that travel well', primary: false },
    { label: 'Something for slow Sunday mornings', primary: false },
  ],
  ps: [
    'a cozy layer for cooler nights',
    'pieces for slow Sunday mornings',
    'something to wear for warm evenings out',
  ],
}

const MARCO_COPY: PersonaCopy = {
  greetingSuffix: (firstName) => `, ${firstName}. Welcome back.`,
  context: () => (
    <>
      I remember you love natural fabrics and pieces that travel well.
      The{' '}
      <span className="sf-context-product">Pellier Linen Shirt</span>{' '}
      just landed in ecru — it picks up where your last saved piece
      left off. Want to build a packing list?
    </>
  ),
  picks: [
    // Must match the first 3 entries in PERSONA_HERO_PILLS.marco exactly —
    // these are Marco's canonical workshop Turn 1/2/3 queries.
    { label: 'What linen do you have for 10 days in Goa?', primary: true },    // Turn 1
    { label: 'What would go with the Pellier shirt?', primary: false },         // Turn 2
    { label: "What's the price range for linen shirts?", primary: false },      // Turn 3
  ],
  ps: [
    'is the Pellier shirt at the Brooklyn warehouse?',
    'what pairs with the Ecru overshirt?',
    'neutral accessories for the road',
  ],
}

const ANNA_COPY: PersonaCopy = {
  greetingSuffix: (firstName) => `, ${firstName}. Welcome back.`,
  context: () => (
    <>
      I know you have an eye for thoughtful gifts. The{' '}
      <span className="sf-context-product">Beeswax Taper Candles</span>{' '}
      and{' '}
      <span className="sf-context-product">Ceramic Ring Dish</span>{' '}
      are our most-gifted pieces this month. Tell me who you're shopping
      for and I'll find something that lands.
    </>
  ),
  picks: [
    { label: 'A thoughtful gift for someone who loves morning rituals', primary: true },  // Turn 1
    { label: 'Something beautiful under $100', primary: false },                           // Turn 2
    { label: 'Help me pair a candle with something else', primary: false },                // Turn 3
  ],
  ps: [
    'wrap-ready gifts with no extra effort',
    'a milestone gift for a new homeowner',
    'candles that feel considered, not generic',
  ],
}

const THEO_COPY: PersonaCopy = {
  greetingSuffix: (firstName) => `, ${firstName}. Good to see you.`,
  context: () => (
    <>
      I see you gravitate toward slow-craft pieces. The{' '}
      <span className="sf-context-product">Stoneware Pour-Over Set</span>{' '}
      pairs beautifully with the{' '}
      <span className="sf-context-product">Ceramic Tumblers</span>{' '}
      — they're from the same kiln run. Your morning table is one piece
      away from complete.
    </>
  ),
  picks: [
    { label: 'Hand-thrown ceramics for a slower morning routine', primary: true },  // Turn 1
    { label: 'What goes well with the pour-over set?', primary: false },             // Turn 2
    { label: 'Linen pieces that soften over seasons', primary: false },              // Turn 3
  ],
  ps: [
    'something for the home, not the wardrobe',
    'artisanal objects worth keeping',
    'pieces with real patina',
  ],
}

function copyForPersona(persona?: PersonaSnapshot | null): PersonaCopy {
  if (!persona) return FRESH_COPY
  switch (persona.id) {
    case 'marco':
      return MARCO_COPY
    case 'anna':
      return ANNA_COPY
    case 'theo':
      return THEO_COPY
    case 'fresh':
    default:
      return FRESH_COPY
  }
}

export default function BoutiqueWelcome({ onSend, persona }: BoutiqueWelcomeProps) {
  const copy = copyForPersona(persona)
  const tod = timeOfDay()
  const firstName = persona ? persona.display_name.split(' ')[0] : ''
  const greeting = `${TOD_GREETING[tod]}${copy.greetingSuffix(firstName)}.`
  const stats = useCatalogStats()

  // Resolve cover product + eyebrow per persona. Anna's gift branch
  // diverges from Marco/Fresh (who get the global standout); the
  // helper is the single place that encodes that rule.
  const { product: coverProduct, eyebrow: coverEyebrow } = resolveCover(
    persona,
    stats,
    tod,
  )

  return (
    <div className="sf-welcome">
      {/* Cover image — real product photo from the catalog */}
      <div className="sf-cover">
        <img
          src={coverProduct.imageUrl}
          alt={coverProduct.name}
          className="sf-cover-img"
        />
        <div className="sf-cover-overlay">
          <div className="sf-cover-eyebrow">
            <span className="sf-cover-dot" />
            {coverEyebrow}
          </div>
          <div className="sf-cover-edition">No. 06</div>
        </div>
      </div>

      {/* Body */}
      <div className="sf-body">
        {/* Eyebrow row */}
        <div className="sf-eyebrow-row">
          <span className="sf-eyebrow-sm">{TOD_EYEBROW[tod]}</span>
          <span className="sf-eyebrow-rule" />
        </div>

        {/* Greeting */}
        <h2 className="sf-greeting">
          <em>{greeting}</em>
        </h2>
        <p className="sf-context">{copy.context(stats)}</p>

        {/* Pre-vetted picks */}
        <div className="sf-section">
          <div className="sf-section-head">
            <span className="sf-eyebrow-sm sf-eyebrow-red">
              <span className="sf-dot" />
              {persona && persona.id !== 'fresh' ? 'Curated for you' : 'Pre-vetted picks'}
            </span>
            <span className="sf-count">3 OF 9</span>
          </div>
          <div className="sf-actions-stack">
            {copy.picks.map((pick) => (
              <button
                key={pick.label}
                type="button"
                className={`sf-action ${pick.primary ? 'sf-action-primary' : ''}`}
                onClick={() => onSend(pick.label)}
              >
                {pick.label}
                <span className="sf-action-arrow">→</span>
              </button>
            ))}
          </div>
        </div>

        {/* Centered-dot divider */}
        <div className="sf-divider" />

        {/* Prompt */}
        <p className="sf-prompt">Or tell me what you're after.</p>

        {/* P.S. close */}
        <div className="sf-postscript">
          <p className="sf-postscript-lead">
            <span className="sf-ps-mark">P.S.</span>
            <span className="sf-ps-dash">&mdash;</span>
            {persona && persona.id !== 'fresh'
              ? " If nothing comes to mind, here's what you've been asking lately:"
              : " If nothing comes to mind, here's what others have been asking lately:"}
          </p>
          <div className="sf-postscript-list">
            {copy.ps.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                className="sf-overheard"
                onClick={() => onSend(suggestion)}
              >
                <span className="sf-overheard-bullet">&middot;</span>
                <span className="sf-overheard-quote">
                  &ldquo;{suggestion}&rdquo;
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
