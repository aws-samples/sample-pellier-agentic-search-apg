import { expect, test, type Page } from '@playwright/test'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)

// Live credentials never belong in screenshots, traces, or recordings.
test.use({ trace: 'off', screenshot: 'off', video: 'off', reducedMotion: 'reduce' })
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true')
    sessionStorage.setItem('observatory-spotlight-seen', 'true')
  })
})

async function accessible(page: Page) {
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') })
  const violations = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: typeof import('axe-core') }).axe
    return (await axe.run(document, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] },
    })).violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) }))
  })
  expect(violations, page.url()).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false)
}

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

for (const width of [1440, 768, 390]) {
  test(`expanded reference evidence is readable and keyboard accessible at ${width}px`, async ({ page }) => {
    test.setTimeout(90000)
    await page.setViewportSize({ width, height: 960 })
    await page.goto('/observatory/memory')
    await page.getByText('Run this exercise in the Code Editor', { exact: true }).click()
    const commands = page.getByRole('region', { name: 'Memory exercise commands' })
    await expect(commands).toBeVisible()
    await commands.focus()
    await expect(commands).toBeFocused()
    await accessible(page)

    await page.goto('/observatory/skills')
    const guidance = page.getByRole('region', { name: /skill guidance$/ }).first()
    await expect(guidance).toBeVisible({ timeout: 15000 })
    await guidance.focus()
    await page.keyboard.press('ArrowDown')
    await expect.poll(() => guidance.evaluate(node => node.scrollTop)).toBeGreaterThan(0)
    await accessible(page)

    await page.goto('/observatory/architecture')
    await expect(page.getByRole('button', { name: /^Open Grounding/ })).toBeVisible()
    await accessible(page)
  })
}

test('every architecture brief opens and returns to its index', async ({ page }) => {
  test.setTimeout(120000)
  await page.goto('/observatory/architecture')
  await expect(page.getByRole('button', { name: /^Open Grounding/ })).toBeVisible()
  const names = (await page.getByRole('button', { name: /^Open / }).allTextContents())
    .map(name => name.replace('›', '').trim())
  expect(names.length).toBeGreaterThan(5)
  for (const name of names) {
    await page.getByRole('button', { name, exact: true }).click()
    await expect(page).toHaveURL(/\/observatory\/architecture\/.+/)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await accessible(page)
    await page.goBack()
    await expect(page).toHaveURL(/\/observatory\/architecture$/)
    await expect(page.getByRole('button', { name, exact: true })).toBeVisible()
  }
})

test('tool filters and every tool disclosure expose their input contract', async ({ page }) => {
  test.setTimeout(90000)
  await page.goto('/observatory/tools')
  const rows = page.locator('[data-testid^="tool-row-"]')
  await expect(rows.first()).toBeVisible()
  const total = await rows.count()
  expect(total).toBeGreaterThan(10)
  for (const name of ['Shipped', 'Exercise', 'Read', 'Write', 'All']) {
    await page.getByRole('button', { name: new RegExp(`^${name} \\(`) }).click()
    await expect(rows.first()).toBeVisible()
  }
  await expect(rows).toHaveCount(total)
  for (let i = 0; i < total; i++) {
    await rows.nth(i).click()
    await expect(rows.nth(i)).toHaveAttribute('aria-expanded', 'true')
    await expect(rows.nth(i).locator('code')).toBeVisible()
    await expect(rows.nth(i).getByRole('button', { name: 'Try in discovery' })).toBeVisible()
  }
  const discovery = page.waitForResponse(r => r.url().endsWith('/api/observatory/tools/discover'))
  await rows.last().getByRole('button', { name: 'Try in discovery' }).focus()
  await page.keyboard.press('Enter')
  expect((await discovery).status()).toBe(200)
})

test('skill-card keyboard actions reach the live router', async ({ page }) => {
  await page.goto('/observatory/skills')
  const card = page.getByTestId('skill-card-the-gift-table')
  await card.click()
  await expect(card).toHaveAttribute('aria-pressed', 'true')
  const response = page.waitForResponse(r => r.url().endsWith('/api/observatory/skills/route'))
  await card.getByRole('button', { name: 'Try in router' }).focus()
  await page.keyboard.press('Enter')
  expect((await response).status()).toBe(200)
})

