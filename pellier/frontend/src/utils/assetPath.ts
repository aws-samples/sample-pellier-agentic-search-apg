/**
 * Resolve a public-directory asset path against the Vite base path.
 *
 * In Workshop Studio, CloudFront proxies `/ports/8000/*` to the
 * code-server origin. Vite's `base` config rewrites JS/CSS chunk
 * URLs but NOT hardcoded `src="/products/..."` strings in JSX.
 * This utility prepends the base so images resolve correctly
 * through the reverse proxy.
 *
 * Usage:
 *   <img src={asset('/products/hero-fresh.png')} />
 *
 * Local dev (base = "/"): returns "/products/hero-fresh.png"
 * Workshop Studio (base = "/ports/8000/"): returns "/ports/8000/products/hero-fresh.png"
 */
const BASE = import.meta.env.BASE_URL ?? '/'

export function asset(path: string): string {
  // Strip leading slash from path to avoid double-slash
  const clean = path.startsWith('/') ? path.slice(1) : path
  // BASE always ends with '/' (Vite guarantees this)
  return `${BASE}${clean}`
}

/**
 * React Router basename — leading slash, no trailing slash.
 * Empty string when the app is served from the domain root.
 */
export function routerBasename(): string {
  if (BASE === '/' || BASE === '') return ''
  return BASE.replace(/\/$/, '')
}

/**
 * Prefix an in-app route for plain `<a href>` links outside React Router.
 * Prefer `<Link to="...">` when possible; basename on BrowserRouter
 * handles those automatically.
 */
export function routePath(path: string): string {
  const base = routerBasename()
  const clean = path.startsWith('/') ? path : `/${path}`
  return base ? `${base}${clean}` : clean
}

/**
 * Resolve a product/image ``src`` for an <img>, correct-by-construction:
 *   - root-relative ("/products/x.png") -> base-prefixed via asset()
 *     so it resolves through the CloudFront /ports/8000/ proxy.
 *   - absolute ("http(s)://…") and data URIs -> returned UNCHANGED
 *     (wrapping these in asset() would corrupt them, e.g.
 *     "/ports/8000/https://…").
 *   - empty / undefined -> undefined (caller renders its placeholder).
 *
 * Use this everywhere an <img src> comes from product.image / imageUrl so
 * one rule governs all cards. Seed ``imgurl`` is root-relative, so without
 * this every product image 404s behind the proxy.
 */
export function imageSrc(src: string | undefined | null): string | undefined {
  if (!src) return undefined
  if (src.startsWith('/')) return asset(src)
  return src // http(s):// or data: - pass through untouched
}
