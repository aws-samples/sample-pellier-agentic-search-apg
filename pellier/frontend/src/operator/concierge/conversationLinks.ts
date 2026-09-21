/** Navigation context only. The server still owns client scope and review terms. */
export function conversationHref(customerId: string, sessionId?: string | null, turnId?: string | null): string {
  const params = new URLSearchParams()
  if (sessionId) params.set('session', sessionId)
  if (sessionId && turnId) params.set('turn', turnId)
  const query = params.size ? `?${params}` : ''
  return `/operator/clients/${encodeURIComponent(customerId)}${query}#operator-concierge`
}

export function conversationReviewHref(reviewId: number, sessionId?: string | null, turnId?: string | null, customerId?: string): string {
  const params = new URLSearchParams()
  if (sessionId && turnId && customerId) {
    params.set('client', customerId)
    params.set('session', sessionId)
    params.set('turn', turnId)
  }
  return `/operator/reviews/${reviewId}${params.size ? `?${params}` : ''}`
}
