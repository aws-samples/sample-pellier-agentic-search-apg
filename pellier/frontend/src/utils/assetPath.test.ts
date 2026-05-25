import { afterEach, describe, expect, it, vi } from 'vitest'

describe('assetPath helpers', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('asset() leaves paths unchanged at root base', async () => {
    vi.stubEnv('BASE_URL', '/')
    const { asset } = await import('./assetPath')
    expect(asset('/products/hero.png')).toBe('/products/hero.png')
  })

  it('asset() prefixes workshop CloudFront base', async () => {
    vi.stubEnv('BASE_URL', '/ports/8000/')
    const { asset } = await import('./assetPath')
    expect(asset('/products/hero.png')).toBe('/ports/8000/products/hero.png')
  })

  it('routerBasename() is empty at root', async () => {
    vi.stubEnv('BASE_URL', '/')
    const { routerBasename } = await import('./assetPath')
    expect(routerBasename()).toBe('')
  })

  it('routerBasename() strips trailing slash for Workshop Studio', async () => {
    vi.stubEnv('BASE_URL', '/ports/8000/')
    const { routerBasename } = await import('./assetPath')
    expect(routerBasename()).toBe('/ports/8000')
  })

  it('routePath() prefixes in-app routes for plain anchors', async () => {
    vi.stubEnv('BASE_URL', '/ports/8000/')
    const { routePath } = await import('./assetPath')
    expect(routePath('/atelier/memory')).toBe('/ports/8000/atelier/memory')
  })
})
