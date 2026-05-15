/**
 * Splits editorial headlines so the "re:*" clause can use Daylight
 * `--dl-accent-ink` (deep maroon) via `text-accent-ink` in the UI.
 */
export function splitHeadlineAtRe(headline: string): {
  lead: string
  tail: string | null
} {
  const i = headline.indexOf('re:')
  if (i < 0) return { lead: headline, tail: null }
  return { lead: headline.slice(0, i), tail: headline.slice(i) }
}
