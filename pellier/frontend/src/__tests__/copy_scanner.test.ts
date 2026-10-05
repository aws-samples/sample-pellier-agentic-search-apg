// @vitest-environment node
/**
 * The copy scanner as a gate: `npm test` fails when `copy.ts` breaks a copy
 * rule, and each rule still catches what it exists to catch.
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { ALLOWED_SENTENCES, scan } from './copy.test.mjs'

const COPY = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '..', 'copy.ts'), 'utf-8')

describe('copy scanner', () => {
  it('finds no violation in copy.ts', () => {
    expect(scan(COPY)).toEqual([])
  })

  it('still flags search as a noun, an em dash, a middle dot and the AI rule', () => {
    expect(scan('export const A = "Your search results";')).toHaveLength(1)
    expect(scan('export const A = "One — two";').join('\n')).toMatch(/em dash/)
    expect(scan('export const A = "One \\u00b7 two";').join('\n')).toMatch(/middle dot/)
    expect(scan('export const A = "AI picks for you";').join('\n')).toMatch(/forbidden word "AI"/)
  })

  it('exempts only the named sentence, verbatim', () => {
    expect(ALLOWED_SENTENCES.map(sentence => sentence.name)).toEqual(['footer imagery disclosure'])
    const sentence = ALLOWED_SENTENCES[0].text
    expect(scan(`export const A = "${sentence}";`)).toEqual([])
    expect(scan('export const A = "AI-generated imagery is lovely.";')).toHaveLength(1)
  })

  it('exempts a URL from the word rules, not the copy around it', () => {
    expect(scan('export const A = "https://github.com/aws-samples/agentic-search";')).toEqual([])
    expect(scan('export const A = "Search https://example.com";')).toHaveLength(1)
  })

  it('honors the search-as-verb marker on its own line only', () => {
    expect(scan('export const A = "Search the shelf"; // copy-allow: search-as-verb')).toEqual([])
    expect(scan('export const A = "Search the shelf";')).toHaveLength(1)
  })
})
