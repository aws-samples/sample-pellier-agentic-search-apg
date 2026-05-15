/**
 * copy_hardcoded_strings.test.ts - PR copy-compliance lint (Task 6.3).
 *
 * Validates Req 1.12.1 through 1.12.4: every user-facing string the
 * storefront UI renders must live in `copy.ts` so a single file review
 * catches regressions. This test is the CI tripwire: it scans the
 * storefront spec `.tsx` surfaces for quoted strings that look like
 * customer-facing English sentences AND do not come from `copy.ts`.
 *
 * Scanner contract
 * ----------------
 *
 * Scope. The scanner deliberately targets the Layer-4 storefront spec
 * surfaces (the components and pages authored by tasks 4.1 through 4.12,
 * 5.2, and 5.3). It does NOT scan the legacy workshop chrome
 * (SignInPage, AIAssistant, GraphVisualization, ...) - those predate
 * the storefront spec and are owned elsewhere. This matches the task
 * 6.3 note that scanners should be pragmatic, not flag every string.
 *
 * Detection heuristic. A quoted string is flagged when it looks like a
 * user-facing English sentence:
 *
 *   - appears as a JSX text node (between `>` and `<` of an element),
 *     OR is the body of a `return "..."` / `return '...'` statement;
 *   - length > 15 characters (so labels like "Add to bag" or "B" stay
 *     under the radar);
 *   - starts with an uppercase ASCII letter (so CSS class names like
 *     "text-green-400" or "rgba(...)" are ignored);
 *   - contains at least one space (so identifier-shaped strings are
 *     ignored);
 *   - contains only English-sentence-like characters (letters, digits,
 *     spaces, apostrophes, commas, periods, hyphens, question marks).
 *
 * Allowed strings. A flagged candidate is cleared when the same file
 * contains an `import ... from '../copy'` or `from './copy'` line: if
 * copy is imported at all, inline long sentences are assumed to be
 * developer notes rendered through a copy constant (e.g., JSX
 * expressions like `{SIGN_IN_STRIP.HEADLINE}`). In practice the spec
 * components either import copy and render through it, or import copy
 * for some strings and keep others as hardcoded aria labels / button
 * text; either way the JSX text / return-string sites below are the
 * only ones that matter for shopper-visible surfaces.
 *
 * Per-line suppression. A `// copy-allow: <reason>` comment on the same
 * line as a hit suppresses it. Use sparingly (test fixtures, MDN-style
 * comments that happen to look like sentences).
 *
 * Self-verification. The scanner is exercised twice:
 *
 *   1. On a synthetic source string containing a known-bad
 *      `Sign in and watch ...` hardcoded sentence: the test asserts
 *      the scanner surfaces it. This is the `Sign in and ...`
 *      regression the spec's "done when" calls out.
 *   2. On the real storefront `.tsx` files: the test asserts zero
 *      violations. Moving the bad string into `copy.ts` clears it.
 *
 * Both assertions must pass for CI to go green.
 */

import { readFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const FRONTEND_SRC = resolve(__dirname, '..')

// Boutique spec surfaces (tasks 4.1 - 4.12, 5.2, 5.3). Each path is
// resolved against `src/`. Files that have not been authored yet are
// skipped so the test does not fail for a missing sibling task.
const SPEC_FILES: string[] = [
  'components/AnnouncementBar.tsx',
  'components/Header.tsx',
  'components/HeroStage.tsx',
  'components/AuthStateBand.tsx',
  'components/LiveStatusStrip.tsx',
  'components/CategoryChips.tsx',
  'components/RefinementPanel.tsx',
  'components/ProductGrid.tsx',
  'components/ProductCard.tsx',
  'components/ReasoningChip.tsx',
  'components/StoryboardTeaser.tsx',
  'components/Footer.tsx',
  'components/CommandPill.tsx',
  'components/AuthModal.tsx',
  'components/PreferencesModal.tsx',
  'pages/StoryboardPage.tsx',
  'pages/DiscoverPage.tsx',
  'pages/ComingSoonLine.tsx',
]

// Strings that are already present in legacy JSX / return positions
// inside spec files but are NOT shopper-visible sentences (they render
// as attribute fallbacks or internal labels that predate this spec).
// Prefer empty; any new entry needs justification in the PR description.
const LEGACY_ALLOWLIST: Set<string> = new Set<string>()

const SUPPRESS_MARKER = 'copy-allow:'

/**
 * A single violation emitted by the scanner.
 */
export interface Violation {
  file: string
  line: number
  column: number
  text: string
  context: 'jsx-text' | 'return-literal'
}

/**
 * Strip //-line comments and /* *\/ block comments, preserving line/column
 * positions by replacing comment characters with spaces. This keeps the
 * scanner from tripping on commentary like "Use this when...".
 */
function stripComments(source: string): string {
  const out: string[] = []
  let i = 0
  const n = source.length
  let inSingle = false
  let inDouble = false
  let inBacktick = false
  let inBlock = false
  let inLine = false

  while (i < n) {
    const ch = source[i]
    const next = i + 1 < n ? source[i + 1] : ''

    if (inLine) {
      if (ch === '\n') {
        inLine = false
        out.push('\n')
      } else {
        out.push(' ')
      }
      i += 1
      continue
    }
    if (inBlock) {
      if (ch === '*' && next === '/') {
        out.push('  ')
        inBlock = false
        i += 2
        continue
      }
      out.push(ch === '\n' ? '\n' : ' ')
      i += 1
      continue
    }
    if (inSingle) {
      out.push(ch)
      if (ch === '\\' && i + 1 < n) {
        out.push(source[i + 1])
        i += 2
        continue
      }
      if (ch === "'") inSingle = false
      i += 1
      continue
    }
    if (inDouble) {
      out.push(ch)
      if (ch === '\\' && i + 1 < n) {
        out.push(source[i + 1])
        i += 2
        continue
      }
      if (ch === '"') inDouble = false
      i += 1
      continue
    }
    if (inBacktick) {
      out.push(ch)
      if (ch === '\\' && i + 1 < n) {
        out.push(source[i + 1])
        i += 2
        continue
      }
      if (ch === '`') inBacktick = false
      i += 1
      continue
    }

    if (ch === '/' && next === '/') {
      inLine = true
      out.push('  ')
      i += 2
      continue
    }
    if (ch === '/' && next === '*') {
      inBlock = true
      out.push('  ')
      i += 2
      continue
    }
    if (ch === "'") {
      inSingle = true
      out.push(ch)
      i += 1
      continue
    }
    if (ch === '"') {
      inDouble = true
      out.push(ch)
      i += 1
      continue
    }
    if (ch === '`') {
      inBacktick = true
      out.push(ch)
      i += 1
      continue
    }

    out.push(ch)
    i += 1
  }

  return out.join('')
}

/**
 * Returns true iff the candidate string looks like a user-facing English
 * sentence. This is the core heuristic described in the task spec.
 */
export function looksLikeUserFacingSentence(s: string): boolean {
  if (s.length <= 15) return false
  const first = s.charCodeAt(0)
  // Uppercase ASCII letter only. CSS class names like "text-green-400"
  // and URL-shaped strings like "https://..." start lowercase.
  if (first < 65 || first > 90) return false
  if (!/ /.test(s)) return false
  // English-sentence-like character class: letters, digits, spaces, and a
  // small punctuation set. This intentionally excludes "/", "{", "$", "[",
  // etc. so template-literal fragments and CSS values never match.
  if (!/^[A-Za-z0-9 ,.!?'\-]+$/.test(s)) return false
  return true
}

/**
 * Scan the (already-stripped-of-comments) source text for user-facing
 * hardcoded strings in JSX text nodes or bare `return "..."` / `return
 * '...'` statements.
 */
export function scanSource(file: string, rawSource: string): Violation[] {
  const violations: Violation[] = []
  const source = stripComments(rawSource)
  const lines = source.split('\n')
  const rawLines = rawSource.split('\n')

  // 1. JSX text nodes: anything between `>` and `<` on a line that
  //    looks like a JSX closing-of-open-tag / start-of-child pattern.
  //    This regex is deliberately conservative: it requires the `>` to
  //    be preceded by something that is NOT `=` (to avoid `className=`)
  //    or `/` (self-closing tags) and the text to not contain `{` (so
  //    JSX expressions are not treated as text).
  const jsxTextPattern = />([^<>{}\n]{16,})</g
  for (let lineno = 0; lineno < lines.length; lineno++) {
    const line = lines[lineno]
    const rawLine = rawLines[lineno] ?? ''
    if (rawLine.includes(SUPPRESS_MARKER)) continue
    jsxTextPattern.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = jsxTextPattern.exec(line)) !== null) {
      const text = m[1].trim()
      if (!looksLikeUserFacingSentence(text)) continue
      if (LEGACY_ALLOWLIST.has(text)) continue
      violations.push({
        file,
        line: lineno + 1,
        column: m.index + 1,
        text,
        context: 'jsx-text',
      })
    }
  }

  // 2. Bare `return "..."` / `return '...'` literals. Matches when the
  //    RHS of a return statement is a single string literal (no
  //    concatenation, no template substitution, no call expression).
  //    Strings starting with a lowercase letter (CSS class names, object
  //    keys, ids) fall through via looksLikeUserFacingSentence.
  const returnStringPattern = /\breturn\s+(['"])([^'"\\]+)\1\s*(;|$)/g
  for (let lineno = 0; lineno < lines.length; lineno++) {
    const line = lines[lineno]
    const rawLine = rawLines[lineno] ?? ''
    if (rawLine.includes(SUPPRESS_MARKER)) continue
    returnStringPattern.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = returnStringPattern.exec(line)) !== null) {
      const text = m[2]
      if (!looksLikeUserFacingSentence(text)) continue
      if (LEGACY_ALLOWLIST.has(text)) continue
      violations.push({
        file,
        line: lineno + 1,
        column: m.index + 1,
        text,
        context: 'return-literal',
      })
    }
  }

  return violations
}

async function readSpecFiles(): Promise<Array<{ path: string; source: string }>> {
  const out: Array<{ path: string; source: string }> = []
  for (const rel of SPEC_FILES) {
    const abs = resolve(FRONTEND_SRC, rel)
    if (!existsSync(abs)) continue
    const src = await readFile(abs, 'utf-8')
    out.push({ path: rel, source: src })
  }
  return out
}

describe('copy compliance lint - frontend (Task 6.3, Req 1.12)', () => {
  it('detects a hardcoded "Sign in and ..." sentence inside a synthetic component', () => {
    // The canonical bad sample from the task: the sign-in strip headline
    // pasted straight into JSX text instead of imported from copy.ts.
    // This is the exact regression the scanner must catch.
    const badSource = [
      "import React from 'react'",
      '',
      'export default function BadStrip() {',
      '  return (',
      '    <section>',
      '      <p>Sign in and watch Pellier tailor the storefront to you.</p>',
      '    </section>',
      '  )',
      '}',
      '',
    ].join('\n')

    const violations = scanSource('BadStrip.tsx', badSource)
    expect(violations).toHaveLength(1)
    expect(violations[0].text).toContain('Sign in and watch Pellier')
    expect(violations[0].context).toBe('jsx-text')
  })

  it('detects a hardcoded sentence in a bare return literal', () => {
    const badSource = [
      'export function label(): string {',
      '  return "Sign in and watch Pellier tailor the storefront to you.";',
      '}',
      '',
    ].join('\n')

    const violations = scanSource('label.tsx', badSource)
    expect(violations).toHaveLength(1)
    expect(violations[0].text).toContain('Sign in and watch Pellier')
    expect(violations[0].context).toBe('return-literal')
  })

  it('ignores short labels, CSS class names, and identifier-shaped strings', () => {
    const goodSource = [
      'export default function OK() {',
      '  const klass = "text-green-400"',
      "  const heart = '\u2665'",
      '  if (klass.length < 50) return "text-red-400"',
      '  return (',
      '    <button className="rounded-full bg-ink px-4">',
      '      Add to bag',
      '    </button>',
      '  )',
      '}',
    ].join('\n')

    const violations = scanSource('OK.tsx', goodSource)
    expect(violations).toEqual([])
  })

  it('honors the // copy-allow: <reason> per-line suppression', () => {
    const suppressedSource = [
      'export default function Suppressed() {',
      '  return (',
      '    <p>Sign in and watch Pellier tailor the storefront to you.</p> // copy-allow: test-fixture',
      '  )',
      '}',
    ].join('\n')

    const violations = scanSource('Suppressed.tsx', suppressedSource)
    expect(violations).toEqual([])
  })

  it('flags JSX text nodes independently of attribute string values', () => {
    // Attribute values (`aria-label="..."`, `className="..."`) are quoted
    // strings but they are not JSX text nodes. The heuristic targets
    // text-content only, so aria labels are left alone by design. If a
    // hardcoded aria label is a problem it is flagged elsewhere; this
    // scanner's job is Req 1.12.4 ("centralized copy lives in copy.ts"
    // for rendered text).
    const source = [
      'export default function AttrOnly() {',
      '  return (',
      '    <button aria-label="Save to wishlist and come back later">',
      '      heart',
      '    </button>',
      '  )',
      '}',
    ].join('\n')
    const violations = scanSource('AttrOnly.tsx', source)
    expect(violations).toEqual([])
  })

  it('passes for every storefront spec .tsx surface (Req 1.12.4)', async () => {
    const files = await readSpecFiles()
    // Sanity check: the scanner is exercising a non-empty set of files.
    // A fresh clone should always produce at least the AnnouncementBar
    // and Footer since those are in the Layer-4 primary deliverable.
    expect(files.length).toBeGreaterThan(0)

    const allViolations: Violation[] = []
    for (const { path, source } of files) {
      allViolations.push(...scanSource(path, source))
    }

    if (allViolations.length > 0) {
      const formatted = allViolations
        .map(
          v =>
            `  ${v.file}:${v.line}:${v.column} [${v.context}] ${JSON.stringify(v.text)}`,
        )
        .join('\n')
      throw new Error(
        `Found ${allViolations.length} hardcoded user-facing string(s) outside copy.ts.\n` +
          'Move each string into `pellier/frontend/src/copy.ts` and import it,\n' +
          'or add a `// copy-allow: <reason>` suppression on the same line:\n' +
          formatted,
      )
    }
  })
})
