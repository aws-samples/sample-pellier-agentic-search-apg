/**
 * CommandPill - floating shopper-chat shortcut pill.
 *
 * Validates Requirements 1.11.1 and 1.11.5.
 *
 * Contract:
 *   - Fixed in the bottom-right corner on every page (Req 1.11.1).
 *   - Compact dusk pill with a small brand mark, the `Ask Pellier` label,
 *     and a styled `Cmd K` keycap.
 *   - Clicking the pill toggles the shopper drawer via
 *     `useUI().toggleDrawer()` (Req 1.11.5) - the same behavior as
 *     the global Cmd+K / Ctrl+K shortcut (Req 1.11.2).
 *
 * Copy comes from the COMMAND_PILL block in copy.ts so the scanner
 * in `src/__tests__/copy.test.ts` keeps it honest. Platform detection
 * swaps the macOS command glyph for `Ctrl K` on non-Mac platforms.
 */
import { useEffect, useState } from 'react'

import { COMMAND_PILL } from '../copy'
import PellierMark from './PellierMark'
import { usePersona } from '../contexts/PersonaContext'
import { useUI } from '../contexts/UIContext'

function detectMac(): boolean {
  if (typeof navigator === 'undefined') return false
  // userAgentData is the forward-compatible API; fall back to platform.
  const uaData = (navigator as unknown as {
    userAgentData?: { platform?: string }
  }).userAgentData
  const platform = uaData?.platform ?? navigator.platform ?? ''
  return /mac|iphone|ipad|ipod/i.test(platform)
}

export default function CommandPill() {
  const { toggleDrawer, activeModal, chatSurface } = useUI()
  const { persona } = usePersona()
  const [isMac, setIsMac] = useState(false)

  useEffect(() => {
    setIsMac(detectMac())
  }, [])

  // Hide the pill while the drawer is open — no reason for two entry
  // points to the same surface to be visible simultaneously.
  if (!persona) return null
  if (chatSurface === 'none') return null
  if (activeModal === 'drawer') return null

  const keycap = isMac ? COMMAND_PILL.KEY_CAP_MAC : COMMAND_PILL.KEY_CAP_WIN

  return (
    <button
      type="button"
      data-testid="command-pill"
      aria-label={`${COMMAND_PILL.LABEL} (${keycap})`}
      aria-pressed={false}
      onClick={toggleDrawer}
      className="concierge-glow fixed bottom-6 right-6 z-40 inline-flex items-center gap-2.5 rounded-full bg-espresso/95 backdrop-blur-md text-cream-50 border-none font-sans text-[13px] font-medium tracking-[0.01em] cursor-pointer transition-transform duration-fade"
      style={{
        padding: '10px 14px 10px 10px',
        WebkitBackdropFilter: 'blur(12px)',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = 'translateY(-1px)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = 'translateY(0)'
      }}
    >
      <PellierMark size={22} data-testid="command-pill-pmark" />
      <span
        data-testid="command-pill-label"
        className="font-sans whitespace-nowrap"
      >
        {COMMAND_PILL.LABEL}
      </span>
      <span
        aria-hidden="true"
        data-testid="command-pill-keycap"
        className="inline-flex items-center justify-center px-2 py-0.5 rounded-md border border-ink-quiet bg-sand/50 text-espresso font-sans text-[11px] font-semibold tracking-[0.02em] min-w-[28px]"
      >
        {keycap}
      </span>
    </button>
  )
}
