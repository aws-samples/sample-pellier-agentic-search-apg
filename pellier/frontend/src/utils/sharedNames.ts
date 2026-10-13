/**
 * Names two or more cards in one grid share ("Linen Overshirt" in olive and in
 * sand). Those cards add their colour under the name so they can be told apart;
 * every other card reads exactly as before.
 */
export function nameKey(name: string): string {
  return name.trim().toLowerCase()
}

export function sharedNames(products: ReadonlyArray<{ name: string }>): Set<string> {
  const counts = new Map<string, number>()
  for (const product of products) {
    const key = nameKey(product.name)
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  return new Set([...counts].filter(([, count]) => count > 1).map(([key]) => key))
}