test('search examples and retrieval comparison display actual Aurora results', async ({ page }) => {
  test.setTimeout(180000)
  await page.goto('/observatory/search')
  for (const name of ['Anna · morning ritual', 'Anna · under $100', 'Marco · linen for Goa', 'Lexical anchor']) {
    const response = page.waitForResponse(r => r.url().includes('/api/observatory/search/explain?'))
    await page.getByRole('button', { name, exact: true }).click()
    expect((await response).status()).toBe(200)
    await expect(page.getByRole('button', { name: 'Run on Aurora', exact: true })).toBeEnabled()
  }
  await page.goto('/observatory/performance')
  const comparison = page.waitForResponse(r => r.url().includes('/api/observatory/search-strategies/compare?'))
  await page.getByRole('button', { name: 'Run on Aurora', exact: true }).click()
  const result = await comparison
  expect(result.status()).toBe(200)
  const data = await result.json()
  await expect(page.locator('.retrieval-strategy')).toHaveCount(data.strategies.length)
  expect(data.strategies.length).toBe(4)
  const pools = page.waitForResponse(r => r.url().includes('/api/observatory/search-strategies/micro-eval?'))
  await page.getByTestId('micro-eval-run').click()
  expect((await pools).status()).toBe(200)
  await expect(page.getByRole('table', { name: 'Rerank pool comparison', exact: true })).toBeVisible()
})

test('shopper Memory evidence tabs and saved session drill-downs remain usable', async ({ page }) => {
  test.setTimeout(120000)
  test.skip(!process.env.E2E_GOVERN_USERNAME || !process.env.E2E_GOVERN_PASSWORD,
    'Requires the existing Marco workshop identity.')
  await page.goto('/signin?returnTo=%2Fobservatory%2Fmemory')
  await page.getByLabel('Username', { exact: true }).fill(process.env.E2E_GOVERN_USERNAME!)
  await page.getByLabel('Password', { exact: true }).fill(process.env.E2E_GOVERN_PASSWORD!)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page).toHaveURL(/\/observatory\/memory$/)
  await expect(page.getByRole('tab', { name: 'Preferences', exact: true })).toBeVisible({ timeout: 30000 })
  for (const name of ['Facts', 'Summary', 'Episodic (optional)', 'Preferences']) {
    await page.getByRole('tab', { name, exact: true }).click()
    await expect(page.getByRole('tabpanel', { name, exact: true })).toBeVisible()
  }
  const refreshed = page.waitForResponse(r => r.url().includes('/api/observatory/memory-showcase/'))
  await page.getByRole('button', { name: 'Refresh memory showcase evidence' }).click()
  expect((await refreshed).status()).toBe(200)
  await page.goto('/observatory/sessions')
  const sessions = page.getByRole('button', { name: /^#/ })
  await expect(sessions.first()).toBeVisible({ timeout: 20000 })
  await sessions.first().click()
  await expect(page.getByRole('tab', { name: 'Replay', exact: true })).toBeVisible({ timeout: 25000 })
  const sessionReads: string[] = []
  page.on('request', request => {
    if (request.url().includes('/api/observatory/sessions/')) sessionReads.push(request.url())
  })
  for (const name of ['Evidence', 'Brief', 'Replay']) {
    await page.getByRole('tab', { name, exact: true }).click()
    await expect(page.getByRole('tab', { name, exact: true })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false)
  }
  expect(sessionReads, 'Changing tabs retains the already loaded session').toEqual([])
})

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
        const evidence = page.getByTestId('operator-review-observatory-link')
        if (await evidence.isVisible()) {
          await evidence.click()
          await expect(page).toHaveURL(/\/observatory\//)
          await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
          await page.goBack()
        }
        await page.goBack()
        await expect(reviews.first()).toBeVisible()
      }
    })
  }
})
