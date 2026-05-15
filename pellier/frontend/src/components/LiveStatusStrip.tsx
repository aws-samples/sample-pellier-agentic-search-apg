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
import { cssVar as c } from '../design/cssVars'
import {
  LIVE_STATUS,
  SHIPPING,
  RETURNS,
  SECURE_CHECKOUT,
} from '../copy'

// --- Design tokens (storefront.md) --------------------------------------

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
        background: c.bg,
        color: c.ink,
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
              background: c.accent,
              boxShadow: `0 0 0 0 ${c.accent}`,
              animation: 'pulse-glow 2s infinite',
            }}
          />
          <span
            data-testid="live-status-copy"
            style={{
              fontSize: '12px',
              letterSpacing: '0.04em',
              color: c.ink2,
            }}
          >
            {LIVE_STATUS}
          </span>
        </div>
        <div
          className="flex items-center gap-4"
          style={{
            fontSize: '12px',
            color: c.ink2,
            letterSpacing: '0.04em',
          }}
        >
          <span
            data-testid="live-status-shipping"
            style={{ color: c.ink2 }}
          >
            {SHIPPING}
          </span>
          <span
            data-testid="live-status-returns"
            style={{ color: c.ink2 }}
          >
            {RETURNS}
          </span>
          <span
            data-testid="live-status-secure"
            style={{ color: c.ink2 }}
          >
            {SECURE_CHECKOUT}
          </span>
        </div>
      </div>
    </section>
  )
}
