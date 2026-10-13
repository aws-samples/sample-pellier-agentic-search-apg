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
      mentionIndex: mentionOf(normalizedContent, product.name),
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

const WORD_CHAR = /[\p{L}\p{N}]/u

/**
 * Where the answer first names a piece: the whole catalog name, or the part
 * before an em-dash variant suffix ("Linen Throw — Sage" named as "Linen
 * Throw"). A name matches as whole words, allowing a plain plural ("Hadley
 * Linen Shirts"), so a short name never matches inside another word.
 */
export function mentionOf(normalizedContent: string, name: string): number {
  if (!name) return -1
  const forms = [name]
  const base = name.split(' — ')[0].trim()
  if (base && base !== name) forms.push(base)
  for (const form of forms) {
    const index = wholeNameIndex(normalizedContent, form.toLowerCase())
    if (index >= 0) return index
  }
  return -1
}

function wholeNameIndex(content: string, name: string): number {
  for (let from = 0; ; from += 1) {
    const at = content.indexOf(name, from)
    if (at < 0) return -1
    const before = at === 0 ? '' : content[at - 1]
    const rest = content.slice(at + name.length)
    const plural = /^(es|s)(?![\p{L}\p{N}])/u.exec(rest)
    const after = plural ? '' : rest.charAt(0)
    if (!WORD_CHAR.test(before) && !WORD_CHAR.test(after)) return at
    from = at
  }
}
