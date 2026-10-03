interface CatalogPromptProduct {
  name: string
  price: number
  category?: string
}

export interface CatalogPromptAction {
  label: string
  prompt: string
}

export function productQuickActions(
  product: CatalogPromptProduct,
): CatalogPromptAction[] {
  const name = product.name.trim() || 'this piece'
  const price = Math.max(1, Math.round(product.price))

  return [
    {
      label: 'Build around it',
      prompt: `What current-catalog pieces pair well with ${name}?`,
    },
    {
      label: 'Similar pieces',
      prompt: `Show current-catalog alternatives to ${name} near $${price}.`,
    },
  ]
}

export function catalogTurnFollowUps(
  products: CatalogPromptProduct[],
  fallback: string[],
): string[] {
  if (products.length >= 2) {
    const [first, second] = products
    return [
      `Compare ${first.name} and ${second.name}.`,
      `What current-catalog pieces pair well with ${first.name}?`,
    ]
  }

  if (products.length === 1) {
    return productQuickActions(products[0]).map(action => action.prompt)
  }

  return fallback.slice(0, 3)
}
