/**
 * Splits editorial headlines so the "re:*" clause can use Daylight
 * `--dl-accent-ink` (deep maroon) via `text-ink-2` in the UI.
 */
export function splitHeadlineAtRe(headline: string): {
  lead: string
  tail: string | null
} {
  const i = headline.indexOf('re:')
  if (i < 0) return { lead: headline, tail: null }
  return { lead: headline.slice(0, i), tail: headline.slice(i) }
}

/**
 * Split an editorial statement around a single accent word so the accent can
 * be set in the burgundy italic of the same family.
 *
 * Returns the whole statement as `before` when `accent` is absent, so a copy
 * edit that drops the accent word degrades to an unaccented headline rather
 * than a mis-split one.
 */
export function splitHeadlineAtAccent(
  headline: string,
  accent: string,
): { before: string; accent: string | null; after: string } {
  if (!accent) return { before: headline, accent: null, after: '' }
  const i = headline.indexOf(accent)
  if (i < 0) return { before: headline, accent: null, after: '' }
  return {
    before: headline.slice(0, i),
    accent,
    after: headline.slice(i + accent.length),
  }
}
