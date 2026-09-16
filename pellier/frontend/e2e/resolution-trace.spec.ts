import { expect, test, type Page } from '@playwright/test'

// Real workshop identities stay in process memory, never browser artifacts.
test.use({ trace: 'off', screenshot: 'off', video: 'off' })

async function chooseMarco(page: Page) {
  await page.getByTestId('persona-pill').click()
  await page.getByTestId('persona-card-marco').click()
  await expect(page.getByTestId('persona-pill')).toContainText('Marco')
}

async function signIn(page: Page, username: string, password: string, returnTo: string) {
  await page.goto(`/signin?returnTo=${encodeURIComponent(returnTo)}`)
  await page.getByLabel('Username', { exact: true }).fill(username)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page).not.toHaveURL(/\/signin/, { timeout: 30000 })
  if (returnTo === '/') await page.getByRole('button', { name: 'Skip welcome tour' }).click()
}

test('separate storefront tour preserves the hero and exposes all three recorded examples', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await page.getByRole('button', { name: 'Skip welcome tour' }).click()
  const hero = page.locator('.pellier-hero-media img')
  await expect(hero).toBeVisible()
  const source = await hero.getAttribute('src')
  await page.getByRole('link', { name: 'How Pellier works', exact: true }).click()
  await expect(page).toHaveURL(/\/how-pellier-works$/)
  await expect(page.getByRole('heading', { level: 1 })).toContainText('A considered answer.')
  const loop = page.getByRole('region', { name: 'Recorded Pellier examples', exact: true })
  await expect(loop).toHaveAttribute('data-active-scenario', 'storefront')
  await expect(loop.getByRole('button', { name: /^(Pause|Resume|Replay)$/ })).toHaveCount(0)
  await loop.getByRole('button', { name: 'View all examples' }).click()
  await expect(loop).toHaveAttribute('data-view', 'all')
  await expect(loop.getByText('Hadley Linen Shirt in ivory, $248.', { exact: false })).toBeVisible()
  await expect(loop.getByText('Read-only investigation complete', { exact: true })).toBeVisible()
  await expect(loop.getByText('Blocked by Cedar', { exact: true })).toBeVisible()
  await expect(loop.getByText(/Historical Gateway DENY/)).toBeVisible()
  await expect(loop.locator('[data-step-id]')).toHaveCount(9)
  await page.getByRole('link', { name: 'Back to the collection' }).click()
  await expect(page.locator('.pellier-hero-media img')).toHaveAttribute('src', source!)
  expect(errors).toEqual([])
})

test('recorded examples repeat through storefront, Operator and Cedar with a readable result hold', async ({ page }) => {
  test.setTimeout(60000)
  await page.goto('/observatory/govern')
  const loop = page.getByRole('region', { name: 'Recorded Pellier examples', exact: true })
  await loop.scrollIntoViewIfNeeded()
  await page.mouse.move(0, 0)
  await expect(loop).toHaveAttribute('data-active-scenario', 'storefront')
  await expect(loop.getByText('A grounded recommendation', { exact: true })).toBeVisible({ timeout: 10000 })
  await expect(loop).toHaveAttribute('data-active-scenario', 'operator', { timeout: 10000 })
  await expect(loop.getByText('Read-only investigation complete', { exact: true })).toBeVisible({ timeout: 10000 })
  await expect(loop).toHaveAttribute('data-active-scenario', 'cedar', { timeout: 10000 })
  await expect(loop.getByText('Blocked by Cedar', { exact: true })).toBeVisible({ timeout: 10000 })
  await expect(loop.locator('[data-step-status="denied"]')).toHaveCount(1)
  await page.screenshot({ path: '/tmp/pellier-govern-cedar.png', fullPage: true, animations: 'disabled' })
  await expect(loop).toHaveAttribute('data-active-scenario', 'storefront', { timeout: 10000 })
  await loop.getByRole('button', { name: 'View all examples' }).click()
  await page.mouse.move(0, 0)
  await expect(loop).toHaveAttribute('data-view', 'all')
  await expect(loop.getByText('Blocked by Cedar', { exact: true })).toBeVisible()
})

