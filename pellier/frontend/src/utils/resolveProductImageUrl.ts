import { imageSrc } from './assetPath'

/**
 * Resolve an Aurora product image URL through the one public-asset contract.
 *
 * The storefront never substitutes a different catalog item when a live record
 * is malformed or unavailable. That would make a participant-facing replay
 * look successful while showing evidence for the wrong product.
 */
export function resolveProductImageUrl(imageUrl: string): string {
  return imageSrc(imageUrl) ?? ''
}
