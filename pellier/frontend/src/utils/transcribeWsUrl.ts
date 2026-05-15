/**
 * Resolves the WebSocket URL for Amazon Transcribe streaming (`/ws/transcribe`).
 *
 * **Workshop Studio / CloudFront:** The SPA is served under `import.meta.env.BASE_URL`
 * (e.g. `/ports/5173/`). Browsers must open **same-origin** `wss://` under that prefix
 * so the proxy can upgrade to uvicorn — not `wss://host:8000/...`, which is often
 * unroutable or blocked when only path-based port forwarding exists.
 *
 * **Optional:** `VITE_TRANSCRIBE_WS_URL` — full `ws://` or `wss://` URL for custom gateways.
 */
export function getTranscribeWebSocketUrl(): string {
  const override = import.meta.env.VITE_TRANSCRIBE_WS_URL as string | undefined
  if (override?.trim()) {
    return override.trim()
  }

  const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const base = (import.meta.env.BASE_URL ?? '/').replace(/\/$/, '')
  const path = `${base}/ws/transcribe`.replace(/\/{2,}/g, '/')
  return `${wsProto}//${window.location.host}${path}`
}
