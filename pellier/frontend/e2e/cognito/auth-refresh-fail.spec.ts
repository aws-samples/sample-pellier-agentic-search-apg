import { expect, test } from '@playwright/test'
import { signIn } from './helpers'

test('a rejected session returns to the current sign-in form with its destination', async ({ page, context }) => {
  await signIn(page, '/observatory/govern/authentication')
  await context.clearCookies({ name: 'access_token' })
  await context.clearCookies({ name: 'refresh_token' })
  const refused = page.waitForResponse(response =>
    response.url().endsWith('/api/auth/refresh') && response.status() === 401)
  await page.reload()
  await refused
  await expect(page).toHaveURL(/\/signin\?returnTo=/)
  expect(new URL(page.url()).searchParams.get('returnTo')).toBe('/observatory/govern/authentication')
  await expect(page.getByLabel('Username', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Password', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Use another sign-in method' })).toBeVisible()
})
