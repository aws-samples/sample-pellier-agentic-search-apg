import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ProductionPatterns from './ProductionPatterns';

vi.mock('../../hooks/useObservatoryData', () => ({
  useObservatoryData: () => { throw new Error('Design references must not depend on an unimplemented endpoint'); },
}));

describe('ProductionPatterns design reference', () => {
  it('renders the four contracts without a data endpoint or fixture', () => {
    render(<MemoryRouter><ProductionPatterns /></MemoryRouter>);
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(4);
    expect(screen.getByRole('link', { name: /Read Lab 3/ })).toHaveAttribute('href', '/observatory/labs/managed-agent-path');
    expect(screen.getByRole('link', { name: /Read Lab 4/ })).toHaveAttribute('href', '/observatory/labs/fail-closed-policy');
    expect(screen.queryByText('Shipped')).not.toBeInTheDocument();
  });

  it('distinguishes session history from the isolated continuity experiment', () => {
    render(<MemoryRouter><ProductionPatterns /></MemoryRouter>);
    expect(screen.getByText('anon-{session_id}')).toBeInTheDocument();
    expect(screen.getByText('user-{cognito_sub}-session-{session_id}')).toBeInTheDocument();
    expect(screen.getByText(/zero prior chat events/)).toBeInTheDocument();
    expect(screen.getByText(/sequential replay check/)).toBeInTheDocument();
  });
});
