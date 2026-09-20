/**
 * API client for Pellier Backend.
 *
 * Task 5.1 (auth utility) adds a 401 response interceptor that:
 *   1. Calls /api/auth/refresh on any 401 response.
 *   2. On refresh success, retries the original request exactly once
 *      (flagged via a `_retry` marker on the Axios request config).
 *   3. On rejected credentials, calls `openSignInChooser({ returnTo: ... })`
 *      from `utils/auth.ts` so the user lands on `/signin` with all
 *      three providers visible (Req 4.2.5). Temporary outages remain
 *      retryable errors and preserve the browser's current page.
 *
 * The retry-once semantics are preserved even when multiple requests
 * fire concurrently by coalescing refreshes onto a shared promise.
 */
import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import {
  SearchQuery,
  SearchResponse,
  Product,
  HealthCheck,
} from './types'
import { openSignInChooser } from '../utils/auth'

import { API_BASE_URL as API_URL } from './apiBase'

/**
 * Extend Axios config with a retry flag. Set on the request before a
 * replay so the interceptor can tell a retried request apart from a
 * fresh one and avoid infinite loops.
 */
interface RetryableAxiosRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
}

import { refreshAuthTokens } from './authRefresh'
export { refreshAuthTokens, AUTH_REFRESH_TIMEOUT_MS } from './authRefresh'

class ApiClient {
  private client: AxiosInstance

  constructor() {
    this.client = axios.create({
      baseURL: API_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
      withCredentials: true,
    })

    this.client.interceptors.request.use(
      (config) => config,
      (error) => {
        console.error('[API] Request error:', error)
        return Promise.reject(error)
      }
    )

    // Response interceptor: log errors AND handle 401 refresh/retry/redirect.
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        if (error.response) {
          console.error('[API] Response error:', error.response.status, error.response.data)
        } else if (error.request) {
          console.error('[API] No response received:', error.request)
        } else {
          console.error('[API] Error:', error.message)
        }

        const original = error.config as RetryableAxiosRequestConfig | undefined

        // Only handle 401s that have a request config (i.e. responses we
        // can replay) and that haven't already been retried.
        const is401 = error.response?.status === 401
        if (is401 && original && !original._retry) {
          original._retry = true

          let refreshed: boolean
          try {
            refreshed = await refreshAuthTokens()
          } catch {
            return Promise.reject(new AxiosError(
              'Sign-in is temporarily unavailable. Please try again.',
              'ERR_AUTH_UNAVAILABLE',
              original,
              undefined,
              { data: { error: 'auth_unavailable' }, status: 503, statusText: 'Service Unavailable', headers: {}, config: original },
            ))
          }
          if (refreshed) {
            // Retry the original request exactly once.
            return this.client.request(original)
          }

          // Refresh failed — fall through to the chooser with a returnTo
          // pinned to the current SPA location (Req 4.2.5). We do not
          // reject before the redirect because the user's page is about
          // to be replaced anyway.
          openSignInChooser({
            returnTo:
              typeof window !== 'undefined'
                ? window.location.pathname + window.location.search
                : '/',
          })
        }

        return Promise.reject(error)
      }
    )
  }

  // Health Check
  async healthCheck(): Promise<HealthCheck> {
    const response = await this.client.get<HealthCheck>('/api/health')
    return response.data
  }

  // Lab 1: Search
  async search(query: SearchQuery): Promise<SearchResponse> {
    const response = await this.client.post<SearchResponse>('/api/search', query)
    return response.data
  }

  async getProduct(productId: number): Promise<Product> {
    const response = await this.client.get<Product>(`/api/products/${productId}`)
    return response.data
  }

  async listProducts(params?: {
    limit?: number
    category?: string
    min_price?: number
    max_price?: number
  }): Promise<Product[]> {
    const response = await this.client.get<Product[]>('/api/products', { params })
    return response.data
  }

  /**
   * Accessor for tests that want to verify the underlying Axios instance
   * (for example to mock adapters). Not part of the public surface.
   */
  get axios(): AxiosInstance {
    return this.client
  }
}

// Export singleton instance
export const apiClient = new ApiClient()
