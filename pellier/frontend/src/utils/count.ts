/** A count as Pellier shows it: thousands separated ("1,284"), so long-tail catalogs read cleanly. */
const COUNT = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })

export function formatCount(value: number): string {
  return COUNT.format(value)
}
