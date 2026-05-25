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
