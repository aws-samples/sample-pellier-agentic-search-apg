/**
 * The home page, products first: signed out, signed in as Anna from the
 * docked panel's chips, and Anna's results with the Builder view on, in both
 * themes at 1440x900, 1280x720 and 390x844, against the recorded storefront
 * fixtures (`fixtures/surfaces.ts`). No backend or model runs.
 *
 * Beside the captures it checks the layout the prototype set: on a laptop
 * the panel is docked open, its chips replace the header's chooser, the
 * product photos start on the first screen, and cards are three across at
 * the prototype's size; with the panel closed they are four across, six from
 * 1800px; on a phone there is no sideways scroll, two cards across, the
 * header chooser stays, and the chips head the panel when it opens. Every
 * count divides twelve, so the home's twelve pieces fill whole rows.
 *
 * The grid pages through the whole catalog, twelve a page: page 2 reads "More
 * from Pellier", a page link lands on the top of the grid, Previous and Next
 * stop at the ends, and on a phone the numbers give way to "Page 2 of 9". A
 * product page's "More from the collection" holds four pieces, four across
 * or two by two. Measured sizes go to `measurements.json` beside the captures.
 *
 *   npx vite --port 5199 &
 *   E2E_BASE_URL=http://localhost:5199 HOME_SHOTS=/path/to/dir \
 *     npx playwright test e2e/home-screenshots.spec.ts
 */
import { expect, test, type Page } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { CATALOG_ORDER, askAnna, stubStorefront, visit } from './fixtures/surfaces'

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

/** Cards across: three beside the docked panel, four or six without it, two on a phone. */
function columnsFor(width: number, docked: boolean): number {
  if (width < 640) return 2
  if (docked && width >= 1080) return 3
  if (width >= 1800) return 6
  return width >= 1024 ? 4 : 3
}

async function checkGrid(
  page: Page,
  grid: string,
  viewport: { width: number; height: number },
  key: string,
  { docked = true, cards }: { docked?: boolean; cards?: number } = {},
) {
  const row = await firstRow(page, grid)
  const columns = columnsFor(viewport.width, docked)
  measured[key] = { columns: row.length, card: `${row[0].width}x${row[0].height}`, top: row[0].y }
  expect(row.length).toBe(columns)
  expect(12 % row.length).toBe(0)
  expect(row[0].width).toBeLessThanOrEqual(360)
  // 4:5 photographs.
  expect(Math.abs(row[0].height / row[0].width - 1.25)).toBeLessThan(0.02)
  if (cards !== undefined) {
    // The grid's pieces fill every row.
    await expect(page.getByTestId(grid).locator('.pellier-card')).toHaveCount(cards)
    expect(cards % columns).toBe(0)
  }
  if (viewport.width >= 1080) {
    // The first row of photos starts on the first screen.
    expect(row[0].y).toBeLessThan(viewport.height)
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
      await expect(page.getByTestId('home-grid-title')).toHaveText('This week at Pellier')
      await expect(page.getByTestId('home-grid-count')).toHaveText('100 pieces')
      await expect(page.getByTestId('home-grid-range')).toHaveText('1–12 of 100')
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
      await checkGrid(page, 'home-grid', viewport, `home-signed-out ${viewport.width}`, { cards: 12 })
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
      await expect(page.getByTestId('home-grid-title')).toHaveText("Anna's edit")
      await expect(page.getByTestId('home-grid-range')).toHaveText('1–12 of 100')
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
      await checkGrid(page, 'home-grid', viewport, `home-anna ${viewport.width}`, { cards: 12 })
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

  for (const viewport of [{ width: 1440, height: 900 }, { width: 1800, height: 1000 }]) {
    test(`home with the panel closed, ${theme} theme, ${viewport.width}px`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
      await page.setViewportSize(viewport)
      await visit(page, { signedIn: false })
      await stubStorefront(page, { signedIn: false })
      await page.goto('/')
      await expect(page.getByTestId('home-grid')).toBeVisible()
      await page.getByRole('button', { name: 'Close Ask Pellier' }).click()
      await expect(page.locator('html')).not.toHaveAttribute('data-ask-docked', 'true')
      await checkGrid(page, 'home-grid', viewport, `home-panel-closed ${viewport.width}`, { docked: false, cards: 12 })
      await page.waitForTimeout(300)
      await page.screenshot({ path: join(SHOTS, `home-panel-closed-${theme}-${viewport.width}.png`) })
    })
  }
}

const names = (page: Page) => page.getByTestId('home-grid').locator('.pellier-card-name')
const nameAt = (index: number) => CATALOG_ORDER[index].name

