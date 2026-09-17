/**
 * LabGrammar tests — one interaction grammar per lab destination.
 *
 * Audit finding D3: every required lab page should present the same three
 * sections (Try / Build / Prove), a persistent "you are here" indicator,
 * exactly one next action, a way back to the Code Editor, and a visible
 * evidence-provenance label.
 *
 * The provenance label is the load-bearing part. `live`, `fixture`,
 * `modeled`, and `unavailable` must be visually and textually distinct,
 * because a fixture value presented like a measurement is the specific
 * confusion the Observatory is supposed to eliminate.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LabGrammar } from './LabGrammar';

function renderGrammar(overrides: Partial<React.ComponentProps<typeof LabGrammar>> = {}) {
  return render(
    <LabGrammar
      labLabel="Lab 1 · Build a PostgreSQL-Grounded Agent"
      try="Ask Marco's Turn 3 in Pellier."
      build="Wire check_inventory between the markers."
      prove="The registry strip reads 17/17 shipped."
      provenance="live"
      proofState="pass"
      nextAction="Re-ask Marco's Turn 3."
      returnAction="Code Editor → agent_tools.py"
      {...overrides}
    />,
  );
}

describe('LabGrammar', () => {
  it('renders all three sections in the same order every time', () => {
    renderGrammar();

    expect(screen.getByText(/Try · in Pellier/i)).toBeInTheDocument();
    expect(screen.getByText(/Build · in the Code Editor/i)).toBeInTheDocument();
    expect(screen.getByText(/Prove · live evidence/i)).toBeInTheDocument();
  });

  it('shows a persistent "you are here" lab indicator', () => {
    renderGrammar();

    expect(
      screen.getByText(/You are here · Lab 1 · Build/i),
    ).toBeInTheDocument();
  });

  it('shows exactly one next action and one way back', () => {
    renderGrammar();

    expect(screen.getByText(/Next:/)).toBeInTheDocument();
    expect(screen.getByText(/Back:/)).toBeInTheDocument();
    // One "Next", not a menu of options.
    expect(screen.getAllByText(/Next:/)).toHaveLength(1);
  });

  it('labels live evidence as measured on this request', () => {
    renderGrammar({ provenance: 'live' });

    expect(screen.getByText('LIVE')).toBeInTheDocument();
    expect(
      screen.getByText(/evidence is live — measured on this request/i),
    ).toBeInTheDocument();
  });

  it('labels fixture evidence as describing no run', () => {
    renderGrammar({ provenance: 'fixture' });

    expect(screen.getByText('FIXTURE')).toBeInTheDocument();
    expect(
      screen.getByText(/illustrative, describes no run/i),
    ).toBeInTheDocument();
  });

  it('labels modeled evidence as calculated rather than observed', () => {
    renderGrammar({ provenance: 'modeled' });

    expect(screen.getByText('MODELED')).toBeInTheDocument();
    expect(screen.getByText(/calculated, not observed/i)).toBeInTheDocument();
  });

  it('points unavailable evidence at the terminal proof instead', () => {
    renderGrammar({ provenance: 'unavailable' });

    expect(screen.getByText('UNAVAILABLE')).toBeInTheDocument();
    expect(
      screen.getByText(/not provisioned — read the terminal proof/i),
    ).toBeInTheDocument();
  });

  it('states a pass/fail/pending proof state unambiguously', () => {
    renderGrammar({ proofState: 'pass' });
    expect(screen.getByText('PASS')).toBeInTheDocument();

    renderGrammar({ proofState: 'fail' });
    expect(screen.getByText('FAIL')).toBeInTheDocument();

    renderGrammar({ proofState: 'pending' });
    expect(screen.getByText('NOT RUN YET')).toBeInTheDocument();
  });

  it('omits the action block when no actions are supplied', () => {
    renderGrammar({ nextAction: undefined, returnAction: undefined });

    expect(screen.queryByText(/Next:/)).toBeNull();
    expect(screen.queryByText(/Back:/)).toBeNull();
  });

});
