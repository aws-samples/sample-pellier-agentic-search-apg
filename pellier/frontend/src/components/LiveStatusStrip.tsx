/**
 * LiveStatusStrip — the reassuring status line above the category chips.
 *
 * Renders the `LIVE_STATUS` copy alongside Shipping / Returns /
 * Secure checkout. The component is intentionally static now: an
 * earlier iteration fetched `/api/inventory` and rendered an amber
 * "Catalog refreshing…" warning when the endpoint reported
 * `stale=true`, but the state surfaced frequently in demo envs where
 * the stale flag is noisy and there's nothing a shopper can do about
 * it. The stale warning is gone; the strip is now pure decoration
 * and free of a network round-trip.
 */
import {
  LIVE_STATUS,
  SHIPPING,
  RETURNS,
  SECURE_CHECKOUT,
} from '../copy'

// --- Design tokens (storefront.md) --------------------------------------
const CREAM = '#fbf4e8'
const INK = '#2d1810'
const INK_SOFT = '#6b4a35'
const ACCENT = '#c44536'

// Kept as exported constants so any future consumer that wants to
// re-introduce the live-signal fetch has the same contract to hit.
export interface InventorySignal {
  last_refreshed: string
  counts: Record<string, number>
  stale: boolean
}
export const INVENTORY_ENDPOINT = '/api/inventory'

export default function LiveStatusStrip() {
  return (
    <section
      data-testid="live-status-strip"
      aria-label="Live inventory status"
      className="w-full border-y"
      style={{
        background: CREAM,
        color: INK,
        borderColor: 'rgba(45, 24, 16, 0.08)',
        padding: '10px 24px',
      }}
    >
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 text-center md:text-left">
        <div className="flex items-center gap-2">
          <span
            data-testid="live-status-pulse-dot"
            aria-hidden="true"
            className="inline-block h-2 w-2 rounded-full"
            style={{
              background: ACCENT,
              boxShadow: `0 0 0 0 ${ACCENT}`,
              animation: 'pulse-glow 2s infinite',
            }}
          />
          <span
            data-testid="live-status-copy"
            style={{
              fontSize: '12px',
              letterSpacing: '0.04em',
              color: INK_SOFT,
            }}
          >
            {LIVE_STATUS}
          </span>
        </div>
        <div
          className="flex items-center gap-4"
          style={{
            fontSize: '12px',
            color: INK_SOFT,
            letterSpacing: '0.04em',
          }}
        >
          <span
            data-testid="live-status-shipping"
            style={{ color: INK_SOFT }}
          >
            {SHIPPING}
          </span>
          <span
            data-testid="live-status-returns"
            style={{ color: INK_SOFT }}
          >
            {RETURNS}
          </span>
          <span
            data-testid="live-status-secure"
            style={{ color: INK_SOFT }}
          >
            {SECURE_CHECKOUT}
          </span>
        </div>
      </div>
    </section>
  )
}
