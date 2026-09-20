import { expect, test } from '@playwright/test'
import { signIn } from './helpers'

test('an expired access cookie refreshes through Cognito and retries hydration', async ({ page, context }) => {
  await signIn(page, '/observatory/govern/authentication')
  expect((await context.cookies()).some(cookie => cookie.name === 'refresh_token')).toBe(true)
  await context.clearCookies({ name: 'access_token' })
  const refreshed = page.waitForResponse(response =>
    response.url().endsWith('/api/auth/refresh') && response.status() === 200)
  const verified = page.waitForResponse(response =>
    response.url().endsWith('/api/auth/me') && response.status() === 200)
  await page.reload()
  await refreshed
  await verified
  await expect(page).toHaveURL(/\/observatory\/govern\/authentication$/)
  await expect(page.getByText('Validated access token', { exact: true })).toBeVisible()
})
