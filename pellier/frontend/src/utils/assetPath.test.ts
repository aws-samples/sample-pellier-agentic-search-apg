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
    expect(routePath('/observatory/memory')).toBe('/ports/8000/observatory/memory')
  })

  it('uses the 960px WebP derivative when a legacy product source names PNG', async () => {
    vi.stubEnv('BASE_URL', '/')
    const { imageSrc } = await import('./assetPath')
    expect(imageSrc('/products/hero-fresh-2.png')).toBe(
      '/products/hero-fresh-2-960.webp',
    )
  })

  it('uses the same derivative when Aurora already names WebP', async () => {
    vi.stubEnv('BASE_URL', '/')
    const { imageSrc } = await import('./assetPath')
    expect(imageSrc('/products/hero-fresh-2.webp')).toBe(
      '/products/hero-fresh-2-960.webp',
    )
  })

  it('preserves an Aurora image that already names a responsive derivative', async () => {
    vi.stubEnv('BASE_URL', '/')
    const { imageSrc } = await import('./assetPath')
    expect(imageSrc('/products/hero-marco-480.webp')).toBe(
      '/products/hero-marco-480.webp',
    )
  })

  it('preserves an explicit PNG screenshot derivative', async () => {
    vi.stubEnv('BASE_URL', '/')
    const { imageSrc } = await import('./assetPath')
    expect(imageSrc('/products/tour-observatory-top-panel-960.png')).toBe(
      '/products/tour-observatory-top-panel-960.png',
    )
  })

  it('normalizes an already-sized Aurora image before building srcset variants', async () => {
    vi.stubEnv('BASE_URL', '/')
    const { responsiveImageSrcSet } = await import('./assetPath')
    expect(
      responsiveImageSrcSet(
        '/products/hero-marco-960.webp',
        [480, 960, 1600],
        'avif',
      ),
    ).toBe(
      '/products/hero-marco-480.avif 480w, /products/hero-marco-960.avif 960w, /products/hero-marco-1600.avif 1600w',
    )
  })

  it('removes an unsized WebP extension before building AVIF candidates', async () => {
    vi.stubEnv('BASE_URL', '/')
    const { responsiveImageSrcSet } = await import('./assetPath')
    expect(
      responsiveImageSrcSet(
        '/products/marco-italian-linen-camp-shirt.webp',
        [480, 960],
        'avif',
      ),
    ).toBe(
      '/products/marco-italian-linen-camp-shirt-480.avif 480w, /products/marco-italian-linen-camp-shirt-960.avif 960w',
    )
  })

  it('treats the 1122px catalog derivative as concrete, not as a stem', async () => {
    vi.stubEnv('BASE_URL', '/')
    const { imageSrc, responsiveImageSrcSet } = await import('./assetPath')
    expect(imageSrc('/products/theo-glass-carafe-1122.webp')).toBe(
      '/products/theo-glass-carafe-1122.webp',
    )
    expect(
      responsiveImageSrcSet('/products/theo-glass-carafe-1122.webp', [480, 960, 1122], 'webp'),
    ).toBe(
      '/products/theo-glass-carafe-480.webp 480w, ' +
        '/products/theo-glass-carafe-960.webp 960w, ' +
        '/products/theo-glass-carafe-1122.webp 1122w',
    )
  })

  it('does not invent a derivative for a non-product asset', async () => {
    vi.stubEnv('BASE_URL', '/')
    const { imageSrc } = await import('./assetPath')
    expect(imageSrc('/assets/wordmark.png')).toBe('/assets/wordmark.png')
  })
})
