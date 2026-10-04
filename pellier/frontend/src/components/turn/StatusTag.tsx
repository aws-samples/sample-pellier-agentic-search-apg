/**
 * A small status pill in one of three roles.
 *
 * Green means good or done (In stock, Delivered, Approved, ALLOW, Recorded
 * once). Red means blocked or needing attention (Sold out, Returned, DENY,
 * Declined, Not found). Neutral grey is pending. Copper is never a status
 * color; a pending tag may carry the pulsing copper dot while someone waits.
 * The word always carries the meaning, so the tag reads without its color.
 */
import type { ReactNode } from 'react'

export type TagTone = 'good' | 'blocked' | 'pending'

export interface StatusTagProps {
  tone: TagTone
  children: ReactNode
  /** Show the pulsing copper dot, for work someone is waiting on. */
  pulse?: boolean
  className?: string
}

export default function StatusTag({ tone, children, pulse = false, className }: StatusTagProps) {
  return (
    <span
      className={['tn-tag', className ?? ''].filter(Boolean).join(' ')}
      data-tone={tone}
      data-testid="status-tag"
    >
      {pulse && <span className="tn-dot tn-dot-sm" aria-hidden="true" />}
      {children}
    </span>
  )
}
