/**
 * One line naming what Pellier is doing now, with the signature copper dot.
 *
 * The dot pulses while work is in progress and stops when it ends. Failure is
 * its own calm state: no pulse, a quiet ring, the same type.
 *
 * The line is a polite, atomic live region: when the label changes, a screen
 * reader speaks the whole new step once, without interrupting.
 */
import type { TurnState } from './turnTypes'

export interface StatusLineProps {
  label: string
  state: TurnState
  className?: string
}

export default function StatusLine({ label, state, className }: StatusLineProps) {
  return (
    <div
      className={['tn-status', className ?? ''].filter(Boolean).join(' ')}
      data-state={state}
      data-testid="turn-status"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <span className="tn-dot" aria-hidden="true" />
      <span className="tn-status-label">{label}</span>
    </div>
  )
}
