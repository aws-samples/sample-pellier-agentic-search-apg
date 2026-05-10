/**
 * Type definitions for Pellier Frontend
 */

// Product Types
export interface Product {
  productId: number
  product_description: string
  imgurl?: string
  producturl?: string
  stars?: number
  reviews?: number
  price?: number
  category_id?: number
  isbestseller?: boolean
  boughtinlastmonth?: number
  category_name?: string
  quantity?: number
}

export interface ProductSearchResult extends Product {
  similarity_score: number
}

// Search Types
export interface SearchFilters {
  category?: string
  min_price?: number
  max_price?: number
  min_rating?: number
  in_stock?: boolean
}

export interface SearchQuery {
  query: string
  limit?: number
  min_similarity?: number
  filters?: SearchFilters
  search_mode?: string
}

export interface SearchResponse {
  query: string
  total_results: number
  results: ProductSearchResult[]
  search_method: string
  execution_time_ms?: number
}

// Inventory Types
export interface InventoryAnalysis {
  total_products: number
  low_stock_count: number
  out_of_stock_count: number
  average_quantity: number
  low_stock_products: Product[]
  out_of_stock_products: Product[]
}

// Recommendation Types
export interface RecommendationRequest {
  product_id: number
  limit?: number
}

export interface RecommendationResponse {
  source_product: Product
  recommendations: ProductSearchResult[]
}

// Health Check Types
export interface HealthCheck {
  status: string
  database: boolean
  embeddings: boolean
  bedrock: boolean
  timestamp: string
}

// API Error Type
export interface ApiError {
  error: string
  status_code: number
}

// === STOREFRONT TYPES (Requirement 1.2 / Design Data Models) ===
//
// The legacy `Product`, `ProductSearchResult`, `SearchResponse`, etc. above
// wrap the Aurora column layout used by existing components and the current
// `/api/search` endpoint (snake_case plus camelCase, matching the backend's
// historical column names).
//
// The boutique types below are the editorial façade consumed by the new
// home page and the personalization endpoints (`/api/products?personalized=…`
// and the personalized `SearchResponse` shape from design.md). They are named
// with a `Boutique` prefix so they never collide with the legacy types.
// The legacy `/api/search` endpoint keeps its current `SearchResponse` shape;
// personalization endpoints use `BoutiqueSearchResponse`.

import type { Intent as BoutiqueIntent } from '../copy'
export type { BoutiqueIntent }

export type ReasoningStyle = 'picked' | 'matched' | 'pricing' | 'context'

export interface ReasoningChip {
  style: ReasoningStyle
  text: string
  urgentClause?: string
}

export type BoutiqueCategory =
  | 'Linen'
  | 'Dresses'
  | 'Accessories'
  | 'Outerwear'
  | 'Footwear'
  | 'Home'
  | 'Home Decor'
  | 'Apparel'
  | 'Bags & Travel'
  | 'Home Fragrance'
  | 'Watches & Jewelry'
  | 'Beauty'
  | 'Wellness'

export type BoutiqueBadge = 'EDITORS_PICK' | 'BESTSELLER' | 'JUST_IN'

export interface BoutiqueProduct {
  id: number
  brand: string
  name: string
  color: string
  price: number
  rating: number
  reviewCount: number
  category: BoutiqueCategory
  imageUrl: string
  badge?: BoutiqueBadge
  tags: string[]
  reasoning?: ReasoningChip
  /** Optional CSS object-position override for the card image crop. */
  imagePosition?: string
}

export interface User {
  userId: string
  email: string
  givenName: string
}

export type VibeTag =
  | 'minimal'
  | 'bold'
  | 'serene'
  | 'adventurous'
  | 'creative'
  | 'classic'
export type ColorTag = 'warm' | 'neutral' | 'earth' | 'soft' | 'moody'
export type OccasionTag =
  | 'everyday'
  | 'travel'
  | 'evening'
  | 'outdoor'
  | 'slow'
  | 'work'
export type CategoryTag =
  | 'linen'
  | 'footwear'
  | 'outerwear'
  | 'accessories'
  | 'home'
  | 'dresses'

export interface Preferences {
  vibe: VibeTag[]
  colors: ColorTag[]
  occasions: OccasionTag[]
  categories: CategoryTag[]
}

export interface BoutiqueSearchResponse {
  products: BoutiqueProduct[]
  queryEmbeddingMs: number
  searchMs: number
  totalMs: number
}

export type BoutiqueSearchResult = BoutiqueSearchResponse
