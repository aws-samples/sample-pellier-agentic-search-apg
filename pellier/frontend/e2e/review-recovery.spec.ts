import { expect, test } from '@playwright/test'

test.use({ trace: 'off', contextOptions: { reducedMotion: 'reduce' } })
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true')
  })
})

test('the client book index preserves the Operator sign-in boundary', async ({ page }) => {
  await page.goto('/operator/clients')
  await expect(page).toHaveURL(/\/operator$/)
  await expect(page.getByTestId('operator-root')).toBeVisible()
  await expect(page.getByTestId('operator-sign-in')).toBeVisible()
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
