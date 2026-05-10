/**
 * Unit tests for the Atelier data layer hooks.
 *
 * Tests verify that useAtelierData correctly loads fixture data,
 * manages loading/error states, and that useToolDiscovery calls
 * the correct endpoint and parses results.
 *
 * **Validates: Requirements 16.1, 16.2**
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useAtelierData } from '../hooks/useAtelierData';
import { useToolDiscovery } from '../hooks/useToolDiscovery';

// ---------------------------------------------------------------------------
// useAtelierData
// ---------------------------------------------------------------------------
describe('useAtelierData', () => {
  it('returns fixture data when source is "fixture"', async () => {
    const { result } = renderHook(() =>
      useAtelierData({ key: 'sessions', source: 'fixture' }),
    );

    // Initially loading
    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Data should be loaded from the sessions fixture
    expect(result.current.data).toBeTruthy();
    expect(result.current.error).toBeNull();
    expect(Array.isArray(result.current.data)).toBe(true);
  });

  it('sets loading state during fetch', async () => {
    const { result } = renderHook(() =>
      useAtelierData({ key: 'agents', source: 'fixture' }),
    );

    // Should start in loading state
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // After loading completes, data should be present
    expect(result.current.data).toBeTruthy();
  });

  it('sets error state when fixture key is invalid', async () => {
    const { result } = renderHook(() =>
      useAtelierData({ key: 'nonexistent-fixture-key', source: 'fixture' }),
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBeTruthy();
    expect(result.current.error).toContain('nonexistent-fixture-key');
    expect(result.current.data).toBeNull();
  });

  it('returns data with refetch function', async () => {
    const { result } = renderHook(() =>
      useAtelierData({ key: 'tools', source: 'fixture' }),
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(typeof result.current.refetch).toBe('function');
    expect(result.current.data).toBeTruthy();
  });

  it('loads different fixture keys correctly', async () => {
    const { result: agentsResult } = renderHook(() =>
      useAtelierData({ key: 'agents', source: 'fixture' }),
    );
    const { result: toolsResult } = renderHook(() =>
      useAtelierData({ key: 'tools', source: 'fixture' }),
    );

    await waitFor(() => {
      expect(agentsResult.current.loading).toBe(false);
      expect(toolsResult.current.loading).toBe(false);
    });

    // Both should have data but they should be different datasets
    expect(agentsResult.current.data).toBeTruthy();
    expect(toolsResult.current.data).toBeTruthy();
    expect(agentsResult.current.data).not.toEqual(toolsResult.current.data);
  });
});

// ---------------------------------------------------------------------------
// useToolDiscovery
// ---------------------------------------------------------------------------
describe('useToolDiscovery', () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    mockFetch.mockReset();
    vi.stubGlobal('fetch', mockFetch);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('calls POST /api/atelier/tools/discover with correct body', async () => {
    const mockResponse = {
      results: [
        {
          rank: 1,
          toolId: 'find_pieces',
          name: 'find_pieces',
          description: 'Search products by query',
          similarity: 0.92,
          status: 'shipped',
        },
      ],
      duration_ms: 42,
      sql: 'SELECT name FROM tool_registry ORDER BY embedding <=> query_embedding LIMIT 5;',
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockResponse),
    });

    const { result } = renderHook(() => useToolDiscovery());

    // Initially no results
    expect(result.current.results).toEqual([]);
    expect(result.current.loading).toBe(false);

    // Trigger discovery
    await act(async () => {
      await result.current.discover('find products for summer');
    });

    // Verify fetch was called with correct endpoint and body
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toBe('/api/atelier/tools/discover');
    expect(options.method).toBe('POST');
    expect(options.headers['Content-Type']).toBe('application/json');

    const body = JSON.parse(options.body);
    expect(body.query).toBe('find products for summer');
    expect(body.limit).toBe(5); // default limit

    // Verify results are parsed
    expect(result.current.results).toHaveLength(1);
    expect(result.current.results[0].name).toBe('find_pieces');
    expect(result.current.durationMs).toBe(42);
    expect(result.current.sql).toContain('SELECT');
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('passes custom limit to the API', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ results: [], duration_ms: 10, sql: '' }),
    });

    const { result } = renderHook(() => useToolDiscovery());

    await act(async () => {
      await result.current.discover('linen products', 3);
    });

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.limit).toBe(3);
  });

  it('sets error state on fetch failure', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'));

    const { result } = renderHook(() => useToolDiscovery());

    await act(async () => {
      await result.current.discover('test query');
    });

    expect(result.current.error).toBe('Network error');
    expect(result.current.results).toEqual([]);
    expect(result.current.loading).toBe(false);
  });

  it('sets error state on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 503,
      statusText: 'Service Unavailable',
    });

    const { result } = renderHook(() => useToolDiscovery());

    await act(async () => {
      await result.current.discover('test query');
    });

    expect(result.current.error).toContain('503');
    expect(result.current.results).toEqual([]);
    expect(result.current.loading).toBe(false);
  });
});
