/**
 * One plain stock line for a product card, as a status tag.
 *
 * Green when stock exists, red when none does, grey when stock was not read.
 * When some warehouses hold the piece and others do not, the line names the
 * cities that do ("In stock in Austin and Portland"), so a Brooklyn shopper
 * learns where it ships from before asking.
 */
import type { TagTone } from '../components/turn/StatusTag'

export interface StockSource {
  /** `product_catalog.quantity`, the catalog's aggregate stock cache. */
  quantity?: number | null
  /** Per-warehouse rows, `city` as the warehouse names it ("Austin, TX"). */
  warehouses?: ReadonlyArray<{ city: string; quantity: number }> | null
}

export interface StockLine {
  tone: TagTone
  label: string
}

/** "Austin, TX" reads as "Austin" on a card. */
function cityName(city: string): string {
  return city.split(',')[0].trim()
}

function joinCities(cities: string[]): string {
  if (cities.length <= 1) return cities.join('')
  return `${cities.slice(0, -1).join(', ')} and ${cities[cities.length - 1]}`
}

export function stockLine(product: StockSource): StockLine {
  const warehouses = product.warehouses ?? []
  if (warehouses.length > 0) {
    const stocked = Array.from(
      new Set(warehouses.filter((row) => row.quantity > 0).map((row) => cityName(row.city))),
    )
    if (stocked.length === 0) return { tone: 'blocked', label: 'Sold out' }
    if (stocked.length === warehouses.length) return { tone: 'good', label: 'In stock' }
    return { tone: 'good', label: `In stock in ${joinCities(stocked)}` }
  }
  if (typeof product.quantity === 'number') {
    return product.quantity > 0
      ? { tone: 'good', label: 'In stock' }
      : { tone: 'blocked', label: 'Sold out' }
  }
  return { tone: 'pending', label: 'Not verified' }
}
