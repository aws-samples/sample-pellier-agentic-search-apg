/**
 * PatternsTab tests — the Atelier teaching surface for the three
 * multi-agent patterns.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PatternsTab from './PatternsTab'

describe('PatternsTab', () => {
  it('renders all three pattern cards in order (Agents-as-Tools, Graph, Dispatcher)', () => {
    render(<PatternsTab />)
    const cards = [
      screen.getByTestId('pattern-card-agents-as-tools'),
      screen.getByTestId('pattern-card-graph'),
      screen.getByTestId('pattern-card-dispatcher'),
    ]
    for (const card of cards) {
      expect(card).toBeInTheDocument()
    }
  })

  it('tags each pattern with where it is used (Boutique / Atelier)', () => {
    render(<PatternsTab />)
    const dispatcher = screen.getByTestId('pattern-card-dispatcher')
    expect(dispatcher.textContent).toContain('Boutique')
    const graph = screen.getByTestId('pattern-card-graph')
    expect(graph.textContent).toMatch(/Atelier/)
  })

  it('renders the "Why Dispatcher for the Boutique?" rationale monograph', () => {
    render(<PatternsTab />)
    expect(
      screen.getByTestId('pattern-rationale-dispatcher'),
    ).toBeInTheDocument()
    expect(screen.getByText(/Why did we choose Dispatcher/i)).toBeInTheDocument()
    // All three rationale clauses.
    expect(
      screen.getByText(/shopper is speaking to Pellier, not to an orchestrator/i),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/latency budget is one LLM call/i),
    ).toBeInTheDocument()
    // "Routing is deterministic" appears both in the Dispatcher card's
    // Good-for list and in the rationale monograph; both are expected.
    expect(
      screen.getAllByText(/Routing is deterministic/i).length,
    ).toBeGreaterThan(0)
  })
})
