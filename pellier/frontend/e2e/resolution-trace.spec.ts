import { expect, test, type Page } from '@playwright/test'

// Real workshop identities stay in process memory, never browser artifacts.
test.use({ trace: 'off', screenshot: 'off', video: 'off' })

async function signIn(page: Page, username: string, password: string, returnTo: string) {
  await page.goto(`/signin?returnTo=${encodeURIComponent(returnTo)}`)
  await page.getByLabel('Username', { exact: true }).fill(username)
  await page.getByLabel('Password', { exact: true }).fill(password)
  const response = page.waitForResponse(reply => reply.url().endsWith('/api/auth/password/sign-in'))
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  expect((await response).status(), 'Cognito password sign-in must verify a session').toBe(200)
  await expect(page).not.toHaveURL(/\/signin/, { timeout: 30000 })
  if (returnTo === '/') await page.getByRole('button', { name: 'Skip welcome tour' }).click()
}

test('real Operator investigation streams numbered steps and preserves them in history', async ({ page }) => {
  test.setTimeout(180000)
  const username = process.env.E2E_OPERATOR_USERNAME
  const password = process.env.E2E_OPERATOR_PASSWORD
  test.skip(!username || !password, 'Requires the existing workshop Operator identity.')
  await signIn(page, username!, password!, '/operator/clients/CUST-JESSICA')
  await expect(page.getByTestId('operator-record')).toBeVisible({ timeout: 25000 })
  const openChat = page.getByRole('button', { name: 'Open chat', exact: true })
  if (await openChat.isVisible()) await openChat.click()
  const input = page.getByTestId('operator-concierge-input')
  await expect(input).toBeEditable({ timeout: 25000 })
  await input.fill('Summarize this client’s recorded orders and preferences. Read only; do not propose or execute an action.')
  const responsePromise = page.waitForResponse(response =>
    response.url().includes('/api/operator/clients/') && response.url().endsWith('/turns/stream'))
  await page.getByTestId('operator-concierge-ask').click()
  const live = page.getByTestId('operator-concierge-live-activity')
  await expect(live).toBeVisible()
  await expect(live.locator('[data-step-id]').first()).toBeVisible({ timeout: 40000 })
  await expect(page.getByTestId('operator-concierge-pending')).not.toBeVisible({ timeout: 120000 })
  const response = await responsePromise
  expect(response.status()).toBe(200)
  const frames = (await response.text()).split('\n\n').filter(frame => frame.includes('data: ')).map(frame => {
    const lines = frame.split('\n')
    return {
      event: lines.find(line => line.startsWith('event: '))?.slice(7).trim(),
      data: JSON.parse(lines.find(line => line.startsWith('data: '))!.slice(6)),
    }
  })
  expect(frames.find(frame => frame.event === 'answer')?.data.status).toBe('complete')
  expect(frames.some(frame => frame.event === 'step' && frame.data.status === 'complete' && /Aurora/i.test(frame.data.source))).toBe(true)
  expect(frames.some(frame => frame.event === 'error')).toBe(false)
  const saved = page.getByTestId('operator-concierge-investigation').last()
  await expect(saved.getByRole('region', { name: 'Investigation trace' })).toBeVisible()
  expect(await saved.locator('[data-step-id]').count()).toBeGreaterThan(0)
  await page.screenshot({ path: '/tmp/pellier-operator-trace.png', fullPage: true, animations: 'disabled' })
})
