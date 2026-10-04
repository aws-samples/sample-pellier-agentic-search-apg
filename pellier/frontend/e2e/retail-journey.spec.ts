import { expect, test } from '@playwright/test'

// Live credentials never belong in screenshots, traces, or recordings.
test.use({ trace: 'off', screenshot: 'off', video: 'off', contextOptions: { reducedMotion: 'reduce' } })
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true')
  })
})

for (const width of [1440, 390]) {
  test(`product image zoom contains focus and returns to shopping at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 })
    await page.goto('/product/2')
    const zoom = page.getByTestId('product-detail-zoom')
    await zoom.click()
    const dialog = page.getByTestId('product-detail-zoom-dialog')
    await expect(dialog).toBeFocused()
    const close = dialog.getByRole('button', { name: 'Close enlarged image' })
    for (const key of ['Tab', 'Tab', 'Shift+Tab']) {
      await page.keyboard.press(key)
      await expect(close).toBeFocused()
    }
    expect(await page.evaluate(() => document.body.style.overflow)).toBe('hidden')
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(zoom).toBeFocused()
    expect(await page.evaluate(() => document.body.style.overflow)).not.toBe('hidden')
    await page.getByTestId('product-detail-add').click()
    const bag = page.getByRole('dialog', { name: /bag/i })
    await expect(bag).toBeVisible()
    await bag.getByRole('button', { name: 'Increase quantity' }).click()
    await bag.getByRole('button', { name: 'Decrease quantity' }).click()
    await bag.getByRole('button', { name: 'Close bag' }).click()
    await expect(bag).toHaveCount(0)
  })

  test(`each Stories link opens its matching essay above the sticky headers at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 })
    await page.goto('/storyboard')
    for (const name of ['Marco', 'Anna', 'Theo']) {
      const link = page.getByRole('link', { name: `Read ${name}'s note`, exact: false })
      await link.focus()
      await page.keyboard.press('Enter')
      await expect(page).toHaveURL(new RegExp(`#field-note-${name.toLowerCase()}$`))
      const article = page.getByRole('article', { name: new RegExp(`^${name},`) })
      await expect(article).toBeFocused()
      const heading = article.getByRole('heading')
      await expect(heading).toBeInViewport()
      const top = await heading.evaluate(node => node.getBoundingClientRect().top)
      const headerBottom = await page.locator('header').evaluateAll(nodes => Math.max(0, ...nodes
        .filter(n => ['fixed', 'sticky'].includes(getComputedStyle(n).position))
        .map(n => n.getBoundingClientRect().bottom)))
      expect(top).toBeGreaterThan(headerBottom)
    }
  })
}

test.describe('authenticated Operator navigation', () => {
  test.skip(!process.env.E2E_OPERATOR_USERNAME || !process.env.E2E_OPERATOR_PASSWORD,
    'Requires a workshop Operator identity for real client records.')
  test.beforeEach(async ({ page }) => {
    await page.goto('/signin?returnTo=%2Foperator')
    await page.getByLabel('Username', { exact: true }).fill(process.env.E2E_OPERATOR_USERNAME!)
    await page.getByLabel('Password', { exact: true }).fill(process.env.E2E_OPERATOR_PASSWORD!)
    const response = page.waitForResponse(r => r.url().endsWith('/api/auth/password/sign-in'))
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    expect((await response).status()).toBe(200)
    await expect(page.getByTestId('operator-book')).toBeVisible({ timeout: 20000 })
  })

  for (const width of [1440, 390]) {
    test(`client filters, all client records, and review drill-downs at ${width}px`, async ({ page }) => {
      test.setTimeout(180000)
      await page.setViewportSize({ width, height: 960 })
      const rows = page.locator('a[data-testid^="operator-client-"]')
      const total = await rows.count()
      expect(total).toBeGreaterThan(0)
      for (const rung of ['registered', 'circle', 'maison']) {
        await page.getByTestId(`operator-ladder-${rung}`).click()
        await expect(page.getByTestId('operator-filter-note')).toContainText(`of ${total}`)
        expect(await rows.count()).toBeLessThan(total)
        await page.getByTestId('operator-filter-clear').click()
        await expect(rows).toHaveCount(total)
      }
      await page.getByRole('button', { name: /^Open requests/ }).click()
      await expect(page.getByRole('button', { name: /^Open requests/ })).toHaveAttribute('aria-pressed', 'true')
      await page.getByTestId('operator-filter-clear').click()
      await page.getByTestId('operator-book-search').fill('Jessica')
      await expect(rows).toHaveCount(1)
      await page.getByTestId('operator-filter-clear').click()
      const clients = await rows.evaluateAll(nodes => nodes.map(n => n.getAttribute('href')!))
      for (const href of clients) {
        await page.locator(`a[data-testid^="operator-client-"][href="${href}"]`).click()
        await expect(page.getByTestId('operator-record')).toBeVisible({ timeout: 15000 })
        await expect(page.getByTestId('operator-storefront-handoff')).toBeVisible()
        for (const disclosure of await page.locator('details').all()) {
          if (await disclosure.isVisible() && await disclosure.getAttribute('open') === null) {
            await disclosure.locator('summary').click()
          }
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false)
        await page.goBack()
        await expect(rows).toHaveCount(total)
      }
      await page.goto('/operator/reviews')
      const reviews = page.locator('a[data-testid^="operator-review-"]')
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByTestId('operator-outcome-filter-pending')).toBeVisible()
      const links = await reviews.evaluateAll(nodes => nodes.map(n => n.getAttribute('href')!))
      expect(links.length).toBeGreaterThan(0)
      for (const href of links) {
        await page.locator(`a[href="${href}"]`).click()
        await expect(page.getByTestId('operator-review-record')).toBeVisible()
        await expect(page.getByTestId('operator-review-client-link')).toBeVisible()
        await page.goBack()
        await expect(reviews.first()).toBeVisible()
      }
    })
  }
})
