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
// The Pellier types below are the editorial facade consumed by the new
// home page and the personalization endpoints (`/api/products?personalized=…`
// and the personalized `SearchResponse` shape from design.md). They are named
// with a `Pellier` prefix so they never collide with the legacy types.
// The legacy `/api/search` endpoint keeps its current `SearchResponse` shape;
// personalization endpoints use `PellierSearchResponse`.

export type ReasoningStyle = 'picked' | 'matched' | 'pricing' | 'context'

export interface ReasoningChip {
  style: ReasoningStyle
  text: string
  urgentClause?: string
}

// The eight store departments, as stored in pellier.product_catalog.category.
export type PellierCategory =
  | 'Clothing' | 'Shoes' | 'Bags and travel' | 'Accessories'
  | 'Home' | 'Kitchen and table' | 'Bath and body' | 'Stationery and gifts'

export type PellierBadge = 'EDITORS_PICK' | 'BESTSELLER' | 'JUST_IN'

export interface PellierProduct {
  id: number
  brand: string
  name: string
  color: string
  price: number
  rating: number
  reviewCount: number
  category: PellierCategory
  imageUrl: string
  badge?: PellierBadge
  tags: string[]
  reasoning?: ReasoningChip
  /** Optional CSS object-position override for the card image crop. */
  imagePosition?: string
  /**
   * `product_catalog.quantity` as read with the listing. `null` means the
   * inventory read did not happen; it is never rendered as zero stock.
   */
  quantity?: number | null
  /** Per-warehouse counts for the card's stock line, highest count first. */
  warehouses?: WarehouseStock[]
}

/**
 * One warehouse's on-hand count, straight from `pellier.warehouse_inventory`.
 * Ship windows are the warehouse's configured range in days — a shipping
 * capability, not a delivery promise for this order.
 */
export interface WarehouseStock {
  warehouseId: string
  name: string
  city: string
  quantity: number
  shipWindowMin?: number | null
  shipWindowMax?: number | null
}

/**
 * Live Aurora inventory for one product.
 *
 * `onHand` is `product_catalog.quantity`; `warehouses` is the per-location
 * breakdown. The API reports both as read rather than reconciling them, so
 * the product page must not present one as derived from the other.
 */
export interface ProductAvailability {
  onHand: number
  warehouses: WarehouseStock[]
}

/**
 * `GET /api/products/{id}` response — the card fields plus catalog copy and
 * live stock.
 *
 * `availability: null` means the inventory read did not happen. It must
 * never be rendered as zero stock.
 */
export interface PellierProductDetail {
  id: number
  brand: string
  name: string
  color: string
  price: number
  rating: number
  reviewCount: number
  category: PellierCategory
  imageUrl: string
  badge?: PellierBadge | null
  tags: string[]
  description?: string | null
  availability?: ProductAvailability | null
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

export interface PellierSearchResponse {
  products: PellierProduct[]
  queryEmbeddingMs: number
  searchMs: number
  totalMs: number
}

export type PellierSearchResult = PellierSearchResponse
