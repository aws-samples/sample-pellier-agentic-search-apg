/**
 * The first visit in a real browser: the two-slide welcome, then the tour,
 * against the recorded storefront fixtures (`fixtures/surfaces.ts`). No
 * backend or model runs.
 *
 * It checks what jsdom cannot: the tour's card takes focus as the welcome
 * hands over (a browser will not focus a hidden element), every stop after
 * the first rings a control that is laid out, at a laptop and a phone width,
 * and the card stays inside the viewport.
 *
 *   npx vite --port 5199 &
 *   E2E_BASE_URL=http://localhost:5199 npx playwright test e2e/first-visit-tour.spec.ts
 */
import { expect, test } from '@playwright/test'
import { stubStorefront, visit } from './fixtures/surfaces'

const STOPS = [
  'The labs run in Code Editor',
  'Ask Pellier',
  'Choose a shopper',
  'Builder view',
  'The Operator, for Lab 4',
]

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`welcome, then the tour at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await visit(page, { signedIn: false, overlay: true })
    await stubStorefront(page, { signedIn: false })
    await page.goto('/')

    await expect(page.getByRole('dialog', { name: 'Begin with the edit.' })).toBeVisible()
    await page.getByRole('button', { name: 'Continue' }).click()
    await page.getByRole('button', { name: 'Explore Pellier' }).click()

    const overlay = page.getByTestId('spotlight-tour')
    for (const [index, title] of STOPS.entries()) {
      const card = page.getByRole('dialog', { name: `Pellier tour: ${title}` })
      await expect(card).toBeVisible()
      await expect(card).toBeFocused()
      await expect(card.getByRole('button', { name: 'Skip' })).toBeVisible()
      await expect(overlay).toHaveAttribute('data-target', index === 0 ? 'none' : 'ring')

      const box = await card.boundingBox()
      expect(box).not.toBeNull()
      expect(box!.x).toBeGreaterThanOrEqual(16)
      expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width - 16)
      expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height)

      await card.getByRole('button', { name: index === STOPS.length - 1 ? 'Done' : 'Next' }).click()
    }
    await expect(overlay).toHaveCount(0)
  })
}

test('?tour=off keeps the welcome and the tour closed', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await visit(page, { signedIn: false, overlay: true })
  await stubStorefront(page, { signedIn: false })
  await page.goto('/?tour=off')
  await expect(page.getByTestId('pellier-hero-search')).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveCount(0)
})
