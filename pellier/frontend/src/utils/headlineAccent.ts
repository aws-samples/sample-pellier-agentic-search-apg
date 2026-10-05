/**
 * Split an editorial statement around a single accent word so the accent can
 * be set apart as an `<em>` in the same face.
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
