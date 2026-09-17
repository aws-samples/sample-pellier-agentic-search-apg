import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Performance from './Performance';
vi.mock('../../hooks/useObservatoryData', () => ({ useObservatoryData: () => ({ data: { sampleCount: 123, warmReuseP50: 2939, searchStrategies: [] }, loading: false, error: null }) }));
describe('Recorded latency provenance', () => {
  it('labels the API aggregate as tool latency and does not invent other measurements', async () => {
    render(<MemoryRouter><Performance /></MemoryRouter>);
    await userEvent.click(screen.getByText('Supporting context: recorded tool latency'));
    expect(screen.getByText('2939 ms')).toBeVisible();
    expect(screen.getByText(/not Runtime warm-start latency/)).toBeVisible();
    expect(screen.queryByText('0ms')).toBeNull();
    expect(screen.queryByRole('button', { name: '24h' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Run on Aurora' })).toBeEnabled();
  });
});
