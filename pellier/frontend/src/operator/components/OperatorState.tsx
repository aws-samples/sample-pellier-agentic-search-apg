/**
 * What the desk says when it has nothing to show, or cannot show it.
 *
 * There were ten of these across four surfaces, each one a centred grey
 * paragraph in a bordered box, and the most common of them — the signed-out
 * desk — was the FIRST thing an operator ever saw. A cold sign-in wall that
 * looks like a rendering failure is the worst possible first impression of a
 * surface whose whole argument is that it can be trusted with a client record.
 *
 * One shape now, built on the shared `EmptyState` primitive so the desk and
 * the Observatory answer an absence the same way: which panel is empty, one
 * sentence in the display face, what would fill it, and the identifier an
 * attendee can go and check.
 *
 * Two surfaces:
 *
 *   `paper`  raised paper with the desk's one resting shadow. Everything
 *            ordinary: an empty queue, an unseeded book, a missing migration.
 *
 *   `plate`  the same state set over the house photograph behind an espresso
 *            scrim, matching the sign-in dialog. Reserved for the one state
 *            that is not a failure at all — the desk is working exactly as
 *            designed and is waiting for an identity. Cream on the scrim
 *            measures 6.3:1 at the scrim's floor over the brightest pixel in
 *            the plate; see `.operator-state[data-surface='plate']`.
 */
import type React from 'react'

import ResponsiveImage from '../../components/ResponsiveImage'
import { EmptyState } from '../../shared'

export type OperatorStateSurface = 'paper' | 'plate'

export interface OperatorStateProps {
  /** Names the panel that is empty, unreachable, or still loading. */
  eyebrow: string
  /** One sentence. Say what is absent, not "no data". */
  headline: React.ReactNode
  /** What would put something here, or which boundary was hit. */
  body?: React.ReactNode
  /** The identifier an operator can go and check. Rendered in mono. */
  reason?: React.ReactNode
  /** At most one recovery action. */
  action?: React.ReactNode
  /** A back link, rendered above the state and outside its reading column. */
  lead?: React.ReactNode
  /** Heading rank for the headline. `1` when this state replaces the page. */
  level?: 1 | 2 | 3
  surface?: OperatorStateSurface
  'data-testid': string
}

const OperatorState: React.FC<OperatorStateProps> = ({
  eyebrow,
  headline,
  body,
  reason,
  action,
  lead,
  level = 2,
  surface = 'paper',
  'data-testid': testId,
}) => (
  <div className="operator-state" data-surface={surface} data-testid={testId}>
    {surface === 'plate' ? (
      // Through ResponsiveImage so the AVIF and WebP derivatives are used and
      // every URL passes the Workshop Studio base path. Never a CSS url().
      <ResponsiveImage
        src="/products/hero-fresh-2.png"
        widths={[960, 1600]}
        sizes="100vw"
        pictureClassName="operator-state-plate"
        className="operator-state-plate-image"
        alt=""
        aria-hidden="true"
        decoding="async"
      />
    ) : null}
    <div className="operator-state-inner">
      {lead ? <div className="operator-state-lead">{lead}</div> : null}
      <EmptyState
        eyebrow={eyebrow}
        headline={headline}
        body={body}
        reason={reason ? <details className="operator-state-details"><summary>Technical details</summary><code>{reason}</code></details> : undefined}
        action={action}
        level={level}
        size="page"
      />
    </div>
  </div>
)

export default OperatorState
