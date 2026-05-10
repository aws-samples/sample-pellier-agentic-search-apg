/**
 * ProductMiniCard — view-only product card rendered inline in the
 * Atelier chat when the recommendation agent returns picks.
 *
 * Deliberately not the storefront's ProductCard: no hover, no add-to-
 * cart, no wishlist, no swatches. This surface is teaching; the
 * agentic demo needs product identity at a glance, not commerce
 * affordances. Boutique for buying; Atelier for watching.
 *
 * Visual: white card, 1px ink-at-14% border, 8px radius. A solid
 * color block across the top (78px) stands in for the product image
 * without needing a network fetch. Name + price + attribute line
 * below.
 */

const INK = '#2d1810'
const INK_QUIET = '#a68668'
const ACCENT = '#c44536'

export interface ProductMiniCardProps {
  name: string
  price?: string
  /** Two or three low-key attributes: e.g. "earl gray · relaxed". */
  attributes?: string
  /** Hex tone for the placeholder color block. Defaults to a warm ivory. */
  tone?: string
}

export default function ProductMiniCard({
  name,
  price,
  attributes,
  tone = '#cdc7b8',
}: ProductMiniCardProps) {
  return (
    <div
      data-testid="product-mini-card"
      className="rounded-lg overflow-hidden"
      style={{
        background: 'white',
        border: '1px solid rgba(45, 24, 16, 0.14)',
      }}
    >
      <div
        aria-hidden
        className="w-full"
        style={{ height: 78, background: tone }}
      />
      <div className="px-[11px] py-[9px]">
        <div
          className="text-[11px] leading-[1.3] font-medium"
          style={{ color: INK }}
        >
          {name}
        </div>
        {price && (
          <div
            className="font-mono text-[11px] mt-1"
            style={{ color: ACCENT }}
          >
            {price}
          </div>
        )}
        {attributes && (
          <div
            className="text-[9px] mt-1.5"
            style={{ color: INK_QUIET, letterSpacing: '0.04em' }}
          >
            {attributes}
          </div>
        )}
      </div>
    </div>
  )
}
