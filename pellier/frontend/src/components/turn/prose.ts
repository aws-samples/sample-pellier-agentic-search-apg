/**
 * The little markdown an answer may carry: paragraphs, bullet lines and
 * `**bold**` product names. Each visible character keeps its index in the
 * source, so a revealing render can key its spans and an unclosed `**`
 * during the reveal still reads as bold.
 *
 * Emphasis for product names and prices is applied as rendering over the
 * revealed text, never written into it: the reveal's target is the raw
 * answer, so a product card arriving mid-reveal cannot change the text
 * already on screen. Ranges are computed once over the full answer in
 * source coordinates, and a partially revealed name reads as bold from its
 * first character, the way an unclosed `**` does.
 */

export interface ProseRun {
  bold: boolean
  text: string
  /** Source index of the run's first visible character. */
  start: number
}

export interface ProseBlock {
  kind: 'p' | 'li'
  runs: ProseRun[]
}

/** A half-open `[start, end)` span of the source to render bold. */
export interface EmphasisRange {
  start: number
  end: number
}

const BULLET = /^[-*•]\s+/
const PRICE = /\$\d+(?:,\d{3})*(?:\.\d{2})?/g
const FENCE = /```[\s\S]*?```/g

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Where product names and prices sit in the full answer. Longer names win
 * over shorter ones that they contain; fenced code is left alone. Prices
 * are emphasized only when there are names to emphasize, as before.
 */
export function emphasisRanges(source: string, names: readonly string[]): EmphasisRange[] {
  const clean = Array.from(new Set(names.map(name => name.trim()).filter(Boolean))).sort(
    (a, b) => b.length - a.length,
  )
  if (clean.length === 0) return []
  const fenced: EmphasisRange[] = []
  for (const match of source.matchAll(FENCE)) {
    fenced.push({ start: match.index ?? 0, end: (match.index ?? 0) + match[0].length })
  }
  const taken: EmphasisRange[] = [...fenced]
  const overlaps = (start: number, end: number) =>
    taken.some(range => start < range.end && end > range.start)
  const found: EmphasisRange[] = []
  const claim = (pattern: RegExp) => {
    for (const match of source.matchAll(pattern)) {
      const start = match.index ?? 0
      const end = start + match[0].length
      if (overlaps(start, end)) continue
      taken.push({ start, end })
      found.push({ start, end })
    }
  }
  for (const name of clean) claim(new RegExp(escapeRegExp(name), 'gi'))
  claim(PRICE)
  return found.sort((a, b) => a.start - b.start)
}

function parseLine(line: string, offset: number, emphasis: readonly EmphasisRange[]): ProseRun[] {
  const runs: ProseRun[] = []
  const emphasized = (index: number) =>
    emphasis.some(range => index >= range.start && index < range.end)
  let marked = false
  let current: ProseRun | null = null
  let cursor = 0
  while (cursor < line.length) {
    if (line.startsWith('**', cursor)) {
      marked = !marked
      cursor += 2
      continue
    }
    const index = offset + cursor
    const bold = marked || emphasized(index)
    if (current === null || current.bold !== bold) {
      current = { bold, text: '', start: index }
      runs.push(current)
    }
    current.text += line[cursor]
    cursor += 1
  }
  return runs
}

export function parseProse(source: string, emphasis: readonly EmphasisRange[] = []): ProseBlock[] {
  const blocks: ProseBlock[] = []
  let offset = 0
  for (const rawLine of source.split('\n')) {
    const lineStart = offset
    offset += rawLine.length + 1
    const line = rawLine.trimEnd()
    if (!line.trim()) continue
    const bullet = line.match(BULLET)
    if (bullet) {
      blocks.push({
        kind: 'li',
        runs: parseLine(line.slice(bullet[0].length), lineStart + bullet[0].length, emphasis),
      })
    } else {
      blocks.push({ kind: 'p', runs: parseLine(line, lineStart, emphasis) })
    }
  }
  return blocks
}

/** The index just past the sentence that first names `needle`, or -1. */
export function sentenceEndAfter(source: string, needle: string): number {
  if (!needle) return -1
  const at = source.toLowerCase().indexOf(needle.toLowerCase())
  if (at < 0) return -1
  const rest = source.slice(at + needle.length)
  const end = rest.search(/[.!?](?=\s|$)/)
  return end < 0 ? source.length : at + needle.length + end + 1
}
