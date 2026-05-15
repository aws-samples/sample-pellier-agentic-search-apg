/**
 * Storefront vector search — used by Atelier session Chat follow-ups.
 * POST /api/search runs embed + pgvector against pellier.product_catalog.
 */

export interface StorefrontSearchProduct {
  id: number;
  brand: string;
  name: string;
  color?: string;
  price: number;
  imageUrl: string;
  category?: string;
}

export interface StorefrontSearchResponse {
  products: StorefrontSearchProduct[];
  queryEmbeddingMs: number;
  searchMs: number;
  totalMs: number;
}

export async function searchCatalog(
  query: string,
  limit = 6,
): Promise<StorefrontSearchResponse> {
  const res = await fetch('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: query.trim(), limit }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(detail || `Search failed (${res.status})`);
  }
  return res.json() as Promise<StorefrontSearchResponse>;
}
