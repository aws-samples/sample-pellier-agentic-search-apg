import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
const { explain } = vi.hoisted(() => ({ explain: vi.fn() }));
vi.mock('../../hooks/useSearchExplain', () => ({ useSearchExplain: () => ({ stages: [], params: null, query: '', loading: false, error: null, durationMs: 0, explain }) }));
import Search from './Search';
describe('Mechanism experiment', () => {
  it('uses a handed query only when requested and distinguishes it from a receipt replay', async () => {
    render(<MemoryRouter initialEntries={['/observatory/search?q=linen']}><Search /></MemoryRouter>);
    expect(explain).not.toHaveBeenCalled();
    expect(screen.getByRole('textbox', { name: 'Search explain query' })).toHaveValue('linen');
    expect(screen.getByText(/does not replay a shopper turn/)).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Run on Aurora' }));
    expect(explain).toHaveBeenCalledWith('linen');
  });
});
