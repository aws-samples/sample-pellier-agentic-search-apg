/**
 * The home page, products first: signed out, signed in as Anna from the
 * docked panel's chips, and Anna's results with the Builder view on, in both
 * themes at 1440x900, 1280x720 and 390x844, against the recorded storefront
 * fixtures (`fixtures/surfaces.ts`). No backend or model runs.
 *
 * Beside the captures it checks the layout the prototype set: on a laptop
 * the panel is docked open, its chips replace the header's chooser, the
 * product photos start on the first screen, and a card is three across and
 * at most 300px wide; on a phone there is no sideways scroll, two cards
 * across, the header chooser stays, and the chips head the panel when it
 * opens. Measured sizes go to `measurements.json` beside the captures.
 *
 *   npx vite --port 5199 &
 *   E2E_BASE_URL=http://localhost:5199 HOME_SHOTS=/path/to/dir \
 *     npx playwright test e2e/home-screenshots.spec.ts
 */
import { expect, test, type Page } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { askAnna, stubStorefront, visit } from './fixtures/surfaces'

const SHOTS = process.env.HOME_SHOTS ?? 'test-results/home'
const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 1280, height: 720 },
  { width: 390, height: 844 },
]
const measured: Record<string, unknown> = {}

interface Box { x: number; y: number; width: number; height: number }

/** The first row of product photos in a grid, as laid out. */
async function firstRow(page: Page, grid: string): Promise<Box[]> {
  const boxes = await page.getByTestId(grid).locator('.pellier-card-photo').evaluateAll(nodes =>
    nodes.map(node => {
      const { x, y, width, height } = node.getBoundingClientRect()
      return { x: Math.round(x), y: Math.round(y), width: Math.round(width), height: Math.round(height) }
    }))
  return boxes.filter(box => box.y === boxes[0].y)
}

async function checkGrid(page: Page, grid: string, viewport: { width: number; height: number }, key: string) {
  const row = await firstRow(page, grid)
  const desktop = viewport.width >= 1080
  measured[key] = { columns: row.length, card: `${row[0].width}x${row[0].height}`, top: row[0].y }
  expect(row[0].width).toBeLessThanOrEqual(300)
  if (desktop) {
    expect(row.length).toBe(3)
    // The first row of photos starts on the first screen.
    expect(row[0].y).toBeLessThan(viewport.height)
  } else {
    expect(row.length).toBe(2)
  }
}

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true })
})

test.afterAll(() => {
  writeFileSync(join(SHOTS, 'measurements.json'), `${JSON.stringify(measured, null, 2)}\n`)
})

for (const theme of ['light', 'dark'] as const) {
  for (const viewport of VIEWPORTS) {
    const desktop = viewport.width >= 1080
    const shot = (name: string) => join(SHOTS, `${name}-${theme}-${viewport.width}.png`)

    test(`home signed out, ${theme} theme, ${viewport.width}px`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
      await page.setViewportSize(viewport)
      await visit(page, { signedIn: false })
      await stubStorefront(page, { signedIn: false })
      await page.goto('/')
      await expect(page.getByTestId('home-grid')).toBeVisible()
      await expect(page.getByTestId('home-grid-count')).toHaveText('4 of 100')
      await expect(page.getByTestId('pellier-hero-headline')).toHaveText('Good things for every day.')
      await expect(page.getByText('Choose who enters Pellier.')).toHaveCount(0)
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width)

      const drawer = page.getByTestId('chat-drawer')
      if (desktop) {
        await expect(drawer).toBeVisible()
        await expect(drawer.getByTestId('ask-panel-subtitle')).toHaveText('Pick a customer to start')
        await expect(drawer.getByRole('group', { name: 'Signed in as' }).getByRole('button'))
          .toHaveText(['Anna', 'Marco', 'Theo', 'Jessica'])
        await expect(drawer.getByTestId('ask-panel-empty')).toContainText('Search from the box on the left')
        // One chooser on screen at a time.
        await expect(page.getByTestId('persona-pill')).toBeHidden()
      } else {
        await expect(drawer).toHaveCount(0)
        await expect(page.getByTestId('persona-pill')).toBeVisible()
      }
      await checkGrid(page, 'home-grid', viewport, `home-signed-out ${viewport.width}`)
      await page.waitForTimeout(300)
      await page.screenshot({ path: shot('home-signed-out') })

      if (!desktop) {
        // The panel stacks under the page; opening it brings it on screen
        // with the chips at its top.
        await page.getByTestId('header-ask-pellier').click()
        await expect(drawer).toBeVisible()
        const chips = drawer.getByTestId('ask-shoppers')
        await expect(chips).toBeInViewport()
        const [panelTop, chipsTop] = await Promise.all([
          drawer.evaluate(el => el.getBoundingClientRect().top),
          chips.evaluate(el => el.getBoundingClientRect().top),
        ])
        expect(chipsTop - panelTop).toBeLessThan(80)
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width)
        await page.waitForTimeout(300)
        await page.screenshot({ path: shot('home-panel') })
      }
    })

    test(`home signed in as Anna, ${theme} theme, ${viewport.width}px`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
      await page.setViewportSize(viewport)
      await visit(page)
      await stubStorefront(page)
      await page.goto('/')
      await expect(page.getByTestId('home-grid')).toBeVisible()
      await expect(page.getByTestId('pellier-hero-eyebrow')).toHaveText("Anna's edit")
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width)

      if (desktop) {
        const drawer = page.getByTestId('chat-drawer')
        await expect(drawer.getByTestId('ask-shopper-anna')).toHaveAttribute('aria-pressed', 'true')
        await expect(drawer.getByTestId('ask-panel-subtitle')).toHaveText('Anna, signed in')
        await expect(drawer.getByTestId('ask-sign-out')).toBeVisible()
        await expect(page.getByTestId('persona-pill')).toBeHidden()
      } else {
        await expect(page.getByTestId('persona-pill')).toContainText('Anna')
      }
      await checkGrid(page, 'home-grid', viewport, `home-anna ${viewport.width}`)
      await page.waitForTimeout(300)
      await page.screenshot({ path: shot('home-anna') })
    })

    test(`Anna's results with Builder view, ${theme} theme, ${viewport.width}px`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
      await page.setViewportSize(viewport)
      await askAnna(page)
      await page.getByTestId('surface-navigation').getByRole('switch', { name: 'Builder view' }).click()
      const view = page.getByTestId('results-view')
      await expect(view.getByTestId('ranking-panel')).toBeVisible()
      await checkGrid(page, 'results-grid', { ...viewport, height: Number.POSITIVE_INFINITY }, `results-builder ${viewport.width}`)
      if (!desktop) await page.locator('#shop').evaluate(el => el.scrollIntoView({ block: 'start' }))
      else await page.evaluate(() => window.scrollTo(0, 0))
      await page.waitForTimeout(400)
      await page.screenshot({ path: shot('results-builder-anna') })
    })
  }
}
