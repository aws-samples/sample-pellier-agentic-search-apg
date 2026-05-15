import { describe, expect, it } from 'vitest';
import type { Tool } from '../../types';
import {
  discoverToolsLocally,
  discoveryQueryForTool,
  filterTools,
} from './toolsDiscoveryUtils';

const sampleTools: Tool[] = [
  {
    numeral: 1,
    functionName: 'find_pieces',
    description: 'Semantic product search',
    status: 'shipped',
    mutationType: 'read',
    signature: 'def find_pieces(query: str) -> str',
    usedBy: ['style_advisor'],
    invocationCount: 100,
    version: '1.0',
  },
  {
    numeral: 9,
    functionName: 'process_return',
    description: 'Process a customer return with audit',
    status: 'exercise',
    mutationType: 'write',
    signature: 'def process_return(order_id: str) -> str',
    usedBy: ['curator'],
    invocationCount: 0,
    version: '0.1',
  },
];

describe('toolsDiscoveryUtils', () => {
  it('filters by status and mutation type', () => {
    expect(filterTools(sampleTools, 'shipped')).toHaveLength(1);
    expect(filterTools(sampleTools, 'exercise')).toHaveLength(1);
    expect(filterTools(sampleTools, 'write')).toHaveLength(1);
    expect(filterTools(sampleTools, 'read')).toHaveLength(1);
  });

  it('ranks tools locally for catalog search queries', () => {
    const results = discoverToolsLocally(
      'find products matching customer preferences',
      sampleTools,
    );
    expect(results[0]?.name).toBe('find_pieces');
  });

  it('builds preset discovery queries per tool', () => {
    expect(discoveryQueryForTool(sampleTools[0])).toContain('find products');
    expect(discoveryQueryForTool(sampleTools[1])).toContain('return');
  });
});
