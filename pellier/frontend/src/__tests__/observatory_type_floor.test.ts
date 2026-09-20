/**
 * The Observatory and the Operator desk never render text below 11px.
 *
 * WORKSHOP.md states this to co-speakers as a shipped property of the surface,
 * and until this test existed nothing enforced it. Half the Observatory had
 * drifted to caption sizes and 22% of the Operator desk sat below 10px --
 * stat tiles, table headers, definition terms, status chips -- which is what
 * made two surfaces that share the storefront's palette and typefaces read as
 * a different, smaller product.
 *
 * 11px is the storefront's eyebrow size. Below it, tracked uppercase stops
 * being text and becomes texture, and on a 14-inch workshop laptop at the back
 * of a room it stops being anything at all.
 *
 * If you need a smaller size, the answer is almost always that weight, colour
 * or letter-spacing should carry the distinction instead. If it genuinely is
 * not, add the file to ALLOWED_BELOW_FLOOR with the reason.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, extname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const HERE = dirname(fileURLToPath(import.meta.url))
const SRC = resolve(HERE, '..')

// Two directories plus the shared files that render *on* those surfaces.
// `TurnReceipt` takes `surface="observatory"`, so it and its stylesheet are
// part of the Observatory even though they live under components/ and
// styles/. A guard scoped to directories missed exactly that.
//
// `shared/` holds the design primitives -- SectionEyebrow, EvidenceCard,
// DataTable, StateBadge, EmptyState -- that both surfaces compose. A size
// that drifts there drifts on both at once, which is the worst version of
// this defect, so the primitives are inside the fence from the day they land.
//
// `styles/observatory-arch.css` used to be listed here. It was retired with
// the rest of the legacy `at-*` architecture set (`components/observatory/`
// plus `styles/observatory-shared.css`), which no file imported: the
// architecture pages render through `observatory/surfaces/understand/`. The
// entry is gone rather than kept as a dead path, because `walk` returns an
// empty list for a missing file and a scan root that matches nothing passes
// forever.
const SCAN_ROOTS = [
  join(SRC, 'observatory'),
  join(SRC, 'operator'),
  join(SRC, 'shared'),
  join(SRC, 'styles', 'turn-receipt.css'),
  join(SRC, 'components', 'TurnReceipt.tsx'),
]

const SCAN_EXTENSIONS = new Set(['.css', '.ts', '.tsx'])

/** Files permitted to fall below the floor, each with a stated reason. */
const ALLOWED_BELOW_FLOOR = new Map<string, string>([
  // (empty today; add with a reason rather than lowering the floor)
])

const FLOOR_PX = 11

// `font-size: 9.5px` in CSS and `fontSize: '10px'` in inline React styles.
// Matches only explicit px values -- rem, em, clamp() and var() are resolved
// elsewhere and are not what drifted.
const CSS_PX = /font-size:\s*(\d+(?:\.\d+)?)px/g
const INLINE_PX = /fontSize:\s*'(\d+(?:\.\d+)?)px'/g

