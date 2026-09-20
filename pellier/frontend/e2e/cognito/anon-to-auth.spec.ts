import { expect, test } from '@playwright/test'
import { signIn } from './helpers'

test('sign-in preserves the anonymous and staff authorization boundaries', async ({ page, browser }) => {
  test.skip(!process.env.E2E_TEST_USER_EMAIL || !process.env.E2E_TEST_USER_PASSWORD, 'Dedicated Cognito test credentials are required')
  await page.goto('/observatory/govern/authentication')
  expect((await page.request.get('/api/auth/me')).status()).toBe(401)
  expect((await page.request.get('/api/user/preferences')).status()).toBe(401)
  await signIn(page, '/observatory/govern/authentication')
  expect((await page.request.get('/api/user/preferences')).status()).toBe(200)
  // A dedicated shopper test identity has no staff authority.
  expect((await page.request.get('/api/operator/clients')).status()).toBe(403)
  const anonymous = await browser.newContext({ baseURL: new URL(page.url()).origin })
  try {
    expect((await anonymous.request.get('/api/auth/me')).status()).toBe(401)
    expect((await anonymous.request.get('/api/user/preferences')).status()).toBe(401)
  } finally {
    await anonymous.close()
  }
})
