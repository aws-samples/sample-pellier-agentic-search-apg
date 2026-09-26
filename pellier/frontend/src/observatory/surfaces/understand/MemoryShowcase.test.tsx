import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MemoryShowcase from './MemoryShowcase';

const { read } = vi.hoisted(() => ({ read: vi.fn() }));
vi.mock('../../hooks/useObservatoryData', () => ({ useObservatoryData: read }));

function snapshot() {
  const panel = { strategyStatus: 'ACTIVE', state: 'waiting', namespace: '/owned/session/', records: [] };
  return { resourceStatus: 'ACTIVE', strategies: { facts: panel, preferences: panel, summary: panel, episodic: panel }, proof: null };
}

function recalledSnapshot() {
  const base = snapshot();
  const record = (kind: string, content: string) => ({
    id: `${kind}-record`,
    kind,
    strategyId: `${kind}-strategy`,
    content,
    raw: JSON.stringify({ content }),
    episode: null,
  });
  const facts = record('facts', 'Theo is choosing ceramics.');
  const preferences = record('preferences', 'Theo prefers natural materials.');
  const summary = record('summary', 'Theo shared his preferences.');
  return {
    ...base,
    strategies: {
      ...base.strategies,
      facts: { ...base.strategies.facts, records: [facts] },
      preferences: { ...base.strategies.preferences, records: [preferences] },
      summary: { ...base.strategies.summary, records: [summary] },
    },
    proof: {
      sourceSessionId: 'first-conversation',
      sourceEventId: 'source-event',
      conversation: [{ role: 'USER', content: 'I prefer natural materials.' }],
      recall: {
        sessionId: 'new-conversation',
        historyEventsLoaded: 0,
        question: 'What would you recommend?',
        answer: 'Consider the returned ceramic bowl.',
        records: [facts, preferences, summary],
        products: [{ productId: 'PRODUCT-01', name: 'Ceramic bowl', price: 48 }],
      },
    },
  };
}

describe('Memory showcase evidence', () => {
  beforeEach(() => read.mockReturnValue({ data: snapshot(), loading: false, error: null, refetch: vi.fn() }));

  it('does not call an active strategy a completed episode', () => {
    render(<MemoryShowcase persona="marco" />);
    fireEvent.click(screen.getByRole('tab', { name: 'Episodic' }));
    expect(screen.getByText('No conversation recorded')).toBeInTheDocument();
    expect(screen.queryByText('Completed episode returned by AgentCore')).not.toBeInTheDocument();
    expect(screen.getByText(/Aurora orders and seeded history do not count/)).toBeInTheDocument();
  });

  it('requires a returned episode and keeps the record identifier inspectable', () => {
    const data = snapshot();
    data.strategies.episodic = { ...data.strategies.episodic, state: 'completed', records: [{ id: 'aws-episode-id', strategyId: 'episodic-strategy', content: 'The gift request concluded.', raw: '<summary>real service output</summary>', episode: { assessment: 'Yes' } }] } as typeof data.strategies.episodic;
    read.mockReturnValue({ data, loading: false, error: null, refetch: vi.fn() });
    render(<MemoryShowcase persona="marco" />);
    fireEvent.click(screen.getByRole('tab', { name: 'Episodic' }));
    expect(screen.getByText('Completed episode returned by AgentCore')).toBeInTheDocument();
    expect(screen.getByText('aws-episode-id')).toBeInTheDocument();
  });

  it('supports keyboard movement between the memory types', () => {
    render(<MemoryShowcase persona="marco" />);
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Facts' }), { key: 'End' });
    expect(screen.getByRole('tab', { name: 'Episodic' })).toHaveAttribute('aria-selected', 'true');
  });

  it('reads the selected identity scope and does not render evidence on error', () => {
    read.mockReturnValue({ data: null, loading: false, error: 'Choose the profile that matches your sign-in.', refetch: vi.fn() });
    render(<MemoryShowcase persona="anna" />);
    expect(read).toHaveBeenCalledWith({ key: 'memory-showcase-anna' });
    expect(screen.getByRole('alert')).toHaveTextContent('matches your sign-in');
    expect(screen.queryByRole('tabpanel')).not.toBeInTheDocument();
  });

  it('leads with preferences and counts required records without waiting for an episode', () => {
    read.mockReturnValue({ data: recalledSnapshot(), loading: false, error: null, refetch: vi.fn() });
    render(<MemoryShowcase persona="theo" />);
    expect(screen.getByRole('tab', { name: 'Preferences' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('3 of 4 required record types returned.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'New conversation' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Episodic' }));
    expect(screen.getByText('Waiting for extraction')).toBeInTheDocument();
  });

  it('preserves the exact supplied context when live preference records change', () => {
    const data = recalledSnapshot();
    data.strategies.preferences.records = [{
      ...data.strategies.preferences.records[0],
      id: 'newer-preference-record',
      content: 'Theo now prefers bright colors.',
    }];
    read.mockReturnValue({ data, loading: false, error: null, refetch: vi.fn() });
    render(<MemoryShowcase persona="theo" />);
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Theo now prefers bright colors.');
    const suppliedContext = screen.getByText('Inspect the exact context supplied').closest('details');
    expect(suppliedContext).toHaveTextContent('Theo prefers natural materials.');
    expect(suppliedContext).toHaveTextContent('preferences-record');
    expect(suppliedContext).not.toHaveTextContent('newer-preference-record');
  });

  it.each([
    { reason: 'prior chat is included', sessionId: 'new-conversation', history: 2 },
    { reason: 'the first session is reused', sessionId: 'first-conversation', history: 0 },
  ])('does not call the recall independent when $reason', ({ sessionId, history }) => {
    const data = recalledSnapshot();
    data.proof.recall.sessionId = sessionId;
    data.proof.recall.historyEventsLoaded = history;
    read.mockReturnValue({ data, loading: false, error: null, refetch: vi.fn() });
    render(<MemoryShowcase persona="theo" />);
    expect(screen.queryByRole('heading', { name: 'New conversation' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Recall result' })).toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent('It cannot establish Memory use in a new conversation.');
  });
});
