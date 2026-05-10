/**
 * API client for Pellier Backend.
 *
 * Task 5.1 (Challenge 9.3) adds a 401 response interceptor that:
 *   1. Calls /api/auth/refresh on any 401 response.
 *   2. On refresh success, retries the original request exactly once
 *      (flagged via a `_retry` marker on the Axios request config).
 *   3. On refresh failure, calls `openSignInChooser({ returnTo: ... })`
 *      from `utils/auth.ts` so the user lands on `/signin` with all
 *      three providers visible (Req 4.2.5).
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

const API_URL = import.meta.env.VITE_API_URL || ''

/**
 * Extend Axios config with a retry flag. Set on the request before a
 * replay so the interceptor can tell a retried request apart from a
 * fresh one and avoid infinite loops.
 */
interface RetryableAxiosRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
}

/**
 * Shared in-flight refresh promise. When multiple requests 401
 * simultaneously they all await the same /api/auth/refresh call rather
 * than triggering a thundering herd.
 */
let refreshInFlight: Promise<boolean> | null = null

/**
 * Call /api/auth/refresh with the current cookies. Returns true when the
 * server responds 2xx (new cookies set server-side), false otherwise.
 * Exported only for tests.
 */
export async function refreshAuthTokens(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight
  refreshInFlight = (async () => {
    try {
      const res = await fetch('/api/auth/refresh', {
        method: 'POST',
        credentials: 'include',
      })
      return res.ok
    } catch {
      return false
    } finally {
      // Clear immediately after completion so the *next* 401 wave starts
      // a fresh refresh rather than reusing this one's result.
      refreshInFlight = null
    }
  })()
  return refreshInFlight
}

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

    // Request logging — unchanged from before.
    this.client.interceptors.request.use(
      (config) => {
        console.log(`[API] ${config.method?.toUpperCase()} ${config.url}`)
        return config
      },
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

          const refreshed = await refreshAuthTokens()
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
    const response = await this.client.get<HealthCheck>('/health')
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

  // Chat
  async chat(message: string, conversationHistory: Array<{role: string, content: string}> = []): Promise<{
    response: string
    tool_calls: any[]
    model: string
    success: boolean
  }> {
    const response = await this.client.post('/api/chat', {
      message,
      conversation_history: conversationHistory
    })
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
