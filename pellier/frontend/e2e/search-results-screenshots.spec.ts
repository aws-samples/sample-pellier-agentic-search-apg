/**
 * Anna's housewarming question fills the page grid: Builder view off and on,
 * both themes, at 1440px and 390px, against the real app with the recorded
 * turn (`fixtures/anna-turn.ts`) and the recorded cards for its ids
 * (`fixtures/anna-cards.ts`). One more capture shows a turn with two
 * searches at once in Builder view (`fixtures/two-searches-turn.ts`): two
 * steps, each with its own "How it ranked". No backend or model runs.
 *
 *   npx vite --port 5199 &
 *   E2E_BASE_URL=http://localhost:5199 RESULTS_SHOTS=/path/to/dir \
 *     npx playwright test e2e/search-results-screenshots.spec.ts
 */
import { expect, test } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { ANNA_QUESTION, ANNA_RESULT_IDS } from './fixtures/anna-turn'
import { ANNA_RESULT_CARDS } from './fixtures/anna-cards'
import { HADLEY_RESULT_CARDS, TWO_SEARCHES_EVENTS, TWO_SEARCHES_QUESTION } from './fixtures/two-searches-turn'
import { askAnna } from './fixtures/surfaces'

const SHOTS = process.env.RESULTS_SHOTS ?? 'test-results/search-results'

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true })
})

for (const theme of ['light', 'dark'] as const) {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    test(`Anna's results, ${theme} theme, ${viewport.width}px`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
      await page.setViewportSize(viewport)
      const shot = (name: string) => join(SHOTS, `anna-results-${name}-${theme}-${viewport.width}.png`)

      await askAnna(page)
      const view = page.getByTestId('results-view')
      await expect(view.getByTestId('results-title')).toHaveText(`Results for “${ANNA_QUESTION}”`)
      // The count describes the grid below it; "Kept 64 of 100" is the panel's.
      await expect(view.getByTestId('results-count')).toHaveText(`${ANNA_RESULT_IDS.length} pieces`)
      await expect(view.getByTestId('results-limit')).toHaveText(['Under $100', 'In stock', 'No candles'])
      await expect(page.getByTestId('pellier-hero')).toHaveAttribute('data-compact', 'true')
      // The folded bar keeps the question, as the prototype's does.
      await expect(page.getByTestId('pellier-hero-search')).toHaveValue(ANNA_QUESTION)

      // The grid is the evidence's order, card for card.
      const names = view.getByTestId('results-grid').locator('.pellier-card-name')
      const expected = ANNA_RESULT_IDS.map(id => ANNA_RESULT_CARDS.find(card => String(card.id) === id)?.name)
      await expect(names).toHaveText(expected as string[])
      await expect(view.getByTestId('ranking-panel')).toHaveCount(0)

      // On a desktop the grid is above the fold beside the docked panel.
      if (viewport.width >= 1080) {
        const top = await view.getByTestId('results-grid').evaluate(el => el.getBoundingClientRect().top)
        expect(top).toBeLessThan(viewport.height)
      }
      // On a phone the dock stacks below the page and opening it scrolled
      // there; bring the results back to the top of the screen.
      const toResults = async () => {
        if (viewport.width < 1080) await page.locator('#shop').evaluate(el => el.scrollIntoView({ block: 'start' }))
      }
      await toResults()
      await page.waitForTimeout(400)
      await page.screenshot({ path: shot('off') })
      await page.screenshot({ path: shot('off-page'), fullPage: true })

      // Builder view on, from the header: How it ranked, full width above the grid.
      await page.getByTestId('surface-navigation').getByRole('switch', { name: 'Builder view' }).click()
      const panel = view.getByTestId('ranking-panel')
      await expect(panel).toBeVisible()
      await expect(panel).toContainText('fused with RRF (k=60), then Cohere Rerank 3.5 on the top 15')
      const panelBox = await panel.boundingBox()
      const gridBox = await view.getByTestId('results-grid').boundingBox()
      expect(panelBox!.y + panelBox!.height).toBeLessThanOrEqual(gridBox!.y)
      await expect(page.getByTestId('chat-drawer').getByTestId('ranking-panel')).toHaveCount(0)
      await toResults()
      await page.waitForTimeout(400)
      await page.screenshot({ path: shot('on') })
      await panel.screenshot({ path: shot('on-panel') })
    })
  }
}

test('two searches at once, Builder view on, light theme, 1440px', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' })
  await page.setViewportSize({ width: 1440, height: 900 })
  await askAnna(page, { turn: TWO_SEARCHES_EVENTS, question: TWO_SEARCHES_QUESTION })
  const view = page.getByTestId('results-view')
  // The answer named two pieces of the linen search: the page shows that search, in its order.
  const names = view.getByTestId('results-grid').locator('.pellier-card-name')
  await expect(names).toHaveText(HADLEY_RESULT_CARDS.map(card => card.name))
  await expect(view.getByTestId('results-count')).toHaveText(`${HADLEY_RESULT_CARDS.length} pieces`)

  await page.getByTestId('surface-navigation').getByRole('switch', { name: 'Builder view' }).click()
  await expect(view.getByTestId('ranking-panel')).toContainText('Hadley Linen Shirt')
  const drawer = page.getByTestId('chat-drawer')
  await drawer.getByTestId('turn-fold').click()
  const summaries = drawer.getByTestId('ranking-summary')
  await expect(summaries).toHaveCount(2)
  await expect(summaries.nth(0)).toContainText('Kept 67 of 100, see the table above the results')
  await expect(summaries.nth(1)).toContainText('Kept 64 of 100, show the table')
  // The housewarming search opens its own ranking in the dock.
  await summaries.nth(1).click()
  const inDock = drawer.getByTestId('ranking-panel')
  await expect(inDock).toContainText('Stoneware Pour-Over Set')
  await expect(inDock).not.toContainText('Hadley Linen Shirt')
  await page.waitForTimeout(400)
  await page.screenshot({ path: join(SHOTS, 'two-searches-on-light-1440.png') })
})
