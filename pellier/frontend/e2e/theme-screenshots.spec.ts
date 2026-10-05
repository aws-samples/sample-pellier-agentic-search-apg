/**
 * Both themes on the direction A surfaces, against the real app with
 * recorded fixtures: Home, the collection, a product page and an Anna turn
 * with the Builder view on, at 1440px and 390px, plus the first-visit
 * overlay. The theme comes from the system preference with no stored
 * choice, which also proves the default. The API stubs are shared with
 * `theme-surfaces.spec.ts` (`fixtures/surfaces.ts`).
 *
 *   npx vite --port 5199 &
 *   E2E_BASE_URL=http://localhost:5199 THEME_SHOTS=/path/to/dir \
 *     npx playwright test e2e/theme-screenshots.spec.ts
 */
import { expect, test } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { ANNA, ANNA_QUESTION } from './fixtures/anna-turn'
import { stubStorefront } from './fixtures/surfaces'

const SHOTS = process.env.THEME_SHOTS ?? 'test-results/theme'

test.beforeEach(async ({ page }) => {
  await page.addInitScript((persona) => {
    sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true')
    sessionStorage.setItem('pellier-persona', JSON.stringify(persona))
    localStorage.setItem('pellier-session-id', 'session-shots')
    localStorage.setItem('pellier-auth-session:shopper', '1')
    localStorage.removeItem('pellier-drawer-storefront')
    localStorage.removeItem('pellier-builder-view')
    localStorage.removeItem('pellier-theme')
  }, ANNA)
  await stubStorefront(page)
  mkdirSync(SHOTS, { recursive: true })
})

for (const theme of ['light', 'dark'] as const) {
  for (const width of [1440, 390]) {
    test(`${theme} theme at ${width}px: home, collection, product, Anna's turn`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme })
      await page.setViewportSize({ width, height: 960 })
      const shot = (name: string) => join(SHOTS, `${name}-${theme}-${width}.png`)

      // Home: the system preference is the default and lands before paint.
      await page.goto('/')
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
      await expect(page.getByRole('button', { name: 'System theme' })).toHaveAttribute('aria-pressed', 'true')
      await expect(page.getByTestId('pellier-hero-search')).toBeVisible()
      await expect(page.getByTestId('product-card-36')).toContainText('In stock in Austin and Portland')
      await expect(page.getByTestId('product-card-12')).toContainText('Sold out')
      await page.waitForTimeout(500)
      await page.screenshot({ path: shot('home') })

      // The collection: the cards with their one stock line.
      await page.getByTestId('product-card-12').getByTestId('status-tag').scrollIntoViewIfNeeded()
      await page.waitForTimeout(600)
      await page.screenshot({ path: shot('collection') })

      // A product page.
      await page.goto('/product/31')
      await expect(page.getByTestId('product-detail-name')).toHaveText('Stoneware Pour-Over Set')
      await expect(page.getByTestId('product-availability')).toHaveAttribute('data-state', 'read')
      await page.waitForTimeout(500)
      await page.screenshot({ path: shot('product') })

      // Anna's turn in the docked panel, with the Builder view on: the page
      // carries How it ranked, the dock one line that points at it.
      await page.goto('/')
      const ask = page.getByTestId('pellier-hero-search')
      await ask.fill(ANNA_QUESTION)
      await ask.press('Enter')
      const drawer = page.getByTestId('chat-drawer')
      await expect(drawer).toBeVisible()
      await expect(drawer.getByTestId('turn-fold')).toBeVisible({ timeout: 20_000 })
      await page.getByTestId('surface-navigation').getByRole('switch', { name: 'Builder view' }).click()
      await drawer.getByTestId('turn-fold').click()
      await expect(drawer.getByTestId('ranking-summary')).toBeVisible()
      await expect(page.getByTestId('results-view').getByTestId('ranking-panel')).toBeVisible()
      if (width < 1080) await drawer.scrollIntoViewIfNeeded()
      await page.waitForTimeout(500)
      await page.screenshot({ path: shot('ask-pellier-builder') })
      await drawer.screenshot({ path: shot('ask-pellier-panel') })

      // The "Latest reply" pill shows only while the newest reply is out of
      // view, and goes once it is back. jsdom has no IntersectionObserver, so
      // this is its only test. A second turn puts the newest reply below the
      // first one.
      const input = drawer.locator('.cd-input')
      await input.fill('Which of those would you pick for a small kitchen?')
      await input.press('Enter')
      await expect(drawer.getByTestId('turn-fold')).toHaveCount(2, { timeout: 20_000 })
      const latest = drawer.locator('.cd-latest')
      await drawer.locator('.cd-body').evaluate((body) => { body.scrollTop = 0 })
      await expect(latest).toBeVisible()
      await latest.click()
      await expect(latest).toBeHidden()
    })
  }

  test(`${theme} theme: the first-visit overlay`, async ({ page }) => {
    // A new session: the overlay has not been seen yet.
    await page.addInitScript(() => sessionStorage.removeItem('pellier-storefront-spotlight-seen'))
    await page.emulateMedia({ colorScheme: theme })
    await page.setViewportSize({ width: 1440, height: 960 })
    await page.goto('/')
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
    const dialog = page.getByRole('dialog', { name: 'Begin with the edit.' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Continue' })).toBeVisible()
    await page.waitForTimeout(700)
    await page.screenshot({ path: join(SHOTS, `spotlight-${theme}-1440.png`) })
  })
}
