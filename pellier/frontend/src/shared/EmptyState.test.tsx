/**
 * EmptyState contract.
 *
 * Two things must hold or the primitive is pointless.
 *
 * The headline keeps the display face. On the Observatory that is fragile:
 * `base.css` forces every heading to sans with `!important`, and `index.css`
 * forces `.font-display` back to sans on top of that. A paragraph carrying an
 * inline family is the one form that survives both, so the test pins the tag
 * as well as the family.
 *
 * And the reason line stays monospace and separate from the prose, because it
 * is the part naming a source an attendee can go and query.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { EmptyState } from './EmptyState'

describe('EmptyState', () => {
  it('sets the headline in the display face at 22 to 24px', () => {
    render(
      <EmptyState
        eyebrow="No telemetry"
        headline="No telemetry panels have been recorded for this session."
        data-testid="empty"
      />,
    )

    const headline = screen.getByText(
      'No telemetry panels have been recorded for this session.',
    )
    expect(headline).toHaveStyle({
      fontFamily: 'var(--display)',
      fontSize: 'clamp(22px, 2vw, 24px)',
      fontWeight: '400',
    })
  })

  it('renders the headline as a heading that keeps the display face', () => {
    // Both halves matter and they used to be in tension. `.font-display`
    // exempts the element from the Observatory's !important family rule, and
    // the inline family outranks the storefront's plain-class rule that would
    // otherwise pull it back to sans. Losing either one silently costs the
    // page its heading or its voice.
    render(<EmptyState eyebrow="Empty" headline="Nothing was recorded." />)
    const headline = screen.getByRole('heading', { level: 2 })
    expect(headline.tagName).toBe('H2')
    expect(headline).toHaveTextContent('Nothing was recorded.')
    expect(headline.classList.contains('font-display')).toBe(true)
    expect(headline).toHaveStyle({ fontFamily: 'var(--display)' })
  })

  it('takes the rank of the thing it stands in for', () => {
    // `/operator` signed out is a whole page whose only sentence is this one;
    // rendered at the default rank it reached a reader with no h1 at all.
    render(
      <EmptyState eyebrow="Client book" headline="Sign in required." level={1} />,
    )
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Sign in required.',
    )
  })

  it('opens with the eyebrow in the shared label recipe', () => {
    render(<EmptyState eyebrow="No telemetry" headline="Nothing yet." />)
    const eyebrow = screen.getByText('No telemetry')
    expect(eyebrow).toHaveAttribute('data-tone', 'muted')
    expect(eyebrow).toHaveStyle({ fontSize: '11px', fontWeight: '600' })
  })

  it('keeps the reason line in mono and apart from the prose', () => {
    render(
      <EmptyState
        eyebrow="No telemetry"
        headline="Nothing was recorded."
        body="Panels appear as the system processes each step."
        reason="pellier.observatory_spans: 0 rows for this session"
        data-testid="empty"
      />,
    )

    const reason = screen.getByText(
      'pellier.observatory_spans: 0 rows for this session',
    )
    expect(reason).toHaveAttribute('data-empty-reason', 'true')
    expect(reason).toHaveStyle({ fontFamily: 'var(--obs-mono)' })

    const body = screen.getByText(
      'Panels appear as the system processes each step.',
    )
    expect(body).toHaveStyle({ fontFamily: 'var(--obs-sans)' })

    // The Operator desk passes a `<details>` disclosure as the reason. Inside a
    // `<p>` the browser closes the paragraph early, so the disclosure escapes
    // the styled wrapper and React warns on every render.
    expect(reason.tagName).not.toBe('P')

    expect(body).not.toHaveAttribute('data-empty-reason')
  })

  it('omits the optional slots entirely rather than reserving space', () => {
    const { container } = render(
      <EmptyState eyebrow="Empty" headline="Nothing was recorded." />,
    )
    expect(container.querySelector('[data-empty-reason]')).toBeNull()
    // The eyebrow and the headline, and nothing standing in for the slots
    // that were not given. The headline is the heading, so no paragraph
    // belongs to this state at all.
    expect(container.querySelectorAll('p')).toHaveLength(0)
    expect(container.querySelectorAll('h2')).toHaveLength(1)
  })

  it('renders the single action it is given', () => {
    render(
      <EmptyState
        eyebrow="Empty"
        headline="Nothing was recorded."
        action={<button type="button">Run a benchmark</button>}
      />,
    )
    expect(
      screen.getByRole('button', { name: 'Run a benchmark' }),
    ).toBeInTheDocument()
  })

  it('centres only when asked, and says which alignment it used', () => {
    const { unmount } = render(
      <EmptyState eyebrow="Empty" headline="Nothing." data-testid="empty" />,
    )
    expect(screen.getByTestId('empty')).toHaveAttribute('data-align', 'start')
    expect(screen.getByTestId('empty')).toHaveStyle({ textAlign: 'left' })
    unmount()

    render(
      <EmptyState
        eyebrow="Empty"
        headline="Nothing."
        align="center"
        data-testid="empty"
      />,
    )
    expect(screen.getByTestId('empty')).toHaveStyle({ textAlign: 'center' })
  })
})
