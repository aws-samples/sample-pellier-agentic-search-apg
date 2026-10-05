/**
 * Every storefront and Operator surface in both themes, at 1440x900 and
 * 390x844, against recorded fixtures (`fixtures/surfaces.ts`): a capture of
 * each, and in the dark theme the contrast sweep (`fixtures/contrast-sweep.ts`),
 * which fails on visible text below 4.5:1, an icon below 3:1, or a border or
 * rule below 1.25:1 against what is painted behind it. The sweep scrolls the
 * page and every scrolling panel so nothing below the fold escapes it.
 *
 *   npx vite --port 5199 &
 *   E2E_BASE_URL=http://localhost:5199 THEME_SHOTS=/path/to/dir \
 *     npx playwright test e2e/theme-surfaces.spec.ts
 */
import { expect, test, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { sweepContrast, type ContrastFinding } from './fixtures/contrast-sweep'
import { SURFACES } from './fixtures/surfaces'

const SHOTS = process.env.THEME_SHOTS ?? 'test-results/theme-surfaces'
const VIEWPORTS = [{ width: 1440, height: 900 }, { width: 390, height: 844 }]
const SETTLE_MS = 250
const MAX_STEPS = 14

/** Scrolls a whole page once so its lazy images load before a full capture. */
async function loadLazyImages(page: Page) {
  const height = await page.evaluate(() => document.documentElement.scrollHeight)
  const screen = await page.evaluate(() => window.innerHeight)
  for (let y = 0; y < height; y += screen) {
    await page.evaluate((top) => window.scrollTo(0, top), y)
    await page.waitForTimeout(150)
  }
  await page.waitForFunction(() => Array.from(document.images).every((img) => img.complete))
  await page.evaluate(() => window.scrollTo(0, 0))
}

async function sweepPage(page: Page): Promise<ContrastFinding[]> {
  const found = new Map<string, ContrastFinding>()
  const collect = async () => {
    for (const finding of await page.evaluate(sweepContrast)) {
      found.set(`${finding.kind} ${finding.path} ${finding.text}`, finding)
    }
  }
  // The window, one screen at a time.
  const height = await page.evaluate(() => document.documentElement.scrollHeight)
  const screen = await page.evaluate(() => window.innerHeight)
  for (let step = 0, y = 0; step < MAX_STEPS && y < height; step += 1, y += Math.round(screen * 0.85)) {
    await page.evaluate((top) => window.scrollTo(0, top), y)
    await page.waitForTimeout(SETTLE_MS)
    await collect()
  }
  await page.evaluate(() => window.scrollTo(0, 0))
  // Every panel that scrolls on its own: the docked Ask Pellier body, the
  // bag, a dialog.
  const scrollers = await page.evaluate(() => {
    let index = 0
    for (const el of Array.from(document.querySelectorAll<HTMLElement>('body *'))) {
      const style = getComputedStyle(el)
      if (!/(auto|scroll)/.test(style.overflowY) || el.scrollHeight <= el.clientHeight + 20) continue
      if (el.getBoundingClientRect().height < 80) continue
      el.setAttribute('data-sweep-scroller', String(index++))
    }
    return index
  })
  for (let index = 0; index < scrollers; index += 1) {
    const panel = page.locator(`[data-sweep-scroller="${index}"]`)
    const [total, view] = await panel.evaluate((el) => [el.scrollHeight, el.clientHeight])
    for (let step = 0, y = 0; step < MAX_STEPS && y < total; step += 1, y += Math.round(view * 0.85)) {
      await panel.evaluate((el, top) => { el.scrollTop = top }, y)
      await page.waitForTimeout(SETTLE_MS)
      await collect()
    }
  }
  return [...found.values()]
}

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true })
})

for (const theme of ['light', 'dark'] as const) {
  for (const viewport of VIEWPORTS) {
    for (const surface of SURFACES) {
      test(`${surface.name}, ${theme} theme, ${viewport.width}px`, async ({ page }) => {
        test.setTimeout(120_000)
        await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
        await page.setViewportSize(viewport)
        await surface.open(page)
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
        if (surface.fullPage) await loadLazyImages(page)
        await page.waitForTimeout(600)
        await page.screenshot({
          path: join(SHOTS, `${surface.name}-${theme}-${viewport.width}.png`),
          fullPage: surface.fullPage,
        })
        if (theme === 'dark') {
          const findings = await sweepPage(page)
          const lines = findings.map((f) => `${f.kind} ${f.ratio}:1 < ${f.min} fg ${f.fg} on ${f.bg} "${f.text}" at ${f.path}`)
          expect(lines, `${surface.name} at ${viewport.width}px in the dark theme`).toEqual([])
        }
      })
    }
  }
}
