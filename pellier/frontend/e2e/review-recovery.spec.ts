import { expect, test } from '@playwright/test'

test.use({ trace: 'off', reducedMotion: 'reduce' })
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true')
    sessionStorage.setItem('observatory-spotlight-seen', 'true')
  })
})

test('the client book index preserves the Operator sign-in boundary', async ({ page }) => {
  await page.goto('/operator/clients')
  await expect(page).toHaveURL(/\/operator$/)
  await expect(page.getByTestId('operator-root')).toBeVisible()
  await expect(page.getByTestId('operator-sign-in')).toBeVisible()
})

test('inaccessible evidence puts Operator recovery before unobserved outcomes', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/observatory/govern/verification')
  const recovery = page.getByRole('link', { name: 'Sign in as Operator' })
  await expect(recovery).toBeVisible()
  await expect(page.getByText('Not yet proved', { exact: true })).toHaveCount(0)
  const action = await recovery.boundingBox()
  const lesson = await page.locator('.boundary-lessons').boundingBox()
  expect(action!.y + action!.height).toBeLessThanOrEqual(lesson!.y)
  await recovery.click()
  await expect(page.getByText('Sign in to your operator account to continue.')).toBeVisible()
  expect(new URL(page.url()).searchParams.get('returnTo')).toBe('/observatory/govern/verification')
})

test('mobile panels are navigation and do not award completion without evidence', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/observatory/workbench')
  const steps = page.getByRole('navigation', { name: 'Workbench steps' })
  await steps.getByRole('button', { name: /Reconcile/ }).click()
  await expect(steps.locator('[data-state="done"]')).toHaveCount(0)
  await expect(steps.getByRole('button', { name: /Reconcile/ })).toHaveAttribute('aria-current', 'step')
})

for (const width of [1280, 390]) {
  test(`opening all recordings keeps the control and first example in reading order at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 })
    await page.goto('/how-pellier-works')
    const toggle = page.getByRole('button', { name: 'View all three', exact: true })
    await toggle.scrollIntoViewIfNeeded()
    const before = await toggle.boundingBox()
    expect(before!.height).toBeGreaterThanOrEqual(44)
    await toggle.click()
    const expanded = page.getByRole('button', { name: 'Play the sequence', exact: true })
    await expect(expanded).toHaveAttribute('aria-expanded', 'true')
    const after = await expanded.boundingBox()
    const first = await page.locator('.trace-scenario-all > div').first().boundingBox()
    expect(Math.abs(after!.y - before!.y)).toBeLessThan(100)
    expect(first!.y).toBeGreaterThanOrEqual(after!.y)
    expect(first!.y).toBeLessThan(844)
  })
}

test('mobile Govern topics expand on demand and close after navigation', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/observatory/govern/verification')
  const topics = page.getByRole('navigation', { name: 'Govern topics' })
  await expect(topics).toBeHidden()
  await page.getByRole('button', { name: 'Browse Govern topics' }).click()
  await expect(topics).toBeVisible()
  await topics.getByRole('link', { name: 'Cedar policies', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Cedar policies' })).toBeVisible()
  await expect(topics).toBeHidden()
})

test('a simulated authentication outage is recoverable without navigating away', async ({ page }) => {
  // Controlled outage injection exercises the browser state; real Cognito
  // authentication is covered by the separate authenticated journey suite.
  let unavailable = true
  await page.route('**/api/auth/me', route => route.fulfill({
    status: unavailable ? 503 : 401,
    contentType: 'application/json',
    body: JSON.stringify({ error: unavailable ? 'auth_unavailable' : 'auth_failed' }),
  }))
  await page.goto('/operator')
  await expect(page.getByText('Session unavailable', { exact: true })).toBeVisible()
  await expect(page.getByText('We couldn’t check your session. Please try again in a moment.')).toBeVisible()
  unavailable = false
  await page.locator('.pellier-session-notice').getByRole('button', { name: 'Try again' }).click()
  await expect(page.locator('.pellier-session-notice')).toHaveCount(0)
  await expect(page.getByTestId('operator-sign-in')).toBeVisible()
  await expect(page).toHaveURL(/\/operator$/)
})

test('keyboard focus keeps the evidence selector below both sticky bars at 320px', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 })
  // One explicitly synthetic row makes the horizontal table keyboard-focusable.
  // This verifies layout only; the authenticated suite verifies actual receipts.
  await page.route('**/api/observatory/governance/outcomes', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      source: 'browser-layout-check',
      runs: [{
        runId: 'browser-layout-check',
        observedAt: '2026-09-20T00:00:00Z',
        complete: false,
        outcomes: {},
        attempts: [{
          id: 1, case: 'Synthetic layout row; no operation performed',
          outcome: 'inconclusive', control: 'No live evidence',
          toolExecuted: null, dataChanged: null, database: {},
        }],
      }],
    }),
  }))
  await page.goto('/observatory/govern/verification')
  const table = page.getByRole('region', { name: 'Recorded boundary outcomes' })
  await table.focus()
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('Shift+Tab')
  const select = page.getByRole('combobox', { name: 'Evidence run' })
  await expect(select).toBeFocused()
  const selectorBounds = await select.boundingBox()
  const headerBounds = await page.locator('.observatory-topbar').boundingBox()
  expect(selectorBounds!.y).toBeGreaterThanOrEqual(headerBounds!.y + headerBounds!.height)
})
