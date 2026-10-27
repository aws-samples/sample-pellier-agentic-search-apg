/**
 * The first visit in a real browser: the short tour, against the recorded
 * storefront fixtures (`fixtures/surfaces.ts`). No backend or model runs.
 *
 * It checks what jsdom cannot: the card takes focus as the tour opens (a
 * browser will not focus a hidden element), each stop rings a control that is
 * laid out at a laptop width, and the card stays inside the viewport at a
 * laptop and a phone width.
 *
 *   npx vite --port 5199 &
 *   E2E_BASE_URL=http://localhost:5199 npx playwright test e2e/first-visit-tour.spec.ts
 */
import { expect, test } from '@playwright/test'
import { stubStorefront, visit } from './fixtures/surfaces'

const STOPS = ['Ask Pellier', 'Builder view', 'The Operator']

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`the short tour on a first visit at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await visit(page, { signedIn: false, overlay: true })
    await stubStorefront(page, { signedIn: false })
    await page.goto('/')

    const overlay = page.getByTestId('spotlight-tour')
    for (const [index, title] of STOPS.entries()) {
      const card = page.getByRole('dialog', { name: `Pellier tour: ${title}` })
      await expect(card).toBeVisible()
      await expect(card).toBeFocused()
      await expect(card.getByRole('button', { name: 'Skip' })).toBeVisible()
      // On a phone only Ask Pellier stays in the bar; the other two fold into the menu.
      const ringed = viewport.width > 560 || index === 0
      await expect(overlay).toHaveAttribute('data-target', ringed ? 'ring' : 'none')

      const box = await card.boundingBox()
      expect(box).not.toBeNull()
      expect(box!.x).toBeGreaterThanOrEqual(16)
      expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width - 16)
      expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height)

      await card.getByRole('button', { name: index === STOPS.length - 1 ? 'Done' : 'Next' }).click()
    }
    await expect(overlay).toHaveCount(0)

    await page.reload()
    await expect(page.getByTestId('pellier-hero-search')).toBeVisible()
    await page.waitForTimeout(1000)
    await expect(page.getByRole('dialog')).toHaveCount(0)
  })
}

test('?tour=off keeps the tour closed', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await visit(page, { signedIn: false, overlay: true })
  await stubStorefront(page, { signedIn: false })
  await page.goto('/?tour=off')
  await expect(page.getByTestId('pellier-hero-search')).toBeVisible()
  await page.waitForTimeout(1000)
  await expect(page.getByRole('dialog')).toHaveCount(0)
})