for (const theme of ['light', 'dark'] as const) {
  test(`home page 2 with the panel open, ${theme} theme, 1440px`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    await page.setViewportSize({ width: 1440, height: 900 })
    await visit(page, { signedIn: false })
    await stubStorefront(page, { signedIn: false })
    await page.goto('/')
    await expect(names(page)).toHaveText(CATALOG_ORDER.slice(0, 12).map(card => card.name))
    await page.screenshot({ path: join(SHOTS, `home-page-1-${theme}-1440.png`) })
    const pager = page.getByTestId('home-pager')
    await expect(pager.getByRole('link', { name: 'Page 1' })).toHaveAttribute('aria-current', 'page')
    await expect(pager.getByTestId('home-pager-prev')).toHaveAttribute('aria-disabled', 'true')
    await expect(pager.getByTestId('home-pager-status')).toBeHidden()
    await pager.scrollIntoViewIfNeeded()
    await page.screenshot({ path: join(SHOTS, `home-pager-${theme}-1440.png`) })

    await pager.getByTestId('home-pager-next').click()
    await expect(page).toHaveURL(/\/\?page=2$/)
    await expect(page.getByTestId('home-grid-title')).toHaveText('More from Pellier')
    await expect(page.getByTestId('home-grid-range')).toHaveText('13–24 of 100')
    await expect(names(page)).toHaveText(CATALOG_ORDER.slice(12, 24).map(card => card.name))
    await expect(pager.getByRole('link', { name: 'Page 2' })).toHaveAttribute('aria-current', 'page')
    // The top of the grid, just under the sticky chrome, not the top of the page.
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(200)
    const top = await page.getByTestId('home-collection').evaluate(el => el.getBoundingClientRect().top)
    expect(top).toBeGreaterThan(60)
    expect(top).toBeLessThan(200)
    await expect(page.getByTestId('chat-drawer')).toBeVisible()
    await checkGrid(page, 'home-grid', { width: 1440, height: Number.POSITIVE_INFINITY }, `home-page-2 1440`, { cards: 12 })
    await page.waitForTimeout(300)
    await page.screenshot({ path: join(SHOTS, `home-page-2-${theme}-1440.png`) })

    // The last page holds four, and Next stops there.
    await pager.getByRole('link', { name: 'Page 9' }).click()
    await expect(page.getByTestId('home-grid-range')).toHaveText('97–100 of 100')
    await expect(names(page)).toHaveText([nameAt(96), nameAt(97), nameAt(98), nameAt(99)])
    await expect(pager.getByTestId('home-pager-next')).toHaveAttribute('aria-disabled', 'true')
    await expect(pager.getByTestId('home-pager-prev')).toHaveAttribute('href', '/?page=8')
    // Back returns to page 2.
    await page.goBack()
    await expect(page.getByTestId('home-grid-range')).toHaveText('13–24 of 100')
  })

  test(`the pager on a phone, ${theme} theme, 390px`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    await page.setViewportSize({ width: 390, height: 844 })
    await visit(page, { signedIn: false })
    await stubStorefront(page, { signedIn: false })
    await page.goto('/?page=2')
    await expect(page.getByTestId('home-grid-range')).toHaveText('13–24 of 100')
    const pager = page.getByTestId('home-pager')
    await expect(pager.getByTestId('home-pager-status')).toHaveText('Page 2 of 9')
    await expect(pager.locator('.pellier-pager-pages')).toBeHidden()
    await expect(pager.getByTestId('home-pager-prev')).toHaveAttribute('href', '/')
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    const box = await pager.boundingBox()
    expect(box!.height).toBeLessThan(60)
    await pager.scrollIntoViewIfNeeded()
    await page.evaluate(() => window.scrollBy(0, 160))
    await page.waitForTimeout(300)
    await page.screenshot({ path: join(SHOTS, `home-pager-${theme}-390.png`) })
    await pager.getByTestId('home-pager-next').click()
    await expect(pager.getByTestId('home-pager-status')).toHaveText('Page 3 of 9')
    await expect(page.getByTestId('home-grid-range')).toHaveText('25–36 of 100')
  })

  for (const [name, viewport, docked, columns] of [
    ['1440', { width: 1440, height: 900 }, true, 4],
    ['1440-panel-closed', { width: 1440, height: 900 }, false, 4],
    ['1280', { width: 1280, height: 720 }, true, 4],
    ['390', { width: 390, height: 844 }, true, 2],
  ] as const) {
    test(`product page, four more from the collection, ${theme} theme, ${name}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
      await page.setViewportSize(viewport)
      await visit(page)
      await stubStorefront(page)
      await page.goto('/product/31')
      await expect(page.getByTestId('product-detail-name')).toHaveText('Stoneware Pour-Over Set')
      if (!docked) await page.getByRole('button', { name: 'Close Ask Pellier' }).click()
      const siblings = page.getByTestId('product-detail-siblings')
      await expect(siblings.locator('.pellier-card')).toHaveCount(4)
      const row = await firstRow(page, 'product-detail-siblings')
      measured[`product-related ${theme} ${name}`] = { columns: row.length, card: `${row[0].width}x${row[0].height}` }
      expect(row.length).toBe(columns)
      expect(4 % row.length).toBe(0)
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width)
      await siblings.scrollIntoViewIfNeeded()
      await page.waitForTimeout(300)
      await page.screenshot({ path: join(SHOTS, `product-${theme}-${name}.png`) })
    })
  }
}
