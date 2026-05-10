/**
 * StatusBadge — the small-caps pill used across architecture pages.
 *
 * Variant → usage mapping (documented so renames stay coherent):
 *
 *   active    — burgundy filled    Skills loaded, MCP tool fired, Tool Registry grant active
 *   considered — cream-2 hairline   Skills evaluated-but-not-loaded
 *   dormant   — transparent hairline Skills never signaled this turn
 *   fired     — burgundy filled     MCP/Tool Registry tool fired this turn (alias of active)
 *   idle      — transparent hairline MCP/Tool Registry tool not fired (alias of dormant)
 *   touched   — burgundy-soft       State Management table touched this turn
 *   pass      — green filled        Evaluations axis passed
 *   watch     — cream-2 hairline    Evaluations axis borderline
 *   fail      — espresso filled     Evaluations axis failed
 *   success   — green filled        Generic success (alias of pass)
 *   warning   — amber filled        Generic warning budget breach
 *   error     — espresso filled     Generic error (alias of fail)
 */
import type { ReactNode } from 'react'

export type StatusBadgeVariant =
  | 'active'
  | 'considered'
  | 'dormant'
  | 'fired'
  | 'idle'
  | 'touched'
  | 'pass'
  | 'watch'
  | 'fail'
  | 'success'
  | 'warning'
  | 'error'

export interface StatusBadgeProps {
  variant: StatusBadgeVariant
  children: ReactNode
}

export default function StatusBadge({ variant, children }: StatusBadgeProps) {
  return <span className={`at-badge at-badge-${variant}`}>{children}</span>
}
