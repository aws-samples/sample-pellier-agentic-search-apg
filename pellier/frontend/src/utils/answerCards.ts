/**
 * The answer's cards, from one place.
 *
 * Ask Pellier shows a card for each piece its answer names ("Pulled for
 * you"); the page grid leads with the same pieces, and the history sent with
 * the next turn carries them, so the three never disagree.
 */

/**
 * The most pieces one answer shows as cards. Four lay out two by two in the
 * panel. The backend bounds the history it accepts by the same number
 * (`ANSWER_CARDS_MAX` in `models/search.py`).
 */
export const ANSWER_CARDS_MAX = 4

/**
 * The pieces an answer shows as cards: those its words name, in order of first
 * mention, at most `ANSWER_CARDS_MAX`.
 */
export function productsNamedInAnswer<T extends { name: string }>(products: readonly T[], content: string): T[] {
  const normalizedContent = content.toLowerCase()

  return products
    .map((product, index) => ({
      product,
      index,
      mentionIndex: product.name
        ? normalizedContent.indexOf(product.name.toLowerCase())
        : -1,
    }))
    .filter((item) => item.mentionIndex >= 0)
    .sort((a, b) =>
      a.mentionIndex === b.mentionIndex
        ? a.index - b.index
        : a.mentionIndex - b.mentionIndex,
    )
    .map((item) => item.product)
    .slice(0, ANSWER_CARDS_MAX)
}
