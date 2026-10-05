import { expect, test, type Page } from '@playwright/test'

/**
 * Use a dedicated test identity; credentials remain in memory and httpOnly cookies.
 *
 * The sign-in page writes the session of the surface it was opened from: a
 * return to the Operator writes the staff session, anything else the shopper's.
 */
export async function signIn(page: Page, returnTo = '/') {
  const surface = /^\/operator(?:\/|$)/.test(returnTo) ? 'staff' : 'shopper'
  const username = process.env.E2E_TEST_USER_EMAIL
  const password = process.env.E2E_TEST_USER_PASSWORD
  test.skip(!username || !password, 'Dedicated Cognito test credentials are required')
  await page.addInitScript(() => {
    sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true')
  })
  await page.goto(`/signin?returnTo=${encodeURIComponent(returnTo)}`)
  await page.getByLabel('Username', { exact: true }).fill(username!)
  await page.getByLabel('Password', { exact: true }).fill(password!)
  const signedIn = page.waitForResponse(response => response.url().endsWith('/api/auth/password/sign-in'))
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  expect((await signedIn).status()).toBe(200)
  await expect(page).toHaveURL(url => url.pathname === returnTo, { timeout: 30_000 })
  await expect.poll(async () => (await page.request.get(`/api/auth/me?surface=${surface}`)).status()).toBe(200)
  await expect.poll(() => page.evaluate(key => localStorage.getItem(key), `pellier-auth-session:${surface}`)).toBe('1')
  return surface
}
