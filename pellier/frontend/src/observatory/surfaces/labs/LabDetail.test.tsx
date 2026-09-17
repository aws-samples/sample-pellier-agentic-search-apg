import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { LAB_EXERCISES } from '../../labs/labCatalog';
import LabDetail from './LabDetail';

function openGuide(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/observatory/labs/:exerciseId" element={<LabDetail />} />
    <Route path="/observatory/guide/:guideId" element={<LabDetail />} />
  </Routes></MemoryRouter>);
}

describe('bundled participant guides', () => {
  it.each(LAB_EXERCISES)('keeps $anchorName steps, recovery, and workbench together', lab => {
    openGuide('/observatory/labs/' + lab.id);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(lab.title);
    expect(screen.getByRole('heading', { name: 'Before you start' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Steps and checkpoints' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Troubleshooting' })).toBeVisible();
    expect(screen.getByRole('link', { name: `Open Lab ${Number(lab.number)} in Workbench` }))
      .toHaveAttribute('href', '/observatory/workbench?lab=' + lab.id);
    expect(screen.getByRole('heading', { level: 1 })).toHaveFocus();
    expect(document.querySelector('main')).toBeNull();
  });

  it('copies the command bytes, without copying the copy button label', async () => {
    const user = userEvent.setup();
    const write = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
    openGuide('/observatory/labs/grounded-inventory');
    const container = document.querySelector('.guide-code')!;
    const expected = container.querySelector('pre')!.textContent!.replace(/\n$/, '');
    await user.click(within(container as HTMLElement).getByRole('button'));
    expect(write).toHaveBeenCalledWith(expected);
    expect(within(container as HTMLElement).getByRole('button')).toHaveTextContent('Copied');
  });

  it('connects the final lab to working summary and cleanup instructions', async () => {
    const user = userEvent.setup();
    openGuide('/observatory/labs/fail-closed-policy');
    await user.click(screen.getByRole('link', { name: 'Summary and cleanup' }));
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Summary');
    expect(screen.getByRole('heading', { name: 'Restore the managed policy baseline' })).toBeVisible();
  });
});
