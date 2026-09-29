/**
 * EmptyState — what a surface says when it has nothing to show.
 *
 * These two surfaces are evidence instruments, so an empty panel is a claim
 * and not a gap: nothing was recorded, nothing was provisioned, nothing was
 * denied. The Observatory and the desk had eighteen of these between them and
 * every one said it differently, several of them in 14px muted grey that read
 * as a rendering failure rather than as an answer.
 *
 * Four parts, and the order is the argument:
 *
 *   eyebrow   which panel is empty
 *   headline  one sentence, Instrument Sans 600 at 22-24px (26-32px when the
 *             state is the page). Large enough to read as an answer rather
 *             than shrinking apologetically; the tools' own heading voice.
 *   body      optional prose: what would fill it
 *   reason    optional mono line: the table, service or window that came back
 *             empty. Mono because this one is an identifier, and it is the
 *             part an attendee can go and check.
 *   action    at most one. Two actions in an empty state means the surface
 *             does not know what it wants the reader to do.
 *
 * The headline is a real heading, in the same face as every other heading on
 * the Observatory and the Operator desk. Fraunces belongs to the storefront.
 *
 * It matters because the desk's signed-out state is a whole page whose only
 * sentence is this one: rendered as a paragraph, `/operator` reached a reader
 * with no headings at all. `level` names where the state sits — `1` when the
 * state IS the page, the default `2` when it stands in for one panel.
 */
import type React from 'react'

import { SectionEyebrow } from './SectionEyebrow'

export interface EmptyStateProps {
  /** Names the panel that is empty. */
  eyebrow: string
  /** One sentence. Say what is absent, not "no data". */
  headline: React.ReactNode
  /** Optional prose: what would put something here. */
  body?: React.ReactNode
  /** Optional mono line naming the source that came back empty. */
  reason?: React.ReactNode
  /** At most one action. */
  action?: React.ReactNode
  /** Heading rank for the headline. `1` when this state replaces the page. */
  level?: 1 | 2 | 3
  /** Editorial scale for a state replacing the page, rather than a small panel. */
  size?: 'panel' | 'page'
  align?: 'start' | 'center'
  className?: string
  'data-testid'?: string
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  eyebrow,
  headline,
  body,
  reason,
  action,
  level = 2,
  size = 'panel',
  align = 'start',
  className,
  'data-testid': testId,
}) => {
  const centered = align === 'center'
  const pageSize = size === 'page'
  const Headline = `h${level}` as 'h1' | 'h2' | 'h3'

  return (
    <div
      className={className}
      data-testid={testId}
      data-align={align}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: centered ? 'center' : 'flex-start',
        textAlign: centered ? 'center' : 'left',
        gap: '12px',
      }}
    >
      <SectionEyebrow tone="muted">{eyebrow}</SectionEyebrow>

      <Headline
        style={{
          margin: 0,
          maxWidth: pageSize ? '28ch' : '46ch',
          fontFamily: 'var(--sans)',
          fontSize: pageSize ? 'clamp(26px, 2.5vw, 32px)' : 'clamp(22px, 2vw, 24px)',
          fontWeight: 600,
          lineHeight: 1.25,
          letterSpacing: '-0.02em',
          color: 'var(--obs-ink-1)',
        }}
      >
        {headline}
      </Headline>

      {body ? (
        <p
          style={{
            margin: 0,
            maxWidth: '52ch',
            fontFamily: pageSize ? 'var(--sans)' : 'var(--obs-sans)',
            fontSize: pageSize ? '16px' : '15px',
            lineHeight: pageSize ? 1.65 : 1.55,
            color: 'var(--obs-ink-3)',
          }}
        >
          {body}
        </p>
      ) : null}

      {reason ? (
        /*
         * A div, not a p. `reason` is a ReactNode and the Operator desk passes
         * a `<details><summary>Technical details</summary>` disclosure through
         * it. `<details>` is flow content, so inside a `<p>` the browser closes
         * the paragraph early: the disclosure lands outside it, loses every
         * style declared here, and React warns about the nesting on each render.
         */
        <div
          data-empty-reason="true"
          style={{
            margin: 0,
            maxWidth: '52ch',
            fontFamily: 'var(--obs-mono)',
            fontSize: '12px',
            lineHeight: 1.5,
            letterSpacing: '0.02em',
            color: 'var(--obs-ink-4)',
            overflowWrap: 'anywhere',
          }}
        >
          {reason}
        </div>
      ) : null}

      {action ? <div style={{ marginTop: '4px' }}>{action}</div> : null}
    </div>
  )
}

export default EmptyState
