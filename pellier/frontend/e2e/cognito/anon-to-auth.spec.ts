import { expect, test } from '@playwright/test'
import { signIn } from './helpers'

test('sign-in preserves the anonymous and staff authorization boundaries', async ({ page, browser }) => {
  test.skip(!process.env.E2E_TEST_USER_EMAIL || !process.env.E2E_TEST_USER_PASSWORD, 'Dedicated Cognito test credentials are required')
  await page.goto('/operator')
  expect((await page.request.get('/api/auth/me')).status()).toBe(401)
  expect((await page.request.get('/api/user/preferences')).status()).toBe(401)
  // The storefront sign-in writes the shopper session, which the desk never reads.
  await signIn(page, '/')
  expect((await page.request.get('/api/user/preferences')).status()).toBe(200)
  expect((await page.request.get('/api/operator/clients')).status()).toBe(401)
  // From the Operator, the same identity gets a staff session and no staff
  // authority; the shopper session beside it is untouched.
  await signIn(page, '/operator')
  expect((await page.request.get('/api/operator/clients')).status()).toBe(403)
  expect((await page.request.get('/api/user/preferences')).status()).toBe(200)
  const anonymous = await browser.newContext({ baseURL: new URL(page.url()).origin })
  try {
    expect((await anonymous.request.get('/api/auth/me')).status()).toBe(401)
    expect((await anonymous.request.get('/api/user/preferences')).status()).toBe(401)
  } finally {
    await anonymous.close()
  }
})
