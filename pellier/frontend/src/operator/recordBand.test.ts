/**
 * Three regressions on the client record, all reported from a real desk.
 *
 * The suite runs with CSS processing off, so a rendered assertion cannot see
 * any of them. These read the stylesheet, which is where each bug lived.
 */

import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const HERE = dirname(fileURLToPath(import.meta.url))
const CSS = readFileSync(join(HERE, 'styles', 'operator.css'), 'utf8')

/**
 * The body of the rule whose selector contains `needle`.
 *
 * `occurrence` picks among repeats, because a selector often appears first in
 * a shared list (`.a,\n.b { min-width: 0 }`) and only later on its own. Taking
 * the first match there reads the wrong body and the assertion misses.
 */
function ruleBody(needle: string, occurrence = 0): string {
  let at = -1
  for (let i = 0; i <= occurrence; i += 1) {
    at = CSS.indexOf(needle, at + 1)
    expect(at, `no rule ${occurrence + 1} matching ${needle}`).toBeGreaterThan(-1)
  }
  const open = CSS.indexOf('{', at)
  return CSS.slice(open, CSS.indexOf('}', open))
}

describe('client record band', () => {
  it('builds its ground from a token the band does not retone', () => {
    // The band redeclares --op-ink to the light band ink so its TYPE follows
    // the token layer. Any background built from --op-ink inside the band
    // therefore resolves to near-white, which is what shipped: the twelve
    // non-persona clients got cream text on a cream gradient and their names
    // were unreadable. The three personas escaped only because their scrim
    // uses literal espresso values.
    const house = ruleBody('.operator-record-head::after')
    expect(house).toContain('--op-band-ground')
    expect(house).not.toContain('var(--op-ink)')

    const head = ruleBody('.operator-record-head {')
    expect(head).toContain('background: var(--op-band-ground)')
    // The retoning that makes the ground necessary is still in place.
    expect(head).toContain('--op-ink: var(--op-band-ink)')
  })

  it('declares the ground darker than the ink printed on it', () => {
    const ground = /--op-band-ground:\s*#([0-9a-f]{6})/i.exec(CSS)?.[1]
    expect(ground, 'no --op-band-ground declaration').toBeTruthy()
    const channels = [0, 2, 4].map((i) =>
      parseInt((ground as string).slice(i, i + 2), 16),
    )
    // Every channel well below mid grey. A light ground here is the bug.
    for (const channel of channels) expect(channel).toBeLessThan(64)
  })
})

describe('piece name register', () => {
  it('uses the register the storefront actually renders', () => {
    // `.product-name` is Fraunces italic in isolation, but index.css resets it
    // to sans inside every page surface a shopper sees. Matching the bare rule
    // made one catalogue name look like two different products.
    const piece = ruleBody('.operator-piece-name {')
    expect(piece).toContain('font-family: var(--sans)')
    expect(piece).toContain('font-style: normal')
    expect(piece).not.toContain('var(--display)')
  })
})

describe('two-pane workbench', () => {
  it('heads the record column with the crumb and runs the Concierge full height', () => {
    // The crumb and the record's section links used to span both columns so the
    // panes opened on the same line. That put 125px above a pane whose height is
    // `100vh - clearance`, so at rest it ran 109px past the bottom of the window
    // and the composer sat off screen until the operator scrolled far enough to
    // pin it. Measured at 1512x950 before and after.
    const crumb = ruleBody('.operator-workbench > .operator-crumb')
    expect(crumb).toContain('grid-column: 1')
    expect(crumb).not.toContain('grid-column: 1 / -1')
    // The grid's row gap owns the space beneath it. Leaving the crumb's own
    // margin in place stacked 18px on top of the row gap.
    expect(crumb).toContain('margin-bottom: 0')

    const pane = ruleBody('.operator-workbench-concierge {', 1)
    expect(pane).toContain('grid-row: 1 / -1')

    // `grid-row: 1 / -1` against an implicit grid resolves to `1 / 1`: the pane
    // takes row one, its own fixed height makes that row 794px tall, and the
    // record is pushed a screen down. The explicit rows are what make -1 mean
    // the end of the grid, so they are the load-bearing half of this fix.
    expect(ruleBody('.operator-workbench {')).toContain('grid-template-rows')
  })

  it('separates the row gap from the measure between the panes', () => {
    const grid = ruleBody('.operator-workbench {')
    const gap = /gap:\s*([0-9]+)px\s+([0-9]+)px/.exec(grid)
    expect(gap, 'workbench gap is no longer a row/column pair').toBeTruthy()
    const [row, column] = [Number(gap?.[1]), Number(gap?.[2])]
    expect(row).toBeLessThan(column)
  })
})

describe('concierge invitation', () => {
  it('is washed in the desk warmth, not in a provenance tone', () => {
    // `--op-source-database` is the teal that marks database provenance on
    // rows that have it. Four percent of it in this panel's gradient pulled
    // the whole thing cold against a cream page and coded provenance onto a
    // panel that carries none.
    const panel = ruleBody('.operator-concierge-empty {')
    expect(panel).not.toContain('--op-source-database')
    expect(panel).toContain('--op-authority')
  })

  it('sets its one sentence in a reading ink, not the caption ink', () => {
    const lede = ruleBody('.operator-concierge-empty-lede')
    expect(lede).toContain('color: var(--op-ink-2)')
    expect(lede).not.toContain('color: var(--op-muted)')
  })
})

