import { asset } from './assetPath'

/**
 * Maps fixture / catalog paths that do not exist under `public/products/`
 * to real PNGs shipped in the repo. Keeps Atelier session chat + brief
 * product tiles from 404ing when JSON drifted from asset filenames.
 */
const PRODUCT_IMAGE_ALIASES: Record<string, string> = {
  '/products/marco-pellier-linen-shirt-ecru.png': '/products/fresh-pellier-linen-shirt.png',
  '/products/marco-knit-tee-undyed.png': '/products/marco-cotton-linen-tee.png',
  '/products/marco-linen-pocket-square.png': '/products/anna-monogrammed-napkins.png',
  '/products/marco-washed-cotton-overshirt.png': '/products/marco-linen-overshirt-sage.png',
  '/products/marco-leather-weekender.png': '/products/marco-leather-weekend-holdall.png',
  '/products/anna-botanical-silk-scarf.png': '/products/anna-botanical-scarf.png',
  '/products/anna-fig-candle.png': '/products/fresh-santal-fig-candle.png',
  '/products/theo-woven-mat-set.png': '/products/fresh-solstice-woven-mat-set.png',
}

/**
 * Resolve a product `imageUrl` from session fixtures or API to a URL that
 * loads correctly with Vite `base` (via `asset()`).
 */
export function resolveProductImageUrl(imageUrl: string): string {
  const key = imageUrl.startsWith('/') ? imageUrl : `/${imageUrl}`
  const mapped = PRODUCT_IMAGE_ALIASES[key] ?? key
  return asset(mapped)
}
