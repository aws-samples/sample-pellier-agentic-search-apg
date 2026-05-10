/**
 * Preference Extraction — Extracts and aggregates user preferences from queries and conversation history.
 * Used by QueryInsight, ConversationMemoryIndicator, ProactiveSuggestions, PersonalizationRadar.
 */

export interface QueryPreferences {
  budget?: string
  maxPrice?: number
  quality?: string
  category?: string
  features: string[]
  searchStrategy: 'hybrid' | 'semantic' | 'category'
}

export interface ExtractedPreferences {
  categories: string[]
  priceRange: { min?: number; max?: number } | null
  qualityPreference: 'budget' | 'mid-range' | 'premium' | null
  features: string[]
  queryCount: number
  avgPriceSearched: number | null
  topCategory: string | null
}

const CATEGORIES = ['headphone', 'laptop', 'phone', 'camera', 'gaming', 'cable', 'smart home', 'speaker', 'tablet', 'watch', 'keyboard', 'mouse', 'monitor', 'charger']
const FEATURES = ['wireless', 'bluetooth', 'usb-c', 'noise cancelling', 'noise-cancelling', 'noise canceling', 'waterproof', 'portable', 'rechargeable', '4k', 'hdr', 'mechanical', 'ergonomic', 'fast charging']

export function extractPreferencesFromQuery(query: string): QueryPreferences {
  const lower = query.toLowerCase()
  const prefs: QueryPreferences = {
    features: [],
    searchStrategy: 'semantic',
  }

  // Price detection
  const priceMatch = lower.match(/under\s+\$?(\d+)|less\s+than\s+\$?(\d+)|below\s+\$?(\d+)|max\s+\$?(\d+)/)
  if (priceMatch) {
    const amount = priceMatch[1] || priceMatch[2] || priceMatch[3] || priceMatch[4]
    prefs.budget = `Under $${amount}`
    prefs.maxPrice = parseInt(amount)
  } else if (lower.match(/cheap|budget|affordable|inexpensive/)) {
    prefs.budget = 'Budget-friendly'
  } else if (lower.match(/premium|expensive|luxury|high.?end/)) {
    prefs.budget = 'Premium'
  }

  // Quality detection
  if (lower.match(/best|top|recommend|quality|premium|high.?rated|top.?rated/)) {
    prefs.quality = 'High-rated preferred'
  }

  // Category detection
  const foundCategory = CATEGORIES.find(cat => lower.includes(cat))
  if (foundCategory) {
    prefs.category = foundCategory.charAt(0).toUpperCase() + foundCategory.slice(1)
    prefs.searchStrategy = 'hybrid'
  }

  // Feature detection
  for (const feature of FEATURES) {
    if (lower.includes(feature)) {
      prefs.features.push(feature.replace(/[-]/g, ' '))
    }
  }

  // Search strategy inference
  if (prefs.category && !prefs.features.length && !prefs.budget) {
    prefs.searchStrategy = 'category'
  }

  return prefs
}

export function aggregateSessionPreferences(
  conversationHistory: Array<{ role: string; content: string }>
): ExtractedPreferences {
  const categories: string[] = []
  const prices: number[] = []
  const allFeatures: string[] = []
  let queryCount = 0

  for (const msg of conversationHistory) {
    if (msg.role !== 'user') continue
    queryCount++

    const prefs = extractPreferencesFromQuery(msg.content)
    if (prefs.category && !categories.includes(prefs.category)) {
      categories.push(prefs.category)
    }
    if (prefs.maxPrice) {
      prices.push(prefs.maxPrice)
    }
    for (const f of prefs.features) {
      if (!allFeatures.includes(f)) {
        allFeatures.push(f)
      }
    }
  }

  const avgPrice = prices.length > 0
    ? Math.round(prices.reduce((a, b) => a + b, 0) / prices.length)
    : null

  let qualityPreference: ExtractedPreferences['qualityPreference'] = null
  if (avgPrice !== null) {
    if (avgPrice < 50) qualityPreference = 'budget'
    else if (avgPrice < 200) qualityPreference = 'mid-range'
    else qualityPreference = 'premium'
  }

  return {
    categories,
    priceRange: prices.length > 0 ? { min: Math.min(...prices), max: Math.max(...prices) } : null,
    qualityPreference,
    features: allFeatures,
    queryCount,
    avgPriceSearched: avgPrice,
    topCategory: categories.length > 0 ? categories[0] : null,
  }
}
