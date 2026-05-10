/**
 * ProductGridHeader — section header rendered above <ProductGrid/>.
 *
 * Layout: left-aligned eyebrow + italic Fraunces heading + a short
 * italic "why these nine" caption that changes per persona, with a
 * right-aligned "Sort: Most loved" button on md+. Eyebrow leads with
 * a pulsing terracotta dot (`.pulse-dot` in index.css).
 *
 * The persona-tailored caption makes "Things worth discovering" read
 * as semantic-search-for-you rather than static chrome. Marco sees
 * "Nine pieces the boutique holds for a linen thread like yours"
 * — the same grid (personalization sort lands later), framed by
 * the reason it's being shown.
 */
import { ChevronDown } from 'lucide-react'

import { PRODUCT_GRID_HEADER } from '../copy'
import { usePersona } from '../contexts/PersonaContext'

const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const ACCENT = '#c44536'

// Short italic captions that frame the nine-card grid. Each persona
// gets one; fresh / null fall through to the editorial default. Kept
// in italic Fraunces so the line reads as a caption, not body copy.
const CAPTIONS_BY_PERSONA: Record<string, string> = {
  marco:
    'Nine pieces the boutique holds for a linen thread like yours.',
  anna:
    'Nine pieces that land well as gifts — milestone and everyday both.',
  theo:
    'Nine pieces that wear in — ceramics, linen, stoneware, slow.',
  fresh:
    "Nine pieces the floor is proud of this week — tell Pellier what catches your eye.",
}

function captionForPersona(id: string | undefined | null): string {
  if (!id) return CAPTIONS_BY_PERSONA.fresh
  return CAPTIONS_BY_PERSONA[id] ?? CAPTIONS_BY_PERSONA.fresh
}

export default function ProductGridHeader() {
  const { persona } = usePersona()
  const caption = captionForPersona(persona?.id)

  return (
    <section
      data-testid="product-grid-header"
      className="mx-auto w-full max-w-7xl px-6 pt-14 pb-8"
    >
      <div className="flex items-end justify-between gap-4">
        <div style={{ maxWidth: 680 }}>
          <div
            data-testid="product-grid-header-eyebrow"
            className="mb-2 flex items-center gap-2"
          >
            <span
              data-testid="product-grid-header-pulse-dot"
              aria-hidden
              className="pulse-dot inline-block h-[6px] w-[6px] rounded-full"
              style={{ background: ACCENT }}
            />
            <span
              className="text-[11px] font-medium uppercase tracking-[0.2em]"
              style={{ color: ACCENT, fontFamily: 'Inter, system-ui, sans-serif' }}
            >
              {PRODUCT_GRID_HEADER.EYEBROW}
            </span>
          </div>
          <h2
            data-testid="product-grid-header-title"
            className="font-[Fraunces] italic leading-tight"
            style={{
              margin: 0,
              color: INK,
              fontSize: '2.5rem',
              fontWeight: 400,
              letterSpacing: '-0.01em',
            }}
          >
            {PRODUCT_GRID_HEADER.TITLE}
          </h2>
          <p
            data-testid="product-grid-header-caption"
            style={{
              margin: '12px 0 0',
              fontFamily: 'Fraunces, Georgia, serif',
              fontStyle: 'italic',
              fontWeight: 400,
              fontSize: 17,
              lineHeight: 1.55,
              color: INK_SOFT,
              letterSpacing: '-0.003em',
            }}
          >
            {caption}
          </p>
        </div>
        <button
          type="button"
          data-testid="product-grid-header-sort"
          className="hidden items-center gap-1 text-xs font-medium hover:underline md:flex"
          style={{ color: INK, fontFamily: 'Inter, system-ui, sans-serif' }}
        >
          {PRODUCT_GRID_HEADER.SORT_LABEL}
          <ChevronDown size={14} strokeWidth={1.75} aria-hidden />
        </button>
      </div>
    </section>
  )
}
