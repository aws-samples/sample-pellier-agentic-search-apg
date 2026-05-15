/**
 * BoutiqueWelcome.resolveCover tests — persona-specific cover
 * resolution for the welcome card.
 *
 * Anna (gift-shopper) gets a pinned gift piece + gift eyebrow.
 * Marco and Fresh fall through to the global standout + time-of-day
 * eyebrow. The helper is pure, so the tests hit it directly without
 * rendering the component.
 */
import { describe, expect, it } from 'vitest'
import { resolveCover } from './BoutiqueWelcome'
import type { PersonaSnapshot } from '../contexts/PersonaContext'
import type { BoutiqueProduct } from '../services/types'
import type { CatalogStats } from '../hooks/useCatalogStats'

function persona(id: string, overrides: Partial<PersonaSnapshot> = {}): PersonaSnapshot {
  return {
    id,
    display_name: id === 'anna' ? 'Anna Chen' : id === 'marco' ? 'Marco Silva' : 'Guest',
    role_tag: '',
    avatar_color: '#000',
    avatar_initial: id[0]?.toUpperCase() ?? 'G',
    customer_id: `cust-${id}`,
    stats: { visits: 0, orders: 0, last_seen_days: null },
    ...overrides,
  }
}

// Tight synthetic catalog with just the pieces the resolver needs to
// find. Keeps the test independent of real showcase-data edits.
const CATALOG: BoutiqueProduct[] = [
  {
    id: 1,
    brand: 'Pellier Editions',
    name: 'Italian Linen Camp Shirt',
    color: 'Indigo',
    price: 128,
    rating: 4.8,
    reviewCount: 214,
    category: 'Linen',
    imageUrl: 'https://example.test/linen.jpg',
    tags: ['linen'],
    reasoning: { style: 'picked', text: 'placeholder' },
  },
  {
    id: 3,
    brand: 'Pellier Home',
    name: 'Beeswax Taper Candles',
    color: 'Natural',
    price: 42,
    rating: 4.9,
    reviewCount: 120,
    category: 'Home',
    imageUrl: 'https://example.test/beeswax.jpg',
    tags: ['home'],
    reasoning: { style: 'picked', text: 'placeholder' },
  },
  {
    id: 8,
    brand: 'Pellier Home',
    name: 'Stoneware Pour-Over Set',
    color: 'Ash Grey',
    price: 165,
    rating: 4.8,
    reviewCount: 210,
    category: 'Home',
    imageUrl: 'https://example.test/pourover.jpg',
    tags: ['home'],
    reasoning: { style: 'picked', text: 'placeholder' },
  },
]

const STATS: CatalogStats = {
  product_count: 444,
  category_count: 12,
  standout_name: 'Italian Linen Camp Shirt',
  standout_category: 'Linen',
  generated_at: '2026-05-01T10:00:00Z',
}

describe('resolveCover', () => {
  it('anna gets the Beeswax Taper Candles and a gift-framed eyebrow regardless of time-of-day', () => {
    const morning = resolveCover(persona('anna'), STATS, 'morning', CATALOG)
    const evening = resolveCover(persona('anna'), STATS, 'evening', CATALOG)

    expect(morning.product.name).toBe('Beeswax Taper Candles')
    expect(morning.eyebrow).toBe('A gift, ready to go')
    expect(evening.product.name).toBe('Beeswax Taper Candles')
    expect(evening.eyebrow).toBe('A gift, ready to go')
  })

  it("anna's gift cover wins even when the catalog standout is set to something else", () => {
    const result = resolveCover(persona('anna'), STATS, 'afternoon', CATALOG)
    // The standout in STATS is the Italian Linen Camp Shirt — Anna
    // should still see her pinned gift piece.
    expect(result.product.name).toBe('Beeswax Taper Candles')
    expect(result.product.name).not.toBe(STATS.standout_name)
  })

  it('theo gets the Stoneware Pour-Over Set and the "Quiet pieces" eyebrow regardless of time-of-day', () => {
    const morning = resolveCover(persona('theo'), STATS, 'morning', CATALOG)
    const evening = resolveCover(persona('theo'), STATS, 'evening', CATALOG)

    expect(morning.product.name).toBe('Stoneware Pour-Over Set')
    expect(morning.eyebrow).toBe('Quiet pieces for slow days')
    expect(evening.product.name).toBe('Stoneware Pour-Over Set')
    expect(evening.eyebrow).toBe('Quiet pieces for slow days')
  })

  it('marco gets the Italian Linen Camp Shirt + "Matched to your thread" regardless of time-of-day', () => {
    const morning = resolveCover(persona('marco'), STATS, 'morning', CATALOG)
    const evening = resolveCover(persona('marco'), STATS, 'evening', CATALOG)

    expect(morning.product.name).toBe('Italian Linen Camp Shirt')
    expect(morning.eyebrow).toBe('Matched to your thread')
    expect(evening.product.name).toBe('Italian Linen Camp Shirt')
    expect(evening.eyebrow).toBe('Matched to your thread')
  })

  it("marco's pinned cover wins even when the catalog standout is something else", () => {
    const offCatalogStats: CatalogStats = {
      ...STATS,
      standout_name: 'Cashmere-Blend Cardigan',
    }
    const result = resolveCover(persona('marco'), offCatalogStats, 'morning', CATALOG)
    expect(result.product.name).toBe('Italian Linen Camp Shirt')
    expect(result.eyebrow).toBe('Matched to your thread')
  })

  it('fresh persona gets the global catalog standout with the time-of-day eyebrow', () => {
    const result = resolveCover(persona('fresh'), STATS, 'evening', CATALOG)
    expect(result.product.name).toBe('Italian Linen Camp Shirt')
    expect(result.eyebrow).toBe("Tonight's standout")
  })

  it('null persona falls through to the global standout', () => {
    const result = resolveCover(null, STATS, 'afternoon', CATALOG)
    expect(result.product.name).toBe('Italian Linen Camp Shirt')
    expect(result.eyebrow).toBe("This afternoon's standout")
  })

  it("falls back to the first catalog entry when stats are missing", () => {
    const result = resolveCover(null, null, 'morning', CATALOG)
    expect(result.product).toBe(CATALOG[0])
    expect(result.eyebrow).toBe("This morning's standout")
  })

  it("anna falls through to the global path if the pinned piece is missing from the catalog", () => {
    const catalogWithoutGift = CATALOG.filter((p) => p.name !== 'Beeswax Taper Candles')
    const result = resolveCover(persona('anna'), STATS, 'morning', catalogWithoutGift)
    expect(result.product.name).toBe('Italian Linen Camp Shirt')
    expect(result.eyebrow).toBe("This morning's standout")
  })

  it("marco falls through to the global path if his pinned piece is missing", () => {
    const catalogWithoutLinen = CATALOG.filter((p) => p.name !== 'Italian Linen Camp Shirt')
    // With the Camp Shirt stripped, standout lookup also fails; we end
    // up on catalog[0] with the TOD eyebrow.
    const result = resolveCover(persona('marco'), STATS, 'morning', catalogWithoutLinen)
    expect(result.product).toBe(catalogWithoutLinen[0])
    expect(result.eyebrow).toBe("This morning's standout")
  })
})
