import { expect, test } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:8000'
const OPERATOR_USERNAME = process.env.E2E_OPERATOR_USERNAME ?? ''
const OPERATOR_PASSWORD = process.env.E2E_OPERATOR_PASSWORD ?? ''

// These checks sign in with live credentials. Do not retain authentication
// requests, form values, or cookies in browser artifacts.
test.use({ trace: 'off', screenshot: 'off', video: 'off' })

test.describe('Operator client storefront handoff', () => {
  test.skip(
    !OPERATOR_USERNAME || !OPERATOR_PASSWORD,
    'Dedicated Operator credentials are required for the client reads',
  )

  // Cookies are scoped to the application origin. Never attach a bearer token
  // to every browser request, including third-party product image requests.
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      sessionStorage.setItem('pellier-storefront-spotlight-seen', 'true')
    })
    await page.goto(`${BASE_URL}/signin?returnTo=%2Foperator`)
    await page.getByLabel('Username', { exact: true }).fill(OPERATOR_USERNAME)
    await page.getByLabel('Password', { exact: true }).fill(OPERATOR_PASSWORD)
    const signedIn = page.waitForResponse(response =>
      response.url().endsWith('/api/auth/password/sign-in'),
    )
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
    expect((await signedIn).status()).toBe(200)
    await expect(page).toHaveURL(new URL('/operator', BASE_URL).toString())
    // Use the browser's loopback handling for Secure cookies, as the app does.
    await expect.poll(() => page.evaluate(async () =>
      (await fetch('/api/auth/me', { credentials: 'include' })).status),
      { timeout: 20000 },
    ).toBe(200)
  })

  test('the live client book stays balanced across all three membership rungs', async ({
    page,
  }) => {
    await page.goto(`${BASE_URL}/operator`)
    await expect(page.getByTestId('operator-book')).toBeVisible()

    for (const rung of ['registered', 'circle', 'maison']) {
      await expect(
        page
          .getByTestId(`operator-ladder-${rung}`)
          .locator('.operator-ladder-count'),
      ).toHaveText('5')
    }
  })

  for (const width of [1440, 768, 390]) {
    test(`live client chat and review navigation remain read-only at ${width}px`, async ({ page }) => {
      const mutations: string[] = []
      page.on('request', request => {
        if (new URL(request.url()).pathname.startsWith('/api/operator/') && request.method() !== 'GET') {
          mutations.push(request.method())
        }
      })
      await page.setViewportSize({ width, height: 960 })
      const row = page.getByTestId('operator-client-jessica')
      await expect(row).toContainText('Open chat')
      await row.click()
      await expect(page).toHaveURL(/CUST-JESSICA#operator-concierge$/)
      await expect(page.getByTestId('operator-concierge-state')).not.toHaveAttribute('data-state', 'loading', { timeout: 60000 })
      await expect(page.getByTestId('operator-concierge-input')).toBeInViewport()
      await page.getByTestId('operator-reviews-link').click()
      await expect(page.getByTestId('operator-reviews')).toBeVisible()
      const reviewLinks = page.locator('a[data-testid^="operator-review-"]')
      if (await reviewLinks.count()) {
        await reviewLinks.first().click()
        await expect(page.getByTestId('operator-review-record')).toBeVisible()
        if (width <= 1000) {
          const browse = page.getByRole('button', { name: 'Browse action queue' })
          await expect(browse).toHaveAttribute('aria-expanded', 'false')
          await browse.click()
          await expect(page.getByRole('textbox', { name: 'Find a review' })).toBeVisible()
          await browse.click()
          await expect(page.getByRole('textbox', { name: 'Find a review' })).toBeHidden()
        }
        await page.getByTestId('operator-review-chat-link').click()
        await expect(page.getByTestId('operator-concierge-input')).toBeInViewport()
      }
      expect(mutations).toEqual([])
      expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false)
    })
  }

  test('Jessica stays a read-only preview and reflects her recorded return evidence', async ({
    page,
  }) => {
    const response = await page.evaluate(async () => {
      const result = await fetch('/api/operator/clients/CUST-JESSICA', { credentials: 'include' })
      return { status: result.status, record: await result.json() }
    })
    expect(response.status).toBe(200)
    const record = response.record
    const count = record.client.returnEvidence.authoritativeReturnCount
    expect(count).toBe(record.returns.length)
    expect(record.client.returnEvidence.supportAssertsReturn).toBe(true)
    // This workshop account may already have completed return exercises.
    // Verify the seeded catchall/robe dispute against actual authoritative rows.
    expect(record.client.returnEvidence.disputedProductIds).toEqual(['41', '42'])
    // A return row is a request; nothing records the parcel arriving, so the
    // ticket's receipt claim stays unconfirmed whatever rows exist.
    expect(record.client.returnEvidence.unconfirmedReturnAssertion).toBe(true)
    const recorded = new Set(
      record.returns.map((row: { productId: string }) => row.productId),
    )
    expect(record.client.returnEvidence.unrecordedDisputedProductIds).toEqual(
      ['41', '42'].filter((id) => !recorded.has(id)),
    )

    await page.goto(
      `${BASE_URL}/operator/clients/CUST-JESSICA`,
    )
    await expect(page.getByTestId('operator-record')).toBeVisible()
    const request = page.getByTestId('operator-service-request')
    await expect(request).toContainText(
      'Return received, refund amount disputed',
    )
    await expect(request).toContainText(`${count} authoritative ${count === 1 ? 'row' : 'rows'}`)
    await expect(request).toHaveAttribute('data-conflict', String(conflict))
    await expect(request).toContainText(
      conflict
        ? 'Reconcile the assertion before promising an outcome.'
        : 'Investigate the request against current records.',
    )

    await page.getByTestId('operator-storefront-handoff').click()
    await expect(page).toHaveURL(/\/\?clientPreview=CUST-JESSICA$/)

    const preview = page.getByTestId('operator-client-preview')
    await expect(preview).toBeVisible()
    await expect(preview).toContainText('Jessica Nakamura')
    await expect(preview).toContainText('Read-only')
    const warning = page.getByTestId('operator-client-preview-evidence-conflict')
    if (conflict) {
      await expect(warning).toContainText(`returns ledger contains ${count} record`)
    } else {
      await expect(warning).toHaveCount(0)
    }
    await expect(page.getByTestId('persona-pill')).toHaveAccessibleName('Select scenario')

    await page.getByTestId('operator-client-preview-record').click()
    await expect(page).toHaveURL(/\/operator\/clients\/CUST-JESSICA$/)
    await expect(page.getByTestId('operator-record')).toBeVisible()
  })

  test('a client preview clears an unrelated shopper persona', async ({
    page,
  }) => {
    await page.goto(BASE_URL)
    await page.getByTestId('persona-pill').click()
    await page.getByTestId('persona-card-marco').click()
    await expect(page.getByTestId('persona-pill')).toContainText('Marco')

    await page.goto(
      `${BASE_URL}/?clientPreview=CUST-JESSICA`,
    )
    await expect(page.getByTestId('operator-client-preview')).toBeVisible()
    await expect(page.getByTestId('persona-pill')).toHaveAccessibleName('Select scenario')
    await expect(page.getByTestId('persona-pill')).not.toContainText('Marco')
  })

  test('a hero handoff performs the canonical persona switch', async ({
    page,
  }) => {
    await page.goto(
      `${BASE_URL}/operator/clients/CUST-MARCO`,
    )
    await expect(page.getByTestId('operator-record')).toBeVisible()

    await page.getByTestId('operator-storefront-handoff').click()
    await expect(page).toHaveURL(new URL('/', BASE_URL).toString())
    await expect(page.getByTestId('persona-pill')).toContainText('Marco')
    await expect(page.getByTestId('operator-client-preview')).toHaveCount(0)
  })
})