for (const viewport of [{ width: 1440, height: 900 }, { width: 1280, height: 720 }, { width: 768, height: 1024 }, { width: 390, height: 844 }]) {
  test(`tour and chat stay usable at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.goto('/how-pellier-works')
    await page.getByRole('button', { name: 'View all examples' }).click()
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({ path: `/tmp/pellier-how-${viewport.width}.png`, fullPage: true, animations: 'disabled' })
    await chooseMarco(page)
    await page.keyboard.press('Meta+k')
    const drawer = page.getByTestId('chat-drawer')
    await expect(drawer).toBeVisible()
    await expect(drawer.getByRole('button', { name: 'Close drawer' })).toBeInViewport()
    await expect(drawer.getByRole('heading', { name: 'Ask Pellier.' })).toBeInViewport()
    await expect(drawer.getByRole('textbox', { name: 'Message Pellier' })).toBeInViewport()
    await expect(drawer.locator('.sf-cover-img')).toBeVisible({ timeout: 25000 })
    await expect(drawer.locator('.sf-context')).toContainText('pieces in your current edit', { timeout: 25000 })
    expect(await drawer.locator('.sf-cover-img').evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true)
    expect(await drawer.locator('.sf-cover').evaluate(frame => {
      const { width, height } = frame.getBoundingClientRect()
      return Math.abs(width / height - 16 / 9) < .02
    })).toBe(true)
    const boxes = await page.evaluate(() => ({
      bar: document.querySelector('.pellier-surface-bar')!.getBoundingClientRect().bottom,
      drawer: document.querySelector('.cd-drawer')!.getBoundingClientRect().top,
      bottom: document.querySelector('.cd-drawer')!.getBoundingClientRect().bottom,
      viewport: innerHeight,
    }))
    expect(boxes.drawer).toBeGreaterThanOrEqual(boxes.bar - 1)
    expect(boxes.bottom).toBeLessThanOrEqual(boxes.viewport + 1)
    await page.screenshot({ path: `/tmp/pellier-chat-${viewport.width}.png`, animations: 'disabled' })
    await drawer.getByRole('button', { name: 'Close drawer' }).click()
    await expect(drawer).not.toBeVisible()
  })
}

test('reduced motion shows a complete example and lets the reader choose Cedar directly', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/how-pellier-works')
  const loop = page.getByRole('region', { name: 'Recorded Pellier examples', exact: true })
  await expect(loop.locator('[data-step-id]')).toHaveCount(3)
  await expect(loop.getByText('A grounded recommendation', { exact: true })).toBeVisible()
  await loop.getByRole('button', { name: 'Cedar blocked', exact: true }).click()
  await expect(loop).toHaveAttribute('data-active-scenario', 'cedar')
  await expect(loop.getByText('Blocked by Cedar', { exact: true })).toBeVisible()
  await expect(loop.locator('[data-step-id]')).toHaveCount(3)
})

test('real shopper request persists evidence and replays it in the Observatory', async ({ page }) => {
  test.setTimeout(180000)
  const username = process.env.E2E_GOVERN_USERNAME
  const password = process.env.E2E_GOVERN_PASSWORD
  test.skip(!username || !password, 'Requires the workshop shopper identity.')
  await signIn(page, username!, password!, '/')
  await chooseMarco(page)
  await page.keyboard.press('Meta+k')
  const drawer = page.getByTestId('chat-drawer')
  await expect(drawer).toBeVisible()
  const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/chat/stream'))
  await drawer.getByRole('textbox', { name: 'Message Pellier' }).fill('Find an ivory linen shirt under $250.')
  await drawer.getByRole('button', { name: 'Ask Pellier', exact: true }).click()
  const response = await responsePromise
  expect(response.status()).toBe(200)
  const events = (await response.text()).split('\n').filter(line => line.startsWith('data:')).map(line => JSON.parse(line.slice(5)))
  const completion = events.findLast(event => event.type === 'complete')?.response
  expect(completion?.success).toBe(true)
  expect(events.some(event => event.type === 'tool_call' && event.status === 'completed')).toBe(true)
  const turnId = events.find(event => event.type === 'turn_start').turn_id
  const sessionId = events.find(event => event.type === 'turn_start').session_id
  const ledgerResponse = await page.request.get(`/api/observatory/turns/${turnId}/ledger`)
  expect(ledgerResponse.status()).toBe(200)
  const ledger = await ledgerResponse.json()
  expect(ledger.events.some((event: { eventKind: string; status: string }) => event.eventKind === 'tool' && event.status === 'succeeded')).toBe(true)
  await expect(drawer.getByText('Hadley Linen Shirt', { exact: false }).first()).toBeVisible()
  await drawer.getByRole('button', { name: 'Close drawer' }).click()
  await page.goto(`/observatory/sessions/${sessionId}/chat`)
  const trace = page.getByRole('region', { name: 'Shopper turn trace' })
  await expect(trace).toBeVisible({ timeout: 15000 })
  await trace.getByRole('button', { name: 'Show all' }).click()
  await expect(trace.getByText('Evidence ready to inspect')).toBeVisible()
  expect(await trace.locator('[data-step-id]').count()).toBeGreaterThan(0)
})

test('real Operator investigation streams numbered steps and preserves them in history', async ({ page }) => {
  test.setTimeout(180000)
  const username = process.env.E2E_OPERATOR_USERNAME
  const password = process.env.E2E_OPERATOR_PASSWORD
  test.skip(!username || !password, 'Requires the existing workshop Operator identity.')
  await signIn(page, username!, password!, '/operator/clients/CUST-MARCO')
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
