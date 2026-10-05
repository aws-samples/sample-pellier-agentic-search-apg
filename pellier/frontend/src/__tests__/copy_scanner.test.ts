// @vitest-environment node
/**
 * The copy scanner as a gate: `npm test` fails when `copy.ts` or a copy file
 * in data/ breaks a copy rule, and each rule still catches what it exists to
 * catch.
 */
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { ALLOWED_SENTENCES, DATA_DIR, DATA_NOT_COPY, dataCopyFiles, scan } from './copy.test.mjs'

const COPY = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '..', 'copy.ts'), 'utf-8')

describe('copy scanner', () => {
  it('finds no violation in copy.ts', () => {
    expect(scan(COPY)).toEqual([])
  })

  it('finds no violation in the copy files in data/', async () => {
    const files = await dataCopyFiles()
    expect(files).toEqual(expect.arrayContaining(['personas.json', 'scenarios.json', 'pellier_catalog.json']))
    for (const name of DATA_NOT_COPY.keys()) expect(existsSync(resolve(DATA_DIR, name)), name).toBe(true)
    for (const name of files) {
      expect(scan(readFileSync(resolve(DATA_DIR, name), 'utf-8'), `data/${name}`), name).toEqual([])
    }
  })

  it('flags an en dash used as a dash, and keeps one in a range', () => {
    expect(scan('{"prompt": "my brother\'s wedding \u2013 not product cards"}', 'data/x.json').join('\n'))
      .toMatch(/data\/x\.json:1:.*en dash \(U\+2013\) used as a dash/)
    expect(scan('{"prompt": "ships in 3\u20135 days"}', 'data/x.json')).toEqual([])
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
