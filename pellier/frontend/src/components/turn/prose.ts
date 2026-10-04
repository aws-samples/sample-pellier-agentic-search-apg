/**
 * The little markdown an answer may carry: paragraphs, bullet lines and
 * `**bold**` product names. Each visible character keeps its index in the
 * source, so a revealing render can key its spans and an unclosed `**`
 * during the reveal still reads as bold.
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

const BULLET = /^[-*•]\s+/

function parseLine(line: string, offset: number): ProseRun[] {
  const runs: ProseRun[] = []
  let bold = false
  let cursor = 0
  let start = offset
  let text = ''
  while (cursor < line.length) {
    if (line.startsWith('**', cursor)) {
      if (text) runs.push({ bold, text, start })
      bold = !bold
      cursor += 2
      start = offset + cursor
      text = ''
      continue
    }
    text += line[cursor]
    cursor += 1
  }
  if (text) runs.push({ bold, text, start })
  return runs
}

export function parseProse(source: string): ProseBlock[] {
  const blocks: ProseBlock[] = []
  let offset = 0
  for (const rawLine of source.split('\n')) {
    const lineStart = offset
    offset += rawLine.length + 1
    const line = rawLine.trimEnd()
    if (!line.trim()) continue
    const bullet = line.match(BULLET)
    if (bullet) {
      blocks.push({ kind: 'li', runs: parseLine(line.slice(bullet[0].length), lineStart + bullet[0].length) })
    } else {
      blocks.push({ kind: 'p', runs: parseLine(line, lineStart) })
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
