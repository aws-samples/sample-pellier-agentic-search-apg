/**
 * Prices as the storefront shows them: whole dollars without cents ("$58"),
 * anything with cents to two places ("$49.50"), thousands separated
 * ("$1,284", "$99,999,999.99", the most `numeric(10,2)` holds).
 */
const WHOLE = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
const CENTS = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 })

export function formatPrice(value: number): string {
  return Number.isInteger(value) ? WHOLE.format(value) : CENTS.format(value)
}
