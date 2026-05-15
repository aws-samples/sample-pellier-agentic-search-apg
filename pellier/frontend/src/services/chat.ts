/**
 * Chat Service - Connects to FastAPI Backend
 * Handles product search and AI chat functionality
 */

const API_BASE_URL =
  import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || ''

/**
 * Get or create session ID for conversation persistence
 */
function getSessionId(): string {
  let sessionId = localStorage.getItem('pellier-session-id')
  if (!sessionId) {
    sessionId = `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    localStorage.setItem('pellier-session-id', sessionId)
  }
  return sessionId
}

// === WIRE IT LIVE (Lab 4a) ===
function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = localStorage.getItem('pellier-access-token')
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}
// === END WIRE IT LIVE ===

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  products?: ChatProduct[]
  suggestions?: string[]
}

export interface ChatProduct {
  id: number
  name: string
  price: number
  image: string
  category?: string
  rating?: number
  reviews?: number
  url?: string
  similarityScore?: number
  quantity?: number
  inStock?: boolean
  originalPrice?: number
  discountPercent?: number
}

export interface AgentExecution {
  agent_steps: Array<{agent: string, action: string, status: string, timestamp: number, duration_ms: number}>
  tool_calls: Array<{tool: string, params?: string, timestamp: number, duration_ms: number, status: string}>
  reasoning_steps: Array<{step: string, content: string, timestamp: number}>
  total_duration_ms: number
  success_rate: number
  /** False when Strands' TracerProvider isn't SDK-backed. UI renders a
   * banner and disables the waterfall instead of synthesizing spans. */
  otel_enabled?: boolean
  /** Actionable failure string from the backend when otel_enabled is
   * false. Rendered verbatim. */
  reason?: string
}

export interface ChatResponse {
  response: string
  products: ChatProduct[]
  suggestions?: string[]
  agent_execution?: AgentExecution
  orchestrator_enabled?: boolean
  token_count?: number
  estimated_cost_usd?: number
}

/**
 * Send a chat message with streaming support
 */
export async function sendChatMessageStreaming(
  query: string,
  conversationHistory: ChatMessage[] = [],
  onUpdate: (data: any) => void,
  workshopMode?: string,
  guardrailsEnabled?: boolean,
  customerId?: string | null,
  pattern?: 'dispatcher' | 'agents_as_tools' | 'graph' | null,
): Promise<ChatResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        message: query,
        conversation_history: conversationHistory.map(msg => ({
          role: msg.role,
          content: msg.content
        })),
        session_id: getSessionId(),
        workshop_mode: workshopMode || null,
        guardrails_enabled: guardrailsEnabled || false,
        customer_id: customerId ?? null,
        pattern: pattern ?? null,
      }),
    })

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`)
    }

    const reader = response.body?.getReader()
    const decoder = new TextDecoder()
    let finalResponse: ChatResponse | null = null
    let lastContent = ''

    if (reader) {
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              onUpdate(data)

              // Track content updates
              if (data.type === 'content') {
                lastContent = data.content
              } else if (data.type === 'content_delta') {
                lastContent += data.delta
              }

              if (data.type === 'complete') {
                finalResponse = {
                  response: data.response.response,
                  products: data.response.products || [],
                  suggestions: data.response.suggestions || [],
                  agent_execution: data.response.agent_execution,
                  token_count: data.response.token_count,
                  estimated_cost_usd: data.response.estimated_cost_usd
                }
              }
            } catch {
              // Partial data, will be completed in next chunk
            }
          }
        }
      }
    }

    return finalResponse || {
      response: lastContent || 'Response completed',
      products: [],
      suggestions: []
    }
  } catch (error) {
    console.error('Streaming chat error:', error)
    throw error
  }
}

/**
 * Send a chat message to the backend and get AI response with products
 */
export async function sendChatMessage(query: string, conversationHistory: ChatMessage[] = [], enableThinking: boolean = false): Promise<ChatResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/chat?enable_thinking=${enableThinking}`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ 
        message: query,
        conversation_history: conversationHistory.map(msg => ({
          role: msg.role,
          content: msg.content
        })),
        session_id: getSessionId()
      }),
    })

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`)
    }

    const data = await response.json()
    
    // Backend already returns formatted products
    const chatProducts: ChatProduct[] = (data.products || []).map((p: any) => ({
        id: p.id ?? p.productId ?? 0,
        name: p.name || p.product_description || '',
        price: p.price || 0,
        image: p.image || p.imgUrl || p.imgurl || '',
        category: p.category || p.category_name,
        rating: p.stars || p.rating,
        reviews: p.reviews,
        url: p.url || p.producturl
      }
    ))

    return {
      response: data.response || 'I found some products for you!',
      products: chatProducts,
      suggestions: data.suggestions || generateSmartSuggestions(query, chatProducts),
      agent_execution: data.agent_execution
    }
  } catch (error) {
    console.error('Chat API error:', error)
    throw error
  }
}

/**
 * Generate smart suggestions based on the search query and results
 */
function generateSmartSuggestions(query: string, products: ChatProduct[]): string[] {
  const lowerQuery = query.toLowerCase()
  
  // Use actual product data to generate relevant suggestions
  if (products.length > 0) {
    const avgPrice = products.reduce((sum, p) => sum + p.price, 0) / products.length
    const categories = [...new Set(products.map(p => p.category).filter(Boolean))]
    const suggestions: string[] = []

    // Price-based follow-up
    if (avgPrice > 100) {
      suggestions.push(`Budget options under $${Math.round(avgPrice / 2)}`)
    } else {
      suggestions.push(`Premium options up to $${Math.round(avgPrice * 3)}`)
    }

    // Category-based follow-up
    if (categories.length > 0) {
      suggestions.push(`More in ${categories[0]}`)
    }

    // Action-based follow-up
    if (products.length >= 2) {
      suggestions.push('Compare the top picks')
    } else {
      suggestions.push("What's trending right now?")
    }

    return suggestions.slice(0, 3)
  }
  
  // Query-type based fallbacks (no products returned)
  if (lowerQuery.includes('watch') || lowerQuery.includes('rolex') || lowerQuery.includes('time')) {
    return ['Luxury watches under $500', 'Best everyday watches', 'Show all watches']
  }
  
  if (lowerQuery.includes('laptop') || lowerQuery.includes('macbook') || lowerQuery.includes('computer')) {
    return ['Best for programming', 'Lightweight laptops', 'Show all laptops']
  }
  
  if (lowerQuery.includes('phone') || lowerQuery.includes('iphone') || lowerQuery.includes('samsung')) {
    return ['Latest smartphones', 'Best phone under $300', 'Show all smartphones']
  }

  if (lowerQuery.includes('shoe') || lowerQuery.includes('sneaker') || lowerQuery.includes('nike')) {
    return ['Running shoes under $100', 'Best rated sneakers', 'Show all shoes']
  }
  
  return ["What's trending?", 'Best rated under $50', 'Show me something surprising']
}

/**
 * Health check for the backend
 */
export async function checkBackendHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/health`)
    return response.ok
  } catch {
    return false
  }
}