/**
 * LabGrammar — one interaction grammar for every required lab destination.
 *
 * An attendee moves among four surfaces (Workshop Studio, Code Editor,
 * Pellier, Observatory). When each Observatory page explains itself differently,
 * the navigation itself becomes the hard part, and the lesson competes
 * with wayfinding.
 *
 * Every required lab page renders the same three sections in the same
 * order:
 *
 *   Try   — the exact Pellier query or action to perform.
 *   Build — the exact Code Editor file, region, or command.
 *   Prove — live evidence with an unambiguous pass/fail state.
 *
 * Plus the three things that keep an attendee oriented: where they are,
 * what the single next action is, and how to get back to the Code Editor.
 *
 * Evidence provenance uses the vocabulary shared with the backend —
 * `live`, `fixture`, `modeled`, `unavailable` — because a fixture value
 * styled like a measurement is the failure this whole surface exists to
 * avoid.
 */
import type React from 'react';
import { Eyebrow } from './Eyebrow';

/** Shared provenance vocabulary. Matches the backend's labels exactly. */
export type EvidenceProvenance = 'live' | 'fixture' | 'modeled' | 'unavailable';

/** Pass/fail state of the Prove section. `pending` = not yet run. */
export type ProofState = 'pass' | 'fail' | 'pending';

export interface LabGrammarProps {
  /** Persistent "you are here" indicator, e.g. "Lab 2 · Build a PostgreSQL-Grounded Agent". */
  labLabel: string;
  /** What the attendee does in Pellier. */
  try: React.ReactNode;
  /** The exact file, region, or command in the Code Editor. */
  build: React.ReactNode;
  /** Live evidence for this step. */
  prove: React.ReactNode;
  /** Provenance of what `prove` renders. */
  provenance: EvidenceProvenance;
  /** Pass/fail/pending state of the proof. */
  proofState: ProofState;
  /** The single next action. One, not a menu. */
  nextAction?: string;
  /** How to return to the Code Editor or lab guide. */
  returnAction?: string;
}

const PROVENANCE_COPY: Record<
  EvidenceProvenance,
  { label: string; detail: string; color: string }
> = {
  live: {
    label: 'LIVE',
    detail: 'measured on this request',
    color: 'var(--obs-green-1)',
  },
  fixture: {
    label: 'FIXTURE',
    detail: 'illustrative, describes no run',
    color: 'var(--obs-ink-3)',
  },
  modeled: {
    label: 'MODELED',
    detail: 'calculated, not observed',
    color: 'var(--obs-amber-1)',
  },
  unavailable: {
    label: 'UNAVAILABLE',
    detail: 'not provisioned — read the terminal proof',
    color: 'var(--obs-red-1)',
  },
};

const PROOF_COPY: Record<ProofState, { label: string; color: string }> = {
  pass: { label: 'PASS', color: 'var(--obs-green-1)' },
  fail: { label: 'FAIL', color: 'var(--gov-deny-fg)' },
  pending: { label: 'NOT RUN YET', color: 'var(--obs-ink-3)' },
};

const sectionStyle: React.CSSProperties = {
  padding: '12px 14px',
  borderLeft: '2px solid var(--obs-rule-2)',
  marginBottom: '10px',
};

const bodyStyle: React.CSSProperties = {
  fontFamily: 'var(--obs-sans)',
  fontSize: '14px',
  lineHeight: 1.6,
  color: 'var(--obs-ink-1)',
  margin: '6px 0 0',
};

const chipStyle: React.CSSProperties = {
  fontFamily: 'var(--obs-mono)',
  fontSize: '11px',
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  borderRadius: '4px',
  padding: '2px 7px',
  fontWeight: 600,
};

export const LabGrammar: React.FC<LabGrammarProps> = ({
  labLabel,
  try: tryStep,
  build,
  prove,
  provenance,
  proofState,
  nextAction,
  returnAction,
}) => {
  const prov = PROVENANCE_COPY[provenance];
  const proof = PROOF_COPY[proofState];

  return (
    <section
      style={{
        padding: '16px 18px',
        backgroundColor: 'var(--obs-cream-2)',
        border: '1px solid var(--obs-rule-1)',
        borderRadius: '4px',
      }}
      aria-label={`${labLabel} — try, build, prove`}
    >
      {/* You are here. Persistent, so an attendee never has to infer it. */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          flexWrap: 'wrap',
          marginBottom: '10px',
        }}
      >
        <span
          style={{
            ...chipStyle,
            color: 'var(--obs-ink-1)',
            backgroundColor: 'var(--obs-cream-1)',
            border: '1px solid var(--obs-rule-2)',
          }}
        >
          You are here · {labLabel}
        </span>
        <span
          style={{
            ...chipStyle,
            color: prov.color,
            backgroundColor: 'var(--obs-cream-1)',
            border: `1px solid ${prov.color}`,
          }}
          title={prov.detail}
        >
          {prov.label}
        </span>
      </div>

      <div style={sectionStyle}>
        <Eyebrow label="Try · in Pellier" variant="muted" />
        <p style={bodyStyle}>{tryStep}</p>
      </div>

      <div style={sectionStyle}>
        <Eyebrow label="Build · in the Code Editor" variant="muted" />
        <p style={bodyStyle}>{build}</p>
      </div>

      <div style={{ ...sectionStyle, borderLeftColor: proof.color }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            flexWrap: 'wrap',
          }}
        >
          <Eyebrow label="Prove · live evidence" variant="muted" />
          <span
            style={{
              ...chipStyle,
              color: proof.color,
              backgroundColor: 'var(--obs-cream-1)',
              border: `1px solid ${proof.color}`,
            }}
          >
            {proof.label}
          </span>
        </div>
        <p style={bodyStyle}>{prove}</p>
        <p
          style={{
            fontFamily: 'var(--obs-sans)',
            fontSize: '12px',
            color: 'var(--obs-ink-3)',
            margin: '6px 0 0',
          }}
        >
          Evidence is {prov.label.toLowerCase()} — {prov.detail}.
        </p>
      </div>

      {(nextAction || returnAction) && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
            marginTop: '4px',
            paddingLeft: '14px',
          }}
        >
          {/* Exactly one next action. A menu here is a decision an
              attendee has to make instead of learning. */}
          {nextAction && (
            <p
              style={{
                fontFamily: 'var(--obs-sans)',
                fontSize: '13px',
                color: 'var(--obs-ink-1)',
                margin: 0,
              }}
            >
              <strong>Next:</strong> {nextAction}
            </p>
          )}
          {returnAction && (
            <p
              style={{
                fontFamily: 'var(--obs-sans)',
                fontSize: '13px',
                color: 'var(--obs-ink-3)',
                margin: 0,
              }}
            >
              <strong>Back:</strong> {returnAction}
            </p>
          )}
        </div>
      )}
    </section>
  );
};

export default LabGrammar;
