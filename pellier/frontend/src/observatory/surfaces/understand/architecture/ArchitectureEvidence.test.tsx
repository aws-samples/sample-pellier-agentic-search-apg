import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DetailPageShell from './DetailPageShell';
import EvaluationsDetail from './EvaluationsDetail';
import McpDetail from './McpDetail';
import ToolRegistryDetail from './ToolRegistryDetail';

vi.mock('../../../hooks/useObservatoryData', () => ({
  useObservatoryData: () => { throw new Error('Static references must not require live evidence'); },
}));

describe('Architecture evidence boundaries', () => {
  it('labels static state as reference unless explicitly backed by measurements', () => {
    const props = { numeral: 'I', conceptName: 'Reference', category: 'workshop' as const,
      title: 'Example', prose: 'Design facts', cheatSheet: [], children: null };
    const view = render(<MemoryRouter><DetailPageShell {...props} liveState={{ label: 'Static', values: [] }} /></MemoryRouter>);
    expect(screen.getByText('Design reference')).toBeInTheDocument();
    expect(screen.queryByText('Live state')).not.toBeInTheDocument();
    view.rerender(<MemoryRouter><DetailPageShell {...props} liveState={{ label: 'Measured', values: [], measured: true }} /></MemoryRouter>);
    expect(screen.getByText('Live state')).toBeInTheDocument();
  });

  it('does not present invented evaluation scores as results', () => {
    render(<MemoryRouter><EvaluationsDetail /></MemoryRouter>);
    expect(screen.queryByText(/91%|94%|340ms|Avg accuracy/)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Measured performance/ })).toHaveAttribute('href', '/observatory/performance');
  });

  it('renders the managed path and registry contracts without missing-concept fallbacks', () => {
    const view = render(<MemoryRouter><McpDetail /></MemoryRouter>);
    expect(screen.getByText(/Labs 1 and 2 establish an in-process baseline/)).toBeInTheDocument();
    view.rerender(<MemoryRouter><ToolRegistryDetail /></MemoryRouter>);
    expect(screen.getByRole('link', { name: /Open Lab 3/ })).toBeInTheDocument();
    expect(screen.queryByText(/15 of 17|15-tool/)).not.toBeInTheDocument();
  });
});
