/**
 * Client-side helpers for the Tools surface — filters, offline discovery,
 * and example queries when the live endpoint is unavailable.
 */
import type { Tool, ToolDiscoveryResult } from '../../types';

export type ToolFilter = 'all' | 'shipped' | 'exercise' | 'read' | 'write';

export const DISCOVERY_EXAMPLES: Array<{ label: string; query: string }> = [
  { label: 'Catalog search', query: 'find products matching customer preferences' },
  { label: 'Hybrid + rerank', query: 'hybrid search with rerank for thoughtful gifts' },
  { label: 'Compare products', query: 'compare two products side by side' },
  { label: 'Price bands', query: 'price range and value picks for linen shirts' },
  { label: 'Warehouse stock', query: 'check floor stock at Brooklyn warehouse' },
  { label: 'Process return', query: 'start a product return with audit trail' },
];

const OFFLINE_SQL =
  'SELECT name, description, 1 - (embedding <=> query_embedding) AS similarity\nFROM tool_registry\nORDER BY embedding <=> query_embedding\nLIMIT $1;';

export function filterTools(tools: Tool[], filter: ToolFilter): Tool[] {
  switch (filter) {
    case 'shipped':
      return tools.filter((t) => t.status === 'shipped');
    case 'exercise':
      return tools.filter((t) => t.status === 'exercise');
    case 'read':
      return tools.filter((t) => t.mutationType === 'read');
    case 'write':
      return tools.filter((t) => t.mutationType === 'write');
    default:
      return tools;
  }
}

/** Workshop fallback when POST /tools/discover is unreachable. */
export function discoverToolsLocally(
  query: string,
  tools: Tool[],
  limit = 5,
): ToolDiscoveryResult[] {
  const q = query.toLowerCase().trim();
  const tokens = q.split(/\s+/).filter((w) => w.length > 2);

  const scored = tools.map((tool) => {
    const hay = `${tool.functionName} ${tool.description}`.toLowerCase();
    let score = 0;
    if (hay.includes(q)) score += 0.45;
    for (const token of tokens) {
      if (hay.includes(token)) score += 0.12;
    }
    if (tool.functionName.toLowerCase().includes(q.replace(/\s+/g, '_'))) {
      score += 0.35;
    }
    return { tool, similarity: Math.min(0.98, 0.38 + score) };
  });

  return scored
    .sort((a, b) => b.similarity - a.similarity)
    .slice(0, limit)
    .map(({ tool, similarity }, idx) => ({
      rank: idx + 1,
      toolId: String(tool.numeral),
      name: tool.functionName,
      description: tool.description,
      similarity,
      status: tool.status,
    }));
}

export function discoveryQueryForTool(tool: Tool): string {
  const presets: Record<string, string> = {
    find_pieces: 'find products matching customer preferences',
    find_pieces_hybrid: 'hybrid search with rerank for gift-ready pieces',
    explore_collection: 'browse the weekend edit collection',
    side_by_side: 'compare two products side by side',
    style_match: 'pieces that pair with this product',
    whats_trending: 'what is trending in the catalog right now',
    price_intelligence: 'price range for linen shirts',
    floor_check: 'is this sku on the floor at Brooklyn warehouse',
    restock_shelf: 'restock low inventory on the shelf',
    process_return: 'process a customer return with audit',
  };
  return presets[tool.functionName] ?? tool.description;
}

export const OFFLINE_DISCOVERY_SQL = OFFLINE_SQL;
