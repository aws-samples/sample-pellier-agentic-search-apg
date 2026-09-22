/** Keep every Pellier request beneath its deployed application path. */
export const API_BASE_URL: string = (
  import.meta.env.VITE_API_URL ||
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.BASE_URL || '/'
).replace(/\/+$/, '')

/** Prefix application API paths once; leave other URLs unchanged. */
export function apiUrl(path: string): string {
  return /^\/api(?:\/|\?|$)/.test(path) ? `${API_BASE_URL}${path}` : path
}

export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const url = apiUrl(path)
  return init === undefined ? fetch(url) : fetch(url, init)
}