describe('concierge pane geometry', () => {
  it('pins below the sticky topbar rather than into it', () => {
    // The topbar is `position: sticky; top: 0` at 65px with a higher stacking
    // level. The pane pinned at 24px, so once the record scrolled the
    // Concierge title sat behind the bar and the pane read as shorter than it
    // was. Both the offset and the height now derive from one token.
    const pane = ruleBody('.operator-workbench-concierge {', 1)
    expect(pane).toContain('top: var(--op-topbar-clearance)')
    expect(pane).toContain('var(--op-topbar-clearance)')

    const clearance = /--op-topbar-clearance:\s*([0-9]+)px/.exec(CSS)
    expect(clearance, 'no --op-topbar-clearance declaration').toBeTruthy()
    const bar = /\.operator-topbar\b[^}]*?min-height:\s*([0-9]+)px/s.exec(CSS)
    // The bar's own height is asserted where it is declared when we can read
    // it; otherwise hold the token above the 65px the desk ships.
    expect(Number(clearance?.[1])).toBeGreaterThanOrEqual(
      bar ? Number(bar[1]) : 65,
    )
  })

  it('centres the standing pill against the name, not its baseline', () => {
    const headline = ruleBody('.operator-record-headline {')
    expect(headline).toContain('align-items: center')
    expect(headline).not.toContain('align-items: baseline')
  })
})

describe('desk warmth', () => {
  it('never blends two provenance tones into one background', () => {
    // Each --op-source-* tone is a hue with a meaning. Two of them at a few
    // percent over warm paper cancel into cool grey, so a panel meant to read
    // as warm paper with a provenance hint reads as a cold slab instead, and
    // any translucent child picks the cast up. Provenance belongs on borders,
    // text and chips, where one tone stays one tone.
    const washes = [...CSS.matchAll(/background:\s*\n?\s*linear-gradient\(([\s\S]*?)\);/g)]
    expect(washes.length).toBeGreaterThan(0)
    const twoToned = washes
      .map((match) => ({
        tones: [...new Set(match[1].match(/--op-source-[a-z]+/g) ?? [])],
        at: CSS.slice(0, match.index ?? 0).split('\n').length,
      }))
      .filter((wash) => wash.tones.length > 1)
    expect(twoToned).toEqual([])
  })
})

describe('topbar account control', () => {
  it('keeps one shape across signed-out and signed-in', () => {
    // The slot rendered a 999px pill when signed out and a 4px rectangle at
    // 34px when signed in, so the corner and the height of the account control
    // changed the moment an operator signed in. Both states now take their
    // border, radius and hover from `.pellier-account-pill` and declare only
    // layout here, which has to match.
    const control = ruleBody('.operator-auth-control {')
    const signin = ruleBody('.operator-auth-signin {')
    for (const rule of [control, signin]) {
      expect(rule).not.toContain('border-radius')
      expect(rule).toContain('min-height: 44px')
      expect(rule).toContain('padding: 7px 14px')
    }
  })
})

describe('service request card', () => {
  it('does not colour its whole body by status', () => {
    // The card tinted its background with the warn hue and then repeated that
    // hue in the border, the eyebrow and the status pill. Colouring an entire
    // panel by state is the dashboard reflex this desk avoids: the state is a
    // mark and a word, and the panel stays paper.
    const card = ruleBody('.operator-service-request {')
    expect(card).toContain('background: var(--op-paper)')
    expect(card).not.toContain('--op-warn')

    const eyebrow = ruleBody('.operator-service-request-eyebrow {')
    expect(eyebrow).not.toContain('--op-warn')
  })

  it('does not lay its facts out as a rule grid of equal cells', () => {
    // Three cells of a 1px-gap grid held two facts and one full sentence, so
    // an instruction sat where a reader expects a number and the column widths
    // existed to fit prose.
    expect(CSS).not.toContain('.operator-service-request-evidence')
  })

  it('sets the two claims beside each other so they can be compared', () => {
    // The card is promoted because a ticket asserts a return the database has
    // no row for. Stacked, the two read as one account of events; side by side
    // the disagreement is the thing the reader sees.
    const claims = ruleBody('.operator-service-request-claims {')
    expect(claims).toContain('grid-template-columns')
    expect(claims).toContain('minmax(0, 1fr) minmax(0, 1fr)')
    // And they stack rather than crush on a narrow pane.
    expect(CSS).toContain('.operator-service-request-claims > div + div')
  })
})

describe('urgent mark', () => {
  it('pulses a ring rather than the dot, and stops under reduced motion', () => {
    // Scaling the dot itself nudges the phrase beside it on every cycle, so
    // the ring is a pseudo-element and the dot holds its size.
    const ring = ruleBody('.operator-service-request-dot::after')
    expect(ring).toContain('animation: operator-urgent-pulse')
    expect(CSS).toContain('@keyframes operator-urgent-pulse')

    const reduced = CSS.slice(CSS.indexOf('.operator-service-request-dot::after'))
    expect(reduced).toContain('prefers-reduced-motion')
    expect(reduced.slice(0, reduced.indexOf('}', reduced.indexOf('prefers-reduced-motion')) + 400))
      .toContain('animation: none')
  })
})

