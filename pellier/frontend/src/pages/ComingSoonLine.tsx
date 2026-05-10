/**
 * ComingSoonLine - shared editorial "coming soon" line used on the
 * Storyboard and Discover minimal index pages.
 *
 * Validates Requirements 1.13.1, 1.13.2, 1.13.3.
 *
 * Contract:
 *   - Renders a centered italic Fraunces line with the caller-supplied
 *     copy (defaults to `STORYBOARD_PAGE_COMING_SOON` from copy.ts).
 *   - Copy rules from Req 1.12 apply - no emoji, no em dash, none of
 *     the forbidden tech words; the scanner in copy.test.ts enforces
 *     the authored strings in copy.ts.
 */
import { STORYBOARD_PAGE_COMING_SOON } from '../copy'

const CREAM = '#fbf4e8'
const INK = '#2d1810'
const FRAUNCES_STACK = 'Fraunces, Georgia, serif'

interface ComingSoonLineProps {
  /** Copy to render. Defaults to STORYBOARD_PAGE_COMING_SOON. */
  copy?: string
  /** Optional testId override so each page can assert on its own instance. */
  testId?: string
}

export default function ComingSoonLine({
  copy = STORYBOARD_PAGE_COMING_SOON,
  testId = 'coming-soon-line',
}: ComingSoonLineProps = {}) {
  return (
    <section
      data-testid={testId}
      style={{
        background: CREAM,
        color: INK,
        padding: '64px 24px',
        textAlign: 'center',
      }}
    >
      <p
        style={{
          fontFamily: FRAUNCES_STACK,
          fontStyle: 'italic',
          fontWeight: 400,
          fontSize: 22,
          lineHeight: 1.4,
          color: INK,
          margin: 0,
          maxWidth: 720,
          marginInline: 'auto',
        }}
      >
        {copy}
      </p>
    </section>
  )
}
