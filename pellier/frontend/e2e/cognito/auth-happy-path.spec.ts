import { expect, test } from '@playwright/test'
import { signIn } from './helpers'

test('password sign-in verifies Cognito identity and protects browser tokens', async ({ page, context }) => {
  await signIn(page, '/observatory/govern/authentication')
  await expect(page.getByText('Validated access token', { exact: true })).toBeVisible()
  const cookies = await context.cookies()
  for (const name of ['access_token', 'refresh_token']) {
    const cookie = cookies.find(item => item.name === name)
    expect(cookie).toMatchObject({ httpOnly: true, secure: true, sameSite: 'Lax' })
  }
  const readable = await page.evaluate(() => ({
    cookies: document.cookie.split(';').map(item => item.split('=')[0].trim()),
    keys: Object.keys(localStorage),
  }))
  expect(readable.cookies).not.toContain('access_token')
  expect(readable.cookies).not.toContain('refresh_token')
  expect(readable.keys).not.toContain('access_token')
  expect(readable.keys).not.toContain('refresh_token')
})