// The `font` shorthand (`font: [style] [variant] [weight] size[/line-height]
// family`) buries its size between optional leading keywords/numeric weights
// and the mandatory family. This surface uses the shorthand throughout
// (`font: 600 11px/1.5 var(--obs-sans)`), and CSS_PX above only matches the
// longhand `font-size:` property, so a shorthand line could drift below the
// floor with nothing to catch it. The leading group consumes style/variant
// keywords and numeric weights (100-900) so the captured group is always the
// size, never a weight or the unitless line-height that can follow.
const CSS_FONT_SHORTHAND_PX =
  /font:\s*['"]?(?:(?:italic|oblique|normal|bold|bolder|lighter|small-caps|[1-9]00)\s+)*(\d+(?:\.\d+)?)px/g

const SIZE_PATTERNS = [CSS_PX, INLINE_PX, CSS_FONT_SHORTHAND_PX]

/**
 * Extract every px size these patterns recognize from one line, exported so
 * the shorthand-parsing regex can be exercised directly against synthetic
 * strings instead of only through a full filesystem scan.
 */
export function detectPxSizesInLine(line: string): number[] {
  const sizes: number[] = []
  for (const pattern of SIZE_PATTERNS) {
    pattern.lastIndex = 0
    let match: RegExpExecArray | null
    while ((match = pattern.exec(line)) !== null) {
      sizes.push(Number.parseFloat(match[1]))
    }
  }
  return sizes
}

function walk(target: string): string[] {
  const stats = statSync(target, { throwIfNoEntry: false })
  if (!stats) return []
  if (stats.isFile()) return SCAN_EXTENSIONS.has(extname(target)) ? [target] : []
  return readdirSync(target).flatMap((entry) => walk(join(target, entry)))
}

interface Violation {
  file: string
  line: number
  size: number
  text: string
}

function findViolations(): Violation[] {
  const violations: Violation[] = []
  for (const file of SCAN_ROOTS.flatMap(walk)) {
    const rel = relative(SRC, file)
    if (ALLOWED_BELOW_FLOOR.has(rel)) continue
    // Test files describe sizes rather than shipping them.
    if (/\.(test|spec)\.[tj]sx?$/.test(file)) continue

    const lines = readFileSync(file, 'utf8').split('\n')
    lines.forEach((line, index) => {
      for (const size of detectPxSizesInLine(line)) {
        if (size < FLOOR_PX) {
          violations.push({
            file: rel,
            line: index + 1,
            size,
            text: line.trim().slice(0, 80),
          })
        }
      }
    })
  }
  return violations
}

describe('Observatory and Operator type floor', () => {
  it('renders no text below 11px', () => {
    const violations = findViolations()
    const report = violations
      .map((v) => `  ${v.file}:${v.line}  ${v.size}px  ${v.text}`)
      .join('\n')
    expect(
      violations,
      violations.length
        ? `Text below the ${FLOOR_PX}px floor:\n${report}\n\n` +
            'WORKSHOP.md tells co-speakers these surfaces never go below ' +
            `${FLOOR_PX}px. Use --text-label, or let weight, colour and ` +
            'letter-spacing carry the distinction instead.'
        : '',
    ).toEqual([])
  })

  it('catches font shorthand sizes, not just the font-size longhand', () => {
    // A bare shorthand size, the pattern this surface uses everywhere.
    expect(detectPxSizesInLine('.a { font: 9px/1.4 var(--obs-sans); }')).toEqual([9])
    // Numeric weight before the size must not be captured as the size.
    expect(
      detectPxSizesInLine('.b { font: 600 9.5px/1.2 var(--obs-mono); }'),
    ).toEqual([9.5])
    // Style keyword before a numeric weight before the size.
    expect(
      detectPxSizesInLine('.c { font: italic 700 10px/1.5 var(--obs-sans); }'),
    ).toEqual([10])
    // A compliant shorthand line reports its real size, not a false floor hit.
    expect(detectPxSizesInLine('.d { font: 600 14px/1.5 var(--obs-sans); }')).toEqual([14])
    // `font: inherit` and other non-numeric shorthand values must not match.
    expect(detectPxSizesInLine('.e { font: inherit; }')).toEqual([])
    // The longhand and inline-style patterns still work alongside the new one.
    expect(detectPxSizesInLine('.f { font-size: 9px; }')).toEqual([9])
    expect(detectPxSizesInLine("fontSize: '9px',")).toEqual([9])
  })

  it('scans the files it claims to scan', () => {
    // A guard whose glob silently stops matching passes forever. This asserts
    // the scan actually reaches the two surfaces and a representative file in
    // each, so an empty result means "clean", never "looked nowhere".
    const scanned = SCAN_ROOTS.flatMap(walk).map((f) => relative(SRC, f))
    expect(scanned.length).toBeGreaterThan(50)
    expect(scanned).toContain(join('observatory', 'styles', 'base.css'))
    expect(scanned).toContain(join('operator', 'styles', 'operator.css'))
    // The dual-surface receipt: shipped on the Observatory, authored outside
    // both directories.
    expect(scanned).toContain(join('styles', 'turn-receipt.css'))
    expect(scanned).toContain(join('components', 'TurnReceipt.tsx'))
    // The shared primitives both surfaces render.
    expect(scanned).toContain(join('shared', 'DataTable.tsx'))
    expect(scanned).toContain(join('shared', 'StateBadge.tsx'))
  })
})
